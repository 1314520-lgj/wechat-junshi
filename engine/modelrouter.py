"""Per-analysis model routes, hard call/deadline budgets and cancellation."""
import contextlib
import json
import threading
import time
import math
from pathlib import Path
_local=threading.local()

@contextlib.contextmanager
def session(settings,home,key,cancel=None):
    previous=getattr(_local,'route',None)
    route={'settings':dict(settings),'home':home,'key':key,'cancel':cancel,'deadline':time.monotonic()+settings.get('generation_timeout',90),'calls':0,'traces':[],'warnings':[],'cost_reserved':0.0,'budget_lock':threading.RLock()}
    _local.route=route
    try:yield route
    finally:_local.route=previous

def current():return getattr(_local,'route',None)
def check(route=None):
    route=route or current()
    if route and route['cancel'] and route['cancel']():raise InterruptedError('会话或消息已变化，旧任务已取消')
    if route and time.monotonic()>=route['deadline']:raise TimeoutError('生成时间已达到上限，可重试')

def validate_models(rows):
    import re
    from vision import validate_base
    if not isinstance(rows,list) or len(rows)>100:raise ValueError('模型目录最多100个项目')
    out=[];ids=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('模型配置格式无效')
        name=row.get('id','')
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',name) or name in ids:raise ValueError('模型编号无效或重复')
        ids.add(name)
        model=row.get('model','');roles=row.get('roles',[])
        if not isinstance(model,str) or not 1<=len(model)<=120 or not isinstance(roles,list) or not roles or set(roles)-{'draft','review','judge','rank'}:raise ValueError('模型名称或职责无效')
        if not isinstance(row.get('enabled',True),bool):raise ValueError('enabled必须为布尔值')
        rate=row.get('max_request_cost',0)
        if isinstance(rate,bool) or not isinstance(rate,(int,float)) or not 0<=rate<=10:raise ValueError('费用上限无效')
        out.append({'id':name,'model':model,'base':validate_base(row.get('base','')),'roles':roles,'enabled':bool(row.get('enabled',True)),'max_request_cost':rate})
    return out

_catalog_cache = {}

def catalog(home):
    path=Path(home)/'models.json'
    if not path.exists():
        _catalog_cache.clear()
        return []
    key=str(path)
    try:
        mtime=path.stat().st_mtime
        if _catalog_cache.get('_key')==key and _catalog_cache.get('_mtime')==mtime:
            return _catalog_cache.get('_value',[])
        value=validate_models(json.loads(path.read_text(encoding='utf-8')))
    except (OSError,ValueError):
        _catalog_cache.clear()
        raise
    _catalog_cache.update(_key=key,_mtime=mtime,_value=value)
    return value

def resolve(model,system):
    route=current()
    if not route:return None
    role={'checking':'review','ranking':'rank','drafting':'draft','judging':'judge'}.get(route.get('phase'),'draft')
    choices=[r for r in catalog(route['home']) if r['enabled'] and role in r['roles']]
    return choices[0] if choices else None

def reserve(model,system):
    check();route=current()
    if not route:return None
    chosen=resolve(model,system)
    cost=chosen['max_request_cost'] if chosen else 0
    reserve_request(chosen['model'] if chosen else model,cost,route=route,route_id=chosen['id'] if chosen else 'default')
    return chosen

def reserve_request(model,cost=0,route=None,phase=None,route_id='default',local=False):
    route=route or current();check(route)
    if not route:return
    if isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0:raise ValueError('费用预留无效')
    with route['budget_lock']:
        if route['calls']>=route['settings'].get('max_model_calls',6):raise TimeoutError('已达到本次模型调用上限')
        if route['cost_reserved']+cost>route['settings'].get('max_analysis_cost',1):raise TimeoutError('达到本次配置费用上限')
        if not local and not cost:
            warning='云端费用未配置，仅限制请求次数，无法保证实际账单上限'
            if warning not in route['warnings']:route['warnings'].append(warning)
        route['cost_reserved']+=cost;route['calls']+=1
        trace={'model':model,'phase':phase or route.get('phase','drafting'),'started':time.time(),'route':route_id,'cost_bound':cost,'local':local,'physical_request':True}
        route['traces'].append(trace)
        return trace

@contextlib.contextmanager
def output_contract(name):
    route=current()
    previous=route.get('output_contract') if route else None
    if route is not None:route['output_contract']=name
    try:yield
    finally:
        if route is not None:
            if previous is None:route.pop('output_contract',None)
            else:route['output_contract']=previous

def format_payload(payload,base,route=None):
    """Trusted code sets the contract; chat/envelope contents cannot enable it."""
    import urllib.parse
    route=route if route is not None else current()
    if route and route.get('output_contract')=='draft-replies-object-v1' and urllib.parse.urlparse(base).hostname=='api.deepseek.com':
        payload={**payload,'response_format':{'type':'json_object'}}
    return payload
