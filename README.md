# 军师 wechat-junshi

军师是一个运行在 Windows 上的微信聊天辅助应用：它**只读**地观察当前可见的微信会话，理解文字与各类媒体内容，结合语境起草并核验候选回复，由你本人确认后填入微信输入框——**它不发送任何消息**，发送永远由你手动完成。

> 这不是自动回复机器人。军师的目标是：看清上下文、说像你的话、把选择权留给你。

## 功能

- **屏幕读取**：Windows Graphics Capture 抓取微信窗口，RapidOCR 识别消息文字，消息区域靠像素锚点自适应定位（深浅色主题、窗口尺寸均可用）
- **媒体理解**：本地 Ollama 视觉模型（默认 `qwen3-vl:2b`）识别表情包、图片、红包/转账/公众号/小程序等卡片、引用、群公告、投票、接龙；语音与视频由你手动导入文件后转写/抽样（CPU Whisper，前 180 秒）
- **语境分析**：关系与口吻设置 → 语境判断 → 起草 3 条候选 → 事实核验 → 推荐排序；提示词注入防护、支付/进度承诺等事实边界检查
- **长期记忆**：你手动确认的事实（DPAPI 加密保存）会参与后续判断与起草，模型推测绝不自动写入记忆
- **证据与更正**：读到的每条消息可查看截图原图证据并手动更正；群成员线索需你确认后才关联身份
- **模型协作**：可配置多个 OpenAI 兼容模型分担 起草/复核/判断/排序 职责，带调用次数、时间与估算费用上限
- **扩展（SDK）**：只读 `read_context` 权限的本地扩展，子进程故障隔离（非安全沙箱，只启用你审阅过的代码）
- **Harness 调度**：可选官方 DeepSeek Harness SDK 子进程调度，只挂载只读证据工具，关闭终端类工具

## 架构

```
launcher.py         托盘 + 单实例 + 健康探针与自动重启
engine/
  junshi.py         引擎主循环 / 本地 HTTP API（仅 127.0.0.1，token 鉴权）
  capture.py        WGC 采集 + 消息区定位（PrintWindow 兜底）
  ocr.py            RapidOCR 识别与行/气泡整理
  vision.py         本地视觉理解（Ollama / OpenAI 兼容）
  avmedia.py        语音转写与视频抽样
  engine.py         分析编排（判断→起草→核验→排序，逐级降级）
  draft.py  replycheck.py  content.py  questions.py
  evidence.py       观察证据库（SQLite，7 天/2 万条封顶）
  memory.py         加密长期记忆
  fill.py           填入微信输入框（只粘贴、绝不发送）
  modelrouter.py    多模型职责路由与预算
  harness_adapter.py  官方 DeepSeek Harness SDK 适配
lib/                Web 面板（host.js 为 DSH 插件宿主）
sdk/                扩展 SDK / MCP 桥 / 示例扩展
skills/             内置知识库（goutoujunshi）
docs/               使用说明、已知限制、开发文档、修复记录
licenses/           第三方组件许可
```

## 运行

本仓库是军师的**开发包**（引擎源码 + 面板 + SDK + 技能 + 文档）。桌面安装包内置 Python 3.12 运行时与第三方依赖（见 `DEPENDENCIES.json`）；在已有安装上更新：把本仓库内容覆盖到安装目录（默认 `%LOCALAPPDATA%\Programs\Junshi`），运行其中的 `launcher.py` 即可。

从头运行所需环境：Python 3.12、numpy、opencv、rapidocr-onnxruntime、windows-capture、Pillow、faster-whisper 等（版本见依赖目录 METADATA 或 `DEPENDENCIES.json`）；本地 Ollama 与 `qwen3-vl:2b`；DeepSeek API 密钥（在应用设置中填入，DPAPI 加密保存）。

## 安全与隐私

- 引擎仅监听 `127.0.0.1`，排他端口绑定，要求实例令牌 + Host/Origin 校验，无 CORS
- 密钥与用户确认的记忆用 Windows DPAPI 加密；观察数据库未整体加密（保留 7 天、上限 2 万条）
- 云端模型只会收到参与分析的聊天文字；视觉默认在本机运行
- 应用没有发送端点；自动填入因微信最新位置无法可靠验证而主动停用
- 请勿把 `private-data-backup`、Harness 会话日志或任何 `.dpapi`/`.sqlite3` 数据文件提交到公开仓库

## 免责声明

本应用仅用于个人学习与辅助表达。使用前请确认符合微信相关条款、当地法律法规以及你所在群聊的知情边界；建议在启用读取前告知对方。发送行为始终由你本人决定。
