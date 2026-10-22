/** Research intent editor. All report metrics remain in the canonical result. */
const ResearchForm = {
  count: 0,
  limits: null,

  initialize(config) {
    if (!config?.defaults || !config?.limits || ![config.limits.min_niches, config.limits.max_niches, config.limits.max_keywords, config.limits.max_subreddits].every(Number.isSafeInteger)
      || config.limits.min_niches !== 3 || config.limits.max_niches !== 5 || config.limits.max_keywords < 1 || config.limits.max_keywords > 8
      || config.limits.max_subreddits < 0 || config.limits.max_subreddits > 4 || !['ollama', 'deterministic'].includes(config.defaults.mode)) throw new Error('Contract cấu hình Web không hợp lệ.');
    this.limits = config.limits;
    const defaults = config.defaults;
    for (const [id, key] of [['inputCategory', 'category'], ['inputGeo', 'geo'], ['inputTimeframe', 'timeframe'], ['inputMode', 'mode']]) {
      document.getElementById(id).value = defaults[key];
    }
    document.getElementById('modelConfiguration').innerText = `Ollama cấu hình: ${config.model_name}. Cần model đã được cài; kết quả sẽ ghi rõ nếu không gọi được.`;
    this.renderRows(defaults.niches);
  },

  renderRows(niches) {
    this.count = niches.length;
    document.getElementById('nicheInputs').innerHTML = niches.map((niche, index) => `<fieldset class="niche-input">
      <legend>Niche ${index + 1}</legend>
      <label>Tên niche<input id="input-niche-${index}-name" required maxlength="200" autocomplete="off"></label>
      <label>Seed keywords — mỗi dòng một cụm từ, tối đa ${this.limits.max_keywords}<textarea id="input-niche-${index}-keywords" required rows="4" maxlength="1800"></textarea></label>
      <label>Subreddits tùy chọn — tối đa ${this.limits.max_subreddits}, cách nhau bằng dấu phẩy<input id="input-niche-${index}-subreddits" maxlength="100" placeholder="Ví dụ tên cộng đồng, không nhập URL" autocomplete="off"></label>
      <p class="section-desc">Để trống subreddit = Reddit chưa được cấu hình cho niche này. Amazon tìm theo tối đa hai seed đầu tiên; không tự dùng sản phẩm từ hub tổng.</p>
      <button type="button" class="btn-secondary" data-remove-niche="${index}" ${niches.length <= this.limits.min_niches ? 'disabled' : ''}>Xóa niche</button>
    </fieldset>`).join('');
    niches.forEach((niche, index) => {
      document.getElementById(`input-niche-${index}-name`).value = niche.name;
      document.getElementById(`input-niche-${index}-keywords`).value = niche.seed_keywords.join('\n');
      document.getElementById(`input-niche-${index}-subreddits`).value = niche.subreddits.join(', ');
    });
    document.getElementById('btnAddNiche').disabled = niches.length >= this.limits.max_niches;
  },

  draft() {
    return Array.from({ length: this.count }, (_, index) => ({
      name: document.getElementById(`input-niche-${index}-name`).value.trim(),
      seed_keywords: document.getElementById(`input-niche-${index}-keywords`).value.split('\n').map(value => value.trim()).filter(Boolean),
      subreddits: document.getElementById(`input-niche-${index}-subreddits`).value.trim()
        ? document.getElementById(`input-niche-${index}-subreddits`).value.split(',').map(value => value.trim()) : [],
    }));
  },

  add() {
    if (this.count < this.limits.max_niches) this.renderRows([...this.draft(), { name: '', seed_keywords: [], subreddits: [] }]);
  },

  remove(index) {
    if (!Number.isInteger(index) || index < 0 || index >= this.count || this.count <= this.limits.min_niches) return;
    const niches = this.draft();
    niches.splice(index, 1);
    this.renderRows(niches);
  },

  read() {
    const niches = this.draft();
    const category = document.getElementById('inputCategory').value.trim();
    if (!category || category.length > 200 || niches.length < this.limits.min_niches || niches.length > this.limits.max_niches) throw new Error('Cần danh mục và 3–5 niche hợp lệ.');
    const names = new Set();
    for (const niche of niches) {
      const key = niche.name.toLocaleLowerCase('vi');
      if (!niche.name || niche.name.length > 200 || names.has(key)) throw new Error('Tên niche không được rỗng, trùng hoặc quá 200 ký tự.');
      names.add(key);
      if (!niche.seed_keywords.length || niche.seed_keywords.length > this.limits.max_keywords || niche.seed_keywords.some(value => value.length > 200)) throw new Error(`Mỗi niche cần 1–${this.limits.max_keywords} keyword, tối đa 200 ký tự mỗi keyword.`);
      if (niche.subreddits.length > this.limits.max_subreddits || niche.subreddits.some(value => !/^[A-Za-z0-9_]{2,21}$/.test(value))) throw new Error('Subreddit phải là tên cộng đồng hợp lệ, không phải URL.');
    }
    return { category, niches, geo: document.getElementById('inputGeo').value.trim(),
      timeframe: document.getElementById('inputTimeframe').value.trim(), mode: document.getElementById('inputMode').value };
  },

  setBusy(busy) {
    document.getElementById('researchFields').disabled = busy;
  },
};
