"""Bound native capture jobs; a timed-out Windows call cannot be killed safely."""
import threading
_lock=threading.Lock()
_jobs={}
def run(key,grab,timeout=2.5):
    with _lock:
        # Never reuse a delayed result as a newly captured frame.
        for old,(thread,box) in list(_jobs.items()):
            if not thread.is_alive():_jobs.pop(old,None)
        if key in _jobs or len(_jobs)>=8:return None
        box={}
        def worker():
            try:box['frame']=grab()
            except Exception:box['frame']=None
        thread=threading.Thread(target=worker,daemon=True)
        _jobs[key]=(thread,box);thread.start()
    thread.join(timeout)
    if thread.is_alive():return None
    with _lock:
        if _jobs.get(key,(None,))[0] is thread:_jobs.pop(key,None)
    return box.get('frame')
def snapshot():
    with _lock:return {'active':sum(t.is_alive() for t,b in _jobs.values()),'limit':8}
