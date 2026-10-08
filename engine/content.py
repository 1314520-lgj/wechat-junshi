"""Conservative message types and group speaker records (no account-ID claims)."""
from emoji_context import emoji_only, context_notes
import hashlib
import re
from urllib.parse import urlsplit

KINDS={'text','emoji','sticker','image','video','audio','quoted','media_unknown','group_notice','poll','relay','system'}
CARD_KINDS=frozenset({'transfer','red_packet','official_account','link','mini_program','app_card'})
KINDS.update(CARD_KINDS)
LABELS={'text':'文字','emoji':'表情','sticker':'表情包','image':'图片','video':'视频','media_unknown':'未知媒体','group_notice':'群公告','poll':'群投票','relay':'群接龙','system':'系统消息'}

LABELS.update(audio='语音',quoted='引用')
LABELS.update(transfer='转账卡片',red_packet='红包卡片',official_account='公众号入口',link='链接分享',mini_program='小程序入口',app_card='外部应用入口')
_MARKERS={'转账':'transfer','微信转账':'transfer','红包':'red_packet','微信红包':'red_packet','公众号':'official_account','公众号文章':'official_account','链接':'link','小程序':'mini_program','应用卡片':'app_card','外部应用':'app_card'}
_URL=re.compile(r'https?://[^\s<>"\u3000]+',re.I)
_AMOUNT=re.compile(r'(?:[¥￥]\s*|(?:金额|转账金额)\s*[:：]\s*)(\d{1,9}(?:\.\d{1,2})?)(?![\d.])')

def card_kind(text,card=False,allow_markers=True):
    text=str(text or '').strip()
    marker=re.match(r'^\[([^\]\n]+)\]',text)
    if allow_markers and marker and marker[1] in _MARKERS:return _MARKERS[marker[1]]
    lines=[re.sub(r'\s+','',line) for line in text.splitlines() if line.strip()]
    # Require a footer plus another field: discussing money is ordinary text.
    if '微信转账' in lines and (_AMOUNT.search(text) or any(x in lines for x in ('待收款','已收款','已退还','已过期'))):return 'transfer'
    if '微信红包' in lines and len(lines)>1 and (card or any(x in lines for x in ('恭喜发财，大吉大利','恭喜发财,大吉大利','已领取','已领完','已过期'))):return 'red_packet'
    if card and len(lines)>1:
        if '小程序' in lines:return 'mini_program'
        if '公众号' in lines or '微信公众号' in lines:return 'official_account'
        if any(re.fullmatch(r'(?:来自|打开)(?:[A-Za-z][A-Za-z0-9 _-]{1,24}|[^\s]{1,16})(?:App|APP|应用)',line) for line in text.splitlines()):return 'app_card'
    urls=_URL.findall(text)
    if urls and (card or text==urls[0]):
        try:host=(urlsplit(urls[0]).hostname or '').lower()
        except ValueError:return None
        if host=='mp.weixin.qq.com':return 'official_account'
        return 'link'
    return None

def card_details(message):
    """Visible preview fields, never authenticated payment or opened content."""
    kind=message.get('kind')
    if kind not in CARD_KINDS:return None
    visible=message.get('media_description') if message.get('content_source')=='vision' else message.get('text')
    text=str(visible or message.get('media_description') or '').strip()
    details={'type':kind,'scope':'visible_preview','status':'unknown'}
    if kind in ('transfer','red_packet'):
        states=[s for s in ('待收款','已收款','已领取','已领完','已退还','已过期') if re.search(r'(?:^|\n)\s*'+s+r'\s*(?:$|\n)',text)]
        if len(states)==1:details['status']=states[0]
        amounts=_AMOUNT.findall(text)
        if len(amounts)==1:details['visible_amount']=amounts[0]
    else:
        lines=[line.strip() for line in text.splitlines() if line.strip()]
        title=re.sub(r'^\[[^\]]+\]\s*','',lines[0]) if lines else ''
        if title and not _URL.fullmatch(title):details['title']=title[:120]
        urls=_URL.findall(text)
        if urls:
            try:details['url_host']=(urlsplit(urls[0]).hostname or '')[:120]
            except ValueError:pass
        if len(lines)>1 and not _URL.fullmatch(lines[-1]):details['visible_source']=lines[-1][:80]
    return details

def _card_completion_evidence(own,messages,kinds):
    # A new card is a new object, even when its type, amount or title repeats.
    # Keep the explicit own argument usable for callers without self rows.
    latest=max((i for i,m in enumerate(messages) if isinstance(m,dict) and m.get('kind') in kinds),default=-1)
    if latest>=0 and any(isinstance(m,dict) and m.get('from')=='me' for m in messages):
        from replycheck import own_text_evidence
        own=own_text_evidence(messages[latest+1:])
    unsure=r'[?？“”"「」『』]|吗|是否|有没有|如果|假如|(?:^|\s)要是|倘若|听说|据说|他说|她说|说过|问了|^\s*(?:你|他|她)|等(?:我|你|他|她)?(?:领|收|读|看|打开|关注|下载|安装)'
    actions=r'(?:领(?:了|到)|领取(?:了)?|收(?:到|下)(?:了)?|收款(?:了)?|转账(?:了)?|付款(?:了)?)(?:红包|钱)?|钱到账了|到账|(?:读完|看完|打开|关注|下载|安装)(?:了)?(?:这篇|这个|那篇|那个|你发的|文章|公众号|链接|小程序|应用|APP)'
    return '\n'.join(unit for unit in re.split(r'[，,。；;！!\n]',own)
                     if not re.search(unsure,unit) and not any(_card_future_claim(unit,match) for match in re.finditer(actions,unit)))

def _card_future_claim(text,match):
    left=max(text.rfind(c,0,match.start()) for c in '，,。；;！!？?\n')+1
    endings=[text.find(c,match.end()) for c in '，,。；;！!？?\n']
    right=min((x for x in endings if x>=0),default=len(text))
    before=text[left:match.start()];after=text[match.end():right]
    if re.search(r'如果|假如|(?:^|\s)要是|倘若',before):return True
    if re.search(r'等(?:我|你|他|她)?(?:这(?:一)?笔|那(?:一)?笔)?(?:钱|红包)?$',before) and not re.search(r'已经|已|刚刚|刚',match.group(0)):return True
    future=r'(?:稍后|待会儿?|一会儿?|将要)(?:我)?(?:先|再|去)?$|(?:^|我|我们|咱们|你|他|她)(?:准备|打算|计划|会|要|将)(?:先|再|去)?(?:把)?(?:这(?:一)?笔|那(?:一)?笔)?$'
    if re.search(future,before) and not re.search(r'已经|已|刚刚|刚',match.group(0)):return True
    # Explicit future continuation, without a completed-action marker.
    return bool(re.match(r'(?:后|以后|之后)(?:我)?再',after) and not re.search(r'已经|已|刚刚|刚|了$',before+match.group(0)))

def card_reply_guard(text,own,messages=()):
    # The object shown in the chat is not evidence that I acted on it.
    payment_own=_card_completion_evidence(own,messages,{'transfer','red_packet'})
    entry_own=_card_completion_evidence(own,messages,{'official_account','link','mini_program','app_card'})
    patterns=(r'(?:我)?(?:已经|已|刚刚|刚|都)?(?:收到了?钱|钱(?:我)?收(?:到了|了)|钱到账了|已收款|收款了|收下了|领了红包|领取了红包|已领取红包|红包(?:已经|已)?(?:领了|收了)|(?:已经|已|刚刚)?转(?:账)?给你了|(?:已经|已)?付款了)',
              r'(?:我)?(?:已经|已|刚刚|刚|都)?(?:读完|看完|打开|关注|下载|安装)(?:了)?(?:这篇|这个|那篇|那个|你发的|文章|公众号|链接|小程序|应用|APP)',
              r'(?:我)?(?:已经|刚刚|刚)(?:读完|看完|打开|关注|下载|安装)了')
    for index,pattern in enumerate(patterns):
        for match in re.finditer(pattern,text,re.I):
            if _card_future_claim(text,match):continue
            left=max(text.rfind(c,0,match.start()) for c in '，,。；;！!？?')+1
            end=[text.find(c,match.end()) for c in '，,。；;！!？?']
            right=min((x for x in end if x>=0),default=len(text))
            clause_text=text[left:right+1]
            if re.search(r'[?？]|吗|有没有|是否',clause_text) and '我' not in clause_text:continue
            clause=text[max(0,match.start()-6):match.start()]
            if re.search(r'没有|没|未|还没|尚未|别|不要',clause):continue
            evidence=payment_own if index==0 else entry_own
            support=any(match.group(0) in unit and not re.search(r'没有|没|未|[?？]|吗|是否|^你|^他|^她',unit) for unit in re.split(r'[，,。；;！!\n]',evidence))
            if not support:return False
    money=any(m.get('kind') in ('transfer','red_packet') for m in messages if isinstance(m,dict))
    if money and text not in payment_own:
        latest=next((m for m in reversed(messages) if isinstance(m,dict) and reply_target(m)),{})
        # Completed receipt can be phrased without the original '领了红包'
        # spelling. Questions, negation and an actual own statement still pass.
        completed=r'领到(?:了红包|红包了)|红包.{0,8}(?:领到了|领取成功)|(?:收款|领取|转账|付款)成功(?:了)?'
        if latest.get('kind') in ('transfer','red_packet'):
            completed+=r'|(?:我)?(?:已经|已|刚刚|刚)(?:领取|收款)(?=[，,。；;！!？?\s]|$)|(?:我)?(?:已经|已|刚刚|刚)?(?:领取了|领到了|领了|收了)(?=[，,。；;！!？?\s]|$)'
        for claim in re.finditer(completed,text):
            if _card_future_claim(text,claim):continue
            left=max(text.rfind(c,0,claim.start()) for c in '，,。；;！!')+1
            endings=[text.find(c,claim.end()) for c in '，,。；;！!']
            right=min((x for x in endings if x>=0),default=len(text))
            clause=text[left:right]
            if re.search(r'[?？]|吗|是否|有没有',clause):continue
            action=re.search(r'领到|领取|收款|转账|付款|领了|收了',claim.group(0))
            action_start=claim.start()+action.start()
            before=text[max(left,action_start-8):action_start]
            if re.search(r'如果|假如|(?:^|\s)要是|倘若',text[left:action_start]):continue
            if re.search(r'等(?:我|你|他|她)?$',text[left:action_start]) and not re.search(r'已经|已|刚刚|刚',claim.group(0)):continue
            if not claim.group(0).startswith('我') and re.search(r'(?:你|他|她)(?:已经|已|刚刚|刚)?$',before):continue
            if re.search(r'(?:不|没|未|别|不要|还没|尚未)(?:会|要|能|想|我|再|了|曾|有){0,6}$',before):continue
            supported=any(claim.group(0) in unit and not re.search(r'没有|没|未|不|[?？]|吗|是否|^你|^他|^她',unit.strip()) for unit in re.split(r'[，,。；;！!\n]',payment_own))
            if not supported:return False
        money_pattern=r'(?:这|那|这笔|那笔)?钱.{0,6}我.{0,6}(?:存着|存下|收下)|我.{0,6}(?:先)?(?:把)?(?:这|那|这笔|那笔)?钱.{0,4}(?:存着|存下|收下)'
        if latest.get('kind') in ('transfer','red_packet'):money_pattern+=r'|我.{0,6}(?:存着|存下|收下)'
        for claim in re.finditer(money_pattern,text):
            if _card_future_claim(text,claim):continue
            action=re.search(r'存着|存下|收下',claim.group(0))
            prefix=text[max(0,claim.start()-6):claim.start()+action.start()]
            if not re.search(r'(?:不|没|未|别|不要)(?:会|要|能|把|将|先|再|我|这|那|笔|钱|给|替|你){0,8}$',prefix):return False
        amount_claims=re.finditer(r'(?:收到|收到了|收下)[¥￥]?\s*\d|(?:\d+(?:\.\d+)?.{0,8}我.{0,6}(?:存着|存下|收下))',text)
        if any(not _card_future_claim(text,claim) for claim in amount_claims) and not (re.search(r'[?？]|吗|是否',text) and '我' not in text):return False
        receipt_claims=re.finditer(r'收到(?:了|啦|咯|喽)?(?:[，,。！!\s]|$)|到账',text)
        if latest.get('kind') in ('transfer','red_packet') and any(not _card_future_claim(text,claim) for claim in receipt_claims) and not re.search(r'没|未|[?？]|吗|是否',text):return False
    entries=any(m.get('kind') in ('official_account','link','mini_program','app_card') for m in messages if isinstance(m,dict))
    # An unrelated quoted chat is not the article's body. Only explicitly
    # supplied body text after the latest entry extends the visible preview.
    latest_entry=max((i for i,m in enumerate(messages) if isinstance(m,dict) and m.get('kind') in ('official_account','link','mini_program','app_card')),default=-1)
    body=any(m.get('kind','text') in ('text','quoted') and re.search(r'^(?:\[引用\]\s*|引用[：:]\s*)?(?:正文|原文|文章内容)[：:]\s*\S',str(m.get('text') or '')) for m in messages[latest_entry+1:] if isinstance(m,dict))
    if entries and not body and text not in entry_own:
        for clause in re.split(r'[，,。；;！!]',text):
            assessment=re.search(r'(?:文章|报道|正文|内容)(?:写得|讲得|说得|挺|很|真|不错|有意思|有道理|靠谱|精彩|好|差)|(?:这篇|那篇)(?:文章|报道)?(?:感觉|看着|看起来)?(?:写得|讲得|说得|挺|很|真|不错|有意思|有道理|靠谱|精彩|好|差)',clause)
            if assessment and not re.search(r'标题|[?？]|吗|是否|是不是',clause):return False
        if re.fullmatch(r'(?:这篇|这个|这|它)?(?:感觉|看着|看起来)?(?:挺|很|真)?(?:不错|有意思|有道理|靠谱|精彩|好|很好)(?:的)?[呀啊呢吧啦！!。\s]*',text):return False
    return True

def context_limits(messages):
    kinds={m.get('kind') for m in messages if isinstance(m,dict)}
    notes=[]
    if kinds & {'transfer','red_packet'}:
        notes.append('支付卡片不是收款证据；以本人文字确认操作为准。没有本人确认时，只致谢或询问用途，不说收到金额、收下、存着或已领取。')
    if kinds & {'official_account','link','mini_program','app_card'}:
        notes.append('入口仅是预览；没有正文时只回应标题或问内容，不评价文章好坏，不说已读或已打开。')
    if kinds & {'sticker','emoji'}:
        notes.append('表情结合前文理解，不固定判断情绪；任务通知配表情仍不是本人已答应完成任务。')
    emoji_notes=context_notes(messages)
    if emoji_notes:notes.append(emoji_notes)
    return ' '.join(notes)

def reply_target(message):
    """System events stay in evidence but are not another person's utterance."""
    return message.get('from')=='her' and message.get('kind','text') not in ('system','time')

def classify(text,card=False):
    text=str(text or '').strip()
    detected=card_kind(text,card)
    if detected:return detected
    if re.match(r'^[#＃]\s*接龙(?:\s|$)',text):return 'relay'
    if text.startswith('[语音]'):return 'audio'
    if text.startswith(('[引用]','引用：','引用:')):return 'quoted'
    if re.search(r'^(?:群公告|公告[：:])',text):return 'group_notice'
    if re.search(r'^(?:群投票|投票(?:$|[：:]))',text) or ('投票' in text and any(k in text for k in ('单选','多选','截止','参与','选项','票数'))):return 'poll'
    if re.search(r'^(?:群接龙|接龙(?:$|[：:]))',text) or ('接龙' in text and (re.search(r'(?:^|\n)\s*\d+[.、\s]',text) or any(k in text for k in ('参与接龙','接龙统计','填写接龙')))):return 'relay'
    if re.search(r'邀请.{0,30}加入群聊|通过扫描.{1,120}加入群聊|撤回了一条消息|修改了群名|加入了群聊|你已添加',text):return 'system'
    if emoji_only(text):return 'emoji'
    return 'text'

def speaker_key(session,name):
    if not name:return ''
    return hashlib.sha256((session+'\0'+name.strip()).encode()).hexdigest()[:16]

def participants(messages, session):
    result={}
    for m in messages:
        name=m.get('name')
        if m.get('from')=='her' and name:
            key=speaker_key(session,name)
            row=result.setdefault(key,{'id':key,'name':name,'messages':0,'identity':'display_name_only'})
            row['messages']+=1
            row['last_time']=m.get('time')
    return list(result.values())

def annotate(messages, session):
    out=[]
    for index,m in enumerate(messages):
        m=dict(m)
        kind=m.get('kind','text')
        if kind=='text' and m.get('content_source')!='user_corrected':m['kind']=classify(m.get('text'))
        elif kind=='media_unknown' and m.get('content_source')!='user_corrected':
            detected=card_kind(m.get('text'),card=True,allow_markers=False)
            if detected:m['kind']=detected
        details=card_details(m)
        if details:m['card_details']=details;m['card_scope']='visible_preview'
        elif m.get('card_details'):
            m.pop('card_details',None);m.pop('card_scope',None)
        observation=hashlib.sha256((session+'\0'+str(index)+'\0'+str(m.get('name',''))+'\0'+str(m.get('text',''))).encode()).hexdigest()[:16]
        m.setdefault('speaker_id','observation-'+observation if m.get('from')=='her' else 'self')
        m.setdefault('identity_confidence','display_name_only' if m.get('name') else 'unknown')
        out.append(m)
    return out
