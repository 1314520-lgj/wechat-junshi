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
    :root{color-scheme:dark;--bg:#141619;--surface:#1d2025;--card:#24282e;--line:#353b43;--text:#f0f2f5;--muted:#aeb6c0;--accent:#59d2a6;--button:#23855f;--shadow:0 14px 48px #0003}
    :root[data-theme=light]{color-scheme:light;--bg:#f3f5f5;--surface:#fff;--card:#f3f5f5;--line:#d8dfe0;--text:#202b30;--muted:#5f6d72;--accent:#17764f;--button:#18764f;--shadow:0 14px 48px #263c4110}
    *{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);overflow:auto;font:15px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif}
    body{padding:22px 16px}button,input,select,textarea{font:inherit}button{cursor:pointer}button:disabled{opacity:.45;cursor:default}button:focus-visible,select:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
    button{border:1px solid var(--line);border-radius:12px;padding:8px 14px;color:var(--text);background:var(--card);transition:background .15s}button:hover:not(:disabled){filter:brightness(1.1)}button.primary{background:var(--button);color:#fff;border-color:var(--button);font-weight:600}button.quiet{background:transparent}button.small{padding:5px 10px;font-size:13px}button.danger{color:#f18c8c}
    main{max-width:620px;margin:auto}header{display:flex;align-items:center;gap:12px;margin-bottom:18px}.mark{width:40px;height:40px;border-radius:13px;background:var(--button);display:grid;place-items:center;font-size:22px;font-weight:600;color:white}h1{font-size:20px;line-height:1.4;margin:0;letter-spacing:1px}.version{font-size:11px;color:var(--muted)}header .spacer{flex:1}h2{font-size:18px;margin:0 0 8px}.muted,.hint{color:var(--muted);font-size:13px}.hint{margin:8px 0 0}.status{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}.dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}.dot.active{background:var(--accent)}
    .panel{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:19px;margin-bottom:14px;box-shadow:var(--shadow)}.row{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.row.between{justify-content:space-between}.row.actions{margin-top:12px}.pills{display:flex;gap:6px}.pills button[aria-pressed=true]{background:var(--button);color:white;border-color:var(--button)}.switcher{display:flex;gap:6px;margin-bottom:18px}.switcher button{flex:1;background:transparent}.switcher button[aria-pressed=true]{background:var(--surface);border-color:var(--accent)}
    input,select,textarea{background:var(--card);border:1px solid var(--line);border-radius:10px;color:var(--text);padding:9px 11px;max-width:100%}select{min-width:110px}input[type=checkbox]{accent-color:var(--accent)}input[type=password],input[type=text]{width:100%}textarea{width:100%;resize:vertical;line-height:1.7;font-size:16px}textarea.reply{background:transparent;border:1px solid transparent;padding:4px 0;min-height:84px;resize:none}textarea.reply:focus{background:var(--card);border-color:var(--line);padding:4px 8px}.reply-card{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:16px;margin:12px 0}.reply-card.best{border-color:var(--accent)}.tag{font-size:11px;color:var(--accent);font-weight:600}.reply-card .label{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
    details{margin-top:12px}summary{cursor:pointer;color:var(--muted);font-size:13px;padding:7px 0}details .panel{box-shadow:none}label.field{display:block;font-size:13px;color:var(--muted);margin:13px 0 5px}.field+input,.field+select{width:100%}.reason{font-size:13px;margin:8px 0;color:var(--muted)}.evidence{padding:10px 0;border-bottom:1px solid var(--line)}.evidence:last-child{border:0}.evidence b{font-size:13px}.evidence p{margin:3px 0}.empty{padding:28px 8px;text-align:center}.empty .symbol{font-size:26px;color:var(--accent);margin-bottom:6px}.banner{padding:11px 13px;border-radius:12px;background:var(--card);margin-bottom:12px;font-size:13px}.error{color:#ffb0a8}.welcome{padding:22px}.notice{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);max-width:calc(100vw - 30px);width:max-content;padding:11px 17px;background:var(--text);color:var(--bg);border-radius:14px;box-shadow:var(--shadow);font-size:13px;z-index:20;pointer-events:none}.footer{text-align:center;font-size:11px;color:var(--muted);margin-top:20px}.subtle-link{border:0;background:transparent;color:var(--muted);padding:3px 0;text-decoration:underline;text-underline-offset:4px}#settings{display:none}#settings.open{display:block}#settings .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}[hidden]{display:none!important}
    @media(max-width:390px){body{padding:12px 10px}.panel{padding:15px}.pills button{padding:6px 9px}.row.actions button{flex:1}#settings .grid{grid-template-columns:1fr}}
    @media(prefers-reduced-motion:reduce){*{transition:none!important}}
  `
  document.head.appendChild(style)
  document.body.innerHTML = `<main>
    <header><div class="mark" aria-hidden="true">军</div><div><h1>军师</h1><div id="status" class="status" role="status"><i class="dot"></i><span>正在连接</span></div></div><span class="spacer"></span><button id="pause" class="small quiet" hidden>暂停</button><button data-act="settings" class="small quiet" aria-expanded="false" aria-controls="settings">设置</button></header>
    <section id="settings" class="panel" aria-label="设置">
      <h2>按你习惯来</h2><div class="grid"><div><label class="field" for="theme">外观</label><select id="theme"><option value="dark">深色</option><option value="light">浅色</option><option value="system">跟随系统</option></select></div><div><label class="field" for="font-size">文字</label><select id="font-size"><option value="normal">标准</option><option value="large">大一点</option></select></div></div>
      <label class="field"><input id="startup" type="checkbox"> 开机在后台启动</label><p class="hint">不自动打开窗口；想用时点桌面图标或托盘。</p>
      <details><summary>账户与高级设置</summary><label class="field" for="key">DeepSeek 密钥</label><input id="key" type="password" autocomplete="off" placeholder="需要更换时再填写"><div class="row actions"><button data-act="save-key">保存密钥</button><button data-act="delete-key" class="quiet">删除密钥</button></div>
        <label class="field" for="model">回复模型</label><input id="model" type="text"><label class="field" for="judge-model">分析模型</label><input id="judge-model" type="text"><label class="field" for="wechat-path">微信程序位置（留空自动查找）</label><input id="wechat-path" type="text"><label class="field" for="context">参考最近几条消息</label><input id="context" type="number" min="3" max="30"><label class="field"><input id="memory" type="checkbox"> 使用军师关系层和加密记忆</label><label class="field" for="target-name">群聊回复对象（不填则不指定）</label><input id="target-name" type="text" placeholder="对象名称"><label class="field" for="custom-style">补充我的说话习惯</label><input id="custom-style" type="text" placeholder="例如：不加句号，不用表情"><div class="row actions"><button data-act="save-advanced" class="primary">保存这些设置</button><button data-act="clear-memory" class="quiet">清空当前会话记忆</button></div>
      </details><div class="row actions"><button data-act="quit" class="quiet">退出军师</button><span class="version">1.1.0 · 轻松版</span></div>
    </section>
    <div id="connection" class="banner" hidden role="status"></div>
    <div class="switcher" role="group" aria-label="使用方式"><button data-act="live" aria-pressed="true">跟随微信</button><button data-act="manual" aria-pressed="false">粘贴聊天</button></div>
    <section id="welcome" class="panel welcome" hidden></section>
    <section id="context-card" class="panel"><div class="row between"><div><h2 id="contact">等待会话</h2><div id="subtitle" class="muted">打开微信里的联系人，军师会跟上</div></div></div><div class="row" style="margin-top:14px"><label class="sr-only" for="relationship">你们的关系</label><select id="relationship"><option>朋友</option><option>恋人</option><option>同学</option><option>同事</option><option>家人</option></select><div class="pills" role="group" aria-label="回复语气"><button data-act="tone" data-tone="温柔" class="small">温柔</button><button data-act="tone" data-tone="幽默" class="small">幽默</button><button data-act="tone" data-tone="简短" class="small">简短</button></div></div><p id="preference-note" class="hint">关系与语气会为这个联系人记住</p></section>
    <section id="manual" class="panel" hidden><label class="field" for="transcript" style="margin-top:0">粘贴需要回复的对话</label><textarea id="transcript" rows="6" placeholder="对方：明天有空吗？&#10;我：下午有空&#10;对方：那几点见？"></textarea><div class="row actions"><button data-act="analyze" class="primary" id="analyze">分析并生成回复</button><button data-act="clear-text" class="quiet">清空</button></div><p class="hint">每段用“我：”或“对方：”标注，最新消息放最后。点击分析会把文字发送给 DeepSeek，并产生 API 费用。</p></section>
    <div id="new-advice" class="banner" hidden>新建议已经好了，你修改的文字会保留。 <button data-act="latest" class="small">查看新建议</button></div>
    <section id="advice" aria-label="回复建议"></section>
    <div class="row between" id="reply-tools" hidden><button data-act="regenerate" class="subtle-link">换一组回复</button><span class="hint">可先改几个字，再填入或复制</span></div>
    <div class="footer">只帮你准备回复，发送由你自己决定。<br>关闭窗口后，军师在托盘里继续运行。</div>
  </main><div id="toast" class="notice" role="status" hidden></div>`
  const $ = id => document.getElementById(id)
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
  let manualPrefs = null
  let st = null, mode = 'live', view = null, manualResult = null, pending = null, dirty = false, inRequest = false, failures = 0, noticeTimer, settingsOpen = false, lastContact = '', manualSeq = 0
  const tones = {温柔:'温柔自然，先接住情绪，不肉麻',幽默:'轻松幽默，有一点调侃，不挖苦',简短:'简洁自然，尽量一句话，不展开'}
  let preferences = {theme:'dark',font:'normal'}
  try { preferences = Object.assign(preferences, JSON.parse(localStorage.getItem('junshi-display') || '{}')) } catch (_) {}
  function theme() {
    const isLight = preferences.theme === 'light' || preferences.theme === 'system' && matchMedia('(prefers-color-scheme:light)').matches
    document.documentElement.dataset.theme = isLight ? 'light' : 'dark'
    const size = preferences.font === 'large' ? '18px' : '16px'
    document.documentElement.style.setProperty('--reply-size',size)
    document.querySelectorAll('.reply').forEach(t => t.style.fontSize=size)
    $('theme').value=preferences.theme; $('font-size').value=preferences.font
  }
  theme()
  matchMedia('(prefers-color-scheme:light)').addEventListener('change',theme)
  function tell(text) { clearTimeout(noticeTimer); $('toast').textContent=text; $('toast').hidden=false; noticeTimer=setTimeout(() => $('toast').hidden=true,3800) }
  function friendly(error) {
    const s=String(error?.message || error || '')
    if (/401|密钥被拒|密钥无效/.test(s)) return '密钥暂时不可用，请在设置里检查或更换'
    if (/402|余额不足/.test(s)) return 'DeepSeek 账户余额不足，请检查账户后重试'
    if (/404|模型/.test(s)) return '模型暂时不可用，可在高级设置里修改模型名'
    if (/429|限流/.test(s)) return '请求有点多，稍等一下再试'
    return s || '暂时没成功，请稍后重试'
  }
  async function api(path,body) {
    const controller=new AbortController(); const timeout=setTimeout(() => controller.abort(),path==='/analyze-text'?240000:8000)
    try {
      const response=await fetch(API+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal})
      const result=await response.json()
      if(!response.ok || !result.ok) throw new Error(result.error || '暂时无法连接军师')
      return result
    } finally { clearTimeout(timeout) }
  }
  function setStatus(text,active=false) { const el=$('status'); if(el.dataset.label===text)return; el.dataset.label=text; el.innerHTML=`<i class="dot ${active?'active':''}"></i><span>${escape(text)}</span>` }
  function initializeSettings() {
    if(!st)return
    const s=st.settings
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
    else if(!st?.settings.has_key){title='先连接你的 DeepSeek 账户';subtitle='密钥在本机加密保存，截图不上传'}
    else if(st?.settings.paused){title='想用的时候，再开始';subtitle='暂停时不再读取新的消息'}
    else if(st?.engine.status==='minimized'){title='微信收起来了';subtitle='军师也歇一会，不会把微信弹出来'}
    else if(st?.engine.status==='no-window'){title='等你打开微信';subtitle='也可以切到“粘贴聊天”直接使用';action='<button data-act="launch" class="small" style="margin-top:10px">打开微信</button>'}
    else if(st?.analysis_inflight){title='正在帮你想回复';subtitle='先看语境，再写三种自然说法，你可以继续聊天'}
    else if(st?.analysis_error){title='这次没有生成成功';subtitle=friendly(st.analysis_error);action='<button data-act="regenerate" class="small" style="margin-top:10px">再试一次</button>'}
    return `<div class="panel empty"><div class="symbol" aria-hidden="true">✦</div><h2>${escape(title)}</h2><div class="muted">${escape(subtitle)}</div>${action}</div>`
  }
  function renderAdvice(a) {
    view=a; dirty=false; pending=null; $('new-advice').hidden=true
    if(!a?.candidates?.length){$('advice').innerHTML=emptyAdvice();$('reply-tools').hidden=true;return}
    $('reply-tools').hidden=false
    const ranked=a.rank_ok!==false && Number.isInteger(a.best_index)
    const order=a.candidates.map((_,i)=>i).sort((x,y)=>(x===a.best_index?-1:y===a.best_index?1:x-y))
    const card=i=>`<article class="reply-card ${ranked&&i===a.best_index?'best':''}"><div class="label"><span class="tag">${ranked&&i===a.best_index?'推荐这句':'也可以这样说'}</span><span>可直接修改</span></div><label class="sr-only" for="reply-${i}">回复 ${i+1}</label><textarea class="reply" id="reply-${i}" data-index="${i}" maxlength="2000" rows="3">${escape(a.candidates[i])}</textarea><div class="row actions">${mode==='live'?`<button data-act="fill" data-index="${i}" class="primary">填入微信</button>`:''}<button data-act="copy" data-index="${i}" class="${mode==='manual'?'primary':'quiet'}">复制</button><span class="hint" data-done="${i}"></span></div></article>`
    const rows=(a.judgment || []).map(r=>`<div class="evidence"><b>${escape(r.label)}</b><p>${escape(r.value)}</p>${r.evidence?`<div class="muted">依据：${escape(r.evidence)}</div>`:''}</div>`).join('')
    const intent=(a.judgment || []).find(r=>r.label==='意图')
    $('advice').innerHTML=`${intent?`<div class="reason">${escape(intent.value)}</div>`:''}${card(order[0])}<details id="alternatives"><summary>再看另外 ${Math.max(0,order.length-1)} 种说法</summary>${order.slice(1).map(card).join('')}</details><details><summary>为什么这样建议</summary><div class="panel">${a.best_reason?`<p class="reason">${escape(a.best_reason)}</p>`:''}${rows || '<p class="muted">暂无明确判断依据</p>'}</div></details>`
    theme(); updateFillAvailability()
  }
  function updateFillAvailability() {
    const valid=mode==='live' && st && !st.settings.paused && !inRequest && view?.ts===st.analysis?.ts && view?.session===st.session && !!st.analysis && failures===0
    document.querySelectorAll('[data-act=fill]').forEach(b=>{b.disabled=!valid;b.title=valid?'填入后由你手动发送':'当前建议已更新、暂停或会话未就绪，仍可复制'})
  }
  function updateState(next) {
    st=next; updateContext()
    const s=st.settings, status=st.engine.status
    $('pause').hidden=!s.has_key; $('pause').textContent=s.paused?'开始':'暂停'
    setStatus(!s.has_key?'等待设置':s.paused?'已暂停':st.analysis_inflight?'正在想回复':status==='capturing'?'跟随中':status==='minimized'?'微信已最小化':status==='no-window'?'等待微信':'准备中',!s.paused&&status==='capturing')
    $('welcome').hidden=true
    if(!s.has_key && !settingsOpen){$('welcome').hidden=false;$('welcome').innerHTML='<h2>两步就能开始</h2><p class="muted">保存 DeepSeek 密钥，再打开要回复的微信会话。分析文字会通过 DeepSeek 处理并产生 API 费用。</p><button data-act="settings" class="primary">设置密钥</button>'}
    else if(s.paused&&mode==='live'){ $('welcome').hidden=false; $('welcome').innerHTML='<div class="row between"><span class="muted">暂时歇一会也没关系</span><button data-act="resume" class="primary small">'+(localStorage.getItem('junshi-consent')?'继续读取':'同意并开始读取')+'</button></div><p class="hint">开启后，当前微信会话文字会发送给 DeepSeek 生成建议；发送消息仍由你决定。</p>' }
    if(mode==='live') {
      if(lastContact!==st.session){lastContact=st.session;renderAdvice(null)}
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
    catch(e){failures++;setStatus('正在重新连接');$('connection').hidden=false;$('connection').textContent=failures<3?'连接暂时中断，正在恢复。你修改的回复会保留。':'还没连上。可从托盘重新打开或重启军师；当前文字不会被清空。';updateFillAvailability()}
    finally{setTimeout(poll,document.hidden?5000:1200)}
  }
  async function changePreferences(patch) {
    if(mode==='manual') {
      manualPrefs ||= {relationship:st.settings.relationship,style:st.settings.style}
      for(const key of ['relationship','style'])if(key in patch){manualPrefs[key]=patch[key];delete patch[key]}
      if(!Object.keys(patch).length){updateContext();tell('这次回复会按这个偏好来');return}
    }
    await api('/settings',patch);if(st)Object.assign(st.settings,patch);updateContext()
    if(mode==='live' && st?.session && !st.settings.paused) {await api('/regenerate',{});tell('记住了，正在按这个语气准备回复')}
    else tell('记住了')
  }
  function parseTranscript(text) {
    const messages=[]
    for(const line of text.split(/\r?\n/).filter(x=>x.trim())) {
      const m=line.match(/^\s*(我|对方|me|her)\s*[:：]\s*(.+)$/i)
      if(m)messages.push({from:/^(我|me)$/i.test(m[1])?'me':'her',text:m[2].trim()})
      else if(messages.length)messages[messages.length-1].text+='\n'+line.trim()
      else throw new Error('请在第一段前标注“我：”或“对方：”')
    }
    if(!messages.length)throw new Error('先粘贴一段聊天')
    return messages
  }
  async function analyzeText() {
    if(inRequest)return
    if(!st?.settings.has_key){tell('先在设置里保存密钥');return}
    const messages=parseTranscript($('transcript').value)
    const seq=++manualSeq; inRequest=true;$('analyze').disabled=true;$('analyze').textContent='正在想回复…'
    try{
      const a=await api('/analyze-text',{messages,relationship:$('relationship').value,style:manualPrefs?.style ?? st.settings.style})
      if(seq!==manualSeq)return
      manualResult=a;if(mode==='manual')renderAdvice(a)
    }finally{inRequest=false;$('analyze').disabled=false;$('analyze').textContent='分析并生成回复'}
  }
  document.addEventListener('input',e=>{if(e.target.classList.contains('reply'))dirty=true})
  document.addEventListener('change',async e=>{
    try{
      if(e.target.id==='relationship')await changePreferences({relationship:e.target.value})
      if(e.target.id==='theme'||e.target.id==='font-size'){preferences.theme=$('theme').value;preferences.font=$('font-size').value;localStorage.setItem('junshi-display',JSON.stringify(preferences));theme()}
      if(e.target.id==='startup'){try{await api('/startup',{enabled:e.target.checked});tell(e.target.checked?'以后开机在后台等你':'已关闭开机启动')}catch(err){e.target.checked=!e.target.checked;throw err}}
    }catch(err){tell(friendly(err))}
  })
  $('pause').addEventListener('click',async()=>{try{if(!st)return;await api(st.settings.paused?'/resume':'/pause',{});localStorage.setItem('junshi-consent','1');tell(st.settings.paused?'开始跟随微信':'已暂停，新消息不会再读取')}catch(e){tell(friendly(e))}})
  document.addEventListener('click',async e=>{
    const button=e.target.closest('[data-act]'); if(!button || button.disabled)return
    const act=button.dataset.act
    try{
      if(act==='settings'){settingsOpen=!settingsOpen;$('settings').classList.toggle('open',settingsOpen);document.querySelector('header [data-act=settings]').setAttribute('aria-expanded',String(settingsOpen));if(settingsOpen){initializeSettings();$('settings').scrollIntoView({block:'start'})}return}
      if(act==='live'||act==='manual'){mode=act;if(mode==='manual')manualPrefs ||= {relationship:st?.settings.relationship || '朋友',style:st?.settings.style || ''};pending=null;dirty=false;manualSeq++;document.querySelectorAll('.switcher button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.act===mode)));$('manual').hidden=mode!=='manual';renderAdvice(mode==='manual'?manualResult:st?.analysis);updateContext();return}
      if(act==='tone'){await changePreferences({style:tones[button.dataset.tone]});return}
      if(act==='resume'){await api('/resume',{});localStorage.setItem('junshi-consent','1');tell('开始跟随微信');return}
      if(act==='launch'){await api('/launch-wechat',{});tell('正在打开微信');return}
      if(act==='latest'){if(pending)renderAdvice(pending);return}
      if(act==='analyze'){await analyzeText();return}
      if(act==='clear-text'){manualSeq++;$('transcript').value='';manualResult=null;renderAdvice(null);return}
      if(act==='regenerate'){if(mode==='manual'){await analyzeText()}else{button.disabled=true;try{await api('/regenerate',{});tell('正在换一组回复')}finally{button.disabled=false}}return}
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
          }else{try{await navigator.clipboard.writeText(text)}catch(_){await api('/copy-text',{text})}tell('已复制，切回微信粘贴即可')}
        }finally{button.disabled=false;if(act==='fill')inRequest=false;updateFillAvailability()}
        return
      }
      if(act==='save-key'){const key=$('key').value.trim();if(!key){tell('先填入密钥');$('key').focus();return}await api('/key',{key});$('key').value='';tell('密钥已加密保存，点“开始”即可使用');return}
      if(act==='delete-key'){await api('/key-delete',{});tell('密钥已删除，读取已暂停');return}
      if(act==='save-advanced'){await changePreferences({model:$('model').value.trim(),judge_model:$('judge-model').value.trim(),wechat_path:$('wechat-path').value.trim(),context:Number($('context').value),junshi_layer:$('memory').checked,reply_target:!!$('target-name').value.trim(),reply_target_name:$('target-name').value.trim(),style:$('custom-style').value.trim()});return}
      if(act==='clear-memory'){await api('/memory-clear',{});tell('当前会话记忆已清空');return}
      if(act==='quit'){await api('/shutdown',{});$('connection').hidden=false;$('connection').textContent='军师已退出，可以关闭窗口。';window.__junshiStopped=true;return}
    }catch(err){tell(friendly(err))}
  })
  // Expose only a parser for offline DOM regression tests; no user data or credentials.
  window.__junshiParseTranscript=parseTranscript
  const originalPoll=poll
  poll=async()=>{if(!window.__junshiStopped)await originalPoll()}
  poll()
})()
