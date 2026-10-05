"""Bounded read-only UIA context confined to the requested process and window."""
import copy,queue,threading,time
from collections import OrderedDict,deque
_cache=OrderedDict();_cache_lock=threading.Lock()
# 单飞用 owner-token 而不是普通锁：worker 线程被目标程序 UIA 永久挂起时，
# 看门狗线程可以替它交还 token，避免快照功能被一把楔死的锁永久拖垮。
# _owner 的读改写用小锁保护（并发 snapshot 时 check-then-set 必须原子）。
_owner=[None]
_owner_lock=threading.Lock()
_owner_progress=[0.0]
WATCHDOG_SECONDS=12.0

def unavailable(reason):return {'available':False,'reason':reason,'read_only':True}

def _try_acquire(token):
    with _owner_lock:
        if _owner[0] is not None:return False
        _owner[0]=token
        _owner_progress[0]=time.monotonic()
        return True

def _release(token):
    with _owner_lock:
        if _owner[0] is token:_owner[0]=None

def _mark_progress(token):
    with _owner_lock:
        if _owner[0] is token:_owner_progress[0]=time.monotonic()

def collect_context(root,hwnd,budget=1.4):
    started=time.monotonic()
    try:
        pid=root.ProcessId
        if not isinstance(pid,int) or isinstance(pid,bool) or pid<=0 or root.NativeWindowHandle!=hwnd:
            return unavailable('unconfirmed_window')
        rows=[];pending=deque([(root,0)]);visited=0;excluded=0
        while pending and visited<500 and time.monotonic()-started<budget:
            item,depth=pending.popleft();visited+=1
            if item.ProcessId!=pid:excluded+=1;continue
            top=item.GetTopLevelControl()
            if top is None or top.NativeWindowHandle!=hwnd:excluded+=1;continue
            if time.monotonic()-started>=budget:break
            name=item.Name
            if not isinstance(name,str):return unavailable('invalid_property')
            rows.append({'name':name[:1000],'type':item.ControlTypeName,'automation_id':item.AutomationId,'depth':depth})
            if depth<24:pending.extend((child,depth+1) for child in item.GetChildren()[:80])
        elapsed=time.monotonic()-started
        if elapsed>=budget:return unavailable('late_result_discarded')
        return {'available':True,'items':rows,'scope':'requested_process_and_toplevel_window','read_only':True,'visited':visited,'excluded_branches':excluded,'truncated':bool(pending),'read_seconds':round(elapsed,3)}
    except Exception as exc:return unavailable(type(exc).__name__)

def snapshot(hwnd,timeout=1.6):
    if not isinstance(hwnd,int) or isinstance(hwnd,bool) or hwnd<=0:return unavailable('no_window')
    key=hwnd;now=time.monotonic()
    with _cache_lock:
        cached=_cache.get(key)
        if cached and now-cached[0]<3:return copy.deepcopy(cached[1])
    token=object()
    if not _try_acquire(token):return unavailable('busy')
    results=queue.Queue(1)
    def worker():
        try:
            _mark_progress(token)
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():
                result=collect_context(auto.ControlFromHandle(key),key)
            _mark_progress(token)
            with _cache_lock:
                _cache[key]=(now,copy.deepcopy(result));_cache.move_to_end(key)
                while len(_cache)>8:_cache.popitem(last=False)
            try:results.put(result,block=False)
            except queue.Full:pass
        except Exception as exc:
            try:results.put(unavailable(type(exc).__name__),block=False)
            except queue.Full:pass
        finally:_release(token)
    def watchdog():
        # worker 被挂起的 GetChildren 卡死且长时间无进展时：交还 token 并给出占位
        # 结果，保证后续 snapshot 不再被永久 busy。慢但仍有进展的 worker 不受影响。
        time.sleep(WATCHDOG_SECONDS)
        with _owner_lock:
            stuck = _owner[0] is token and time.monotonic() - _owner_progress[0] > WATCHDOG_SECONDS
            if stuck:
                _owner[0] = None
        if stuck:
            try:results.put(unavailable('uia_hung_worker_abandoned'),block=False)
            except queue.Full:pass
    try:threading.Thread(target=worker,daemon=True).start()
    except Exception:
        _release(token)
        return unavailable('worker_start_failed')
    threading.Thread(target=watchdog,daemon=True).start()
    try:return copy.deepcopy(results.get(timeout=timeout))
    except queue.Empty:return unavailable('timeout')
