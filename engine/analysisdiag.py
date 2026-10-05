"""Whitelist structural failure metadata before exposing it to API clients."""
def safe(value):
    if not isinstance(value,dict):return None
    out={}
    if type(value.get('actual_requests')) is int and 0<=value['actual_requests']<=100:
        out['actual_requests']=value['actual_requests']
    if value.get('phase') in ('start','judgment','judging','draft','drafting','ranking','reply-check','checking','checking-retry','check','vision','vision-update','verified-cache','shared-generation'):
        out['phase']=value['phase']
    for key in ('draft','review'):
        rows=value.get(key)
        if not isinstance(rows,list):continue
        clean=[]
        for row in rows[:4]:
            if not isinstance(row,dict):continue
            item={}
            ints=('length','recognized_strings','attempt') if key=='draft' else ('input_count','returned_count','usable_rejected','grounding_rejected','relevance_rejected','accepted')
            bools=('fenced','empty') if key=='draft' else ('strict',)
            for name in ints:
                if type(row.get(name)) is int and 0<=row[name]<=1048576:item[name]=row[name]
            for name in bools:
                if type(row.get(name)) is bool:item[name]=row[name]
            if key=='draft' and row.get('json_type') in ('dict','list','str','int','float','bool','NoneType','invalid'):item['json_type']=row['json_type']
            if key=='review' and row.get('failure_kind') in ('model_error','invalid_json','schema','no_accepted_replies'):item['failure_kind']=row['failure_kind']
            if item:clean.append(item)
        if clean:out[key]=clean
    return out or None
