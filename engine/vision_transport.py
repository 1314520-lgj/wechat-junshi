"""Cancellable local socket reads with Python's standard HTTP/JSON parsers."""
import http.client,io,json,select,time,urllib.parse

MAX_JSON_BYTES=1024*1024

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
        conn.request(req.get_method(),url.path+('?' +url.query if url.query else ''),body=req.data,headers=dict(req.header_items()))
        with conn.getresponse() as response:
            if response.status!=200:raise OSError('本地视觉HTTP状态 '+str(response.status))
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
