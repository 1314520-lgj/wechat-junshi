"""Application-wide cancellable request admission; local models share one slot."""
import contextlib
import threading
import time
import urllib.parse
_condition=threading.Condition()
_active={'local':{},'cloud':{}}
_waiting={'local':0,'cloud':0}

def snapshot():
    with _condition:
        return {name:{'active':len(_active[name]),'waiting':_waiting[name]} for name in _active}

@contextlib.contextmanager
def slot(base,timeout=30,deadline=None,route=None):
    import modelrouter
    route=route or modelrouter.current()
    host=urllib.parse.urlparse(base).hostname
    bucket='local' if host in ('127.0.0.1','localhost','::1') else 'cloud'
    limit=1 if bucket=='local' else (route['settings'].get('max_cloud_requests',1) if route else 1)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=4:raise ValueError('云端并发上限必须为1到4的整数')
    expires=min(time.monotonic()+timeout,deadline if deadline is not None else float('inf'),route['deadline'] if route else float('inf'))
    identity=object();admitted=False
    with _condition:
        _waiting[bucket]+=1
        try:
            while True:
                modelrouter.check(route)
                remaining=expires-time.monotonic()
                if remaining<=0:raise TimeoutError('等待模型通道超时，可重试')
                effective=min([limit,*_active[bucket].values()])
                if len(_active[bucket])<effective:
                    _active[bucket][identity]=limit;admitted=True;break
                _condition.wait(min(.1,remaining))
        finally:_waiting[bucket]-=1
    try:
        modelrouter.check(route)
        yield max(.05,expires-time.monotonic())
    finally:
        if admitted:
            with _condition:
                _active[bucket].pop(identity,None);_condition.notify_all()
