"""引擎的本地 HTTP 路由分派。

从 `junshi.py` 拆出：原先 `Handler._route` 是一条 320 行的 `if` 长链，
33 个分支全挤在一个方法里，改一处要通读全篇，也不便于单独审阅某个端点。

这里只做「分派 + 每个端点一个具名方法」，业务实现仍全部留在 `junshi.py`
（`state_payload` / `do_fill` / `do_copy` / `do_analyze_text` / `save_config` 等），
因此本模块不改变任何行为，只是把入口收窄、把每个端点变成可单独阅读的函数。

循环导入的处理：`junshi.py` 在模块级 `import apiroutes`，而本模块需要在
运行期访问 `junshi` 的模块级状态（STATE / CONFIG / API_KEY / _lock / DSH_HOME
/ ANALYSIS_GUARD）。因此这里一律通过下面的 `_app()` 惰性取用——只在真正处理
请求时读取属性，不在导入期解引用，`junshi` 尚未定义这些名字时也不会出错。
本模块被当作顶层模块导入（引擎把 engine/ 加进 sys.path）。
"""
import json
import os
import threading
import time
import uuid

_CAPABILITIES = {
    'ok': True,
    'api_version': '1.0',
    'app_version': '1.5.70',
    'tools': ['state', 'participants', 'analyze-text', 'cancel-manual', 'regenerate',
              'settings', 'extensions', 'vision-models', 'fill', 'models', 'evidence',
              'correct-message', 'uia', 'memory-confirm', 'media-file', 'media-job',
              'attach-media', 'verify-extension'],
    'evidence_api_version': '1.1',
    'sends_messages': False,
}


def _app():
    """惰性取用 junshi 模块，避免导入期循环依赖。"""
    import junshi
    return junshi


# ===== 只读端点（GET） =====

def capabilities(handler, app):
    handler._json(dict(_CAPABILITIES))


def models_get(handler, app):
    handler._json({'ok': True, 'models': __import__('modelrouter').catalog(app.DSH_HOME)})


def uia(handler, app):
    snapshot = (__import__('uia_reader').snapshot(app.STATE['wechat'].get('hwnd', 0))
                if app.CONFIG.get('uia_enabled') else {'available': False, 'reason': 'disabled'})
    handler._json({'ok': True, 'snapshot': snapshot})


def participants(handler, app):
    payload = app.state_payload()
    handler._json({'ok': True, 'session': payload['session'], 'participants': payload['participants'],
                   'identity_limit': '仅按屏幕昵称区分；同名不能视为唯一账号'})


def extensions(handler, app):
    from extensions import catalog
    handler._json({'ok': True, 'extensions': catalog(os.path.join(app.DSH_HOME, 'extensions')),
                   'enabled': app.CONFIG.get('enabled_extensions', [])})


def vision_models(handler, app):
    """列出本机 Ollama 的模型，并标记哪些支持 vision。"""
    from vision import validate_base
    from urllib.parse import urlparse
    base = validate_base(app.CONFIG.get('vision_base', ''))
    parsed = urlparse(base)
    if parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('自动发现目前只支持本机 Ollama')
    endpoint = f'{parsed.scheme}://{parsed.netloc}/api/tags'
    opener = __import__('urllib.request', fromlist=['build_opener']).build_opener(
        __import__('urllib.request', fromlist=['ProxyHandler']).ProxyHandler({}))
    with opener.open(endpoint, timeout=5) as response:
        data = json.load(response)
    models = []
    for item in data.get('models', []):
        caps = item.get('capabilities', [])
        if not caps:
            request = __import__('urllib.request', fromlist=['Request']).Request(
                f'{parsed.scheme}://{parsed.netloc}/api/show',
                data=json.dumps({'model': item['name']}).encode(),
                headers={'Content-Type': 'application/json'})
            try:
                with opener.open(request, timeout=5) as response:
                    details = json.load(response)
                caps = details.get('capabilities', [])
            except Exception as exc:
                # Ollama 旧版本没有 /api/show；此处失败只影响 vision 标记的精度，
                # 因此降级为「未知」而不是让整个端点 500。留一条诊断痕迹便于排查。
                app.flog(f'vision-models: /api/show failed for {item.get("name")!r}: {exc!r}')
        models.append({'name': item['name'], 'vision': 'vision' in caps})
    handler._json({'ok': True, 'models': models})


def health(handler, app):
    capture_thread = getattr(handler.server, 'capture_thread', None)
    handler._json({'ok': True, 'pid': os.getpid(), 'status': app.STATE['status'],
                   'heartbeat_age': round(time.time() - app.STATE['heartbeat'], 1),
                   'capture_thread_alive': bool(capture_thread and capture_thread.is_alive())})


def state(handler, app):
    handler._json(app.state_payload())


def frame_png(handler, app):
    with app._lock:
        frame = app.STATE['last_frame']
        captured_at = app.STATE['last_frame_at']
    if frame is None:
        handler._json({'ok': False, 'error': '还没有帧'}, 404)
        return
    try:
        import io
        import numpy as np
        from PIL import Image
        scale = 1 if handler.headers.get('X-Junshi-Frame-Scale') == '1' else 2
        small = frame[::scale, ::scale]
        img = Image.fromarray(np.ascontiguousarray(small))
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        data = buf.getvalue()
        handler.send_response(200)
        handler.send_header('Content-Type', 'image/png')
        handler.send_header('Content-Length', str(len(data)))
        handler.send_header('Cache-Control', 'no-store')
        if captured_at is not None:
            handler.send_header('X-Junshi-Captured-At', str(captured_at))
        handler.end_headers()
        handler.wfile.write(data)
    except Exception as e:
        handler._json({'ok': False, 'error': str(e)}, 500)


def settings_get(handler, app):
    handler._json({'ok': True, 'settings': app.state_payload()['settings']})


def ui(handler, app):
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>军师 · 微信回复</title>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>html,body{margin:0;padding:0;background:#17191d;overflow:hidden}</style>"
        "</head><body>"
        "<script>window.__DSH_JUNSHI_API__='';window.__JUNSHI_STANDALONE__=true</script>"
        "<script src='/ui/panel.js'></script>"
        "</body></html>")
    body = html.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(body)


def panel_js(handler, app):
    js = app._panel_js()
    if js is None:
        handler._json({'ok': False, 'error': 'panel.js 不可用'}, 404)
        return
    body = js.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/javascript; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(body)


# ===== 写入端点（POST） =====

def cancel_manual(handler, app):
    identity = handler._body().get('request_id')
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 80:
        raise ValueError('请求编号无效')
    from manualjobs import jobs
    jobs.cancel(identity)
    handler._json({'ok': True, 'cancellation_requested': True})


def media_file(handler, app):
    """接收上传的媒体文件，后台跑语音转写 + 画面抽样。"""
    body = handler._body()
    with app._lock:
        if any(job['state'] in ('queued', 'running') for job in app.STATE['media_jobs'].values()):
            raise ValueError('已有媒体正在处理')
        identity = uuid.uuid4().hex
        app.STATE['media_jobs'] = {identity: {'id': identity, 'state': 'queued',
                                              'phase': 'speech', 'started': time.time()}}
        settings = dict(app.CONFIG)

    def work():
        job = app.STATE['media_jobs'][identity]
        job['state'] = 'running'
        try:
            from securestore import read_json
            try:
                key = read_json(os.path.join(app.DSH_HOME, 'vision-key.dpapi')).get('key', '')
            except Exception as exc:
                # 视觉密钥是可选项：没配就走纯语音转写路径，不是错误。
                app.flog(f'media-file: no vision key ({exc!r}); continuing speech-only')

            def progress(phase):
                job['phase'] = phase

            job['result'] = __import__('avmedia').analyze_upload(body, settings, key, progress)
            job['state'] = 'done'
        except Exception as exc:
            job['error'] = str(exc)[:200]
            job['state'] = 'error'
        finally:
            job['seconds'] = round(time.time() - job['started'], 2)

    threading.Thread(target=work, daemon=True).start()
    handler._json({'ok': True, 'id': identity})


def media_job(handler, app):
    identity = handler._body().get('id')
    handler._json({'ok': True, 'job': app.STATE['media_jobs'].get(identity, {'state': 'expired'})})


def memory_confirm(handler, app):
    body = handler._body()
    fact = body.get('fact')
    if not isinstance(fact, str) or not 1 <= len(fact.strip()) <= 200:
        raise ValueError('确认事实应为1至200字')
    from memory import load_memory, save_memory
    with app._lock:
        contact = app.STATE['session']
        if body.get('session') != contact:
            raise ValueError('会话已变化')
        memory = load_memory(contact)
        memory.update(source='user_confirmed', updated=time.time())
        memory['facts'] = (memory['facts'] + [fact.strip()])[-30:]
        save_memory(contact, memory)
    handler._json({'ok': True})


def models_post(handler, app):
    from pathlib import Path
    from modelrouter import validate_models
    from modelsettings import is_unchanged
    from securestore import write_json
    body = handler._body()
    rows = validate_models(body.get('models'))
    if is_unchanged(app.DSH_HOME, rows, body.get('keys', {})):
        handler._json({'ok': True, 'models': rows, 'unchanged': True})
        return
    for identity, key in body.get('keys', {}).items():
        if identity not in {r['id'] for r in rows} or not isinstance(key, str) or len(key) > 1000:
            raise ValueError('模型密钥无效')
        write_json(Path(app.DSH_HOME) / ('model-' + identity + '.dpapi'), {'key': key})
    target = Path(app.DSH_HOME) / 'models.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    temp.replace(target)
    with app._lock:
        app.STATE['session_since'] = time.time()
        app.STATE['analysis'] = None
    app.schedule_analysis()
    handler._json({'ok': True, 'models': rows})


def evidence(handler, app):
    body = handler._body()
    key = body.get('crop_id', '')
    if not isinstance(key, str):
        raise ValueError('证据编号无效')
    image = __import__('media').get(key)
    handler._json({'ok': True, 'image': image, 'expired': not bool(image)})


def attach_media(handler, app):
    """把已处理完成的媒体结果挂到某条消息上，再触发重新分析。"""
    body = handler._body()
    with app._lock:
        if body.get('session') != app.STATE['session']:
            raise ValueError('会话已变化，请重新关联')
        target = next((m for m in app.STATE['messages'] if m.get('message_id') == body.get('message_id')), None)
        job = app.STATE['media_jobs'].get(body.get('job_id'))
        if not target or target.get('kind') not in ('media_unknown', 'video', 'audio'):
            raise ValueError('请确认文件属于当前可见媒体消息')
        if not job or job.get('state') != 'done':
            raise ValueError('媒体处理尚未完成或已过期')
        decoded = job['result']
        parts = [decoded['coverage']]
        parts += ['转写 ' + str(s['start']) + '-' + str(s['end']) + '秒：' + s['text']
                  + ('（不确定）' if s['uncertain'] else '') for s in decoded.get('transcript', [])]
        parts += ['抽样画面 ' + str(s['second']) + '秒：' + (s.get('description') or '未知')
                  for s in decoded.get('visual_samples', [])]
        fields = {
            'kind': 'video' if decoded.get('has_video') else 'audio',
            'media_description': '\n'.join(parts)[:4000],
            'media_transcript': decoded.get('transcript', []),
            'content_source': 'user_attached_file',
            'file_evidence': {'sha256': decoded.get('file_sha256'), 'filename': decoded.get('filename'),
                              'coverage': decoded['coverage'], 'job_id': body.get('job_id')},
        }
        corrected = __import__('evidence').store(app.DSH_HOME).attach_media(target['message_id'], fields)
        for collection in (app.STATE['messages'], app.STATE['messages_by_session'].get(app.STATE['session'], [])):
            for index, message in enumerate(collection):
                if message.get('message_id') == corrected['message_id']:
                    collection[index] = corrected
        app.STATE['session_since'] = time.time()
        app.STATE['analysis'] = None
    app.schedule_analysis()
    handler._json({'ok': True, 'message': corrected})


def correct_message(handler, app):
    body = handler._body()
    with app._lock:
        if (body.get('session') != app.STATE['session']
                or not any(m.get('message_id') == body.get('message_id') for m in app.STATE['messages'])):
            raise ValueError('会话已变化或消息已过期')
        corrected = __import__('evidence').store(app.DSH_HOME).correct(body.get('message_id'), body.get('patch'))
        for collection in (app.STATE['messages'], app.STATE['messages_by_session'].get(app.STATE['session'], [])):
            for idx, m in enumerate(collection):
                if m.get('message_id') == corrected['message_id']:
                    collection[idx] = corrected
        app.STATE['analysis'] = None
        app.STATE['session_since'] = time.time()
    app.schedule_analysis()
    handler._json({'ok': True, 'message': corrected})


def verify_extension(handler, app):
    from extensions import verify
    body = handler._body()
    handler._json({'ok': True, 'verification': verify(os.path.join(app.DSH_HOME, 'extensions'),
                                                      body.get('id', ''))})


def vision_key(handler, app):
    from securestore import write_json
    key = handler._body().get('key')
    if not isinstance(key, str) or len(key) > 1000:
        raise ValueError('密钥无效')
    write_json(os.path.join(app.DSH_HOME, 'vision-key.dpapi'), {'key': key})
    handler._json({'ok': True})


def startup(handler, app):
    enabled = handler._body().get('enabled')
    if not isinstance(enabled, bool):
        raise ValueError('开机启动选项无效')
    app.set_startup(enabled)
    handler._json({'ok': True})


def settings_post(handler, app):
    patch = handler._body()
    if not isinstance(patch, dict):
        raise ValueError('设置必须为对象')
    expected = patch.pop('expected_session', None)
    saved = app.save_config(patch, expected_session=expected)
    app.log('设置已更新')
    handler._json({'ok': True, 'settings': app.state_payload()['settings'], **saved})


def fill(handler, app):
    body = handler._body()
    handler._json(app.do_fill(body.get('index', 0), edited_text=body.get('text'),
                              analysis_ts=body.get('analysis_ts')))


def copy_text(handler, app):
    text = handler._body().get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        handler._json({'ok': False, 'error': '回复应为 1 到 2000 字'}, 400)
        return
    from fill import set_clipboard
    set_clipboard(text)
    handler._json({'ok': True})


def copy(handler, app):
    handler._json(app.do_copy(handler._body().get('index', 0)))


def pause(handler, app):
    app.save_config({'paused': True})
    with app._lock:
        app.STATE['session_since'] = time.time()
    app.log('已暂停读取')
    handler._json({'ok': True})


def resume(handler, app):
    if not app.API_KEY:
        handler._json({'ok': False, 'error': '请先保存 API 密钥'}, 400)
        return
    app.save_config({'paused': False})
    app.schedule_analysis()
    app.log('已恢复读取')
    handler._json({'ok': True})


def regenerate(handler, app):
    if not app.API_KEY:
        handler._json({'ok': False, 'error': '请先保存 API 密钥'}, 400)
        return
    with app._lock:
        if app.ANALYSIS_GUARD['in_flight']:
            app.ANALYSIS_GUARD['pending'] = True
            app.ANALYSIS_GUARD['pending_force_fresh'] = True
            handler._json({'ok': True, 'note': '已记住你的偏好，当前分析结束后更新'})
            return
        msgs = [dict(m) for m in app.STATE['messages']]
        cfg = dict(app.CONFIG)
        cfg['_session'] = app.STATE['session']
        cfg['_session_since'] = app.STATE['session_since']
        cfg['_force_fresh'] = True
        if not msgs:
            handler._json({'ok': False, 'error': '还没有识别到消息'})
            return
        app.ANALYSIS_GUARD['in_flight'] = True
    threading.Thread(target=app.run_analysis, args=(msgs, cfg, app.ANALYSIS_GUARD), daemon=True).start()
    handler._json({'ok': True, 'note': '正在重新生成候选'})


def analyze_text(handler, app):
    handler._json(app.do_analyze_text(handler._body()))


def launch_wechat(handler, app):
    handler._json(app.launch_wechat())


def key_delete(handler, app):
    """清除 API 密钥。

    这里给 `app.API_KEY` 赋值等价于原 `_route` 里的 `global API_KEY` —— app 就是
    junshi 模块对象，属性写入落在模块 __dict__ 上，与全局变量是同一份存储。
    """
    app.API_KEY = ''
    os.environ.pop('DEEPSEEK_API_KEY', None)
    try:
        os.remove(os.path.join(app.DSH_HOME, 'api-key.dpapi'))
    except FileNotFoundError:
        pass
    app.save_config({'paused': True})
    with app._lock:
        app.STATE['analysis'] = None
    handler._json({'ok': True})


def key(handler, app):
    body = handler._body()
    value = str(body.get('key') or '').strip()
    if not value:
        handler._json({'ok': False, 'error': '密钥不能为空'}, 400)
        return
    app.API_KEY = value
    os.environ['DEEPSEEK_API_KEY'] = value
    try:
        from securestore import write_json
        write_json(os.path.join(app.DSH_HOME, 'api-key.dpapi'), {'key': value})
    except Exception:
        handler._json({'ok': False, 'error': 'Windows 加密保存失败，请重试'}, 500)
        return
    app.log('密钥已使用 Windows DPAPI 加密保存')
    handler._json({'ok': True, 'saved_secure': True})


def memory_clear(handler, app):
    with app._lock:
        contact = app.STATE['session'] or '当前会话'
        if app.STATE['analysis']:
            app.STATE['analysis']['memory_facts'] = 0
    try:
        from memory import memory_path
        p = memory_path(contact)
        if os.path.isfile(p):
            os.remove(p)
            app.log(f'已清空「{contact}」的军师记忆')
            handler._json({'ok': True, 'note': f'已清空「{contact}」的记忆'})
        else:
            handler._json({'ok': True, 'note': '这个会话还没有记忆'})
    except Exception as e:
        handler._json({'ok': False, 'error': f'清空失败：{e}'})


def shutdown(handler, app):
    handler._json({'ok': True})
    threading.Thread(target=handler.server.shutdown, daemon=True).start()


# ===== 分派表 =====
# (方法, 路径) -> 处理函数。表驱动替代原来的 33 段 if 长链：
# 想查某个端点只需看这一处，新增端点也不会再撑大某个方法。
ROUTES = {
    ('GET', '/capabilities'): capabilities,
    ('GET', '/models'): models_get,
    ('POST', '/models'): models_post,
    ('GET', '/uia'): uia,
    ('POST', '/evidence'): evidence,
    ('POST', '/attach-media'): attach_media,
    ('POST', '/correct-message'): correct_message,
    ('GET', '/participants'): participants,
    ('GET', '/extensions'): extensions,
    ('POST', '/verify-extension'): verify_extension,
    ('GET', '/vision-models'): vision_models,
    ('POST', '/vision-key'): vision_key,
    ('GET', '/health'): health,
    ('GET', '/state'): state,
    ('GET', '/frame.png'): frame_png,
    ('GET', '/settings'): settings_get,
    ('POST', '/settings'): settings_post,
    ('POST', '/startup'): startup,
    ('POST', '/fill'): fill,
    ('POST', '/copy-text'): copy_text,
    ('POST', '/copy'): copy,
    ('POST', '/pause'): pause,
    ('POST', '/resume'): resume,
    ('POST', '/regenerate'): regenerate,
    ('POST', '/analyze-text'): analyze_text,
    ('POST', '/launch-wechat'): launch_wechat,
    ('POST', '/key-delete'): key_delete,
    ('POST', '/key'): key,
    ('POST', '/memory-clear'): memory_clear,
    ('POST', '/memory-confirm'): memory_confirm,
    ('POST', '/cancel-manual'): cancel_manual,
    ('POST', '/media-file'): media_file,
    ('POST', '/media-job'): media_job,
    ('GET', '/ui'): ui,
    ('GET', '/ui/panel.js'): panel_js,
    ('POST', '/shutdown'): shutdown,
}


def route(handler):
    """分派一次请求。语义与原 `Handler._route` 完全一致。"""
    app = _app()
    from urllib.parse import urlparse
    path = urlparse(handler.path).path
    if not handler._check():
        handler._json({'ok': False, 'error': 'unauthorized'}, 401)
        return
    handler_route = ROUTES.get((handler.command, path))
    if handler_route is None:
        handler._json({'ok': False, 'error': 'not found'}, 404)
        return
    handler_route(handler, app)
