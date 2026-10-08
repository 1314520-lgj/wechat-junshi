"""Loopback-only Harness transport: reserve every upstream model HTTP request."""
import contextlib
import http.server
import json
import threading
import urllib.request
import urllib.error
import hashlib
_gateways={};_lock=threading.Lock()
class Gateway:
    def __init__(self,base,key):
        self.base=base.rstrip('/');self.key=key;self.route=None;self.guard=threading.RLock()
        owner=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.headers.get('Authorization')!='Bearer '+owner.key or self.path not in ('/chat/completions','/v1/chat/completions'):
                    self.send_error(403);return
                headers_sent=False
                try:
                    n=int(self.headers.get('Content-Length','0'))
                    if not 0<n<=2*1024*1024:raise ValueError('body')
                    body=self.rfile.read(n);payload=json.loads(body)
                    with owner.guard:route=owner.route
                    if route is None:raise InterruptedError('inactive route')
                    import modelrouter
                    payload=modelrouter.format_payload(payload,owner.base,route)
                    body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
                    chosen=modelrouter.catalog(route['home'])
                    role={'checking':'review','ranking':'rank','judging':'judge'}.get(route.get('phase'),'draft')
                    selected=next((x for x in chosen if x['enabled'] and role in x['roles']),None)
                    from requestgate import slot
                    with slot(owner.base,timeout=max(.1,route['deadline']-__import__('time').monotonic()),route=route):
                        modelrouter.reserve_request(payload.get('model','unknown'),selected['max_request_cost'] if selected else 0,route=route,route_id=selected['id'] if selected else 'harness')
                        req=urllib.request.Request(owner.base+'/chat/completions',data=body,headers={'Authorization':'Bearer '+owner.key,'Content-Type':'application/json'})
                        remaining=max(.1,route['deadline']-__import__('time').monotonic())
                        class NoRedirect(urllib.request.HTTPRedirectHandler):
                            def redirect_request(self,*args,**kwargs):return None
                        with urllib.request.build_opener(NoRedirect()).open(req,timeout=min(40,remaining)) as response:
                            self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','application/json'));self.send_header('Connection','close');self.end_headers();headers_sent=True
                            while True:
                                modelrouter.check(route)
                                data=response.read1(8192)
                                if not data:break
                                self.wfile.write(data);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                except Exception:
                    # 头一旦提交就不能再写状态行（会产出损坏的 200+垃圾体）；
                    # 流写到一半失败只能断开连接，把错误留给客户端自己发现。
                    if not headers_sent:
                        try:self.send_error(429,'Model request failed or budget exhausted')
                        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                self.close_connection=True
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    @property
    def url(self):return 'http://127.0.0.1:'+str(self.server.server_port)
@contextlib.contextmanager
def connect(base,key,route):
    identity=hashlib.sha256((base+'|'+key).encode()).hexdigest()
    with _lock:
        if identity not in _gateways:
            if len(_gateways)>=8:
                # 先淘汰空闲网关；全部忙时宁可报错也不打断在途请求。
                victim=next((k for k,g in _gateways.items() if g.route is None),None)
                if victim is None:raise RuntimeError('Harness transport capacity')
                try:
                    _gateways[victim].server.shutdown();_gateways[victim].server.server_close()
                except Exception:pass
                _gateways.pop(victim,None)
            _gateways[identity]=Gateway(base,key)
        gateway=_gateways[identity]
        # route 赋值在 _lock 内完成：淘汰扫描读 g.route 就不会再看到
        # “已取出网关但还没挂上 route”的中间态（否则会被当空闲网关误杀）。
        with gateway.guard:gateway.route=route
    try:yield gateway.url
    finally:
        with gateway.guard:gateway.route=None
