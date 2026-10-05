# -*- coding: utf-8 -*-
"""ctypes.wintypes 缺的 Win32 结构与 GDI 声明（64 位安全：句柄/指针全部显式声明）。"""
import ctypes
from ctypes import wintypes as w

UINT = w.UINT
BOOL = w.BOOL
DWORD = w.DWORD
HDC = w.HDC
HWND = w.HWND
HINSTANCE = w.HINSTANCE
HANDLE = w.HANDLE
HICON = getattr(w, "HICON", w.HANDLE)
HCURSOR = HANDLE
HBRUSH = HANDLE
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t
LPWSTR = ctypes.c_wchar_p
LPVOID = ctypes.c_void_p

POINT = w.POINT
SIZE = w.SIZE
RECT = w.RECT

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", HBRUSH),
        ("lpszMenuName", LPWSTR),
        ("lpszClassName", LPWSTR),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", w.WORD),
        ("biBitCount", w.WORD),
        ("biCompression", DWORD),
        ("biSizeImage", DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", DWORD),
        ("biClrImportant", DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


def declare():
    """设置 GDI/user32 常用函数的 restype/argtypes，防止 64 位句柄截断。"""
    u32, k32, gdi = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.gdi32
    k32.GetModuleHandleW.restype = HINSTANCE
    k32.GetModuleHandleW.argtypes = [LPVOID]
    k32.OpenProcess.restype = HANDLE
    k32.OpenProcess.argtypes = [DWORD, BOOL, DWORD]
    k32.QueryFullProcessImageNameW.restype = BOOL
    k32.QueryFullProcessImageNameW.argtypes = [HANDLE, DWORD, LPWSTR, ctypes.POINTER(DWORD)]
    k32.CloseHandle.restype = BOOL
    k32.CloseHandle.argtypes = [HANDLE]
    gdi.CreateCompatibleDC.restype = HDC
    gdi.CreateCompatibleDC.argtypes = [HDC]
    gdi.CreateCompatibleBitmap.restype = HANDLE
    gdi.CreateCompatibleBitmap.argtypes = [HDC, ctypes.c_int, ctypes.c_int]
    gdi.SelectObject.restype = HANDLE
    gdi.SelectObject.argtypes = [HDC, HANDLE]
    gdi.DeleteObject.restype = BOOL
    gdi.DeleteObject.argtypes = [HANDLE]
    gdi.DeleteDC.restype = BOOL
    gdi.DeleteDC.argtypes = [HDC]
    gdi.GetDIBits.restype = ctypes.c_int
    gdi.GetDIBits.argtypes = [HDC, HANDLE, UINT, UINT, LPVOID,
                              ctypes.POINTER(BITMAPINFO), UINT]
    gdi.CreateDIBSection.restype = HANDLE
    gdi.CreateDIBSection.argtypes = [HDC, ctypes.POINTER(BITMAPINFO), UINT,
                                     ctypes.POINTER(LPVOID), HANDLE, DWORD]
    gdi.CreateFontW.restype = HANDLE
    gdi.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD,
                                DWORD, DWORD, LPWSTR]
    gdi.SetBkMode.restype = ctypes.c_int
    gdi.SetBkMode.argtypes = [HDC, ctypes.c_int]
    gdi.SetTextColor.restype = ctypes.c_ulong
    gdi.SetTextColor.argtypes = [HDC, ctypes.c_ulong]
    u32.DrawTextW.restype = ctypes.c_int
    u32.DrawTextW.argtypes = [HDC, LPWSTR, ctypes.c_int, ctypes.POINTER(RECT), UINT]
    u32.GetDC.restype = HDC
    u32.GetDC.argtypes = [HWND]
    u32.ReleaseDC.restype = ctypes.c_int
    u32.ReleaseDC.argtypes = [HWND, HDC]
    u32.GetWindowDC.restype = HDC
    u32.GetWindowDC.argtypes = [HWND]
    u32.PrintWindow.restype = BOOL
    u32.PrintWindow.argtypes = [HWND, HDC, UINT]
    u32.UpdateLayeredWindow.restype = BOOL
    u32.UpdateLayeredWindow.argtypes = [HWND, HDC, ctypes.POINTER(POINT),
                                        ctypes.POINTER(SIZE), HDC, ctypes.POINTER(POINT),
                                        ctypes.c_ulong, ctypes.POINTER(BLENDFUNCTION), DWORD]
    u32.RegisterClassW.restype = w.ATOM
    u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    u32.CreateWindowExW.restype = HWND
    u32.CreateWindowExW.argtypes = [DWORD, LPWSTR, LPWSTR, DWORD, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, HWND, HANDLE, HINSTANCE, LPVOID]
    u32.DefWindowProcW.restype = LRESULT
    u32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
    u32.SetWindowPos.restype = BOOL
    u32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, UINT]
    u32.ShowWindow.restype = BOOL
    u32.ShowWindow.argtypes = [HWND, ctypes.c_int]
    u32.DestroyWindow.restype = BOOL
    u32.DestroyWindow.argtypes = [HWND]
    u32.MonitorFromPoint.restype = HANDLE
    u32.MonitorFromPoint.argtypes = [POINT, DWORD]
    ctypes.windll.shcore.GetDpiForMonitor.restype = ctypes.c_long
    ctypes.windll.shcore.GetDpiForMonitor.argtypes = [HANDLE, ctypes.c_int,
                                                      ctypes.POINTER(UINT), ctypes.POINTER(UINT)]
