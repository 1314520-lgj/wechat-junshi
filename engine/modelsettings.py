"""No-op model saves do not invalidate suggestions or trigger paid calls."""
from pathlib import Path
from modelrouter import catalog
def is_unchanged(home,rows,keys):
    if not isinstance(keys,dict):raise ValueError('模型密钥格式无效')
    ids={r['id'] for r in rows}
    if any(k not in ids or not isinstance(v,str) or len(v)>1000 for k,v in keys.items()):raise ValueError('模型密钥无效')
    if catalog(home)!=rows:return False
    from securestore import read_json
    for identity,key in keys.items():
        p=Path(home)/('model-'+identity+'.dpapi')
        if (read_json(p).get('key','') if p.exists() else '')!=key:return False
    return True
