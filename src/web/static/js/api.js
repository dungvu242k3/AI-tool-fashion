/**
 * API Service for Product Trend Research Tool.
 * Handles HTTP communication with the Python server endpoints cleanly.
 */
const Api = {
  /**
   * Fetches the latest generated report or cached state.
   */
  async getLatestReport() {
    const response = await fetch('/api/latest');
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }
    return await response.json();
  },

  /**
   * Executes the end-to-end research pipeline.
   * @param {boolean} fastMode - Whether to run in optimized fast mode.
   */
  async runPipeline(fastMode = true) {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ fast_mode: fastMode }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `HTTP error ${response.status}`);
    }
    return data;
  },

  /**
   * Fetches list of all generated reports.
   */
  async getReportsList() {
    const response = await fetch('/api/reports');
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }
    return await response.json();
  },
};
