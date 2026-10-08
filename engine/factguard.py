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

_PERIODS={
    '下班前':re.compile(r'(?:临(?:近)?|快(?:要|到)?|马上(?:要)?).{0,2}下班|下班前'),
    '下班后':re.compile(r'下班(?:后|以后|之后)'),
    '午休':re.compile(r'午休'),
    '半夜':re.compile(r'大?半夜|深夜'),
    '一大早':re.compile(r'一大早'),
}
_UNREAD=re.compile(r'(?:我|^)(?:还|也|尚|其实|确实|根本|真)?(?:没(?:有)?|未)(?:点(?:开|进(?:去)?)|打开|读(?:过|完)?|看(?:过|完)?)(?!懂|清|到|出来)')
_PHONE_EXCUSE=re.compile(r'(?:我|^)(?P<period>这[一二两三四五六七八九十几\d]+天|最近)?(?:我)?(?:(?:刚才|刚刚|之前|一直|确实|其实|根本|刚|真的|真|还|都|就|也)){0,4}(?:没(?:有)?(?:顾(?:得)?上|来得及|空|时间)?|未)(?:看|碰|拿|用)手机')
_PAST_HABIT=re.compile(r'^(?:我)?(?:之前|以前|原来|过去)(?:一直|总是|都|每次)(?P<fact>[^，,。；;！!\n?？]{1,32})')
_MESSAGE_EXCUSE=re.compile(r'(?:我|^)(?P<period>这[一二两三四五六七八九十几\d]+天|最近)?(?:我)?(?:(?:刚才|刚刚|之前|一直|确实|其实|根本|刚|真的|真|还|都|就|也)){0,4}没(?:有)?(?:顾(?:得)?上|来得及)(?P<action>看|回)(?:消息|微信|你)?(?=$|[\s，,。；;！!？?])')
_REPLY_INTENT=re.compile(r'(?:我|^)(?:真的|真|其实|确实|也)?不是故意(?P<action>不回|没回|晚回|不理)(?:你|消息)?')
_UNUSED_ENTRY=re.compile(r'(?:我|^)(?:还|也|尚|其实|确实|根本|真)?(?:没(?:有)?|未)(?P<action>使用(?:过)?|用(?:过)?|试用(?:过)?|试(?:过)?|体验(?:过)?|玩(?:过)?|接触(?:过)?|见过|听过|了解过|打开(?:过)?|点开(?:过)?|点进(?:去)?(?:过)?|安装(?:过)?|装(?:过)?|下载(?:过)?|关注(?:过)?)')
_REMAINING_WORK=re.compile(r'(?:还差|还剩|尚余|剩下|还有)(?P<count>\d{1,3}|[一二两三四五六七八九十]{1,3})(?P<unit>处|项|页|题|步|份)')
_ABSOLUTE_PROMISE=re.compile(r'(?P<fact>(?:(?:(?:下次|以后|往后|今后)(?:我)?(?:绝(?:对)?|保证)?(?:再也)?不(?:会)?(?:再)?|(?:我(?:保证)?|^)(?:再也|绝(?:对)?)不(?:会)?(?:再)?|(?:我(?:保证)?|^)不(?:会)?再|我保证不(?:会)?(?:再)?)(?:这样|犯(?:错|同样的错)?|忘(?:记)?|失约|让你等|让你失望|让你难过)|(?:下次|以后|往后|今后)(?:我)?(?:一定|肯定|保证|绝对)(?:会)?(?:提前|及时|准时)?(?:告诉你|(?:跟你|和你)(?:说|讲)(?:一声)?|(?:说|讲)一声|通知你|回复你|回你|做到|改正|注意))[^，,。；;！!\n?？]{0,12})')
_PERSONAL_ACTIVITY=re.compile(r'(?:^|我(?:也|现在|这会儿|此刻)?)(?P<fact>(?:正(?:在)?|在)(?:吃(?:饭|面|火锅|烧烤|饺子|米饭|外卖)|睡觉|开车|坐车|上班|上课|开会|加班|逛街|打游戏|运动|跑步|洗澡|看电影|家(?:里)?|公司|学校|宿舍|医院|路上)|刚(?:刚)?(?:下班|到家|睡醒|吃完饭|起床))')

def personal_assertion_issue(text,messages):
    """Narrow concrete facts and absolute pledges found in observed chat replies.

    Ordinary care and suggestions are allowed. Reliable self-authored clauses,
    never incoming text, quotes or questions, can support the same assertion.
    These lexical categories do not attempt to classify every personal fact.
    """
    from replycheck import own_text_evidence,reliable_latest_spoken,same_observed_speaker
    own_units=_assertive_units(own_text_evidence(messages))
    def normalize(value):
        value=value.replace('正在','在').replace('刚刚','刚').replace('在家里','在家')
        return ('在'+value[1:]) if value.startswith('正') else value
    spoken=reliable_latest_spoken(messages)
    query=str(spoken.get('text') or '')
    eating_foods={normalize(match['fact'])[2:] for source in own_units for match in _PERSONAL_ACTIVITY.finditer(source.strip()) if normalize(match['fact']).startswith('在吃')}
    own_eating=bool(eating_foods)
    asks_eating=bool(re.search(r'吃完|吃好了?',query) and re.search(r'[?？]|吗|没|呀|吧',query))
    meal_progress=re.compile(r'(?:^|我(?:现在|这会儿)?)(?P<fact>(?:快(?:要)?|马上|差不多)(?:吃完|吃好)|还(?:得|要|需要)(?:一会儿?|一点时间|几分钟))')
    def progress_value(value):return value.replace('还得','还要').replace('还需要','还要').replace('一会儿','一会')
    known_progress={progress_value(match['fact']) for source in own_units for match in meal_progress.finditer(source.strip())
                    if not re.search(r'[“”"「」『』]|说了|说过|没说|没有说',source)}
    modifiers=r'(?P<mod>(?:(?:现在|这会儿|真的|真|很|挺|有点|特别|非常|太|并不|没有|没|不|一点也不|不是)){0,4})'
    feeling_report=re.compile(r'(?:^|我)'+modifiers+r'(?P<emotion>生气|难过|伤心)')
    feeling_claim=re.compile(r'(?:我(?:知道|看得出)你(?:现在|这会儿)?|你(?:现在|这会儿)?肯定(?:是)?)'+modifiers+r'(?P<emotion>生气|难过|伤心)')
    def feeling_state(mod):
        if re.search(r'不是(?:不|没有|没)',mod):return True
        if re.search(r'(?:不是|没有|不|没)(?:很|挺|有点|特别|非常|太)',mod):return None
        return not bool(re.search(r'不|没',mod))
    food_amount=re.compile(r'(?:(?:^|我(?:吃的|点的|的|这边)?|这(?:碗|份|盘)?|\s)(?P<food>米饭|饭菜|面条|饺子|馄饨|烧烤|火锅|外卖|食物|面|饭|菜|粥)(?:的)?(?P<measure>分量|份量|量)?|(?P<portion>分量|份量))(?P<mod>(?:(?:有点儿?|有些|有一点|一点|挺|很|太|比较|稍微|并不|不|没有|没|不是|特别|非常)){0,3})(?P<amount>多|少|大|小)')
    def amount_value(match):
        if match['amount'] in ('大','小') and not (match['measure'] or match['portion']):return None
        state=feeling_state(match['mod'])
        if state is None:return None
        food=match['food'] or (next(iter(eating_foods)) if len(eating_foods)==1 else 'portion')
        food={'面条':'面','米饭':'饭'}.get(food,food)
        return (food,{'大':'多','小':'少'}.get(match['amount'],match['amount']),state)
    known_amounts={amount_value(match) for source in own_units for match in food_amount.finditer(source.strip()) if not re.search(r'[“”"「」『』]|说了|说过|没说|没有说',source)}-{None}
    # A known cancellation without advance notice establishes the omission,
    # not an external trigger or lack of time to tell the other person.
    cancellation_index=None
    for index,message in enumerate(messages):
        if not isinstance(message,dict):continue
        source=own_text_evidence([message])
        if any(cancelled(unit) for unit in _assertive_units(source)):cancellation_index=index
    event_units=_assertive_units(own_text_evidence(messages[cancellation_index:])) if cancellation_index is not None else []
    event_units=[source for source in event_units if not re.search(r'[“”"「」『』]|说了|说过|没说|没有说|听说|据说|好像',source)]
    external_notice=re.compile(r'(?P<party>那边|对方|他们|单位|公司|领导)(?:(?:临时|刚刚|刚|突然|又|才|刚才)){0,2}(?:通知|告知)(?:我|的)?')
    tell_excuse=re.compile(r'(?:^|我)(?:也|还|确实|其实|真|刚(?:刚)?){0,3}(?P<reason>没(?:有)?(?:来得及|顾(?:得)?上))(?:提前)?(?:(?:跟你|和你)(?:说|讲)|(?:告诉|通知|告知)你|(?:说|讲)(?:一声)?)')
    known_notices={match['party'] for source in event_units for match in external_notice.finditer(source) if not re.search(r'不是|并非|不代表',source[:match.start()])}
    known_tell_reasons={'time' if '来得及' in match['reason'] else 'attention' for source in event_units for match in tell_excuse.finditer(source.strip())}
    feelings={}
    for message in messages:
        if not isinstance(message,dict) or message.get('from')!='her' or message.get('kind','text') not in ('text','emoji') or not spoken or not same_observed_speaker(spoken,message):continue
        low=message.get('vision_uncertain') or any('置信度偏低' in str(x) for x in (message.get('uncertainties') or []))
        if low and message.get('text_confirmation')!='user_confirmed':continue
        for source in _assertive_units(str(message.get('text') or '')):
            if re.search(r'[“”"「」『』]|听说|据说|他说|她说|我说|我问|不代表|没说|没有说',source):continue
            for match in feeling_report.finditer(source.strip()):feelings[match['emotion']]=feeling_state(match['mod'])
    for clause in re.split(r'[，,。；;！!\n]',str(text)):
        unit=clause.strip()
        if re.search(r'如果|假如|要是|假设',unit):continue
        questioning=bool(re.search(r'[?？]|吗|是否|是不是',unit))
        if cancellation_index is not None and not questioning:
            for claim in external_notice.finditer(unit):
                if re.search(r'不是|并非|不代表',unit[:claim.start()]) or re.match(r'(?:的话|话)',unit[claim.end():]):continue
                if claim['party'] not in known_notices:return '当前取消只说明没有提前告知，不能补出那边或公司临时通知等外部原因'
            for claim in tell_excuse.finditer(unit):
                if re.match(r'的话',unit[claim.end():]):continue
                reason='time' if '来得及' in claim['reason'] else 'attention'
                if reason not in known_tell_reasons:return '没有提前说不等于没来得及或没顾上告知；不能为当前取消编造这些推脱理由'
        if own_eating and asks_eating and not questioning and not re.search(r'可能|也许|好像|不确定|吃完(?:后|再|就|的话)',unit):
            if any(progress_value(match['fact']) not in known_progress for match in meal_progress.finditer(unit)):
                return '本人只说正在吃饭，不能据此补出快吃完或还需要一会儿；直接回应还在吃即可'
            for claim in food_amount.finditer(unit):
                value=amount_value(claim)
                if value is not None and value not in known_amounts and not re.match(r'(?:的话|就)',unit[claim.end():]):
                    return '本人只说正在吃饭，不能编造食物分量多或少来解释为什么没吃完；可直接回应还在吃'
        if not questioning and not re.search(r'可能|也许|好像|不确定',unit):
            for claim in feeling_claim.finditer(unit):
                state=feeling_state(claim['mod'])
                if state is None or claim['emotion'] not in feelings or feelings[claim['emotion']]!=state:
                    return '表情与语境只能帮助理解，不能断言我知道或看得出对方的情绪；可靠本人情绪表述才支持确定回应'
        for pattern in (_ABSOLUTE_PROMISE,_PERSONAL_ACTIVITY):
            if pattern is _PERSONAL_ACTIVITY and re.search(r'[?？]|吗|是否|是不是',unit):continue
            supports=[m for source in own_units for m in pattern.finditer(source.strip())
                      if pattern is not _ABSOLUTE_PROMISE or not re.search(r'(?:不敢|不能|没法|无法|不)(?:保证|承诺)',source.strip()[:m.start()])]
            for claim in pattern.finditer(unit):
                if pattern is _ABSOLUTE_PROMISE and (re.search(r'[?？]|吗',unit) or re.search(r'(?:不敢|不能|没法|无法|不)(?:保证|承诺)',unit[:claim.start()])):continue
                if not any(normalize(m['fact'])==normalize(claim['fact']) for m in supports):
                    return '没有本人明确依据，不能添加以后绝不再犯的承诺' if pattern is _ABSOLUTE_PROMISE else '没有本人可靠文字，不能编造我正在吃饭、刚下班、刚到家或具体位置来让聊天自然'
    return None

def remaining_quantity_issue(text,messages):
    """Do not invent a count of remaining work to sound helpful.

    This only covers concrete count assertions, not general task completion.
    First-person quantities require the user's own reliable text. Questions,
    suggestions and uncertainty never establish a remaining count.
    """
    def normalize(value):
        if value.isdigit():return int(value)
        digits={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
        if '十' in value:
            left,right=value.split('十',1);return digits.get(left,1)*10+digits.get(right,0)
        return digits.get(value,-1)
    for clause in re.split(r'[，,。；;！!\n]',str(text)):
        claims=list(_REMAINING_WORK.finditer(clause))
        if not claims or re.search(r'[?？]|吗|是否|是不是|有没有|如果|假如|要是|假设|可能|也许',clause):continue
        own=bool(re.search(r'我|这边',clause[:claims[0].start()]))
        evidence=[]
        for m in list(messages)[-10:]:
            if not isinstance(m,dict) or m.get('kind','text') not in ('text','emoji') or m.get('from') not in ('me','her'):continue
            if own and m.get('from')!='me':continue
            low=m.get('vision_uncertain') or any('置信度偏低' in str(x) for x in m.get('uncertainties',[]))
            if low and m.get('text_confirmation')!='user_confirmed':continue
            for unit in _assertive_units(str(m.get('text') or '')):
                if re.search(r'不是|并非|并不|不再|已经不',unit):continue
                evidence.extend((normalize(x['count']),x['unit']) for x in _REMAINING_WORK.finditer(unit))
        if any((normalize(x['count']),x['unit']) not in evidence for x in claims):return '原文没有给出剩余事项数量，不能凭空添出还差几处、几项、几页或几题'
    return None

def _entry_action(match):
    verb=match['action']
    for action,prefixes in [('install',('安装','装')),('download',('下载',)),('follow',('关注',)),('use',('使用','用')),('try',('试用','试')),('experience',('体验',)),('play',('玩',)),('open',('打开','点开','点进')),('exposure',('接触',)),('see',('见',)),('hear',('听',)),('know',('了解',))]:
        if verb.startswith(prefixes):return action
    return None


def _assertive_units(text):
    return [unit for unit in re.split(r'[，,。；;！!\n]',text)
            if not re.search(r'[?？]|吗|是否|是不是|有没有|如果|假如|要是|假设|可能|也许|不确定',unit)]


def conversational_detail_issue(text,messages):
    """Guard observed natural-chat embellishments, including negative action claims."""
    from replycheck import own_text_evidence
    from content import reply_target
    personal=personal_assertion_issue(text,messages)
    if personal:return personal
    quantity=remaining_quantity_issue(text,messages)
    if quantity:return quantity
    own=own_text_evidence(messages)
    own_units=_assertive_units(own)
    habit_facts=[match['fact'].strip() for unit in own_units for match in _PAST_HABIT.finditer(unit.strip())]
    for clause in re.split(r'[，,。；;！!\n]',str(text)):
        intent=_REPLY_INTENT.search(clause.strip())
        if intent and not re.search(r'[?？]|吗|如果|假如|要是|假设',clause):
            known=[m for unit in own_units for m in _REPLY_INTENT.finditer(unit.strip())]
            if not any(m['action']==intent['action'] for m in known):
                return '没有本人表态，不能编造不是故意不回的过去意图；接住对方等待的事情即可'
        history=_PAST_HABIT.search(clause.strip())
        if history and history['fact'].strip() not in habit_facts and not re.search(r'[?？]|吗|如果|假如|要是|假设',clause):
            return '没有本人依据，不能为这次完成的事补出以前一直如何的经历'
        for pattern in (_PHONE_EXCUSE,_MESSAGE_EXCUSE):
            claim=pattern.search(clause.strip())
            supports=[match for unit in own_units for match in pattern.finditer(unit.strip())]
            supported=claim and any((not claim['period'] or claim['period']==source['period']) and (pattern is _PHONE_EXCUSE or claim['action']==source['action']) for source in supports)
            if claim and not supported:
                # A genuine question or conditional is not a claimed explanation.
                if not re.search(r'[?？]|吗|如果|假如|要是|假设',clause):
                    return '没有本人依据，不能编造没看手机、没顾上看或没来得及回作为迟回的理由；回应当前消息即可'
    latest=next((m for m in reversed(messages) if isinstance(m,dict) and reply_target(m)),{})
    target=latest.get('speaker_id') if latest.get('identity_confidence')=='user_confirmed' and latest.get('identity_scope')=='observation' else None
    reliable=[]
    for m in messages:
        if not isinstance(m,dict) or m.get('kind','text') not in ('text','emoji'):continue
        if m.get('from')=='her' and target and m.get('speaker_id')!=target:continue
        low=m.get('vision_uncertain') or any('置信度偏低' in str(x) for x in m.get('uncertainties',[]))
        if low and m.get('text_confirmation')!='user_confirmed':continue
        reliable.append(str(m.get('text') or ''))
    evidence='\n'.join(unit for source in reliable for unit in _assertive_units(source)
                       if not re.search(r'不是|并非|不在|别|不要',unit))
    for clause in re.split(r'[，,。；;！!\n]',str(text)):
        # Ask/conditional scope is clause-local: a later question cannot excuse
        # a preceding unsupported assertion about the time of the event.
        question=bool(re.search(r'[?？]|吗|是否|是不是|有没有',clause))
        hypothetical=bool(re.search(r'如果|假如|要是|假设',clause))
        rest_suggestion=bool(re.fullmatch(r'(?:你)?(?:下班后|午休)(?:可以|记得|先|就|好好|多)?(?:歇(?:会|一会|歇)?|休息(?:一下)?|放松(?:一下)?|睡(?:会|一会))(?:儿|吧|啊)?',clause.strip()))
        for label,pattern in _PERIODS.items():
            if pattern.search(clause) and not pattern.search(evidence) and not (question or hypothetical or rest_suggestion):
                return '原文没有说明'+label+'，不要为了共情补出事情发生的时段'
    entry_kinds={'official_account','link','mini_program','app_card'}
    has_entry=any(isinstance(m,dict) and m.get('kind') in entry_kinds for m in messages)
    question=str(latest.get('text') or '')
    usage_context=latest.get('kind') in entry_kinds or bool(re.search(r'用过|用了|安装|装过|下载|关注|这个|这款|小程序|应用|软件|App|app',question))
    if has_entry and usage_context:
        entries=[i for i,m in enumerate(messages) if isinstance(m,dict) and m.get('kind') in entry_kinds]
        # A negative experience with an earlier entry is not transferable to a
        # newly shared app. With one entry, preceding self-report can refer to it.
        source=own_text_evidence(messages[entries[-1]+1:] if len(entries)>1 else messages)
        known={_entry_action(match) for unit in _assertive_units(source) for match in _UNUSED_ENTRY.finditer(unit.strip())}
        for unit in re.split(r'[，,。；;！!\n]',str(text)):
            claim=_UNUSED_ENTRY.search(unit.strip())
            if claim and _entry_action(claim) not in known:
                return '入口预览不能证明本人没用、没试、没装、没打开或其他否定经历；不能换同义词编造，可问对方使用体验'
    explicit_entry=bool(re.search(r'这篇|那篇|文章|正文|链接|小程序|网页|公众号',question))
    other_object=bool(re.search(r'电影|电视剧|球赛|比赛|演唱会|照片',question))
    article_context=latest.get('kind') in entry_kinds or explicit_entry or (not other_object and bool(re.search(r'看了|看过|你看',question)))
    if has_entry and article_context:
        for claim in (match for unit in re.split(r'[，,。；;！!\n]',str(text)) for match in _UNREAD.finditer(unit.strip())):
            action='open' if re.search(r'点开|点进|打开',claim.group()) else 'read'
            supported=any(('open' if re.search(r'点开|点进|打开',m.group()) else 'read')==action
                          for unit in _assertive_units(own) for m in _UNREAD.finditer(unit))
            if not supported:return '没有本人依据，不能声称我没看、没读或没打开；直接回应标题或问内容'
    return None

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
    if conversational_detail_issue(text,messages):return False
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
