"""Bounded observations with immutable OCR provenance and explicit human corrections."""
import hashlib, json, os, sqlite3, threading, time, uuid
from pathlib import Path

class EvidenceStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.lock=threading.RLock()
        self._participant_cache={}
        self._insert_count=0
        self.db.executescript('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, session TEXT, created REAL, payload TEXT); CREATE TABLE IF NOT EXISTS persons(id TEXT PRIMARY KEY, session TEXT, name TEXT, avatar TEXT, confirmed INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS corrections(id TEXT, created REAL, payload TEXT);')
        self.db.commit()
        self.db.execute('CREATE TABLE IF NOT EXISTS session_sequences(session TEXT PRIMARY KEY, seq INTEGER)')
        self.db.execute('CREATE INDEX IF NOT EXISTS observations_session_created ON observations(session,created)')
        self.db.commit()

    def _same_recent_observation(self,m,session,evidence):
        # Reuse an OCR observation, never a person identity or human correction.
        # Exact full-frame/crop/position/avatar evidence is required; visual
        # similarity, names alone and truncated boundaries are insufficient.
        if evidence.get('source')!='screenshot_ocr' or evidence.get('boundary_truncated_candidate') is not False:return None
        if not all(isinstance(evidence.get(k),str) and evidence[k] for k in ('frame_id','crop_id')):return None
        if m.get('from')=='her' and m.get('kind') not in ('system','time') and not evidence.get('avatar_crop_id'):return None
        rect=evidence.get('rect')
        if not isinstance(rect,list) or len(rect)!=4:return None
        proof=('source','frame_id','crop_id','rect','avatar_crop_id')
        now=time.time();matched=[]
        for created,payload in self.db.execute('SELECT created,payload FROM observations WHERE session=? AND created>=?',(session,now-120)):
            if not 0<=now-created<=120:continue
            try:old=json.loads(payload)
            except (ValueError,TypeError):continue
            if not isinstance(old,dict):continue
            if old.get('corrected_at') or old.get('identity_confidence')=='user_confirmed' or old.get('text_confirmation')=='user_confirmed' or old.get('media_association_source'):continue
            previous=old.get('evidence') or {}
            if not isinstance(previous,dict):continue
            if previous.get('boundary_truncated_candidate') is not False:continue
            if old.get('original_observation')!=m.get('original_observation'):continue
            if all(previous.get(k)==evidence.get(k) for k in proof):matched.append(old)
            if len(matched)>1:return None
        return {**matched[0],'reobserved_at':now,'observation_reused':True} if matched else None

    def observe(self, message, session, evidence=None):
        m=dict(message); evidence=dict(evidence or {})
        m['original_observation']={key:m.get(key) for key in ('from','name','text','time','kind','media_id')}
        m.update(message_id=uuid.uuid4().hex,session=session,observed_at=time.time(),content_source='ocr',original_text=m.get('text',''),evidence=evidence)
        m['uncertainties']=[]
        from content import CARD_KINDS, card_details
        if m.get('kind') in CARD_KINDS:m['card_details']=card_details(m)
        if m.get('kind') in CARD_KINDS or m.get('kind') in ('relay','poll','group_notice'):
            m['card_scope']='visible_preview'
            m['uncertainties'].append('卡片仅识别屏幕可见内容；展开后或屏幕外内容尚未核对')
        if evidence.get('ocr_confidence') is not None and evidence['ocr_confidence']<.85:m['uncertainties'].append('文字识别置信度偏低，请核对原图')
        if m.get('kind') in ('media_unknown','image','video','sticker'):m['uncertainties'].append('媒体内容尚未核对')
        with self.lock:
            previous=self._same_recent_observation(m,session,evidence)
            if previous is not None:return previous
            self.db.execute('INSERT OR IGNORE INTO session_sequences VALUES(?,0)',(session,))
            self.db.execute('UPDATE session_sequences SET seq=seq+1 WHERE session=?',(session,))
            m['sequence']=self.db.execute('SELECT seq FROM session_sequences WHERE session=?',(session,)).fetchone()[0]
            if m.get('kind') in ('system','time'):m.update(speaker_id='system',identity_confidence='system')
            elif m.get('from')=='me':m.update(speaker_id='self',identity_confidence='self_side')
            else:
                avatar=evidence.get('avatar_fingerprint',''); name=m.get('name') or ''
                matches=self.db.execute('SELECT id FROM persons WHERE session=? AND name=? AND avatar=? LIMIT 8',(session,name,avatar)).fetchall() if avatar and name else []
                person=uuid.uuid4().hex
                self.db.execute('INSERT INTO persons VALUES(?,?,?,?,0)',(person,session,name,avatar))
                m.update(speaker_id=person,identity_confidence='visual_candidate' if avatar and name else 'unknown',identity_scope='observation',identity_candidates=[r[0] for r in matches])
                if m['identity_confidence']!='user_confirmed':m['uncertainties'].append('人物视觉线索不等于唯一微信账号')
            self.db.execute('INSERT INTO observations VALUES(?,?,?,?)',(m['message_id'],session,m['observed_at'],json.dumps(m,ensure_ascii=False)))
            # 保留清理每 200 条跑一次：ORDER BY ... OFFSET 20000 与整表扫描
            # 不该挂在每条 OCR 观察的插入路径上。
            self._insert_count += 1
            if self._insert_count % 200 == 0:
                self.db.execute('DELETE FROM observations WHERE created<?',(time.time()-7*86400,))
                self.db.execute('DELETE FROM observations WHERE id IN (SELECT id FROM observations ORDER BY created DESC LIMIT -1 OFFSET 20000)')
                self.db.execute('DELETE FROM corrections WHERE created<?',(time.time()-7*86400,))
                self.db.execute('DELETE FROM corrections WHERE id NOT IN (SELECT id FROM observations)')
                self.db.execute("DELETE FROM persons WHERE session NOT IN (SELECT DISTINCT session FROM observations)")
            self.db.commit()
        return m

    def correct(self, message_id, patch):
        if not isinstance(patch,dict) or set(patch)-{'text','name','kind','speaker_id','time'}:raise ValueError('不支持的更正字段')
        if any(not isinstance(v,str) or len(v)>4000 for v in patch.values()):raise ValueError('更正内容无效')
        from content import KINDS
        if 'kind' in patch and patch['kind'] not in KINDS:raise ValueError('消息类型无效')
        with self.lock:
            row=self.db.execute('SELECT session,payload FROM observations WHERE id=?',(message_id,)).fetchone()
            if not row:raise ValueError('消息已离开记录范围')
            m=json.loads(row[1]);old_kind=m.get('kind');new_kind=patch.get('kind',old_kind)
            if new_kind in ('system','time') and 'speaker_id' in patch:raise ValueError('系统与时间记录不能指定为人物发言')
            m.update(patch);m['content_source']='user_corrected';m['corrected_at']=time.time()
            from content import CARD_KINDS, card_details
            if new_kind in CARD_KINDS:
                m['card_details']=card_details(m);m['card_scope']='visible_preview'
            elif old_kind in CARD_KINDS:
                m.pop('card_details',None);m.pop('card_scope',None)
            if new_kind in ('system','time'):
                m.update(speaker_id='system',identity_confidence='system',identity_scope='observation',identity_candidates=[])
            elif old_kind in ('system','time') and 'speaker_id' not in patch:
                if m.get('from')=='me':m.update(speaker_id='self',identity_confidence='self_side',identity_scope='observation',identity_candidates=[])
                else:
                    person=uuid.uuid4().hex
                    self.db.execute('INSERT INTO persons VALUES(?,?,?,?,0)',(person,row[0],m.get('name') or '',(m.get('evidence') or {}).get('avatar_fingerprint','')))
                    m.update(speaker_id=person,identity_confidence='unknown',identity_scope='observation',identity_candidates=[])
                    m['uncertainties']=list(dict.fromkeys(m.get('uncertainties',[])+['人物视觉线索不等于唯一微信账号']))
            if 'text' in patch:
                m['text_confirmation']='user_confirmed'
                m['uncertainties']=[u for u in m.get('uncertainties',[]) if '文字识别置信度偏低' not in u]
            if 'speaker_id' in patch:
                if patch['speaker_id']=='self':m['from']='me'
                else:
                    person=self.db.execute('SELECT session FROM persons WHERE id=?',(patch['speaker_id'],)).fetchone()
                    if not person or person[0]!=row[0]:raise ValueError('人物不属于当前会话')
                    m['from']='her'
                m['identity_confidence']='user_confirmed';m['identity_scope']='observation'
            self.db.execute('INSERT INTO corrections VALUES(?,?,?)',(message_id,time.time(),json.dumps(patch,ensure_ascii=False)))
            self.db.execute('UPDATE observations SET payload=? WHERE id=?',(json.dumps(m,ensure_ascii=False),message_id));self.db.commit()
        return m

    def attach_media(self,message_id,fields):
        with self.lock:
            row=self.db.execute('SELECT payload FROM observations WHERE id=?',(message_id,)).fetchone()
            if not row:raise ValueError('消息已离开记录范围')
            message=json.loads(row[0]);message.update(fields)
            message['media_association_source']='user_confirmed_file_association'
            message['uncertainties']=list(dict.fromkeys(message.get('uncertainties',[])+['语音转写与视频抽样未经人工逐项核对，未处理部分保持未知']))
            self.db.execute('UPDATE observations SET payload=? WHERE id=?',(json.dumps(message,ensure_ascii=False),message_id))
            self.db.execute('INSERT INTO corrections VALUES(?,?,?)',(message_id,time.time(),json.dumps({'action':'attach_media','evidence':fields.get('file_evidence')},ensure_ascii=False)))
            self.db.commit();return message

    def participants(self, session):
        with self.lock:
            revision=self.db.total_changes
            cached=self._participant_cache.get(session)
            if cached and cached[0]==revision:return cached[1]
            rows=self.db.execute('SELECT id,name,avatar,confirmed FROM persons WHERE session=?',(session,)).fetchall()
            messages=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM observations WHERE session=? ORDER BY created',(session,))]
        grouped={}
        for message in messages:
            if message.get('kind') in ('system','time'):continue
            key=message.get('speaker_id')
            stat=grouped.setdefault(key,{'count':0,'last':message,'confirmed':0});stat['count']+=1;stat['last']=message
            if message.get('identity_confidence')=='user_confirmed' and message.get('identity_scope')=='observation':stat['confirmed']+=1
        result=[]
        for identity,name,avatar,confirmed in rows:
            mine=grouped.get(identity)
            if mine:result.append({'id':identity,'name':mine['last'].get('name') or name or '发言人待确认','avatar_fingerprint':avatar,'confirmed_messages':mine['confirmed'],'identity':'user_confirmed' if mine['confirmed']==mine['count'] else 'visual_candidate' if avatar and name else 'unknown','messages':mine['count'],'last_time':mine['last'].get('time')})
        answer={'items':result,'observed':len(result),'confirmed':sum(bool(r['identity']=='user_confirmed') for r in result),'total_members':None,'limit':'仅已观察人物线索，同一个人可能对应多条待确认线索；相同头像昵称可能是不同账号，未经用户确认不会宣称唯一身份'}
        with self.lock:
            if len(self._participant_cache)>=8:self._participant_cache.clear()
            self._participant_cache[session]=(revision,answer)
        return answer

def frame_evidence(frame, lines, boxes):
    import numpy as np
    from PIL import Image
    from media import remember
    height,width=frame.shape[:2];stamp=hashlib.sha256(frame.tobytes()).hexdigest()[:24]
    result=[]
    for index,(who,name,text,y,tm,kind) in enumerate(lines):
        end=lines[index+1][3] if index+1<len(lines) else height
        candidates=[b for b in boxes if b[4] not in ('name','time','tiny') and y-8<=b[1]<end and b[4] in (who,kind,'card','gray')]
        box=(min(b[0] for b in candidates),min(b[1] for b in candidates),max(b[2] for b in candidates),max(b[3] for b in candidates)) if candidates else (0,max(0,y),width,min(height,y+70))
        evidence={'frame_id':stamp,'rect':list(map(int,box)),'crop_id':remember(frame,box),'read_at':time.time(),'source':'screenshot_ocr','time_scope':'visible_separator' if tm else 'unknown'}
        evidence['boundary_truncated_candidate']=box[1]<12 or box[3]>=height-24
        confidence=[float(b[6]) for b in candidates if len(b)>6 and isinstance(b[6],(int,float))]
        evidence['ocr_confidence']=min(confidence) if confidence else None
        # Geometric candidates only. No face identity inference or automatic confirmation.
        try:
            import cv2
            cv2.setNumThreads(1)
            gutter=frame[:, :max(1,min(128,int(width*.14)))]
            gray=cv2.cvtColor(gutter,cv2.COLOR_RGB2GRAY)
            edges=cv2.Canny(gray,40,100)
            contours,_=cv2.findContours(edges,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            options=[]
            for contour in contours:
                x,ay,w,h=cv2.boundingRect(contour)
                if 22<=w<=85 and 22<=h<=85 and .8<=w/h<=1.25 and abs(ay-y)<55:options.append((abs(ay-y),x,ay,w,h))
            if who=='her' and options:
                _,x,ay,w,h=min(options)
                avatar=frame[ay:ay+h,x:x+w]
                if np.std(avatar)>12:
                    small=np.asarray(Image.fromarray(avatar).convert('L').resize((9,8)))
                    bits=(small[:,1:]>small[:,:-1]).flatten()
                    evidence['avatar_fingerprint']=hex(sum(int(b)<<i for i,b in enumerate(bits)))[2:].zfill(16)
                    evidence['avatar_crop_id']=remember(frame,(x,ay,x+w,ay+h))
        except Exception:
            evidence['avatar_detection_unavailable']=True
        result.append(evidence)
    return result

_stores={}
_stores_lock=threading.RLock()
def store(home):
    path=str(Path(home)/'observations.sqlite3')
    with _stores_lock:
        if path not in _stores:_stores[path]=EvidenceStore(path)
        return _stores[path]
