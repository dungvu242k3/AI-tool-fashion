"""Auditable collector-boundary snapshots, NOT HTTP/HTML bodies or rejected records.

Manifest-last commits a complete run. Partial directories remain diagnostic only.
Checksums detect corruption, not malicious local writers/provider impersonation.
"""
import hashlib
import os
import re
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path

from src.collectors.performance_settings import SOURCES, PerformanceSettings
from src.config import DATA_POLICY_VERSION
from src.reporters.result_codec import canonical_json, decode_document, read_document

SCHEMA = "validated-collector-input-v1"
MANIFEST_MAX_BYTES = 512 * 1024
RUN_ID = re.compile(r"[0-9a-f]{32}")


def _atomic_bytes(target: Path, body: bytes):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class CollectionSnapshotWriter:
    def __init__(self, output_dir, run_id: str, niche_names, settings: PerformanceSettings):
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid snapshot run ID")
        names = tuple(niche_names)
        if not 1 <= len(names) <= 100 or len(set(names)) != len(names):
            raise ValueError("Invalid snapshot niche set")
        root = Path(output_dir).resolve()
        self.directory = root / "snapshots" / run_id
        if not self.directory.resolve().is_relative_to(root):
            raise ValueError("Snapshot directory escapes output root")
        self.directory.parent.mkdir(parents=True, exist_ok=True)
        # A collision must not overwrite any source artifact from an earlier run.
        self.directory.mkdir(exist_ok=False)
        self.run_id, self.names, self.settings = run_id, names, settings
        self._entries, self._bytes, self._committed = {}, 0, False
        self._lock = threading.Lock()

    def capture(self, position: int, source: str, result):
        if type(position) is not int or not 0 <= position < len(self.names) or source not in SOURCES or result.source != source:
            raise ValueError("Invalid snapshot identity")
        filename = f"{position:04d}_{source}.json"
        document = {"schema": SCHEMA, "data_policy": DATA_POLICY_VERSION, "run_id": self.run_id,
                    "position": position, "niche": self.names[position], "source": source,
                    "collection": asdict(result)}
        body = canonical_json(document).encode("utf-8")
        if len(body) > self.settings.snapshot_max_bytes:
            raise ValueError("Collector snapshot exceeds byte budget; no evidence truncation")
        with self._lock:
            if self._committed or filename in self._entries:
                raise ValueError("Snapshot already captured/committed")
            if self._bytes + len(body) > self.settings.snapshot_run_max_bytes:
                raise ValueError("Run snapshots exceed byte budget")
            _atomic_bytes(self.directory / filename, body)
            self._entries[filename] = {"filename": filename, "position": position, "source": source,
                                       "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            self._bytes += len(body)

    def commit(self) -> str:
        with self._lock:
            expected = {f"{index:04d}_{source}.json" for index in range(len(self.names)) for source in SOURCES}
            if self._committed or set(self._entries) != expected:
                raise ValueError("Cannot commit incomplete/already committed snapshots")
            manifest = {"schema": SCHEMA, "data_policy": DATA_POLICY_VERSION, "run_id": self.run_id,
                        "boundary": "validated_collector_output_before_processing",
                        "niches": list(self.names), "total_bytes": self._bytes,
                        "entries": [self._entries[key] for key in sorted(self._entries)]}
            body = canonical_json(manifest).encode("utf-8")
            if len(body) > MANIFEST_MAX_BYTES:
                raise ValueError("Snapshot manifest exceeds byte budget")
            _atomic_bytes(self.directory / "manifest.json", body)
            self._committed = True
        return f"snapshots/{self.run_id}/manifest.json"


def read_collection_snapshots(output_dir, run_id: str, *, settings=None) -> list[dict]:
    """Read strict bounded JSON only. Never execute/replay snapshots as a fresh run."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid snapshot run ID")
    settings = settings if settings is not None else PerformanceSettings()
    root = Path(output_dir).resolve()
    directory = (root / "snapshots" / run_id).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("Snapshot directory escapes output root")
    manifest_path = directory / "manifest.json"
    if manifest_path.resolve().parent != directory:
        raise ValueError("Snapshot manifest escapes directory")
    manifest = read_document(manifest_path, max_bytes=MANIFEST_MAX_BYTES)
    names, entries = manifest.get("niches"), manifest.get("entries")
    if (manifest.get("schema") != SCHEMA or manifest.get("data_policy") != DATA_POLICY_VERSION
            or manifest.get("run_id") != run_id
            or manifest.get("boundary") != "validated_collector_output_before_processing"
            or not isinstance(names, list) or not 1 <= len(names) <= 100
            or not all(isinstance(name, str) and 0 < len(name) <= 200 for name in names)
            or len(set(names)) != len(names) or not isinstance(entries, list)
            or len(entries) != len(names) * len(SOURCES)):
        raise ValueError("Invalid snapshot manifest")
    expected = {f"{i:04d}_{source}.json" for i in range(len(names)) for source in SOURCES}
    documents, seen, total = [], set(), 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid snapshot entry")
        filename, size, position, source = (entry.get(key) for key in ("filename", "bytes", "position", "source"))
        if (not isinstance(filename, str) or filename not in expected or filename in seen
                or type(position) is not int or not 0 <= position < len(names) or source not in SOURCES
                or filename != f"{position:04d}_{source}.json"
                or type(size) is not int or not 0 < size <= settings.snapshot_max_bytes):
            raise ValueError("Invalid snapshot entry identity/size")
        total += size
        if total > settings.snapshot_run_max_bytes:
            raise ValueError("Snapshot run exceeds byte budget")
        path = directory / filename
        if path.resolve().parent != directory:
            raise ValueError("Snapshot file escapes directory")
        with path.open("rb") as stream:
            body = stream.read(size + 1)
        if len(body) != size or hashlib.sha256(body).hexdigest() != entry.get("sha256"):
            raise ValueError("Snapshot checksum/size mismatch")
        document = decode_document(body, max_bytes=settings.snapshot_max_bytes)
        if (document.get("schema") != SCHEMA or document.get("data_policy") != DATA_POLICY_VERSION
                or document.get("run_id") != run_id or document.get("position") != position
                or document.get("niche") != names[position] or document.get("source") != source
                or not isinstance(document.get("collection"), dict)
                or document["collection"].get("source") != source):
            raise ValueError("Snapshot identity mismatch")
        seen.add(filename)
        documents.append(document)
    if seen != expected or type(manifest.get("total_bytes")) is not int or total != manifest["total_bytes"]:
        raise ValueError("Incomplete snapshot manifest")
    return documents
