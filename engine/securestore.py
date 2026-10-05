"""Windows DPAPI storage: bound to current Windows user; atomic writes."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path

class BLOB(ctypes.Structure):
    _fields_ = [('size', w.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def _crypt(data, decrypt=False):
    if os.name != 'nt':
        raise OSError('DPAPI requires Windows')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = (ctypes.c_ubyte * max(1,len(data)))()
    if data: ctypes.memmove(buf, data, len(data))
    source = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    result = BLOB()
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(BLOB),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(BLOB)]
        ok = fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(BLOB),w.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(BLOB)]
        ok = fn(ctypes.byref(source),'Junshi',None,None,None,1,ctypes.byref(result))
    if not ok: raise ctypes.WinError(ctypes.get_last_error())
    try: return ctypes.string_at(result.data,result.size)
    finally: kernel.LocalFree(ctypes.cast(result.data,ctypes.c_void_p))

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    payload=_crypt(json.dumps(value,ensure_ascii=False).encode('utf-8'))
    tmp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    try:
        tmp.write_bytes(payload);os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

def read_json(path):
    return json.loads(_crypt(Path(path).read_bytes(),decrypt=True).decode('utf-8'))
