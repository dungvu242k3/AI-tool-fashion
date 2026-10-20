/**
 * UI Renderer Module.
 * Responsible for pure DOM manipulation and data visualization.
 */
const UI = {
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

  /**
   * Updates top metrics cards.
   */
  renderMetrics(metadata) {
    if (!metadata) return;
    const elNiches = document.getElementById('metricNiches');
    const elKeywords = document.getElementById('metricKeywords');
    const elProducts = document.getElementById('metricProducts');
    const elElapsed = document.getElementById('metricElapsed');

    if (elNiches) elNiches.innerText = metadata.total_niches || 3;
    if (elKeywords) elKeywords.innerText = metadata.total_keywords || 0;
    if (elProducts) elProducts.innerText = metadata.total_products || 0;
    if (elElapsed) elElapsed.innerText = `${metadata.elapsed_seconds || 0}s`;
  },

  /**
   * Renders the Niche ranking table.
   */
  renderRanking(rankingList) {
    const tbody = document.getElementById('rankingBody');
    if (!tbody) return;

    if (!rankingList || rankingList.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" class="empty-state">Chưa có dữ liệu phân tích. Nhấn <strong>"Chạy phân tích xu hướng"</strong> để bắt đầu.</td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = rankingList.map(r => `
      <tr>
        <td><span class="tag-rank">Hạng ${this.escape(r.rank)}</span></td>
        <td><strong>${this.escape(r.niche)}</strong></td>
        <td><span class="tag-potential">${this.escape(r.potential)}</span></td>
        <td style="color: var(--text-secondary);">${this.escape(r.recommendation)}</td>
      </tr>
    `).join('');
  },

  /**
   * Renders top opportunities cards.
   */
  renderTopIdeas(topIdeas) {
    const container = document.getElementById('topIdeasGrid');
    if (!container) return;

    if (!topIdeas || topIdeas.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">Chưa có dữ liệu sản phẩm. Dữ liệu sẽ hiển thị ngay sau khi phân tích.</div>
      `;
      return;
    }

    container.innerHTML = topIdeas.map((item, idx) => `
      <div class="card-item">
        <div>
          <div style="font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; text-transform: uppercase;">
            Ưu tiên #${idx + 1} &bull; ${this.escape(item.niche)}
          </div>
          <div class="card-item-title">${this.escape(item.title)}</div>
          <div class="field-row">
            <span class="field-label">Sản phẩm đề xuất</span>
            <span class="field-val">${this.escape(item.what_to_sell)}</span>
          </div>
          <div class="field-row">
            <span class="field-label">Khách hàng mục tiêu</span>
            <span class="field-val">${this.escape(item.target_audience)}</span>
          </div>
          <div class="field-row">
            <span class="field-label">Cơ sở lựa chọn</span>
            <span class="field-val">${this.escape(item.why_now)}</span>
          </div>
        </div>
        <div class="card-footer">${this.escape(item.financials)}</div>
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
   * 4. Community Discussions (Reddit title, upvotes, comments, pain point summary, link)
   * 5. Proposed Product Ideas (what to sell, target audience, why sell now)
   */
  renderNicheDetails(prefix, nData) {
    if (!nData) return;

    // 1. Keywords
    const kwBox = document.getElementById(`${prefix}Keywords`);
    if (kwBox && nData.keywords) {
      kwBox.innerHTML = nData.keywords.map(k => {
        const queries = (k.related_queries || []).slice(0, 3).map(q => 
          `<span class="query-chip">${this.escape(q)}</span>`
        ).join('');

        return `
        <div class="card-item" style="padding: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong style="color: #fff; font-size: 14px;">${this.escape(k.keyword)}</strong>
            <span class="tag-potential" style="text-transform: uppercase; font-size: 10px;">${this.escape(k.trend)}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px;">
            Điểm quan tâm: <strong>${Number(k.score || 0).toFixed(0)}/100</strong>
          </div>
          <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.4;">
            ${this.escape(k.signal_summary || '')}
          </p>
          ${queries ? `<div style="margin-bottom: 10px;">${queries}</div>` : ''}
          <a href="${this.safeUrl(k.source_url)}" target="_blank" rel="noopener noreferrer" class="link-out">Mở Google Trends &rarr;</a>
        </div>
      `;
      }).join('');
    }

    // 2. Analysis (TASK-1 Mandatory Section 2)
    const anaBox = document.getElementById(`${prefix}Analysis`);
    if (anaBox) {
      const text = nData.analysis_text || '';
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
    }

    // 3. Competitor Products (Amazon)
    const prdBox = document.getElementById(`${prefix}Products`);
    if (prdBox && nData.products) {
      prdBox.innerHTML = nData.products.slice(0, 3).map(p => `
        <div class="card-item" style="padding: 16px;">
          <div style="font-size: 13px; font-weight: 600; color: #fff; margin-bottom: 6px; line-height: 1.4;">${this.escape(p.title)}</div>
          <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 10px;">
            <span style="color: #34d399; font-weight: 600;">${this.escape(p.price)}</span>
            <span style="color: var(--text-tertiary);">${p.rating > 0 ? this.escape(p.rating) + ' &#9733; (' + (p.reviews_count || 0) + ')' : 'Top Seller'}</span>
          </div>
          <a href="${this.safeUrl(p.url)}" target="_blank" rel="noopener noreferrer" class="link-out">Xem trên Amazon &rarr;</a>
        </div>
      `).join('');
    }

    // 4. Community Discussions (Reddit)
    const discBox = document.getElementById(`${prefix}Discussions`);
    if (discBox) {
      if (nData.discussions && nData.discussions.length > 0) {
        discBox.innerHTML = nData.discussions.slice(0, 3).map(d => `
          <div class="card-item" style="padding: 16px;">
            <div style="font-size: 13px; font-weight: 600; color: #fff; margin-bottom: 6px; line-height: 1.4;">${this.escape(d.title)}</div>
            <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.4;">${this.escape(d.content_summary || '')}</p>
            <div class="discussion-meta" style="margin-bottom: 10px;">
              <span>&#9650; ${d.score || 0} upvotes</span>
              <span>&#128172; ${d.comments || 0} thảo luận</span>
            </div>
            <a href="${this.safeUrl(d.url)}" target="_blank" rel="noopener noreferrer" class="link-out">Xem bài viết trên Reddit &rarr;</a>
          </div>
        `).join('');
      } else {
        discBox.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1;">Không có bài thảo luận mới được ghi nhận.</div>`;
      }
    }

    // 5. Product Ideas (TASK-1 Mandatory Section 3)
    const ideasBox = document.getElementById(`${prefix}Ideas`);
    if (ideasBox && nData.ideas) {
      ideasBox.innerHTML = nData.ideas.map((idea, idx) => `
        <div class="card-item">
          <div>
            <div style="font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; text-transform: uppercase;">Ý TƯỞNG #${idx + 1}</div>
            <div class="card-item-title">${this.escape(idea.name)}</div>
            <div class="field-row">
              <span class="field-label">Bán cái gì</span>
              <span class="field-val">${this.escape(idea.rationale || idea.name)}</span>
            </div>
            <div class="field-row">
              <span class="field-label">Cho ai</span>
              <span class="field-val">${this.escape(idea.target_audience)}</span>
            </div>
            <div class="field-row">
              <span class="field-label">Vì sao nên bán bây giờ</span>
              <span class="field-val">${this.escape(idea.why_now)}</span>
            </div>
          </div>
        </div>
      `).join('');
    }
  },

  /**
   * Renders the raw markdown content into pre element.
   */
  renderMarkdown(markdownText) {
    const rawBox = document.getElementById('rawReportText');
    if (rawBox && markdownText) {
      rawBox.innerText = markdownText;
    }
  },

  /**
   * Renders the complete dashboard dataset.
   */
  renderAll(data) {
    if (!data) return;
    this.renderMetrics(data.metadata);
    this.renderRanking(data.ranking);
    this.renderTopIdeas(data.top_ideas);
    this.renderMarkdown(data.markdown_content);

    if (data.niches) {
      const nicheKeys = Object.keys(data.niches);
      nicheKeys.forEach((key, idx) => {
        if (idx < 3) {
          this.renderNicheDetails(`niche${idx}`, data.niches[key]);
        }
      });
    }
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
  finishProgress(message) {
    for (let i = 1; i <= 5; i++) {
      const badge = document.getElementById(`step${i}`);
      if (badge) badge.className = 'step-badge completed';
    }
    const statusText = document.getElementById('statusText');
    if (statusText) statusText.innerText = message;

    setTimeout(() => {
      const progressBox = document.getElementById('progressBox');
      if (progressBox) progressBox.style.display = 'none';
    }, 2800);
  },
};
