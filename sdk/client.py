"""Same-user local Junshi API client. Never print/store the controller token."""
import json
import os
import sys
import urllib.request
from pathlib import Path

class Client:
    def __init__(self, installation=None, data=None):
        local=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
        self.installation=Path(installation) if installation else local/'Programs'/'Junshi'
        self.data=Path(data) if data else local/'Junshi'
        sys.path.insert(0,str(self.installation/'engine'))
        from securestore import read_json
        self._read_json=read_json
        self._opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def call(self,path,body=None):
        if not path.startswith('/') or '?' in path:raise ValueError('path')
        info=self._read_json(self.data/'instance.dpapi')
        req=urllib.request.Request(f"http://127.0.0.1:{int(info['port'])}{path}",
            data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),
            headers={'Authorization':'Bearer '+info['token'],'Content-Type':'application/json'})
        with self._opener.open(req,timeout=240 if path=='/analyze-text' else 10) as r:result=json.load(r)
        if not result.get('ok'):raise RuntimeError(result.get('error','Local API failed'))
        return result
    def state(self):return self.call('/state')
    def participants(self):return self.call('/participants')
    def analyze(self,messages,relationship='朋友',style=''):
        return self.call('/analyze-text',{'messages':messages,'relationship':relationship,'style':style})

if __name__=='__main__':
    client=Client()
    print(json.dumps(client.call('/capabilities'),ensure_ascii=False,indent=2))
