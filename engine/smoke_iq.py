# -*- coding: utf-8 -*-
"""升级后的智能链路自测：判断(deepseek-chat) + 记忆提取 + 排序看完整对话。"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import junshi  # noqa: F401  (读 API_KEY)
from memory import extract, load_memory  # noqa: E402

API_KEY = junshi.API_KEY
msgs = [
    {"from": "her", "text": "在吗，上次说好的周末爬山还去吗？"},
    {"from": "me", "text": "去啊，我周六早上有空"},
    {"from": "her", "text": "那你别忘了带充电宝，我上次手机没电了"},
    {"from": "me", "text": "记住了，这次一定带"},
    {"from": "her", "text": "对了，我妈下周过生日，我想买个按摩仪，你有什么推荐吗"},
]

print("== 记忆提取 ==")
got = extract("军师自测", msgs, API_KEY, "deepseek-flash", timeout=40)
mem = load_memory("军师自测")
print("FACTS", json.dumps(mem.get("facts"), ensure_ascii=False))
print("OPEN", json.dumps(mem.get("open_items"), ensure_ascii=False))
print("TONE", mem.get("emotion_tone"))

print("== 完整链路（judge=deepseek-chat）==")
req = urllib.request.Request(
    "http://127.0.0.1:19387/dsh-junshi/api/analyze-text",
    data=json.dumps({"messages": msgs, "relationship": "朋友"}).encode("utf-8"),
    method="POST", headers={"Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=120))
print("JUDGMENT", json.dumps(r.get("judgment"), ensure_ascii=False))
for i, c in enumerate(r.get("candidates") or []):
    print(f"CAND{i+1} [{round(r['scores'][i]*100)}%]", c)
