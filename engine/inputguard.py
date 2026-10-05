"""Conservative automatic draft guard: foreground, idle, blank input, no send."""
import ctypes,time,re
import numpy as np
from ocr import _engine

class LASTINPUTINFO(ctypes.Structure):
    _fields_=[('cbSize',ctypes.c_uint),('dwTime',ctypes.c_uint)]

def idle_seconds():
    info=LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO),0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):return 0
    return ((ctypes.windll.kernel32.GetTickCount()-info.dwTime)&0xffffffff)/1000

def inspect_input(frame,area):
    x0,_,x1,y1=map(int,area[:4]);h,w=frame.shape[:2]
    toolbar_height=max(60,int(h*.075))
    crop=frame[y1+10:h-toolbar_height,x0+12:x1-12]
    if crop.shape[0]<35 or crop.shape[1]<100:return False,'无法可靠定位输入区'
    res,_=_engine()(crop,use_cls=False)
    allowed=('按住鼠标','语音输入','按住空格','输入消息','发送消息')
    placeholders={'按住说话','按住鼠标说话','按住鼠标语音输入文字','按住空格说话','输入消息','发送消息'}
    for box,text,_ in res or []:
        if not text.strip():continue
        normalized=re.sub(r'[\s，,。.!！：:]','',text)
        if normalized not in placeholders:return False,'输入框已有文字，保留你的草稿'
        # A user can type exactly the placeholder wording. Bright/contrasting
        # glyphs are a real draft; only low-contrast placeholder rendering passes.
        try:
            xs=[p[0] for p in box];ys=[p[1] for p in box]
            region=crop[max(0,int(min(ys))):min(crop.shape[0],int(max(ys))+1),max(0,int(min(xs))):min(crop.shape[1],int(max(xs))+1)].astype(float)
            pixels=region.reshape(-1,3);neutral=pixels[np.ptp(pixels,axis=1)<35]
            background=np.median(crop.reshape(-1,3),axis=0)
            if not len(neutral) or np.percentile(np.max(np.abs(neutral-background),axis=1),99.5)>90:return False,'输入框存在高对比文字，保留你的草稿'
        except (ValueError,TypeError,IndexError):return False,'无法核对输入框文字，保留你的草稿'
    # A nonuniform input may contain an attachment, mention tag or sticker.
    q=(crop[::2,::2].astype(int)//16).reshape(-1,3)
    _,counts=np.unique(q,axis=0,return_counts=True)
    if counts.max()/max(1,len(q))<.985:return False,'输入框可能已有内容，保留你的草稿'
    return True,'输入框为空'

def verify_ready(hwnd,frame,area,check_idle=True):
    if int(ctypes.windll.user32.GetForegroundWindow())!=int(hwnd):raise RuntimeError('微信不在前台，自动填入已跳过')
    if check_idle and idle_seconds()<2:raise RuntimeError('你正在操作，自动填入已跳过')
    ok,reason=inspect_input(frame,area)
    if not ok:raise RuntimeError(reason)

def last_input_tick():
    info=LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO),0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):raise RuntimeError('无法核对输入活动')
    return info.dwTime
