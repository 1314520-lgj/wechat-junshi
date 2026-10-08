# Junshi (wechat-junshi) — a read-only WeChat reply assistant for Windows

[![CI](https://github.com/1314520-lgj/wechat-junshi/actions/workflows/ci.yml/badge.svg)](https://github.com/1314520-lgj/wechat-junshi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](requirements.txt)
[![Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4.svg)](#running)

Junshi is a Windows desktop assistant that **observes** the currently visible WeChat conversation, understands text and rich media, drafts and fact-checks candidate replies in context, and lets **you** paste them into the input box. **It never sends anything** — sending is always your own action.

> Not an auto-reply bot. Junshi's goal: understand the context, sound like you, and leave the choice to you.

Current version: **1.5.70**. The interface adapts to window width and height, switches between columns and a stacked layout, keeps drafts while resizing, and keeps the settings close button reachable. See [release notes](docs/1.5.70.md) (Chinese).

## Highlights

- **Screen reading**: captures the WeChat window via Windows Graphics Capture (PrintWindow fallback) and recognizes message text with RapidOCR. The message area is located by pixel anchors — works across light/dark themes and window sizes.
- **Media understanding**: a local vision model (default `qwen3-vl:2b` via Ollama) classifies stickers, images, payment/red-packet/Official-Account/Mini-Program cards, quotes, group notices, polls and relays. Voice & video are transcribed/sampled from files you import (CPU Whisper, first 180 s).
- **Context-aware drafting**: relationship & tone settings → context judgment → 3 draft candidates → grounding/fact review → ranking. Includes prompt-injection defenses and fact-boundary checks (payments, progress promises, etc.).
- **Long-term memory**: facts you explicitly confirm (DPAPI-encrypted) shape future drafts; model guesses are never auto-saved as memory.
- **Evidence & correction**: every message keeps its screenshot crop as evidence and can be corrected by hand; group-member identities are linked only after your confirmation.
- **Model collaboration**: multiple OpenAI-compatible models can share drafting/review/judging/ranking roles, with per-analysis call-count, time and estimated-cost budgets.
- **Extension SDK**: local, read-only (`read_context`) extensions run in an isolated subprocess (a fault boundary, not a security sandbox).
- **Harness scheduling (optional)**: official DeepSeek Harness SDK subprocess with a single read-only evidence tool; terminal tools disabled.

## Architecture

```
launcher.py          tray icon, single instance, health probe & auto-restart
engine/
  junshi.py          main loop / local HTTP API (127.0.0.1 only, token auth)
  capture.py         WGC capture + message-area localization (PrintWindow fallback)
  ocr.py             RapidOCR recognition and row/bubble grouping
  vision.py          local vision understanding (Ollama / OpenAI-compatible)
  avmedia.py         speech transcription & video sampling
  engine.py          analysis pipeline (judge → draft → review → rank, graceful degradation)
  draft.py replycheck.py content.py questions.py
  evidence.py        observation store (SQLite, 7-day / 20k cap)
  memory.py          encrypted long-term memory
  fill.py            paste into the WeChat input box (paste only — never send)
  modelrouter.py     multi-model role routing and budgets
  harness_adapter.py official DeepSeek Harness SDK adapter
lib/                web panel (host.js is the DSH plugin host)
sdk/                extension SDK / MCP bridge / example extension
skills/             built-in knowledge base (goutoujunshi)
docs/               usage guide, known limitations, developer docs (Chinese)
licenses/           third-party licenses
```

## Run from source

Windows 10/11 + Python 3.12:

```powershell
git clone https://github.com/1314520-lgj/wechat-junshi.git
cd wechat-junshi
pip install -r requirements.txt
python -X utf8 launcher.py
```

Setup: enter a DeepSeek API key in the settings panel (stored with Windows DPAPI). For media understanding, install [Ollama](https://ollama.com) and run `ollama pull qwen3-vl:2b`. The optional Harness scheduler needs the official `deepseek-harness-sdk==0.1.5rc1` (not on PyPI); everything works without it.

Speech transcription additionally requires the local `models/whisper-small` model files, including `model.bin`; installing the Python package does not supply those weights. Missing media evidence stays unknown.

A prebuilt desktop installer exists but is not part of this repository; this repo is the full application source (dev package). To update an installed copy, quit Junshi through its settings, back up the install directory (`%LOCALAPPDATA%\Programs\Junshi`), and update the corresponding source files while retaining the runtime, models and user data.

## Layout checks

With Node.js 20 or newer, run `npm install`, `npx playwright install chromium`, then `npm run test:layout`. Tests use synthetic conversations and a mocked service; they do not contact WeChat or any model provider.

## Development

**Requirements:** Windows 10/11 + **Python 3.12** (`rapidocr-onnxruntime==1.4.4`
declares `Requires-Python >=3.6,<3.13`; on 3.13 dependency resolution fails) +
Node.js ≥ 20 (layout checks only).

```powershell
git clone https://github.com/1314520-lgj/wechat-junshi.git
cd wechat-junshi
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install              # enable git hooks, once
```

**Pre-submit checks** (same policy as CI — make sure they are green):

```powershell
pre-commit run --all-files      # file hygiene + ruff + pip-audit
ruff check .                    # ruleset and exemptions live in pyproject.toml
python -m unittest discover -s tests -p "test_*.py"
```

CI runs four dimensions on every push / PR: Python static checks and offline unit
tests, panel layout and interaction (Playwright), a pre-commit re-run to confirm
the hook policy, and dependency vulnerability scanning (pip-audit). Local hooks can
be bypassed with `--no-verify`; CI cannot — so CI is the final arbiter.

Full conventions (code style, dependency policy, security red lines, PR checklist)
are in [CONTRIBUTING.md](CONTRIBUTING.md) (Chinese).

## Security & privacy

- The engine listens on `127.0.0.1` only (exclusive port bind), requires an instance token + Host/Origin checks, and sends no CORS headers.
- API keys and user-confirmed memory are encrypted with Windows DPAPI; the observation database itself is not encrypted (7-day retention, 20k cap).
- Cloud models only ever receive the chat text that participates in an analysis; vision runs locally by default.
- There is no send endpoint; automatic fill has been removed; explicit copy and manual fill remain available.
- Never commit `private-data-backup`, Harness session logs, or any `.dpapi` / `.sqlite3` files (covered by `.gitignore`).

## Disclaimer

For personal study and expression assistance only. Make sure your use complies with WeChat's terms, local law, and the consent expectations of the people you chat with. Sending is always your own decision.

## License

[MIT](LICENSE) © 2026 wechat-junshi contributors. Third-party components keep their own licenses under `licenses/`.

---

Chinese README: [README.md](README.md) · 问题与建议请在 [Issues](https://github.com/1314520-lgj/wechat-junshi/issues) 提出，欢迎 PR。

Version 1.5.70 preserves speaker ownership when reusing verified advice, scopes payment and entry completion to the current card, invalidates pending advice when manual context changes, and keeps fill/copy failures separate from model regeneration. See [release notes](docs/1.5.70.md).
