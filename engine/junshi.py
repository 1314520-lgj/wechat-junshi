from advicefresh import advice_fresh,ADVICE_TTL_SECONDS
# -*- coding: utf-8 -*-
"""军师引擎主进程：微信窗口采集 → 黄色边框 → OCR → Jev 判断 → 起草 → 排序 → HTTP API。

全程内存，不落任何截图。API key 只从环境变量 DEEPSEEK_API_KEY 读。
"""
import ctypes
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse as up
import urllib.request
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.makedirs(os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh"), exist_ok=True)

# ===== 最早启动：把 stdout/stderr 重定向到文件 =====
# 宿主（DeepSeek Harness 桌面壳）是无控制台的 GUI 进程，子进程继承到的 std 句柄
# 可能是坏句柄/满管道：任何 stderr 写入都可能永久阻塞（实测引擎卡死在 import 阶段）。
# 这里在一切重导入之前就换成真实文件句柄。
_LOG_FILE = os.path.join(os.environ.get("DSH_HOME") or
                         os.path.join(os.path.expanduser("~"), ".dsh"), ".dsh-junshi-engine.log")
try:
    _log_fd = os.open(_LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.dup2(_log_fd, 1)
    os.dup2(_log_fd, 2)
except Exception:
    _log_fd = None
if _log_fd:
    sys.stdout = io.TextIOWrapper(os.fdopen(_log_fd, "ab", buffering=0),
                                  encoding="utf-8", errors="replace")
    sys.stderr = sys.stdout
elif sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stderr

# 宿主进程可能注入自己的 PYTHONPATH/PYTHONHOME，与引擎 vendor 目录冲突：一律清掉
for _var in ("PYTHONPATH", "PYTHONHOME"):
    os.environ.pop(_var, None)

import numpy as np

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(ENGINE_DIR,"..","media-runtime"))
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, os.path.join(ENGINE_DIR, "vendor"))


def _panel_js():
    """独立面板脚本：开发树里从 lib/panel.js 读；PyInstaller 里从 _MEIPASS/lib 读。"""
    cands = []
    try:
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            cands.append(os.path.join(meipass, "lib", "panel.js"))
    except Exception:
        pass
    cands.append(os.path.normpath(os.path.join(ENGINE_DIR, "..", "lib", "panel.js")))
    for p in cands:
        try:
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
    return None


def _trace(msg):
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


_trace(f"start pid={os.getpid()} cwd={os.getcwd()} py={sys.version.split()[0]}")
_trace("importing border/capture/engine/ocr...")
import content  # noqa: E402
from border import YellowBorder  # noqa: E402
_trace("border ok")
from capture import (Capture, PrintCapture, chat_area, find_chat_hwnd,  # noqa: E402
                     unminimize, window_rect, make_capture)
_trace("capture ok")
from engine import analyze, display_judgment  # noqa: E402
_trace("engine ok")
from fill import fill as fill_into  # noqa: E402
_trace("fill ok")
from ocr import Reader, read_title, similar  # noqa: E402
_trace("ocr(rapidocr) ok")

DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
CONFIG_PATH = os.environ.get("DSH_JUNSHI_CONFIG") or os.path.join(DSH_HOME, ".dsh-junshi.json")
LOG_PATH = os.path.join(DSH_HOME, ".dsh-junshi.log")


def flog(msg):
    """启动期文件日志（stdout 在宿主里不可见，靠它排查启动问题）。"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

DEFAULT_CONFIG = {
    "relationship": "恋人",
    "style": "",
    "context": 10,
    "reply_target": False,
    "reply_target_name": "",
    "junshi_layer": True,
    "model": "deepseek-flash",
    "judge_model": "deepseek-chat",
    "wechat_path": r"D:\Weixin\Weixin.exe",
    "auto_launch": False,
    "paused": True,
    "vision_enabled": False,
    "vision_keep_alive_minutes": 5,
    "vision_base": "http://127.0.0.1:11434/v1",
    "vision_model": "",
    "enabled_extensions": [],
    "harness_enabled": True,
    "generation_timeout": 120,
    "max_model_calls": 6,
    "max_cloud_requests": 1,
    "max_analysis_cost": 1.0,
    "uia_enabled": True,
}

_lock = threading.RLock()
CONFIG = dict(DEFAULT_CONFIG)
LOG = deque(maxlen=200)
STATE = {
    "status": "starting",
    "heartbeat": time.time(),
    "capture_backend": None,
    "ocr_ms": 0,
    "ocr_metrics": {},
    "layout_metrics": {},
    "uia_snapshot": {},
    "title_ready": False,
    "recognition_phase": "waiting",
    "analysis_phase": "idle",
    "analysis_started": 0,
    "manual_phase": "idle",
    "manual_phase_request": None,
    "manual_preview": None,
    "media_jobs": {},
    "session": "",
    "session_since": 0,
    "messages": [],               # 当前会话的消息（切会话自动切换）
    "messages_by_session": {},    # {会话名: [消息, ...]}，每个会话独立累积，防串味
    "analysis": None,
    "analysis_error": None,
    "analysis_inflight": False,
    "wechat": {"running": False, "visible": False, "hwnd": 0, "rect": None},
    "border": False,
    "last_frame": None,          # numpy（调试视图用）
    "last_frame_at": None,
    "last_area": None,
    "fill": None,
    "launch_wait": False,
}

_token = os.environ.get("DSH_JUNSHI_TOKEN") or secrets.token_urlsafe(32)
API_KEY = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()

if not API_KEY:
    try:
        from securestore import read_json
        API_KEY = str(read_json(os.path.join(DSH_HOME, "api-key.dpapi")).get("key") or "")
    except Exception:
        pass

if not API_KEY and not os.environ.get("JUNSHI_STANDALONE"):
    # 回退：直接读 DSH 官方凭据文件（与 ctx.credentials.resolve('DEEPSEEK_API_KEY') 同源）。
    # 只在内存里用，绝不打印、绝不落盘。
    try:
        _cred_path = os.path.join(DSH_HOME, ".credentials.yaml")
        with open(_cred_path, encoding="utf-8") as _f:
            for _line in _f:
                _m = re.match(r"^\s*DEEPSEEK_API_KEY\s*:\s*['\"]?([^'\"]+?)['\"]?\s*$", _line)
                if _m:
                    API_KEY = _m.group(1).strip()
                    break
    except Exception:
        pass


def log(msg):
    with _lock:
        LOG.append({"t": time.strftime("%H:%M:%S"), "msg": str(msg)[:300]})


def load_config():
    global CONFIG
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if data.get('enabled_extensions'):
                from extensions import catalog
                approved={x['id'] for x in catalog(os.path.join(DSH_HOME,'extensions')) if x['verified']}
                data['enabled_extensions']=[x for x in data['enabled_extensions'] if x in approved]
            with _lock:
                for k, v in validate_settings(data).items():
                    CONFIG[k] = v
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"配置读取失败：{e}")


def validate_settings(patch):
    if not isinstance(patch, dict):
        raise ValueError("设置必须为对象")
    result = {}
    for key, value in patch.items():
        if key not in DEFAULT_CONFIG:
            continue
        if key in ('generation_timeout','max_model_calls','max_cloud_requests','max_analysis_cost'):
            limits={'generation_timeout':(15,180),'max_model_calls':(1,12),'max_cloud_requests':(1,4),'max_analysis_cost':(0,10)}
            lo,hi=limits[key]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not lo<=value<=hi or (key!='max_analysis_cost' and not isinstance(value,int)):raise ValueError('预算设置无效')
            result[key]=value;continue
        if key == 'vision_keep_alive_minutes':
            from vision import keep_alive_value
            keep_alive_value(value);result[key]=value;continue
        if key == 'enabled_extensions':
            import re
            if not isinstance(value,list) or len(value)>20 or any(not isinstance(v,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',v) for v in value):raise ValueError('扩展列表无效')
            from extensions import catalog
            trusted={x['id'] for x in catalog(os.path.join(DSH_HOME,'extensions')) if x['verified']}
            if set(value)-trusted:raise ValueError('扩展尚未通过验证或代码已变更，请先验证')
            result[key]=value;continue
        if key == 'vision_base':
            from vision import validate_base
            value=validate_base(value)
        if key == "context":
            if isinstance(value, bool) or not isinstance(value, int) or not 3 <= value <= 30:
                raise ValueError("上下文必须为 3 到 30 的整数")
        elif isinstance(DEFAULT_CONFIG[key], bool):
            if not isinstance(value, bool):
                raise ValueError("开关设置必须为布尔值")
        elif not isinstance(value, str) or len(value) > 1000:
            raise ValueError("设置文字无效")
        if key in ("model", "judge_model") and not value.strip():
            raise ValueError("模型名不能为空")
        result[key] = value
    return result


def startup_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _ = winreg.QueryValueEx(key, "Junshi")
        return "Junshi.exe" in value
    except Exception:
        return False

def set_startup(enabled):
    import winreg
    executable = os.path.normpath(os.path.join(ENGINE_DIR, "..", "Junshi.exe"))
    if not os.path.isfile(executable):
        raise ValueError("仅安装版支持开机启动")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "Junshi", 0, winreg.REG_SZ, '"' + executable + '" --background')
        else:
            try:
                winreg.DeleteValue(key, "Junshi")
            except FileNotFoundError:
                pass


def contact_preferences_path(name):
    import hashlib
    return os.path.join(DSH_HOME, "contact-preferences", hashlib.sha256(name.encode("utf-8")).hexdigest() + ".dpapi")

def restore_contact_preferences(name):
    from securestore import read_json
    try:
        saved = validate_settings(read_json(contact_preferences_path(name)))
    except Exception:
        saved = {"relationship": "朋友", "style": ""}
    with _lock:
        for key in ("relationship", "style"):
            if key in saved:
                CONFIG[key] = saved[key]


def save_config(patch=None,expected_session=None):
    changed=set();contact_saved=True
    with _lock:
        if expected_session is not None and (not isinstance(expected_session,str) or STATE["session"]!=expected_session):
            raise ValueError("会话已经切换，请在当前联系人下重新选择偏好")
        data=dict(CONFIG)
        if patch:
            for key,value in validate_settings(patch).items():
                if key in DEFAULT_CONFIG and value is not None:
                    if data.get(key)!=value:changed.add(key)
                    data[key]=value
        # Serialize disk and memory together: never report a failed write as saved.
        temp=CONFIG_PATH+".tmp"
        try:
            with open(temp,"w",encoding="utf-8") as handle:
                json.dump(data,handle,ensure_ascii=False,indent=2)
            os.replace(temp,CONFIG_PATH)
        except Exception as error:
            try:os.remove(temp)
            except OSError:pass
            raise RuntimeError("设置没有保存成功，请检查磁盘空间或文件权限后重试") from error
        CONFIG.update(data)
        analysis_keys={'model','judge_model','harness_enabled','generation_timeout','max_model_calls','max_cloud_requests','max_analysis_cost','vision_enabled','vision_model','vision_base','enabled_extensions','context','junshi_layer','reply_target','reply_target_name','relationship','style'}
        regenerate=bool(analysis_keys.intersection(changed))
        if regenerate:
            STATE['session_since']=time.time();STATE['analysis']=None
        if changed.intersection({"relationship","style"}) and STATE["session"]:
            STATE["session_since"]=time.time()
            try:
                from securestore import write_json
                write_json(contact_preferences_path(STATE["session"]),{"relationship":CONFIG["relationship"],"style":CONFIG["style"]})
            except Exception:
                contact_saved=False
                log("本次偏好已生效，但联系人偏好保存失败")
    if regenerate:schedule_analysis()
    return {"contact_preferences_saved":contact_saved}


# ---------- 采集循环（主线程） ----------

ANALYSIS_GUARD = {"in_flight": False, "pending": False}


def schedule_analysis(force_fresh=False):
    """有新消息就触发（分析在独立线程跑，不堵采集）。
    正在分析时标记 pending，结束后自动对最新消息重跑，保证不落后于连发消息。"""
    with _lock:
        if not API_KEY or CONFIG.get("paused"):
            return
        if ANALYSIS_GUARD["in_flight"]:
            ANALYSIS_GUARD["pending"] = True
            if force_fresh:ANALYSIS_GUARD["pending_force_fresh"] = True
            return
        msgs = [dict(m) for m in STATE["messages"]]
        if not msgs or (not force_fresh and not content.reply_target(msgs[-1])):
            return
        cfg = dict(CONFIG)
        cfg["_session"] = STATE["session"]
        cfg["_session_since"] = STATE["session_since"]
        if force_fresh:cfg["_force_fresh"] = True
        ANALYSIS_GUARD["in_flight"] = True
        ANALYSIS_GUARD["pending"] = False
    threading.Thread(target=run_analysis, args=(msgs, cfg, ANALYSIS_GUARD), daemon=True).start()


def _hide_border(border_box):
    b = border_box.get("b")
    if b:
        try:
            b.hide()
        except Exception:
            pass


def capture_loop(border_box, stop):
    cap = None
    cap_hwnd = 0
    readers = {}
    title = ""
    head = None
    last_launch = 0.0
    warned = False
    ticks = 0
    last_hb = 0.0

    def border():
        """黄框窗口必须在采集线程里创建：SetWindowPos/ShowWindow 与窗口同线程才不会
        跨线程 SendMessage 死锁（主线程只跑 HTTP，不泵消息）。"""
        b = border_box.get("b")
        if b is None:
            try:
                b = YellowBorder("军师 · 正在读取")
                border_box["b"] = b
            except Exception as e:
                log(f"黄框创建失败：{' '.join(str(e).split())[:100]}")
                border_box["b"] = False
                return False
        return b

    def set_status(s):
        with _lock:
            STATE["status"] = s

    while not stop.is_set():
        with _lock:
            STATE["heartbeat"] = time.time()
        ticks += 1
        now = time.time()
        if now - last_hb > 5:
            last_hb = now
            print(f"[junshi hb] ticks={ticks} status={STATE['status']} hwnd={STATE['wechat']['hwnd']}",
                  flush=True)
        try:
            with _lock:
                cfg = dict(CONFIG)
            if cfg["paused"]:
                if cap is not None:
                    cap.stop()
                    cap = None
                _hide_border(border_box)
                with _lock:
                    STATE["border"] = False
                    __import__('viewstate').invalidate(STATE,'paused')
                head=None
                set_status("paused")
                time.sleep(0.4)
                continue

            hwnd, app = find_chat_hwnd()
            with _lock:
                STATE["wechat"]["running"] = bool(hwnd)
                STATE["wechat"]["visible"] = bool(hwnd)
            if not hwnd:
                with _lock:__import__('viewstate').invalidate(STATE,'no-window')
                head=None
                if cap is not None:
                    cap.stop()
                    cap = None
                _hide_border(border_box)
                with _lock:
                    STATE["border"] = False
                    STATE["wechat"]["hwnd"] = 0
                    STATE["wechat"]["rect"] = None
                set_status("no-window")
                now = time.time()
                if cfg["auto_launch"] and now - last_launch > 20:
                    last_launch = now
                    launch_wechat()
                time.sleep(0.8)
                continue
            with _lock:
                STATE["wechat"]["hwnd"] = int(hwnd)
            if ctypes.windll.user32.IsIconic(hwnd):
                with _lock:__import__('viewstate').invalidate(STATE,'minimized')
                head=None
                if cap is not None:
                    cap.stop();cap=None
                _hide_border(border_box)
                with _lock:
                    STATE['border']=False
                    STATE['title_ready']=False
                    STATE['recognition_phase']='waiting'
                set_status('minimized')
                time.sleep(.8)
                continue
            if cap is None or cap_hwnd != hwnd:
                # 换窗口/换会话对象时重建采集
                if cap is not None:
                    try:
                        cap.stop()
                    except Exception:
                        pass
                cap_hwnd = hwnd
                try:
                    try:
                        cap = Capture(hwnd)
                        backend = "wgc"
                    except Exception as e:
                        log(f"WGC 不可用（{' '.join(str(e).split())[:100]}），退回 PrintWindow")
                        cap, _ = make_capture(hwnd)
                        backend = "printwindow"
                    with _lock:
                        STATE["capture_backend"] = backend
                    log(f"采集已启动（{backend}）")
                except Exception as e:
                    with _lock:__import__('viewstate').invalidate(STATE,'capture-failed')
                    head=None
                    set_status("no-window")
                    log(f"采集启动失败：{' '.join(str(e).split())[:120]}")
                    time.sleep(2)
                    continue
            if not cap.alive():
                with _lock:__import__('viewstate').invalidate(STATE,'capture-ended')
                head=None
                cap.stop()
                cap = None
                time.sleep(0.5)
                continue

            rect = window_rect(hwnd)
            with _lock:
                STATE["wechat"]["rect"] = list(rect)
            b = border()
            try:
                if b:
                    b.update_rect(rect)
                    b.show()
                    with _lock:
                        STATE["border"] = True
            except Exception as e:
                log(f"黄框失败：{' '.join(str(e).split())[:100]}")
                with _lock:
                    STATE["border"] = False
            set_status('capturing' if STATE['title_ready'] and STATE['last_area'] else 'locating')

            with _lock:
                recover = (STATE["title_ready"] and not STATE["analysis"]
                           and not STATE["analysis_error"] and not ANALYSIS_GUARD["in_flight"]
                           and any(content.reply_target(m) for m in STATE["messages"]))
            if recover:
                schedule_analysis()

            with _lock: STATE["recognition_phase"] = "waiting-frame"
            full = cap.settled()
            if full is None:
                time.sleep(0.05)
                continue
            with _lock:
                STATE["last_frame"] = full
                STATE["last_frame_at"] = cap.last_settled_at
            area,layout_metrics = __import__('layout').validated_area(full)
            with _lock:STATE['layout_metrics']=layout_metrics
            if area is None:
                cap.area=None
                with _lock:
                    __import__('viewstate').invalidate(STATE,'no-area')
                    STATE['recognition_phase']='locating'
                head=None
                set_status('no-area')
                if not warned:
                    log("消息区认不出来（窗口太小？）")
                    warned = True
                time.sleep(0.05)
                continue
            warned = False
            cap.area = area
            with _lock:
                STATE["last_area"] = [int(v) for v in area[:4]]
            x0, y0, x1, y1, bg, y_pane = area
            crop = full[y_pane:y0, x0:x1]
            if head is None or not np.array_equal(crop, head):
                head = crop
                try:
                    name = read_title(crop, app)
                except Exception:
                    name = ""
                name = name.strip() if name else ""
                if not name:
                    head = None
                    with _lock:
                        __import__('viewstate').invalidate(STATE,'no-title')
                    cap.request_recheck(2)
                    time.sleep(0.3)
                    continue
                with _lock:
                    STATE["title_ready"] = True
                    STATE.pop("_view_invalid_reason",None)
                if name != title:
                    title = name
                    with _lock:
                        restore_contact_preferences(title)
                        STATE["session"] = title
                        STATE["session_since"] = time.time()
                        # 切换会话：旧候选作废（防填错会话），消息切换为该会话自己的缓存
                        old = STATE["analysis"]
                        if old and old.get("session") != title:
                            log(f"已切换到「{title}」，上一个会话的候选已作废")
                        STATE["analysis"] = None
                        STATE["analysis_error"] = None
                        STATE["messages"] = [dict(m) for m in
                                             STATE["messages_by_session"].get(title, [])]
                    log(f"当前会话：{title}")
                    # 新会话里如果有对方消息，直接为该会话生成候选
                    with _lock:
                        has_her = any(content.reply_target(m) for m in STATE["messages"])
                    if has_her:
                        schedule_analysis()

            if title not in readers:
                readers[title] = Reader(app)
            reader = readers[title]
            try:
                with _lock: STATE["recognition_phase"] = "recognizing"
                lines = reader.read(full[y0:y1, x0:x1], bg)
                with _lock:
                    STATE["ocr_ms"] = int(reader.last_ms)
                    STATE["ocr_metrics"] = dict(reader.last_metrics)
                    STATE["recognition_phase"] = "ready"
                new = reader.new_lines(lines)
                if CONFIG.get('uia_enabled'):
                    STATE['uia_snapshot']=__import__('uia_reader').snapshot(hwnd)
                # Recover after an unreadable title or a discarded generation:
                # unchanged messages must not leave the panel blank forever.
                with _lock:
                    recover = (STATE["title_ready"] and not STATE["analysis"]
                               and not STATE["analysis_error"] and not ANALYSIS_GUARD["in_flight"]
                               and any(content.reply_target(m) for m in STATE["messages"]))
                if recover and not new:
                    schedule_analysis()
                if new:
                    with _lock:
                        for message_index,(w, n, t, tm, k) in enumerate(new):
                            msg = {"from": w, "text": t, "name": n if w == "her" else None,
                                   "time": tm, "kind": k}
                            from content import annotate
                            media_id=reader.new_media_ids[message_index]
                            if media_id:msg['media_id']=media_id
                            msg=__import__('evidence').store(DSH_HOME).observe(msg,title,reader.new_evidence[message_index])
                            STATE["messages"].append(msg)
                            bucket = STATE["messages_by_session"].setdefault(title, [])
                            bucket.append(msg)
                            del STATE["messages"][:-500]
                            del bucket[:-500]
                    for w, n, t, tm, k in new:
                        who = "我" if w == "me" else ("对方" if not n else n)
                        tstr = f" {tm}" if tm else ""
                        body = f"[表情包：{t}]" if k == "sticker" else t
                        log(f"{who}{tstr}: {body}")
                    if any(content.reply_target({'from':w,'kind':k}) for w, _, _, _, k in new):
                        schedule_analysis()
            except Exception as e:
                log(f"OCR 出错：{' '.join(str(e).split())[:120]}")
        except Exception:
            log(" ".join(traceback.format_exc().split())[-200:])
        time.sleep(0.25)

    if cap is not None:
        try:
            cap.stop()
        except Exception:
            pass
    set_status("stopped")


def flash_dsh_window():
    """新候选就绪时闪烁 DeepSeek Harness 的任务栏窗口：
    用户多半正在微信里，闪烁提醒「军师有建议了，回来看」。"""
    try:
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p),
                        ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint),
                        ("dwTimeout", ctypes.c_uint)]
        u32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, _):
            if not u32.IsWindowVisible(hwnd):
                return True
            n = u32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            if "DeepSeek Harness" in buf.value:
                found.append(hwnd)
            return True

        u32.EnumWindows(cb, 0)
        for hwnd in found:
            fi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x00000003 | 0x0000000C, 4, 0)
            u32.FlashWindowEx(ctypes.byref(fi))
    except Exception:
        pass


# ---------- 全局热键：微信里 Ctrl+Alt+F 循环填入候选（不离开微信） ----------

HOTKEY_ID = 0xBEEF
HOTKEY_CYCLE = {"index": -1}


def _hotkey_fill():
    """热键触发：第一次按填入推荐候选，再按切换下一条，直接在微信输入框里换。"""
    with _lock:
        analysis = STATE["analysis"] or {}
        cands = analysis.get("candidates") or []
        if not cands:
            return
        best = int(analysis.get("best_index") or 0)
        idx = best if HOTKEY_CYCLE["index"] < 0 else (HOTKEY_CYCLE["index"] + 1) % len(cands)
    reply = do_fill(idx)
    if not reply.get("ok"):
        log("热键拒绝填入：" + reply.get("error", "校验失败"))


def hotkey_loop(stop):
    """独立线程：RegisterHotKey + 消息循环，绝不影响采集主循环。"""
    try:
        import ctypes.wintypes as w
        u32 = ctypes.windll.user32
        # MOD_CONTROL(2) | MOD_ALT(1) | MOD_NOREPEAT(0x4000)；VK 'F' = 0x46
        if not u32.RegisterHotKey(None, HOTKEY_ID, 2 | 1 | 0x4000, 0x46):
            log("热键 Ctrl+Alt+F 注册失败（可能被其他程序占用）")
            return
        log("全局热键就绪：微信里按 Ctrl+Alt+F 循环填入候选")
        msg = w.MSG()
        while not stop.is_set():
            if u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
                if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:  # WM_HOTKEY
                    _hotkey_fill()
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.05)
        try:
            u32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            pass
    except Exception as e:
        log(f"热键线程异常：{' '.join(str(e).split())[:100]}")


def message_signature(messages,visual_only=False):
    import hashlib
    fields=('from','name','text','time','kind','media_id') if visual_only else ('from','name','text','time','kind','media_id','speaker_id')
    rows=[tuple(m.get(k) for k in fields) for m in messages]
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()


def run_analysis(msgs, cfg, guard):
    with _lock:
        STATE["analysis"] = None
        STATE["analysis_error"] = None
        STATE["analysis_diagnostics"] = None
        STATE["analysis_inflight"] = True
    t0 = time.time()
    cfg=dict(cfg);cfg['_home']=DSH_HOME
    original_signature=message_signature(msgs)
    def cancelled():
        with _lock:return not STATE['title_ready'] or STATE['session']!=cfg.get('_session') or STATE['session_since']!=cfg.get('_session_since') or CONFIG.get('paused') or message_signature(STATE['messages'])!=original_signature or any(CONFIG.get(k)!=cfg.get(k) for k in ('model','judge_model','harness_enabled','style','relationship','vision_enabled','vision_model'))
    cfg['_cancel']=cancelled
    with _lock: STATE["analysis_started"] = t0
    def progress(phase):
        with _lock: STATE["analysis_phase"] = phase
    contact = ""
    with _lock:
        contact = cfg.get("_session") or STATE["session"] or "当前会话"
    mem = None
    if cfg.get("junshi_layer"):
        from memory import load_memory
        mem = load_memory(contact)
    try:
        from securestore import read_json
        try:vision_key=read_json(os.path.join(DSH_HOME,'vision-key.dpapi')).get('key','')
        except Exception:vision_key=''
        reply_to = cfg["reply_target_name"] if cfg["reply_target"] else None
        def preview(result):
            if cancelled():return
            with _lock:
                if cancelled():return
                STATE['analysis']={**result,'ts':t0-.001,'took':round(time.time()-t0,2),'session':contact,'source_signature':original_signature,'source_tail':[dict(m) for m in msgs[-3:]],'latest_position_verified':False,'context_scope':'observed_messages_latest_position_unverified','judgment':display_judgment(result.get('answers',{}))}
        cfg['_on_partial']=preview
        result = analyze(
            msgs, cfg["relationship"], API_KEY, model=cfg["model"],
            judge_model=cfg.get("judge_model") or cfg["model"],
            timeout=40, context=cfg["context"], reply_to=reply_to, style=cfg["style"],
            junshi_layer=cfg["junshi_layer"], memory=mem, progress=progress, settings=cfg, vision_key=vision_key, extension_dir=os.path.join(DSH_HOME,'extensions'))
        with _lock:
            if cancelled():
                return
            STATE["analysis"] = {
                "ts": t0,
                "took": round(time.time() - t0, 1),
                "session": contact,
                "source_signature": message_signature(msgs),
                "source_tail": [dict(m) for m in msgs[-3:]],
                "context_scope": "observed_messages_latest_position_unverified",
                "latest_position_verified": False,
                "media_pending":bool(result.get("media_pending")),
                "completion_stage":result.get("completion_stage"),
                "candidates": result["candidates"],
                "scores": [round(float(s), 4) for s in result["scores"]],
                "best_index": int(result["best_index"]),
                "rank_ok": bool(result.get("rank_ok")),
                "selection_method":result.get('selection_method'),
                "review_ok":bool(result.get('review_ok')),
                "best_reason": result.get("best_reason") or "",
                "judgment": display_judgment(result["answers"]),
                "model": cfg["model"],
                "judge_model": cfg.get("judge_model") or cfg["model"],
                "memory_facts": len((mem or {}).get("facts") or []),
                "understood_messages": result.get('understood_messages',[]),
                "warnings": result.get('warnings',[]),
                "extension_notes": result.get('extension_notes',[]),
                'cache_hit':bool(result.get('cache_hit')),
                'cache_age_seconds':result.get('cache_age_seconds'),
                'phase_timings':result.get('phase_timings',[]),
                'model_trace':result.get('model_trace',[]),
                'draft_diagnostics':result.get('draft_diagnostics',[]),
                'usage':dict(result.get('usage') or {}),
            }
        log(f"候选已生成（{len(result['candidates'])} 条，{round(time.time() - t0, 1)}s）")
        HOTKEY_CYCLE["index"] = -1  # 新候选：热键从推荐条重新开始
        # 提醒用户回来看建议：任务栏闪烁 DSH 窗口
        threading.Thread(target=flash_dsh_window, daemon=True).start()
        # 后台更新长期记忆（不阻塞回复流程；失败静默）
        if False:  # model hypotheses must never become confirmed memory
            def _remember():
                try:
                    from memory import extract
                    got = extract(contact, msgs, API_KEY, cfg["model"], timeout=30)
                    with _lock:
                        if got and STATE["analysis"] and STATE["analysis"].get("session") == contact:
                            STATE["analysis"]["memory_facts"] = len(got.get("facts") or [])
                except Exception:
                    pass
            threading.Thread(target=_remember, daemon=True).start()
    except InterruptedError:
        pass
    except Exception as e:
        error = " ".join(str(e).split())[:200]
        with _lock:
            if not cancelled():
                STATE["analysis_error"] = error
                STATE["analysis_diagnostics"] = __import__('analysisdiag').safe(getattr(e,"analysis_diagnostics",None))
        log(f"分析失败：{error}")
    finally:
        with _lock:
            STATE["analysis_inflight"] = False
            STATE["analysis_phase"] = "idle"
            pending_force = guard.pop("pending_force_fresh",False)
            pending = guard["pending"]
            guard["pending"] = False
            guard["in_flight"] = False
        if pending:
            # 分析期间又来了新消息：对最新消息重跑，不落后
            schedule_analysis(force_fresh=pending_force)







def launch_wechat():
    """打开微信：已在运行就激活，否则启动进程并等窗口出现。"""
    with _lock:
        cfg = dict(CONFIG)
    hwnd, _ = find_chat_hwnd()
    if hwnd:
        log("微信窗口已在运行")
        return {"ok": True, "already": True}
    path = cfg.get("wechat_path") or ""
    if not path or not os.path.isfile(path):
        # 再找几个常见位置
        for cand in (r"D:\Weixin\Weixin.exe",
                     os.path.expandvars(r"%ProgramFiles%\Tencent\Weixin\Weixin.exe"),
                     os.path.expandvars(r"%ProgramFiles%\Tencent\WeChat\WeChat.exe"),
                     os.path.expandvars(r"%ProgramFiles(x86)%\Tencent\WeChat\WeChat.exe")):
            if os.path.isfile(cand):
                path = cand
                break
    if not path or not os.path.isfile(path):
        log(f"找不到微信程序：{path or '未配置'}")
        return {"ok": False, "error": f"找不到微信程序：{path or '未配置'}"}
    try:
        subprocess.Popen([path], cwd=os.path.dirname(path))
        log("正在打开微信…")
    except Exception as e:
        log(f"打开微信失败：{e}")
        return {"ok": False, "error": f"打开微信失败：{e}"}
    with _lock:
        STATE["launch_wait"] = True
    threading.Thread(target=_wait_wechat, daemon=True).start()
    return {"ok": True, "already": False}


def _wait_wechat():
    for _ in range(80):
        hwnd, _ = find_chat_hwnd()
        if hwnd:
            log("微信窗口已出现")
            with _lock:
                STATE["launch_wait"] = False
            return
        time.sleep(0.5)
    with _lock:
        STATE["launch_wait"] = False
    log("等待微信窗口超时（也许需要扫码登录）")


# ---------- HTTP API ----------

def state_payload():
    with _lock:
        analysis = STATE["analysis"]
        payload = {
            "ok": True,
            "ts": time.time(),
            "engine": {
                "pid": os.getpid(),
                "status": STATE["status"],
                "capture_backend": STATE["capture_backend"],
                "frame_captured_at":STATE["last_frame_at"],
                "frame_age_seconds":round(max(0,time.time()-STATE["last_frame_at"]),1) if STATE["last_frame_at"] else None,
                "native_capture_jobs":__import__('capturejobs').snapshot(),
                "uia":STATE["uia_snapshot"],
                "ocr_ms": STATE["ocr_ms"],
                "ocr_metrics": dict(STATE["ocr_metrics"]),
                "layout_metrics":dict(STATE['layout_metrics']),
                "title_ready": STATE["title_ready"],
                "recognition_phase": STATE["recognition_phase"],
                "analysis_phase": STATE["analysis_phase"],
                "analysis_elapsed": round(time.time()-STATE["analysis_started"],1) if STATE["analysis_inflight"] else 0,
                "manual_phase": STATE["manual_phase"],
                "manual_phase_request": STATE.get("manual_phase_request"),
                "model": CONFIG["model"],
                "request_channels":__import__('requestgate').snapshot(),
                "judge_model": CONFIG.get("judge_model") or CONFIG["model"],
            },
            "wechat": dict(STATE["wechat"]),
            "border": STATE["border"],
            "session": STATE["session"],
            "messages": [dict(m) for m in STATE["messages"]][-30:],
            "source_signature": message_signature(STATE["messages"]),
            "analysis": {**analysis,"expired":not advice_fresh(analysis),"valid_for_seconds":ADVICE_TTL_SECONDS} if analysis else None,
            "analysis_error": STATE["analysis_error"],
            "analysis_diagnostics": STATE.get("analysis_diagnostics") if STATE["analysis_error"] else None,
            "analysis_inflight": STATE["analysis_inflight"],
            "manual_preview": STATE.get("manual_preview"),
            "last_area": STATE["last_area"],
            "launch_wait": STATE["launch_wait"],
            "participants": __import__('evidence').store(DSH_HOME).participants(STATE['session'])['items'],
            "identity_coverage": __import__('evidence').store(DSH_HOME).participants(STATE['session']),
            "harness": __import__('harness_adapter').status(),
            "settings": {
                "relationship": CONFIG["relationship"],
                "style": CONFIG["style"],
                "context": int(CONFIG["context"]),
                "reply_target": bool(CONFIG["reply_target"]),
                "reply_target_name": CONFIG["reply_target_name"],
                "junshi_layer": bool(CONFIG["junshi_layer"]),
                "model": CONFIG["model"],
                "judge_model": CONFIG.get("judge_model") or CONFIG["model"],
                "wechat_path": CONFIG["wechat_path"],
                "auto_launch": bool(CONFIG["auto_launch"]),
                "paused": bool(CONFIG["paused"]),
                "has_key": bool(API_KEY),
                "harness_enabled":bool(CONFIG.get('harness_enabled')),
                "generation_timeout":CONFIG['generation_timeout'],
                "max_model_calls":CONFIG['max_model_calls'],
                "max_cloud_requests":CONFIG['max_cloud_requests'],
                "max_analysis_cost":CONFIG['max_analysis_cost'],
                "uia_enabled":CONFIG['uia_enabled'],
                "vision_enabled": bool(CONFIG.get('vision_enabled')),
                "vision_base": CONFIG.get('vision_base',''),
                "vision_model": CONFIG.get('vision_model',''),
                "vision_keep_alive_minutes":CONFIG.get('vision_keep_alive_minutes',5),
                "enabled_extensions": CONFIG.get('enabled_extensions',[]),
                "start_at_login": startup_enabled(),
            },
            "log": list(LOG),
        }
        return payload


def do_fill(index, edited_text=None, analysis_ts=None):
    with _lock:
        analysis = STATE["analysis"]
        area = STATE["last_area"]
        hwnd = STATE["wechat"]["hwnd"]
        cur_session = STATE["session"]
        signature = message_signature(STATE["messages"])
    if analysis and analysis.get("source_signature") != signature:
        return {"ok": False, "error": "消息已变化，旧建议已过期，请重新分析"}
    if not analysis or not analysis.get("candidates"):
        return {"ok": False, "error": "还没有候选回复"}
    if analysis_ts is not None and analysis.get("ts") != analysis_ts:
        return {"ok": False, "error": "建议已更新，请查看新建议；你修改的文字仍可复制"}
    if edited_text is not None and analysis_ts is None:
        return {"ok": False, "error": "编辑后的回复缺少会话版本，请重新生成"}
    # 防填错会话：候选必须属于当前打开的会话
    if analysis.get("session") and cur_session and analysis["session"] != cur_session:
        return {"ok": False, "error": f"候选是「{analysis['session']}」的，当前已切到「{cur_session}」。请重新生成"}
    if not advice_fresh(analysis):
        return {'ok':False,'error':'建议已过期或时间异常，请重新生成；修改的文字仍可复制'}
    cands = analysis["candidates"]
    try:
        index = int(index)
    except (TypeError, ValueError):
        index = 0
    if not 0 <= index < len(cands):
        return {"ok": False, "error": "候选序号超出范围"}
    if not area or not hwnd:
        return {"ok": False, "error": "还没有定位到微信输入框（消息区未识别）"}
    text = cands[index] if edited_text is None else edited_text
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        return {"ok": False, "error": "回复应为 1 到 2000 字"}
    if any(word in text for word in ("转账", "红包", "借钱")):
        return {"ok": False, "error": "涉及资金操作，请自行核对处理"}
    try:
        if CONFIG.get("paused"):
            return {"ok": False, "error": "已暂停读取，仅允许复制"}
        fill_into(int(hwnd), area, text, verify=lambda: verify_live_session(int(hwnd), cur_session,expected_analysis=analysis))
    except Exception as e:
        log(f"填入失败：{' '.join(str(e).split())[:160]}")
        return {"ok": False, "error": f"填入失败：{' '.join(str(e).split())[:160]}"}
    log(f"已填入候选 {index + 1}（发送仍由你手动）")
    HOTKEY_CYCLE["index"] = int(index)  # 面板填入后，热键从这里继续循环
    return {"ok": True, "filled": text, "index": index}


def verify_live_session(hwnd, expected, expected_analysis=None):
    """Independent fresh screenshot; never trust stale capture-loop state."""
    if not advice_fresh(expected_analysis):
        raise RuntimeError('建议已过期或时间异常，停止填入')
    current, app = find_chat_hwnd()
    if not expected or current != hwnd or not app:
        raise RuntimeError("聊天窗口已变化，请复制回复后手动粘贴")
    cap, _ = make_capture(hwnd)
    frame = None
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            frame = cap.settled()
            if frame is not None:
                break
            time.sleep(0.05)
    finally:
        cap.stop()
    if frame is None:
        raise RuntimeError("无法重新核验当前会话，仅允许复制")
    area = chat_area(frame)
    if not area:
        raise RuntimeError("会话区域不确定，仅允许复制")
    from inputguard import inspect_input
    empty,reason=inspect_input(frame,area)
    if not empty:raise RuntimeError(reason)
    x0, y0, x1, y1, bg, y_pane = area
    title = read_title(frame[y_pane:y0,x0:x1], app)
    if not title or title.strip() != expected.strip():
        raise RuntimeError("当前会话标题不一致，已拒绝填入，仅允许复制")
    with _lock:
        if not expected_analysis or STATE.get('analysis') is not expected_analysis or expected_analysis.get('source_signature')!=message_signature(STATE['messages']):raise RuntimeError('消息或建议已更新，停止填入')
    if expected_analysis:
        reader=Reader(app)
        visible=reader.read(frame[y0:y1,x0:x1],bg)
        tail=[{'from':who,'name':nm,'text':text,'time':tm,'kind':kind,'media_id':reader.media_refs.get(y) if kind=='media_unknown' else None} for who,nm,text,y,tm,kind in visible[-3:]]
        expected_tail=[m.get('original_observation') or m for m in expected_analysis.get('source_tail',[])]
        if message_signature(tail,visual_only=True)!=message_signature(expected_tail,visual_only=True):
            raise RuntimeError('屏幕消息未核对一致，停止填入，请重新分析')
        if not advice_fresh(expected_analysis):
            raise RuntimeError('核验期间建议已过期，停止填入')


def do_copy(index):
    with _lock:
        analysis = STATE["analysis"]
    if not analysis or not analysis.get("candidates"):
        return {"ok": False, "error": "还没有候选回复"}
    cands = analysis["candidates"]
    try:
        index = int(index)
    except (TypeError, ValueError):
        index = 0
    if not 0 <= index < len(cands):
        return {"ok": False, "error": "候选序号超出范围"}
    from fill import set_clipboard
    try:
        set_clipboard(cands[index])
    except Exception as e:
        return {"ok": False, "error": f"复制失败：{e}"}
    return {"ok": True, "copied": cands[index]}


def do_analyze_text(body):
    msgs = body.get("messages") or []
    if not API_KEY:
        return {"ok": False, "error": "请先保存 API 密钥"}
    if not isinstance(msgs, list) or not msgs or len(msgs) > 100:
        return {"ok": False, "error": "消息数量应在 1 到 100 条之间"}
    if any(not isinstance(m, dict) or m.get("from") not in ("her", "me") or not isinstance(m.get("text"), str) or len(m["text"]) > 4000 for m in msgs):
        return {"ok": False, "error": "消息格式无效或过长"}
    rel = str(body.get("relationship") or CONFIG["relationship"])
    style = str(body.get('style','') if 'style' in body else CONFIG['style'])
    reply_to=body.get('reply_to')
    if reply_to is not None and (not isinstance(reply_to,str) or len(reply_to)>80):return {'ok':False,'error':'回复对象名称无效'}
    def progress(phase):
        with _lock:
            if STATE.get('manual_phase_request')==phase_id:STATE['manual_phase']=phase
    request_id=body.get('request_id')
    if request_id is not None and (not isinstance(request_id,str) or not request_id.strip() or len(request_id)>80):return {'ok':False,'error':'请求编号无效'}
    cancel_event=None
    phase_id=request_id or uuid.uuid4().hex
    phase_owned=False
    try:
        if request_id is not None:
            from manualjobs import jobs
            cancel_event=jobs.start(request_id)
            if cancel_event.is_set():raise InterruptedError('本次生成已取消')
        with _lock:STATE['manual_phase_request']=phase_id;STATE['manual_phase']='start';phase_owned=True
        from securestore import read_json
        try:vision_key=read_json(os.path.join(DSH_HOME,'vision-key.dpapi')).get('key','')
        except Exception:vision_key=''
        def preview(result):
            if request_id:
                with _lock:
                    if cancel_event and cancel_event.is_set():return
                    STATE['manual_preview']={'request_id':request_id,'result':{**result,'judgment':display_judgment(result.get('answers',{}))}}
        result = analyze(msgs, rel, API_KEY, model=CONFIG["model"], timeout=40,
                         judge_model=CONFIG.get("judge_model") or CONFIG["model"],
                         context=CONFIG["context"], style=style,reply_to=reply_to,
                         junshi_layer=CONFIG["junshi_layer"], progress=progress, settings={**CONFIG, '_force_fresh':bool(body.get('force_fresh',False)), **({'_cancel':cancel_event.is_set} if cancel_event is not None else {}), **({'_on_partial':preview} if request_id else {})},vision_key=vision_key,extension_dir=os.path.join(DSH_HOME,'extensions'))
        return {
            "ok": True,
            "candidates": result["candidates"],
            "review_ok": bool(result.get("review_ok")),
            "selection_method": result.get("selection_method"),
            "phase_timings": result.get("phase_timings", []),
            "model_trace": result.get("model_trace", []),
            "cost_reserved": result.get("cost_reserved", 0),
            "cost_is_estimate": True,
            "usage": dict(result.get('usage') or {}),
            "cache_hit": bool(result.get("cache_hit")),
            "cache_age_seconds": result.get("cache_age_seconds"),
            "coalesced":bool(result.get("coalesced")),
            "media_pending":bool(result.get("media_pending")),
            "completion_stage":result.get("completion_stage"),
            "scores": [round(float(s), 4) for s in result["scores"]],
            "best_index": int(result["best_index"]),
            "best_reason": result.get("best_reason") or "",
            "rank_ok": bool(result.get("rank_ok")),
            "judgment": display_judgment(result["answers"]),
            "understood_messages": result.get('understood_messages',[]),
            "warnings": result.get('warnings',[]),
            "extension_notes": result.get('extension_notes',[]),
        }
    except InterruptedError:
        return {'ok':False,'cancelled':True,'error':'本次生成已取消，输入文字仍保留'}
    except Exception as e:
        return {"ok": False, "error": " ".join(str(e).split())[:200], "diagnostics":__import__('analysisdiag').safe(getattr(e,'analysis_diagnostics',None))}
    finally:
        if cancel_event is not None:jobs.finish(request_id,cancel_event)
        with _lock:
            if phase_owned and STATE.get('manual_phase_request')==phase_id:
                STATE['manual_phase']='idle';STATE['manual_phase_request']=None


class Handler(BaseHTTPRequestHandler):
    server_version = "DshJunshi/1.0"

    def log_message(self, fmt, *args):  # 静默
        pass

    def _check(self):
        import hmac
        if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return False
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
            flog('API host rejected: '+repr(host)+' expected_port='+str(self.server.server_port))
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
            return False
        path = up.urlparse(self.path).path
        if self.command == "GET" and path in ("/ui", "/ui/panel.js"):
            return True
        auth = self.headers.get("Authorization", "")
        accepted = bool(_token) and hmac.compare_digest(auth, "Bearer " + _token)
        if not accepted:flog('API authentication rejected; authorization_present='+str(bool(auth)))
        return accepted
    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 不发 Access-Control-Allow-Origin：引擎只服务本机代理，杜绝任意网页直读聊天内容
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 <= n <= (28*1024*1024 if self.path=='/media-file' else 262144):
            raise ValueError("请求过大")
        value = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        if not isinstance(value, dict):
            raise ValueError("请求必须为 JSON 对象")
        return value

    def _route(self):
        global API_KEY
        parsed = up.urlparse(self.path)
        path = parsed.path
        if not self._check():
            self._json({"ok": False, "error": "unauthorized"}, 401)
            return
        if self.command == 'GET' and path == '/capabilities':
            self._json({'ok':True,'api_version':'1.0','app_version':'1.5.69','tools':['state','participants','analyze-text','cancel-manual','regenerate','settings','extensions','vision-models','fill','models','evidence','correct-message','uia','memory-confirm','media-file','media-job','attach-media','verify-extension'], 'evidence_api_version':'1.1', 'sends_messages':False});return
        if self.command == 'POST' and path == '/cancel-manual':
            identity=self._body().get('request_id')
            if not isinstance(identity,str) or not identity.strip() or len(identity)>80:raise ValueError('请求编号无效')
            from manualjobs import jobs
            jobs.cancel(identity);self._json({'ok':True,'cancellation_requested':True});return
        if self.command == 'POST' and path == '/media-file':
            body=self._body()
            with _lock:
                if any(job['state'] in ('queued','running') for job in STATE['media_jobs'].values()):raise ValueError('已有媒体正在处理')
                identity=uuid.uuid4().hex
                STATE['media_jobs']={identity:{'id':identity,'state':'queued','phase':'speech','started':time.time()}}
                settings=dict(CONFIG)
            def work():
                job=STATE['media_jobs'][identity];job['state']='running'
                try:
                    from securestore import read_json
                    try:key=read_json(os.path.join(DSH_HOME,'vision-key.dpapi')).get('key','')
                    except Exception:key=''
                    def progress(phase):job['phase']=phase
                    job['result']=__import__('avmedia').analyze_upload(body,settings,key,progress);job['state']='done'
                except Exception as exc:job['error']=str(exc)[:200];job['state']='error'
                finally:job['seconds']=round(time.time()-job['started'],2)
            threading.Thread(target=work,daemon=True).start();self._json({'ok':True,'id':identity});return
        if self.command == 'POST' and path == '/media-job':
            identity=self._body().get('id')
            self._json({'ok':True,'job':STATE['media_jobs'].get(identity,{'state':'expired'})});return
        if self.command == 'POST' and path == '/memory-confirm':
            body=self._body();fact=body.get('fact')
            if not isinstance(fact,str) or not 1<=len(fact.strip())<=200:raise ValueError('确认事实应为1至200字')
            from memory import load_memory,save_memory
            with _lock:
                contact=STATE['session']
                if body.get('session')!=contact:raise ValueError('会话已变化')
                memory=load_memory(contact);memory.update(source='user_confirmed',updated=time.time());memory['facts']=(memory['facts']+[fact.strip()])[-30:];save_memory(contact,memory)
            self._json({'ok':True});return
        if self.command == 'GET' and path == '/models':
            self._json({'ok':True,'models':__import__('modelrouter').catalog(DSH_HOME)});return
        if self.command == 'POST' and path == '/models':
            from pathlib import Path
            from modelrouter import validate_models
            from securestore import write_json
            body=self._body();rows=validate_models(body.get('models'))
            from modelsettings import is_unchanged
            if is_unchanged(DSH_HOME,rows,body.get('keys',{})):
                self._json({'ok':True,'models':rows,'unchanged':True});return
            for identity,key in body.get('keys',{}).items():
                if identity not in {r['id'] for r in rows} or not isinstance(key,str) or len(key)>1000:raise ValueError('模型密钥无效')
                write_json(Path(DSH_HOME)/('model-'+identity+'.dpapi'),{'key':key})
            target=Path(DSH_HOME)/'models.json';temp=target.with_suffix('.tmp');temp.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8');temp.replace(target)
            with _lock:STATE['session_since']=time.time();STATE['analysis']=None
            schedule_analysis()
            self._json({'ok':True,'models':rows});return
        if self.command == 'GET' and path == '/uia':
            self._json({'ok':True,'snapshot':__import__('uia_reader').snapshot(STATE['wechat'].get('hwnd',0)) if CONFIG.get('uia_enabled') else {'available':False,'reason':'disabled'}});return
        if self.command == 'POST' and path == '/evidence':
            body=self._body();key=body.get('crop_id','')
            if not isinstance(key,str):raise ValueError('证据编号无效')
            self._json({'ok':True,'image':__import__('media').get(key),'expired':not bool(__import__('media').get(key))});return
        if self.command == 'POST' and path == '/attach-media':
            body=self._body()
            with _lock:
                if body.get('session')!=STATE['session']:raise ValueError('会话已变化，请重新关联')
                target=next((m for m in STATE['messages'] if m.get('message_id')==body.get('message_id')),None)
                job=STATE['media_jobs'].get(body.get('job_id'))
                if not target or target.get('kind') not in ('media_unknown','video','audio'):raise ValueError('请确认文件属于当前可见媒体消息')
                if not job or job.get('state')!='done':raise ValueError('媒体处理尚未完成或已过期')
                decoded=job['result'];parts=[decoded['coverage']]
                parts+=['转写 '+str(s['start'])+'-'+str(s['end'])+'秒：'+s['text']+('（不确定）' if s['uncertain'] else '') for s in decoded.get('transcript',[])]
                parts+=['抽样画面 '+str(s['second'])+'秒：'+(s.get('description') or '未知') for s in decoded.get('visual_samples',[])]
                fields={'kind':'video' if decoded.get('has_video') else 'audio','media_description':'\n'.join(parts)[:4000],'media_transcript':decoded.get('transcript',[]),'content_source':'user_attached_file','file_evidence':{'sha256':decoded.get('file_sha256'),'filename':decoded.get('filename'),'coverage':decoded['coverage'],'job_id':body.get('job_id')}}
                corrected=__import__('evidence').store(DSH_HOME).attach_media(target['message_id'],fields)
                for collection in (STATE['messages'],STATE['messages_by_session'].get(STATE['session'],[])):
                    for index,message in enumerate(collection):
                        if message.get('message_id')==corrected['message_id']:collection[index]=corrected
                STATE['session_since']=time.time();STATE['analysis']=None
            schedule_analysis();self._json({'ok':True,'message':corrected});return
        if self.command == 'POST' and path == '/correct-message':
            body=self._body()
            with _lock:
                if body.get('session')!=STATE['session'] or not any(m.get('message_id')==body.get('message_id') for m in STATE['messages']):raise ValueError('会话已变化或消息已过期')
                corrected=__import__('evidence').store(DSH_HOME).correct(body.get('message_id'),body.get('patch'))
                for collection in (STATE['messages'],STATE['messages_by_session'].get(STATE['session'],[])):
                    for idx,m in enumerate(collection):
                        if m.get('message_id')==corrected['message_id']:collection[idx]=corrected
                STATE['analysis']=None
                STATE['session_since']=time.time()
            schedule_analysis();self._json({'ok':True,'message':corrected});return
        if self.command == 'GET' and path == '/participants':
            payload=state_payload();self._json({'ok':True,'session':payload['session'],'participants':payload['participants'],'identity_limit':'仅按屏幕昵称区分；同名不能视为唯一账号'});return
        if self.command == 'GET' and path == '/extensions':
            from extensions import catalog
            self._json({'ok':True,'extensions':catalog(os.path.join(DSH_HOME,'extensions')),'enabled':CONFIG.get('enabled_extensions',[])});return
        if self.command == 'POST' and path == '/verify-extension':
            from extensions import verify
            body=self._body()
            self._json({'ok':True,'verification':verify(os.path.join(DSH_HOME,'extensions'),body.get('id',''))});return
        if self.command == 'GET' and path == '/vision-models':
            from vision import validate_base
            from urllib.parse import urlparse
            base=validate_base(CONFIG.get('vision_base',''));parsed=urlparse(base)
            if parsed.hostname not in ('127.0.0.1','localhost','::1'):raise ValueError('自动发现目前只支持本机 Ollama')
            endpoint=f'{parsed.scheme}://{parsed.netloc}/api/tags'
            with __import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['ProxyHandler']).ProxyHandler({})).open(endpoint,timeout=5) as r:data=json.load(r)
            models=[]
            opener=__import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['ProxyHandler']).ProxyHandler({}))
            for item in data.get('models',[]):
                caps=item.get('capabilities',[])
                if not caps:
                    request=__import__('urllib.request',fromlist=['Request']).Request(f'{parsed.scheme}://{parsed.netloc}/api/show',data=json.dumps({'model':item['name']}).encode(),headers={'Content-Type':'application/json'})
                    try:
                        with opener.open(request,timeout=5) as response:details=json.load(response)
                        caps=details.get('capabilities',[])
                    except Exception:pass
                models.append({'name':item['name'],'vision':'vision' in caps})
            self._json({'ok':True,'models':models});return
        if self.command == 'POST' and path == '/vision-key':
            from securestore import write_json
            key=self._body().get('key')
            if not isinstance(key,str) or len(key)>1000:raise ValueError('密钥无效')
            write_json(os.path.join(DSH_HOME,'vision-key.dpapi'),{'key':key});self._json({'ok':True});return
        if self.command == "GET" and path == "/health":
            self._json({"ok": True, "pid": os.getpid(), "status": STATE["status"], "heartbeat_age": round(time.time() - STATE["heartbeat"], 1), "capture_thread_alive": bool(getattr(self.server, "capture_thread", None) and self.server.capture_thread.is_alive())})
            return
        if self.command == "GET" and path == "/state":
            self._json(state_payload())
            return
        if self.command == "GET" and path == "/frame.png":
            with _lock:
                frame = STATE["last_frame"]
                captured_at = STATE["last_frame_at"]
            if frame is None:
                self._json({"ok": False, "error": "还没有帧"}, 404)
                return
            try:
                from PIL import Image
                scale=1 if self.headers.get('X-Junshi-Frame-Scale')=='1' else 2
                small = frame[::scale, ::scale]
                img = Image.fromarray(np.ascontiguousarray(small))
                buf = io.BytesIO()
                img.save(buf, "PNG")
                data = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                if captured_at is not None:self.send_header('X-Junshi-Captured-At',str(captured_at))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return
        if self.command == "GET" and path == "/settings":
            self._json({"ok": True, "settings": state_payload()["settings"]})
            return
        if self.command == "POST" and path == "/startup":
            enabled = self._body().get("enabled")
            if not isinstance(enabled, bool):
                raise ValueError("开机启动选项无效")
            set_startup(enabled)
            self._json({"ok": True})
            return
        if self.command == "POST" and path == "/settings":
            patch = self._body()
            if not isinstance(patch,dict):raise ValueError("设置必须为对象")
            expected=patch.pop("expected_session",None)
            saved=save_config(patch,expected_session=expected)
            log("设置已更新")
            self._json({"ok": True, "settings": state_payload()["settings"],**saved})
            return
        if self.command == "POST" and path == "/fill":
            body = self._body()
            self._json(do_fill(body.get("index", 0), edited_text=body.get("text"), analysis_ts=body.get("analysis_ts")))
            return
        if self.command == "POST" and path == "/copy-text":
            text = self._body().get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                self._json({"ok": False, "error": "回复应为 1 到 2000 字"}, 400)
                return
            from fill import set_clipboard
            set_clipboard(text)
            self._json({"ok": True})
            return
        if self.command == "POST" and path == "/copy":
            self._json(do_copy(self._body().get("index", 0)))
            return
        if self.command == "POST" and path == "/pause":
            save_config({"paused": True})
            with _lock:
                STATE["session_since"] = time.time()
            log("已暂停读取")
            self._json({"ok": True})
            return
        if self.command == "POST" and path == "/resume":
            if not API_KEY:
                self._json({"ok": False, "error": "请先保存 API 密钥"}, 400)
                return
            save_config({"paused": False})
            schedule_analysis()
            log("已恢复读取")
            self._json({"ok": True})
            return
        if self.command == "POST" and path == "/regenerate":
            if not API_KEY:
                self._json({"ok": False, "error": "请先保存 API 密钥"}, 400)
                return
            with _lock:
                if ANALYSIS_GUARD["in_flight"]:
                    ANALYSIS_GUARD["pending"] = True
                    ANALYSIS_GUARD["pending_force_fresh"] = True
                    self._json({"ok": True, "note": "已记住你的偏好，当前分析结束后更新"})
                    return
                msgs = [dict(m) for m in STATE["messages"]]
                cfg = dict(CONFIG)
                cfg["_session"] = STATE["session"]
                cfg["_session_since"] = STATE["session_since"]
                cfg['_force_fresh'] = True
                if not msgs:
                    self._json({"ok": False, "error": "还没有识别到消息"})
                    return
                ANALYSIS_GUARD["in_flight"] = True
            threading.Thread(target=run_analysis, args=(msgs, cfg, ANALYSIS_GUARD), daemon=True).start()
            self._json({"ok": True, "note": "正在重新生成候选"})
            return
        if self.command == "POST" and path == "/analyze-text":
            self._json(do_analyze_text(self._body()))
            return
        if self.command == "POST" and path == "/launch-wechat":
            self._json(launch_wechat())
            return
        if self.command == "POST" and path == "/key-delete":
            API_KEY = ""
            os.environ.pop("DEEPSEEK_API_KEY", None)
            try:
                os.remove(os.path.join(DSH_HOME, "api-key.dpapi"))
            except FileNotFoundError:
                pass
            save_config({"paused": True})
            with _lock:
                STATE["analysis"] = None
            self._json({"ok": True})
            return
        if self.command == "POST" and path == "/key":
            body = self._body()
            key = str(body.get("key") or "").strip()
            if not key:
                self._json({"ok": False, "error": "密钥不能为空"}, 400)
                return
            API_KEY = key
            os.environ["DEEPSEEK_API_KEY"] = key
            try:
                from securestore import write_json
                write_json(os.path.join(DSH_HOME, "api-key.dpapi"), {"key": key})
            except Exception:
                self._json({"ok": False, "error": "Windows 加密保存失败，请重试"}, 500)
                return
            log("密钥已使用 Windows DPAPI 加密保存")
            self._json({"ok": True, "saved_secure": True})
            return
        if self.command == "POST" and path == "/memory-clear":
            with _lock:
                contact = STATE["session"] or "当前会话"
                if STATE["analysis"]:
                    STATE["analysis"]["memory_facts"] = 0
            try:
                from memory import memory_path
                p = memory_path(contact)
                if os.path.isfile(p):
                    os.remove(p)
                    log(f"已清空「{contact}」的军师记忆")
                    self._json({"ok": True, "note": f"已清空「{contact}」的记忆"})
                else:
                    self._json({"ok": True, "note": "这个会话还没有记忆"})
            except Exception as e:
                self._json({"ok": False, "error": f"清空失败：{e}"})
            return
        if self.command == "GET" and path == "/ui":
            html = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<title>军师 · 微信回复</title>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<style>html,body{margin:0;padding:0;background:#17191d;overflow:hidden}</style>"
                "</head><body>"
                "<script>window.__DSH_JUNSHI_API__='';window.__JUNSHI_STANDALONE__=true</script>"
                "<script src='/ui/panel.js'></script>"
                "</body></html>")
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.command == "GET" and path == "/ui/panel.js":
            js = _panel_js()
            if js is None:
                self._json({"ok": False, "error": "panel.js 不可用"}, 404)
                return
            body = js.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.command == "POST" and path == "/shutdown":
            self._json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_GET(self):
        try:
            self._route()
        except Exception as e:
            self._json({"ok": False, "error": " ".join(str(e).split())[:200]}, 500)

    def do_POST(self):
        try:
            self._route()
        except Exception as e:
            self._json({"ok": False, "error": " ".join(str(e).split())[:200]}, 500)


def main():
    flog(f"main start pid={os.getpid()} python={sys.version.split()[0]}")
    import faulthandler
    faulthandler.enable()
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
    load_config()
    flog(f"config loaded, key={'yes' if API_KEY else 'no'}, paused={CONFIG.get('paused')}")
    if not API_KEY:
        log("未设置 DEEPSEEK_API_KEY：能读屏，但无法生成候选")
    # Tracebacks on demand only; avoid hourly growth during healthy idle.
    border_box = {}
    stop = threading.Event()
    t = threading.Thread(target=capture_loop, args=(border_box, stop), daemon=True)
    t.start()
    threading.Thread(target=hotkey_loop, args=(stop,), daemon=True).start()
    log("军师引擎已启动")
    if CONFIG.get("auto_launch"):
        hwnd, _ = find_chat_hwnd()
        if not hwnd:
            threading.Thread(target=launch_wechat, daemon=True).start()
    port = int(os.environ.get("DSH_JUNSHI_PORT") or 47830)
    server, actual, last_err = None, port, None
    for attempt in range(10):
        try:
            import socket
            class ExclusiveHTTPServer(ThreadingHTTPServer):
                allow_reuse_address = False
                def server_bind(self):
                    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    super().server_bind()
            server = ExclusiveHTTPServer(("127.0.0.1", port + attempt), Handler)
            actual = port + attempt
            break
        except OSError as e:
            last_err = e
    if server is None:
        log(f"端口绑定失败：{last_err}")
        os._exit(2)
    try:
        # 每个插件实例按自己的 token 写独立端口文件，多实例互不干扰；旧通用文件保留作兼容
        tag = re.sub(r"[^A-Za-z0-9]", "", _token)[:8] or "open"
        with open(os.path.join(DSH_HOME, f".dsh-junshi.port.{tag}"), "w", encoding="utf-8") as f:
            f.write(str(actual))
        with open(os.path.join(DSH_HOME, ".dsh-junshi.port"), "w", encoding="utf-8") as f:
            f.write(str(actual))
    except Exception:
        pass
    server.capture_thread = t
    log(f"HTTP API: 127.0.0.1:{actual}")
    flog(f"bound port {actual}")
    # 独立运行（exe 双击，无宿主 token）：自动打开浏览器面板
    if not _token and os.environ.get("DSH_JUNSHI_NO_BROWSER") != "1":
        try:
            threading.Timer(1.0, lambda: os.startfile(f"http://127.0.0.1:{actual}/ui")).start()
            log("已打开独立面板（浏览器）")
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        from harness_adapter import close_all
        close_all()
        server.server_close()
        b = border_box.get("b")
        if b:
            try:
                b.dispose()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        flog("FATAL: " + traceback.format_exc())
        raise


