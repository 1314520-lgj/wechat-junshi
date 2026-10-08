"""OCR 新特性离线自测：时间识别 + 表情包识别 + 2x 提速（合成帧，不碰真实微信）。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

from chatapps import WECHAT
from ocr import Reader, find_stickers, is_time_text

# 合成一张消息区：面板底色 #EDEDED，中间灰字时间，右侧绿气泡，左侧白气泡，右下角彩色表情包块
H, W = 600, 900
pane = np.array([237, 237, 237], dtype=np.uint8)
chat = np.full((H, W, 3), pane, dtype=np.uint8)

# 灰色时间戳（居中）："下午 3:24"
def draw_text(img, x, y, text, size=24, color=(120, 120, 120), thick=3):
    from PIL import Image, ImageDraw
    pil = Image.fromarray(img)
    d = ImageDraw.Draw(pil)
    # 用默认字体画（无字体依赖，直接用矩形模拟不精确——这里用文字渲染）
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)
        d.text((x, y), text, font=font, fill=color)
    except Exception:
        d.text((x, y), text, fill=color)
    return np.array(pil, copy=True)

chat = draw_text(chat, 380, 20, "下午 3:24")

# 对方白气泡 + 深色字
chat[100:160, 40:360] = (255, 255, 255)
chat = draw_text(chat, 60, 115, "晚上一起吃饭吗", size=26, color=(20, 20, 20))

# 我方绿气泡 + 深色字
chat[200:260, 520:840] = (149, 236, 105)
chat = draw_text(chat, 540, 215, "好呀 几点", size=26, color=(20, 20, 20))

# 表情包：一个彩色渐变块（无文字），靠左
blob = np.zeros((120, 120, 3), dtype=np.uint8)
for i in range(120):
    blob[i, :, 0] = np.linspace(255, 60, 120).astype(np.uint8)
    blob[i, :, 1] = np.linspace(60, 255, 120).astype(np.uint8)
    blob[i, :, 2] = np.linspace(120, 90, 120).astype(np.uint8)
chat[340:460, 60:180] = blob

r = Reader(WECHAT)
lines = r.read(chat, pane)
print("OCR_MS", r.last_ms)
for ln in lines:
    print("LINE", ln)
assert is_time_text("下午 3:24") and is_time_text("昨天 22:10") and is_time_text("10-05")
assert not is_time_text("你好呀")
found = [l for l in lines if l[5] == "media_unknown"]
print("UNKNOWN_MEDIA", found)
assert len(found) >= 1, "彩色块应识别为未知媒体，不能猜成表情包"
texts = {l[2] for l in lines}
assert "晚上一起吃饭吗" in texts, "应识别出对方消息"
assert any("好呀" in t for t in texts), "应识别出我方消息"
assert all(l[5]=='text' for l in lines if l[0]=='me'), '绿气泡普通文字不能误判为媒体'
timed = [l for l in lines if l[4]]
print("TIMED", timed)
assert any(l[4] == "下午3:24" for l in lines), "时间戳应挂到消息上"
print("OCR_SELFTEST_OK")
