"""OCR/读取时微信窗口边缘的黄色提示框：置顶、穿透点击、不抢焦点。

分层窗口逐像素 alpha：一圈黄色圆角描边（呼吸光晕 + 流动虚线），中间完全透明，
顶部中缝一个「军师 · 正在读取」小徽标（GDI 画字）。点击全部穿透（WS_EX_TRANSPARENT），
不进任务栏（WS_EX_TOOLWINDOW）、不激活（WS_EX_NOACTIVATE）。
"""
import ctypes
import math
import threading
import time

import numpy as np

import winstruct as ws
from winstruct import (BITMAPINFO, BLENDFUNCTION, POINT, RECT, SIZE, UINT, WNDCLASSW, WNDPROC)

ws.declare()
u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32


def _diag(where, exc):
    """记录「降级但可继续」的失败；日志本身失败不得影响调用方。"""
    try:
        import junshi
        junshi.flog(f'{where}: {type(exc).__name__}: {exc}')
    except Exception:
        pass

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
DIB_RGB_COLORS = 0

YELLOW = (255, 204, 0)
PAD = 8
BORDER = 3
R = 16
FPS = 6


def _dpi_scale_of(rect):
    """所在显示器的缩放（物理像素 → 虚拟坐标 的除数）。进程是 system-DPI aware。"""
    try:
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        mon = u32.MonitorFromPoint(POINT(cx, cy), 2)
        dx, dy = UINT(), UINT()
        ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy))
        return max(1.0, dx.value / 96.0), max(1.0, dy.value / 96.0)
    except Exception:
        return 1.0, 1.0


@WNDPROC
def _wndproc(hwnd, msg, wp, lp):
    return u32.DefWindowProcW(hwnd, msg, wp, lp)


class YellowBorder:
    def __init__(self, label="军师 · 正在读取"):
        self.label = label
        self._visible = False
        self._rect = None
        self._size = (0, 0)
        self._phase = 0.0
        self._run = True
        self._last_paint_diag = 0.0  # 绘制失败日志的节流时间戳
        self._hinst = k32.GetModuleHandleW(None)
        cls = WNDCLASSW(
            style=0,
            lpfnWndProc=_wndproc,
            hInstance=self._hinst,
            lpszClassName="DshJunshiYellowBorder",
        )
        atom = u32.RegisterClassW(ctypes.byref(cls))
        if not atom:
            raise RuntimeError("RegisterClassW 失败")
        self._hwnd = u32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
            "DshJunshiYellowBorder", "dsh-junshi-border", WS_POPUP,
            0, 0, 10, 10, None, None, self._hinst, None)
        if not self._hwnd:
            raise RuntimeError("CreateWindowExW 失败")
        self._font = gdi.CreateFontW(
            -14, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0, "Microsoft YaHei UI")
        self._t = threading.Thread(target=self._anim, daemon=True)
        self._t.start()

    def update_rect(self, rect):
        self._rect = tuple(rect)
        if self._visible:
            self._place()

    def show(self):
        self._visible = True
        if self._rect:
            self._place()

    def hide(self):
        self._visible = False
        try:
            u32.ShowWindow(self._hwnd, 0)
        except Exception as exc:
            _diag('Border.hide', exc)

    def dispose(self):
        # 不跨线程 DestroyWindow（会 SendMessage 死锁）：窗口随进程退出由系统回收。
        # 字体是 GDI 对象，任何线程都能安全释放，避免重复创建实例时累积句柄。
        self._run = False
        self.hide()
        try:
            if getattr(self, "_font", None):
                gdi.DeleteObject(self._font)
                self._font = None
        except Exception as exc:
            # GDI 对象没删掉就是句柄泄漏（每实例 1 个）。
            _diag('Border.dispose: DeleteObject(font)', exc)

    def _place(self):
        l, t, r, b = self._rect
        sx, sy = _dpi_scale_of(self._rect)
        vl = int(round((l - PAD) / sx))
        vt = int(round((t - PAD) / sy))
        vw = max(20, int(round((r - l + 2 * PAD) / sx)))
        vh = max(20, int(round((b - t + 2 * PAD) / sy)))
        # 不带 SWP_SHOWWINDOW：可见性由 UpdateLayeredWindow 承担，避免跨线程 SendMessage 死锁
        u32.SetWindowPos(self._hwnd, HWND_TOPMOST, vl, vt, vw, vh, SWP_NOACTIVATE)
        self._size = (vw, vh)

    def _anim(self):
        while self._run:
            if self._visible and self._size[0] >= 20:
                try:
                    self._paint()
                except Exception as exc:
                    # 绘制失败表现为「提示框不出现」，用户只会以为功能坏了。
                    # 逐帧重试但每帧都留痕会刷爆日志，故按 5 秒节流记录。
                    now = time.monotonic()
                    if now - self._last_paint_diag > 5.0:
                        self._last_paint_diag = now
                        _diag('Border._anim: _paint failed', exc)
            time.sleep(1.0 / FPS)

    def _paint(self):
        wpx, hpx = self._size
        self._phase = (self._phase + 0.18) % (2 * math.pi)
        bmp = np.zeros((hpx, wpx, 4), dtype=np.uint8)

        yy, xx = np.mgrid[0:hpx, 0:wpx]
        d = np.minimum(np.minimum(xx, wpx - 1 - xx), np.minimum(yy, hpx - 1 - yy)).astype(np.int32)
        corner = R
        cxx = np.minimum(np.minimum(xx, wpx - 1 - xx), corner).astype(np.int32)
        cyy = np.minimum(np.minimum(yy, hpx - 1 - yy), corner).astype(np.int32)
        in_corner = (xx < corner) | (xx > wpx - 1 - corner) | (yy < corner) | (yy > hpx - 1 - corner)
        corner_d = (cxx - corner) ** 2 + (cyy - corner) ** 2

        pulse = 0.72 + 0.28 * math.sin(self._phase)
        for off, alpha in ((5, 30), (4, 55), (3, 90), (2, 150), (1, 200), (0, 255)):
            m = (d >= off) & (d < off + BORDER)
            m &= ~(in_corner & (corner_d > (corner - off) ** 2 + 0.01))
            a = int(alpha * (pulse if off >= 1 else 1.0))
            bmp[m, 0], bmp[m, 1], bmp[m, 2], bmp[m, 3] = YELLOW[0], YELLOW[1], YELLOW[2], a

        core = (d >= BORDER - 1) & (d < BORDER + 1)
        core &= ~(in_corner & (corner_d > (corner - 1) ** 2 + 0.01))
        along = np.maximum(np.abs(xx.astype(np.int64) * 2 - wpx), np.abs(yy.astype(np.int64) * 2 - hpx))
        phase = int(self._phase * 90) % 110
        gap = ((along + phase) % 110) < 46
        bmp[core & gap, 3] = 0

        badge = self._badge(bmp)
        self._blit(bmp, badge)

    def _badge(self, bmp):
        hpx, wpx = bmp.shape[:2]
        text = self.label
        tw = sum(14 if ord(c) > 127 else 8 for c in text)
        bw, bh = tw + 22, 24
        if wpx < bw + 8:
            return None
        x0, y0 = (wpx - bw) // 2, 0
        bmp[y0:y0 + bh, x0:x0 + bw, 0] = YELLOW[0]
        bmp[y0:y0 + bh, x0:x0 + bw, 1] = YELLOW[1]
        bmp[y0:y0 + bh, x0:x0 + bw, 2] = YELLOW[2]
        bmp[y0:y0 + bh, x0:x0 + bw, 3] = 235
        bmp[y0 + bh - 1, x0:x0 + bw, 3] = 120
        bmp[y0 + bh - 2, x0:x0 + bw, 3] = 200
        return (x0, y0, bw, bh, text)

    def _blit(self, bmp, badge):
        wpx, hpx = self._size
        hdc = u32.GetDC(None)
        mem = gdi.CreateCompatibleDC(hdc)
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFO().bmiHeader)
        bi.bmiHeader.biWidth = wpx
        bi.bmiHeader.biHeight = -hpx
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = 0
        bits = ctypes.c_void_p()
        hbmp = gdi.CreateDIBSection(hdc, ctypes.byref(bi), DIB_RGB_COLORS,
                                    ctypes.byref(bits), None, 0)
        if not hbmp:
            gdi.DeleteDC(mem)
            u32.ReleaseDC(None, hdc)
            return
        old = gdi.SelectObject(mem, hbmp)
        ctypes.memmove(bits, bmp.ctypes.data, bmp.nbytes)
        if badge:
            x0, y0, bw, bh, text = badge
            gdi.SetBkMode(mem, 1)
            gdi.SetTextColor(mem, 0x00331C00)
            gdi.SelectObject(mem, self._font)
            rc = RECT(x0 + 10, y0 + 2, x0 + bw - 8, y0 + bh - 2)
            u32.DrawTextW(mem, text, -1, ctypes.byref(rc), 0x25)
        pt = POINT(0, 0)
        sz = SIZE(wpx, hpx)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        u32.UpdateLayeredWindow(self._hwnd, hdc, None, ctypes.byref(sz), mem,
                                ctypes.byref(pt), 0, ctypes.byref(blend), ULW_ALPHA)
        gdi.SelectObject(mem, old)
        gdi.DeleteObject(hbmp)
        gdi.DeleteDC(mem)
        u32.ReleaseDC(None, hdc)


if __name__ == "__main__":
    b = YellowBorder("军师 · 正在读取")
    b.update_rect((200, 100, 1000, 700))
    b.show()
    time.sleep(4)
    b.dispose()
    print("border ok")
