/** Controller: one real job, no synthetic progress or automatic POST retry. */
let globalReportData = null;
let activeJobId = null;
let isWatching = false;
let configReady = false;
let pollInterval = 1000;
const pausePolling = delay => new Promise(resolve => setTimeout(resolve, delay));

function selectTab(id) { UI.selectTab(id); }

async function followJob(initial) {
  activeJobId = initial.job_id;
  let job = initial;
  let errors = 0;
  let sequence = null;
  let previousStatus = null;
  while (true) {
    if (job.progress?.sequence !== sequence || job.status !== previousStatus) {
      UI.renderJob(job);
      sequence = job.progress?.sequence;
      previousStatus = job.status;
    }
    if (job.status === 'failed') {
      activeJobId = null;
      throw new Error(`${job.error} Job ID: ${job.job_id}`);
    }
    if (job.status === 'completed') {
      const result = await Api.getJobResult(job.job_id);
      if (!result?.report_filename) throw new Error('Job chưa có publication hợp lệ; không tạo báo cáo thay thế.');
      globalReportData = result;
      activeJobId = null;
      UI.renderAll(result);
      UI.finishProgress(result.message, result.status);
      return;
    }
    await pausePolling(pollInterval * (2 ** errors));
    try {
      job = await Api.getJob(activeJobId);
      errors = 0;
    } catch (error) {
      if (error.status === 404) { activeJobId = null; throw error; }
      errors++;
      document.getElementById('statusText').innerText = 'Mất kết nối theo dõi; chưa biết trạng thái job. Không tự chạy lại nghiên cứu.';
      if (errors >= 3) throw error;
    }
  }
}

async function runAnalysis() {
  if (isWatching || !configReady) return;
  const errorBox = document.getElementById('formError');
  errorBox.innerText = '';
  let input;
  if (!activeJobId) {
    try { input = ResearchForm.read(); } catch (error) { errorBox.innerText = error.message; return; }
  }
  isWatching = true;
  ResearchForm.setBusy(true);
  try {
    if (activeJobId) {
      await followJob(await Api.getJob(activeJobId));
    } else {
      globalReportData = null;
      UI.renderAll({ status: 'running', message: 'Đang gửi yêu cầu nghiên cứu; chưa có kết quả mới.' });
      const key = crypto.randomUUID();
      let job;
      try {
        job = await Api.startJob(input, key);
      } catch (error) {
        if (error.status && error.status !== 429) throw error;
        // A lost POST acknowledgement must not trigger a second collection.
        const active = await Api.getActiveJob().catch(() => null);
        if (!active?.job) throw error;
        job = active.job;
        errorBox.innerText = 'Đang theo dõi job server hiện có; không gửi thêm yêu cầu. Input trong job có thể thuộc lần gửi trước/cửa sổ khác.';
      }
      await followJob(job);
    }
  } catch (error) {
    errorBox.innerText = error.message || 'Không theo dõi được job. Xem log server theo job ID.';
    UI.renderStatus({ status: activeJobId || error.status === 0 ? 'connection_lost' : 'failed', message: errorBox.innerText });
    UI.finishProgress(activeJobId ? 'Đã dừng theo dõi; job có thể vẫn chạy. Bấm Theo dõi lại job để tiếp tục.' : errorBox.innerText, 'failed');
  } finally {
    isWatching = false;
    ResearchForm.setBusy(false);
    document.getElementById('btnRun').innerText = activeJobId ? 'Theo dõi lại job' : 'Chạy nghiên cứu';
  }
}

async function copyReport() {
  if (!globalReportData?.markdown_content) return;
  try { await navigator.clipboard.writeText(globalReportData.markdown_content); }
  catch { document.getElementById('formError').innerText = 'Không truy cập được clipboard. Bạn có thể sao chép từ tab báo cáo.'; }
}

function downloadReport() {
  if (!globalReportData?.markdown_content) return;
  const url = URL.createObjectURL(new Blob([globalReportData.markdown_content], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = globalReportData.report_filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

window.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('researchForm').addEventListener('submit', event => { event.preventDefault(); runAnalysis(); });
  document.getElementById('btnAddNiche').addEventListener('click', () => ResearchForm.add());
  document.getElementById('nicheInputs').addEventListener('click', event => {
    const button = event.target.closest('[data-remove-niche]');
    if (button) ResearchForm.remove(Number(button.dataset.removeNiche));
  });
  document.getElementById('tabBar').addEventListener('click', event => {
    const button = event.target.closest('[data-tab]');
    if (button) selectTab(button.dataset.tab);
  });
  document.getElementById('tabBar').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const buttons = Array.from(document.querySelectorAll('[data-tab]'));
    const current = buttons.indexOf(event.target.closest('[data-tab]'));
    if (current < 0 || !buttons.length) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (current + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
    selectTab(buttons[next].dataset.tab);
    buttons[next].focus();
  });
  document.getElementById('btnCopy').addEventListener('click', copyReport);
  document.getElementById('btnDownload').addEventListener('click', downloadReport);
  ResearchForm.setBusy(true);
  try {
    const config = await Api.getConfig();
    ResearchForm.initialize(config);
    pollInterval = Number.isFinite(config.poll_interval_ms) ? Math.max(500, Math.min(5000, config.poll_interval_ms)) : 1000;
    configReady = true;
    const active = await Api.getActiveJob();
    if (active.job) {
      activeJobId = active.job.job_id;
      await runAnalysis();
    } else {
      const result = await Api.getLatestReport();
      UI.renderAll(result);
      globalReportData = result?.report_filename ? result : null;
    }
  } catch (error) {
    document.getElementById('formError').innerText = error.message || 'Không tải được cấu hình/báo cáo. Tải lại trang để thử lại.';
  } finally { ResearchForm.setBusy(!configReady); }
});
