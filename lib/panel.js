// Junshi 1.1: calm standalone interface. No external fonts, scripts, or analytics.
(() => {
  'use strict'
  if (window.__junshiUXLoaded) return
  window.__junshiUXLoaded = true
  const API = window.__DSH_JUNSHI_API__ ?? ''
  let token = ''
  try {
    token = new URLSearchParams(location.hash.slice(1)).get('token') || sessionStorage.getItem('junshi-token') || ''
    if (token) sessionStorage.setItem('junshi-token', token)
    if (location.hash) history.replaceState(null, '', location.pathname)
  } catch (_) {}
  const style = document.createElement('style')
  style.textContent = `
    :root{color-scheme:dark;--bg:#131918;--surface:#1b2421;--card:#222e29;--line:#35463e;--text:#edf3ef;--muted:#a5b9ae;--accent:#7cdbad;--button:#26724f;--tint:#233d30;--warning:#f2c992;--error:#ffb9ae;--shadow:0 8px 28px #00000018;--reply-size:16px}
    :root[data-theme=light]{color-scheme:light;--bg:#f2f5f0;--surface:#fff;--card:#f4f7f3;--line:#d6e2d8;--text:#20392a;--muted:#607467;--accent:#26734c;--button:#26734c;--tint:#edf6ed;--warning:#87561b;--error:#b63b2c;--shadow:0 8px 28px #284a3110}
    *{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font:15px/1.7 'Segoe UI','Microsoft YaHei',sans-serif}body{padding:24px 22px 28px}button,input,select,textarea{font:inherit}button{cursor:pointer;min-height:40px;border:1px solid var(--line);border-radius:11px;padding:8px 14px;color:var(--text);background:var(--card);transition:background .15s,border-color .15s}button:disabled{opacity:.48;cursor:not-allowed}button:hover:not(:disabled){background:var(--tint);border-color:var(--accent)}button.primary{background:var(--button);color:#fff;border-color:var(--button);font-weight:600}button.primary:hover:not(:disabled){filter:brightness(1.12)}button.quiet{background:transparent}button.small{padding:6px 11px;font-size:13px;min-height:36px}button.danger{color:var(--error)}button:focus-visible,select:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
    main{width:100%;max-width:none;margin:auto}header{display:flex;align-items:center;gap:12px;margin-bottom:24px}.mark{width:44px;height:44px;border-radius:15px;background:var(--button);display:grid;place-items:center;font-size:23px;font-weight:600;color:#fff;box-shadow:0 4px 12px #26734c20}h1{font-size:22px;line-height:1.3;margin:0;letter-spacing:2px}header .spacer{flex:1}.version{font-size:11px;color:var(--muted)}h2{font-size:18px;line-height:1.5;margin:0 0 6px}.muted,.hint{color:var(--muted);font-size:13px}.hint{margin:8px 0 0}.status{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted);margin-top:3px}.dot{width:6px;height:6px;border-radius:50%;background:var(--muted)}.dot.active{background:var(--accent);box-shadow:0 0 0 3px var(--tint)}
    .workspace{display:grid;grid-template-columns:minmax(0,clamp(280px,31vw,400px)) minmax(0,1fr);gap:24px;align-items:start}.source-column,.result-column{min-width:0}.source-column{grid-column:1;grid-row:1}.result-column{grid-column:2;grid-row:1 / span 2}.section-title{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:0 0 12px}.section-title h2{font-size:14px;letter-spacing:1px;margin:0}.section-title span{font-size:12px;color:var(--muted)}.panel{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:20px;margin:0 0 14px;box-shadow:var(--shadow)}.row{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.row.between{justify-content:space-between}.row.actions{margin-top:14px}.pills{display:flex;gap:6px;flex-wrap:wrap}.pills button[aria-pressed=true]{background:var(--tint);color:var(--accent);border-color:var(--accent);font-weight:600}.switcher{display:flex;gap:4px;background:var(--card);padding:5px;border:1px solid var(--line);border-radius:14px;margin-bottom:20px;max-width:clamp(280px,31vw,400px)}.switcher button{flex:1;background:transparent;border-color:transparent;min-height:42px}.switcher button[aria-pressed=true]{background:var(--surface);color:var(--accent);box-shadow:0 2px 6px #0000000d;font-weight:600;border-color:var(--line)}
    input,select,textarea{background:var(--card);border:1px solid var(--line);border-radius:10px;color:var(--text);padding:10px 12px;max-width:100%;min-width:0}select{min-width:100px}input[type=checkbox]{accent-color:var(--accent);width:17px;height:17px;vertical-align:middle;margin-right:6px}input[type=password],input[type=text]{width:100%}textarea{width:100%;resize:vertical;line-height:1.8;font-size:var(--reply-size)}textarea::placeholder{color:var(--muted);opacity:.8}#transcript{min-height:180px;max-height:60vh}#transcript[aria-invalid=true]{border-color:var(--warning)}.input-meta{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:7px;color:var(--muted);font-size:12px}.input-meta button{min-height:32px}.input-error{color:var(--warning);font-size:12px;margin:6px 0 0}.shortcut{font-size:11px;color:var(--muted);margin-left:auto}.reply-card{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:22px;margin:0 0 14px;box-shadow:var(--shadow)}.reply-card.best{border-color:var(--accent);background:linear-gradient(145deg,var(--tint),var(--surface) 65%)}.tag{font-size:12px;color:var(--accent);font-weight:600}.reply-card .label{display:flex;align-items:center;justify-content:space-between;font-size:12px;color:var(--muted);gap:12px;margin-bottom:14px}.reply-card.best .tag{background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:3px 9px}.reply-edit-hint{color:var(--muted)}textarea.reply{display:block;background:transparent;border-color:transparent;padding:7px 8px;min-height:70px;max-height:clamp(90px,35dvh,320px);resize:none;overflow-y:auto;font-size:var(--reply-size);margin:0 -8px;width:calc(100% + 16px)}textarea.reply:hover,textarea.reply:focus{background:var(--card);border-color:var(--line)}.reply-card .actions{border-top:1px solid var(--line);padding-top:14px;margin-top:18px}.reply-card [data-done]:empty{display:none}.reply-card [data-done]{flex-basis:100%;margin-top:0;color:var(--accent)}
    details{margin-top:12px}summary{cursor:pointer;color:var(--muted);font-size:13px;padding:9px 0;overflow-wrap:anywhere}summary:hover{color:var(--text)}details .panel{box-shadow:none;margin-top:12px}details.panel{box-shadow:none;padding:9px 18px}details.panel>summary{color:var(--text)}details.panel[open]{padding-bottom:18px}#member-list,#readback-list{border:1px solid var(--line);border-radius:10px;padding:4px 12px;background:var(--card)}#member-list .evidence,#readback-list .evidence{padding:7px 0}.drawer-triggers{margin-top:4px}.drawer-triggers .hint{font-size:11px;margin:0 0 0 2px}.drawer{position:fixed;inset:0;z-index:60;visibility:hidden}.drawer.open{visibility:visible}.drawer-backdrop{position:absolute;inset:0;background:rgba(8,16,12,.55);opacity:0;transition:opacity .22s}.drawer.open .drawer-backdrop{opacity:1}.drawer-panel{position:absolute;top:0;right:0;bottom:0;width:min(92vw,480px);background:var(--surface);border-left:1px solid var(--line);box-shadow:-28px 0 70px rgba(0,0,0,.25);display:flex;flex-direction:column;transform:translateX(102%);transition:transform .22s ease}.drawer.open .drawer-panel{transform:translateX(0)}.drawer-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line)}.drawer-head h2{margin:0;font-size:16px}.drawer-body{flex:1;overflow-y:auto;overscroll-behavior:contain;padding:14px 18px 28px}#alternatives{margin-bottom:14px}#alternatives>summary{border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:12px 15px;margin-bottom:12px}.field{display:block;font-size:13px;color:var(--muted);margin:13px 0 5px}.field+input,.field+select{width:100%}.reason{font-size:13px;margin:0 0 14px;color:var(--muted);overflow-wrap:anywhere}.evidence{padding:12px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.evidence:last-child{border:0}.evidence b{font-size:13px}.evidence p{margin:5px 0}.evidence .row{margin-top:9px}.empty{padding:42px 24px;text-align:center;min-height:270px;display:flex;flex-direction:column;justify-content:center}.empty h2{font-size:19px;margin:12px 0 8px}.empty .symbol{display:grid;place-items:center;width:48px;height:48px;border-radius:16px;background:var(--tint);font-size:25px;color:var(--accent);margin:0 auto}.banner{padding:13px 15px;border:1px solid var(--line);border-radius:12px;background:var(--card);margin-bottom:12px;font-size:13px;overflow-wrap:anywhere}.error{color:var(--error)}#request-error{border-color:var(--error)}#analysis-warning,#result-state{color:var(--warning)}#work-status[data-busy=true]{display:flex;align-items:center;gap:10px;border-color:var(--accent);background:var(--tint)}#work-status[data-busy=true]:before{content:'';width:15px;height:15px;flex:none;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.welcome{padding:22px}.notice{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);max-width:calc(100vw - 32px);width:max-content;padding:12px 18px;background:var(--text);color:var(--bg);border-radius:12px;box-shadow:var(--shadow);font-size:13px;z-index:20;pointer-events:none}.footer{text-align:center;font-size:11px;color:var(--muted);margin-top:26px;padding-top:18px;border-top:1px solid var(--line)}.subtle-link{border:0;background:transparent;color:var(--accent);padding:6px 0;text-decoration:underline;text-underline-offset:4px}#reply-tools{gap:8px;padding:0 3px}.media-import{margin-top:14px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}[hidden]{display:none!important}
    dialog{background:var(--surface);color:var(--text);border:1px solid var(--line);border-radius:20px;padding:24px;box-shadow:0 24px 80px #0005;max-height:85vh;overflow:auto;overscroll-behavior:contain}dialog::backdrop{background:#0b181366;backdrop-filter:blur(3px)}dialog h2{font-size:20px}dialog img{display:block;max-height:65vh;object-fit:contain;margin-bottom:14px}#settings{display:none;width:min(540px,calc(100vw - 28px));margin:auto}#settings[open]{display:block}#settings .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}#settings>details{border-top:1px solid var(--line);padding-top:8px}#settings .settings-heading{margin-bottom:18px}#settings .settings-heading h2{margin:0}#settings .settings-heading button{margin-left:auto}#settings .settings-account{padding:14px;background:var(--card);border-radius:12px;margin-bottom:10px}#settings .settings-account button{background:var(--surface)}.key-status{font-size:12px;color:var(--muted)}#settings .settings-end{border-top:1px solid var(--line);padding-top:14px;margin-top:20px}
    @media(min-width:761px){.switcher{margin-left:0}}
    @media(max-width:760px){main{max-width:none}.workspace{grid-template-columns:1fr;gap:8px}.source-column{grid-column:1;grid-row:1}.result-column{grid-column:1;grid-row:2}.switcher{max-width:none}.result-column .section-title{margin-top:8px}.empty{min-height:200px}}
    @media(max-width:480px){body{padding:16px 12px 24px}header{margin-bottom:18px}.mark{width:38px;height:38px;border-radius:12px}h1{font-size:20px}.panel,.reply-card{padding:17px;border-radius:15px}.row.actions{gap:8px}.pills{gap:4px}.pills button{padding:6px 10px}.shortcut{display:none}.section-title span{font-size:11px}#settings .grid{grid-template-columns:1fr}dialog{padding:18px}.reply-card .actions button{flex:1}#manual .actions #analyze{flex:1}#live-message{font-size:14px}.switcher{margin-bottom:16px}}
    .support-column{grid-column:1;grid-row:2;min-width:0}.support-column .drawer-triggers{margin-top:0}
    /* Keep everyday actions close; reserve the drawer for checking details. */
    body{padding-top:20px}header{margin-bottom:18px}.workspace{grid-template-columns:minmax(0,clamp(280px,31vw,400px)) minmax(0,1fr);gap:clamp(14px,2vw,28px)}.switcher{max-width:clamp(280px,31vw,400px);margin-bottom:16px}.panel,.reply-card{padding:18px;margin-bottom:12px}.section-title{margin-bottom:10px}.section-title span{letter-spacing:0}.preference-grid{display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;margin-top:12px}.preference-grid .field{margin:0 0 5px}.preference-grid select{width:100%;min-width:0;padding:7px 10px;min-height:36px}.preference-grid .pills{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px}.preference-grid .pills button{padding:5px 0}.preference-grid .tone-label{font-size:13px;color:var(--muted);margin-bottom:5px}.reply-card .label{margin-bottom:8px;align-items:flex-start}.reply-edit-hint{text-align:right;overflow-wrap:anywhere}.reply-card .actions{margin-top:10px;padding-top:12px}#live-actions .actions{align-items:flex-start}#live-help{flex:1;min-width:130px;margin:0;padding-top:6px}#contact,#subtitle,#live-message{overflow-wrap:anywhere}#manual-target-field{display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 12px;margin-top:12px}#manual-target-field .field{margin:0}#manual-target-note{grid-column:2;margin:0}.drawer-triggers{padding-top:12px;border-top:1px solid var(--line);margin-top:16px;gap:8px}.drawer-triggers button{flex:1 1 140px}.drawer-triggers .section-title{flex-basis:100%;margin-bottom:0}.reason{margin-bottom:10px}.footer{margin-top:20px;padding-top:14px}.drawer{display:none;visibility:visible;width:100vw;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;border:0;border-radius:0;background:transparent;overflow:hidden;box-shadow:none}.drawer[open]{display:block}.drawer[open] .drawer-backdrop{opacity:1}.drawer::backdrop{background:transparent;backdrop-filter:none}.drawer-panel{transform:none;width:min(100vw,480px)}.drawer-head{flex:none}.drawer-body{min-height:0;scrollbar-gutter:stable}.drawer-head h2{overflow-wrap:anywhere}#member-list:empty,#readback-list:empty{display:none}dialog:not(.drawer) .row.actions{gap:8px}dialog:not(.drawer)>input,dialog:not(.drawer)>select{width:100%}
    @media(max-width:760px){.support-column{grid-column:1;grid-row:3;margin-top:4px}.workspace{grid-template-columns:1fr;gap:12px}.switcher{max-width:none}.drawer-triggers{margin-top:12px}.result-column .section-title{margin-top:0}}
    @media(max-width:480px){body{padding:14px 12px 22px}header{margin-bottom:14px}.switcher{margin-bottom:12px}.panel,.reply-card{padding:15px}.preference-grid{grid-template-columns:1fr;gap:8px}.preference-field{display:grid;grid-template-columns:38px minmax(0,1fr);align-items:center;gap:6px}.preference-grid .field,.preference-grid .tone-label{margin:0}.preference-field select{max-width:120px}.row.actions{margin-top:12px}#live-help{font-size:12px;min-width:110px}.section-title{gap:6px}.section-title h2{letter-spacing:0}.drawer-triggers button{flex-basis:120px}.drawer-head,.drawer-body{padding-left:15px;padding-right:15px}.drawer-head h2{font-size:15px}.footer{font-size:11px}.reply-card .actions button{min-width:0}}
    /* Use the current viewport for spacing and editor bounds; resizing keeps drafts intact. */
    body{padding:clamp(12px,2dvh,24px) clamp(12px,2vw,32px) 24px}#transcript{min-height:clamp(90px,25dvh,220px);max-height:max(90px,55dvh)}
    dialog:not(.drawer){--dialog-space:24px;padding:var(--dialog-space);max-width:calc(100vw - 24px);max-height:min(85dvh,calc(100dvh - 24px))}
    #settings .settings-heading{position:sticky;top:calc(-1 * var(--dialog-space));z-index:2;background:var(--surface);margin:calc(-1 * var(--dialog-space)) calc(-1 * var(--dialog-space)) 18px;padding:14px var(--dialog-space);border-bottom:1px solid var(--line)}
    @media(max-width:480px){dialog:not(.drawer){--dialog-space:18px}#settings .settings-heading{padding-top:12px;padding-bottom:12px}}
    @media(max-height:600px){body{padding-top:10px;padding-bottom:14px}header{margin-bottom:10px}.switcher{margin-bottom:10px}.panel,.reply-card{padding:12px;margin-bottom:10px}.section-title{margin-bottom:8px}.preference-grid{margin-top:10px;gap:8px}.empty{min-height:clamp(100px,28dvh,180px);padding:20px}.footer{margin-top:12px;padding-top:10px}dialog:not(.drawer){--dialog-space:14px}#settings .settings-heading{padding-top:10px;padding-bottom:10px;margin-bottom:12px}}
    @media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
  `
  document.head.appendChild(style)
  document.body.innerHTML = `<main>
    <header><div class="mark" aria-hidden="true">军</div><div><h1>军师</h1><div id="status" class="status" role="status"><i class="dot"></i><span>正在连接</span></div></div><span class="spacer"></span><button id="pause" class="small quiet" hidden>暂停</button><button data-act="settings" class="small quiet" aria-expanded="false" aria-controls="settings">设置</button></header>
    <dialog id="settings" aria-labelledby="settings-title">
      <div class="row settings-heading"><h2 id="settings-title">按你习惯来</h2><button data-act="close-settings" class="small quiet" aria-label="关闭设置">关闭</button></div><div class="settings-account row between"><span id="key-status" class="key-status">账户状态加载中</span><button data-act="setup-key" class="small">密钥设置</button></div><p id="settings-feedback" class="banner" role="status" hidden></p><div class="grid"><div><label class="field" for="theme">外观</label><select id="theme"><option value="dark">深色</option><option value="light">浅色</option><option value="system">跟随系统</option></select></div><div><label class="field" for="font-size">文字</label><select id="font-size"><option value="normal">标准</option><option value="large">大一点</option></select></div></div>
      <label class="field"><input id="startup" type="checkbox"> 开机在后台启动</label><p class="hint">不自动打开窗口；想用时点桌面图标或托盘。</p>
      <details><summary>图片、表情包与本地视觉模型</summary>
        <label class="field" for="vision-base">视觉接口地址</label><input id="vision-base" type="text" placeholder="http://127.0.0.1:11434/v1">
        <label class="field" for="vision-model">视觉模型</label><input id="vision-model" type="text" list="vision-model-list" placeholder="qwen3-vl:2b"><datalist id="vision-model-list"></datalist>
        <label class="field" for="vision-key">视觉服务密钥（本机 Ollama 可留空）</label><input id="vision-key" type="password" autocomplete="off">
        <label class="field"><input id="vision-enabled" type="checkbox"> 使用此服务理解当前会话媒体</label><p class="hint">会将媒体裁剪图发往你设置的服务，本机 Ollama 在本机识图。视觉描述会作为文字交给回复模型。视频仅看缩略图，不代表看过完整视频。</p>
        <label class="field" for="vision-keep-alive">本地视觉模型用完后保留</label><select id="vision-keep-alive"><option value="0">立即释放</option><option value="5">5分钟（默认）</option><option value="10">10分钟</option><option value="15">15分钟</option></select><p class="hint">仅用于本机 Ollama；保留会占用显存，便于接着识图。不自动预热，首次仍需加载。更改后下次实际识图生效，不额外调用模型。</p><div class="row actions"><button data-act="save-vision">保存视觉设置</button><button data-act="discover-vision">查看本机模型</button></div><p id="vision-status" class="hint" role="status"></p>
      </details>
      <details><summary>功能扩展与其他 AI 接入</summary><p class="hint">支持本机 API、MCP 和 Python 扩展。扩展默认关闭；启用的扩展可读取当前聊天并运行本机代码，只启用你信任的扩展。</p><div id="extension-list"></div><button data-act="load-extensions" class="small">查找已安装扩展</button><button data-act="save-extensions" class="small">保存启用项</button></details>
      <details><summary>账户与高级设置</summary><label class="field" for="key">DeepSeek 密钥</label><input id="key" type="password" autocomplete="off" placeholder="需要更换时再填写"><div class="row actions"><button data-act="save-key">保存密钥</button><button data-act="delete-key" class="quiet">删除密钥</button></div>
        <label class="field" for="model">回复模型</label><input id="model" type="text"><label class="field" for="judge-model">分析模型</label><input id="judge-model" type="text"><label class="field" for="wechat-path">微信程序位置（留空自动查找）</label><input id="wechat-path" type="text"><label class="field" for="context">参考最近几条消息</label><input id="context" type="number" min="3" max="30"><label class="field"><input id="memory" type="checkbox"> 使用军师关系层和加密记忆</label><label class="field" for="target-name">群聊回复对象（不填则不指定）</label><input id="target-name" type="text" placeholder="对象名称"><label class="field" for="custom-style">补充我的说话习惯</label><input id="custom-style" type="text" placeholder="例如：不加句号，不用表情"><div class="row actions"><button data-act="save-advanced" class="primary">保存这些设置</button><button data-act="clear-memory" class="quiet">清空当前会话记忆</button></div>
      </details><div class="row actions settings-end"><button data-act="quit" class="quiet">退出军师</button><span class="version" id="app-version">版本加载中…</span></div>
    </dialog>
    <div id="connection" class="banner" hidden role="status"></div>
    <div class="switcher" role="group" aria-label="使用方式"><button data-act="live" aria-pressed="true">跟随微信</button><button data-act="manual" aria-pressed="false">粘贴聊天</button></div>
    <div class="workspace"><div class="source-column"><div class="section-title"><h2>聊天与偏好</h2><span>先核对，再选一句</span></div>
    <section id="welcome" class="panel welcome" hidden></section>
    <section id="context-card" class="panel"><div class="row between"><div><h2 id="contact">等待会话</h2><div id="subtitle" class="muted">打开微信里的联系人，军师会跟上</div></div></div><div class="preference-grid"><div class="preference-field"><label class="field" for="relationship">关系</label><select id="relationship"><option>朋友</option><option>恋人</option><option>同学</option><option>同事</option><option>家人</option></select></div><div class="preference-field"><div class="tone-label" id="tone-label">语气</div><div class="pills" role="group" aria-labelledby="tone-label"><button data-act="tone" data-tone="自然" class="small">自然</button><button data-act="tone" data-tone="温柔" class="small">温柔</button><button data-act="tone" data-tone="幽默" class="small">幽默</button><button data-act="tone" data-tone="简短" class="small">简短</button></div></div></div><p id="preference-note" class="hint">关系与语气会为这个联系人记住</p></section>
    <section id="live-actions" class="panel"><p id="live-message" class="hint" style="margin-top:0"></p><div class="row actions"><button id="live-reply" data-act="regenerate" class="primary" disabled>帮我回复</button><span id="live-help" class="hint" role="status">正在连接军师</span></div></section>
    <section id="manual" class="panel" hidden><label class="field" for="transcript" style="margin-top:0">粘贴需要回复的对话</label><textarea id="transcript" rows="6" aria-describedby="transcript-help transcript-error" placeholder="对方：明天有空吗？&#10;我：下午有空&#10;对方：那几点见？"></textarea><div class="input-meta"><span id="transcript-count">尚未输入</span><button data-act="example" id="transcript-example" class="small quiet">试填一段示例</button></div><p id="transcript-error" class="input-error" hidden></p><div id="manual-target-field" class="row" hidden><label class="field" for="manual-target">回复谁</label><select id="manual-target" aria-describedby="manual-target-note"><option value="">最新发言人</option></select><span id="manual-target-note" class="hint">只指定这次回复</span></div><div class="row actions"><button data-act="analyze" class="primary" id="analyze">分析并生成回复</button><button data-act="clear-text" id="clear-text" class="quiet">清空</button><button data-act="undo-clear" id="undo-clear" class="small quiet" hidden>撤销清空</button><button data-act="cancel-manual" id="cancel-manual" class="quiet" hidden>停止生成</button></div><p class="hint" id="transcript-help">每段用“我：”或“对方：”开头，最新消息放最后。<br>Ctrl + Enter 生成回复。分析会发送文字给 DeepSeek，并产生 API 费用。</p></section>
    </div><div class="result-column"><div class="section-title"><h2>回复建议</h2><span>选一句，也可以改几个字</span></div>
    <div id="new-advice" class="banner" hidden>新建议已经好了，你修改的文字会保留。 <button data-act="latest" class="small">查看新建议</button></div>
    <div id="work-status" class="banner" role="status" hidden></div>
    <div id="result-state" class="banner" role="status" hidden></div>
    <div id="request-error" class="banner error" role="alert" hidden><span id="request-error-text"></span> <button data-act="retry-request" class="small">重试</button></div>
    <div id="analysis-warning" class="banner" role="alert" hidden><span id="analysis-warning-text"></span> <button data-act="regenerate" class="small">重试识别与生成</button></div>
    <div class="row drawer-triggers"><button data-act="open-drawer" data-view="readback" class="small" id="trigger-readback">核对最近消息<span id="readback-count" class="hint"></span></button><button data-act="open-drawer" data-view="members" class="small" id="trigger-members">群聊人物<span id="members-count" class="hint"></span></button><button data-act="open-drawer" data-view="media" class="small">理解语音/视频</button></div>
    <div id="cache-note" class="banner" role="status" hidden></div>
    <section id="advice" aria-label="回复建议"></section>
    <div class="row between" id="reply-tools" hidden><button data-act="regenerate" class="subtle-link">换一组回复</button><span class="hint">可先改几个字，再填入或复制</span></div>
    <details id="diagnostics" hidden><summary>查看本次处理耗时</summary><p id="diagnostics-text" class="hint"></p></details></div></div>
    <div class="footer">只帮你准备回复，发送由你自己决定。<br>关闭窗口后，军师在托盘里继续运行。</div>
  </main><dialog id="drawer" class="drawer" aria-labelledby="drawer-title"><div class="drawer-backdrop" data-act="close-drawer"></div><div class="drawer-panel"><div class="drawer-head"><h2 id="drawer-title">核对</h2><button data-act="close-drawer" class="small quiet">关闭</button></div><div class="drawer-body"><p id="drawer-feedback" class="banner" role="status" hidden></p><div id="drawer-readback" class="drawer-view"><p class="hint" id="frame-age-note"></p><p class="hint">文字识别和视觉描述都可能有误，看不清的媒体会保留未知。滚动历史会改变观察顺序；目前未确认消息列表最新位置。先核对，再使用建议。</p><div id="readback-list"></div><div class="row actions"><button data-act="confirm-memory" class="small">添加我确认的会话事实</button><button data-act="correct-context" class="small">修正这些消息并分析</button></div><p class="hint">修正会进入粘贴聊天，不改微信记录。用“[图片]”“[视频]”“[表情包]”“[未知媒体]”区分媒体；已知内容可写成普通文字。</p></div><div id="drawer-members" class="drawer-view" hidden><p class="hint">逐条保留发言人和时间。这里只列屏幕上读到的人；昵称不是微信账号，同名无法保证是同一人。</p><div id="member-list"></div></div><div id="drawer-media" class="drawer-view" hidden></div></div></div></dialog><div id="toast" class="notice" role="status" hidden></div>`
  const $ = id => document.getElementById(id)
  document.addEventListener('close',e=>{if(e.target instanceof HTMLDialogElement&&!e.target.id)e.target.remove()},true)

  const routingSection=document.createElement('details');routingSection.innerHTML=`<summary>模型协作与扩展</summary><label class=field><input id=harness-enabled type=checkbox> 使用官方 DeepSeek Harness 调度</label><p id=harness-status class=hint></p><div id=model-catalog></div><p class=hint>同一职责优先使用排在前面的已启用模型。费用为你填写的单次估算上限，服务商实际计费仍需核对；填零表示价格未知。</p><label class=field>模型编号</label><input id=route-id type=text><label class=field>兼容接口地址</label><input id=route-base type=text placeholder="http://127.0.0.1:11434/v1"><label class=field>模型名称</label><input id=route-model type=text><label class=field>密钥</label><input id=route-key type=password><label class=field>职责</label><select id=route-role><option value=draft>回复起草</option><option value=review>事实复核</option><option value=judge>语境理解</option><option value=rank>候选评估</option></select><label class=field>单次费用估算上限</label><input id=route-cost type=number value=0 min=0 max=10 step=.001><button data-act=add-model>保存模型</button><label class=field>每次分析时间上限（秒）</label><input id=generation-timeout type=number min=15 max=180><label class=field>云端并发请求上限</label><input id=max-cloud-requests type=number min=1 max=4><p class=hint>默认1；本地文字与视觉共用单任务通道。Harness任务仍串行，避免取消影响其他任务。</p><label class=field>逻辑调用次数上限</label><input id=max-model-calls type=number min=1 max=12><label class=field>已知价格的估算费用上限</label><input id=max-analysis-cost type=number min=0 max=10 step=.01><button data-act=save-budget>保存预算</button><p id=routing-error class=error></p></details>`;$('settings').querySelector('.settings-end').before(routingSection);
  async function refreshModels(){const data=await api('/models');$('model-catalog').innerHTML=data.models.map(m=>`<div class=evidence><b>${escape(m.id)}</b> ${escape(m.model)} · ${escape(m.roles.join('/'))} · ${m.enabled?'启用':'停用'}<button data-act=route-toggle data-route="${escape(m.id)}">${m.enabled?'停用':'启用'}</button><button data-act=route-first data-route="${escape(m.id)}">优先</button><button data-act=route-delete data-route="${escape(m.id)}">移除</button></div>`).join('')}
  routingSection.addEventListener('toggle',()=>{if(routingSection.open)refreshModels().catch(e=>$('routing-error').textContent=friendly(e))});
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
  const mediaSection=$('drawer-media');mediaSection.innerHTML='<p class=hint>选择从微信保存的文件，最多20MB。视频抽样画面与语音分别识别，不代表完整看过所有画面。音频最多处理前180秒，首次转写较慢。</p><input id=media-file type=file accept=".mp4,.mov,.mkv,.webm,.wav,.mp3,.m4a,.ogg,.flac,.aac"><div class="row actions"><button data-act=import-media>开始理解</button></div><p id=media-work class=hint></p><div id=media-result></div><p id=media-error class=error></p>';
  const drawerTitles={readback:'核对军师最近读到的消息',members:'群聊人物线索',media:'理解本地语音与视频'}
  let drawerReturnFocus=null, drawerOverflow=''
  const drawer=$('drawer')
  const drawerTriggers=document.querySelector('.drawer-triggers')
  drawerTriggers.insertAdjacentHTML('afterbegin','<div class="section-title"><h2>核对与补充</h2><span>按需查看</span></div>')
  const support=document.createElement('div');support.className='support-column';support.append(drawerTriggers);document.querySelector('.workspace').append(support)
  drawerTriggers.querySelectorAll('[data-act=open-drawer]').forEach(b=>{b.setAttribute('aria-controls','drawer');b.setAttribute('aria-haspopup','dialog');b.setAttribute('aria-expanded','false')})
  function openDrawer(view) {
    if(!Object.hasOwn(drawerTitles,view))return
    document.querySelectorAll('.drawer-view').forEach(v=>{v.hidden=v.id!=='drawer-'+view})
    $('drawer-title').textContent=drawerTitles[view];$('drawer-feedback').hidden=true;$('toast').hidden=true
    if(!drawer.open){drawerReturnFocus=document.activeElement;drawerOverflow=document.body.style.overflow;drawer.showModal();document.body.style.overflow='hidden'}
    drawerTriggers.querySelectorAll('button').forEach(b=>b.setAttribute('aria-expanded',String(b.dataset.view===view)))
    drawer.querySelector('.drawer-head button').focus()
    if(view==='members')updateMembers();if(view==='readback')updateReadback()
  }
  function closeDrawer() {if(drawer.open)drawer.close()}
  drawer.addEventListener('cancel',e=>{e.preventDefault();closeDrawer()})
  drawer.addEventListener('keydown',e=>{
    if(e.key!=='Tab'||[...document.querySelectorAll('dialog:modal')].at(-1)!==drawer)return
    const items=[...drawer.querySelectorAll('button,input,select,textarea,a[href],[tabindex="0"]')].filter(el=>!el.disabled&&el.getClientRects().length)
    const first=items[0],last=items.at(-1)
    if(!first)return
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  })
  drawer.addEventListener('close',()=>{
    document.body.style.overflow=drawerOverflow
    drawerTriggers.querySelectorAll('button').forEach(b=>b.setAttribute('aria-expanded','false'))
    if(drawerReturnFocus?.isConnected&&!drawerReturnFocus.hidden)drawerReturnFocus.focus()
  })
  let manualPrefs = null, manualError = "", liveError = "", manualStale = false, readbackMessages = [], readbackSignature = "", membersSignature = "", importedMediaJob = null
  let st = null, mode = 'live', view = null, manualResult = null, pending = null, dirty = false, inRequest = false, failures = 0, noticeTimer, settingsOpen = false, lastContact = '', manualSeq = 0, pendingManualSeq = null
  const attachButton=document.createElement('button');attachButton.dataset.act='attach-media-job';attachButton.textContent='确认文件所属消息并用于回复';mediaSection.append(attachButton);
  // Drafts stay in this window's memory; never persist chat text to disk.
  const drafts = new Map()
  let draftKey = 'live:'
  function rememberDraft() {
    if (!view) return
    const edits = {}
    document.querySelectorAll('.reply').forEach(t => { edits[t.dataset.index] = t.value })
    drafts.delete(draftKey)
    drafts.set(draftKey, {view, edits, dirty, pending, pendingManualSeq})
    if (drafts.size > 12) drafts.delete(drafts.keys().next().value)
  }
  function restoreDraft(key, fallback) {
    draftKey = key
    const saved = drafts.get(key)
    renderAdvice(saved?.view || fallback)
    if (saved) {
      for (const [i,text] of Object.entries(saved.edits)) { const t=$('reply-'+i); if(t){t.value=text;const label=document.querySelector('[data-edit="'+i+'"]');if(label)label.textContent=text!==saved.view?.candidates?.[Number(i)]?'已修改 · 会使用你的文字':'可直接修改'} }
      dirty=saved.dirty; pendingManualSeq=saved.pendingManualSeq ?? null;pending=mode==='manual'&&pendingManualSeq!==manualSeq?null:saved.pending
      $('new-advice').hidden=!pending
    }
    fitReplies();updateFillAvailability()
  }
  const tones = {自然:'',温柔:'温柔自然，先接住情绪，不肉麻',幽默:'轻松幽默，有一点调侃，不挖苦',简短:'简洁自然，尽量一句话，不展开'}
  let preferences = {theme:'system',font:'normal'}
  try { preferences = Object.assign(preferences, JSON.parse(localStorage.getItem('junshi-display') || '{}')) } catch (_) {}
  function theme() {
    const isLight = preferences.theme === 'light' || preferences.theme === 'system' && matchMedia('(prefers-color-scheme:light)').matches
    document.documentElement.dataset.theme = isLight ? 'light' : 'dark'
    const size = preferences.font === 'large' ? '18px' : '16px'
    document.documentElement.style.setProperty('--reply-size',size)
    document.body.style.fontSize=preferences.font==='large'?'18px':'15px'
    document.querySelectorAll('.reply').forEach(t => t.style.fontSize=size)
    $('theme').value=preferences.theme; $('font-size').value=preferences.font;fitReplies()
  }
  theme()
  matchMedia('(prefers-color-scheme:light)').addEventListener('change',theme)
  let settingsReturnFocus=null, clearedTranscript=''
  function openSettings(key=false) {
    if(!settingsOpen){settingsReturnFocus=document.activeElement;settingsOpen=true;initializeSettings();$('settings-feedback').hidden=true;$('settings').showModal()}
    document.querySelector('header [data-act=settings]').setAttribute('aria-expanded','true')
    if(key){$('key').closest('details').open=true;$('key').scrollIntoView({block:'center'});$('key').focus()}
    else $('settings').querySelector('[data-act=close-settings]').focus()
  }
  $('settings').addEventListener('close',()=>{settingsOpen=false;document.querySelector('header [data-act=settings]').setAttribute('aria-expanded','false');if(settingsReturnFocus?.isConnected)settingsReturnFocus.focus()})
  function fitReplies(){document.querySelectorAll('.reply').forEach(t=>{if(!t.getClientRects().length)return;const bounds=getComputedStyle(t),minimum=parseFloat(bounds.minHeight)||70,maximum=Math.max(minimum,parseFloat(bounds.maxHeight)||320);const scroll=t.scrollTop;t.style.height='0px';t.style.height=Math.min(maximum,Math.max(minimum,t.scrollHeight+2))+'px';t.scrollTop=scroll})}
  window.addEventListener('resize',fitReplies)
  document.addEventListener('toggle',e=>{if(e.target.open)fitReplies()},true)
  function updateManualInput(){
    const text=$('transcript').value.trim();let error='',count=0,names=[]
    if(text){try{const messages=parseTranscript(text);count=messages.length;names=[...new Set(messages.filter(m=>m.from==='her'&&m.name).map(m=>m.name))]}catch(e){error=friendly(e)}}
    const select=$('manual-target'),signature=JSON.stringify(names);if(select.dataset.names!==signature){const previous=select.value;select.replaceChildren(new Option('最新发言人',''),...names.map(name=>new Option(name,name)));if(names.includes(previous))select.value=previous;select.dataset.names=signature}
    $('manual-target-field').hidden=names.length<2
    $('transcript-count').textContent=text?(count?count+' 段消息 · ':'')+text.length+' 字':'尚未输入'
    $('transcript-error').hidden=!error;$('transcript-error').textContent=error;$('transcript').setAttribute('aria-invalid',String(!!error))
    $('transcript-example').hidden=!!text;$('clear-text').disabled=!text;$('undo-clear').hidden=!clearedTranscript||!!text
    $('analyze').disabled=inRequest||!text||!!error||!st?.settings.has_key||failures>0
  }
  document.addEventListener('keydown',e=>{
    if(e.key==='Tab'&&settingsOpen){
      const items=[...$('settings').querySelectorAll('button,input,select,textarea,summary,[tabindex="0"]')].filter(x=>!x.disabled&&x.getClientRects().length)
      const first=items[0],last=items.at(-1)
      if(items.length&&(e.shiftKey&&document.activeElement===first||!e.shiftKey&&document.activeElement===last)){e.preventDefault();(e.shiftKey?last:first).focus()}
    }
    if(e.target.id==='transcript'&&(e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!e.isComposing&&mode==='manual'&&!settingsOpen){e.preventDefault();if(!$('analyze').disabled)$('analyze').click()}
  })
  function tell(text) { clearTimeout(noticeTimer);if(settingsOpen){$('toast').hidden=true;$('settings-feedback').textContent=text;$('settings-feedback').hidden=false;return} if(drawer.open){$('toast').hidden=true;$('drawer-feedback').textContent=text;$('drawer-feedback').hidden=false;$('drawer-feedback').scrollIntoView({block:'nearest'});return} $('toast').textContent=text; $('toast').hidden=false; noticeTimer=setTimeout(() => $('toast').hidden=true,3800) }
  function friendly(error) {
    if(error?.name==='AbortError')return '等待时间较长，请稍后重试；你输入的文字会保留'
    const s=String(error?.message || error || '')
    if (/401|密钥被拒|密钥无效/.test(s)) return '密钥暂时不可用，请在设置里检查或更换'
    if (/402|余额不足/.test(s)) return 'DeepSeek 账户余额不足，请检查账户后重试'
    if (/404|模型/.test(s)) return '模型暂时不可用，可在高级设置里修改模型名'
    if (/429|限流/.test(s)) return '请求有点多，稍等一下再试'
    return s || '暂时没成功，请稍后重试'
  }
  async function api(path,body,signal) {
    const controller=new AbortController(); const timeout=setTimeout(() => controller.abort(),path==='/analyze-text'?240000:8000)
    const abort=()=>controller.abort();if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true})
    try {
      const response=await fetch(API+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal})
      const result=await response.json()
      if(!response.ok || !result.ok) throw new Error(result.error || '暂时无法连接军师')
      return result
    } finally { clearTimeout(timeout);signal?.removeEventListener('abort',abort) }
  }
  const mediaLabels={image:'图片',video:'视频',sticker:'表情包',media_unknown:'未知媒体'}
  const kindLabels={text:'文字',audio:'语音',quoted:'引用',...mediaLabels,emoji:'表情',group_notice:'群公告',poll:'群投票',relay:'群接龙',system:'系统消息',transfer:'转账卡片',red_packet:'红包卡片',official_account:'公众号入口',link:'链接分享',mini_program:'小程序入口',app_card:'外部应用入口'}
  const phases={start:'准备',vision:'理解图片与表情包',judging:'理解语境',drafting:'起草回复',checking:'核对事实与承诺',ranking:'选择合适的回复'}
  function showErrors() {
    const error=mode==='manual'?manualError:liveError || st?.analysis_error
    $('request-error').hidden=!error
    $('request-error-text').textContent=error?friendly(error):''
  }
  function showStale() {
    const stale=mode==='manual'?manualStale:!!view && (st?.analysis?.expired || st?.engine.title_ready===false || st?.settings.paused || view.ts!==st?.analysis?.ts || view.session!==st?.session || view.source_signature!==st?.source_signature)
    $('result-state').hidden=!stale
    $('result-state').textContent=stale?'这组是旧建议，尚未针对当前原文或偏好更新；请重新分析。修改的回复仍可复制。':''
  }
  function updateMembers() {
    const members=st?.participants || []
    $('trigger-members').hidden=mode!=='live' || !members.length
    $('members-count').textContent=members.length?' · '+members.length+' 条':''
    // 大群几百条线索：内容不变时不要每 1.2 秒重建一遍列表。
    const signature=JSON.stringify(members)
    if(signature===membersSignature)return
    membersSignature=signature
    $('member-list').innerHTML='<p class=hint>已观察人物线索 '+escape(Number(st.identity_coverage?.observed ?? members.length) || 0)+' 条人物线索，用户确认 '+escape(Number(st.identity_coverage?.confirmed ?? 0) || 0)+' 人；不代表全部群成员，相同头像昵称可能属于不同账号。</p>'+members.map(m=>`<div class="evidence"><b>${escape(m.name)}</b><span class="hint"> · ${escape(Number(m.messages)||0)} 条 · ${m.identity==='user_confirmed'?'用户已确认':'仅视觉线索，待确认'}${m.last_time?' · '+escape(m.last_time):''}</span></div>`).join('')
  }
  function updateReadback() {
    $('trigger-readback').hidden=mode!=='live'
    const ageNote=$('frame-age-note')
    const age=st?.engine.frame_age_seconds
    ageNote.textContent=age==null?'还没有可核对采集时间的画面':`当前证据画面采集于 ${age} 秒前；不代表已确认列表最新位置${st?.engine.title_ready===false?'，当前会话未确认':''}`
    const sameContext=st?.analysis?.session===st?.session && st?.analysis?.source_signature===st?.source_signature
    const understood=new Map((sameContext?st?.analysis?.understood_messages || []:[]).filter(m=>m.message_id || m.media_id).map(m=>[m.message_id || m.media_id,m]))
    const messages=(st?.messages || []).slice(-10).map(m=>{
      const seen=understood.get(m.message_id || m.media_id)
      if(!seen)return m
      const evidence={...m,kind:seen.kind}
      for(const key of ['media_description','media_caption','vision_uncertain','vision_confidence','media_understanding_complete','content_source'])if(key in seen)evidence[key]=seen[key]
      evidence.uncertainties=[...new Set([...(m.uncertainties||[]),...(seen.uncertainties||[])])]
      if(seen.card_details){evidence.card_details=seen.card_details;evidence.card_scope='visible_preview'}
      return evidence
    })
    $('readback-count').textContent=messages.length?' · '+messages.length+' 条':''
    const signature=JSON.stringify(messages)
    if(signature===readbackSignature)return
    readbackSignature=signature;readbackMessages=messages.map(m=>({...m}))
    $('readback-list').innerHTML=messages.length?messages.map((m,i)=>`<div class="evidence"><b>${escape(m.from==='me'?'我':m.name || '发言人待确认')}</b><span class="hint">${m.time?' · '+escape(m.time):''} · ${escape(kindLabels[m.kind] || m.kind || '文字')} · ${m.content_source==='user_corrected'?'已更正':'尚未人工核对'}</span><p>${escape(m.text || '['+(mediaLabels[m.kind] || '媒体')+'，文字未知]')}${m.media_description?'<br>画面观察（待核对）：'+escape(m.media_description):''}${m.media_caption&&!m.media_description?'<br>配字观察（待核对）：'+escape(m.media_caption):''}${m.vision_uncertain?'<br><span class=hint>图案尚未确认，建议只依据可用文字；可点下方核对原图或更正。</span>':''}</p><div class="hint">${escape((m.uncertainties || []).join('；'))}</div><div class="row"><button class="small" data-act="correct-observation" data-row="${i}">更正文字与归属</button>${m.evidence?.crop_id?`<button class="small" data-act="show-evidence" data-row="${i}">查看读取原图</button>`:''}</div></div>`).join(''):'<p class="muted">尚未读到消息。请展开微信并等待识别，或使用粘贴聊天。</p>'
  }
  function updateProgress() {
    $('cancel-manual').hidden=mode!=='manual'||!inRequest
    const phase=mode==='manual'?(inRequest&&st?.engine.manual_phase_request===activeManualRequest?st.engine.manual_phase:null):st?.analysis_inflight?st.engine.analysis_phase:null
    let text=phase?phases[phase] || '正在准备回复':''
    if(phase&&mode==='live')text+=' · '+st.engine.analysis_elapsed+' 秒'
    if(mode==='manual'&&inRequest){text ||= '正在准备回复';text+=' · '+Math.max(0,Math.floor((Date.now()-manualStartedAt)/1000))+' 秒'}
    if(phase==='vision')text+=' · 首次识图可能需要加载模型'
    if(mode==='live'&&!text&&st?.engine.recognition_phase==='recognizing'&&!st?.settings.paused)text='正在识别微信文字'
    if(mode==='live'&&st?.engine.title_ready===false&&!st?.settings.paused)text='正在确认会话标题；旧建议暂时仅可复制'
    if(mode==='live'&&st?.engine.recognition_phase==='locating')text='消息区域未定位，请展开微信或拉大聊天窗口后重试'
    const active=!!(phase||(mode==='manual'&&inRequest)||(mode==='live'&&['recognizing','locating'].includes(st?.engine.recognition_phase)))
    const progress=text
    let timing=''
    const m=st?.engine.ocr_metrics
    if(mode==='live'&&m&&Number.isFinite(m.ocr_ms))timing=m.ocr_cache_hit?`最近识别：相同图像复用文字，整理 ${m.post_ms} 毫秒`:`最近识别：文字 ${(m.ocr_ms/1000).toFixed(1)} 秒，整理 ${(m.post_ms/1000).toFixed(1)} 秒`
    if(!phase&&mode==='live'&&st?.analysis?.phase_timings?.length)timing+=(timing?' · ':'')+st.analysis.phase_timings.filter(x=>x.seconds>.05).map(x=>(phases[x.phase]||x.phase)+' '+x.seconds.toFixed(1)+'秒').join(' / ')
    const result=mode==='manual'?manualResult:st?.analysis
    const vision=(result?.model_trace || []).filter(x=>x.phase==='vision').at(-1)
    if(!phase&&vision){
      const parts=[['queue_seconds','排队'],['load_seconds','模型加载'],['prompt_eval_seconds','视觉输入'],['eval_seconds','描述生成']].filter(([key])=>Number.isFinite(vision[key])).map(([key,label])=>label+' '+vision[key].toFixed(1)+'秒')
      if(parts.length)timing+=(timing?' · ':'')+(vision.local?'本地视觉：':'视觉：')+parts.join(' / ')
    }
    $('work-status').hidden=!progress;$('work-status').textContent=progress;$('work-status').dataset.busy=String(active)
    $('advice').setAttribute('aria-busy',String(!!(phase||mode==='manual'&&inRequest)))
    $('diagnostics').hidden=!timing;$('diagnostics-text').textContent=timing;updateManualInput()
  }
  function setStatus(text,active=false) { const el=$('status'); if(el.dataset.label===text)return; el.dataset.label=text; el.innerHTML=`<i class="dot ${active?'active':''}"></i><span>${escape(text)}</span>` }
  function initializeSettings() {
    if(!st)return
    const s=st.settings
    $('key-status').textContent=s.has_key?'已保存账户密钥':'尚未设置账户密钥'
    $('harness-enabled').checked=!!s.harness_enabled;$('generation-timeout').value=s.generation_timeout;$('max-cloud-requests').value=s.max_cloud_requests || 1;$('max-model-calls').value=s.max_model_calls;$('max-analysis-cost').value=s.max_analysis_cost
    $('vision-base').value=s.vision_base || 'http://127.0.0.1:11434/v1';$('vision-model').value=s.vision_model || '';$('vision-enabled').checked=!!s.vision_enabled;$('vision-keep-alive').value=String(s.vision_keep_alive_minutes??5);
    $('model').value=s.model; $('judge-model').value=s.judge_model; $('wechat-path').value=s.wechat_path || ''; $('context').value=s.context; $('memory').checked=s.junshi_layer; $('startup').checked=!!s.start_at_login; $('target-name').value=s.reply_target?s.reply_target_name:''; $('custom-style').value=s.style || ''
  }
  function updateContext() {
    if(!st)return
    const s=mode==='manual' && manualPrefs ? manualPrefs : st.settings
    if(document.activeElement!==$('relationship'))$('relationship').value=s.relationship
    document.querySelectorAll('[data-tone]').forEach(b => b.setAttribute('aria-pressed',String(s.style===tones[b.dataset.tone])))
    $('contact').textContent=mode==='manual'?'这段聊天':(st.session || '等待会话')
    $('subtitle').textContent=mode==='manual'?'核对文字后，选一句最像你的回复':(st.session?'只看当前会话，不替你发送':'打开微信里的联系人，军师会跟上')
    $('preference-note').textContent=mode==='manual'?'关系和语气用于这次回复':'关系与语气会为这个联系人记住'
  }
  function emptyAdvice() {
    let title='下一句，交给军师帮你想',subtitle='有新消息时，这里会出现合适的回复',action=''
    if(mode==='manual'){title='把对话贴进来就好';subtitle='不用截图，不用等微信识别'}
    else if(!st?.settings.has_key){title='先连接你的 DeepSeek 账户';subtitle='密钥在本机加密保存；视觉内容按所选接口处理'}
    else if(st?.settings.paused){title='想用的时候，再开始';subtitle='暂停时不再读取新的消息'}
    else if(st?.engine.status==='minimized'){title='微信收起来了';subtitle='军师也歇一会，不会把微信弹出来'}
    else if(st?.engine.status==='no-window'){title='等你打开微信';subtitle='也可以切到“粘贴聊天”直接使用';action='<button data-act="launch" class="small" style="margin-top:10px">打开微信</button>'}
    else if(st?.analysis_inflight){title='正在帮你想回复';subtitle='先看语境，再准备合适的说法，你可以继续聊天'}
    else if(st?.analysis_error){title='这次没有生成成功';subtitle=friendly(st.analysis_error);action='<button data-act="regenerate" class="small" style="margin-top:10px">再试一次</button>'}
    return `<div class="panel empty"><div class="symbol" aria-hidden="true">✦</div><h2>${escape(title)}</h2><div class="muted">${escape(subtitle)}</div>${action}</div>`
  }
  function renderAdvice(a) {
    view=a; dirty=false; pending=null; pendingManualSeq=null; $('new-advice').hidden=true
    if(a?.media_pending && !(a.warnings||[]).some(w=>w.includes('媒体')))a={...a,warnings:[...(a.warnings||[]),'媒体尚未理解，建议仅依据可用文字']}
    const cacheInfo=!!(a?.cache_hit||a?.coalesced);const warnings=(a?.warnings||[]).filter(w=>!cacheInfo||!String(w).startsWith('复用'))
    $('cache-note').hidden=!cacheInfo;$('cache-note').textContent=cacheInfo?'已复用相同内容的已核验回复，这次没有新增模型调用':''
    $('analysis-warning').hidden=!warnings.length;$('analysis-warning-text').textContent=warnings.join('；')
    if(!a?.candidates?.length){$('advice').innerHTML=emptyAdvice();$('reply-tools').hidden=true;return}
    $('reply-tools').hidden=false
    const ranked=(a.rank_ok!==false || a.selection_method==='first_verified') && Number.isInteger(a.best_index)
    const order=a.candidates.map((_,i)=>i).sort((x,y)=>(x===a.best_index?-1:y===a.best_index?1:x-y))
    const card=i=>`<article class="reply-card ${ranked&&i===a.best_index?'best':''}"><div class="label"><span class="tag">${ranked&&i===a.best_index?'推荐这句':'也可以这样说'}</span><span class="reply-edit-hint" data-edit="${i}">可直接修改</span></div><label class="sr-only" for="reply-${i}">回复 ${i+1}</label><textarea class="reply" id="reply-${i}" data-index="${i}" maxlength="2000" rows="3">${escape(a.candidates[i])}</textarea><div class="row actions">${mode==='live'?`<button data-act="fill" data-index="${i}" class="primary">填入微信</button>`:''}<button data-act="copy" data-index="${i}" class="${mode==='manual'?'primary':'quiet'}">复制</button><span class="hint" data-done="${i}"></span></div></article>`
    const rows=(a.judgment || []).map(r=>`<div class="evidence"><b>${escape(r.label)}</b><p>${escape(r.value)}</p>${r.evidence?`<div class="muted">依据：${escape(r.evidence)}</div>`:''}</div>`).join('')
    const intent=(a.judgment || []).find(r=>r.label==='意图')
    $('advice').innerHTML=`${intent?`<div class="reason">${escape(intent.value)}</div>`:''}${card(order[0])}${order.length>1?`<details id="alternatives"><summary>再看另外 ${order.length-1} 种说法</summary>${order.slice(1).map(card).join('')}</details>`:''}<details><summary>为什么这样建议</summary><div class="panel">${a.best_reason?`<p class="reason">${escape(a.best_reason)}</p>`:''}${rows || '<p class="muted">暂无明确判断依据</p>'}${(a.warnings || []).map(w=>'<p class="hint">'+escape(w)+'</p>').join('')}${(a.extension_notes || []).map(n=>'<p class="hint">扩展提示：'+escape(n.note)+'</p>').join('')}</div></details>`
    theme(); updateFillAvailability();showStale()
  }
  function updateFillAvailability() {
    updateLiveActions()
    const valid=mode==='live' && st && !st.settings.paused && !inRequest && !st.analysis_inflight && st.engine.status==='capturing' && st.engine.title_ready!==false && view?.ts===st.analysis?.ts && view?.session===st.session && view?.source_signature===st.source_signature && !!st.analysis && !st.analysis.expired && failures===0
    document.querySelectorAll('[data-act=fill]').forEach(b=>{b.disabled=!valid;b.title=valid?'填入后由你手动发送':st?.engine.status==='minimized'?'展开微信后可填入，现在仍可复制':'当前建议已更新、暂停或会话未就绪，仍可复制'})
  }
  function updateLiveActions() {
    $('live-actions').hidden=mode!=='live'
    const s=st?.settings, e=st?.engine
    const message=(st?.messages || []).filter(m=>!['system','time'].includes(m.kind)).at(-1)
    const ready=!!s?.has_key && !s.paused && e?.status==='capturing' && e.title_ready!==false && !!st?.session && !!message && !st.analysis_inflight && !inRequest && failures===0
    $('live-reply').disabled=!ready
    $('live-reply').textContent=st?.analysis_inflight?'正在想回复…':st?.analysis?'重新帮我回复':'帮我回复'
    const text=(message?.text || '').trim() || '['+(kindLabels[message?.kind] || '内容待识别')+']'
    $('live-message').textContent=message?'最近读到 · '+(message.from==='me'?'我':message.name || '对方')+'：'+text.slice(0,160):'还没读到聊天内容'
    $('live-help').textContent=failures?'正在恢复连接':!s?.has_key?'先在设置中保存密钥':s.paused?'点上方“开始”读取微信':e?.status==='no-window'?'打开微信和要回复的会话':e?.status==='minimized'?'展开微信后继续':e?.title_ready===false?'正在确认当前会话':st?.analysis_inflight?'你可以继续查看聊天':!ready?'等待识别，请保持聊天窗口可见':'核对上面的消息，再点按钮生成'
  }
  function updateState(next) {
    st=next;$('harness-status').textContent='调度状态：'+(st.harness?.state || '等待')+' · '+(st.harness?.version || '')+' · 不开放终端工具'; updateContext();updateReadback();updateMembers();updateProgress();showErrors();showStale()
    if(mode==='manual'&&inRequest&&activeManualSequence===manualSeq&&st.manual_preview?.request_id===activeManualRequest&&previewSeenRequest!==activeManualRequest){previewSeenRequest=activeManualRequest;const a=st.manual_preview.result;if(view&&(dirty||document.activeElement?.classList.contains('reply'))){pending=a;pendingManualSeq=activeManualSequence;$('new-advice').hidden=false}else renderAdvice(a)}
    const s=st.settings, status=st.engine.status
    $('pause').hidden=!s.has_key; $('pause').textContent=s.paused?'开始':'暂停'
    updateManualInput();$('key-status').textContent=s.has_key?'已保存账户密钥':'尚未设置账户密钥'
    setStatus(mode==='manual'?(inRequest?'正在准备回复':'粘贴聊天'):!s.has_key?'等待设置':s.paused?'已暂停':st.analysis_inflight?'正在想回复':status==='capturing'?'跟随中':status==='minimized'?'微信已最小化':status==='no-window'?'等待微信':status==='locating'||status==='no-area'?'正在定位消息区':'准备中',!s.paused&&status==='capturing')
    $('welcome').hidden=true
    if(!s.has_key && !settingsOpen){$('welcome').hidden=false;$('welcome').innerHTML='<h2>两步就能开始</h2><p class="muted">保存 DeepSeek 密钥，再打开要回复的微信会话。分析文字会通过 DeepSeek 处理并产生 API 费用。</p><button data-act="setup-key" class="primary">设置密钥</button>'}
    else if(s.paused&&mode==='live'){ $('welcome').hidden=false; $('welcome').innerHTML='<div class="row between"><span class="muted">暂时歇一会也没关系</span><button data-act="resume" class="primary small">'+(localStorage.getItem('junshi-consent')?'继续读取':'同意并开始读取')+'</button></div><p class="hint">开启后，当前微信会话文字会发送给 DeepSeek 生成建议；发送消息仍由你决定。</p>' }
    if(mode==='live') {
      if(lastContact!==st.session){rememberDraft();lastContact=st.session;restoreDraft('live:'+st.session,null)}
      const a=st.analysis
      if(a && a.ts!==view?.ts){
        const editing=document.activeElement?.classList.contains('reply')
        if(view&&(dirty||editing)){pending=a;$('new-advice').hidden=false}
        else renderAdvice(a)
      } else if(!view) $('advice').innerHTML=emptyAdvice()
    }
    updateFillAvailability()
  }
  async function poll() {
    try{ const next=await api('/state'); failures=0;$('connection').hidden=true;updateState(next) }
    catch(e){failures++;setStatus('正在重新连接');$('connection').hidden=false;$('connection').textContent=failures<3?'连接暂时中断，正在恢复。你修改的回复会保留。':'还没连上。可从托盘重新打开或重启军师；当前文字不会被清空。';updateFillAvailability();updateManualInput()}
    finally{setTimeout(poll,document.hidden?5000:1200)}
  }
  let preferenceBusy=false
  function setPreferenceBusy(value){preferenceBusy=value;$('relationship').disabled=value;document.querySelectorAll('[data-tone]').forEach(b=>b.disabled=value)}
  async function changePreferences(patch) {
    if(preferenceBusy)return
    const current=mode==='manual'?{...st?.settings,...manualPrefs}:st?.settings
    if(current&&Object.entries(patch).every(([key,value])=>current[key]===value)){tell('正在使用这个偏好');return}
    if(mode==='manual') {
      cancelManualRequest();invalidateManualEvidence();manualPrefs ||= {relationship:st?.settings.relationship || '朋友',style:st?.settings.style || ''}
      for(const key of ['relationship','style'])if(key in patch){manualPrefs[key]=patch[key];delete patch[key]}
      if(!Object.keys(patch).length){updateContext();showStale();tell('偏好已更新，重新分析后生效');return}
    }
    const requestMode=mode,requestSession=st?.session
    setPreferenceBusy(true)
    const scoped=requestMode==='live'&&Object.keys(patch).some(key=>['relationship','style'].includes(key))
    try{
      const body=scoped?{...patch,expected_session:requestSession || ''}:patch
      const saved=await api('/settings',body)
      if(mode!==requestMode||scoped&&st?.session!==requestSession){tell('设置已处理，请核对当前会话的偏好');return}
      if(st)Object.assign(st.settings,patch);updateContext()
      if(saved.contact_preferences_saved===false){tell('本次偏好已生效，但未能记住；切换联系人后请重新选择');return}
      // The backend already schedules changed settings; do not force a second pass.
      tell(requestMode==='live'&&st?.session&&!st.settings.paused?'偏好已保存，正在按新设置准备回复':'设置已保存')
    }catch(error){if(mode===requestMode&&(!scoped||st?.session===requestSession)){$('relationship').value=st?.settings.relationship || '朋友';updateContext()}throw error}
    finally{setPreferenceBusy(false)}
  }
  function parseTranscript(text) {
    const messages=[]
    for(const line of text.split(/\r?\n/).filter(x=>x.trim())) {
      const m=line.match(/^\s*(我|对方|me|her)(?:（([^）]+)）)?\s*[:：]\s*(.+)$/i)
      if(m){const text=m[3].trim();const media=text.match(/^\[(图片|视频|表情包|未知媒体)\]$/);messages.push({from:/^(我|me)$/i.test(m[1])?'me':'her',text:media?'':text,...(m[2]?{name:m[2]}:{}),...(media?{kind:{图片:'image',视频:'video',表情包:'sticker',未知媒体:'media_unknown'}[media[1]]}:{})})}
      else if(messages.length)messages[messages.length-1].text+='\n'+line.trim()
      else throw new Error('请在第一段前标注“我：”或“对方：”')
    }
    if(!messages.length)throw new Error('先粘贴一段聊天')
    return messages
  }
  // Pending manual suggestions belong to the source/preferences sequence that produced them.
  function clearManualPending() {
    pending=null;pendingManualSeq=null;$('new-advice').hidden=true
    const saved=drafts.get('manual');if(saved){saved.pending=null;saved.pendingManualSeq=null}
  }
  function invalidateManualEvidence() {
    manualSeq++;manualStale=!!view;manualResult=null;clearManualPending();drafts.delete('manual')
  }
  let activeManualRequest=null,activeManualSequence=0,previewSeenRequest=null,manualStartedAt=0,manualController=null;
  function cancelManualRequest(notify=false) {
    if(!manualController)return
    const identity=activeManualRequest;manualSeq++;clearManualPending();manualController.abort();manualController=null
    activeManualRequest=null;activeManualSequence=0;inRequest=false;manualStartedAt=0
    $('analyze').disabled=false;$('analyze').textContent='分析并生成回复';updateProgress();updateFillAvailability()
    api('/cancel-manual',{request_id:identity}).catch(()=>{if(notify)tell('已停止显示这次结果；服务端取消未确认，可能仍有已开始的请求')})
    if(notify)tell('已请求停止生成，输入和修改的回复会保留')
  }
  async function analyzeText(forceFresh=false) {
    if(inRequest)return
    if(!st?.settings.has_key){tell('先在设置里保存密钥');return}
    const messages=parseTranscript($('transcript').value)
    manualError='';clearManualPending();document.querySelector('[data-act=retry-request]').hidden=false;showErrors()
    const seq=++manualSeq;activeManualSequence=seq;activeManualRequest=crypto.randomUUID();manualStartedAt=Date.now();manualController=new AbortController();const controller=manualController; inRequest=true;$('analyze').disabled=true;$('analyze').textContent='正在想回复…';updateProgress()
    try{
      const a=await api('/analyze-text',{messages,relationship:$('relationship').value,style:manualPrefs?.style ?? st.settings.style,reply_to:$('manual-target').value,force_fresh:forceFresh,request_id:activeManualRequest},controller.signal)
      if(seq!==manualSeq)return
      manualResult=a;const keepEdit=mode==='manual'&&view&&(dirty||document.activeElement?.classList.contains('reply'));manualStale=!!keepEdit;if(keepEdit){pending=a;pendingManualSeq=seq;$('new-advice').hidden=false}else{drafts.delete('manual');if(mode==='manual')renderAdvice(a)}
    }catch(error){if(seq!==manualSeq||controller.signal.aborted)return;manualError=friendly(error);showErrors();throw error}finally{if(manualController===controller){manualController=null;activeManualRequest=null;inRequest=false;updateProgress();$('analyze').textContent='分析并生成回复';updateManualInput()}}
  }
  document.addEventListener('input',e=>{
    if(e.target.classList.contains('reply')){
      // 任一候选框与原文不同就算 dirty：只比当前框会把 A 框的修改
      // 在还原 B 框时误判为“没有修改”，导致新建议横幅与覆盖保护失效。
      const boxes=[...document.querySelectorAll('.reply')]
      dirty=!view?.candidates || boxes.some(ta=>{
        const i=Number(ta.dataset.index)
        return !Number.isInteger(i) || ta.value!==view.candidates[i]
      })
      fitReplies();const label=document.querySelector('[data-edit="'+e.target.dataset.index+'"]');if(label)label.textContent=e.target.value!==view?.candidates?.[Number(e.target.dataset.index)]?'已修改 · 会使用你的文字':'可直接修改'
    }
    if(e.target.id==='transcript'){cancelManualRequest();invalidateManualEvidence();showStale();updateManualInput()}})
  document.addEventListener('change',async e=>{
    try{
      if(e.target.id==='manual-target'){cancelManualRequest();invalidateManualEvidence();showStale();tell('回复对象已选择，重新分析后生效')}
      if(e.target.id==='relationship')await changePreferences({relationship:e.target.value})
      if(e.target.id==='theme'||e.target.id==='font-size'){preferences.theme=$('theme').value;preferences.font=$('font-size').value;localStorage.setItem('junshi-display',JSON.stringify(preferences));theme()}
      if(e.target.id==='harness-enabled'){try{await api('/settings',{harness_enabled:e.target.checked});tell('调度设置已保存')}catch(err){e.target.checked=!e.target.checked;throw err}}
      if(e.target.id==='startup'){try{await api('/startup',{enabled:e.target.checked});tell(e.target.checked?'以后开机在后台等你':'已关闭开机启动')}catch(err){e.target.checked=!e.target.checked;throw err}}
    }catch(err){tell(friendly(err))}
  })
  $('pause').addEventListener('click',async()=>{try{if(!st)return;await api(st.settings.paused?'/resume':'/pause',{});localStorage.setItem('junshi-consent','1');tell(st.settings.paused?'开始跟随微信':'已暂停，新消息不会再读取')}catch(e){tell(friendly(e))}})
  document.addEventListener('click',async e=>{
    const button=e.target.closest('[data-act]'); if(!button || button.disabled)return
    const act=button.dataset.act
    try{
      if(act==='open-drawer'){openDrawer(button.dataset.view);return}
      if(act==='close-drawer'){closeDrawer();return}
      if(act==='attach-media-job'){
        if(!importedMediaJob){$('media-error').textContent='请先完成文件理解';return}
        const rows=(st?.messages || []).filter(m=>['media_unknown','video','audio'].includes(m.kind));
        if(!rows.length){$('media-error').textContent='当前没有可关联的可见语音或视频消息；可以先核对媒体类型或使用手动聊天';return}
        const dialog=document.createElement('dialog');dialog.style.width='min(500px,95vw)';dialog.innerHTML='<h2>确认文件对应的消息</h2><p>请选择实际所属的微信消息。应用不会自动判断文件属于谁。此操作只确认文件关联，转写和视频抽样仍需核对。</p><select id=attach-target><option value="">请选择</option></select><label class=field><input id=attach-confirm type=checkbox> 我确认该文件对应所选消息</label><button id=attach-save>关联并重新分析</button><button id=attach-cancel>取消</button><p id=attach-error class=error></p>';
        for(const m of rows)dialog.querySelector('#attach-target').add(new Option((m.sequence || '')+' · '+(m.from==='me'?'我':m.name || '发言人待确认')+' · '+(m.text || kindLabels[m.kind]),m.message_id));
        const selectedSession=st.session;dialog.querySelector('#attach-cancel').onclick=()=>dialog.remove();dialog.querySelector('#attach-save').onclick=async()=>{try{const id=dialog.querySelector('#attach-target').value;if(!id||!dialog.querySelector('#attach-confirm').checked)throw Error('请明确确认文件关联');await api('/attach-media',{session:selectedSession,message_id:id,job_id:importedMediaJob.id});dialog.remove();readbackSignature='';tell('文件已关联；转写和抽样仍保留未核对标记')}catch(error){dialog.querySelector('#attach-error').textContent=friendly(error)}};document.body.append(dialog);dialog.showModal();return
      }
      if(act==='confirm-memory'){
        const fact=prompt('填写你确认的事实。不会自动把模型推测写进记忆。');if(!fact?.trim())return;await api('/memory-confirm',{session:st.session,fact:fact.trim()});tell('已保存用户确认的事实');return
      }
      if(act==='import-media'){
        const file=$('media-file').files[0];if(!file)throw new Error('请先选择文件');if(file.size>20*1024*1024)throw new Error('文件不能超过20MB');
        button.disabled=true;$('media-error').textContent='';$('media-result').textContent='';$('media-work').textContent='正在导入文件';
        try{
          const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file)});
          const created=await api('/media-file',{name:file.name,data});
          for(let count=0;count<360;count++){
            const {job}=await api('/media-job',{id:created.id});$('media-work').textContent=job.phase==='vision'?'正在理解抽样画面':'正在解码与转写语音';
            if(job.state==='error')throw new Error(job.error);if(job.state==='expired')throw new Error('任务记录已过期');
            if(job.state==='done'){
              importedMediaJob={id:created.id};
              $('media-work').textContent='完成，用时 '+job.seconds+' 秒';const result=job.result;
              $('media-result').innerHTML='<p class=hint>'+escape(result.coverage)+'</p>'+(result.transcript || []).map(segment=>'<p>'+escape(segment.start+'–'+segment.end+'秒：'+segment.text+(segment.uncertain?'（待核对）':''))+'</p>').join('')+(result.visual_samples || []).map(frame=>'<p>'+escape(frame.second+'秒画面：'+(frame.description || '未知'))+'</p>').join('')+'<p class=hint>'+escape((result.warnings || []).join('；'))+'</p>';break
            }
            await new Promise(resolve=>setTimeout(resolve,1000));if(count===359)throw new Error('等待超时，可稍后重试')
          }
        }catch(error){$('media-error').textContent=friendly(error);$('media-work').textContent='处理未完成，可重试'}finally{button.disabled=false}return
      }
      if(act==='show-evidence'){
        const message=readbackMessages[Number(button.dataset.row)];const data=await api('/evidence',{crop_id:message.evidence.crop_id});
        if(!data.image){tell('原图已离开缓存，可重新识别');return}
        const dialog=document.createElement('dialog');dialog.style.maxWidth='95vw';
        const image=document.createElement('img');image.src='data:image/jpeg;base64,'+data.image;image.style.maxWidth='85vw';dialog.append(image);
        const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>dialog.remove();dialog.append(close);document.body.append(dialog);dialog.showModal();return
      }
      if(act==='correct-observation'){
        const m=readbackMessages[Number(button.dataset.row)];if(!m?.message_id){tell('请等待重新读取');return}
        const dialog=document.createElement('dialog');dialog.style.width='min(500px,95vw)';dialog.style.background='var(--surface)';dialog.style.color='var(--text)';
        dialog.innerHTML='<h2>核对这条消息</h2><label class=field>文字内容</label><textarea id=correct-text rows=4></textarea><label class=field>显示昵称</label><input id=correct-name><label class=field>消息类型</label><select id=correct-kind></select><label class=field>发言人关联</label><select id=correct-person><option value="">暂不确认唯一身份</option></select><p class=hint>只有你确认是同一个人后才关联。昵称与头像相同不代表唯一账号。</p><div class=row><button id=correct-save>保存并重新分析</button><button id=correct-close>取消</button></div><p id=correct-error class=error></p>';
        document.body.append(dialog);dialog.querySelector('#correct-text').value=m.text || '';dialog.querySelector('#correct-name').value=m.name || '';
        const kinds=dialog.querySelector('#correct-kind');for(const [value,label] of Object.entries(kindLabels)){const o=new Option(label,value);kinds.add(o)}kinds.value=m.kind || 'text';
        const person=dialog.querySelector('#correct-person');person.add(new Option('我（当前账号）','self'));for(const member of st.participants || [])person.add(new Option((member.name || '未知')+' · '+member.id.slice(0,8),member.id));
        dialog.querySelector('#correct-close').onclick=()=>dialog.remove();dialog.querySelector('#correct-save').onclick=async()=>{try{const patch={text:dialog.querySelector('#correct-text').value,name:dialog.querySelector('#correct-name').value,kind:kinds.value};if(person.value)patch.speaker_id=person.value;await api('/correct-message',{session:m.session,message_id:m.message_id,patch});dialog.remove();readbackSignature='';tell('已保存更正，旧建议已作废')}catch(error){dialog.querySelector('#correct-error').textContent=friendly(error)}};dialog.showModal();return
      }
      if(act==='save-budget'){await api('/settings',{generation_timeout:Number($('generation-timeout').value),max_cloud_requests:Number($('max-cloud-requests').value),max_model_calls:Number($('max-model-calls').value),max_analysis_cost:Number($('max-analysis-cost').value)});tell('预算已保存');return}
      if(act==='add-model'){
        const previous=await api('/models');const id=$('route-id').value.trim();const models=previous.models.filter(m=>m.id!==id);models.push({id,model:$('route-model').value.trim(),base:$('route-base').value.trim(),roles:[$('route-role').value],enabled:true,max_request_cost:Number($('route-cost').value)});
        const keys={};if($('route-key').value)keys[id]=$('route-key').value;await api('/models',{models,keys});$('route-key').value='';await refreshModels();tell('协作模型已保存');return
      }
      if(['route-toggle','route-first','route-delete'].includes(act)){const data=await api('/models');let rows=data.models;const id=button.dataset.route;if(act==='route-toggle')rows=rows.map(m=>m.id===id?{...m,enabled:!m.enabled}:m);if(act==='route-first')rows=[...rows.filter(m=>m.id===id),...rows.filter(m=>m.id!==id)];if(act==='route-delete')rows=rows.filter(m=>m.id!==id);await api('/models',{models:rows});await refreshModels();return}
      if(act==='save-vision'){
        const patch={vision_base:$('vision-base').value.trim(),vision_model:$('vision-model').value.trim(),vision_enabled:$('vision-enabled').checked,vision_keep_alive_minutes:Number($('vision-keep-alive').value)}
        if(patch.vision_enabled&&!patch.vision_model){tell('请先填写支持图片的模型名');return}
        if($('vision-key').value.trim()){await api('/vision-key',{key:$('vision-key').value.trim()});$('vision-key').value=''}
        await api('/settings',patch);$('vision-status').textContent='已保存；有新媒体时会按此设置处理';return
      }
      if(act==='discover-vision'){
        const patch={vision_base:$('vision-base').value.trim()};await api('/settings',patch)
        const result=await api('/vision-models');const models=result.models.filter(m=>m.vision)
        $('vision-model-list').innerHTML=models.map(m=>`<option value="${escape(m.name)}"></option>`).join('')
        $('vision-status').textContent=models.length?'支持视觉：'+models.map(m=>m.name).join('、'):'本机未安装支持图片的模型';if(models.length===1)$('vision-model').value=models[0].name;return
      }
      if(act==='verify-extension'){await api('/verify-extension',{id:button.dataset.extensionId});document.querySelector('[data-act=load-extensions]').click();tell('当前代码已通过验证，修改后需重新验证');return}
      if(act==='load-extensions'){
        const data=await api('/extensions');$('extension-list').innerHTML='<p class=hint>只启用已审阅且可信的本地代码。子进程用于故障隔离，并非操作系统安全沙箱。</p>'+data.extensions.map(x=>`<label class=field><input type=checkbox data-extension="${escape(x.id)}" ${!x.verified?'disabled':''} ${data.enabled.includes(x.id)&&x.verified?'checked':''}>${escape(x.name)} · ${x.verified?'已验证':'待验证'}</label><p class=hint>${escape(x.description)} · ${escape(x.permissions.join('/'))}</p><button data-act=verify-extension data-extension-id="${escape(x.id)}">验证当前代码</button>`).join('');return
      }
      if(act==='legacy-load-extensions'){
        const result=await api('/extensions');$('extension-list').innerHTML=result.extensions.length?result.extensions.map(x=>`<label class="field"><input type="checkbox" data-extension="${escape(x.id)}" ${result.enabled.includes(x.id)?'checked':''}> ${escape(x.name)}</label><p class="hint">${escape(x.description)}</p>`).join(''):'<p class="hint">尚未安装扩展。请按扩展开发包的说明安装。</p>';return
      }
      if(act==='save-extensions'){await api('/settings',{enabled_extensions:Array.from(document.querySelectorAll('[data-extension]:checked'),e=>e.dataset.extension)});tell('扩展设置已保存，下次分析生效');return}
      if(act==='setup-key'){openSettings(true);return}
      if(act==='correct-context'){
        if(!readbackMessages.length){tell('尚未读到消息');return}
        const text=readbackMessages.map(m=>(m.from==='me'?'我':m.name?'对方（'+m.name+'）':'对方')+'：'+(mediaLabels[m.kind]?'['+mediaLabels[m.kind]+']':m.text)).join('\n')
        closeDrawer();document.querySelector('.switcher [data-act=manual]').click();$('transcript').value=text;$('transcript').dispatchEvent(new Event('input',{bubbles:true}));$('transcript').focus();tell('请修正文字和媒体类型，再点分析');return
      }
      if(act==='retry-request'){if(mode==='manual')await analyzeText();else {liveError='';await api('/regenerate',{})}return}
      if(act==='settings'){openSettings();return}
      if(act==='close-settings'){$('settings').close();return}
      if(act==='example'){if(!$('transcript').value.trim()){$('transcript').value='对方：明天有空吗？\n我：下午有空\n对方：那几点见？';$('transcript').dispatchEvent(new Event('input',{bubbles:true}));$('transcript').focus()}return}
      if(act==='undo-clear'){if(clearedTranscript&&!$('transcript').value.trim()){$('transcript').value=clearedTranscript;clearedTranscript='';$('transcript').dispatchEvent(new Event('input',{bubbles:true}));$('transcript').focus();tell('已恢复清空前的文字')}return}
      if(act==='live'||act==='manual'){if(mode===act)return;if(mode==='manual')cancelManualRequest();rememberDraft();mode=act;if(mode==='manual')manualPrefs ||= {relationship:st?.settings.relationship || '朋友',style:st?.settings.style || ''};document.querySelectorAll('.switcher button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.act===mode)));$('manual').hidden=mode!=='manual';if(mode==='live')lastContact=st?.session || '';showErrors();updateProgress();restoreDraft(mode==='manual'?'manual':'live:'+lastContact,mode==='manual'?manualResult:st?.analysis);updateContext();if(st)updateState(st);return}
      if(act==='tone'){await changePreferences({style:tones[button.dataset.tone]});return}
      if(act==='resume'){await api('/resume',{});localStorage.setItem('junshi-consent','1');tell('开始跟随微信');return}
      if(act==='launch'){await api('/launch-wechat',{});tell('正在打开微信');return}
      if(act==='latest'){
        if(pending){
          if(mode==='manual'&&pendingManualSeq!==manualSeq){clearManualPending();tell('原文或偏好已变化，请重新分析');return}
          if(mode==='manual'){manualStale=false;manualResult=pending}
          drafts.delete(draftKey);renderAdvice(pending)
        }
        return
      }
      if(act==='analyze'){await analyzeText();return}
      if(act==='cancel-manual'){cancelManualRequest(true);return}
      if(act==='clear-text'){cancelManualRequest();manualSeq++;clearedTranscript=$('transcript').value;$('transcript').value='';manualResult=null;manualStale=false;manualError='';drafts.delete('manual');renderAdvice(null);showErrors();updateManualInput();$('transcript').focus();tell('已清空，可点“撤销清空”恢复');return}
      if(act==='regenerate'){if(mode==='manual'){await analyzeText(true)}else{button.disabled=true;try{await api('/regenerate',{});tell('正在换一组回复')}finally{button.disabled=false}}return}
      if(act==='fill'||act==='copy'){
        const index=Number(button.dataset.index),text=$('reply-'+index).value.trim()
        if(!text){tell('回复还是空的');return}
        button.disabled=true
        try{
          if(act==='fill'){
            if(inRequest)return
            inRequest=true;updateFillAvailability()
            await api('/fill',{index,text,analysis_ts:view.ts})
            const done=document.querySelector(`[data-done="${index}"]`);if(done)done.textContent='已填入，记得自己发送'
            tell('已填入微信，发送由你自己决定')
          }else{try{await navigator.clipboard.writeText(text)}catch(_){await api('/copy-text',{text})}const done=document.querySelector(`[data-done="${index}"]`);if(done)done.textContent='已复制，可切回微信粘贴';tell('已复制，切回微信粘贴即可')}
        }catch(error){
          if(act==='fill'){
            const done=document.querySelector(`[data-done="${index}"]`);if(done)done.textContent='填入未成功，可点“复制”手动粘贴'
            const copy=button.closest('.reply-card')?.querySelector('[data-act=copy]');if(copy){copy.classList.remove('quiet');copy.classList.add('primary');copy.focus()}
          }
          if(act==='copy'){
            const done=document.querySelector(`[data-done="${index}"]`);if(done)done.textContent='复制未成功，可再次点“复制”，或选中文字手动复制'
            button.disabled=false;button.focus()
          }
          tell(friendly(error))
        }finally{button.disabled=false;if(act==='fill')inRequest=false;updateFillAvailability()}
        return
      }
      if(act==='save-key'){const key=$('key').value.trim();if(!key){tell('先填入密钥');$('key').focus();return}await api('/key',{key});$('key').value='';tell('密钥已加密保存，点“开始”即可使用');return}
      if(act==='delete-key'){if(!confirm('删除密钥会暂停读取，之后需要重新填写。确定删除？'))return;await api('/key-delete',{});tell('密钥已删除，读取已暂停');return}
      if(act==='save-advanced'){await changePreferences({model:$('model').value.trim(),judge_model:$('judge-model').value.trim(),wechat_path:$('wechat-path').value.trim(),context:Number($('context').value),junshi_layer:$('memory').checked,reply_target:!!$('target-name').value.trim(),reply_target_name:$('target-name').value.trim(),style:$('custom-style').value.trim()});return}
      if(act==='clear-memory'){if(!confirm('确定清空当前会话记忆？此操作无法撤销。'))return;await api('/memory-clear',{});tell('当前会话记忆已清空');return}
      if(act==='quit'){await api('/shutdown',{});$('connection').hidden=false;$('connection').textContent='军师已退出，可以关闭窗口。';window.__junshiStopped=true;return}
    }catch(err){if(['save-vision','discover-vision','add-model','save-budget'].includes(act))$('vision-status').textContent=friendly(err);if(['analyze','regenerate','retry-request','save-key','save-advanced'].includes(act)){if(mode==='manual')manualError=friendly(err);else liveError=friendly(err);$('request-error').hidden=false;$('request-error-text').textContent=friendly(err);document.querySelector('[data-act=retry-request]').hidden=['save-key','save-advanced'].includes(act)}tell(friendly(err));
      // 保存失败时把设置表单重置回后端真实状态，避免 UI 长期漂移。
      if(['save-advanced','save-budget','save-vision','save-extensions','add-model'].includes(act)){try{initializeSettings()}catch(_){}}}
  })
  // 版本号与引擎保持一致：从 /capabilities 动态读取，避免面板版本滞后
  api('/capabilities').then(caps => {
    const el = document.getElementById('app-version')
    if (el && caps && caps.app_version) el.textContent = caps.app_version + ' · 证据与模型协作'
  }).catch(() => {})
  // Expose only a parser for offline DOM regression tests; no user data or credentials.
  window.__junshiParseTranscript=parseTranscript
  const originalPoll=poll
  poll=async()=>{if(!window.__junshiStopped)await originalPoll()}
  poll()
})()


