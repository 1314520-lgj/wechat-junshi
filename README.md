# 军师 wechat-junshi

[![CI](https://github.com/1314520-lgj/wechat-junshi/actions/workflows/ci.yml/badge.svg)](https://github.com/1314520-lgj/wechat-junshi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](requirements.txt)
[![Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4.svg)](#运行)

军师是一个运行在 Windows 上的微信聊天辅助应用：它**只读**地观察当前可见的微信会话，理解文字与各类媒体内容，结合语境起草并核验候选回复，由你本人确认后填入微信输入框——**它不发送任何消息**，发送永远由你手动完成。

> 这不是自动回复机器人。军师的目标是：看清上下文、说像你的话、把选择权留给你。

当前版本：**1.5.70**。保留窗口自适应排版，改进人物归属缓存、红包/转账与入口操作的事实核验、旧建议失效和填入失败提示。详见 [1.5.70 使用与验证说明](docs/1.5.70.md)。

## 功能

- **自适应界面**：支持连续调整窗口大小、浅深色主题和大字模式；已编辑的回复与粘贴内容保持不变，缩放不触发新分析。
- **屏幕读取**：Windows Graphics Capture 抓取微信窗口，RapidOCR 识别消息文字，消息区域靠像素锚点自适应定位（深浅色主题、窗口尺寸均可用）
- **媒体理解**：本地 Ollama 视觉模型（默认 `qwen3-vl:2b`）识别表情包、图片、红包/转账/公众号/小程序等卡片、引用、群公告、投票、接龙；语音与视频由你手动导入文件后转写/抽样（CPU Whisper，前 180 秒）
- **语境分析**：关系与口吻设置 → 语境判断 → 起草最多 3 条候选 → 事实核验 → 推荐排序；提示词注入防护、支付/进度承诺等事实边界检查
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

**从源码运行**（Windows 10/11 + Python 3.12）：

```powershell
git clone https://github.com/1314520-lgj/wechat-junshi.git
cd wechat-junshi
pip install -r requirements.txt
python -X utf8 launcher.py
```

设置：在面板设置里填入 DeepSeek API 密钥（DPAPI 加密保存）；媒体理解需安装 [Ollama](https://ollama.com) 并执行 `ollama pull qwen3-vl:2b`；可选 Harness 调度需要官方 `deepseek-harness-sdk==0.1.5rc1`（未发布到 PyPI），不装也能正常使用。

语音转写还需另备 `models/whisper-small/model.bin` 及对应模型文件；仅安装 Python 依赖不会提供这些权重。缺少模型时保持未知，不会编造转写。

桌面安装包内置 Python 3.12 运行时与全部依赖，但不随本仓库分发；本仓库是完整应用源码（开发包）。在已有安装上升级：先在军师设置中退出，备份安装目录（默认 `%LOCALAPPDATA%\Programs\Junshi`），再覆盖对应源码并启动 `launcher.py`；保留运行时、模型和用户数据。

> English README: [README.en.md](README.en.md)

## 界面验证

界面检查使用虚构会话与模拟服务，不连接微信或模型。需要 Node.js 20 及以上：

```powershell
npm install
npx playwright install chromium
npm run test:layout
npm run test:actions
python -m unittest discover -s tests -p "test_*scope.py"
```

测试覆盖窗口宽高、连续缩放、草稿保留、长设置滚动、抽屉操作、待采用建议失效、复制/填入失败及人物/卡片证据范围。Python 运行依赖不受界面测试依赖影响。

## 开发

**环境**：Windows 10/11 + **Python 3.12**（`rapidocr-onnxruntime==1.4.4` 声明
`Requires-Python >=3.6,<3.13`，在 3.13 上依赖解析会失败）+ Node.js ≥ 20（仅面板检查）。

```powershell
git clone https://github.com/1314520-lgj/wechat-junshi.git
cd wechat-junshi
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install              # 启用提交前钩子（只需一次）
```

**提交前检查**（与 CI 同策略，合并前请确保全绿）：

```powershell
pre-commit run --all-files      # 文件卫生 + ruff + pip-audit
ruff check .                    # 规则集与豁免理由见 pyproject.toml
python -m unittest discover -s tests -p "test_*.py"
```

CI 在每次 push / PR 上跑四个维度：Python 静态检查与离线单元测试、面板排版与交互
（Playwright）、提交前钩子同策略复核、依赖漏洞扫描（pip-audit）。本地钩子可以被
`--no-verify` 绕过，CI 不能——所以 CI 才是最终裁决者。

详细约定（工程风格、依赖策略、安全红线、PR 自查）见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全与隐私

- 引擎仅监听 `127.0.0.1`，排他端口绑定，要求实例令牌 + Host/Origin 校验，无 CORS
- 密钥与用户确认的记忆用 Windows DPAPI 加密；观察数据库未整体加密（保留 7 天、上限 2 万条）
- 云端模型只会收到参与分析的聊天文字；视觉默认在本机运行
- 应用没有发送端点；自动填入已移除；复制、手动填入保留
- 请勿把 `private-data-backup`、Harness 会话日志或任何 `.dpapi`/`.sqlite3` 数据文件提交到公开仓库

## 免责声明

本应用仅用于个人学习与辅助表达。使用前请确认符合微信相关条款、当地法律法规以及你所在群聊的知情边界；建议在启用读取前告知对方。发送行为始终由你本人决定。

## 许可证

[MIT](LICENSE) © 2026 wechat-junshi contributors。第三方组件保留各自许可证（见 `licenses/`）。

---

问题与建议请在 [Issues](https://github.com/1314520-lgj/wechat-junshi/issues) 提出，欢迎 PR 与 Star。
