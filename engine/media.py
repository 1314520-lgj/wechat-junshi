"""Bounded, memory-only media crops. No screenshots or credentials in exports."""
from collections import OrderedDict
import base64
import hashlib
import io
import threading
from PIL import Image

_lock=threading.RLock()
_crops=OrderedDict()
_descriptions=OrderedDict()

def remember(frame,rect):
    x0,y0,x1,y1=map(int,rect)
    crop=frame[max(0,y0):min(frame.shape[0],y1),max(0,x0):min(frame.shape[1],x1)]
    if crop.size==0:return None
    image=Image.fromarray(crop)
    # Evidence identity precedes lossy compression/downscaling. Include shape
    # and mode so different crops cannot share a pixel byte stream identity.
    proof=repr((image.mode,image.size)).encode('ascii')+b'\0'+image.tobytes()
    key=hashlib.sha256(proof).hexdigest()[:24]
    image.thumbnail((1024,1024))
    if image.mode not in ('RGB','L'):
        image = image.convert('RGB')
    buf=io.BytesIO();image.save(buf,format='JPEG',quality=85)
    raw=buf.getvalue()
    with _lock:
        _crops[key]=base64.b64encode(raw).decode('ascii');_crops.move_to_end(key)
        while len(_crops)>256:_crops.popitem(last=False)
    return key

def get(key):
    with _lock:return _crops.get(key)

def description(key,provider):
    with _lock:return _descriptions.get((key,provider))

def save_description(key,provider,value):
    with _lock:
        _descriptions[(key,provider)]=value
        while len(_descriptions)>512:_descriptions.popitem(last=False)
