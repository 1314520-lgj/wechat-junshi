"""找微信窗口 + 采集帧 + 从帧里定位消息区。基于 JevChat-Windows（MIT）二次开发。

主路：Windows Graphics Capture（被遮挡也能截 GPU 合成窗口）。
备路：PrintWindow + PW_RENDERFULLCONTENT 轮询（WGC 起不来时兜底）。
帧全程内存，绝不落盘。
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes

import numpy as np

import winstruct as ws
from winstruct import BITMAPINFO

from chatapps import APPS, by_exe

ws.declare()
u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
gdi = ctypes.windll.gdi32


def _diag(where, exc):
    """记录一次「降级但可继续」的失败。

    采集链路里有若干刻意的最佳努力分支（DWM 取不到就用旧 API、
    WGC 起不来就退 PrintWindow）。这些降级会让画面质量或裁切精度
    悄悄变化，必须在日志里留一条痕迹，否则只有肉眼能发现。
    """
    try:
        import junshi
        junshi.flog(f'{where}: {type(exc).__name__}: {exc}')
    except Exception:
        pass


def exe_of(pid: int) -> str:
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    buf, size = ctypes.create_unicode_buffer(1024), ctypes.c_uint(1024)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    k32.CloseHandle(h)
    return os.path.basename(buf.value).lower() if ok else ""


def find_chat_hwnd():
    """枚举可见顶层窗口，按进程名认出微信，返回 (hwnd, ChatApp) 或 (None, None)。"""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = by_exe(exe_of(pid.value))
        if app:
            title = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, title, 256)
            rect = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(rect))
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            found.append((hwnd, title.value, area, app))
        return True

    u32.EnumWindows(cb, 0)
    if not found:
        return None, None
    for app in APPS.values():
        mine = [f for f in found if f[3] is app]
        if not mine:
            continue
        if app.main_title:
            hit = next((f for f in mine if f[1] == app.main_title), None)
            if hit:
                return hit[0], app
        rooms = [f for f in mine if f[1] not in app.skip_titles] or mine
        best = max(rooms, key=lambda f: f[2])
        return best[0], app
    return None, None


def window_rect(hwnd):
    """扩展边界（物理像素，跟采集帧对齐）。失败退回 GetWindowRect。"""
    r = wintypes.RECT()
    try:
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) == 0:
            return int(r.left), int(r.top), int(r.right), int(r.bottom)
    except Exception as exc:
        # 退回 GetWindowRect 时窗口含不可见边框，裁出来的聊天区会偏一点。
        # 这个偏差会一路传到 OCR 截图，所以必须能被追溯。
        _diag(f'window_rect: DwmGetWindowAttribute failed, falling back ({hwnd=})', exc)
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return int(r.left), int(r.top), int(r.right), int(r.bottom)


def unminimize(hwnd):
    """最小化时无激活还原并压到最底：不抢焦点、不遮挡。"""
    if not u32.IsIconic(hwnd):
        return False
    u32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    u32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x13)  # HWND_BOTTOM, NOSIZE|NOMOVE|NOACTIVATE
    return True


def chat_area(full, header_h=60):
    """消息列表区 (x0, y_top, x1, y_in, 面板底色, y_pane)，全靠像素锚点，不写死坐标，深浅主题通用。
    认不出返回 None。"""
    H, W = full.shape[:2]
    right = full[::8, W // 2::8].reshape(-1, 3)
    if right.size == 0:
        return None
    vals, cnt = np.unique(right, axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    isbg = np.abs(full.astype(np.int16) - bg.astype(np.int16)).sum(-1) <= 6
    col = isbg[H // 4: H * 3 // 4].mean(0)
    # Dark mode's left navigation can share the chat background. Select one
    # continuous right-side panel, never span the sidebar between two matches.
    edges=np.diff(np.pad((col>.3).astype(np.int8),(1,1)))
    runs=[(int(a),int(b)) for a,b in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)) if b-a>=100 and b>W*.65]
    if not runs:return None
    x0,x1=max(runs,key=lambda r:r[1]-r[0])
    # Tall image/card bubbles can split the body's background columns and make
    # the largest run start AFTER the messages. Use the unobstructed title band
    # to recover the pane boundary; the sidebar remains a different background.
    header_col = isbg[:max(1, H // 10)].mean(0)
    header_edges = np.diff(np.pad((header_col > .3).astype(np.int8), (1, 1)))
    header_runs = [(int(a), int(b)) for a, b in zip(np.flatnonzero(header_edges == 1), np.flatnonzero(header_edges == -1))
                   if b - a >= 100 and b > W * .8 and W * .08 < a < W * .7]
    if header_runs:
        hx0, hx1 = max(header_runs, key=lambda r:r[1]-r[0])
        if hx0 < x0 and hx1 >= x1 - 8:
            x0, x1 = hx0, hx1
    row = isbg[:, x0:x1].mean(1)
    y0 = int(np.argmax(row > 0.9))
    y1 = H - int(np.argmax(row[::-1] > 0.9))
    # A thin right-side background strip is not a reliable conversation pane.
    # Reject it rather than turn cropped fragments into fabricated messages.
    if x1 - x0 < max(100, W * .2) or y1 - y0 < 100:
        return None
    band = full[y0:y1, x0:x1].astype(np.int16)
    seps = y0 + np.where((band.std(axis=(1, 2)) < 4) & (row[y0:y1] < 0.1))[0]
    seps = [int(s) for i, s in enumerate(seps) if i == 0 or s - seps[i - 1] > 3]
    below = [s for s in seps if s > y0 + 0.45 * (y1 - y0)]
    # Web/search panes can mimic the chat background. Without an independent
    # input-area boundary, their cards must never become observed messages.
    if not below:
        return None
    y_in = below[0]
    # A mid-page card separator is not the bottom chat composer. Unusual
    # layouts remain unsupported rather than silently accepting web cards.
    if y_in < H * .70 or H - y_in < 35:
        return None
    above = [s for s in seps if y0 + header_h < s < y_in - 50]
    y_top = above[-1] if above else y0 + header_h
    if x1 - x0 < 100 or y_in - y_top < 40:
        return None
    return x0, y_top, x1, y_in, bg, y0


class _Settler:
    """采集线程只做「跟上一帧比」；settled() 在画面停稳后交出整帧，中间帧全跳过。

    WGC 回调线程与主循环线程并发访问 pending/area，全部状态迁移用锁保护；
    定位搜索（chat_area）按帧内容去重 + 时间节流，画面不变时不再重跑。"""

    def __init__(self, settle=0.25, max_wait=1.0):
        self.settle, self.max_wait = settle, max_wait
        self.area = self.last = self.pending = None
        self.t = self.t0 = 0.0
        self._layout_header=None
        self.pending_at = self.last_settled_at = None
        self._recheck_at = None
        self._lock = threading.Lock()
        self._last_search_frame = None
        self._last_search_at = None

    def request_recheck(self, delay=2):
        """Retry unreadable metadata once, using a later received frame only."""
        with self._lock:
            deadline = time.perf_counter() + delay
            if self._recheck_at is None or deadline < self._recheck_at:
                self._recheck_at = deadline

    def on_frame(self, full):
        if full is None or full.max() == 0:
            return
        with self._lock:
            # Observe the whole header: split panes can move the chat without
            # changing dimensions, while the former right-side web pane stays still.
            header=full[:max(1,min(100,full.shape[0]//8)):4,::8]
            layout_changed=self._layout_header is not None and (header.shape!=self._layout_header.shape or not np.array_equal(header,self._layout_header))
            self._layout_header=header.copy()
            if layout_changed:
                self.area=None;self.last=None
            if self.area is None or full.shape != getattr(self, "shape", None):
                self.shape = full.shape
                now_p = time.perf_counter()
                unchanged = (self._last_search_frame is not None
                             and full.shape == self._last_search_frame.shape
                             and np.array_equal(full, self._last_search_frame))
                throttled = (not unchanged and self._last_search_at is not None
                             and now_p - self._last_search_at < 0.5)
                if unchanged or throttled:
                    # 画面没变或刚找过：只换 pending，不重跑像素分析。
                    if self.pending is None:self.t0=now_p
                    self.pending,self.t=full,now_p
                    self.pending_at=time.time()
                    return
                self._last_search_frame = full.copy()
                self._last_search_at = now_p
                self.area = chat_area(full)
                self.last = None
            if self.area is None:
                if self.pending is None:self.t0=time.perf_counter()
                self.pending,self.t=full,time.perf_counter()
                self.pending_at=time.time()
                self._recheck_at=None
                return
            x0, y0, x1, y1 = self.area[:4]
            # A title change must reach the main loop even when both chats have
            # identical visible bubbles. Keep drafts outside the observed region.
            y_pane = self.area[5] if len(self.area) > 5 else 0
            chat = full[y_pane:y1, x0:x1]
            if self._recheck_at is not None and time.perf_counter() >= self._recheck_at:
                self.last = None
            if self.last is not None and np.array_equal(chat, self.last):
                return
            self.last = chat.copy()
            if self.pending is None:
                self.t0 = time.perf_counter()
            self.pending, self.t = full, time.perf_counter()
            self.pending_at=time.time()
            self._recheck_at=None

    def settled(self):
        with self._lock:
            if self.pending is None:
                return None
            now = time.perf_counter()
            if now - self.t < self.settle and now - self.t0 < self.max_wait:
                return None
            full = self.pending
            self.pending = None
            self.last_settled_at=self.pending_at
            self.pending_at=None
            return full


class Capture(_Settler):
    """WGC 盯窗口。事件回调名必须是 on_frame_arrived / on_closed（windows-capture 按名字分派）。"""

    def __init__(self, hwnd, settle=0.25, max_wait=1.0):
        super().__init__(settle, max_wait)
        from windows_capture import WindowsCapture
        cap = WindowsCapture(cursor_capture=None, draw_border=False,
                             minimum_update_interval=100, window_hwnd=int(hwnd))
        cap.event(self.on_frame_arrived)
        cap.event(self.on_closed)
        self.ctl = cap.start_free_threaded()
        self._closed = False

    def on_frame_arrived(self, frame, control):
        try:
            full = np.ascontiguousarray(frame.frame_buffer[:, :, :3][:, :, ::-1])  # BGRA→RGB
            self.on_frame(full)
        except Exception:
            # 原生回调里不允许异常逃逸：ctypes 只会打印后吞掉并丢帧，
            # 还会让 _Settler 状态停在半路。这里计数后继续等下一帧。
            self._frame_errors = getattr(self, "_frame_errors", 0) + 1

    def on_closed(self):
        self._closed = True

    def alive(self):
        return (not self._closed) and (not self.ctl.is_finished())

    def stop(self):
        try:
            self.ctl.stop()
        except Exception:
            pass

    def wait(self):
        try:
            self.ctl.wait()
        except Exception:
            pass


class PrintCapture(_Settler):
    """PrintWindow + PW_RENDERFULLCONTENT 轮询兜底（每帧带超时，防微信线程不响应卡死）。"""

    def __init__(self, hwnd, settle=0.25, max_wait=1.0, interval=0.3):
        super().__init__(settle, max_wait)
        self.hwnd = hwnd
        self.interval = interval
        self._run = True
        self._backoff = 0
        import threading
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _grab(self):
        rect = window_rect(self.hwnd)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w <= 0 or h <= 0:
            return None
        hdc_win = u32.GetWindowDC(self.hwnd)
        if not hdc_win:
            return None
        hdc = gdi.CreateCompatibleDC(hdc_win)
        hbmp = gdi.CreateCompatibleBitmap(hdc_win, w, h)
        u32.ReleaseDC(self.hwnd, hdc_win)
        if not hdc or not hbmp:
            # 一个成功一个失败时必须各自释放，否则 GDI 句柄逐帧泄漏。
            if hbmp: gdi.DeleteObject(hbmp)
            if hdc: gdi.DeleteDC(hdc)
            return None
        old = None
        try:
            old = gdi.SelectObject(hdc, hbmp)
            if not old or old == ctypes.c_void_p(-1).value:
                return None
            flags = 2 | 0x10  # PW_RENDERFULLCONTENT | PW_CLIENTONLY
            if not u32.PrintWindow(self.hwnd, hdc, flags):
                return None
            bi = BITMAPINFO()
            bi.bmiHeader.biSize = ctypes.sizeof(bi.bmiHeader)
            bi.bmiHeader.biWidth = w
            bi.bmiHeader.biHeight = -h
            bi.bmiHeader.biPlanes = 1
            bi.bmiHeader.biBitCount = 32
            bi.bmiHeader.biCompression = 0
            buf = np.empty((h, w, 4), dtype=np.uint8)
            got = gdi.GetDIBits(hdc, hbmp, 0, h,
                                buf.ctypes.data, ctypes.byref(bi), 0)
            if not got:
                return None
            return np.ascontiguousarray(buf[:, :, :3][:, :, ::-1])
        finally:
            # 位图仍选中在 DC 里时 DeleteObject 必然失败：先换回旧对象再删，
            # 否则每次 _grab 泄漏一张位图，几十分钟内耗尽 GDI 句柄。
            if old and old != ctypes.c_void_p(-1).value:
                gdi.SelectObject(hdc, old)
            gdi.DeleteObject(hbmp)
            gdi.DeleteDC(hdc)

    def _grab_guarded(self, timeout=2.5):
        """A blocked native call keeps one slot; repeated polls never spawn more."""
        from capturejobs import run
        return run(int(self.hwnd),self._grab,timeout)

    def _loop(self):
        unchanged_streak = 0
        while self._run:
            if self._backoff > 0:
                time.sleep(self._backoff)
                self._backoff = 0
                continue
            try:
                full = self._grab_guarded()
                if full is None:
                    self._backoff = 5
                else:
                    prev = getattr(self, "_prev_frame", None)
                    same = prev is not None and full.shape == prev.shape and np.array_equal(full, prev)
                    self._prev_frame = full
                    unchanged_streak = unchanged_streak + 1 if same else 0
                self.on_frame(full)
            except Exception:
                self._backoff = 5
            # 画面长时间没变化时降频，避免兜底模式整天 3.3fps 整窗强制重绘。
            time.sleep(1.0 if unchanged_streak >= 10 else self.interval)

    def alive(self):
        return self._run

    def stop(self):
        self._run = False

    def wait(self):
        pass


def make_capture(hwnd, prefer_wgc=True):
    """起 WGC，失败退回 PrintWindow。"""
    if prefer_wgc:
        try:
            return Capture(hwnd), "wgc"
        except Exception as exc:
            # 退回 PrintWindow 会丢掉「窗口被遮挡也能采到」的能力，属于显著降级。
            _diag(f'make_capture: WGC unavailable, falling back to PrintWindow ({hwnd=})', exc)
    return PrintCapture(hwnd), "printwindow"
