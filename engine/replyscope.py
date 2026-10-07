"""Keep one recipient consistent through drafting, review and local checks.

Names identify observed speakers in this snippet, not unique WeChat accounts.
Confirmed same-name identities must be disambiguated rather than guessed.
"""
def resolve_target(messages,reply_to=None):
    from content import reply_target
    incoming=[m for m in messages if isinstance(m,dict) and reply_target(m)]
    if reply_to is not None and not isinstance(reply_to,str):raise ValueError('回复对象应为姓名文字')
    explicit=(reply_to or '').strip()
    if len(explicit)>80:raise ValueError('回复对象名称过长')
    names={str(m.get('name') or '').strip() for m in incoming}-{''}
    if not explicit and len(names)>1 and incoming and not str(incoming[-1].get('name') or '').strip():raise ValueError('当前最后发言人未确认，请选择回复对象或更正归属')
    target=explicit or (str(incoming[-1].get('name') or '').strip() if len(names)>1 and incoming else '')
    if not target:return None
    found=[m for m in incoming if str(m.get('name') or '').strip()==target]
    if not found:raise ValueError('当前记录没有指定对象的发言，请补充聊天或取消指定对象')
    identities={m['speaker_id'] for m in found if m.get('speaker_id') and m.get('identity_confidence')=='user_confirmed' and m.get('identity_scope')=='observation'}
    if len(identities)>1:raise ValueError('同名发言人尚未区分，请先核对身份再选择回复对象')
    return target

def target_context(messages,reply_to=None):
    if not reply_to:return list(messages)
    return [m for m in messages if not isinstance(m,dict) or m.get('from')!='her' or str(m.get('name') or '').strip()==reply_to]
