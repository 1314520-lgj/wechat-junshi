"""Conservative composer/header pixel witnesses; never proves latest position."""
import hashlib
import time
import threading
from collections import OrderedDict
import numpy as np
import cv2
cv2.setNumThreads(1)
_cache=OrderedDict();_lock=threading.Lock()

def composer_boxes(full):
    H,W=full.shape[:2]
    gray=cv2.cvtColor(full,cv2.COLOR_RGB2GRAY)
    contours,_=cv2.findContours(cv2.Canny(gray,8,24),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,w,h=map(int,cv2.boundingRect(contour))
        if not (W*.05<x and W*.2<w<W*.95 and H*.6<y and H*.06<h<H*.3 and y+h>H*.9 and 2<w/h<20):continue
        if len(contour)<12 or cv2.contourArea(contour)/(w*h)<.96:continue
        boxes.append((x,y,x+w,y+h))
    # Nested one-pixel borders are one witness, not different composers.
    out=[]
    for box in sorted(boxes,key=lambda r:-(r[2]-r[0])*(r[3]-r[1])):
        if any(max(0,min(box[2],a[2])-max(box[0],a[0]))*max(0,min(box[3],a[3])-max(box[1],a[1]))>.9*(box[2]-box[0])*(box[3]-box[1]) for a in out):continue
        out.append(box)
    return out[:4]

def _send_witness(full,box,recognize,metrics):
    x,y,x1,y1=box
    if y1-y<35:return False
    footer=np.ascontiguousarray(full[y+int((y1-y)*.7):y1,x:x1])
    key=(footer.shape,hashlib.sha256(footer.tobytes()).digest())
    with _lock:
        cached=_cache.get(key)
        if cached and time.monotonic()-cached[0]<(60 if cached[1] else 2):
            metrics['footer_cache_hits']+=1;return cached[1]
    start=time.perf_counter()
    try:rows=recognize(footer)
    except Exception:
        metrics['error']='输入区域文字证据读取失败';return False
    ok=any(str(text).replace(' ','').strip() in ('发送','Send') and isinstance(conf,(int,float)) and conf>=.85 for text,conf in rows)
    metrics['footer_ocr_ms']+=round((time.perf_counter()-start)*1000,1)
    with _lock:
        _cache[key]=(time.monotonic(),ok);_cache.move_to_end(key)
        while len(_cache)>4:_cache.popitem(last=False)
    return ok

def _separators_in(band):
    """Row where the flat list background ends and a flat brighter band starts.

    `band` is a float array shaped (rows, width, 3). On a real dark-theme
    window the boundary is a wide flat band (tens of rows) rather than a
    hairline, and content such as the toolbar can sit between the list and that
    band, so this looks for the transition between two flat regions of
    different brightness rather than a thin line.
    """
    mean=band.mean((1,2));std=band.std((1,2))
    flat=[bool(s<3) for s in std]
    runs=[]
    start=None
    for i,is_flat in enumerate(flat):
        if is_flat and start is None:start=i
        if not is_flat and start is not None:
            runs.append((start,i));start=None
    if start is not None:runs.append((start,len(flat)))
    # Brightest sustained flat run wins; require it to be reasonably tall so a
    # single stray row cannot stand in for the boundary.
    best=None
    for a,b in runs:
        if b-a<4:continue
        level=float(mean[a:b].mean())
        if best is None or level>best[2]:best=(a,b,level)
    if best is None:return []
    a,b,level=best
    # The run immediately above must be flat and clearly darker.
    prev=[r for r in runs if r[1]<=a]
    if not prev:return []
    pa,pb=prev[-1]
    if pb-pa<2:return []
    before=float(mean[pa:pb].mean())
    if not 3<=abs(level-before)<=40:return []
    if level<=before:return []
    return [a]

def _rounded_area(full,box):
    H,W=full.shape[:2];x,y,x1,y1=box
    # A composer too narrow to judge must be rejected, not guessed from a
    # handful of pixels. Measured real width is 797; 200 keeps ample room for
    # the central strip while refusing degenerate slivers.
    if x1-x<200:return None
    band=full[:H//5,x:x1].astype(float)
    mean=band.mean((1,2));std=band.std((1,2))
    # A clipped avatar immediately below the real header line can occupy a
    # small part of the next row. Require >=95% exact background pixels;
    # do not relax the actual separator or its preceding row.
    median=np.median(band,axis=1)
    fraction=np.mean(np.all(band==median[:,None,:],axis=2),axis=1)
    below_mean=np.where(fraction>=.95,median.mean(1),mean)
    below_std=np.where(fraction>=.95,median.std(1),std)
    separators=[]
    for row in range(max(2,int(H*.02)),len(mean)-4):
        for thickness in (1,2,3):
            end=row+thickness
            if max(std[row-1:end])<3 and below_std[end]<3 and abs(mean[row-1]-below_mean[end])<1.5 and all(3<=abs(v-mean[row-1])<=40 for v in mean[row:end]):
                separators.append(row);break
    if not separators:
        # In the dark theme the composer is outlined, so across the full box
        # width those vertical edges keep the spread above the flatness limit
        # and the full-width test can never fire. Measured on a real window,
        # the boundary reads std 0.47 on a bubble-free central strip but 5.12
        # across the full width. Retry on that strip; it is the same pixel
        # boundary, measured where bubbles cannot interfere, not a weaker guess.
        width=x1-x
        if width>=40:
            strip=band[:,int(width*.35):int(width*.65)]
            if strip.shape[1]>=20:
                separators=_separators_in(strip)
    if not separators:return None
    top=min(separators)+1
    if y-top<H*.25:return None
    pixels=full[top:y:8,x:x1:8].reshape(-1,3)
    colors,counts=np.unique(pixels,axis=0,return_counts=True)
    return x,top,x1,y,colors[counts.argmax()],0

def validated_area(full,recognize=None,recognize_details=None):
    """A visible send marker is a reading witness, never input permission."""
    started=time.perf_counter();metrics={'footer_ocr_ms':0,'footer_cache_hits':0,'latest_position_verified':False}
    if recognize is None:
        from ocr import _engine
        def recognize(crop):
            rows,_=_engine()(crop,use_cls=False)
            return [(r[1],float(r[2])) for r in rows or []]
    matches=[]
    boxes=composer_boxes(full)
    for box in boxes:
        area=_rounded_area(full,box)
        if area is not None and _send_witness(full,box,recognize,metrics):matches.append(area)
    # A composer-shaped region must be the only one on the frame. Counting only
    # the boxes that happen to match would let a screen with two input regions
    # (measured on a real search page: 2 boxes) pass by matching just one of
    # them, so "exactly one input box" was never actually enforced. Measured
    # counts: live chat 1, group-split chat 1, search page 2.
    ambiguous=len(boxes)>1
    area=matches[0] if (len(matches)==1 and not ambiguous) else None
    if ambiguous:metrics['ambiguous_composer_boxes']=len(boxes)
    if not matches and not ambiguous:
        from capture import chat_area
        legacy=chat_area(full)
        if legacy is not None and _send_witness(full,(legacy[0],legacy[3],legacy[2],full.shape[0]),recognize,metrics):
            metrics.update(source='legacy_geometry_send_ocr',layout_ms=round((time.perf_counter()-started)*1000,1));return legacy,metrics
    if area is None and len(boxes)==1:
        if recognize_details is None:
            from ocr import _engine
            def recognize_details(crop):
                rows,_=_engine()(crop,use_cls=False)
                return rows or []
        from headerwitness import area_from_agreement
        fallback=area_from_agreement(full,boxes[0],recognize_details)
        if fallback is not None and _send_witness(full,boxes[0],recognize,metrics):
            metrics.update(source='selected_sidebar_title_send_ocr',layout_ms=round((time.perf_counter()-started)*1000,1),title_sidebar_agreement=True)
            return fallback,metrics
    metrics.update(source='rounded_composer_send_ocr' if area is not None else 'unconfirmed',layout_ms=round((time.perf_counter()-started)*1000,1))
    return area,metrics
