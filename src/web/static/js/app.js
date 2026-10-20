/**
 * Main Controller Module.
 * Initializes event listeners, orchestrates API requests and UI state.
 */
let globalReportData = null;

/**
 * Switches the active tab view.
 */
function selectTab(id) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

  const targetBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(id));
  if (targetBtn) targetBtn.classList.add('active');

  const targetPane = document.getElementById(`tab-${id}`);
  if (targetPane) targetPane.classList.add('active');
}

/**
 * Triggers the 1-Click End-to-End analysis.
 */
async function runAnalysis() {
  const btn = document.getElementById('btnRun');
  if (!btn) return;

  btn.disabled = true;
  btn.innerText = "Đang xử lý...";
  UI.setStepProgress(1, "BƯỚC 1/5: Đang thu thập tín hiệu Google Trends, Amazon và Reddit...");

  try {
    const data = await Api.runPipeline(true);
    if (data && data.success) {
      globalReportData = data;
      UI.finishProgress(`Hoàn thành! Đã xuất báo cáo: ${data.report_filename}`);
      UI.renderAll(data);
    } else {
      UI.finishProgress("Phân tích hoàn tất.");
    }
  } catch (error) {
    console.error("Analysis execution error:", error);
    UI.finishProgress(error.message || "Đã xảy ra lỗi trong quá trình phân tích.");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
      </svg>
      <span>Chạy phân tích xu hướng</span>
    `;
  }
}

/**
 * Copies markdown report to clipboard.
 */
function copyReport() {
  const text = globalReportData ? globalReportData.markdown_content : document.getElementById('rawReportText')?.innerText;
  if (text) {
    navigator.clipboard.writeText(text);
    alert("Đã sao chép nội dung báo cáo.");
  }
}

/**
 * Downloads report as .md file.
 */
function downloadReport() {
  const text = globalReportData ? globalReportData.markdown_content : document.getElementById('rawReportText')?.innerText;
  const filename = globalReportData ? globalReportData.report_filename : "trend_report.md";
  if (text) {
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
  }
}

/**
 * Lifecycle hook: automatically fetch latest data on page load.
 */
window.addEventListener('DOMContentLoaded', async () => {
  try {
    const data = await Api.getLatestReport();
    if (data && data.success) {
      globalReportData = data;
      UI.renderAll(data);
    }
  } catch (err) {
    console.log("Waiting for user to trigger analysis.");
  }
});
