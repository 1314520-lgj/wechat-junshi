'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = process.env.JUNSHI_ROOT
  ? path.resolve(process.env.JUNSHI_ROOT)
  : fs.existsSync(path.join(__dirname, 'lib', 'panel.js')) ? __dirname : path.dirname(__dirname);
const outputDir = process.env.TEST_OUTPUT_DIR ? path.resolve(process.env.TEST_OUTPUT_DIR) : path.join(root, 'test-results');
const baselineRoot = process.env.JUNSHI_BASELINE ? path.resolve(process.env.JUNSHI_BASELINE) : null;
const origin = 'http://junshi.responsive';
const checks = [], screenshots = [], observations = [];
const longReply = '这是一段用于验证窗口变化的合成建议，编辑过的文字应完整保留，超长内容可以在编辑框内滚动阅读。'.repeat(35);
const modelPaths = ['/analyze-text', '/regenerate', '/fill', '/import-media'];
const check = (name, passed) => { assert.ok(passed, name); checks.push(name); };
const fixture = () => ({
  ok: true, session: '合成测试朋友', source_signature: 'synthetic-sample',
  settings: { has_key: true, paused: false, relationship: '朋友', style: '', context: 10, model: 'test', judge_model: 'test', generation_timeout: 60, max_model_calls: 6 },
  engine: { status: 'capturing', title_ready: true, frame_age_seconds: 2 },
  participants: [],
  messages: Array.from({ length: 25 }, (_, i) => ({ message_id: 'synthetic-' + i, from: 'her', kind: 'text', text: '这是一条只用于测试核对区滚动的合成消息。' + i })),
  analysis: { ts: 10, session: '合成测试朋友', source_signature: 'synthetic-sample', candidates: ['好的，周末见。', '到时见。', '周末可以。'], best_index: 0, rank_ok: true, review_ok: true, warnings: [], judgment: [], phase_timings: [] }
});
async function hitVisible(page, selector) {
  return page.locator(selector).evaluate(element => {
    const r = element.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    const hit = document.elementFromPoint(x, y);
    return r.width > 0 && r.height > 0 && r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1 && !!hit && (element === hit || element.contains(hit));
  });
}
async function centerClick(page, selector) {
  const point = await page.locator(selector).evaluate(e => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.click(point.x, point.y);
}
(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.TEST_BROWSER_EXECUTABLE ? { executablePath: process.env.TEST_BROWSER_EXECUTABLE } : {}) });
  async function create(width, height, theme = 'light', font = 'normal', sourceRoot = root) {
    const page = await browser.newPage({ viewport: { width, height }, colorScheme: theme });
    page.setDefaultTimeout(10000);
    const posts = [], errors = [];
    let state = fixture();
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(({ theme, font }) => {
      localStorage.setItem('junshi-display', JSON.stringify({ theme, font }));
      Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => {} } });
    }, { theme, font });
    await page.route(origin + '/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<!doctype html><html><head><meta charset="utf-8"></head><body><script src="/panel.js"></script></body></html>' });
      if (url.pathname === '/panel.js') return route.fulfill({ contentType: 'application/javascript; charset=utf-8', body: fs.readFileSync(path.join(sourceRoot, 'lib', 'panel.js'), 'utf8') });
      if (route.request().method() === 'POST') {
        posts.push({ path: url.pathname, body: route.request().postDataJSON() });
        if (url.pathname === '/settings') state = { ...state, settings: { ...state.settings, ...route.request().postDataJSON() } };
      }
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(url.pathname === '/state' ? state : { ok: true, app_version: '1.5.69', models: [], extensions: [] }) });
    });
    await page.goto(origin + '/');
    await page.waitForSelector('#reply-0');
    return { page, posts, errors };
  }
  async function screenshot(page, name) {
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: path.join(outputDir, name + '.png'), fullPage: false });
    screenshots.push(name + '.png');
  }
  try {
    if (baselineRoot) {
      const wide = await create(1920, 1080, 'light', 'normal', baselineRoot);
      const used = await wide.page.locator('main').evaluate(e => e.getBoundingClientRect().width);
      check('1.5.68 baseline reproduces unused wide window space', used < 1200);
      observations.push({ baseline: true, viewport: '1920x1080', main_width: used });
      await screenshot(wide.page, '169-before-wide');
      await wide.page.close();
      const short = await create(320, 240, 'dark', 'normal', baselineRoot);
      await short.page.locator('#reply-0').fill(longReply);
      const editorHeight = await short.page.locator('#reply-0').evaluate(e => e.getBoundingClientRect().height);
      check('1.5.68 baseline reproduces editor taller than short window', editorHeight > 240);
      await short.page.locator('header [data-act=settings]').click();
      await short.page.locator('#settings').evaluate(d => { d.querySelectorAll('details').forEach(e => e.open = true); d.scrollTop = d.scrollHeight; });
      check('1.5.68 baseline reproduces hidden close control after settings scroll', !await hitVisible(short.page, '[data-act=close-settings]'));
      await short.page.close();
    }
    const sizes = [[1920,1080],[1366,768],[1024,600],[901,600],[900,600],[820,600],[761,600],[760,600],[620,400],[520,400],[380,400],[320,240],[280,240]];
    for (const [width, height] of sizes) {
      const theme = width % 2 ? 'dark' : 'light';
      const font = [1920,761,380,280].includes(width) ? 'large' : 'normal';
      const view = await create(width, height, theme, font), page = view.page;
      const label = width + 'x' + height + ' ' + theme + ' ' + font;
      check(label + ' no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      check(label + ' main uses available window width', await page.locator('main').evaluate(e => e.getBoundingClientRect().width >= innerWidth - 66));
      check(label + ' expected columns fit', await page.evaluate(() => {
        const source = document.querySelector('.source-column').getBoundingClientRect(), result = document.querySelector('.result-column').getBoundingClientRect();
        return innerWidth > 760 ? result.left >= source.right : result.top >= source.bottom;
      }));
      if (width <= 760) check(label + ' tools follow replies', await page.evaluate(() => document.querySelector('.support-column').getBoundingClientRect().top >= document.querySelector('.result-column').getBoundingClientRect().bottom));
      await page.locator('#reply-0').fill(longReply);
      const editor = await page.locator('#reply-0').evaluate(e => {
        const css = getComputedStyle(e); e.scrollTop = e.scrollHeight;
        return { height: e.getBoundingClientRect().height, limit: parseFloat(css.maxHeight), scroll: e.scrollTop, scrollHeight: e.scrollHeight, clientHeight: e.clientHeight, viewport: innerHeight, overflow: css.overflowY };
      });
      check(label + ' editor fits CSS limit and viewport', editor.height <= editor.limit + 1 && editor.limit <= height && editor.limit <= 320);
      check(label + ' long text scrolls inside editor', editor.scroll > 0 && editor.scrollHeight > editor.clientHeight && editor.overflow === 'auto');
      const copy = page.locator('[data-act=copy][data-index="0"]');
      await copy.scrollIntoViewIfNeeded();
      check(label + ' copy is reachable', await hitVisible(page, '[data-act=copy][data-index="0"]') && await copy.isEnabled());
      await page.locator('header [data-act=settings]').click();
      await page.locator('#settings').evaluate(d => { d.querySelectorAll('details').forEach(e => e.open = true); d.scrollTop = d.scrollHeight; });
      check(label + ' settings fits and scrolls', await page.locator('#settings').evaluate(e => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1 && e.scrollHeight > e.clientHeight && e.scrollWidth <= e.clientWidth; }));
      check(label + ' settings heading covers the top edge while scrolled', await page.locator('#settings').evaluate(e => { const d = e.getBoundingClientRect(), h = e.querySelector('.settings-heading').getBoundingClientRect(); return h.top <= d.top + 2 && h.left <= d.left + 2 && h.right >= d.right - 2; }));
      check(label + ' settings close remains visible at bottom', await hitVisible(page, '[data-act=close-settings]'));
      check(label + ' settings last control remains reachable', await hitVisible(page, '[data-act=quit]'));
      if (width === 320) await screenshot(page, '169-settings-short');
      await centerClick(page, '[data-act=close-settings]');
      check(label + ' settings close truly works without scrolling', await page.locator('#settings').evaluate(e => !e.open));
      await page.locator('#trigger-readback').click();
      await page.locator('.drawer-body').evaluate(e => e.scrollTop = e.scrollHeight);
      check(label + ' drawer fits and scrolls', await page.locator('.drawer-body').evaluate(e => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1 && e.scrollHeight > e.clientHeight && e.scrollWidth <= e.clientWidth; }));
      check(label + ' drawer final action is reachable', await hitVisible(page, '[data-act=correct-context]'));
      check(label + ' drawer close remains visible', await hitVisible(page, '.drawer-head [data-act=close-drawer]'));
      await centerClick(page, '.drawer-head [data-act=close-drawer]');
      await page.waitForFunction(() => !document.querySelector('#drawer').open && document.body.style.overflow === '');
      check(label + ' drawer restores focus and scrolling', await page.evaluate(() => !document.querySelector('#drawer').open && document.activeElement === document.querySelector('#trigger-readback') && document.body.style.overflow === ''));
      check(label + ' no model or WeChat requests', !view.posts.some(x => modelPaths.includes(x.path)));
      check(label + ' no page errors', view.errors.length === 0);
      observations.push({ viewport: width + 'x' + height, theme, font, editor_height: editor.height, editor_limit: editor.limit });
      if ([1920,820,380].includes(width)) {
        await page.locator('#reply-0').fill('好的，周末见。');
        await screenshot(page, '169-after-' + width);
      }
      await page.close();
    }
    const live = await create(1366, 768), page = live.page;
    await page.locator('#reply-0').fill(longReply);
    await page.locator('#reply-0').evaluate(e => { e.focus(); e.setSelectionRange(12, 23, 'forward'); e.scrollTop = 100; });
    const before = await page.locator('#reply-0').evaluate(e => ({ value: e.value, start: e.selectionStart, end: e.selectionEnd, scroll: e.scrollTop }));
    for (const [width, height] of [[820,600],[761,600],[760,600],[380,400],[280,240],[1920,1080]]) {
      await page.setViewportSize({ width, height });
      await page.waitForFunction(({ width, height }) => innerWidth === width && innerHeight === height, { width, height });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const after = await page.locator('#reply-0').evaluate(e => ({ value: e.value, start: e.selectionStart, end: e.selectionEnd, scroll: e.scrollTop, focused: document.activeElement === e, height: e.getBoundingClientRect().height, limit: parseFloat(getComputedStyle(e).maxHeight) }));
      check('continuous resize ' + width + ' preserves edited reply, caret and focus', after.value === before.value && after.start === before.start && after.end === before.end && after.focused);
      check('continuous resize ' + width + ' retains reply scroll and applies height limit', Math.abs(after.scroll - before.scroll) <= 1 && after.height <= after.limit + 1 && after.limit <= height);
    }
    await page.locator('.switcher [data-act=manual]').click();
    const transcript = '对方：合成的输入文字，请保持原样。\n我：会保留文字。';
    await page.locator('#transcript').fill(transcript);
    await page.locator('#transcript').evaluate(e => { e.focus(); e.setSelectionRange(4, 8); });
    for (const [width,height] of [[520,400],[320,240],[1024,600],[620,820]]) {
      await page.setViewportSize({ width,height });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      check('continuous resize ' + width + ' preserves transcript and caret', await page.locator('#transcript').evaluate((e,text) => e.value === text && e.selectionStart === 4 && e.selectionEnd === 8 && document.activeElement === e, transcript));
      check('continuous resize ' + width + ' leaves analysis ready', await page.locator('#analyze').isEnabled());
    }
    await page.locator('.switcher [data-act=live]').click();
    check('switching back after resize preserves edited live reply', await page.locator('#reply-0').inputValue() === longReply);
    await page.locator('header [data-act=settings]').click();
    await page.locator('#theme').selectOption('dark');
    await page.locator('#font-size').selectOption('large');
    await centerClick(page, '[data-act=close-settings]');
    await page.setViewportSize({width:320,height:240});
    check('theme and large font update after resize without losing reply', await page.locator('#reply-0').inputValue() === longReply && await page.evaluate(() => document.documentElement.dataset.theme === 'dark' && parseFloat(getComputedStyle(document.querySelector('#reply-0')).fontSize) > 16 && document.documentElement.scrollWidth <= innerWidth));
    check('all continuous resize and display changes issue zero model requests', !live.posts.some(x => modelPaths.includes(x.path)));
    check('continuous resize has no page errors', live.errors.length === 0);
    await page.close();
    const report = { passed: true, checks: checks.length, details: checks, observations, screenshots, synthetic_data_only: true, no_real_model_calls: true, no_wechat_actions: true };
    fs.writeFileSync(path.join(outputDir,'test-responsive-results.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify({passed:true,checks:checks.length,viewports:sizes.length,screenshots}));
  } catch (error) {
    fs.writeFileSync(path.join(outputDir,'test-responsive-results.json'),JSON.stringify({passed:false,checks:checks.length,details:checks,error:String(error),screenshots,synthetic_data_only:true,no_real_model_calls:true,no_wechat_actions:true},null,2));
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
