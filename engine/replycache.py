"""Small process-only cache of already verified results for identical evidence."""
import copy,hashlib,inspect,json,threading,time
from collections import OrderedDict
from pathlib import Path
_entries=OrderedDict();_lock=threading.Lock();TTL=60;CAPACITY=8
# 消息里只有这些字段代表「可见证据本身」；observed_at/sequence/speaker_id/evidence 等
# 观察元数据每次都变，不能进缓存键，否则同一证据重新观察后永远打不中缓存/飞行合并。
_MESSAGE_KEY_FIELDS=('from','text','kind','media_description','thumbnail_description',
    'media_transcript','media_association_source','media_understanding_complete',
    'transcript_confirmation','vision_uncertain','vision_confidence','content_source','time','who',
    'name','text_confirmation','uncertainties','media_understanding_complete','media_incomplete',
    'media_caption','media_id','identity_confidence','identity_scope')

def cached_visual_evidence(message,settings):
    if not settings.get('vision_enabled') or not message.get('media_id'):return None
    from media import description
    from vision import validate_base,VISION_CACHE_VERSION
    try:provider=validate_base(settings.get('vision_base',''))+'|'+settings.get('vision_model','').strip()+'|'+VISION_CACHE_VERSION
    except (ValueError,AttributeError):return None
    cached=description(message['media_id'],provider)
    if not cached or cached.get('uncertain') or cached.get('confidence',0)<.75:return None
    # Thumbnail and audio-bubble descriptions never prove full understanding.
    if message.get('kind') in ('video','audio') or cached.get('kind') in ('video','audio','media_unknown'):return None
    return cached
def key_for(fn,args,kwargs,home,allow_unresolved=False):
    values=inspect.signature(fn).bind_partial(*args,**kwargs);values.apply_defaults();v=dict(values.arguments)
    settings=dict(v.get('settings') or {})
    if settings.get('enabled_extensions') or settings.get('_force_fresh'):return None
    cleaned=[]
    for m in v.get('messages',[]):
        if not isinstance(m,dict):return None
        visual=None
        if not allow_unresolved and m.get('kind') in ('media_unknown','image','video','audio','sticker') and (not m.get('media_description') or m.get('vision_uncertain') or m.get('media_understanding_complete') is False):
            # An explicitly uncertain supplied observation remains uncertain.
            if m.get('vision_uncertain') or m.get('media_understanding_complete') is False:return None
            visual=cached_visual_evidence(m,settings)
            if visual is None:return None
        row={k:m[k] for k in _MESSAGE_KEY_FIELDS if k in m}
        # Random observation IDs change each read. Explicitly confirmed speaker
        # links affect source ownership and must distinguish cached advice.
        if m.get('identity_confidence')=='user_confirmed' and m.get('speaker_id'):
            row['speaker_id']=m['speaker_id']
        if visual is not None:row['cached_visual_evidence']=visual
        cleaned.append(row)
    v['messages']=cleaned
    settings.pop('_cancel',None);settings.pop('_on_partial',None);v['settings']=settings;v.pop('progress',None)
    try:
        catalog=Path(home)/'models.json';v['catalog_digest']=hashlib.sha256(catalog.read_bytes()).hexdigest() if catalog.exists() else None
        v['home']=str(home)
        raw=json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    except (TypeError,ValueError,OSError):return None
    return hashlib.sha256(raw.encode()).hexdigest()
def get(key):
    if key is None:return None
    with _lock:
        entry=_entries.get(key)
        if not entry:return None
        age=time.monotonic()-entry[0]
        if age>=TTL:_entries.pop(key,None);return None
        result=copy.deepcopy(entry[1]);result['cache_age_seconds']=round(age,3)
        result['cache_hit']=True;result['model_trace']=[];result['cost_reserved']=0
        if 'usage' in result:result['usage']={'requests':0,'phase':'verified-cache','cost_reserved':0,'draft_attempts':0}
        result['phase_timings']=[{'phase':'verified-cache','seconds':0}]
        result['warnings']=list(result.get('warnings',[]))+[f'复用{TTL}秒内相同证据与设置的已核验建议；本次没有新增模型调用']
        return result
def put(key,result):
    if key is None or not result.get('review_ok') or not result.get('candidates'):return
    with _lock:
        _entries[key]=(time.monotonic(),copy.deepcopy(result));_entries.move_to_end(key)
        while len(_entries)>CAPACITY:_entries.popitem(last=False)

_flights={}
def join(key,cancel):
    token=object()
    with _lock:
        leader=key not in _flights or _flights[key].get('abandoned',False)
        if leader:_flights[key]={'event':threading.Event(),'members':{},'result':None,'error':None,'abandoned':False}
        flight=_flights[key];flight['members'][token]=cancel
        return flight,token,leader
def shared_cancel(flight):
    with _lock:
        if flight.get('abandoned',False):return True
        members=list(flight['members'].items())
    cancelled=not members or all(check is not None and check() for _,check in members)
    if not cancelled:return False
    with _lock:
        # A live waiter may have joined while callbacks ran. Retry on the next
        # poll rather than cancelling a changed membership snapshot.
        if list(flight['members'].items())!=members:return False
        flight['abandoned']=True
        return True
def leave(flight,token):
    with _lock:flight['members'].pop(token,None)
def publish(key,flight,result=None,error=None):
    with _lock:
        flight['result']=copy.deepcopy(result);flight['error']=error
        if _flights.get(key) is flight:_flights.pop(key,None)
        flight['event'].set()
def wait(flight,cancel,timeout=90):
    started=time.monotonic();deadline=started+timeout
    while not flight['event'].wait(.05):
        if cancel and cancel():raise InterruptedError('等待者已取消')
        if time.monotonic()>=deadline:raise TimeoutError('共享生成等待超时')
    if cancel and cancel():raise InterruptedError('等待者已取消')
    if flight['error']:raise flight['error']
    result=copy.deepcopy(flight['result']);result['model_trace']=[];result['cost_reserved']=0
    if 'usage' in result:result['usage']={'requests':0,'phase':'shared-generation','cost_reserved':0,'draft_attempts':0}
    result['coalesced']=True;result['warnings']+=['复用同证据正在生成的已核验结果；本请求未重复调用模型']
    result['phase_timings']=[{'phase':'shared-generation','seconds':round(time.monotonic()-started,3)}]
    return result
