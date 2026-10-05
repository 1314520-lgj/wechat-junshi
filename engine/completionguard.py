"""Finite lexical status binding; not a general semantic proof."""
import re
WORK=re.compile(r'(?:新|旧|这份|那份|第[一二三四五六七八九十0-9]+份|[A-Z])?(?:汇总|季度|年度|周|月)?(?:报告|项目|任务|作业|方案|文件|邮件|资料)')
STATUSES=[
 ('not_done',r'(?:还没|没有|没|尚未|未).{0,4}(?:写好|做好|弄好|搞定|完成|处理好)'),
 ('not_sent',r'(?:还没|没有|没|尚未|未).{0,4}(?:发出|发送|发好)'),
 ('not_submitted',r'(?:还没|没有|没|尚未|未).{0,4}(?:提交|交上去)'),
 ('submitted',r'交上去了|提交好了|提交了|已(?:经)?提交'),
 ('sent',r'发出去了|发送好了|发好了|发出了|发送了|已(?:经)?发出|已(?:经)?发送'),
 ('done',r'写好了|做好了|弄好了|搞定了|处理好了|完成了|已(?:经)?完成'),
]
def status(text):
    return next((name for name,pattern in STATUSES if re.search(pattern,text)),None)

def evidence_status(text,wanted):
    """Completion, sending and submission are independent status families."""
    family=wanted.removeprefix('not_')
    negative=[m.span() for name,pattern in STATUSES if name=='not_'+family for m in re.finditer(pattern.replace('.{0,4}','.{0,4}?'),text)]
    positive=[m.span() for name,pattern in STATUSES if name==family for m in re.finditer(pattern,text)]
    # "没有完成了" must not become positive merely because 完成了 overlaps.
    positive=[(left,right) for left,right in positive if not any(left<end and right>start for start,end in negative)]
    if negative and positive:return 'ambiguous'
    if negative:return 'not_'+family
    return family if positive else None

def latest_bound(objects,kind,own):
    units=list(own_units(own))
    for obj in objects:
        for unit,bound in reversed(units):
            if obj not in bound:continue
            actual=evidence_status(unit,kind)
            if actual is None:continue
            if actual!=kind:return False
            if not kind.startswith('not_') and obj not in WORK.findall(unit):return False
            break
        else:return False
    return bool(objects)

UNSURE=re.compile(r'[?？“”"「」『』]|吗|是不是|是否|可能|大概|也许|好像|不确定|如果|假如|打算|计划|准备|明天|后天|下周|好了再|完成后|听说|据说|他说|她说|说了|说过|问了|不是|并非|不代表|否认|没有说')
def own_units(own):
    # Only a comma continuation inside the same sentence may inherit one
    # explicitly named task. Questions/plans and new objects reset the link.
    for sentence in re.split(r'[。；;！!\n]',own):
        previous=set()
        for unit in re.split(r'[，,]',sentence):
            objects=set(WORK.findall(unit))
            if UNSURE.search(unit):previous=set();continue
            if objects:previous=objects if len(objects)==1 else set()
            bound=objects or previous
            if status(unit) in ('done','sent','submitted'):previous=set()
            yield unit,bound

def _negative_clause_bound(text,own,messages):
    """Authorize only a simple, evidenced negative status paraphrase."""
    value=text.strip().rstrip('。！!')
    names=WORK.findall(value)
    if len(names)>1:return False
    bare=WORK.sub('',value)
    bare=re.sub(r'^(?:我们|我)(?:的)?','',bare).strip()
    if not re.fullmatch(r'(?:还没|还未|没有|没|尚未|未)(?:写好|做好|弄好|搞定|完成|处理好|发出|发送|发好|提交|交上去)(?:了|呢)?',bare):return False
    kind=status(value)
    if kind not in ('not_done','not_sent','not_submitted'):return False
    from content import reply_target
    latest=next((m for m in reversed(messages) if isinstance(m,dict) and reply_target(m)),{})
    targets=set(WORK.findall(str(latest.get('text') or '')))
    objects=set(names)
    if not objects:
        if len(targets)!=1:return False
        objects=targets
    resolved=set()
    for obj in objects:
        matches={target for target in targets if target.endswith(obj)}
        if len(matches)>1:return False
        resolved.update(matches or {obj})
    return latest_bound(resolved,kind,own)

def negative_reply_bound(text,own,messages):
    """Every clause must be a bound negative or verbatim ongoing status.

    Combining known clauses is allowed; no extra sentence, deadline or promise
    is authorized by the presence of one supported negative clause.
    """
    from content import reply_target
    latest=next((m for m in reversed(messages) if isinstance(m,dict) and reply_target(m)),{})
    targets=set(WORK.findall(str(latest.get('text') or '')))
    clauses=[c.strip() for c in re.split(r'[，,。；;！!\n]',text) if c.strip()]
    if not clauses:return False
    negative=False
    for clause in clauses:
        clause=re.sub(r'^(?:但是|不过|只是|但)\s*','',clause)
        if _negative_clause_bound(clause,own,messages):negative=True;continue
        if len(targets)!=1 or UNSURE.search(clause):return False
        names=WORK.findall(clause)
        if len(names)>1:return False
        if names and not next(iter(targets)).endswith(names[0]):return False
        bare=re.sub(r'^(?:我们|我)(?:的)?','',WORK.sub('',clause)).strip()
        kind=status(bare)
        if kind in ('done','sent','submitted') and re.fullmatch(r'已(?:经)?(?:完成|发送|发出|提交)|(?:完成|发送|发出|提交|写好|做好|弄好|搞定|处理好|发好|提交好)了',bare):
            if not latest_bound(targets,kind,own):return False
            continue
        if not re.fullmatch(r'还在(?:校对|核对|处理)',bare):return False
        if not any(targets.issubset(bound) and bare==re.sub(r'^(?:我们|我)(?:的)?','',WORK.sub('',unit)).strip() for unit,bound in own_units(own)):return False
    return negative

def negative_progress_options(own,messages):
    """Finite grounded wording hints; never invent a missing status."""
    from content import reply_target
    latest=next((m for m in reversed(messages) if isinstance(m,dict) and reply_target(m)),{})
    targets=set(WORK.findall(str(latest.get('text') or '')))
    if len(targets)!=1:return []
    target=next(iter(targets));out=[]
    wording={'not_done':'还没完成','not_sent':'尚未发送','not_submitted':'尚未提交'}
    for unit,bound in own_units(own):
        kind=status(unit)
        if target in bound and kind in wording:
            value=target+wording[kind]+'。'
            if negative_reply_bound(value,own,messages) and value not in out:out.append(value)
    return out

def completion_bound(text,own,messages):
    from content import reply_target
    latest=next((m for m in reversed(messages) if isinstance(m,dict) and reply_target(m)),{})
    query=str(latest.get('text') or '')
    asked=bool(WORK.search(query) and re.search(r'进度|进展|写好|完成|做好|搞定|提交|发出|做到|可以交|能交|交了吗',query) and re.search(r'[?？]|怎么样|如何|到哪|没',query))
    targets=set(WORK.findall(query)) if asked else set()
    for clause in re.split(r'[，,。；;！!\n]',text):
        clause=clause.strip();kind=status(clause)
        mine=bool(re.match(r'^(?:我|我们)',clause))
        if not kind or not (mine or (asked and WORK.search(clause))):continue
        if re.match(r'^(?:等|待|如果|假如|要是)',clause):continue
        if not mine and re.search(r'[?？]|吗|了没|是不是|是否',clause):continue
        objects=set(WORK.findall(clause)) or targets
        if asked:
            resolved=set()
            for obj in objects:
                matches={target for target in targets if target.endswith(obj)}
                if len(matches)>1:return False
                resolved.update(matches or {obj})
            objects=resolved
        if not objects and clause in own:continue
        # A paraphrase needs the same named task and status in one reliable
        # own evidence unit; another person's words and another task cannot bind.
        supported=latest_bound(objects,kind,own)
        if not supported:return False
    return True
