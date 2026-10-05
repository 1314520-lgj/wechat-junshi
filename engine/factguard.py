"""Conservative date/time/place/event binding to individual evidence units.

This is a lexical guard, not general semantic understanding. Unknown facts
require clarification; model review remains mandatory.
"""
import re
DATE=re.compile(r'今天|今晚|今早|明天|明晚|明早|后天|昨天|昨日|下周|本周|(?:星期|周)[一二三四五六日天]|\d{1,2}月\d{1,2}[日号]|\d{1,2}/\d{1,2}')
CLOCK=re.compile(r'(?:上午|下午|晚上|凌晨|早上|中午)?\s*(?:\d{1,2}|[零一二两三四五六七八九十]{1,3})(?:[:：]\d{2}|点(?:半|\d{1,2}分)?)')
def dates(text):
    out=set()
    for x in DATE.findall(text):
        x={'今晚':'今天','今早':'今天','明晚':'明天','明早':'明天','昨日':'昨天'}.get(x,x)
        x=x.replace('星期','周').replace('周天','周日')
        m=re.fullmatch(r'(\d{1,2})(?:月|/)(\d{1,2})(?:[日号])?',x)
        if m:x=f'{int(m[1])}/{int(m[2])}'
        out.add(x)
    return out
def places(text):
    value=DATE.sub(' ',CLOCK.sub(' ',text))
    value=re.sub(r'原文|通知|图上|记录|写的是|写的|位于|地点|集合|开会|会议(?!室)|聚餐|吃饭|时间|是在|在|到|去|是|我看到|安排',' ',value)
    named=set(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]{0,12}(?:门口|会议室|教室|食堂|操场|办公室|车站|餐厅|体育馆|图书馆|教学楼|校门)',value))
    # Definite references imply a previously established shared place, even in
    # a proposal/question. Generic suggestions to find a new place do not.
    references=re.findall(r'(?:楼下|旁边|附近)(?:的)?(?:那家|这家)(?:店|餐馆|馆子)?|(?:那家|这家)(?:店|餐馆|馆子)|老地方',value)
    return named|{x.replace('的','') for x in references}
def events(text):return set(re.findall(r'聚餐|开会|会议|上课|交作业|培训|面试',text))

DENIED=re.compile(r'(?<!是)不是|并非|不在')
TENTATIVE=re.compile(r'[?？]|吗|是否|是不是|可能|也许|不确定|如果|假如')

def cancelled(text):
    negatives=[m.span() for m in re.finditer(r'(?:没有|尚未|并未|不是|未|没|不)\s*取消',text)]
    return any(not any(m.start()<right and m.end()>left for left,right in negatives) for m in re.finditer('取消',text))

def evidence_units(source):
    # Keep continuations inside their sentence; a bare cancellation tail
    # applies to that sentence, never to another sentence's arrangement.
    for sentence in re.split(r'[。\n；;]',source):
        units=re.split(r'[，,]',sentence)
        cancellation_tail=any(cancelled(u) and not (dates(u) or places(u) or events(u) or CLOCK.search(u)) for u in units)
        for index,unit in enumerate(units):yield unit,(cancelled(unit) or cancellation_tail),index==0
def facts_bound(text,messages,times):
    ds,ps,es,ts=dates(text),places(text),events(text),times(text)
    if not (ds or ps or ts):return True
    # A direct second-person location statement/question must not borrow facts
    # from another explicitly confirmed person in a group. Visual similarity
    # never supplies this identity link; quoted/system text is not self-report.
    latest=next((m for m in reversed(messages) if isinstance(m,dict) and m.get('from')=='her' and m.get('kind') not in ('system','time')),None)
    if latest and latest.get('speaker_id') and latest.get('identity_confidence')=='user_confirmed' and latest.get('identity_scope')=='observation' and re.match(r'^你[^。；;\n]{0,24}在',text.strip()):
        target=latest['speaker_id']
        messages=[m for m in messages if isinstance(m,dict) and m.get('speaker_id')==target and m.get('identity_confidence')=='user_confirmed' and m.get('identity_scope')=='observation' and m.get('kind','text') in ('text','emoji')]
    fact_sentences=[unit for unit in re.split(r'[。\n；;]',text) if dates(unit) or places(unit) or times(unit)]
    fact_parts=[unit for unit in re.split(r'[。\n；;，,]',text) if dates(unit) or places(unit) or times(unit)]
    nonassertive=bool(fact_parts) and all(re.search(r'能不能|能否|无法保证|没法保证|不保证|不确定',unit) for unit in fact_parts)
    qualified=bool(fact_sentences) and all(re.search(r'看到|图上|识别|可能|待核对|确认|是不是|对吗|通知(?:上|里|写)',unit) for unit in fact_sentences)
    if re.search(r'(?:我|我们|已经|已|现已|刚刚)确认|确认了|已核实|核实了',text) and not re.search(r'^(?:我|我们)确认一下[，,\s]*(?:是不是|是否)',text.strip()):qualified=False
    reply_modes={(bool(DENIED.search(unit)),is_cancelled) for unit,is_cancelled,_ in evidence_units(text) if dates(unit) or places(unit) or times(unit)}
    # Mixed asserted/cancelled or affirmed/denied factual clauses cannot lend
    # each other a status. Complex corrections remain conservatively blocked.
    if len(reply_modes)!=1:return False
    reply_denied,reply_cancelled=next(iter(reply_modes))
    for m in messages:
        if not isinstance(m,dict):continue
        original=str(m.get('text') or '')
        faithful_own_question=m.get('from')=='me' and text.strip()==original.strip()
        uncertain=m.get('vision_uncertain') or any('置信度偏低' in u for u in m.get('uncertainties',[]))
        if uncertain and m.get('text_confirmation')!='user_confirmed' and not qualified:continue
        description=str(m.get('media_description') or '')
        # Vision/ASR output is never upgraded to human-confirmed fact.
        sources=[original]+([description] if qualified else [])
        for source in sources:
            previous=None
            for unit,source_cancelled,first in evidence_units(source):
                if first:previous=None
                uds,ups,ues,uts=dates(unit),places(unit),events(unit),times(unit)
                # A continuation can supply the place after a time-only clause.
                if previous and not (uts or uds or ues):
                    uds=previous[0];uts=previous[3];ues=previous[2]
                elif not uds and previous:uds=previous[0]
                relation_matches=bool(DENIED.search(unit))==reply_denied and source_cancelled==reply_cancelled
                reliable_assertion=not TENTATIVE.search(unit) or qualified or nonassertive or faithful_own_question
                if relation_matches and reliable_assertion and ds.issubset(uds) and all(any(t & u for u in uts) for t in ts) and all(any(p==q or p in q for q in ups) for p in ps) and (not es or es.issubset(ues)):
                    return True
                previous=(uds,ups,ues,uts)
    return False
