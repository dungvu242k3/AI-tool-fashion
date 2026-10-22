/**
 * UI Renderer Module.
 * Responsible for pure DOM manipulation and data visualization.
 */
const UI = {
  selectedTab: 'summary',
  progressJob: null,

  selectTab(id) {
    const pane = document.getElementById(`tab-${id}`);
    if (!pane) return;
    this.selectedTab = id;
    document.querySelectorAll('[data-tab]').forEach(button => {
      const selected = button.dataset.tab === id;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
      button.setAttribute('tabindex', selected ? '0' : '-1');
    });
    document.querySelectorAll('.tab-pane').forEach(panel => {
      const selected = panel.id === `tab-${id}`;
      panel.classList.toggle('active', selected);
      panel.hidden = !selected;
    });
  },

  sourceBadge(state, offline = false) {
    const status = state?.status;
    let label = 'Unknown', tone = 'unknown';
    if (status === 'not_configured') label = 'Not configured';
    if (status === 'failed') { label = 'Failed'; tone = 'failed'; }
    if (status === 'partial') { label = 'Partial'; tone = 'partial'; }
    if (status === 'success') {
      if (offline) label = 'Snapshot';
      else if (Number.isInteger(state.record_count) && state.record_count > 0 && state.cached_record_count === state.record_count) label = 'Cached';
      else if (Number.isSafeInteger(state.record_count) && state.record_count > 0 && Number.isSafeInteger(state.cached_record_count)
        && state.cached_record_count >= 0 && state.cached_record_count < state.record_count
        && state.is_live === true && state.live_attempted === true && state.request_count > 0) { label = state.cached_record_count > 0 ? 'Live + cache' : 'Live'; tone = 'live'; }
      else label = 'Success — chưa xác nhận live';
    }
    if (offline && status !== 'success') label = `Snapshot — ${label}`;
    return `<span class="source-badge source-${tone}">${label}</span>`;
  },

  renderNiches(data) {
    const entries = Object.entries(data.niches || {}).slice(0, 100);
    const tabs = document.getElementById('nicheTabs');
    const panes = document.getElementById('nichePanes');
    if (!tabs || !panes) return;
    const offline = data.metadata?.execution_kind === 'offline_publication_audit';
    tabs.innerHTML = entries.map(([name], index) => `<button id="tab-button-niche${index}" type="button" class="tab-btn" role="tab" data-tab="niche${index}" aria-controls="tab-niche${index}" aria-selected="false">${this.escape(name)}</button>`).join('');
    panes.innerHTML = entries.map(([name, niche], index) => `<section id="tab-niche${index}" class="tab-pane" role="tabpanel" aria-labelledby="tab-button-niche${index}" hidden><div class="content-card">
      <h2>${this.escape(name)}</h2><div class="source-badges">${Object.entries(niche.source_statuses || data.source_statuses?.[name] || {}).map(([source, state]) => `<p>${this.escape(source)}: ${this.sourceBadge(state, offline)}</p>`).join('')}</div>
      <h3 class="card-title">Keyword có số đo</h3><div id="niche${index}Keywords" class="grid-3"></div>
      <h3 class="card-title">Dữ kiện, phân tích và giới hạn</h3><div id="niche${index}Analysis" class="analysis-box"></div>
      <h3 class="card-title">Mẫu sản phẩm Amazon</h3><div id="niche${index}Products" class="grid-3"></div>
      <h3 class="card-title">Mẫu bài viết Reddit</h3><div id="niche${index}Discussions" class="grid-3"></div>
      <h3 class="card-title">Đề xuất thử nghiệm chưa xác minh market fit</h3><div id="niche${index}Ideas" class="grid-3"></div>
    </div></section>`).join('');
    entries.forEach(([, niche], index) => this.renderNicheDetails(`niche${index}`, niche));
    if (!['summary', 'report', ...entries.map((_, index) => `niche${index}`)].includes(this.selectedTab)) this.selectedTab = 'summary';
    this.selectTab(this.selectedTab);
  },

  renderJob(job) {
    const box = document.getElementById('progressBox');
    if (box) box.style.display = 'block';
    if (this.progressJob !== job.job_id) {
      this.progressJob = job.job_id;
      for (let index = 1; index <= 5; index++) {
        const badge = document.getElementById(`step${index}`);
        if (badge) badge.className = 'step-badge';
      }
    }
    document.getElementById('jobReference').innerText = `Job ID: ${job.job_id}`;
    if (job.progress) {
      this.setStepProgress(job.progress.step, `${job.progress.title}${job.progress.detail ? ' — ' + job.progress.detail : ''}`);
    } else {
      document.getElementById('statusText').innerText = job.status === 'queued' ? 'Job đã được nhận; đang chờ worker.' : 'Worker đang chạy; chưa có bước tiến trình được gửi về.';
    }
  },
  /**
   * Defensive utility to sanitize untrusted text and prevent DOM XSS.
   */
  escape(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  /**
   * Validates URLs to only allow legitimate http/https links.
   */
  safeUrl(url) {
    if (!url || typeof url !== 'string') return '#';
    const trimmed = url.trim();
    if (/^https?:\/\//i.test(trimmed)) {
      return this.escape(trimmed);
    }
    return '#';
  },

  observedMetric(record, name) {
    return record.raw_metric && Object.prototype.hasOwnProperty.call(record.raw_metric, name)
      ? record.raw_metric[name] : record[name];
  },

  qualityGatePassed(assessment) {
    return assessment?.gate_passed === true && ['sufficient', 'partial'].includes(assessment.status);
  },

  renderQualityAssessment(assessment) {
    if (!assessment || typeof assessment !== 'object' || Array.isArray(assessment)) return '';
    const count = value => Number.isSafeInteger(value) && value >= 0 ? this.escape(value) : '—';
    const ratio = Number.isFinite(assessment.valid_ratio) && assessment.valid_ratio >= 0 && assessment.valid_ratio <= 1
      ? (assessment.valid_ratio * 100).toFixed(1) + '%' : 'chưa xác định';
    const issues = Array.isArray(assessment.issues) ? assessment.issues.slice(0, 30) : [];
    return `<div class="data-quality"><strong>${this.qualityGatePassed(assessment) ? 'Đạt gate tối thiểu' : 'Dữ liệu chưa đủ'}</strong>
      <p>Candidate hợp lệ: ${count(assessment.valid_count)}/${count(assessment.candidate_count)} (${ratio}); loại: ${count(assessment.rejected_count)}; trùng: ${count(assessment.duplicate_count)}.</p>
      <p>Phủ nguồn cấu hình: ${count(assessment.observed_source_count)}/${count(assessment.configured_source_count)}; keyword có series: ${count(assessment.qualifying_keyword_count)}; evidence bổ sung: ${count(assessment.supporting_record_count)}.</p>
      ${issues.map(issue => `<p>${this.escape(issue?.message || '')}</p>`).join('')}</div>`;
  },

  redditCreatedAt(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return 'Chưa có dữ liệu';
    const date = new Date(value * 1000);
    return Number.isFinite(date.getTime()) ? date.toISOString() : 'Chưa có dữ liệu';
  },

  renderRedditPainPoints(points, discussions) {
    if (!Array.isArray(points) || !Array.isArray(discussions)) return '';
    const evidence = new Map(discussions.filter(d => d && typeof d.provenance?.evidence_id === 'string').map(d => [d.provenance.evidence_id, d]));
    const accepted = points.slice(0, 5).filter(p => p && typeof p.quote === 'string' && p.quote.length >= 8 && p.quote.length <= 500
      && Array.isArray(p.evidence_ids) && p.evidence_ids.length > 0 && p.evidence_ids.length <= 5
      && new Set(p.evidence_ids).size === p.evidence_ids.length && p.evidence_ids.every(id => {
        const post = evidence.get(id);
        return typeof id === 'string' && post && ((typeof post.selftext === 'string' && post.selftext.includes(p.quote))
          || (typeof post.title === 'string' && post.title.includes(p.quote)));
      }));
    if (!accepted.length) return '';
    return '<div class="card-item"><p>Trích dẫn ứng viên pain point — cần đọc ngữ cảnh, không đại diện toàn thị trường:</p>'
      + accepted.map(p => `<p>${this.escape(p.quote)} — ${p.evidence_ids.map(id => `<a href="${this.safeUrl(evidence.get(id).url)}" target="_blank" rel="noopener noreferrer">Evidence ${this.escape(id)}</a>`).join(', ')}</p>`).join('') + '</div>';
  },

  /**
   * Updates top metrics cards.
   */
  renderMetrics(metadata = {}) {
    const elNiches = document.getElementById('metricNiches');
    const elKeywords = document.getElementById('metricKeywords');
    const elProducts = document.getElementById('metricProducts');
    const elElapsed = document.getElementById('metricElapsed');

    if (elNiches) elNiches.innerText = metadata.total_niches ?? '—';
    if (elKeywords) elKeywords.innerText = metadata.total_keywords ?? '—';
    if (elProducts) elProducts.innerText = metadata.total_products ?? '—';
    if (elElapsed) elElapsed.innerText = metadata.elapsed_seconds == null ? '—' : `${metadata.elapsed_seconds}s`;
  },

  renderStatus(data) {
    const panel = document.getElementById('dataStatus');
    if (!panel) return;
    const metadata = data.metadata || {};
    const labels = { running: 'Đang thực thi', connection_lost: 'Chưa xác nhận trạng thái job', success: 'Đầy đủ', partial: 'Chưa đầy đủ', failed: 'Không thu thập được', legacy: 'Báo cáo cũ chưa kiểm chứng', no_report: 'Chưa có báo cáo', invalid_cache: 'Cache không hợp lệ' };
    let html = `<p><strong>${this.escape(labels[data.status] || 'Chưa có kết quả')}</strong>: ${this.escape(data.message || '')}</p>`;
    if (data.status === 'partial' || data.status === 'failed') {
      html += '<p role="alert"><strong>BÁO CÁO CHƯA ĐẦY ĐỦ — không đủ cơ sở xác nhận toàn bộ khuyến nghị.</strong></p>';
    }
    if (metadata.run_id) html += `<p>Run ID: ${this.escape(metadata.run_id)}</p>`;
    if (metadata.timestamp) html += `<p>Thời gian tạo: ${this.escape(metadata.timestamp)}</p>`;
    if (metadata.execution_kind) html += `<p>Loại lần chạy: ${this.escape(metadata.execution_kind)}</p>`;
    if (metadata.requested_mode) html += `<p>Chế độ yêu cầu: ${this.escape(metadata.requested_mode)}</p>`;
    if (metadata.mode) {
      const mode = metadata.mode === 'deterministic' ? 'Tổng hợp dữ liệu; không có đầu ra AI được sử dụng' : metadata.mode;
      html += `<p>Chế độ thực tế: ${this.escape(mode)}${metadata.model_name ? ' — ' + this.escape(metadata.model_name) : ''}</p>`;
    }
    if (metadata.model_attempted) html += `<p>Model đã thử gọi: ${this.escape(metadata.model_attempted)}</p>`;
    if (metadata.execution_kind === 'offline_publication_audit') {
      html += '<p>Trạng thái và request dưới đây thuộc snapshot gốc, không phải request mới trong audit.</p>';
    }
    const sourceRows = Object.entries(data.source_statuses || {}).flatMap(([niche, sources]) =>
      Object.entries(sources).map(([source, result]) => `<li>${this.escape(niche)} / ${this.escape(source)}: ${this.sourceBadge(result, metadata.execution_kind === 'offline_publication_audit')} ${this.escape(result.status)} (${this.escape(result.record_count)} bản ghi${result.request_count == null ? '' : ', ' + this.escape(result.request_count) + ' request mới'}${result.cached_record_count ? ', ' + this.escape(result.cached_record_count) + ' bản ghi từ cache' : ''})</li>`)
    );
    if (sourceRows.length) html += `<ul>${sourceRows.join('')}</ul>`;
    const healthRows = Object.entries(data.source_health || {}).map(([source, health]) =>
      `<li>${this.escape(source)}: ${this.escape(health.status)}; ${this.escape(health.request_count)} request mới; ${this.escape(health.retry_count)} retry${health.cached_record_count ? '; ' + this.escape(health.cached_record_count) + ' bản ghi từ cache' : ''}</li>`
    );
    if (healthRows.length) html += `<p>Tình trạng nguồn toàn lần chạy:</p><ul>${healthRows.join('')}</ul>`;
    if (metadata.warnings?.length) html += `<ul>${metadata.warnings.map(w => `<li>${this.escape(w)}</li>`).join('')}</ul>`;
    panel.innerHTML = html;
    panel.dataset.status = data.status || '';
  },

  /**
   * Renders the Niche ranking table.
   */
  renderRanking(assessment, niches = {}) {
    const tbody = document.getElementById('rankingBody');
    if (!tbody) return;
    const supported = assessment?.method === 'fixed_weight_observed_evidence_v1';
    const rows = supported && ['available', 'partial'].includes(assessment.status) && Array.isArray(assessment.ranking) ? assessment.ranking.slice(0, 100).filter(row =>
      row?.status === 'ranked' && Number.isSafeInteger(row.rank) && row.rank > 0
      && typeof row.niche === 'string' && Object.prototype.hasOwnProperty.call(niches, row.niche)
      && this.qualityGatePassed(niches[row.niche]?.quality_assessment)
      && typeof row.observed_score === 'number' && Number.isFinite(row.observed_score)
      && row.observed_score >= 0 && row.observed_score <= 100) : [];
    const number = value => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(6) : 'chưa có dữ liệu';
    const percent = value => typeof value === 'number' && Number.isFinite(value) ? (value * 100).toFixed(1) + '%' : 'chưa xác định';
    let html = rows.length ? rows.map(row => `<tr>
      <td><span class="tag-rank">Hạng ${this.escape(row.rank)}</span></td>
      <td><strong>${this.escape(row.niche)}</strong></td>
      <td>Quan sát: ${number(row.observed_score)}/100<br>Tổng đủ 5 nhóm: ${number(row.total_score)}<br>Cận trên: ${number(row.score_upper_bound)}<br>Phủ trọng số: ${percent(row.component_coverage)}<br>Confidence dữ liệu: ${typeof row.confidence === 'number' && Number.isFinite(row.confidence) ? number(row.confidence) + '%' : 'chưa xác định'}</td>
      <td>${this.escape(row.explanation)}${this.renderRankingBreakdown(row.components)}</td>
    </tr>`).join('') : '<tr><td colspan="4" class="empty-state">Chưa có niche đủ điều kiện xếp hạng; không tự tạo điểm.</td></tr>';
    if (supported) {
      const unranked = Array.isArray(assessment.unranked) ? assessment.unranked.slice(0, 100) : [];
      html += unranked.map(row => `<tr><td>Chưa xếp hạng</td><td>${this.escape(row?.niche)}</td><td>Chưa đủ dữ liệu so sánh</td><td>${this.escape(row?.explanation)}${this.renderRankingBreakdown(row?.components)}</td></tr>`).join('');
      html += `<tr><td colspan="4">Method: ${this.escape(assessment.method)}; policy: ${this.escape(assessment.policy_id)}.
        ${(Array.isArray(assessment.warnings) ? assessment.warnings.slice(0, 10) : []).map(note => `<p>${this.escape(note)}</p>`).join('')}</td></tr>`;
    }
    tbody.innerHTML = html;
  },

  renderRankingBreakdown(components) {
    if (!Array.isArray(components)) return '';
    const number = value => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(6) : 'chưa có dữ liệu';
    return '<details><summary>Breakdown, công thức và evidence</summary>' + components.slice(0, 5).map(component => {
      const inputs = Array.isArray(component?.inputs) ? component.inputs : [];
      return `<section><p><strong>${this.escape(component?.label)}</strong>: ${number(component?.score)}/100; trọng số ${number(component?.weight)}; contribution ${number(component?.contribution)}; mẫu ${this.escape(component?.sample_size)}/${this.escape(component?.candidate_count)}.</p>
        <p>${this.escape(component?.status)} / ${this.escape(component?.reason)}</p><p>${this.escape(component?.formula)}</p>
        ${inputs.slice(0, 20).map(item => `<p><a href="${this.safeUrl(item?.source_url)}" target="_blank" rel="noopener noreferrer">Evidence ${this.escape(item?.evidence_id)}</a>: ${this.escape(item?.identity)}; ${this.escape(JSON.stringify(item?.measurements || {}))}; thu thập ${this.escape(item?.retrieved_at)}; request ${this.escape(item?.request_id)}${item?.from_cache ? '; cache giữ timestamp gốc' : ''}.</p>`).join('')}
        ${inputs.length > 20 ? '<p>Còn evidence trong JSON/báo cáo đầy đủ.</p>' : ''}</section>`;
    }).join('') + '</details>';
  },

  /**
   * Renders top opportunities cards.
   */
  groundedAnalysisAccepted(niche) {
    const analysis = niche?.grounded_analysis;
    return this.qualityGatePassed(niche?.quality_assessment) && niche.analysis_status === 'success'
      && niche.generation_mode === 'ollama' && niche.ai_validation?.outcome === 'source_references_verified'
      && analysis?.schema_version === 'grounded-analysis-v1'
      && typeof analysis.evidence_digest === 'string' && /^[a-f0-9]{64}$/.test(analysis.evidence_digest)
      && analysis.evidence_digest === niche.quality_assessment.data_digest
      && analysis.niche_name === (niche.niche_name || niche.name)
      && Array.isArray(analysis.facts) && analysis.facts.length <= 16
      && Array.isArray(analysis.quotes) && analysis.quotes.length <= 5 && Array.isArray(analysis.ideas) && analysis.ideas.length <= 3;
  },

  ideaEvidenceRecords(ids, niche) {
    if (!Array.isArray(ids) || !ids.length || ids.length > 12 || new Set(ids).size !== ids.length) return [];
    const pool = ['keywords', 'products', 'discussions'].flatMap(key => Array.isArray(niche?.[key]) ? niche[key].slice(0, 1000) : []);
    const records = new Map(pool.filter(record => record?.provenance?.evidence_id).map(record => [record.provenance.evidence_id, record]));
    return ids.every(id => typeof id === 'string' && records.has(id)) ? ids.map(id => records.get(id)) : [];
  },

  groundedIdeaAccepted(idea, niche) {
    if (!this.groundedAnalysisAccepted(niche) || idea?.kind !== 'proposal_not_verified_market_fit'
      || idea.validation_status !== 'source_references_verified' || typeof idea.idea_id !== 'string') return false;
    const canonical = niche.grounded_analysis.ideas.slice(0, 3).find(item => item?.idea_id === idea.idea_id);
    if (!canonical || !['name', 'rationale', 'target_audience', 'why_now', 'kind', 'validation_status']
      .every(key => typeof idea[key] === 'string' && idea[key] === canonical[key])) return false;
    const sameIds = key => Array.isArray(idea[key]) && Array.isArray(canonical[key])
      && idea[key].length === canonical[key].length && idea[key].every((id, index) => id === canonical[key][index]);
    if (!['evidence_ids', 'basis_fact_ids', 'basis_quote_ids'].every(sameIds)) return false;
    if (!idea.basis_fact_ids.length || idea.basis_fact_ids.length > 8 || idea.basis_quote_ids.length > 5) return false;
    const facts = new Map(niche.grounded_analysis.facts.filter(fact => fact?.kind === 'fact').map(fact => [fact.fact_id, fact]));
    const quotes = new Map(niche.grounded_analysis.quotes.filter(quote => quote?.quote_id).map(quote => [quote.quote_id, quote]));
    if (!idea.basis_fact_ids.every(id => facts.has(id)) || !idea.basis_quote_ids.every(id => quotes.has(id))) return false;
    const basis = [...idea.basis_fact_ids.map(id => facts.get(id)), ...idea.basis_quote_ids.map(id => quotes.get(id))];
    if (!basis.every(item => Array.isArray(item.evidence_ids))) return false;
    const expectedIds = new Set(basis.flatMap(item => item.evidence_ids));
    if (expectedIds.size !== idea.evidence_ids.length || !idea.evidence_ids.every(id => expectedIds.has(id))) return false;
    return this.ideaEvidenceRecords(idea.evidence_ids, niche).length === idea.evidence_ids.length;
  },

  renderIdeaEvidence(ids, niche) {
    return this.ideaEvidenceRecords(ids, niche).map(record => {
      const provenance = record.provenance;
      return `<a href="${this.safeUrl(provenance.source_url)}" target="_blank" rel="noopener noreferrer">Evidence ${this.escape(provenance.evidence_id)}</a> (${this.escape(provenance.retrieved_at)})`;
    }).join(', ');
  },

  renderTopIdeas(assessment, niches = {}) {
    const container = document.getElementById('topIdeasGrid');
    if (!container) return;
    const topIdeas = assessment?.method === 'grounded_research_slots_round_robin_v1'
      && ['available', 'partial'].includes(assessment.status) && Array.isArray(assessment.top_ideas)
      ? assessment.top_ideas.slice(0, 3).filter(idea => typeof idea?.niche === 'string'
        && Number.isSafeInteger(idea.selection_position) && idea.selection_position >= 1 && idea.selection_position <= 3
        && Object.prototype.hasOwnProperty.call(niches, idea.niche) && this.groundedIdeaAccepted(idea, niches[idea.niche])) : [];
    if (!topIdeas.length) {
      container.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">Chưa có đề xuất đã kiểm tra evidence từ niche đủ điều kiện; không tự tạo Top 3.</div>
      `;
      return;
    }

    container.innerHTML = topIdeas.map(item => `
      <div class="card-item">
        <div>
          <div style="font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; text-transform: uppercase;">
            Đề xuất thử nghiệm #${this.escape(item.selection_position)} &bull; ${this.escape(item.niche)}
          </div>
          <div class="card-item-title">${this.escape(item.name)}</div>
          <div class="field-row">
            <span class="field-label">Sản phẩm đề xuất</span>
            <span class="field-val">${this.escape(item.rationale)}</span>
          </div>
          <div class="field-row">
            <span class="field-label">Đối tượng giả định</span>
            <span class="field-val">${this.escape(item.target_audience)}</span>
          </div>
          <div class="field-row">
            <span class="field-label">Cơ sở lựa chọn</span>
            <span class="field-val">${this.escape(item.why_now)}</span>
          </div>
        </div>
        <div class="card-footer">Đề xuất chưa kiểm chứng market fit; không phải dự báo doanh số/lợi nhuận.<br>${this.renderIdeaEvidence(item.evidence_ids, niches[item.niche])}</div>
      </div>
    `).join('');
  },

  /**
   * Renders details for a specific niche tab (keywords, products, ideas).
   */
  /**
   * Renders details for a specific niche tab:
   * 1. Keywords (with score, trend, related queries, Google Trends link)
   * 2. Analysis (market trend, customer profile & pain points, competition & price range)
   * 3. Competitor Products (Amazon title, price, rating, reviews, link)
   * 4. Community Discussions (source excerpts, score, comments, evidence; no fabricated summary)
   * 5. Proposed Product Ideas (what to sell, target audience, why sell now)
   */
  renderAmazonListings(listings) {
    if (!Array.isArray(listings) || !listings.length) return '';
    const labels = { search: 'Amazon Search', best_sellers: 'Amazon Best Sellers', movers_shakers: 'Amazon Movers & Shakers' };
    return `<ul>${listings.slice(0, 8).map(listing => {
      const position = listing.source_type === 'search'
        ? `Vị trí tìm kiếm: ${this.escape(listing.search_position ?? 'Chưa rõ')}`
        : `Hạng trong danh sách: ${this.escape(listing.listing_rank ?? 'Chưa có số đo')}`;
      return `<li><a href="${this.safeUrl(listing.listing_url)}" target="_blank" rel="noopener noreferrer">${labels[listing.source_type] || 'Amazon (nguồn chưa xác minh)'}</a> — ${position}${listing.is_sponsored === true ? ' — Sponsored' : ''}</li>`;
    }).join('')}</ul>`;
  },

  renderNicheDetails(prefix, nData) {
    if (!nData) return;
    const allowRecommendations = this.qualityGatePassed(nData.quality_assessment)
      && nData.data_quality !== 'insufficient' && nData.analysis_status !== 'insufficient_data';

    // 1. Keywords
    const kwBox = document.getElementById(`${prefix}Keywords`);
    if (kwBox && nData.keywords) {
      kwBox.innerHTML = nData.keywords.map(k => {
        const queries = (k.related_queries || []).slice(0, 3).map(q => 
          `<span class="query-chip">${this.escape(q)}</span>`
        ).join('');
        const suggestions = (k.suggestions || []).map(q => this.escape(q)).join(', ');
        const observedScore = this.observedMetric(k, 'score');
        const calculation = k.derived_metric ?? k.metrics;
        const growth = Number.isFinite(calculation?.growth_percent) ? calculation.growth_percent.toFixed(2) + '%' : 'Chưa xác định';
        const metrics = Number.isFinite(calculation?.window_points_used) ? `<p>Thay đổi interest trung bình: ${growth}; ${this.escape(calculation.window_points_used)} điểm/cửa sổ.</p>` : '';

        return `
        <div class="card-item" style="padding: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong style="color: #fff; font-size: 14px;">${this.escape(k.keyword)}</strong>
            <span class="tag-potential" style="text-transform: uppercase; font-size: 10px;">${this.escape(k.trend)}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px;">
            Điểm quan tâm gốc: <strong>${Number.isFinite(observedScore) ? observedScore.toFixed(0) + '/100' : 'Chưa có số đo'}</strong>
          </div>
          <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.4;">
            ${this.escape(k.signal_summary || '')}
          </p>
          ${queries ? `<div style="margin-bottom: 10px;">${queries}</div>` : ''}
          ${metrics}
          ${suggestions ? `<p>Google Suggest (gợi ý, không phải tín hiệu tăng trưởng): ${suggestions}</p>` : ''}
          ${k.provenance?.from_cache ? `<p>Dữ liệu từ cache; thu thập gốc: ${this.escape(k.provenance.retrieved_at)}</p>` : ''}
          <a href="${this.safeUrl(k.source_url)}" target="_blank" rel="noopener noreferrer" class="link-out">Mở Google Trends &rarr;</a>
        </div>
      `;
      }).join('') || '<div class="empty-state">Không có keyword với số đo hợp lệ.</div>';
    }

    // 2. Analysis (TASK-1 Mandatory Section 2)
    const anaBox = document.getElementById(`${prefix}Analysis`);
    if (anaBox) {
      const text = nData.analysis_status === 'success' && (!allowRecommendations || !this.groundedAnalysisAccepted(nData)) ? '' : nData.analysis_text || '';
      if (text) {
        const lines = text.split('\n');
        let htmlContent = '';
        lines.forEach(line => {
          line = line.trim();
          if (!line) return;
          // Format markdown bold **text** -> <strong>text</strong>
          let formatted = this.escape(line).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
          if (line.startsWith('- ')) {
            htmlContent += `<div class="analysis-bullet"><span class="bullet-dot">&bull;</span><div>${formatted.substring(2)}</div></div>`;
          } else if (line.startsWith('  - ')) {
            htmlContent += `<div class="analysis-subbullet"><span class="bullet-dash">&ndash;</span><div>${formatted.substring(4)}</div></div>`;
          } else {
            htmlContent += `<p style="margin-bottom: 8px;">${formatted}</p>`;
          }
        });
        anaBox.innerHTML = htmlContent;
      } else {
        anaBox.innerHTML = `<div class="empty-state">Chưa có dữ liệu phân tích thị trường.</div>`;
      }
      anaBox.innerHTML = this.renderQualityAssessment(nData.quality_assessment) + anaBox.innerHTML;
    }

    // 3. Competitor Products (Amazon)
    const prdBox = document.getElementById(`${prefix}Products`);
    if (prdBox && nData.products) {
      prdBox.innerHTML = nData.products.slice(0, 3).map(p => {
        const price = this.observedMetric(p, 'price');
        const rating = this.observedMetric(p, 'rating');
        const reviews = this.observedMetric(p, 'reviews_count');
        return `
        <div class="card-item" style="padding: 16px;">
          <div style="font-size: 13px; font-weight: 600; color: #fff; margin-bottom: 6px; line-height: 1.4;">${this.escape(p.title)}</div>
          <p>${this.escape(p.source || 'Amazon')}${p.asin ? ' — ASIN: ' + this.escape(p.asin) : ''}${p.is_sponsored === true ? ' — Sponsored' : ''}</p>
          <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 10px;">
            <span style="color: #34d399; font-weight: 600;">${this.escape(price ?? 'Chưa có giá')}</span>
            <span style="color: var(--text-tertiary);">${rating == null ? 'Chưa có rating' : this.escape(rating) + ' &#9733;'} (${this.escape(reviews ?? 'Chưa có số đánh giá')})</span>
          </div>
          ${this.renderAmazonListings(p.listings || [])}
          <a href="${this.safeUrl(p.url)}" target="_blank" rel="noopener noreferrer" class="link-out">Xem trên Amazon &rarr;</a>
        </div>
      `;
      }).join('') || '<div class="empty-state">Không thu thập được sản phẩm Amazon.</div>';
    }

    // 4. Community Discussions (Reddit)
    const discBox = document.getElementById(`${prefix}Discussions`);
    if (discBox) {
      if (nData.discussions && nData.discussions.length > 0) {
        discBox.innerHTML = nData.discussions.slice(0, 3).map(d => {
          const score = this.observedMetric(d, 'score');
          const comments = this.observedMetric(d, 'comments');
          const created = this.observedMetric(d, 'created_utc');
          return `
          <div class="card-item" style="padding: 16px;">
            <div style="font-size: 13px; font-weight: 600; color: #fff; margin-bottom: 6px; line-height: 1.4;">${this.escape(d.title)}</div>
            <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.4;">${this.escape(d.content_summary || '')}</p>
            <div class="discussion-meta" style="margin-bottom: 10px;">
              <span>&#9650; Điểm Reddit: ${this.escape(score ?? 'Chưa có dữ liệu')}</span>
              <span>&#128172; ${this.escape(comments ?? 'Chưa có dữ liệu')} bình luận</span>
            </div>
            <p style="font-size: 11px; color: var(--text-tertiary);">${this.escape(d.source || 'Reddit')} · Adapter: ${this.escape(d.provider ?? 'Chưa có dữ liệu')} · ID: ${this.escape(d.post_id ?? 'Chưa có dữ liệu')} · Tạo: ${this.escape(this.redditCreatedAt(created))}</p>
            ${d.provenance ? `<p style="font-size: 11px; color: var(--text-tertiary);">Evidence: ${this.escape(d.provenance.evidence_id)} · Thu thập: ${this.escape(d.provenance.retrieved_at)}</p>` : ''}
            <a href="${this.safeUrl(d.url)}" target="_blank" rel="noopener noreferrer" class="link-out">Xem bài viết trên Reddit &rarr;</a>
          </div>
        `;
        }).join('');
        if (allowRecommendations) discBox.innerHTML += this.renderRedditPainPoints(nData.reddit_pain_points || [], nData.discussions);
      } else {
        discBox.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1;">Không có bài thảo luận mới được ghi nhận.</div>`;
      }
    }

    // 5. Product Ideas (TASK-1 Mandatory Section 3)
    const ideasBox = document.getElementById(`${prefix}Ideas`);
    if (ideasBox) {
      if (!allowRecommendations) {
        ideasBox.innerHTML = '<div class="empty-state">Dữ liệu chưa đủ hoặc chưa được đánh giá; không hiển thị ý tưởng/khuyến nghị.</div>';
        return;
      }
      const acceptedIdeas = (Array.isArray(nData.ideas) ? nData.ideas : []).filter(idea => this.groundedIdeaAccepted(idea, nData));
      ideasBox.innerHTML = acceptedIdeas.map((idea, idx) => `
        <div class="card-item">
          <div>
            <div style="font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; text-transform: uppercase;">Đề xuất chưa kiểm chứng #${idx + 1}</div>
            <div class="card-item-title">${this.escape(idea.name)}</div>
            <div class="field-row">
              <span class="field-label">Bán cái gì</span>
              <span class="field-val">${this.escape(idea.rationale || idea.name)}</span>
            </div>
            <div class="field-row">
              <span class="field-label">Cho ai (giả định)</span>
              <span class="field-val">${this.escape(idea.target_audience)}</span>
            </div>
            <div class="field-row">
              <span class="field-label">Vì sao nên bán bây giờ</span>
              <span class="field-val">${this.escape(idea.why_now)}</span>
            </div>
            <p>${this.renderIdeaEvidence(idea.evidence_ids, nData)}</p>
          </div>
        </div>
      `).join('') || '<div class="empty-state">Chưa có đề xuất grounded được chấp nhận; không hiển thị ý tưởng tự do hoặc dữ liệu thay thế.</div>';
    }
  },

  /**
   * Renders the raw markdown content into pre element.
   */
  renderMarkdown(markdownText) {
    const rawBox = document.getElementById('rawReportText');
    if (rawBox) {
      rawBox.innerText = markdownText || 'Chưa có báo cáo được nạp.';
    }
  },

  /**
   * Renders the complete dashboard dataset.
   */
  renderAll(data) {
    if (!data) return;
    this.renderStatus(data);
    this.renderMetrics(data.metadata);
    this.renderRanking(data.ranking_assessment, data.niches || {});
    this.renderTopIdeas(data.analysis_summary, data.niches || {});
    this.renderMarkdown(data.markdown_content);
    const category = document.getElementById('categoryDisplay');
    if (category) category.innerText = data.metadata?.category ? `Danh mục báo cáo: ${data.metadata.category}` : 'Chưa có báo cáo';
    this.renderNiches(data);
  },

  /**
   * Updates stepper progress state.
   */
  setStepProgress(stepNum, message) {
    const progressBox = document.getElementById('progressBox');
    const statusText = document.getElementById('statusText');

    if (progressBox) progressBox.style.display = 'block';
    if (statusText) statusText.innerText = message;

    for (let i = 1; i <= 5; i++) {
      const badge = document.getElementById(`step${i}`);
      if (badge) {
        if (i < stepNum) {
          badge.className = 'step-badge completed';
        } else if (i === stepNum) {
          badge.className = 'step-badge active';
        } else {
          badge.className = 'step-badge';
        }
      }
    }
  },

  /**
   * Completes the progress bar and hides it.
   */
  finishProgress(message, status = 'success') {
    for (let i = 1; i <= 5; i++) {
      const badge = document.getElementById(`step${i}`);
      if (badge) badge.className = status === 'success' ? 'step-badge completed' : 'step-badge';
    }
    const statusText = document.getElementById('statusText');
    if (statusText) statusText.innerText = message;

    // Remain visible until the next real job; an old timer must not hide a new job.
  },
};
