'use strict';
const fs = require('fs'), path = require('path'), assert = require('assert');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = process.env.JUNSHI_ROOT ? path.resolve(process.env.JUNSHI_ROOT)
  : fs.existsSync(path.join(__dirname, 'lib', 'panel.js')) ? __dirname : path.dirname(__dirname);
const baselineRoot = process.env.JUNSHI_BASELINE ? path.resolve(process.env.JUNSHI_BASELINE) : null;
const outputDir = process.env.TEST_OUTPUT_DIR ? path.resolve(process.env.TEST_OUTPUT_DIR) : path.join(root, 'test-results');
const origin = 'http://junshi.actions', checks = [], baselineChecks = [];
const check = (name, condition) => { assert.ok(condition, name); checks.push(name); };
const baselineCheck = (name, condition) => { assert.ok(condition, name); baselineChecks.push(name); };
function advice(ts, text) {
  return { ok: true, ts, session: 'Synthetic contact', source_signature: 'synthetic-source', candidates: [text], best_index: 0, rank_ok: true, review_ok: true, warnings: [], judgment: [] };
}
(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.TEST_BROWSER_EXECUTABLE ? { executablePath: process.env.TEST_BROWSER_EXECUTABLE } : {}) });
  async function create(sourceRoot) {
    const page = await browser.newPage({ viewport: { width: 1024, height: 800 } });
    page.setDefaultTimeout(10000);
    const posts = [], copied = [], errors = []; let generation = 10, copyFails = false;
    let state = { ok: true, session: 'Synthetic contact', source_signature: 'synthetic-source', settings: { has_key: true, paused: false, relationship: '朋友', style: '', context: 10, generation_timeout: 60, max_cloud_requests: 1, max_model_calls: 6, max_analysis_cost: 0 }, engine: { status: 'capturing', title_ready: true }, participants: [], messages: [{ from: 'her', kind: 'text', text: 'Synthetic message' }], analysis: advice(1, 'Synthetic live reply 1') };
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => {
      let sequence = 0;
      if (!crypto.randomUUID) crypto.randomUUID = () => 'synthetic-' + ++sequence;
      Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('Synthetic clipboard refusal'); } } });
    });
    await page.route(origin + '/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<!doctype html><html><head><meta charset="utf-8"></head><body><script src="/panel.js"></script></body></html>' });
      if (url.pathname === '/panel.js') return route.fulfill({ contentType: 'application/javascript; charset=utf-8', body: fs.readFileSync(path.join(sourceRoot, 'lib', 'panel.js'), 'utf8') });
      let result = { ok: true, app_version: 'synthetic', models: [], extensions: [] };
      if (route.request().method() === 'POST') posts.push({ path: url.pathname, body: route.request().postDataJSON() });
      if (url.pathname === '/fill') result = { ok: false, error: '当前输入框不是空白，仅允许复制' };
      if (url.pathname === '/copy-text') {
        copied.push(route.request().postDataJSON().text);
        result = copyFails ? { ok: false, error: 'Synthetic clipboard unavailable' } : { ok: true };
      }
      if (url.pathname === '/analyze-text') result = advice(++generation, 'Synthetic manual reply ' + generation);
      if (url.pathname === '/settings') state = { ...state, settings: { ...state.settings, ...route.request().postDataJSON() } };
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(url.pathname === '/state' ? state : result) });
    });
    await page.goto(origin + '/'); await page.waitForSelector('#reply-0');
    return { page, posts, copied, errors, setCopyFailure: value => { copyFails = value; }, setState: patch => { state = { ...state, ...patch }; }, state: () => state };
  }
  async function generate(page) {
    await Promise.all([page.waitForResponse(r => new URL(r.url()).pathname === '/analyze-text'), page.locator('#analyze').click()]);
    await page.waitForFunction(() => !document.querySelector('#analyze').disabled);
  }
  async function makePending(page) {
    await page.locator('#reply-0').fill('Synthetic edited reply');
    await generate(page);
    await page.waitForFunction(() => !document.querySelector('#new-advice').hidden);
  }
  try {
    if (baselineRoot) {
      const old = await create(baselineRoot), p = old.page;
      await p.locator('[data-act=fill][data-index="0"]').click();
      await p.waitForFunction(() => !document.querySelector('#request-error').hidden);
      await p.locator('[data-act=retry-request]').click();
      baselineCheck('1.5.69 fill retry incorrectly starts regeneration', old.posts.some(x => x.path === '/regenerate'));
      await p.locator('.switcher [data-act=manual]').click();
      await p.locator('#transcript').fill('对方：合成第一段'); await generate(p);
      await p.locator('#reply-0').fill('Synthetic edited reply');
      await p.locator('#transcript').fill('对方：合成第二段'); await generate(p);
      await p.waitForFunction(() => !document.querySelector('#new-advice').hidden);
      await p.locator('[data-act=latest]').click();
      baselineCheck('1.5.69 accepting current manual result leaves stale warning', await p.locator('#result-state').isVisible());
      await makePending(p);
      await p.locator('#transcript').fill('对方：完全不同的合成第三段');
      baselineCheck('1.5.69 source edit leaves prior pending result available', await p.locator('#new-advice').isVisible());
      await p.locator('[data-act=latest]').click();
      baselineCheck('1.5.69 prior-source pending result replaces current edited reply', await p.locator('#reply-0').inputValue() !== 'Synthetic edited reply');
      await p.close();
    }
    const app = await create(root), p = app.page;
    await p.locator('#reply-0').fill('Synthetic edited live reply');
    await p.locator('[data-act=fill][data-index="0"]').click();
    await p.waitForFunction(() => document.querySelector('[data-done="0"]').textContent.includes('复制'));
    check('failed fill keeps current edited reply', await p.locator('#reply-0').inputValue() === 'Synthetic edited live reply');
    check('failed fill focuses actionable copy fallback', await p.locator('[data-act=copy]').evaluate(e => e.classList.contains('primary') && document.activeElement === e));
    check('failed fill exposes no generic regeneration retry', await p.locator('#request-error').isHidden() && await p.locator('[data-act=retry-request]').isHidden());
    app.setCopyFailure(true); await p.locator('[data-act=copy]').click();
    await p.waitForFunction(() => document.querySelector('[data-done="0"]').textContent.includes('复制未成功'));
    check('failed copy shows inline repeat/manual-copy action', (await p.locator('[data-done="0"]').textContent()).includes('再次点'));
    check('failed copy remains enabled and focused', await p.locator('[data-act=copy]').isEnabled() && await p.locator('[data-act=copy]').evaluate(e => document.activeElement === e));
    check('failed copy also exposes no regeneration retry', await p.locator('#request-error').isHidden());
    app.setCopyFailure(false); await p.locator('#reply-0').fill('Synthetic final copy edit'); await p.locator('[data-act=copy]').click();
    await p.waitForFunction(() => document.querySelector('[data-done="0"]').textContent.includes('已复制'));
    check('copy retry uses current edit', app.copied.at(-1) === 'Synthetic final copy edit');
    check('fill/copy failures and recovery generate no model calls', !app.posts.some(x => ['/analyze-text', '/regenerate'].includes(x.path)));
    app.setState({ analysis: advice(2, 'Synthetic live reply 2') });
    await p.waitForFunction(() => !document.querySelector('#new-advice').hidden);
    await p.locator('.switcher [data-act=manual]').click();
    await p.locator('#transcript').fill('对方：合成第一段'); await generate(p);
    await p.locator('#reply-0').fill('Synthetic edited reply');
    await p.locator('#transcript').fill('对方：合成第二段'); await generate(p);
    await p.waitForFunction(() => !document.querySelector('#new-advice').hidden);
    check('manual result waits while preserving user edit', await p.locator('#reply-0').inputValue() === 'Synthetic edited reply');
    await p.locator('[data-act=latest]').click();
    check('accepting valid manual result displays new reply', (await p.locator('#reply-0').inputValue()).startsWith('Synthetic manual reply'));
    check('accepting valid manual result clears stale warning', await p.locator('#result-state').isHidden());
    await makePending(p); await p.locator('#transcript').fill('对方：完全不同的合成第三段');
    check('source edit invalidates pending manual result', await p.locator('#new-advice').isHidden());
    await p.locator('[data-act=latest]').evaluate(e => e.click());
    check('queued latest click cannot accept prior-source result', await p.locator('#reply-0').inputValue() === 'Synthetic edited reply');
    check('source edit preserves draft and marks it stale', await p.locator('#result-state').isVisible());
    await p.locator('#transcript').fill('对方（甲）：合成甲的消息\n对方（乙）：合成乙的消息'); await makePending(p);
    await p.locator('#manual-target').selectOption('乙');
    check('target change invalidates pending result and preserves edit', await p.locator('#new-advice').isHidden() && await p.locator('#reply-0').inputValue() === 'Synthetic edited reply');
    await makePending(p); await p.locator('[data-tone=温柔]').click();
    check('tone change invalidates pending result without replacing edit', await p.locator('#new-advice').isHidden() && await p.locator('#reply-0').inputValue() === 'Synthetic edited reply');
    await makePending(p); await p.locator('#relationship').selectOption('同学');
    check('relationship change invalidates pending result', await p.locator('#new-advice').isHidden());
    await makePending(p);
    await p.locator('.switcher [data-act=live]').click();
    check('live pending reply survives manual context changes', await p.locator('#new-advice').isVisible() && await p.locator('#reply-0').inputValue() === 'Synthetic final copy edit');
    await p.locator('[data-act=latest]').click();
    check('live latest still applies correct pending result', await p.locator('#reply-0').inputValue() === 'Synthetic live reply 2');
    await p.locator('.switcher [data-act=manual]').click();
    check('valid manual pending reply survives mode switch', await p.locator('#new-advice').isVisible());
    await p.locator('[data-act=latest]').click();
    check('restored valid manual latest clears stale warning', await p.locator('#result-state').isHidden());
    check('manual mode retains copy-only actions', await p.locator('[data-act=fill]').count() === 0);
    check('automatic filling remains absent', await p.locator('#auto-fill').count() === 0 && !(await p.locator('body').textContent()).includes('自动填入'));
    check('UI issued only one explicit fill and no forced regeneration', app.posts.filter(x => x.path === '/fill').length === 1 && !app.posts.some(x => x.path === '/regenerate'));
    check('no browser errors', app.errors.length === 0);
    await p.close();
    const report = { passed: true, checks: checks.length, details: checks, baseline_checks: baselineChecks, synthetic_data_only: true, all_api_responses_mocked: true, no_real_model_calls: true, no_wechat_actions: true };
    fs.writeFileSync(path.join(outputDir, 'final-actions-test-results.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ passed: true, checks: checks.length, baseline_checks: baselineChecks.length }));
  } catch (error) {
    fs.writeFileSync(path.join(outputDir, 'final-actions-test-results.json'), JSON.stringify({ passed: false, checks: checks.length, details: checks, baseline_checks: baselineChecks, error: String(error), synthetic_data_only: true, all_api_responses_mocked: true }, null, 2));
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
