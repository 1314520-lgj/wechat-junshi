"""新证据链自测：心理/意图/依据/适合度/危险度/建议动作 每项挂证据 + 更像人的候选。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import junshi  # 导入即读取 API_KEY，并把 stdout 重定向到日志文件
from engine import analyze, display_judgment

msgs = [
    {"from": "her", "text": "你昨天是不是又忘了给我带奶茶", "time": "昨天 18:02"},
    {"from": "me", "text": "啊我错了 真忘了"},
    {"from": "her", "text": "就知道你会忘 算了 今天补上吧"},
    {"from": "me", "text": "必须补 下班就买"},
    {"from": "her", "text": "这还差不多 我要芋泥波波三分糖", "time": "今天 09:40"},
]
result = analyze(msgs, "恋人", junshi.API_KEY, model="deepseek-flash",
                 judge_model="deepseek-chat", junshi_layer=True)
print("== 判断（每条挂证据）==")
for r in display_judgment(result["answers"]):
    ev = f"  依据：{r['evidence']}" if r.get("evidence") else ""
    print(f"- {r['label']}：{r['value']}{ev}")
print("== 适合度 + 推荐理由 ==")
for i, c in enumerate(result["candidates"]):
    print(f"{i+1}. [{round(result['scores'][i]*100)}%] {c}")
print("推荐理由：", result.get("best_reason"))
