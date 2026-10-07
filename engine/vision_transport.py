"""Cancellable local socket reads with Python's standard HTTP/JSON parsers."""
import http.client,io,json,select,time,urllib.parse,urllib.error
import os,subprocess,threading,socket
from pathlib import Path

MAX_JSON_BYTES=1024*1024
_service_lock=threading.Lock()
_last_service_start=0.0

def recover_local_ollama(url,deadline,route=None):
    """Start the existing local Ollama only after a refused connection.

    A request has not left the machine or reached a model at this point. Do not
    install anything, alter startup preferences, or launch arbitrary URL/PATH
    executables. Child listener is restricted to the configured loopback port.
    """
    global _last_service_start
    if os.name!='nt' or url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost') or url.port!=11434 or url.path!='/api/chat' or url.query:
        return False
    import modelrouter
    candidates=[Path(os.environ.get('LOCALAPPDATA',''))/'Programs'/'Ollama'/'ollama.exe',
                Path(os.environ.get('ProgramFiles',''))/'Ollama'/'ollama.exe']
    executable=next((p for p in candidates if p.is_absolute() and p.is_file()),None)
    if executable is None:return False
    with _service_lock:
        modelrouter.check(route)
        if time.monotonic()>=deadline:return False
        if not _last_service_start or time.monotonic()-_last_service_start>30:
            environment=dict(os.environ);environment['OLLAMA_HOST']='127.0.0.1:11434'
            try:
                subprocess.Popen([str(executable),'serve'],cwd=str(executable.parent),env=environment,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except OSError:return False
            _last_service_start=time.monotonic()
        expires=min(deadline,time.monotonic()+4)
        while time.monotonic()<expires:
            modelrouter.check(route)
            try:
                with socket.create_connection(('127.0.0.1',11434),timeout=min(.2,max(.01,expires-time.monotonic()))):
                    return True
            except OSError:time.sleep(min(.1,max(0,expires-time.monotonic())))
    return False

def bounded_json(response):
    """Limit compatible cloud responses as well as the local transport."""
    headers=getattr(response,'headers',None)
    length=headers.get('Content-Length') if headers is not None else None
    try:declared=int(length) if length is not None else None
    except (TypeError,ValueError):declared=None
    if declared is not None and declared>MAX_JSON_BYTES:
        raise ValueError('视觉响应超过大小上限')
    body=response.read(MAX_JSON_BYTES+1)
    if len(body)>MAX_JSON_BYTES:raise ValueError('视觉响应超过大小上限')
    if declared is not None and len(body)<declared:
        raise http.client.IncompleteRead(b'',declared-len(body))
    return json.loads(body)

class CancellableRaw(io.RawIOBase):
    def __init__(self,sock,route,deadline):
        super().__init__();self.sock=sock.dup();self.route=route;self.deadline=deadline
    def readable(self):return True
    def readinto(self,buffer):
        import modelrouter
        while True:
            modelrouter.check(self.route)
            remaining=self.deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('本地视觉响应超时')
            if select.select([self.sock],[],[],min(.05,remaining))[0]:
                modelrouter.check(self.route)
                return self.sock.recv_into(buffer)
    def close(self):
        if not self.closed:self.sock.close()
        super().close()

class CancellableResponse(http.client.HTTPResponse):
    def __init__(self,sock,route,deadline,**kwargs):
        super().__init__(sock,**kwargs)
        previous=self.fp
        self.fp=io.BufferedReader(CancellableRaw(sock,route,deadline))
        previous.close()

def local_json(req,timeout,route=None):
    import modelrouter
    url=urllib.parse.urlparse(req.full_url)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.username or url.password:
        raise ValueError('仅允许本机HTTP视觉请求')
    deadline=time.monotonic()+timeout
    conn=http.client.HTTPConnection(url.hostname,url.port or 80,timeout=timeout)
    conn.response_class=lambda sock,**kwargs:CancellableResponse(sock,route,deadline,**kwargs)
    try:
        modelrouter.check(route)
        try:
            conn.request(req.get_method(),url.path+('?' +url.query if url.query else ''),body=req.data,headers=dict(req.header_items()))
        except ConnectionRefusedError:
            conn.close()
            if not recover_local_ollama(url,deadline,route):raise
            modelrouter.check(route)
            conn.timeout=max(.1,deadline-time.monotonic())
            conn.request(req.get_method(),url.path,body=req.data,headers=dict(req.header_items()))
        with conn.getresponse() as response:
            if response.status!=200:
                # Keep the status for safe diagnostics; never read a service
                # error body, which may echo private image/prompt material.
                raise urllib.error.HTTPError(req.full_url,response.status,'本地视觉HTTP请求失败',None,None)
            if response.length is not None and response.length>MAX_JSON_BYTES:
                raise ValueError('本地视觉响应超过大小上限')
            declared_length=response.length
            body=response.read(MAX_JSON_BYTES+1)
            if declared_length is not None and len(body)<declared_length:
                raise http.client.IncompleteRead(b'',declared_length-len(body))
            if len(body)>MAX_JSON_BYTES:raise ValueError('本地视觉响应超过大小上限')
            result=json.loads(body)
        modelrouter.check(route);return result
    finally:conn.close()
