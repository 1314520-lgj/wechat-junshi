"""消息区截图 → 谁说了什么 + 什么时候说的 + 是不是表情包。RapidOCR 吃 numpy，不落盘。
（基于 JevChat-Windows，MIT，二次开发：新增 2x 提速、时间识别、表情包/图片识别）"""
import difflib
from content import classify
from media import remember
import re
import time
import hashlib
import copy

import numpy as np
try:
    import cv2
    cv2.setNumThreads(1)  # Avoid unbounded OpenCV worker pools beside OCR/Ollama.
except ImportError:
    pass
from rapidocr_onnxruntime import RapidOCR

from chatapps import DEFAULT, ChatApp

_ENGINE = None
SCALE = 2  # OCR 前缩小倍数：大消息区 2x 提速，框坐标再映射回原图


def refine_native_text(chat, rows, engine):
    """Re-read detected crops from native pixels without repeating detection."""
    cropper = getattr(engine, 'get_crop_img_list', None)
    recognizer = getattr(engine, 'text_rec', None)
    if not callable(cropper) or not callable(recognizer):
        return rows
    try:
        boxes = np.asarray([row[0] for row in rows], dtype=np.float32)
        crops = cropper(chat, boxes.copy())
        recognized, _ = recognizer(crops, False)
        if len(recognized) != len(rows):
            raise ValueError('native OCR row count mismatch')
        output = []
        for row, item in zip(rows, recognized):
            text, confidence = item[:2]
            if not isinstance(text, str) or not text.strip() or not np.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
                raise ValueError('invalid native OCR row')
            output.append((row[0], text, float(confidence)))
        return output
    except Exception:
        # Keep readable evidence but explicitly reduce confidence on failure;
        # no model or guessed correction substitutes for native recognition.
        return [(box, text, min(float(confidence), .49)) for box, text, confidence in rows]


def supplement_gray_lines(chat, rows, engine):
    """Bounded native OCR for centered low-contrast lines missed by detection."""
    recognizer = getattr(engine, 'text_rec', None)
    if not callable(recognizer):
        return rows
    try:
        h,w=chat.shape[:2]
        pixels=chat.astype(int)
        colors,counts=np.unique(chat[::8,::8].reshape(-1,3),axis=0,return_counts=True)
        bg=colors[counts.argmax()].astype(int)
        contrast=np.abs(pixels-bg).sum(-1)
        ink=((contrast>60)&(contrast<360)&(pixels.max(-1)-pixels.min(-1)<25)).astype(np.uint8)
        linked=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((3,28),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(linked,8)
        boxes=[]
        for x,y,width,height,_ in stats[1:]:
            if width<w*.2 or not 5<=height<=60 or not .3<(x+width/2)/w<.7:continue
            region=pixels[y:y+height,x:x+width]
            if (np.abs(region-bg).sum(-1)<=6).mean()<.55:continue
            box=(max(0,x-4),max(0,y-4),min(w,x+width+4),min(h,y+height+4))
            # Existing OCR already owns this region; never add it twice.
            if any(max(0,min(box[2],max(p[0] for p in r[0]))-max(box[0],min(p[0] for p in r[0])))*max(0,min(box[3],max(p[1] for p in r[0]))-max(box[1],min(p[1] for p in r[0])))>.5*(box[2]-box[0])*(box[3]-box[1]) for r in rows):continue
            boxes.append(box)
        boxes=sorted(boxes,key=lambda b:b[1])[-6:]
        if not boxes:return rows
        recognized,_=recognizer([chat[y:y1,x:x1] for x,y,x1,y1 in boxes],False)
        if len(recognized)!=len(boxes):return rows
        added=[]
        for box,item in zip(boxes,recognized):
            text,confidence=item[:2]
            if not isinstance(text,str) or not text.strip() or not np.isfinite(float(confidence)) or not 0<=float(confidence)<=1:continue
            x,y,x1,y1=box
            added.append(([[int(x),int(y)],[int(x1),int(y)],[int(x1),int(y1)],[int(x),int(y1)]],text,float(confidence)))
        return list(rows)+added
    except Exception:
        return rows


def _engine(app: ChatApp = DEFAULT):
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RapidOCR(intra_op_num_threads=4, det_limit_type="max",
                           det_limit_side_len=4000)
    return _ENGINE


def read_title(header, app: ChatApp = DEFAULT):
    """面板头部那一条截图 → 会话名。取最靠上的一行里最靠左的；群聊成员数「(422)」去掉。"""
    res, _ = _engine(app)(header, use_cls=False)
    if not res:
        return ""
    first = min(res, key=lambda r: r[0][0][1])
    row = first[0][0][1] + (first[0][2][1] - first[0][0][1])
    same = [r for r in res if r[0][0][1] < row]
    if not same:
        return ""
    text = min(same, key=lambda r: r[0][0][0])[1]
    return re.sub(r"\s*[（(]\d+[)）]\s*$", "", text.strip())


def who_said(chat, box, app: ChatApp = DEFAULT):
    """按 OCR 框里的颜色分类：平底色占比 <45% = 图片里的字；
    绿底 → me；非绿且对比度 ≥150 → her；其余（灰字）→ gray。"""
    xs, ys = [p[0] for p in box], [p[1] for p in box]
    reg = chat[int(min(ys)):int(max(ys)), int(min(xs)):int(max(xs))].astype(int)
    if reg.size == 0:
        return None, None, 0
    vals, cnt = np.unique(reg.reshape(-1, 3), axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    if cnt.max() / reg.shape[0] / reg.shape[1] < 0.45:
        # Tight OCR boxes can contain mostly antialiased glyphs. Sample the
        # surrounding bubble margin before declaring the text to be media.
        x0,y0,x1,y1=int(min(xs)),int(min(ys)),int(max(xs)),int(max(ys))
        margin=chat[max(0,y0-4):min(chat.shape[0],y1+4),max(0,x0-4):min(chat.shape[1],x1+4)]
        q=(margin.astype(int)//16).reshape(-1,3)
        colors,counts=np.unique(q,axis=0,return_counts=True)
        dominant=colors[counts.argmax()]
        share=counts.max()/max(1,len(q))
        if share < 0.55:
            return None, bg, 0
        pixels=margin.reshape(-1,3)
        bg=np.median(pixels[(pixels.astype(int)//16==dominant).all(axis=1)],axis=0).astype(int)
    diff = np.abs(reg @ [0.299, 0.587, 0.114] - bg @ [0.299, 0.587, 0.114])
    ink_h = best = 0
    for r in (diff > 60).any(axis=1):
        best = best + 1 if r else 0
        ink_h = max(ink_h, best)
    if app.is_me(bg):
        return "me", bg, ink_h
    return ("her" if diff.max() >= 150 else "gray"), bg, ink_h


def similar(a, b):
    """同一段像素挪个位置 OCR 会抖，按相似度判同一条。"""
    if a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75:
        return True
    return len(a) == len(b) >= 3 and sum(x != y for x, y in zip(a, b)) <= 1


def same_observation_row(a,b):
    if a==b:return True
    # Same encoded pixels are stronger evidence than fluctuating OCR text.
    # Preserve repeated posts through ordered overlap, not global image merging.
    return (a[4]=='media_unknown' and b[4]=='media_unknown' and bool(a[5])
            and a[5]==b[5] and a[:2]==b[:2] and a[3]==b[3])


_TIME_RE = re.compile(
    r"^(?:(?:今天|昨天|前天|星期[一二三四五六日天]|周[一二三四五六日天])\s*)?"
    r"(?:上午|下午|晚上|凌晨|早上|中午|深夜)?\s*\d{1,2}:\d{1,2}\s*$"
    r"|^\d{1,2}[-/月]\d{1,2}日?\s*(?:\d{1,2}:\d{1,2})?\s*$")


def is_time_text(text):
    return bool(_TIME_RE.match(str(text or "").strip()))


def white_image_container(region):
    """A large light preview needs an actual varied image patch, not only text."""
    if region.shape[0]<96 or region.shape[1]<96:return False
    pixels=region[::2,::2].astype(int)
    values,counts=np.unique((pixels//32).reshape(-1,3),axis=0,return_counts=True)
    dominant=values[counts.argmax()]
    if dominant.min()<6 or dominant.max()-dominant.min()>1 or counts.max()/len(pixels.reshape(-1,3))<.55:return False
    colored=((pixels.max(-1)-pixels.min(-1)>45)&(np.abs(pixels-dominant*32).sum(-1)>80)).astype(np.uint8)
    try:
        import cv2
        _,_,stats,_=cv2.connectedComponentsWithStats(colored,8)
    except Exception:return False
    miniature_picture=False
    for x,y,w,h,area in stats[1:]:
        if area<24:continue
        patch=pixels[y:y+h,x:x+w]
        colors=len(np.unique((patch//32).reshape(-1,3),axis=0))
        if region.shape[1]>=128 and w>=16 and h>=16 and area>=80 and colors>=6:return True
        if w>=6 and h>=5 and colors>=12:miniature_picture=True
    # A compressed, tall chat screenshot can have only a 14px avatar. Require
    # several miniature text bands as well; a small emoji in normal text fails.
    if miniature_picture and region.shape[0]>=160 and region.shape[0]/region.shape[1]>=1.5:
        ink=((pixels.max(-1)-pixels.min(-1)<35)&(pixels.mean(-1)<dominant.mean()*32-50)).astype(np.uint8)
        linked=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((1,4),np.uint8))
        _,_,bands,_=cv2.connectedComponentsWithStats(linked,8)
        positions=[int(y) for x,y,w,h,area in bands[1:] if w>=6 and 1<=h<=5 and area>=5]
        if len(positions)>=3 and max(positions)-min(positions)>=20:return True
    return False


def find_stickers(chat, pane_bg, exclude_rects, min_w=14, min_h=14):
    """无文字的图片/表情包：非底色连通块（cv2），排除所有 OCR 文本框。
    → [(x0, y0, x1, y1)] 原图坐标。"""
    try:
        import cv2
    except Exception:
        return []
    h, w = chat.shape[:2]
    if h < 40 or w < 40:
        return []
    small = chat[::2, ::2]
    diff = np.abs(small.astype(int) - pane_bg).sum(-1)
    mask = (diff > 36).astype(np.uint8)
    for (x0, y0, x1, y1) in exclude_rects:
        sx0, sy0 = max(0, int(x0) // 2), max(0, int(y0) // 2)
        sx1, sy1 = min(mask.shape[1], int(x1) // 2), min(mask.shape[0], int(y1) // 2)
        mask[sy0:sy1, sx0:sx1] = 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if cw < min_w // 2 or ch < min_h // 2:
            continue
        if area / max(1, cw * ch) < 0.30:
            continue
        # 平底色块（气泡/UI 卡片）不是图片：主色占比高 = 平块；
        # 表情包/图片色彩丰富，没有占 55% 以上的单一颜色
        region = small[y:y + ch, x:x + cw]
        if cw<12 or ch<12:
            # The smaller threshold is for colored emoji, not gray OCR glyphs.
            colored=region.max(-1).astype(int)-region.min(-1).astype(int)>45
            if int(colored.sum())<6 or colored.mean()<.25:continue
        vals, cnt = np.unique(region.reshape(-1, 3), axis=0, return_counts=True)
        if cnt.max() / max(1, region.shape[0] * region.shape[1]) > 0.55:
            dominant=vals[cnt.argmax()].astype(int)
            # Small emoji can be mostly yellow. Plain white/gray and green
            # message bubbles are still excluded; gutter avatars are filtered later.
            if dominant.max()-dominant.min()<45:
                if not white_image_container(chat[y*2:min(h,(y+ch)*2),x*2:min(w,(x+cw)*2)]):continue
            elif dominant[1]>dominant[0]+40 and dominant[1]>dominant[2]+40:continue
        out.append((int(x * 2), int(y * 2), int((x + cw) * 2), int((y + ch) * 2)))
    # 去掉被更大块完全包含的
    kept = []
    for r in out:
        if any(r is not o and o[0] <= r[0] and o[1] <= r[1]
               and o[2] >= r[2] and o[3] >= r[3] for o in out):
            continue
        kept.append(r)
    return kept


def is_avatar_region(rect, width):
    x0,y0,x1,y1=rect
    gutter=min(width*.11,96)
    return (x1-x0 <= 96 and y1-y0 <= 96
            and ((x0+x1)/2 < gutter or (x0+x1)/2 > width-gutter))


def group_card_rows(raw,chat,pane_bg):
    """Join OCR rows only inside a large card with an explicit visible card title."""
    def anchor(row):
        return row[7] in ('group_notice','poll','relay') or row[2].strip() in ('微信转账','微信红包','微信公众号','公众号','小程序')
    if not any(anchor(row) for row in raw):return raw
    try:
        import cv2
        mask=(np.abs(chat[::2,::2].astype(int)-pane_bg).sum(-1)>36).astype(np.uint8)
        _,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
    except Exception:return raw
    grouped=list(raw)
    for x,y,w,h,area in stats[1:]:
        if w<80 or h<50 or area/max(1,w*h)<.5:continue
        top,bottom=int(y*2),int((y+h)*2)
        anchors=[r for r in grouped if anchor(r) and top<=r[3]<bottom]
        if not anchors:continue
        anchor_row=anchors[0]
        # Card geometry is stronger than transient name state: numbered names
        # inside the card are participants, never a new sender for each line.
        rows=[r for r in grouped if r[0]==anchor_row[0] and top<=r[3] and r[4]<=bottom and r[7]!='media_unknown']
        if len(rows)<2:continue
        text='\n'.join(r[2] for r in sorted(rows,key=lambda r:r[3]))
        grouped=[r for r in grouped if r not in rows]
        kind=classify(text,card=True)
        if kind=='text':continue
        grouped.append((anchor_row[0],anchor_row[1],text,top,bottom,anchor_row[5],anchor_row[6],kind))
    return grouped


def prepare_ocr(chat,pane_bg):
    """Avoid recognizing hundreds of names in one large gray system paragraph.

    Keep a visible unknown-system record instead of fabricating a full transcript.
    Normal bubbles, short timestamps and speaker names remain untouched.
    """
    try:
        import cv2
        pixels=chat.astype(int)
        contrast=np.abs(pixels-pane_bg).sum(-1)
        gray=pixels.max(-1)-pixels.min(-1)<25
        ink=((contrast>60)&(contrast<360)&gray).astype(np.uint8)
        linked=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((24,30),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(linked,8)
        regions=[]
        for x,y,w,h,_ in stats[1:]:
            if w<chat.shape[1]*.65 or h<max(140,chat.shape[0]*.18):continue
            surrounding=chat[y:y+h:2,x:x+w:2].astype(int)
            if (np.abs(surrounding-pane_bg).sum(-1)<=6).mean()<.65:continue
            regions.append((max(0,int(x)-2),max(0,int(y)-2),min(chat.shape[1],int(x+w)+2),min(chat.shape[0],int(y+h)+2)))
        if not regions:return chat,[]
        image=chat.copy()
        for x0,y0,x1,y1 in regions:image[y0:y1,x0:x1]=pane_bg
        return image,regions
    except Exception:return chat,[]


def has_color_ink(chat,rect,bg):
    x0,y0,x1,y1=rect
    pixels=chat[y0:y1,x0:x1].astype(int)
    if bg is None or pixels.size==0:return False
    colored=(pixels.max(-1)-pixels.min(-1)>45)&(np.abs(pixels-bg).sum(-1)>100)
    # Antialiased black glyphs on green bubbles inherit the background hue.
    # Treat a different hue as colored content, not ordinary font smoothing.
    bg_chroma=np.asarray(bg,dtype=float)-np.mean(bg)
    bg_norm=np.linalg.norm(bg_chroma)
    if bg_norm>20:
        chroma=pixels-pixels.mean(-1,keepdims=True)
        norm=np.linalg.norm(chroma,axis=-1)
        cosine=(chroma*bg_chroma).sum(-1)/np.maximum(1,norm*bg_norm)
        colored&=cosine<.9
    return int(colored.sum())>=20


def inline_container(chat,rect,bg):
    """Find the flat text bubble surrounding colored inline glyphs."""
    try:
        import cv2
        mask=(np.abs(chat.astype(int)-bg).sum(-1)<=6).astype(np.uint8)
        _,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
        candidates=[(int(x),int(y),int(x+w),int(y+h)) for x,y,w,h,_ in stats[1:]
                    if x<=rect[0] and y<=rect[1] and x+w>=rect[2] and y+h>=rect[3]
                    and h<=max(120,chat.shape[0]*.2) and w>=rect[2]-rect[0]]
        return min(candidates,key=lambda r:(r[2]-r[0])*(r[3]-r[1])) if candidates else rect
    except Exception:return rect


def scroll_media_matches(previous, current, old_evidence, evidence):
    """Observation alignment only: two unique exact anchors + identical avatar/media pixels.
    Never merges people, confirms names, or equates changed media frames.
    """
    def rect(items,i):
        r=items[i].get('rect') if i<len(items) else None
        return r if isinstance(r,(list,tuple)) and len(r)==4 else None
    def anchor(i,j):
        old,row=previous[i],current[j]
        if old==row:return True
        if old[4]!='media_unknown' or row[4]!='media_unknown' or not old[5] or old[0]!=row[0] or old[3:]!=row[3:]:return False
        avatar=old_evidence[i].get('avatar_crop_id') if i<len(old_evidence) else None
        return bool(avatar and j<len(evidence) and avatar==evidence[j].get('avatar_crop_id') and not old_evidence[i].get('boundary_truncated_candidate') and not evidence[j].get('boundary_truncated_candidate'))
    shifts=[]
    for i,row in enumerate(previous):
        js=[j for j in range(len(current)) if anchor(i,j)]
        if len(js)!=1:continue
        j=js[0]
        if sum(anchor(k,j) for k in range(len(previous)))!=1:continue
        a,b=rect(old_evidence,i),rect(evidence,j)
        if a and b and a[0]==b[0] and a[2]==b[2] and a[3]-a[1]==b[3]-b[1]:shifts.append(b[1]-a[1])
    if len(shifts)<2 or max(shifts)-min(shifts)>3:return set()
    agreeing=[d for d in shifts if sum(abs(d-other)<=3 for other in shifts)>=2]
    if not agreeing:return set()
    # Competing translations must not supply an ambiguous match.
    if max(agreeing)-min(agreeing)>3:return set()
    delta=sum(agreeing)/len(agreeing);matched=set()
    for j,row in enumerate(current):
        if row[4]!='media_unknown' or not row[5]:continue
        candidates=[i for i,old in enumerate(previous) if old[0]==row[0] and old[3:]==row[3:]]
        peers=[r for r in current if r[0]==row[0] and r[3:]==row[3:]]
        if len(candidates)!=1 or len(peers)!=1:continue
        i=candidates[0];a,b=rect(old_evidence,i),rect(evidence,j)
        if not a or not b or not (a[0]==b[0] and a[2]==b[2] and a[3]-a[1]==b[3]-b[1] and abs(b[1]-a[1]-delta)<=3):continue
        avatar=old_evidence[i].get('avatar_crop_id')
        if avatar and avatar==evidence[j].get('avatar_crop_id') and not old_evidence[i].get('boundary_truncated_candidate') and not evidence[j].get('boundary_truncated_candidate'):matched.add(j)
    return matched


class Reader:
    """一个会话一个 Reader：lh/seen 各自算，切走再切回不会把旧消息当新的重报。"""

    def __init__(self, app: ChatApp = DEFAULT):
        self.app = app
        self.ocr = _engine(app)
        self.lh = None
        self.seen = []
        self.previous = []
        self.media_refs = {}
        self.new_media_ids = []
        self.last_boxes = []
        self.last_ms = 0
        self.last_metrics = {}
        self._ocr_cache = None
        self.ocr_cache_hit = False
        self._tiny_batch = []

    def _ocr(self, chat):
        """2x 缩小识别（快），空结果且原图够大时退回原分辨率。→ 原图坐标的 [(box, text)]。"""
        t0 = time.perf_counter()
        # Cache only lexical OCR, never message identity, attribution or evidence.
        # Exact pixels, shape and dtype; one entry per Reader, bounded and expiring.
        fingerprint = (chat.shape, str(chat.dtype), hashlib.sha256(chat.tobytes()).digest())
        cached = self._ocr_cache
        self.ocr_cache_hit = bool(cached and cached[0] == fingerprint and t0 - cached[1] < 60)
        if self.ocr_cache_hit:
            result = copy.deepcopy(cached[2])
            self.last_ms = int((time.perf_counter() - t0) * 1000)
            return result
        target = chat
        scale = 1
        if min(chat.shape[:2]) >= 900:
            target = chat[::SCALE, ::SCALE]
            scale = SCALE
        res, _ = self.ocr(target, use_cls=False)
        if not res and scale > 1:
            res, _ = self.ocr(chat, use_cls=False)
            scale = 1
        self.last_ms = int((time.perf_counter() - t0) * 1000)
        result = [([(p[0] * scale, p[1] * scale) for p in box], text, conf)
                  for box, text, conf in res or []] if scale > 1 else (res or [])
        # Small-font recognition must use original pixels, even when detection
        # used the faster reduced frame. This is local OCR, not another model call.
        if scale > 1 and result:
            result = refine_native_text(chat, result, self.ocr)
        if scale > 1:
            result = supplement_gray_lines(chat, result, self.ocr)
        self.last_ms = int((time.perf_counter() - t0) * 1000)
        self._ocr_cache = (fingerprint, time.perf_counter(), copy.deepcopy(result))
        return result

    def read(self, chat, pane_bg):
        """→ [(who, name, text, y, time, kind)]，同一气泡多行已合并；
        kind ∈ text/sticker，time = 该消息上方的灰字时间（可能 None）。"""
        self.last_boxes = []
        self.media_refs = {}
        self._tiny_batch = []
        read_started = time.perf_counter()
        W = chat.shape[1]
        prepared,system_regions=prepare_ocr(chat,pane_bg)
        res = self._ocr(prepared)
        name, cur_time, raw = None, None, []
        names=[]; timestamps=[];inline_regions={}
        visual_regions=find_stickers(chat,pane_bg,[])
        avatar_regions=[r for r in visual_regions if is_avatar_region(r,W)]
        media_regions=[r for r in visual_regions if not is_avatar_region(r,W)]
        containers=[]
        for region in media_regions:
            x0,y0,x1,y1=region
            # A visible source footer keeps structured cards on their existing path.
            footers=('微信转账','微信红包','微信公众号','公众号','小程序')
            has_footer=any(text.strip() in footers and x0<=min(p[0] for p in box) and max(p[0] for p in box)<=x1
                           and y1-max(30,(y1-y0)*.2)<=min(p[1] for p in box) and max(p[1] for p in box)<=y1
                           for box,text,_ in res)
            if has_footer:self.last_boxes.append(region+('card',''))
            else:containers.append(region)
        for box, text, confidence in sorted(res, key=lambda r: r[0][0][1]):
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            rect = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
            container=next((r for r in containers if r[0]<=rect[0] and r[1]<=rect[1] and r[2]>=rect[2] and r[3]>=rect[3]),None)
            if container:
                side='me' if (container[0]+container[2])/2/W>.55 else 'her'
                if container[1] not in self.media_refs:
                    self.media_refs[container[1]]=remember(chat,container)
                    self.last_boxes.append(container+('media_unknown',text))
                raw.append((side,name if side=='her' else None,text.strip(),container[1],container[3],0,cur_time,'media_unknown'))
                continue
            kind, bg, h = who_said(chat, box, self.app)
            if (kind is None and is_avatar_region(rect,W)) or any(r[0]<=rect[0] and r[1]<=rect[1] and r[2]>=rect[2] and r[3]>=rect[3] for r in avatar_regions):
                self.last_boxes.append(rect + ("avatar", text))
                continue
            on_pane = bg is not None and np.abs(bg - pane_bg).sum() <= 6
            center_x = (rect[0] + rect[2]) / 2 / W
            # 灰字：时间戳 / 发言人名 / 其他
            if kind == "gray" or (on_pane and kind == "her"):
                if on_pane and 0.28 < center_x < 0.72 and is_time_text(text):
                    name=None
                    cur_time = re.sub(r"\s+", "", text)
                    timestamps.append((rect[1],cur_time))
                    self.last_boxes.append(rect + ("time", text))
                    continue
                if classify(text) in ('group_notice','poll','relay','system'):
                    raw.append(('her',name,text,rect[1],rect[3],h,cur_time,classify(text)))
                    self.last_boxes.append(rect + ('card',text,float(confidence)))
                    continue
                if text in ('展开','收起') and not on_pane:
                    raw.append(('her',name,text,rect[1],rect[3],h,cur_time,'text'))
                    self.last_boxes.append(rect + ('card',text,float(confidence)))
                    continue
                taken = bool(on_pane and rect[0] < 0.25 * W and len(text) <= 16
                             and not re.search("[:：]", text))
                if taken:
                    name = text
                    names.append((rect[1],text))
                self.last_boxes.append(rect + ("name" if taken else "gray", text,float(confidence)))
                continue
            # 图片里的字（表情包带字）：当作表情包消息，保留文字
            if kind is None:
                side = "me" if center_x > 0.55 else "her"
                region=next((r for r in media_regions if r[0]<=rect[0] and r[1]<=rect[1] and r[2]>=rect[2] and r[3]>=rect[3]),rect)
                self.media_refs[region[1]]=remember(chat,region)
                self.last_boxes.append(region + ("media_unknown", text))
                raw.append((side, name if side == "her" else None, text.strip(),
                            region[1], region[3], 0, cur_time, "media_unknown"))
                continue
            if self.lh and h < 0.6 * self.lh:
                # 首帧若被大卡片/多行气泡带偏，lh 标定过高会把正常单行消息当 tiny 丢弃。
                # 同一帧内连续 3 条以上高度一致的小行 → 按它们重标定，而不是永久漏读。
                self._tiny_batch.append(h)
                if len(self._tiny_batch) >= 3:
                    med = float(np.median(self._tiny_batch))
                    self._tiny_batch = []
                    if med >= 6:
                        self.lh = max(med, 8.0)
                    else:
                        self.last_boxes.append(rect + ("tiny", text))
                        continue
                else:
                    self.last_boxes.append(rect + ("tiny", text))
                    continue
            if has_color_ink(chat,rect,bg):
                box=inline_container(chat,rect,bg)
                region=(max(0,box[0]-4),max(0,box[1]-4),min(W,box[2]+4),min(chat.shape[0],box[3]+4))
                self.media_refs[region[1]]=remember(chat,region)
                inline_regions[region[1]]=region
                self.last_boxes.append(region+('media_unknown',text))
                raw.append((kind,name if kind=='her' else None,text,region[1],region[3],h,cur_time,'media_unknown'))
                continue
            self.last_boxes.append(rect + (kind, text,float(confidence)))
            raw.append((kind, name if kind == "her" else None, text,
                        rect[1], rect[3], h, cur_time, classify(text)))
        if not self.lh:
            hs = [r[5] for r in raw if r[5] > 0]
            if len(hs) >= 3:
                self.lh = float(np.median(hs))

        # 无文字的表情包/图片：连通块检测（排除所有已识别的文本框）
        exclude = [r[:4] for r in self.last_boxes]
        for (x0, y0, x1, y1) in find_stickers(chat, pane_bg, exclude):
            # Small colored blocks in the outer gutter are avatars, not messages.
            if is_avatar_region((x0,y0,x1,y1),W):
                continue
            side = "me" if (x0 + x1) / 2 / W > 0.55 else "her"
            media_name=next((nm for yy,nm in reversed(names) if yy<=y0 and y0-yy<500),None) if side=='her' else None
            media_time=next((tm for yy,tm in reversed(timestamps) if yy<=y0),None)
            self.media_refs[y0]=remember(chat,(x0,y0,x1,y1))
            self.last_boxes.append((x0, y0, x1, y1, "media_unknown", ""))
            raw.append((side, media_name, "",
                        y0, y1, self.lh or 20, media_time, "media_unknown"))

        for x0,y0,x1,y1 in system_regions:
            raw.append(('her',None,'一段较长的灰色系统提示（未完整识别，可在最近消息中手动修正）',y0,y1,0,None,'system'))
        for top,region in inline_regions.items():
            anchors=[r for r in raw if r[3]==top and r[7]=='media_unknown']
            if not anchors:continue
            anchor=anchors[0]
            rows=[r for r in raw if r[0]==anchor[0] and r[1]==anchor[1] and top<=r[3] and r[4]<=region[3]]
            raw=[r for r in raw if r not in rows]
            text=' '.join(dict.fromkeys(r[2] for r in sorted(rows,key=lambda r:r[3])))
            raw.append((anchor[0],anchor[1],text,top,region[3],anchor[5],anchor[6],'media_unknown'))
        raw=group_card_rows(raw,chat,pane_bg)
        # 合并同人多行（时间取第一条的；表情包永远单独成条）
        lines = []
        for who, nm, text, top, bottom, h, t, kind in sorted(raw, key=lambda r: r[3]):
            if kind == "media_unknown":
                if lines and lines[-1][6]==kind and lines[-1][3]==top and lines[-1][0]==who:
                    lines[-1][2]+=self.app.join+text
                    continue
                lines.append([who, nm, text, top, bottom, t, kind])
                continue
            if kind=='text' and lines and lines[-1][0] == who and lines[-1][1] == nm \
                    and lines[-1][6] == "text" \
                    and top - lines[-1][4] < 0.6 * (self.lh or h):
                lines[-1][2] += self.app.join + text
                lines[-1][4] = bottom
            else:
                lines.append([who, nm, text, top, bottom, t, kind])
        self.last_metrics = {"ocr_ms":self.last_ms,"post_ms":int((time.perf_counter()-read_started)*1000)-self.last_ms,"width":int(chat.shape[1]),"height":int(chat.shape[0]),"unread_system_blocks":len(system_regions)}
        output=[(w, n, t, y, tm, classify(t) if k=="text" else k) for w, n, t, y, _, tm, k in lines]
        from evidence import frame_evidence
        self.last_evidence=frame_evidence(chat,output,self.last_boxes)
        self.last_metrics['post_ms']=int((time.perf_counter()-read_started)*1000)-self.last_ms
        self.last_metrics['ocr_cache_hit'] = self.ocr_cache_hit
        return output

    def new_lines(self, lines):
        """去重（滚动不重复）→ 这一帧真正新出现的 [(who, name, text, time, kind)]。"""
        current=[(w,n,t,tm,k,self.media_refs.get(y) if k=='media_unknown' else None) for w,n,t,y,tm,k in lines]
        evidence=getattr(self,'last_evidence',[{} for _ in current])
        aligned=scroll_media_matches(self.previous,current,getattr(self,'previous_evidence',[]),evidence)
        def already_seen(row,index):
            if index in aligned:return True
            if self._seen(*row):return True
            clipped=index<len(evidence) and evidence[index].get('boundary_truncated_candidate')
            if not clipped or row[4]!='text' or len(row[2])<20:return False
            return any(old[0]==row[0] and old[1]==row[1] and old[3]==row[3] and old[4]==row[4]
                       and len(old[2])>len(row[2]) and old[2].startswith(row[2]) for old in self.seen)
        if not self.previous:
            new_indices=list(range(len(current)))
        else:
            overlap=0
            for size in range(min(len(self.previous),len(current)),0,-1):
                if all(same_observation_row(a,b) for a,b in zip(self.previous[-size:],current[:size])):
                    overlap=size;break
            if overlap:
                new_indices=list(range(overlap,len(current)))
            elif current and current[-1] in self.seen:
                new_indices=[] # scrolling into already-seen history
            else:
                known_y=[line[3] for i,line in enumerate(lines) if already_seen(current[i],i)]
                floor=max(known_y) if known_y else -1
                new_indices=[i for i,(row,line) in enumerate(zip(current,lines)) if line[3]>floor and not already_seen(row,i)]
        new_indices=[i for i in new_indices if i not in aligned]
        self.previous=current
        self.previous_evidence=copy.deepcopy(evidence)
        for row in current:
            if row not in self.seen:self.seen.append(row)
        del self.seen[:-500]
        self.new_media_ids=[current[i][5] for i in new_indices]
        self.new_evidence=[evidence[i] if i<len(evidence) else {} for i in new_indices]
        return [current[i][:5] for i in new_indices]

    def _seen(self, who, name, text, tm=None, kind=None, media_id=None):
        # Different words or digits may be a changed fact, not OCR jitter.
        return any(w==who and n==name and old_tm==tm and old_kind==kind and old_media==media_id
                   and (t==text or (kind=='media_unknown' and bool(media_id)))
                   for w,n,t,old_tm,old_kind,old_media in self.seen)
