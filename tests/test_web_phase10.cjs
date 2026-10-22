// Isolated browser API/DOM doubles; never use these records in production reports.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto').webcrypto;
const scripts = path.resolve(__dirname, '../src/web/static/js');

function environment({ timers = false } = {}) {
  const nodes = new Map(), listeners = {};
  const node = id => {
    if (!nodes.has(id)) {
      const value = { id, innerHTML: '', innerText: '', value: '', style: {}, dataset: {}, className: '', disabled: false,
        hidden: false, attributes: {}, events: {}, addEventListener(name, fn) { this.events[name] = fn; },
        focus() { this.focused = true; },
        setAttribute(name, text) { this.attributes[name] = text; }, getAttribute(name) { return this.attributes[name]; } };
      value.classList = { toggle(name, enabled) {
        const classes = new Set(value.className.split(' ').filter(Boolean));
        if (enabled) classes.add(name); else classes.delete(name);
        value.className = [...classes].join(' ');
      }};
      nodes.set(id, value);
    }
    return nodes.get(id);
  };
  const context = vm.createContext({ console, crypto, AbortController, Blob, URL,
    setTimeout: timers ? fn => { Promise.resolve().then(fn); return 1; } : () => 1, clearTimeout() {},
    document: { getElementById: node, querySelectorAll(selector) {
      if (selector === '[data-tab]') return [...nodes.values()].filter(value => value.dataset.tab);
      if (selector === '.tab-pane') return [...nodes.values()].filter(value => /^tab-(summary|report|niche\d+)$/.test(value.id));
      return [];
    }}, window: { addEventListener(name, fn) { listeners[name] = fn; } } });
  const load = name => vm.runInContext(fs.readFileSync(path.join(scripts, `${name}.js`), 'utf8'), context);
  load('ui'); load('form');
  return { context, nodes, node, listeners, load };
}

function config() {
  return { defaults: { category: 'Fixture category', mode: 'ollama', geo: 'VN', timeframe: 'today 3-m',
    niches: Array.from({ length: 3 }, (_, index) => ({ name: `Fixture ${index}`, seed_keywords: ['alpha', 'bravo'], subreddits: [] })) },
    limits: { min_niches: 3, max_niches: 5, max_keywords: 8, max_subreddits: 4 }, model_name: 'fixture-local', poll_interval_ms: 1000 };
}

const result = () => ({ report_filename: 'fixture.md', markdown_content: 'Fixture diagnostic Markdown', status: 'partial',
  success: false, message: 'Fixture partial', metadata: { category: 'Fixture category' }, niches: {} });
const job = (status, step = null) => ({ job_id: 'a'.repeat(32), status, progress: step ? {
  step, total_steps: 5, sequence: step, title: `Fixture server step ${step}`, detail: 'From callback' } : null });

async function controller(api = {}) {
  const env = environment({ timers: true });
  env.context.Api = { getConfig: async () => config(), getActiveJob: async () => ({ job: null }),
    getLatestReport: async () => ({ status: 'no_report' }), ...api };
  env.load('app');
  await env.listeners.DOMContentLoaded();
  return env;
}

test('phase 10 renders all five niche tabs from result labels with safe index IDs', () => {
  const { context, node } = environment();
  context.fixture = { metadata: { total_niches: 5 }, niches: Object.fromEntries(Array.from({ length: 5 }, (_, index) =>
    [`Niche <script>${index}</script>`, { keywords: [], products: [], discussions: [], ideas: [] }])) };
  vm.runInContext('UI.renderAll(fixture)', context);
  const tabs = node('nicheTabs').innerHTML;
  assert.match(tabs, /data-tab="niche4"/);
  assert.match(node('nichePanes').innerHTML, /id="niche4Ideas"/);
  assert.match(tabs, /&lt;script&gt;/);
  assert.doesNotMatch(tabs, /<script>|onclick=/);
  assert.equal(node('metricNiches').innerText, 5);
  vm.runInContext('UI.renderAll({ status: "invalid_cache" })', context);
  assert.equal(node('nicheTabs').innerHTML, '');
  assert.equal(node('nichePanes').innerHTML, '');
});

test('phase 10 tab selection updates ARIA and hides inactive panels without inline code', () => {
  const { context, node } = environment();
  for (const id of ['summary', 'niche4', 'report']) { node(`tab-button-${id}`).dataset.tab = id; node(`tab-${id}`); }
  vm.runInContext('UI.selectTab("niche4")', context);
  assert.equal(node('tab-button-niche4').attributes['aria-selected'], 'true');
  assert.equal(node('tab-summary').hidden, true);
  assert.equal(node('tab-niche4').hidden, false);
});

for (const [name, state, offline, expected] of [
  ['live', { status: 'success', is_live: true, live_attempted: true, record_count: 3, cached_record_count: 0, request_count: 1 }, false, 'Live'],
  ['mixed cache', { status: 'success', is_live: true, live_attempted: true, record_count: 3, cached_record_count: 1, request_count: 1 }, false, 'Live + cache'],
  ['cached', { status: 'success', is_live: true, record_count: 3, cached_record_count: 3 }, false, 'Cached'],
  ['partial', { status: 'partial' }, false, 'Partial'], ['failed', { status: 'failed' }, false, 'Failed'],
  ['not configured', { status: 'not_configured' }, false, 'Not configured'],
  ['archived', { status: 'success', is_live: true, live_attempted: true }, true, 'Snapshot'],
]) test(`phase 10 source badge distinguishes ${name}`, () => {
  const { context } = environment(); context.state = state;
  const html = vm.runInContext(`UI.sourceBadge(state, ${offline})`, context);
  assert.ok(html.includes(`>${expected}</span>`));
  if (offline || name === 'cached') assert.doesNotMatch(html, />Live/);
});

test('phase 10 contradictory empty success cannot become Live', () => {
  const { context } = environment();
  const html = vm.runInContext('UI.sourceBadge({status:"success", is_live:true, live_attempted:true, request_count:1, cached_record_count:0, record_count:0})', context);
  assert.doesNotMatch(html, />Live/);
});

test('phase 10 form defaults to Ollama, preserves entered values and bounds add/remove', () => {
  const { context, node } = environment(); context.config = config();
  vm.runInContext('ResearchForm.initialize(config)', context);
  assert.equal(node('inputMode').value, 'ollama');
  node('input-niche-0-name').value = 'User edited name';
  vm.runInContext('ResearchForm.add(); ResearchForm.add(); ResearchForm.add()', context);
  assert.equal(vm.runInContext('ResearchForm.count', context), 5);
  assert.equal(node('input-niche-0-name').value, 'User edited name');
  assert.equal(node('btnAddNiche').disabled, true);
  vm.runInContext('ResearchForm.remove(4); ResearchForm.remove(3); ResearchForm.remove(0)', context);
  assert.equal(vm.runInContext('ResearchForm.count', context), 3);
  assert.equal(node('input-niche-0-name').value, 'User edited name');
});

test('phase 10 treats editable strings as values rather than HTML and sends only allowed fields', () => {
  const { context, node } = environment(); context.config = config();
  context.config.defaults.niches[0].name = '<img src=x onerror=bad()>';
  vm.runInContext('ResearchForm.initialize(config)', context);
  assert.doesNotMatch(node('nicheInputs').innerHTML, /<img|onerror=/);
  assert.match(node('input-niche-0-name').value, /<img/);
  const payload = JSON.parse(vm.runInContext('JSON.stringify(ResearchForm.read())', context));
  assert.deepEqual(Object.keys(payload).sort(), ['category', 'geo', 'mode', 'niches', 'timeframe']);
  assert.equal(payload.geo, 'VN');
  assert.equal(payload.niches[0].subreddits.length, 0);
});

test('phase 10 form blocks malformed/duplicate niches and subreddit URLs', () => {
  const { context, node } = environment(); context.config = config();
  vm.runInContext('ResearchForm.initialize(config)', context);
  node('input-niche-1-name').value = 'Fixture 0';
  assert.throws(() => vm.runInContext('ResearchForm.read()', context), /trùng/);
  node('input-niche-1-name').value = 'Fixture 1';
  node('input-niche-0-subreddits').value = 'https://reddit.com/r/community';
  assert.throws(() => vm.runInContext('ResearchForm.read()', context), /Subreddit/);
});

test('phase 10 invalid config limits cannot inject HTML into editor', () => {
  const { context, node } = environment(); context.config = config();
  context.config.limits.max_keywords = '<img src=x>';
  assert.throws(() => vm.runInContext('ResearchForm.initialize(config)', context), /Contract/);
  assert.equal(node('nicheInputs').innerHTML, '');
});

test('phase 10 queued progress has no invented active step and callback text is literal', () => {
  const { context, node } = environment(); context.job = job('queued');
  vm.runInContext('UI.renderJob(job)', context);
  assert.equal(node('step1').className, 'step-badge');
  assert.match(node('statusText').innerText, /đang chờ worker/);
  context.job = job('running', 3); context.job.progress.detail = '<img src=x>';
  vm.runInContext('UI.renderJob(job)', context);
  assert.match(node('statusText').innerText, /<img src=x>/);
  assert.equal(node('step3').className, 'step-badge active');
  assert.doesNotMatch(node('statusText').innerHTML, /<img/);
});

test('phase 10 controller submits explicit mode once and only shows server progress', async () => {
  const inputs = [], steps = [];
  const pending = [job('running', 2), job('completed', 5)];
  const env = await controller({ startJob: async (input, key) => { inputs.push({ input, key }); return job('queued'); },
    getJob: async () => pending.shift(), getJobResult: async () => result() });
  env.context.recordStep = step => steps.push(step);
  vm.runInContext('const originalStep = UI.setStepProgress.bind(UI); UI.setStepProgress = (step, text) => { recordStep(step); originalStep(step,text); }', env.context);
  await vm.runInContext('runAnalysis()', env.context);
  assert.equal(inputs.length, 1); assert.equal(inputs[0].input.mode, 'ollama'); assert.match(inputs[0].key, /^[a-f0-9-]{36}$/);
  assert.deepEqual(steps, [2, 5]);
  assert.equal(env.node('rawReportText').innerText, 'Fixture diagnostic Markdown');
  assert.equal(env.node('researchFields').disabled, false);
  assert.equal(vm.runInContext('activeJobId', env.context), null);
});

test('phase 10 reload resumes an active job without another POST', async () => {
  let posts = 0;
  const env = await controller({ getActiveJob: async () => ({ job: job('running', 1) }),
    startJob: async () => { posts++; }, getJob: async () => job('completed', 5), getJobResult: async () => result() });
  assert.equal(posts, 0);
  assert.equal(env.node('rawReportText').innerText, 'Fixture diagnostic Markdown');
});

test('phase 10 polling failure does not declare server failed or repeat collection and can resume', async () => {
  let posts = 0, failures = true;
  const env = await controller({ startJob: async () => { posts++; return job('running', 1); },
    getJob: async () => { if (failures) { const error = new Error('Fixture offline'); error.status = 0; throw error; } return job('completed', 5); },
    getJobResult: async () => result() });
  await vm.runInContext('runAnalysis()', env.context);
  assert.equal(posts, 1); assert.equal(env.node('btnRun').innerText, 'Theo dõi lại job');
  assert.match(env.node('dataStatus').innerHTML, /Chưa xác nhận trạng thái job/);
  assert.equal(env.node('step5').className, 'step-badge');
  failures = false;
  await vm.runInContext('runAnalysis()', env.context);
  assert.equal(posts, 1); assert.equal(vm.runInContext('activeJobId', env.context), null);
});

test('phase 10 duplicate clicks cannot submit a second job', async () => {
  let resolve, calls = 0;
  const env = await controller({ startJob: () => { calls++; return new Promise(done => { resolve = done; }); }, getJobResult: async () => result() });
  const pending = vm.runInContext('runAnalysis()', env.context);
  await vm.runInContext('runAnalysis()', env.context);
  resolve(job('completed', 5)); await pending;
  assert.equal(calls, 1);
});

test('phase 10 validation rejection does not silently follow an unrelated job', async () => {
  let activeCalls = 0;
  const env = await controller({ getActiveJob: async () => { activeCalls++; return { job: null }; }, startJob: async () => { const error = new Error('Fixture invalid payload'); error.status = 400; throw error; } });
  await vm.runInContext('runAnalysis()', env.context);
  assert.equal(activeCalls, 1); assert.match(env.node('formError').innerText, /invalid payload/);
});

test('phase 10 API uses same-origin CSRF and idempotency headers without implicit fast mode', async () => {
  const env = environment(); const calls = [];
  env.context.fetch = async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => ({ job_id: 'fixture-job' }) }; };
  env.load('api'); env.context.input = config().defaults;
  vm.runInContext('Api.csrfToken = "fixture-csrf"', env.context);
  await vm.runInContext('Api.startJob(input, "fixture-request-key")', env.context);
  const options = calls[0].options;
  assert.equal(options.headers['X-CSRF-Token'], 'fixture-csrf');
  assert.equal(options.headers['Idempotency-Key'], 'fixture-request-key');
  assert.equal(options.credentials, 'same-origin'); assert.equal(options.redirect, 'error');
  assert.equal(JSON.parse(options.body).mode, 'ollama');
  assert.equal(JSON.parse(options.body).fast_mode, undefined);
});

test('phase 10 API reports server errors without pretending they are research results', async () => {
  const env = environment();
  env.context.fetch = async () => ({ ok: false, status: 403, json: async () => ({ error: 'Fixture CSRF denied' }) });
  env.load('api');
  await assert.rejects(vm.runInContext('Api.getConfig()', env.context), /CSRF denied/);
});

test('phase 10 keyboard tab navigation uses safe dataset IDs and roving focus', async () => {
  const env = await controller();
  for (const id of ['summary', 'niche0', 'report']) { env.node(`tab-button-${id}`).dataset.tab = id; env.node(`tab-${id}`); }
  let prevented = false;
  env.node('tabBar').events.keydown({ key: 'ArrowRight', target: { closest: () => env.node('tab-button-summary') }, preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(env.node('tab-button-niche0').focused, true);
  assert.equal(env.node('tab-button-niche0').attributes.tabindex, '0');
  assert.equal(env.node('tab-button-summary').attributes.tabindex, '-1');
  assert.equal(env.node('tab-niche0').hidden, false);
});

test('phase 10 transport timeout is unknown job state, not an invented result', async () => {
  const env = environment(); let calls = 0;
  env.context.fetch = async () => { calls++; const error = new Error('Fixture abort'); error.name = 'AbortError'; throw error; };
  env.load('api');
  await assert.rejects(vm.runInContext('Api.getJob("fixture")', env.context), error => error.status === 0 && error.message.includes('có thể vẫn đang chạy'));
  assert.equal(calls, 1);
});

test('phase 10 client cannot submit before receiving CSRF configuration', () => {
  const env = environment(); let calls = 0;
  env.context.fetch = async () => { calls++; };
  env.load('api');
  assert.throws(() => vm.runInContext('Api.startJob({}, "fixture-request")', env.context), /token/);
  assert.equal(calls, 0);
});
