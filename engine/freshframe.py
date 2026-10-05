"""Fresh-frame acquisition for the latest-position witness.

Why this module exists
----------------------
The witness used to be measured from `STATE["last_frame"]`, the engine's own
WGC frame, and rejected whenever that frame was older than a wall-clock bound.
Measured on real WeChat (2026-10-03), that design could never pass:

  * WGC only emits a frame when the window repaints. A motionless WeChat
    legitimately produces no new frame, so `frame_age` grows without bound.
    Observed: 13s -> 33s -> 127s -> 241s -> 437s on a window whose pixels were
    provably unchanged (successive screen grabs differed by 0 changed pixels).
  * The capture loop itself was alive the whole time (`ticks` climbing, status
    `capturing`, `recognition_phase` cycling), so the growing age said nothing
    about capture health.
  * Result: `available=false, reason='画面已过期'` forever, on a window that was
    demonstrably at a stable position. Automatic filling was unreachable in
    exactly the still case it is designed for.

So instead of asking "how old is the engine's frame", this module asks the only
question that actually matters: "does a freshly captured frame still show the
same thing the engine last measured?"

`frame_unchanged()` re-captures the window and compares it against the engine's
frame. If they match, the engine's frame still describes the screen, no matter
how long ago it arrived. If they differ, the verdict is refused and the engine
will pick up the new frame on its next capture. The wall-clock age stays as a
diagnostic only, never as the gate.

Two independent guards, both mandatory:

1. `unobscured()` — a screen grab shows whatever is on top. If another window
   covers WeChat, the grab is not WeChat's content and must never be measured.
   Verified against real windows: `WindowFromPoint` on a 3x3 grid over the
   window, each hit resolved to its root ancestor and compared to WeChat's hwnd.
2. `frame_matches_window()` — WGC can hand back a frame whose size disagrees
   with the window rect (observed 1281 vs 735). A mismatch is refused outright.

Read-only by construction: this module only reads pixels and window geometry.
It contains no input, focus, click, clipboard, or send path, and tests assert
that by source inspection.
"""
import sys
import time

_FORBIDDEN_SOURCE = (
    "SendKeys", "SendInput", "keybd_event", "mouse_event", "SetForegroundWindow",
    "SetActiveWindow", "SetFocus", "Click", "ScrollTo", "SetClipboard",
    "clipboard", "PostMessage", "SendMessage", "WM_SETTEXT", "pyperclip",
)


def _unverified(reason, **extra):
    out = {
        "available": False,
        "verified": False,
        "reason": reason,
        "source": "fresh_frame_currency",
        "read_only": True,
        "evidence_kind": "geometry_only",
    }
    out.update(extra)
    return out


def source_is_read_only(path=None):
    """True when this module contains no input/focus/click/send path.

    Checked on the parsed syntax tree, not on raw text: the module docstring
    deliberately *names* the forbidden operations to explain why they are
    absent, and a substring scan over the source would read that prose as a
    violation. Only real identifiers and attribute accesses are considered.
    """
    import ast
    import os
    path = path or os.path.abspath(__file__)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except Exception:
        return False
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            else:
                names.append(node.module or "")
        for name in names:
            for token in _FORBIDDEN_SOURCE:
                if token in name:
                    return False
    return True


def window_rect(hwnd):
    """Current window rect via the engine's own reader (DPI-correct)."""
    from capture import window_rect as _wr
    return _wr(int(hwnd))


def frame_matches_window(shape, rect):
    """A frame whose size disagrees with the window rect is refused."""
    try:
        h, w = shape[:2]
        left, top, right, bottom = (int(v) for v in rect)
    except Exception:
        return False
    ww, wh = right - left, bottom - top
    if ww <= 0 or wh <= 0:
        return False
    return abs(int(w) - ww) <= 2 and abs(int(h) - wh) <= 2


def unobscured(hwnd, rect, grid=3):
    """True when every sampled point over the window belongs to WeChat itself.

    A screen grab shows the topmost window at each pixel, so an overlapping
    window would silently contribute someone else's pixels. Resolving
    `WindowFromPoint` to its root ancestor and comparing against WeChat's hwnd
    detects that without touching either window.
    """
    import ctypes
    from ctypes import wintypes
    try:
        user32 = ctypes.windll.user32
        get_ancestor = user32.GetAncestor
        get_ancestor.restype = wintypes.HWND
        get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
    except Exception:
        return False
    left, top, right, bottom = (int(v) for v in rect)
    if right - left < 40 or bottom - top < 40:
        return False
    grid = max(2, int(grid))
    for iy in range(grid):
        y = top + int((bottom - top) * (iy + 1) / (grid + 1))
        for ix in range(grid):
            x = left + int((right - left) * (ix + 1) / (grid + 1))
            try:
                hit = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
            except Exception:
                return False
            if not hit:
                return False
            try:
                root = int(get_ancestor(hit, 2) or 0)  # GA_ROOT
            except Exception:
                return False
            if root != int(hwnd):
                return False
    return True


def grab(hwnd, rect):
    """Fresh screen grab of the window as (bgr_uint8, gray_uint8).

    Returns (None, None) on any failure: the witness must never fall back to a
    stale frame, so an unreadable grab is a refusal, not a retry-with-old-data.
    """
    try:
        import numpy as np
        from PIL import ImageGrab
    except Exception:
        return None, None
    left, top, right, bottom = (int(v) for v in rect)
    try:
        opener = getattr(ImageGrab, "grab", None)
        if opener is None:
            return None, None
        try:
            img = opener(bbox=(left, top, right, bottom), all_screens=True)
        except TypeError:
            img = opener(bbox=(left, top, right, bottom))
    except Exception:
        return None, None
    if img is None:
        return None, None
    try:
        rgb = np.asarray(img.convert("RGB"))
        gray = np.asarray(img.convert("L"))
        # Engine frames are BGR uint8, matching Capture.settled().
        return np.ascontiguousarray(rgb[:, :, ::-1]), gray
    except Exception:
        return None, None


def to_luma(frame):
    """Convert a BGR engine frame to the same luma the fresh grab is reduced to.

    The fresh grab is turned into grayscale by PIL's `convert("L")`, which is a
    rounded ITU-R 601-2 luma. Reducing the engine's colour frame with a plain
    channel mean instead disagrees by more than the comparison tolerance on any
    saturated pixel, so a genuinely identical window measured 3.2% "changed" and
    the gate refused everything. Both sides must use the same definition.
    """
    import numpy as np
    arr = np.asarray(frame)
    if getattr(arr, "ndim", 0) != 3 or arr.shape[2] < 3:
        return arr
    b = arr[:, :, 0].astype(np.float64)
    g = arr[:, :, 1].astype(np.float64)
    r = arr[:, :, 2].astype(np.float64)
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return np.clip(np.rint(luma), 0, 255).astype(arr.dtype if arr.dtype.kind == "f" else np.uint8)


def frame_unchanged(engine_frame, fresh_gray, rect, tolerance=12, max_changed=0.004):
    """True when a fresh grab matches the engine's frame in the window area.

    `max_changed` is the fraction of pixels allowed to differ by more than
    `tolerance`. Measured on a still WeChat: 0.0. The bound exists so that
    anti-aliasing or a caret cannot veto an otherwise identical frame, while a
    genuinely changed window (new message, scroll) still fails.
    """
    import numpy as np
    if engine_frame is None or fresh_gray is None:
        return False, None
    try:
        eg = to_luma(engine_frame)
        eg = np.asarray(eg)
        h = min(eg.shape[0], fresh_gray.shape[0])
        w = min(eg.shape[1], fresh_gray.shape[1])
        if h < 40 or w < 40:
            return False, None
        a = eg[:h, :w].astype(int)
        b = np.asarray(fresh_gray)[:h, :w].astype(int)
        diff = np.abs(a - b)
        changed = float((diff > int(tolerance)).mean())
        return changed <= float(max_changed), round(changed, 6)
    except Exception:
        return False, None


def confirm_frame_current(hwnd, engine_frame, engine_frame_at, stale_after=900.0):
    """Decide whether `engine_frame` still describes the screen right now.

    Returns a witness-shaped dict carrying diagnostics; `available=False` means
    the caller must keep every guard active.

    The wall-clock age is reported but never used as the gate, because a still
    window has no repaint to wait for. Only a real disagreement between the
    engine's frame and a fresh grab, an occluded window, a size mismatch, or a
    genuinely stalled pipeline can refuse.
    """
    if not hwnd:
        return _unverified("微信窗口未就绪，无法核对是否位于最新位置")
    if engine_frame is None or not engine_frame_at:
        return _unverified("还没有当前画面，无法核对是否位于最新位置")

    age = max(0.0, time.time() - float(engine_frame_at))
    diag = {
        "frame_age_seconds": round(age, 2),
        "frame_source": "engine_wgc_frame",
        "freshness_rule": "screen_regrab_agreement_not_wallclock",
        "stale_after_seconds": float(stale_after),
    }
    # A pipeline that has not even confirmed a frame for a very long time is
    # treated as stalled. This bound is deliberately generous: it only exists to
    # catch a dead capture, and it is not the freshness test.
    if age > float(stale_after):
        out = _unverified(
            "画面已过期（%.1f 秒前），无法核对是否位于最新位置" % age, **diag)
        out["frame_is_current"] = False
        out["capture_live"] = False
        return out

    try:
        rect = window_rect(hwnd)
    except Exception:
        return _unverified("无法读取微信窗口位置，无法核对是否位于最新位置", **diag)
    diag["window_rect"] = [int(v) for v in rect]

    if not frame_matches_window(getattr(engine_frame, "shape", ()), rect):
        out = _unverified("捕获画面尺寸与窗口不一致，已拒绝判定", **diag)
        out["frame_matches_window"] = False
        return out
    diag["frame_matches_window"] = True

    if not unobscured(hwnd, rect):
        out = _unverified("微信窗口被其它窗口遮挡，无法核对是否位于最新位置", **diag)
        out["unobscured"] = False
        return out
    diag["unobscured"] = True

    fresh, fresh_gray = grab(hwnd, rect)
    if fresh is None or fresh_gray is None:
        out = _unverified("无法获取当前画面，无法核对是否位于最新位置", **diag)
        out["frame_is_current"] = False
        return out

    same, changed = frame_unchanged(engine_frame, fresh_gray, rect)
    diag["changed_pixel_ratio"] = changed
    diag["frame_is_current"] = bool(same)
    diag["capture_live"] = True
    diag["frame_source"] = "engine_wgc_frame+screen_regrab"
    if not same:
        out = _unverified(
            "微信窗口画面已变化，等待新画面后重新核对是否位于最新位置", **diag)
        out["frame_is_current"] = False
        return out
    return diag
