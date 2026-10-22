/** Same-origin transport. POST is never automatically retried. */
class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

const Api = {
  csrfToken: null,
  async json(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, cache: 'no-store', credentials: 'same-origin', redirect: 'error' });
      const data = await response.json();
      if (!response.ok) throw new ApiError(data.error || data.message || `HTTP ${response.status}`, response.status);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new ApiError('Kết nối quá hạn; job có thể vẫn đang chạy trên server.', 0);
      throw error;
    } finally { clearTimeout(timeout); }
  },
  async getConfig() {
    const config = await this.json('/api/config');
    this.csrfToken = config.csrf_token;
    return config;
  },
  getLatestReport() { return this.json('/api/latest'); },
  getActiveJob() { return this.json('/api/jobs/active'); },
  getJob(id) { return this.json(`/api/jobs/${encodeURIComponent(id)}`); },
  getJobResult(id) { return this.json(`/api/jobs/${encodeURIComponent(id)}/result`); },
  getReportsList() { return this.json('/api/reports'); },
  startJob(input, key) {
    if (!this.csrfToken) throw new Error('Chưa tải cấu hình/token; hãy tải lại trang.');
    return this.json('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json',
      'X-CSRF-Token': this.csrfToken, 'Idempotency-Key': key }, body: JSON.stringify(input) });
  },
};
