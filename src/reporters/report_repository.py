"""Atomically persist results/diagnostics and reject caches from older policies."""
import json
import os
import tempfile
import re
from pathlib import Path

from src.config import DATA_POLICY_VERSION, REPORTS_DIR
from src.models.research_result import MAX_DOCUMENT_BYTES, ResearchResult
from src.reporters.report_generator import ReportGenerator
from src.reporters.result_codec import publication, read_document, report_filename, validate_publication


class ReportRepository:
    def __init__(self, output_dir=REPORTS_DIR):
        self.directory = Path(output_dir)

    def save_latest(self, result: dict):
        """Low-level compatibility writer; readers still validate the entire envelope."""
        self._save_json("latest_data.json", result)

    def publish(self, result: ResearchResult) -> dict:
        """Render and serialize the SAME snapshot, then commit latest only after Markdown.

        Each file is atomic; a failed latest replacement can leave an orphan report,
        but never replaces the last good cache with half a document.
        """
        markdown = ReportGenerator().render(result)
        filename = report_filename(result)
        data = publication(result, self.directory / filename, markdown)
        # Check full serialized envelope before writing either artifact; no truncation.
        serialized = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        if len(serialized.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError("Published result exceeds cache byte budget")
        self._save_text(filename, markdown)
        self._save_text("latest_data.json", serialized)
        return data

    def save_diagnostics(self, run_id: str, result: dict) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid run ID")
        relative = f"diagnostics/{run_id}.json"
        self._save_json(relative, result)
        return relative

    def _save_json(self, relative_path: str, result: dict):
        self._save_text(relative_path, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))

    def _save_text(self, relative_path: str, content: str):
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=target.parent, suffix=".tmp", delete=False
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load_latest(self) -> dict:
        path = self.directory / "latest_data.json"
        if not path.exists():
            return {"success": False, "status": "no_report", "message": "Chưa có báo cáo mới."}
        try:
            result = read_document(path)
        except (OSError, ValueError, UnicodeError, RecursionError, OverflowError):
            return {"success": False, "status": "invalid_cache", "message": "Không đọc được cache báo cáo."}
        metadata = result.get("metadata") if isinstance(result, dict) else None
        if not isinstance(metadata, dict) or metadata.get("data_policy") != DATA_POLICY_VERSION:
            return {
                "success": False, "status": "legacy",
                "message": "Cache thuộc chính sách cũ, chưa tương thích schema/quality/ranking hiện tại. Hãy chạy thu thập mới.",
            }
        try:
            validate_publication(result, self.directory)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
            return {"success": False, "status": "invalid_cache", "message": "Cache không khớp contract báo cáo; cần chạy thu thập mới."}
        return result

    def list_reports(self) -> dict:
        current, legacy = [], []
        marker = f"<!-- data-policy: {DATA_POLICY_VERSION} -->"
        for path in sorted(self.directory.glob("report_trend_*.md"), key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True):
            with path.open(encoding="utf-8") as stream:
                verified_format = marker in stream.read(1024)
            (current if verified_format else legacy).append(path.name)
        return {"success": True, "reports": current, "legacy_reports": legacy}
