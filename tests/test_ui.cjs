// Isolated DOM doubles verify presentation of missing/partial data.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const scripts = path.resolve(__dirname, '../src/web/static/js');

test('phase 9 labels archived source requests as historical rather than a fresh live run', () => {
  const { context, nodes } = environment();
  context.fixture = { status: 'partial', metadata: { execution_kind: 'offline_publication_audit' } };
  vm.runInContext('UI.renderStatus(fixture)', context);
  assert.match(nodes.get('dataStatus').innerHTML, /snapshot gốc, không phải request mới trong audit/);
  assert.match(nodes.get('dataStatus').innerHTML, /Loại lần chạy: offline_publication_audit/);
});

test('phase 9 displays canonical run context and a prominent partial warning without inventing model use', () => {
  const { context, nodes } = environment();
  context.fixture = { status: 'partial', metadata: {
    run_id: 'fixture-run', timestamp: '2026-10-21T00:00:00Z', requested_mode: 'ollama',
    mode: 'deterministic', model_name: null, model_attempted: 'fixture-model',
  }};
  vm.runInContext('UI.renderStatus(fixture)', context);
  const html = nodes.get('dataStatus').innerHTML;
  assert.match(html, /role="alert"/);
  assert.match(html, /BÁO CÁO CHƯA ĐẦY ĐỦ/);
  assert.match(html, /Run ID: fixture-run/);
  assert.match(html, /2026-10-21T00:00:00Z/);
  assert.match(html, /Chế độ yêu cầu: ollama/);
  assert.match(html, /không có đầu ra AI được sử dụng/);
  assert.match(html, /Model đã thử gọi: fixture-model/);
});

test('phase 9 escapes run context and never assigns a fresh timestamp when loading an older run', () => {
  const { context, nodes } = environment();
  context.fixture = { status: 'success', metadata: {
    run_id: '<script>bad()</script>', timestamp: '2026-10-21T00:00:00Z',
    requested_mode: '<img src=x>', mode: 'ollama', model_name: '<img src=x>', model_attempted: '<img src=x>',
  }};
  vm.runInContext('UI.renderStatus(fixture)', context);
  const html = nodes.get('dataStatus').innerHTML;
  assert.doesNotMatch(html, /<script>|<img|role="alert"/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /2026-10-21T00:00:00Z/);
  vm.runInContext('UI.renderStatus({ status: "no_report" })', context);
  assert.doesNotMatch(nodes.get('dataStatus').innerHTML, /Run ID|Thời gian tạo|Model đã thử/);
});

function environment() {
  const nodes = new Map();
  const listeners = {};
  const context = vm.createContext({
    console,
    setTimeout: () => 0,
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, { innerHTML: '', innerText: '', style: {}, dataset: {}, checked: false, value: '', addEventListener() {} });
        return nodes.get(id);
      },
      querySelectorAll: () => [],
    },
    window: { addEventListener: (name, callback) => { listeners[name] = callback; } },
  });
  vm.runInContext(fs.readFileSync(path.join(scripts, 'ui.js'), 'utf8'), context);
  return { context, nodes, listeners };
}

// Only presentation fixtures; never loaded into runtime reports.
function phase7Payload() {
  const component = {
    label: 'Fixture component', weight: 0.3, score: 0, contribution: 0,
    status: 'available', reason: 'observed_sample_only', sample_size: 2, candidate_count: 2,
    formula: 'Fixture formula from server', inputs: [{
      evidence_id: 'fixture-evidence', source_url: 'https://trends.google.com/trends/explore?q=fixture',
      identity: 'Fixture observation', retrieved_at: '2026-10-21T00:00:00Z', request_id: 'fixture-request',
      measurements: { recent_mean: 0 },
    }],
  };
  const row = {
    niche: 'Fixture A', rank: 7, status: 'ranked', observed_score: 12.345678, total_score: null,
    score_upper_bound: 32.345678, component_coverage: 0.8, confidence: 80,
    explanation: 'Fixture explanation from server', components: [component],
  };
  return {
    ranking: [{ ...row, niche: 'Wrong alias', rank: 1 }],
    ranking_assessment: {
      method: 'fixed_weight_observed_evidence_v1', policy_id: 'fixture-policy', status: 'partial',
      ranking: [row, { ...row, niche: 'Fixture B', rank: 2, observed_score: 0 }],
      unranked: [], warnings: ['Not a business success probability'],
    },
    niches: {
      'Fixture A': { quality_assessment: { gate_passed: true, status: 'sufficient' } },
      'Fixture B': { quality_assessment: { gate_passed: true, status: 'partial' } },
    },
  };
}

test('phase 7 renders canonical server order, scores, missing totals and breakdown without recomputing', () => {
  const { context, nodes } = environment();
  context.fixture = phase7Payload();
  vm.runInContext('UI.renderAll(fixture)', context);
  const html = nodes.get('rankingBody').innerHTML;
  assert.ok(html.indexOf('Hạng 7') < html.indexOf('Hạng 2'));
  assert.ok(html.indexOf('Fixture A') < html.indexOf('Fixture B'));
  assert.match(html, /12\.345678\/100/);
  assert.match(html, /Quan sát: 0\.000000\/100/);
  assert.match(html, /Tổng đủ 5 nhóm: chưa có dữ liệu/);
  assert.match(html, /Cận trên: 32\.345678/);
  assert.match(html, /80\.0%/);
  assert.match(html, /contribution 0\.000000/);
  assert.match(html, /fixture-evidence/);
  assert.match(html, /fixture-request/);
  assert.match(html, /Fixture formula from server/);
  assert.doesNotMatch(html, /Wrong alias/);
  assert.match(nodes.get('topIdeasGrid').innerHTML, /không tự tạo Top 3/);
});

test('phase 7 escapes untrusted ranking fields and blocks executable evidence links', () => {
  const { context, nodes } = environment();
  const fixture = phase7Payload();
  const row = fixture.ranking_assessment.ranking[0];
  row.explanation = '<script>bad()</script>';
  row.components[0].formula = '<img src=x onerror=bad()>';
  row.components[0].inputs[0].source_url = 'javascript:bad()';
  row.components[0].inputs[0].identity = '" onclick="bad()';
  fixture.ranking_assessment.warnings = ['<svg onload=bad()>'];
  context.fixture = fixture;
  vm.runInContext('UI.renderAll(fixture)', context);
  const html = nodes.get('rankingBody').innerHTML;
  assert.doesNotMatch(html, /<script|<img|<svg|href="javascript:/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;img/);
  assert.match(html, /href="#"/);
  assert.match(html, /&quot; onclick=&quot;bad\(\)/);
});

test('phase 7 refuses ranked cards that contradict the quality gate or numeric contract', () => {
  const { context, nodes } = environment();
  const fixture = phase7Payload();
  fixture.niches['Fixture A'].quality_assessment.gate_passed = false;
  fixture.ranking_assessment.ranking[1].observed_score = NaN;
  context.fixture = fixture;
  vm.runInContext('UI.renderAll(fixture)', context);
  assert.doesNotMatch(nodes.get('rankingBody').innerHTML, /Hạng 7|Hạng 2/);
  assert.match(nodes.get('rankingBody').innerHTML, /Chưa có niche đủ điều kiện/);
});

test('phase 7 clears stale or unknown-method rankings and explains unranked niches', () => {
  const { context, nodes } = environment();
  context.fixture = phase7Payload();
  vm.runInContext('UI.renderAll(fixture)', context);
  vm.runInContext("UI.renderAll({ranking: [{niche: 'Old demo', rank: 1}]})", context);
  assert.doesNotMatch(nodes.get('rankingBody').innerHTML, /Old demo|Fixture A|Hạng 7/);
  context.fixture.ranking_assessment.ranking = [];
  context.fixture.ranking_assessment.unranked = [{ niche: '<b>Blocked</b>', explanation: 'missing evidence', components: [] }];
  vm.runInContext('UI.renderAll(fixture)', context);
  const html = nodes.get('rankingBody').innerHTML;
  assert.match(html, /Chưa xếp hạng/);
  assert.match(html, /&lt;b&gt;Blocked/);
  assert.match(html, /missing evidence/);
  vm.runInContext("fixture.ranking_assessment.method = 'unknown'; UI.renderAll(fixture)", context);
  assert.doesNotMatch(nodes.get('rankingBody').innerHTML, /Blocked/);
});

test('phase 7 bounds rendered evidence but keeps original canonical inputs intact', () => {
  const { context, nodes } = environment();
  context.fixture = phase7Payload();
  const component = context.fixture.ranking_assessment.ranking[0].components[0];
  const observation = component.inputs[0];
  component.inputs = Array.from({ length: 25 }, (_, index) => ({ ...observation, evidence_id: 'fixture-' + index }));
  vm.runInContext('UI.renderAll(fixture)', context);
  const html = nodes.get('rankingBody').innerHTML;
  assert.match(html, /Evidence fixture-19/);
  assert.doesNotMatch(html, /Evidence fixture-20/);
  assert.match(html, /Còn evidence trong JSON/);
  assert.equal(component.inputs.length, 25);
});

test('phase 7 additional unknown confidence has no percent suffix and unavailable status blocks contradictory ranks', () => {
  const { context, nodes } = environment();
  context.fixture = phase7Payload();
  context.fixture.ranking_assessment.ranking[0].confidence = null;
  vm.runInContext('UI.renderAll(fixture)', context);
  assert.match(nodes.get('rankingBody').innerHTML, /Confidence dữ liệu: chưa xác định/);
  assert.doesNotMatch(nodes.get('rankingBody').innerHTML, /chưa có dữ liệu%/);
  vm.runInContext("fixture.ranking_assessment.status = 'unavailable'; UI.renderAll(fixture)", context);
  assert.doesNotMatch(nodes.get('rankingBody').innerHTML, /Hạng 7|Hạng 2/);
});

test('unknown measurements are shown as unknown, not zero or Top Seller', () => {
  const { context, nodes } = environment();
  context.fixture = {
    keywords: [{ keyword: 'Fixture keyword', score: null, trend: 'unavailable' }],
    products: [{ title: 'Fixture product', price: null, rating: null, reviews_count: null }],
    discussions: [{ title: 'Fixture discussion', score: null, comments: null }],
    ideas: [],
  };
  vm.runInContext("UI.renderNicheDetails('niche0', fixture)", context);
  assert.match(nodes.get('niche0Keywords').innerHTML, /Chưa có số đo/);
  assert.doesNotMatch(nodes.get('niche0Keywords').innerHTML, /0\/100/);
  assert.match(nodes.get('niche0Products').innerHTML, /Chưa có giá/);
  assert.doesNotMatch(nodes.get('niche0Products').innerHTML, /Top Seller|4\.5|850|24\.99/);
  assert.match(nodes.get('niche0Discussions').innerHTML, /Chưa có dữ liệu/);
});

test('partial and legacy results clear stale cards and preserve genuine zeros', () => {
  const { context, nodes } = environment();
  context.fixture = {
    status: 'partial', message: 'Fixture warning',
    metadata: { total_niches: 1, total_keywords: 0, total_products: 0, elapsed_seconds: 0 },
    markdown_content: 'Fixture diagnostic report',
    source_statuses: { Fixture: { reddit: { status: 'failed', record_count: 0 } } },
    niches: { Fixture: { keywords: [], products: [], discussions: [], ideas: [] } },
  };
  vm.runInContext('UI.renderAll(fixture)', context);
  assert.equal(nodes.get('metricKeywords').innerText, 0);
  assert.equal(nodes.get('metricElapsed').innerText, '0s');
  assert.match(nodes.get('dataStatus').innerHTML, /failed/);
  assert.equal(nodes.get('rawReportText').innerText, 'Fixture diagnostic report');
  vm.runInContext("UI.renderAll({status: 'legacy', message: 'Unverified cache'})", context);
  assert.equal(nodes.get('metricKeywords').innerText, '—');
  assert.doesNotMatch(nodes.get('rawReportText').innerText, /Fixture diagnostic/);
  assert.equal(nodes.get('nichePanes').innerHTML, '');
  assert.equal(nodes.get('nicheTabs').innerHTML, '');
});

test('source warnings are escaped before rendering', () => {
  const { context, nodes } = environment();
  vm.runInContext("UI.renderAll({status: 'failed', message: '<script>bad()</script>', metadata: {warnings: ['<img src=x>']}})", context);
  assert.doesNotMatch(nodes.get('dataStatus').innerHTML, /<script>|<img/);
  assert.match(nodes.get('dataStatus').innerHTML, /&lt;script&gt;/);
});

test('controller renders partial output and defaults to actual AI mode', async () => {
  const { context, nodes, listeners } = environment();
  const modes = [];
  const fixture = {
    success: false, status: 'partial', message: 'Fixture partial result', report_filename: 'fixture.md',
    markdown_content: 'Fixture diagnostic report', metadata: {}, niches: {},
  };
  context.Api = {
    getConfig: async () => ({ defaults: { category: 'Fixture', geo: '', timeframe: 'today 3-m', mode: 'ollama',
      niches: [0, 1, 2].map(index => ({ name: `Fixture ${index}`, seed_keywords: ['alpha', 'bravo'], subreddits: [] })) },
      limits: { min_niches: 3, max_niches: 5, max_keywords: 8, max_subreddits: 4 }, model_name: 'fixture', poll_interval_ms: 1000 }),
    getActiveJob: async () => ({ job: null }),
    startJob: async input => { modes.push(input.mode); return { job_id: 'fixture', status: 'completed' }; },
    getJobResult: async () => fixture,
    getLatestReport: async () => fixture,
  };
  context.crypto = { randomUUID: () => 'fixture-idempotency-key' };
  vm.runInContext(fs.readFileSync(path.join(scripts, 'form.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(scripts, 'app.js'), 'utf8'), context);
  await listeners.DOMContentLoaded();
  await vm.runInContext('runAnalysis()', context);
  assert.deepEqual(modes, ['ollama']);
  assert.equal(nodes.get('rawReportText').innerText, 'Fixture diagnostic report');
  assert.match(nodes.get('dataStatus').innerHTML, /Fixture partial result/);
  assert.notEqual(nodes.get('step5').className, 'step-badge completed');
  assert.equal(vm.runInContext('globalReportData.report_filename', context), 'fixture.md');
});

test('phase 3 distinguishes cached observations and escapes autocomplete suggestions', () => {
  const { context, nodes } = environment();
  context.fixture = {
    status: 'partial', metadata: {},
    source_statuses: { Fixture: { google_trends: { status: 'success', record_count: 1, request_count: 0, cached_record_count: 1 } } },
    source_health: { google_trends: { status: 'success', request_count: 0, retry_count: 0, cached_record_count: 1 } },
    niches: { Fixture: { keywords: [{
      keyword: 'Fixture', score: 40, trend: 'rising', suggestions: ['<img src=x onerror=bad()>'],
      metrics: { growth_percent: 25, window_points_used: 2 },
      provenance: { from_cache: true, retrieved_at: '<script>bad()</script>' },
    }], products: [], discussions: [], ideas: [] } },
  };
  vm.runInContext('UI.renderAll(fixture)', context);
  const html = nodes.get('niche0Keywords').innerHTML;
  assert.match(html, /25.00%/);
  assert.match(html, /không phải tín hiệu tăng trưởng/);
  assert.match(html, /Dữ liệu từ cache/);
  assert.doesNotMatch(html, /<img|<script/);
  assert.match(nodes.get('dataStatus').innerHTML, /0 request mới/);
  assert.match(nodes.get('dataStatus').innerHTML, /1 bản ghi từ cache/);
});

test('phase 4 distinguishes Amazon source ranks and escapes sponsored product text', () => {
  const { context, nodes } = environment();
  context.fixture = { products: [{
    title: '<img src=x onerror=bad()>', asin: 'B000000001', source: 'Amazon Search',
    price: '$12.50', is_sponsored: true, listings: [
      { source_type: 'search', search_position: 2, listing_rank: null, is_sponsored: true, listing_url: 'https://www.amazon.com/s?k=fixture' },
      { source_type: 'best_sellers', search_position: null, listing_rank: 7, listing_url: 'https://www.amazon.com/gp/bestsellers' },
      { source_type: 'movers_shakers', search_position: null, listing_rank: 3, listing_url: 'https://www.amazon.com/gp/movers-and-shakers' },
    ], url: 'https://www.amazon.com/dp/B000000001',
  }] };
  vm.runInContext("UI.renderNicheDetails('niche0', fixture)", context);
  const html = nodes.get('niche0Products').innerHTML;
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /ASIN: B000000001/);
  assert.match(html, /Sponsored/);
  assert.match(html, /Vị trí tìm kiếm: 2/);
  assert.match(html, /Amazon Best Sellers/);
  assert.match(html, /Hạng trong danh sách: 7/);
  assert.match(html, /Amazon Movers &amp; Shakers|Amazon Movers & Shakers/);
});

test('phase 5 renders real Reddit metadata and only linked source quotes safely', () => {
  const { context, nodes } = environment();
  const quote = 'I cannot find the size <img src=x>';
  context.fixture = {
    quality_assessment: { gate_passed: true, status: 'sufficient' },
    discussions: [{ title: '<script>bad()</script>', selftext: quote, content_summary: quote,
      score: 0, comments: null, post_id: 'abc123', created_utc: 1792537200, source: 'Reddit r/fixture',
      url: 'https://www.reddit.com/r/fixture/comments/abc123/fixture/',
      provenance: { evidence_id: 'reddit-evidence', retrieved_at: '2026-10-21T00:00:00+00:00' } }],
    reddit_pain_points: [
      { quote, evidence_ids: ['reddit-evidence'] },
      { quote: 'FAKE_UNSUPPORTED_PAIN_POINT', evidence_ids: ['unknown'] },
    ],
  };
  vm.runInContext("UI.renderNicheDetails('niche0', fixture)", context);
  const html = nodes.get('niche0Discussions').innerHTML;
  assert.doesNotMatch(html, /<script|<img|FAKE_UNSUPPORTED_PAIN_POINT/);
  assert.match(html, /ID: abc123/);
  assert.match(html, /Evidence: reddit-evidence/);
  assert.match(html, /Điểm Reddit: 0/);
  assert.match(html, /Chưa có dữ liệu.*bình luận/);
  assert.match(html, /không đại diện toàn thị trường/);
  assert.equal(vm.runInContext('UI.redditCreatedAt(Infinity)', context), 'Chưa có dữ liệu');
});

test('phase 5 invalid quote objects do not crash UI or create unsupported claims', () => {
  const { context } = environment();
  context.invalid = [null, { quote: '', evidence_ids: ['known'] },
    { quote: 'UNSUPPORTED_CLAIM', evidence_ids: ['known'] },
    { quote: 'Exact source quote', evidence_ids: ['known', 'known'] }];
  context.posts = [{ title: 'Exact source quote', selftext: 123, provenance: { evidence_id: 'known' } }];
  assert.equal(vm.runInContext('UI.renderRedditPainPoints(invalid, posts)', context), '');
  assert.equal(vm.runInContext('UI.renderRedditPainPoints(null, posts)', context), '');
  assert.equal(vm.runInContext('UI.renderRedditPainPoints([], null)', context), '');
});

test('phase 6 shows quality evidence counts, escapes reasons and blocks unsafe recommendations', () => {
  const { context, nodes } = environment();
  context.fixture = {
    data_quality: 'insufficient', analysis_text: 'Observed only', ideas: [{ name: 'UNSUPPORTED_IDEA' }],
    quality_assessment: { gate_passed: false, valid_count: 3, candidate_count: 4, valid_ratio: 0.75,
      rejected_count: 1, duplicate_count: 0, observed_source_count: 2, configured_source_count: 3,
      qualifying_keyword_count: 1, supporting_record_count: 1, issues: [{ message: '<script>bad()</script>' }] },
  };
  vm.runInContext("UI.renderNicheDetails('niche0', fixture)", context);
  assert.match(nodes.get('niche0Analysis').innerHTML, /Dữ liệu chưa đủ/);
  assert.match(nodes.get('niche0Analysis').innerHTML, /3\/4 \(75.0%\)/);
  assert.match(nodes.get('niche0Analysis').innerHTML, /Phủ nguồn cấu hình: 2\/3/);
  assert.doesNotMatch(nodes.get('niche0Analysis').innerHTML, /<script/);
  assert.doesNotMatch(nodes.get('niche0Ideas').innerHTML, /UNSUPPORTED_IDEA/);
  assert.match(nodes.get('niche0Ideas').innerHTML, /không hiển thị ý tưởng/);
});

test('phase 6 prefers raw observed score and keeps unknown values unknown', () => {
  const { context, nodes } = environment();
  context.fixture = { keywords: [
    { keyword: 'Real zero', raw_metric: { score: 0 }, score: 99, derived_metric: { growth_percent: 50, window_points_used: 2 } },
    { keyword: 'Unknown', raw_metric: { score: null }, score: 88, derived_metric: {} },
  ] };
  vm.runInContext("UI.renderNicheDetails('niche0', fixture)", context);
  const html = nodes.get('niche0Keywords').innerHTML;
  assert.match(html, /0\/100/);
  assert.match(html, /50.00%/);
  assert.match(html, /Chưa có số đo/);
  assert.doesNotMatch(html, /99\/100|88\/100/);
});

test('phase 6 contradictory flags cannot expose AI text and raw commerce/community fields win', () => {
  const { context, nodes } = environment();
  context.fixture = {
    data_quality: 'insufficient', analysis_status: 'success', analysis_text: 'UNSUPPORTED_AI_CLAIM',
    quality_assessment: { gate_passed: true, status: 'insufficient' }, ideas: [{ name: 'UNSUPPORTED_IDEA' }],
    products: [{ title: 'Observed', raw_metric: { price: null, rating: 0, reviews_count: null }, price: '$999.99', rating: 5, reviews_count: 9000 }],
    discussions: [{ title: 'Observed', raw_metric: { score: 0, comments: null, created_utc: null }, score: 9999, comments: 999 }],
  };
  vm.runInContext("UI.renderNicheDetails('niche0', fixture)", context);
  assert.doesNotMatch(nodes.get('niche0Analysis').innerHTML, /UNSUPPORTED_AI_CLAIM/);
  assert.doesNotMatch(nodes.get('niche0Ideas').innerHTML, /UNSUPPORTED_IDEA/);
  assert.match(nodes.get('niche0Products').innerHTML, /Chưa có giá/);
  assert.doesNotMatch(nodes.get('niche0Products').innerHTML, /999.99|9000/);
  assert.match(nodes.get('niche0Discussions').innerHTML, /Điểm Reddit: 0/);
  assert.doesNotMatch(nodes.get('niche0Discussions').innerHTML, /9999|999 bình luận/);
});

test('phase 6 quality badge rejects contradictory or untyped gate flags', () => {
  const { context } = environment();
  assert.equal(vm.runInContext("UI.qualityGatePassed({gate_passed: 1, status: 'sufficient'})", context), false);
  assert.equal(vm.runInContext("UI.qualityGatePassed({gate_passed: true, status: 'insufficient'})", context), false);
  assert.match(vm.runInContext("UI.renderQualityAssessment({gate_passed: true, status: 'insufficient'})", context), /Dữ liệu chưa đủ/);
});

function phase8Payload() {
  const idea = {
    idea_id: 'idea_fixture', kind: 'proposal_not_verified_market_fit', validation_status: 'source_references_verified',
    name: 'Fabric gift pouch', rationale: 'Reusable fabric pouch', target_audience: 'Gift recipients',
    why_now: 'Observed recent mean = 40, not proven market fit.', evidence_ids: ['trend-id', 'amazon-id'],
    basis_fact_ids: ['F1', 'F2'], basis_quote_ids: [],
  };
  const niche = {
    name: 'Fixture', niche_name: 'Fixture', data_quality: 'sufficient', analysis_status: 'success', generation_mode: 'ollama',
    quality_assessment: { gate_passed: true, status: 'sufficient', data_digest: 'a'.repeat(64) },
    ai_validation: { outcome: 'source_references_verified' },
    grounded_analysis: {
      schema_version: 'grounded-analysis-v1', niche_name: 'Fixture', evidence_digest: 'a'.repeat(64),
      facts: [
        { fact_id: 'F1', kind: 'fact', metric: 'trend.recent_mean', value: 40, evidence_ids: ['trend-id'] },
        { fact_id: 'F2', kind: 'fact', metric: 'amazon.title', value: 'Observed product', evidence_ids: ['amazon-id'] },
      ], quotes: [], ideas: [{ ...idea }],
    },
    analysis_text: 'Observed data with source-checked facts.', ideas: [{ ...idea }],
    keywords: [{ keyword: 'Observed keyword', provenance: { source: 'google_trends', evidence_id: 'trend-id', source_url: 'https://trends.google.com/trends/explore?q=fixture', retrieved_at: 'original-time' } }],
    products: [{ title: 'Observed product', provenance: { source: 'amazon', evidence_id: 'amazon-id', source_url: 'https://www.amazon.com/dp/B000000001', retrieved_at: 'original-time' } }], discussions: [],
  };
  return {
    niches: { Fixture: niche }, top_ideas: [{ name: 'UNVERIFIED_ALIAS' }],
    analysis_summary: {
      method: 'grounded_research_slots_round_robin_v1', status: 'partial', warnings: [],
      top_ideas: [{ ...idea, niche: 'Fixture', niche_rank: 1, selection_position: 1, financials: 'FAKE_PROFIT',
        source_links: [{ evidence_id: 'amazon-id', url: 'https://evil.test/forged-url' }] }],
    },
  };
}

test('phase 8 displays grounded proposals as unverified hypotheses with original source links', () => {
  const { context, nodes } = environment();
  context.fixture = phase8Payload();
  vm.runInContext('UI.renderAll(fixture)', context);
  const ideas = nodes.get('niche0Ideas').innerHTML;
  assert.match(ideas, /Đề xuất chưa kiểm chứng/);
  assert.match(ideas, /Fabric gift pouch/);
  assert.match(ideas, /Evidence trend-id/);
  assert.match(ideas, /Evidence amazon-id/);
  assert.match(ideas, /original-time/);
  const summary = nodes.get('topIdeasGrid').innerHTML;
  assert.match(summary, /Đề xuất thử nghiệm/);
  assert.match(summary, /không phải dự báo doanh số/);
  assert.doesNotMatch(summary, /FAKE_PROFIT|UNVERIFIED_ALIAS|evil.test/);
  assert.match(summary, /amazon.com\/dp\/B000000001/);
});

test('phase 8 hides free-form AI ideas and prose without validated structured analysis', () => {
  const { context, nodes } = environment();
  context.fixture = phase8Payload();
  context.fixture.niches.Fixture.grounded_analysis = null;
  context.fixture.niches.Fixture.analysis_text = 'UNVERIFIED_CLAIM';
  vm.runInContext('UI.renderAll(fixture)', context);
  assert.doesNotMatch(nodes.get('niche0Analysis').innerHTML, /UNVERIFIED_CLAIM/);
  assert.doesNotMatch(nodes.get('niche0Ideas').innerHTML, /Fabric gift pouch/);
  assert.match(nodes.get('topIdeasGrid').innerHTML, /không tự tạo Top 3/);
});

test('phase 8 rejects digest mismatch, absent citations and inconsistent canonical proposal fields', () => {
  for (const variant of ['digest', 'citation', 'basis', 'fields', 'status']) {
    const { context, nodes } = environment();
    const fixture = phase8Payload();
    const niche = fixture.niches.Fixture;
    if (variant === 'digest') niche.grounded_analysis.evidence_digest = 'b'.repeat(64);
    if (variant === 'citation') niche.products = [];
    if (variant === 'basis') niche.grounded_analysis.facts = [];
    if (variant === 'fields') {
      niche.ideas[0].why_now = 'FAKE_CLAIM';
      fixture.analysis_summary.top_ideas[0].why_now = 'FAKE_CLAIM';
    }
    if (variant === 'status') niche.ai_validation.outcome = 'invalid_output';
    context.fixture = fixture;
    vm.runInContext('UI.renderAll(fixture)', context);
    assert.doesNotMatch(nodes.get('niche0Ideas').innerHTML, /Fabric gift pouch|FAKE_CLAIM/);
    assert.doesNotMatch(nodes.get('topIdeasGrid').innerHTML, /Fabric gift pouch|FAKE_CLAIM/);
  }
});

test('phase 8 escapes source and proposal strings and never renders model-supplied links', () => {
  const { context, nodes } = environment();
  const fixture = phase8Payload();
  const niche = fixture.niches.Fixture;
  for (const item of [niche.ideas[0], niche.grounded_analysis.ideas[0], fixture.analysis_summary.top_ideas[0]]) {
    item.name = '<img src=x onerror=bad()>';
    item.why_now = '<script>bad()</script>';
  }
  niche.products[0].provenance.source_url = 'javascript:bad()';
  niche.products[0].provenance.retrieved_at = '<svg onload=bad()>';
  context.fixture = fixture;
  vm.runInContext('UI.renderAll(fixture)', context);
  const html = nodes.get('topIdeasGrid').innerHTML + nodes.get('niche0Ideas').innerHTML;
  assert.doesNotMatch(html, /<img|<script|<svg|href="javascript:/);
  assert.match(html, /&lt;img/);
  assert.match(html, /href="#"/);
  assert.doesNotMatch(html, /evil.test/);
});

test('phase 8 stale cards clear on invalid results and deterministic fallback remains visible', () => {
  const { context, nodes } = environment();
  context.fixture = phase8Payload();
  vm.runInContext('UI.renderAll(fixture)', context);
  vm.runInContext("UI.renderAll({status: 'partial', niches: {Fixture: {analysis_status: 'invalid_output', analysis_text: 'Observed fallback only', ideas: []}}})", context);
  assert.doesNotMatch(nodes.get('topIdeasGrid').innerHTML, /Fabric gift pouch/);
  assert.match(nodes.get('niche0Analysis').innerHTML, /Observed fallback only/);
});

test('phase 8 canonical selection slots are not renumbered and unavailable summaries fail closed', () => {
  const { context, nodes } = environment();
  context.fixture = phase8Payload();
  context.fixture.analysis_summary.top_ideas[0].selection_position = 2;
  vm.runInContext('UI.renderAll(fixture)', context);
  assert.match(nodes.get('topIdeasGrid').innerHTML, /Đề xuất thử nghiệm #2/);
  assert.doesNotMatch(nodes.get('topIdeasGrid').innerHTML, /Đề xuất thử nghiệm #1/);
  context.fixture.analysis_summary.status = 'unavailable_no_grounded_ranked_ideas';
  vm.runInContext('UI.renderAll(fixture)', context);
  assert.doesNotMatch(nodes.get('topIdeasGrid').innerHTML, /Fabric gift pouch/);
});
