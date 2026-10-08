"""DeepSeek 官网 OpenAI 兼容接口的薄客户端（urllib，无第三方 SDK）。
判断、起草、排序三个阶段共用。key 只从环境变量读，绝不落盘、绝不打进日志。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
MAX_RETRIES = 3


class LlmError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _redact(text: str, api_key: str = "") -> str:
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    for env in ("DEEPSEEK_API_KEY", "LLM_API_KEY", "JEV_API_KEY"):
        key = os.environ.get(env) or ""
        if key:
            text = text.replace(key, "[REDACTED]")
    return text


def _fail(exc: Exception, what: str, api_key: str = ""):
    if isinstance(exc, LlmError):
        raise exc
    status = getattr(exc, "status", None)
    if isinstance(getattr(exc, "code", None), int):
        status = exc.code
    hint = {401: "密钥被拒", 402: "余额不足", 403: "没有权限", 404: "模型或地址不对",
            422: "请求被拒", 429: "被限流", 529: "服务过载"}.get(status, "")
    detail = _redact(str(exc), api_key).strip()[:300]
    head = f"{what} HTTP {status}" if status else f"{what}失败"
    raise LlmError(f"{head}: {hint or detail or type(exc).__name__}", status)


def _direct_chat(api_key, system, turns, model=DEFAULT_MODEL, temperature=1.2,
         max_tokens=400, thinking=False, timeout=30, base=BASE):
    """发一轮对话，返回模型输出的纯文本。turns = [user, assistant, user, ...] 奇数条。"""
    messages = [{"role": "system", "content": system}]
    for i, text in enumerate(turns):
        messages.append({"role": "assistant" if i % 2 else "user", "content": text})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if __import__("urllib.parse", fromlist=["urlparse"]).urlparse(base).hostname == "api.deepseek.com":
        payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
    import modelrouter
    payload=modelrouter.format_payload(payload,base)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = base.rstrip("/") + "/chat/completions"
    last_status = None
    import modelrouter
    attempts=1 if modelrouter.current() else MAX_RETRIES+1
    for attempt in range(attempts):
        modelrouter.check()
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        })
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs):return None
            opener=urllib.request.build_opener(NoRedirect())
            with opener.open(req, timeout=timeout) as resp:
                try:
                    data = json.loads(resp.read().decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise LlmError("模型返回了无法解析的内容")
                if not isinstance(data, dict):
                    raise LlmError("模型返回了异常结构")
                try:
                    choice = (data.get("choices") or [{}])[0]
                    content = choice.get("message", {}).get("content") or ""
                    finished = choice.get("finish_reason")
                except (AttributeError, TypeError, KeyError):
                    raise LlmError("模型返回结构异常")
                if not content or not isinstance(content, str):
                    raise LlmError("模型返回空内容")
                if finished == "length":
                    raise LlmError("模型输出被截断，请重试")
                return content
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            if exc.code in (429, 529, 500, 502, 503) and attempt < attempts-1:
                time.sleep(2 ** attempt)
                continue
            try:
                raw = exc.read().decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            raise LlmError(f"HTTP {exc.code}: {_redact(raw, api_key)[:300]}", exc.code)
        except (TimeoutError, OSError) as exc:
            if attempt < attempts-1:
                time.sleep(2 ** attempt)
                continue
            _fail(exc, "请求", api_key)
    raise LlmError(f"HTTP {last_status}: 重试耗尽", last_status)


def _chat(api_key, system, turns, model=DEFAULT_MODEL, temperature=1.2,
         max_tokens=400, thinking=False, timeout=30, base=BASE):
    import modelrouter
    selected=modelrouter.resolve(model,system)
    route=modelrouter.current()
    if selected:
        model=selected['model'];base=selected['base']
        from securestore import read_json
        from pathlib import Path
        key_path=Path(route['home'])/('model-'+selected['id']+'.dpapi')
        api_key=read_json(key_path).get('key','') if key_path.exists() else ''
        if not api_key and __import__('urllib.parse',fromlist=['urlparse']).urlparse(base).hostname not in ('127.0.0.1','localhost','::1'):raise LlmError('此模型尚未设置密钥')
    if route:
        timeout=min(timeout,max(.5,route['deadline']-time.monotonic()))
        if route['settings'].get('harness_enabled',True) and (__import__('urllib.parse',fromlist=['urlparse']).urlparse(base).hostname=='api.deepseek.com'):
            try:
                from harness_adapter import complete
                return complete(api_key,model,system,turns,route['home'],timeout,route['cancel'],max_tokens,base,observations=route.get('observations',[]))
            except InterruptedError:raise
            except Exception as exc:
                modelrouter.check()
                route['warnings'].append('Harness未完成本阶段，已切换基础接口：'+type(exc).__name__)
                timeout=min(timeout,max(.5,route['deadline']-time.monotonic()))
    from requestgate import slot
    with slot(base,timeout=timeout) as remaining:
        modelrouter.reserve(model,system)
        result=_direct_chat(api_key,system,turns,model,temperature,max_tokens,thinking,min(timeout,remaining),base)
    modelrouter.check()
    return result


def chat(api_key,system,turns,model=DEFAULT_MODEL,temperature=1.2,max_tokens=400,thinking=False,timeout=30,base=BASE):
    return _chat(api_key,system,turns,model,temperature,max_tokens,thinking,timeout,base)
