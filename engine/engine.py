# -*- coding: utf-8 -*-
"""整条链的唯一入口：对话 → Jev 判断 → 带着判断起草 3 条 → 排序 → 结构化结果。

三段式（与 JevChat-Windows 同口径，判断/排序改用 DeepSeek JSON）：
判断失败自动退回盲起草；排序失败按第一条推荐。
"""
from __future__ import annotations

import re
import modelrouter
from deepseek import LlmError, chat
from draft import draft_candidates
from replycheck import review
from goutoujunshi import JUDGE_LAYER
from questions import (build_judge_prompt, build_rank_prompt, build_state,
                       guidance_text, parse_judgment, parse_rank)

_REPLY_IDX = {"reply_a": 0, "reply_b": 1, "reply_c": 2}

def _usage_snapshot():
    route=modelrouter.current()
    if route is None:return {}
    return {'requests':route.get('calls',0),'phase':route.get('phase','start'),
            'cost_reserved':route.get('cost_reserved',0.0),
            'draft_attempts':route.get('draft_attempts',0)}

def calls_available(needed):
    route=modelrouter.current()
    return route is None or route['settings'].get('max_model_calls',6)-route['calls']>=needed


def needs_context_judgment(messages):
    """Extra interpretation requires usable evidence, not a placeholder alone.

    All scenes still pass grounding review. Structured readable cards, quotations,
    understood media and long context retain the additional judgment/ranking.
    """
    from content import CARD_KINDS
    chars = 0
    for m in messages:
        chars += len(m.get('text') or '')
        if not media_unresolved(m):
            chars += len(m.get('media_description') or '')
        if chars > 1600:
            return True
    for m in messages:
        kind = m.get('kind', 'text')
        # These visible objects already reach drafting and integrated review.
        # Their type alone doesn't justify another interpretation/rank call.
        if kind in ('text', 'emoji', 'sticker', 'system', 'time') or kind in CARD_KINDS:
            continue
        if media_unresolved(m):
            continue
        if m.get('media_description') and not m.get('vision_uncertain'):
            return True
        if kind in ('quoted', 'group_notice', 'poll', 'relay') and (m.get('text') or '').strip():
            return True
    return False


def media_unresolved(m):
    from content import CARD_KINDS
    kind=m.get('kind')
    if kind in CARD_KINDS:return bool(m.get('vision_uncertain') or not (m.get('text') or m.get('media_description')))
    if kind=='media_unknown':return True
    if kind=='video':
        return bool(m.get('media_understanding_complete') is not True or not m.get('media_description') or m.get('vision_uncertain'))
    if m.get('kind')=='audio':
        segments=m.get('media_transcript')
        return not (m.get('media_association_source')=='user_confirmed_file_association' and m.get('media_understanding_complete') is True and m.get('transcript_confirmation')=='user_verified_full_audio' and isinstance(segments,list) and segments and all(isinstance(s,dict) and isinstance(s.get('text'),str) and s['text'].strip() and s.get('uncertain') is False for s in segments))
    # Missing a screenshot/crop is missing evidence, not proof of understanding.
    return bool(kind in ('image','sticker') and (not m.get('media_description') or m.get('vision_uncertain') or m.get('media_understanding_complete') is False))

def reply_evidence_signature(messages):
    """Ignore only unusable derived media observations, never readable facts."""
    result=[]
    for message in messages:
        row=dict(message)
        if media_unresolved(row):
            row['kind']='unresolved_media'
            for field in ('media_description','thumbnail_description','vision_confidence',
                          'vision_uncertain','media_understanding_complete','content_source'):
                row.pop(field,None)
        result.append(row)
    return result


def _analyze_impl(messages: list, relationship: str, api_key: str,
            model: str = "deepseek-flash", judge_model: str | None = None,
            timeout: float = 30, context: int = 10,
            reply_to: str | None = None, style: str = "", thinking: bool = False,
            junshi_layer: bool = True, memory: dict | None = None, progress=None, settings=None, vision_key="", extension_dir="") -> dict:
    """返回 {candidates, best_index, best_reply, scores, answers, usage, reply_to}。
    判断/排序走 judge_model（可配更强的），起草走 model（便宜、快）。
    只有对方最新说话时才有意义调它——是不是该触发由调用方判断。"""
    notify = progress or (lambda phase: None)
    settings=settings or {}
    from content import annotate
    from vision import understand
    from extensions import run_hooks
    messages=annotate(messages,settings.get('_session',''))
    from replyscope import resolve_target,target_context
    reply_to=resolve_target(messages[-context:],reply_to)
    partial=None
    callback=settings.get('_on_partial')
    media_pending=any(media_unresolved(m) for m in messages[-context:])
    from content import reply_target
    latest=next((m for m in reversed(target_context(messages[-context:],reply_to)) if reply_target(m)),{})
    route=modelrouter.current()
    enough_budget=not route or route['settings'].get('max_model_calls',6)-route['calls']>=5
    eligible=callback and not settings.get('_preliminary') and settings.get('vision_enabled') and media_pending and enough_budget and not settings.get('enabled_extensions') and latest.get('kind')=='text' and len(latest.get('text',''))>=4 and not re.search(r'这张图|这个视频|图片里|看图|语音|截图|这是什么',latest.get('text',''))
    if eligible:
        preliminary={**settings,'vision_enabled':False,'_preliminary':True};preliminary.pop('_on_partial',None)
        partial=_analyze_impl(messages,relationship,api_key,model,judge_model,timeout,context,reply_to,style,thinking,junshi_layer,memory,notify,preliminary,vision_key,extension_dir)
        partial['media_pending']=True;partial['completion_stage']='text_verified_media_pending'
        partial['warnings']+=['仅文字建议已核验；媒体理解仍在进行，内容未知，尚未完成全部分析']
        modelrouter.check();callback(partial)
        # Draft + integrated review are mandatory. Extra interpretation is
        # optional and must never consume the calls reserved for this pair.
        settings={**settings,'_vision_leave_calls':2}
    recent,vision_warnings=understand(messages[-context:],settings,vision_key,notify)
    reusable=bool(partial and reply_evidence_signature(recent)==reply_evidence_signature(messages[-context:]))
    if reusable:
        from replycheck import usable,grounded
        # A new uncertainty flag can change grounding even when no new facts
        # were obtained. Never skip these independent checks for reused text.
        reusable=bool(partial.get('review_ok') and partial.get('candidates') and all(usable(c) and grounded(c,target_context(recent,reply_to)) for c in partial['candidates']))
    if reusable:
        # The text was reviewed already. A thumbnail or another uncertain
        # observation adds UI evidence, but does not add facts to redraft from.
        partial['understood_messages']=(messages[:-context]+recent)[-30:]
        partial['media_pending']=any(media_unresolved(m) for m in recent)
        partial['warnings']=[w for w in partial['warnings'] if '媒体理解仍在进行' not in w]+vision_warnings+['文字建议已核验；媒体仍未知，本轮未完成媒体理解']
        partial['completion_stage']='text_verified_media_unresolved';return partial
    messages=messages[:-context]+recent
    if modelrouter.current():modelrouter.current()['observations']=[dict(m) for m in messages[-context:]]
    extension_notes,extension_warnings=run_hooks(extension_dir,settings.get('enabled_extensions',[]),messages,{'api_version':'1.0','session':settings.get('_session',''),'relationship':relationship})
    complex_scene=not settings.get('_preliminary') and needs_context_judgment(messages[-context:])
    notify("judging")
    state = build_state(messages, relationship, keep=context, reply_to=reply_to)
    judge = judge_model or model
    answers: dict = {}
    judged = False
    judge_prompt = build_judge_prompt(state, memory)
    system = judge_prompt["system"] + ("\n" + JUDGE_LAYER if junshi_layer else "")
    try:
        if not complex_scene or not calls_available(3):raise LlmError("core drafting and review have priority")
        content = chat(api_key, system, [judge_prompt["user"]], model=judge,
                       temperature=0.3, max_tokens=1200, thinking=False, timeout=timeout)
        answers = parse_judgment(content)
        judged = bool(answers)
        if not judged and calls_available(3):
            # 重试一次，提示只输出 JSON
            content = chat(api_key, system,
                           [judge_prompt["user"], content, "只输出一个 JSON 对象，别的都不要。"],
                           model=judge, temperature=0.2, max_tokens=1200,
                           thinking=False, timeout=timeout)
            answers = parse_judgment(content)
            judged = bool(answers)
    except (LlmError, TimeoutError):
        judged = False  # 退回盲起草

    notify("drafting")
    try:
        candidates = draft_candidates(messages, relationship, api_key, model=model,
                                      timeout=timeout, keep=context, reply_to=reply_to,
                                      style=style, thinking=thinking,
                                      guidance=guidance_text(answers) if judged else None,
                                      junshi_layer=junshi_layer, memory=memory)
    except TimeoutError:
        raise LlmError("预算不足，起草未完成，请稍后重试")
    if not candidates:
        raise LlmError("起草结果没有可用候选回复")

    notify("checking")
    try:
        candidates = review(messages[-context:], candidates, api_key, judge, timeout, relationship=relationship, style=style,**({'reply_to':reply_to} if reply_to else {}))
    except TimeoutError:
        raise LlmError("预算不足，回复核验未完成，请重试")
    integrated_index=getattr(candidates,"best_index",None)
    notify("ranking")
    scores = [0.0, 0.0, 0.0]
    if len(candidates) >= 2 and complex_scene and integrated_index is None and calls_available(1):
        try:
            rp = build_rank_prompt(state, candidates)
            content = chat(api_key, rp["system"], [rp["user"]], model=judge,
                           temperature=0.3, max_tokens=400, thinking=False, timeout=timeout)
            rank = parse_rank(content, candidates)
            if not rank:
                content = chat(api_key, rp["system"],
                               [rp["user"], content, "只输出 JSON 对象。"],
                               model=judge, temperature=0.2, max_tokens=400,
                               thinking=False, timeout=timeout)
                rank = parse_rank(content, candidates)
        except (LlmError, TimeoutError):
            rank = {}
        answers = {**answers, **rank}
        probs = ((answers.get("best_reply") or {}).get("probabilities")) or {}
        for key, idx in _REPLY_IDX.items():
            try:
                scores[idx] = float(probs.get(key, 0.0))
            except (TypeError, ValueError):
                scores[idx] = 0.0

    best_key = (answers.get("best_reply") or {}).get("choice")
    best_index = _REPLY_IDX.get(best_key, 0)
    if best_index >= len(candidates):
        best_index = 0
    if integrated_index is not None:best_index=integrated_index
    rank_ok = integrated_index is not None or bool(best_key in _REPLY_IDX)
    selection_method='integrated_review' if integrated_index is not None else 'model_rank' if rank_ok else 'first_verified' if not complex_scene or len(candidates)==1 else 'unranked'
    if not rank_ok:
        scores = [0.0, 0.0, 0.0]
    best_reason = "事实核验同时选择推荐回复，未单独调用排序模型" if integrated_index is not None else (answers.get("best_reply") or {}).get("reason") or ""

    return {
        "candidates": candidates,
        "understood_messages": messages[-30:],
        "warnings": vision_warnings+extension_warnings,
        "extension_notes": extension_notes,
        "best_index": best_index,
        "best_reply": candidates[best_index],
        "best_reason": best_reason or ("首条候选已核验；普通对话未额外调用排序模型" if selection_method=="first_verified" else "排序未完成，请自行选择" if not rank_ok else ""),
        "rank_ok": rank_ok,
        "selection_method":selection_method,
        "review_ok":True,
        "media_pending":any(media_unresolved(m) for m in messages[-context:]),
        "completion_stage":"media_updated" if partial else "reviewed",
        "scores": scores,
        "answers": answers,
        "usage": _usage_snapshot(),
        "reply_to": reply_to,
    }


def display_judgment(answers: dict) -> list:
    """answers → 面板显示的判断摘要行列表：
    [{label, value, evidence?, danger?}]——每条判断都挂证据，界面直接展示「为什么这么建议」。"""
    from questions import CHOICE_LABELS
    rows = []
    a = answers or {}
    psy = (a.get("psychology") or {}).get("text")
    if psy:
        rows.append({"label": "心理", "value": str(psy),
                     "evidence": (a.get("psychology") or {}).get("evidence")})
    for name, title in (("true_intent", "意图"), ("she_needs", "需要"),
                        ("best_action", "建议动作")):
        one = a.get(name) or {}
        choice = one.get("choice")
        if choice:
            rows.append({"label": title, "value": CHOICE_LABELS[name].get(choice, choice),
                         "evidence": one.get("evidence")})
    dl = a.get("danger_level") or {}
    if isinstance(dl.get("score"), (int, float)) and not isinstance(dl.get("score"), bool):
        rows.append({"label": "危险度", "value": f"{int(round(dl['score']))}/9",
                     "danger": int(round(dl["score"])), "evidence": dl.get("evidence")})
    noul = a.get("literal_question") or {}
    if isinstance(noul.get("noul"), (int, float)):
        rows.append({"label": "字面意思", "value": "是" if noul["noul"] >= 0.5 else "否（有潜台词）",
                     "evidence": noul.get("evidence")})
    return rows


def _analyze_uncached(*args, **kwargs):
    import os
    import time
    settings=kwargs.get('settings') or {}
    import replycache
    home=settings.get('_home') or os.environ.get('DSH_HOME') or os.path.join(os.environ.get('LOCALAPPDATA','.'),'Junshi')
    cancel=settings.get('_cancel')
    if cancel and cancel():raise InterruptedError('旧任务已取消')
    cache_key=replycache.key_for(_analyze_impl,args,kwargs,home)
    cached=replycache.get(cache_key)
    if cached is not None:
        if cancel and cancel():raise InterruptedError('旧任务已取消')
        return cached
    started=time.monotonic();phases=[];last=[started,'start']
    callback=kwargs.get('progress') or (lambda phase:None)
    def progress(phase):
        modelrouter.check();now=time.monotonic()
        phases.append({'phase':last[1],'seconds':round(now-last[0],3)})
        last[:]=[now,phase]
        route=modelrouter.current()
        if route:route['phase']=phase
        callback(phase)
    kwargs['progress']=progress
    with modelrouter.session(settings,settings.get('_home') or os.environ.get('DSH_HOME') or os.path.join(os.environ.get('LOCALAPPDATA','.'),'Junshi'),args[2] if len(args)>2 else kwargs.get('api_key',''),settings.get('_cancel')) as route:
        try:
            result=_analyze_impl(*args,**kwargs)
        except Exception as exc:
            from analysisdiag import safe
            exc.analysis_diagnostics=safe({'draft':route.get('draft_diagnostics',[]),'review':route.get('review_diagnostics',[]),'actual_requests':route['calls'],'phase':route.get('phase','start')})
            raise
        modelrouter.check()
        phases.append({'phase':last[1],'seconds':round(time.monotonic()-last[0],3)})
        result['phase_timings']=phases;result['model_trace']=route['traces']
        result['warnings']+=route['warnings'];result['cost_reserved']=route['cost_reserved']
        result['draft_diagnostics']=route.get('draft_diagnostics',[])
        result['cache_hit']=False
        result['usage']=_usage_snapshot()
        # Newly understood exact crops can now supply a safe cache key for the
        # original observation. Repeated clicks need not redraft this result.
        if cache_key is None:cache_key=replycache.key_for(_analyze_impl,args,kwargs,home)
        replycache.put(cache_key,result)
        return result

def analyze(*args,**kwargs):
    import os,replycache
    settings=dict(kwargs.get('settings') or {});cancel=settings.get('_cancel')
    if cancel and cancel():raise InterruptedError('旧任务已取消')
    home=settings.get('_home') or os.environ.get('DSH_HOME') or os.path.join(os.environ.get('LOCALAPPDATA','.'),'Junshi')
    key=replycache.key_for(_analyze_impl,args,kwargs,home)
    cached=replycache.get(key)
    if cached is not None:
        if cancel and cancel():raise InterruptedError('旧任务已取消')
        return cached
    flightkey=replycache.key_for(_analyze_impl,args,kwargs,home,allow_unresolved=True)
    if flightkey is None:return _analyze_uncached(*args,**kwargs)
    flight,token,leader=replycache.join(flightkey,cancel)
    try:
        if not leader:return replycache.wait(flight,cancel,settings.get('generation_timeout',90))
        run=dict(kwargs);run['settings']={**settings,'_cancel':lambda:replycache.shared_cancel(flight)}
        try:
            result=_analyze_uncached(*args,**run)
            replycache.publish(flightkey,flight,result=result)
        except BaseException as exc:
            replycache.publish(flightkey,flight,error=exc);raise
        if cancel and cancel():raise InterruptedError('旧任务已取消')
        return result
    finally:replycache.leave(flight,token)
