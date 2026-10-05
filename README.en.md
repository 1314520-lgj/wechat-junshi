# Junshi (wechat-junshi) — a read-only WeChat reply assistant for Windows

Junshi is a Windows desktop assistant that **observes** the currently visible WeChat conversation, understands text and rich media, drafts and fact-checks candidate replies in context, and lets **you** paste them into the input box. **It never sends anything** — sending is always your own action.

> Not an auto-reply bot. Junshi's goal: understand the context, sound like you, and leave the choice to you.

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

A prebuilt desktop installer exists but is not part of this repository; this repo is the full application source (dev package). To update an installed copy, overwrite the install directory (`%LOCALAPPDATA%\Programs\Junshi`) with this repository.

## Security & privacy

- The engine listens on `127.0.0.1` only (exclusive port bind), requires an instance token + Host/Origin checks, and sends no CORS headers.
- API keys and user-confirmed memory are encrypted with Windows DPAPI; the observation database itself is not encrypted (7-day retention, 20k cap).
- Cloud models only ever receive the chat text that participates in an analysis; vision runs locally by default.
- There is no send endpoint; automatic fill is intentionally disabled because the latest-message position cannot be reliably verified for this WeChat version.
- Never commit `private-data-backup`, Harness session logs, or any `.dpapi` / `.sqlite3` files (covered by `.gitignore`).

## Disclaimer

For personal study and expression assistance only. Make sure your use complies with WeChat's terms, local law, and the consent expectations of the people you chat with. Sending is always your own decision.

## License

[MIT](LICENSE) © 2026 wechat-junshi contributors. Third-party components keep their own licenses under `licenses/`.

---

Chinese README: [README.md](README.md) · 问题与建议请在 [Issues](https://github.com/1314520-lgj/wechat-junshi/issues) 提出，欢迎 PR。
