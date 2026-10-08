"""把选中的候选填进微信输入框：写剪贴板 → 点输入框 → Ctrl+V。
绝不发回车、绝不点发送。（基于 JevChat-Windows，MIT）"""
import ctypes
import ctypes.wintypes as w
import time

u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32

k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
k32.GlobalFree.argtypes = [ctypes.c_void_p]
u32.SetClipboardData.restype = ctypes.c_void_p
u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
# 64 位句柄安全：前台窗口/焦点相关调用全部显式声明，防止按 c_int 截断句柄。
u32.GetForegroundWindow.restype = ctypes.c_void_p
u32.GetForegroundWindow.argtypes = []
u32.SetForegroundWindow.restype = w.BOOL
u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
u32.GetWindowThreadProcessId.restype = ctypes.c_ulong
u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u32.GetCursorPos.restype = w.BOOL
u32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
u32.SetCursorPos.restype = w.BOOL
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u32.AttachThreadInput.restype = w.BOOL
u32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, w.BOOL]
u32.OpenClipboard.restype = w.BOOL
u32.OpenClipboard.argtypes = [ctypes.c_void_p]
u32.GetClipboardData.restype = ctypes.c_void_p
u32.GetClipboardData.argtypes = [ctypes.c_uint]
u32.EmptyClipboard.restype = w.BOOL
u32.EmptyClipboard.argtypes = []
u32.CloseClipboard.restype = w.BOOL
u32.CloseClipboard.argtypes = []
u32.IsClipboardFormatAvailable.restype = w.BOOL
u32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]


def read_clipboard_text():
    """读剪贴板当前文本；失败返回 None（不抛）。"""
    try:
        if not u32.OpenClipboard(None):
            return None
        try:
            h = u32.GetClipboardData(13)
            if not h:
                return None
            p = k32.GlobalLock(h)
            if not p:
                return None
            try:
                return ctypes.wstring_at(p)
            finally:
                k32.GlobalUnlock(h)
        finally:
            u32.CloseClipboard()
    except Exception:
        return None


def _clipboard_holds_non_text():
    """剪贴板里是图片/文件等无法恢复的内容时返回 True（不能为一次粘贴清掉它）。"""
    try:
        if not u32.OpenClipboard(None):
            return False
        try:
            return bool(u32.IsClipboardFormatAvailable(2) or u32.IsClipboardFormatAvailable(15)
                        or u32.IsClipboardFormatAvailable(0xC006) or u32.IsClipboardFormatAvailable(0xC005))
        finally:
            u32.CloseClipboard()
    except Exception:
        return False


def set_clipboard(text):
    """写剪贴板（重试几次，避开剪贴板被占用）。"""
    data = text.encode("utf-16-le") + b"\0\0"
    for attempt in range(10):
        if not u32.OpenClipboard(None):
            time.sleep(0.05)
            continue
        try:
            u32.EmptyClipboard()
            h = k32.GlobalAlloc(0x2, len(data))
            if not h:
                raise RuntimeError("GlobalAlloc 失败")
            p = k32.GlobalLock(h)
            if not p:
                k32.GlobalFree(h)
                raise RuntimeError("GlobalLock 失败")
            ctypes.memmove(p, data, len(data))
            k32.GlobalUnlock(h)
            if not u32.SetClipboardData(13, h):
                k32.GlobalFree(h)
                raise RuntimeError(f"SetClipboardData 失败 (attempt {attempt})")
            return
        finally:
            u32.CloseClipboard()
    raise RuntimeError("OpenClipboard 连续失败，剪贴板被其他程序占用")


def fill(hwnd, area, text, rect=None, verify=None):
    """area = 消息区 (x0, y0, x1, y1)（帧内物理像素）；输入框就在底线 y1 下面。"""
    from capture import unminimize, window_rect

    if verify:
        verify()
    # 手动模式先还原再取坐标：最小化时 GetWindowRect 给的是最小化矩形，坐标会落空。
    unminimize(hwnd)
    if _clipboard_holds_non_text():
        raise RuntimeError("剪贴板里有图片或文件，为避免覆盖它们请先复制一段文字后再填入")
    old_clip = read_clipboard_text()
    set_clipboard(text)
    r = w.RECT()
    if rect is None:
        l, t, rr, b = window_rect(hwnd)
        r.left, r.top, r.right, r.bottom = l, t, rr, b
    else:
        r.left, r.top, r.right, r.bottom = rect
    x0, _, _, y1 = area
    cx, cy = r.left + x0 + 60, r.top + y1 + 40  # 分隔线下 40px = 输入框文字区

    # SetForegroundWindow 有前台保护，AttachThreadInput 绕过
    fg = u32.GetForegroundWindow()
    if fg != hwnd:
        fg_tid = u32.GetWindowThreadProcessId(fg, None)
        our_tid = k32.GetCurrentThreadId()
        u32.AttachThreadInput(our_tid, fg_tid, True)
        u32.SetForegroundWindow(hwnd)
        u32.AttachThreadInput(our_tid, fg_tid, False)
        time.sleep(0.15)

    old = w.POINT()
    u32.GetCursorPos(ctypes.byref(old))
    u32.SetCursorPos(cx, cy)
    time.sleep(0.05)
    u32.mouse_event(0x2, 0, 0, 0, 0)
    u32.mouse_event(0x4, 0, 0, 0, 0)
    time.sleep(0.05)
    u32.SetCursorPos(old.x, old.y)
    time.sleep(0.05)
    if u32.GetForegroundWindow() != hwnd:
        raise RuntimeError("微信未获得焦点，已拒绝粘贴")
    if verify:
        verify()
    # 发键前复检前台窗口：核验之后切窗/焦点被抢会让 Ctrl+V 贴到别处。
    # 手动模式不复检输入空闲——GetLastInputInfo 对任何鼠标移动都更新，
    # 手动点“填入”后随手移动鼠标会误中止。
    if u32.GetForegroundWindow()!=hwnd:raise RuntimeError('前台窗口变化，已拒绝粘贴')
    # 光标移到已有文本末尾再粘贴：连续多次填入不串行
    u32.keybd_event(0x11, 0, 0, 0)
    u32.keybd_event(0x23, 0, 0, 0)
    u32.keybd_event(0x23, 0, 2, 0)
    u32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.05)
    u32.keybd_event(0x11, 0, 0, 0)
    u32.keybd_event(0x56, 0, 0, 0)
    u32.keybd_event(0x56, 0, 2, 0)
    u32.keybd_event(0x11, 0, 2, 0)
    # 到此为止。发不发、改不改，人来。
    # 微信异步处理 Ctrl+V 时才读剪贴板：等它取完再恢复，避免贴到旧内容。
    if old_clip is not None:
        time.sleep(0.2)
        if read_clipboard_text() == text:
            try:
                set_clipboard(old_clip)
            except Exception:
                pass
