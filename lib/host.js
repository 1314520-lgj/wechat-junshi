// dsh-junshi：微信军师 Host 插件
// 职责：拉起 Python 引擎（读屏/OCR/黄色边框/判断/起草/排序/填入）→ 把引擎 API 代理到 Web →
// 注入 Apple 风格面板脚本 → 注册 skills（junshi / goutoujunshi）→ 注册 agent 工具。
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const ENGINE_DIR = path.join(PACKAGE_ROOT, 'engine')
const SKILLS_DIR = path.join(PACKAGE_ROOT, 'skills')
const DSH_HOME = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const ENGINE_BASE_PORT = 47830
const ENGINE_ENTRY = 'junshi.py'

function pythonCandidates() {
  const cands = []
  if (process.env.DSH_JUNSHI_PYTHON) cands.push(process.env.DSH_JUNSHI_PYTHON)
  cands.push(path.join(DSH_HOME, 'dsh-runtimes', 'dsh-primary-runtime', 'dependencies', 'python', 'python.exe'))
  cands.push('python')
  return cands
}

function readText(file) {
  try {
    return fs.readFileSync(file, 'utf8')
  } catch (err) {
    return ''
  }
}

function loadSkills() {
  const junshi = readText(path.join(SKILLS_DIR, 'junshi-skill.md'))
  const goutou = readText(path.join(SKILLS_DIR, 'goutoujunshi', 'SKILL.md'))
  return { junshi, goutou }
}

// 面板脚本注入行（桌面壳只认结构化注入行；onerror 吞掉，路由不在时静默失败）
const PANEL_ROW_TEXT =
  '(function(){try{var d=document.body||document.head||document.documentElement;if(!d)return;' +
  'var s=document.createElement("script");s.src="/dsh-junshi/panel.js";' +
  's.onerror=function(){};d.appendChild(s)}catch(e){}})()'

function json(res, status, payload) {
  const body = Buffer.from(JSON.stringify(payload))
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': body.length,
    'cache-control': 'no-store',
  })
  res.end(body)
}

export default {
  name: 'dsh-junshi',

  apply(root) {
    const rowDisposers = []
    root.effect(() => () => { for (const d of rowDisposers) { try { d() } catch (err) {} } })
    // ① 注入行立刻注册（不依赖任何服务，桌面壳在宿主启动时收集一次注入表）
    rowDisposers.push(root.on('webserver/index-inject', (table) => {
      try {
        if (!Array.isArray(table)) return
        for (const row of table) {
          if (!row) continue
          if (row.kind === 'script-src' && row.src === '/dsh-junshi/panel.js') return
          if (row.kind === 'script' && typeof row.text === 'string'
            && row.text.indexOf('/dsh-junshi/panel.js') >= 0) return
        }
        table.push({ kind: 'script', placement: 'body', text: PANEL_ROW_TEXT })
      } catch (err) {}
    }))

    // ② 其余逻辑：等齐服务再跑
    root.inject(['webServer', 'credentials'], (ctx) => {
      const disposers = []
      const skills = loadSkills()
      const engineToken = crypto.randomBytes(24).toString('hex')
      let engine = null
      let restartTimer = null
      let disposed = false
      let restarts = 0
      let restartWindowStart = Date.now()
      let starting = false

      function hlog(msg) {
        try {
          fs.appendFileSync(path.join(DSH_HOME, '.dsh-junshi-host.log'),
            `[${new Date().toTimeString().slice(0, 8)}] ${msg}\n`)
        } catch (err) {}
      }

      // ---------- 引擎生命周期 ----------
      function resolvePython() {
        for (const cand of pythonCandidates()) {
          try {
            if (cand === 'python') return cand
            if (fs.existsSync(cand)) return cand
          } catch (err) {}
        }
        return 'python'
      }

      async function resolveApiKey() {
        // 带 8s 超时：凭据服务偶发阻塞时不能卡死引擎拉起
        // （引擎自己有 .credentials.yaml 回退，拿不到 env key 也能工作）。
        try {
          const cred = await Promise.race([
            ctx.credentials.resolve('DEEPSEEK_API_KEY'),
            new Promise((r) => setTimeout(() => r(null), 8000)),
          ])
          return cred && cred.value ? String(cred.value) : ''
        } catch (err) {
          return ''
        }
      }

      async function startEngine() {
        if (disposed || starting) return
        starting = true
        const python = resolvePython()
        const apiKey = await resolveApiKey()
        hlog(`startEngine: python=${python} key=${apiKey ? 'yes' : 'no'}`)
        const env = {
          ...process.env,
          DSH_HOME,
          DSH_JUNSHI_TOKEN: engineToken,
          DSH_JUNSHI_PORT: String(ENGINE_BASE_PORT),
          PYTHONIOENCODING: 'utf-8',
        }
        delete env.PYTHONPATH
        delete env.PYTHONHOME
        if (apiKey) env.DEEPSEEK_API_KEY = apiKey
        let logFd = null
        try { logFd = fs.openSync(path.join(DSH_HOME, '.dsh-junshi-engine.log'), 'a') } catch (err) {}
        try {
          // 纯 Python 模式：DSH 自带运行时跑引擎源码，不依赖任何 exe
          engine = spawn(python, ['-X', 'utf8', '-u', path.join(ENGINE_DIR, ENGINE_ENTRY)], {
            cwd: ENGINE_DIR,
            env,
            // 宿主是 GUI 进程没有控制台：stdin 忽略、stdout/stderr 直接进文件，
            // 绝不用 'inherit'（无效句柄会让 Python 写 stderr 时卡死）
            stdio: ['ignore', logFd || 'ignore', logFd || 'ignore'],
            windowsHide: true,
          })
        } catch (err) {
          hlog('spawn threw: ' + String((err && err.message) || err))
          console.warn('[dsh-junshi] 引擎启动失败:', String((err && err.message) || err))
          engine = null
          starting = false
          scheduleRestart()
          return
        }
        const myLogFd = logFd
        engine.once('exit', () => { try { myLogFd && fs.closeSync(myLogFd) } catch (err) {} })
        engine.on('error', (err) => {
          hlog('engine error: ' + String((err && err.message) || err))
          engine = null
          starting = false
          scheduleRestart()
        })
        engine.on('exit', (code) => {
          hlog(`engine exit code=${code}`)
          engine = null
          starting = false
          if (!disposed) scheduleRestart()
        })
        await readEnginePort()
        starting = false
      }

      // 每个插件实例用自己的 token 端口文件，多实例互不干扰
      function readPortNow() {
        const files = [
          path.join(DSH_HOME, `.dsh-junshi.port.${engineToken.slice(0, 8)}`),
          path.join(DSH_HOME, '.dsh-junshi.port'),
        ]
        for (const f of files) {
          try {
            const n = Number(fs.readFileSync(f, 'utf8').trim())
            if (n >= 1024 && n <= 65535) return n
          } catch (err) {}
        }
        return ENGINE_BASE_PORT
      }

      async function readEnginePort() {
        for (let i = 0; i < 40; i++) {
          if (disposed) return ENGINE_BASE_PORT
          const n = readPortNow()
          if (n !== ENGINE_BASE_PORT) return n
          await new Promise((r) => setTimeout(r, 250))
        }
        return ENGINE_BASE_PORT
      }

      function scheduleRestart() {
        if (disposed) return
        if (restartTimer) return
        const now = Date.now()
        if (now - restartWindowStart > 60000) {
          restartWindowStart = now
          restarts = 0
        }
        const delay = restarts >= 4 ? 15000 : 2000
        restarts++
        restartTimer = setTimeout(() => {
          restartTimer = null
          void startEngine()
        }, delay)
      }

      // 守护：每 12 秒探活一次；引擎死了就重启（不依赖 exit 事件语义）
      const supervisor = setInterval(async () => {
        if (disposed) return
        try {
          const resp = await engineFetch('/health')
          if (resp && resp.ok) return
        } catch (err) {}
        hlog('supervisor: engine dead, restarting')
        try { engine && engine.kill() } catch (err) {}
        engine = null
        scheduleRestart()
      }, 12000)

      // ---------- 代理 ----------
      async function engineFetch(suffix, init) {
        const port = readPortNow() // 每次实时读端口文件，引擎换端口也能自愈
        const url = `http://127.0.0.1:${port}${suffix}${suffix.includes('?') ? '&' : '?'}token=${engineToken}`
        try {
          return await fetch(url, { ...(init || {}), signal: AbortSignal.timeout(120000) })
        } catch (err) {
          return null
        }
      }

      function registerRoute(route) {
        disposers.push(ctx.webServer.register(route))
      }

      // panel.js
      let panelCache = { text: '', mtimeMs: 0 }
      function loadPanelJs() {
        const file = path.join(PACKAGE_ROOT, 'lib', 'panel.js')
        try {
          const st = fs.statSync(file)
          if (panelCache.mtimeMs !== st.mtimeMs) {
            panelCache = { text: fs.readFileSync(file, 'utf8'), mtimeMs: st.mtimeMs }
          }
        } catch (err) {}
        return panelCache.text
      }
      registerRoute({
        kind: 'exact',
        path: '/dsh-junshi/panel.js',
        handler: (req, res) => {
          const text = loadPanelJs()
          res.writeHead(200, {
            'content-type': 'application/javascript; charset=utf-8',
            'cache-control': 'no-store',
            'content-length': Buffer.byteLength(text),
          })
          res.end(text)
        },
      })

      // API 前缀代理 → 引擎
      registerRoute({
        kind: 'prefix',
        path: '/dsh-junshi/api',
        handler: async (req, res) => {
          try {
            const host = String(req.headers.host || '')
            if (!/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host.trim())) {
              json(res, 403, { ok: false, error: 'loopback only' })
              return
            }
            const site = String(req.headers['sec-fetch-site'] || '').toLowerCase()
            if (site === 'cross-site') {
              json(res, 403, { ok: false, error: 'cross-site rejected' })
              return
            }
            const suffix = (req.url || '').slice('/dsh-junshi/api'.length) || '/'
            const bodyChunks = []
            for await (const chunk of req) bodyChunks.push(chunk)
            const method = req.method || 'GET'
            const init = {
              method,
              headers: { 'content-type': 'application/json' },
            }
            if (bodyChunks.length) init.body = Buffer.concat(bodyChunks)
            const upstream = await engineFetch(suffix, init)
            if (!upstream) {
              json(res, 503, { ok: false, error: 'engine unavailable（正在启动或已退出）' })
              return
            }
            const ct = upstream.headers.get('content-type') || 'application/json'
            const data = Buffer.from(await upstream.arrayBuffer())
            res.writeHead(upstream.status, {
              'content-type': ct,
              'content-length': data.length,
              'cache-control': 'no-store',
            })
            res.end(data)
          } catch (err) {
            json(res, 502, { ok: false, error: String((err && err.message) || err).slice(0, 200) })
          }
        },
      })

      // API key 设置：写 DSH 官方凭据（key 不落本插件任何文件），然后带新 key 重启引擎
      registerRoute({
        kind: 'exact',
        path: '/dsh-junshi/key',
        handler: async (req, res) => {
          try {
            // 与 /dsh-junshi/api 代理同样的本地校验：任意本地网页不能用
            // no-cors 简单 POST 覆写密钥（计费劫持/内容外流）。
            const host = String(req.headers.host || '')
            if (!/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host.trim())) {
              json(res, 403, { ok: false, error: 'loopback only' })
              return
            }
            const site = String(req.headers['sec-fetch-site'] || '').toLowerCase()
            if (site === 'cross-site') {
              json(res, 403, { ok: false, error: 'cross-site rejected' })
              return
            }
            const chunks = []
            for await (const chunk of req) chunks.push(chunk)
            let key = ''
            try {
              key = String(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}').key || '').trim()
            } catch (err) {}
            if (!key) {
              json(res, 400, { ok: false, error: '密钥不能为空' })
              return
            }
            await ctx.credentials.set('DEEPSEEK_API_KEY', key)
            try { engine && engine.kill() } catch (err) {}
            engine = null
            scheduleRestart()
            json(res, 200, { ok: true, note: '密钥已保存，引擎重启中' })
          } catch (err) {
            json(res, 500, { ok: false, error: String((err && err.message) || err).slice(0, 200) })
          }
        },
      })

      // ---------- skills ----------
      const skillsSvc = ctx.skills || ctx.get('skills')
      if (skillsSvc && typeof skillsSvc.register === 'function') {
        if (skills.junshi) {
          try {
            disposers.push(skillsSvc.register({
              name: 'junshi',
              description: '微信军师：本地读屏识别微信会话，按 Jev 7 题口径判断语境/意图/紧张度，生成并排序 3 条候选回复，一键安全填入微信输入框（发送永远手动）。配合 junshi_status / junshi_reply / junshi_fill / junshi_analyze_text 工具使用。',
              whenToUse: '用户在微信里收到消息、不知道/想更快决定怎么回、需要把候选直接填进微信输入框时；或需要判断一段对话的意图与危险度时。',
              content: skills.junshi,
              invocation: { modelInvocable: true, userInvocable: true },
            }))
          } catch (err) {
            console.warn('[dsh-junshi] junshi skill 注册失败:', String((err && err.message) || err))
          }
        }
        if (skills.goutou) {
          try {
            disposers.push(skillsSvc.register({
              name: 'goutoujunshi',
              description: '狗头军师（goutoujunshi）：恋爱军师与情绪支持 skill。用于心动、暧昧、追求、聊天分析、约会、关系确认、冲突、冷淡、投入失衡、分手、复合、婚姻家庭问题；分析关系信号、设计主动推进或退出策略、润色可直接发送的话术。',
              whenToUse: '用户带着聊天记录/截图/转述来问关系问题、要话术、要策略、要情绪支持时；判断回复前需要关系背景时。',
              content: skills.goutou,
              invocation: { modelInvocable: true, userInvocable: true },
            }))
          } catch (err) {
            console.warn('[dsh-junshi] goutoujunshi skill 注册失败:', String((err && err.message) || err))
          }
        }
      }

      // ---------- agent 工具 ----------
      const textOut = (render) => ({
        schema: { type: 'string' },
        render: (_args, value) => [{ type: 'text', text: render ? render(value) : value }],
      })

      async function callEngine(suffix, init) {
        const upstream = await engineFetch(suffix, init)
        if (!upstream) return { ok: false, error: '军师引擎不可用' }
        try {
          return await upstream.json()
        } catch (err) {
          return { ok: false, error: '引擎返回无法解析' }
        }
      }

      function summarizeState(st) {
        if (!st || !st.ok) return '军师引擎暂不可用。'
        const parts = []
        parts.push(`状态：${st.engine.status}（${st.engine.capture_backend || '未采集'}，OCR ${st.engine.ocr_ms}ms，模型 ${st.engine.model}）`)
        parts.push(`微信窗口：${st.wechat.running ? '已找到' : '未找到'}`)
        parts.push(`当前会话：${st.session || '（未识别）'}`)
        const msgs = st.messages || []
        if (msgs.length) {
          parts.push('最近消息：\n' + msgs.slice(-8).map((m) =>
            `${m.from === 'me' ? '我' : (m.name || '对方')}: ${m.text}`).join('\n'))
        }
        if (st.analysis && st.analysis.candidates) {
          const j = st.analysis.judgment || {}
          parts.push('判断摘要：' + JSON.stringify(j, null, 0))
          parts.push('候选回复：\n' + st.analysis.candidates.map((c, i) =>
            `${i + 1}. ${c}（${Math.round((st.analysis.scores[i] || 0) * 100)}%）`).join('\n'))
        } else if (st.analysis_error) {
          parts.push('最近一次生成失败：' + st.analysis_error)
        }
        return parts.join('\n')
      }

      ctx.tools.register({
        name: 'junshi_status',
        description: '读取微信军师的实时状态：当前识别的微信会话、最近消息、判断摘要与候选回复。',
        parameters: {
          type: 'object',
          properties: {},
          additionalProperties: false,
        },
        output: textOut(),
        timeoutMs: 15000,
        async execute() {
          const st = await callEngine('/state')
          return summarizeState(st)
        },
      })

      ctx.tools.register({
        name: 'junshi_reply',
        description: '让军师重新判断当前微信会话并生成 3 条候选回复（Jev 7 题判断 → 起草 → 排序），返回判断摘要与候选。',
        parameters: {
          type: 'object',
          properties: {},
          additionalProperties: false,
        },
        output: textOut(),
        timeoutMs: 150000,
        async execute() {
          const start = await callEngine('/regenerate', {
            method: 'POST', body: '{}',
            headers: { 'content-type': 'application/json' },
          })
          if (!start || !start.ok) return `无法开始生成：${(start && start.error) || '引擎不可用'}`
          for (let i = 0; i < 90; i++) {
            await new Promise((r) => setTimeout(r, 2000))
            const st = await callEngine('/state')
            if (st && st.analysis) {
              return '已生成候选：\n' + summarizeState(st)
            }
            if (st && st.analysis_error) return `生成失败：${st.analysis_error}`
          }
          return '生成超时（90s），请稍后用 junshi_status 查看结果。'
        },
      })

      ctx.tools.register({
        name: 'junshi_fill',
        description: '把当前候选回复的第 N 条安全填入微信输入框（只填文字，绝不自动发送，发送由用户手动）。',
        parameters: {
          type: 'object',
          properties: {
            index: { type: 'number', description: '候选序号，1 开始（推荐条通常排第一）。' },
          },
          required: ['index'],
          additionalProperties: false,
        },
        output: textOut(),
        timeoutMs: 30000,
        async execute(args) {
          const idx = Number(args.index) || 1
          const res = await callEngine('/fill', {
            method: 'POST',
            body: JSON.stringify({ index: idx - 1 }),
            headers: { 'content-type': 'application/json' },
          })
          if (res && res.ok) {
            return `已把候选 ${idx} 填入微信输入框：「${res.filled}」。请人工检查后手动发送。`
          }
          return `填入失败：${(res && res.error) || '未知错误'}`
        },
      })

      ctx.tools.register({
        name: 'junshi_analyze_text',
        description: '对一段对话文本跑完整军师链路（Jev 判断 → 3 条候选 → 排序），不需要打开微信。适合分析用户贴出的聊天记录。',
        parameters: {
          type: 'object',
          properties: {
            messages: {
              type: 'array',
              description: '对话消息数组，每条 {from: "her"|"me", text: "…", name?: "发言人"}，最新在最后。',
              items: {
                type: 'object',
                properties: {
                  from: { type: 'string', enum: ['her', 'me'] },
                  text: { type: 'string' },
                  name: { type: 'string' },
                },
                required: ['from', 'text'],
                additionalProperties: false,
              },
            },
            relationship: { type: 'string', description: '你们的关系（恋人/朋友/同事/家人/自定义）。' },
            style: { type: 'string', description: '用户对自己说话风格的描述。' },
          },
          required: ['messages'],
          additionalProperties: false,
        },
        output: textOut(),
        timeoutMs: 150000,
        async execute(args) {
          const res = await callEngine('/analyze-text', {
            method: 'POST',
            body: JSON.stringify(args),
            headers: { 'content-type': 'application/json' },
          })
          if (res && res.ok) {
            const j = res.judgment || {}
            return '判断摘要：' + JSON.stringify(j, { ensure_ascii: false }) + '\n候选回复：\n'
              + res.candidates.map((c, i) => `${i + 1}. ${c}（${Math.round((res.scores[i] || 0) * 100)}%）`).join('\n')
          }
          return `分析失败：${(res && res.error) || '未知错误'}`
        },
      })

      // ---------- 启动 ----------
      hlog('plugin apply: starting engine')
      void startEngine()
      root.effect(() => () => {
        disposed = true
        clearInterval(supervisor)
        if (restartTimer) clearTimeout(restartTimer)
        try { engine && engine.kill() } catch (err) {}
        for (const d of disposers) { try { d() } catch (err) {} }
      })
    })
  },
}
