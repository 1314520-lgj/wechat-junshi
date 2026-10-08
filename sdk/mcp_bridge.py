"""Minimal newline-JSON MCP stdio bridge; sends no WeChat messages."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from client import Client
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')

client=Client()
TOOLS=[
 {'name':'junshi_get_context','description':'Read currently recognized messages and suggestions from local Junshi. Contains chat text.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'junshi_get_participants','description':'Read observed group speaker profiles. Screen display names are not verified WeChat account IDs.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'junshi_analyze_text','description':'Generate suggestions through the user-configured model; may incur API cost. Does not input or send a message.','inputSchema':{'type':'object','properties':{'messages':{'type':'array','items':{'type':'object','properties':{'from':{'enum':['me','her']},'text':{'type':'string'},'name':{'type':'string'},'kind':{'type':'string'},'time':{'type':'string'}},'required':['from','text']}},'relationship':{'type':'string'},'style':{'type':'string'}},'required':['messages']}},
 {'name':'junshi_list_extensions','description':'Read installed and enabled local Junshi extension metadata.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'junshi_capabilities','description':'Read local Junshi API version and features.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}
]
def handle(request):
    method=request.get('method');params=request.get('params') or {}
    if method=='initialize':return {'protocolVersion':params.get('protocolVersion') if params.get('protocolVersion') in ('2024-11-05','2025-03-26','2025-06-18') else '2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'junshi-local','version':'1.0.0'}}
    if method=='ping':return {}
    if method=='tools/list':return {'tools':TOOLS}
    if method=='tools/call':
        name=params.get('name');args=params.get('arguments') or {}
        if name=='junshi_get_context':
            state=client.state()
            result={k:state.get(k) for k in ('session','messages','analysis','analysis_error','engine','participants','identity_coverage','harness')}
        elif name=='junshi_get_participants':result=client.participants()
        elif name=='junshi_analyze_text':result=client.analyze(args['messages'],args.get('relationship','朋友'),args.get('style',''))
        elif name=='junshi_list_extensions':result=client.call('/extensions')
        elif name=='junshi_capabilities':result=client.call('/capabilities')
        else:raise ValueError('Unknown tool')
        return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}]}
    raise ValueError('Unknown method')

for line in sys.stdin:
    request={}
    try:
        request=json.loads(line)
        if 'id' not in request:continue
        response={'jsonrpc':'2.0','id':request['id'],'result':handle(request)}
    except Exception as exc:
        # Error classes only: do not reflect URLs, credentials or chat back in errors.
        response={'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32000,'message':type(exc).__name__+': 本机军师不可用或请求无效'}}
    sys.stdout.write(json.dumps(response,ensure_ascii=False)+'\n');sys.stdout.flush()
