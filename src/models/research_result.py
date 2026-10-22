"""An owned, immutable publication snapshot; views never score or fill missing data.

Collection/quality/grounding validators remain responsible for source truth.
This boundary checks output consistency, not authenticity or market validity.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
import math
import re
from types import MappingProxyType
from typing import Any, ClassVar

from src.collectors.evidence_validation import IDENTIFIER, aware_timestamp, is_http_url, valid_text
from src.config import DATA_POLICY_VERSION
from src.models.research_integrity import encoded, validate_record_views
from src.models.research_views import validate_health_view, validate_quality_view, validate_summary_view

SCHEMA_VERSION = "research-result-v1"
SOURCE_RECORDS = {"google_trends": "keywords", "amazon": "products", "reddit": "discussions"}
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_DOCUMENT_NODES = 2_000_000
MAX_DOCUMENT_DEPTH = 48


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def freeze_json(value, *, depth=0, budget=None):
    """Bound work before traversing; reject cycles, non-JSON types and non-finite values."""
    if budget is None:
        budget = [MAX_DOCUMENT_NODES, MAX_DOCUMENT_BYTES]
    budget[0] -= 1
    require(budget[0] >= 0 and depth <= MAX_DOCUMENT_DEPTH, "Research result exceeds tree budget")
    if value is None or type(value) is bool:
        return value
    if isinstance(value, str):
        require(valid_text(value, MAX_DOCUMENT_BYTES, empty=True, multiline=True), "Invalid result text")
        budget[1] -= len(value.encode("utf-8"))
        require(budget[1] >= 0, "Research result exceeds text budget")
        return value
    if type(value) in (int, float):
        require(abs(value) <= 2**53 - 1 and math.isfinite(value), "Invalid result number")
        return value
    if isinstance(value, Mapping):
        require(all(isinstance(key, str) for key in value), "JSON keys must be strings")
        return MappingProxyType({freeze_json(key, depth=depth + 1, budget=budget):
                                 freeze_json(item, depth=depth + 1, budget=budget)
                                 for key, item in value.items()})
    require(isinstance(value, (list, tuple)), "Non-JSON result value")
    return tuple(freeze_json(item, depth=depth + 1, budget=budget) for item in value)


def thaw_json(value):
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def same_view(left, right):
    return encoded(thaw_json(left)) == encoded(thaw_json(right))


def evidence_entries(niches: Mapping) -> list[dict]:
    """Index every retained record/listing without losing cross-niche associations."""
    entries = []
    for name, data in niches.items():
        seen = {}
        for field in SOURCE_RECORDS.values():
            for record in data[field]:
                provenances = [record["provenance"], *(item["provenance"] for item in record.get("listings", ()))]
                for provenance in provenances:
                    identity = provenance["evidence_id"]
                    require(identity not in seen or seen[identity] == provenance, "Conflicting evidence identity")
                    if identity not in seen:
                        entries.append({"niche": name, **provenance})
                        seen[identity] = provenance
    return entries


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Created once after analysis; all mutable inputs are detached and frozen."""

    metadata: Mapping[str, Any]
    niches: Mapping[str, Any]
    source_statuses: Mapping[str, Any]
    request_metadata: Mapping[str, Any]
    ranking_assessment: Mapping[str, Any]
    analysis_summary: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...] = field(init=False)
    schema_version: ClassVar[str] = SCHEMA_VERSION

    def __post_init__(self):
        budget = [MAX_DOCUMENT_NODES, MAX_DOCUMENT_BYTES]
        for spec in fields(self):
            if spec.init:
                object.__setattr__(self, spec.name, freeze_json(getattr(self, spec.name), budget=budget))
        try:
            object.__setattr__(self, "evidence", tuple(MappingProxyType(entry) for entry in evidence_entries(self.niches)))
            self._validate()
        except (KeyError, TypeError, AttributeError, IndexError) as exc:
            raise ValueError("Incomplete research result") from exc

    def _validate(self):
        meta = self.metadata
        require(meta["data_policy"] == DATA_POLICY_VERSION, "Incompatible data policy")
        require(isinstance(meta["run_id"], str) and re.fullmatch(r"[a-f0-9]{32}", meta["run_id"]) is not None, "Invalid run ID")
        require(meta["diagnostics_file"] == f"diagnostics/{meta['run_id']}.json", "Invalid diagnostics path")
        require(aware_timestamp(meta["timestamp"]) is not None and valid_text(meta["category"], 500), "Invalid run context")
        require(meta["status"] in {"success", "partial", "failed"}, "Invalid run status")
        require(meta["data_quality"] in {"sufficient", "partial", "insufficient"}, "Invalid run quality")
        require(meta["requested_mode"] in {"ollama", "deterministic"}, "Invalid requested mode")
        require(meta["execution_kind"] in {"live_collection", "offline_publication_audit"}, "Invalid execution kind")
        require(valid_text(meta["cost"], 500) and type(meta["elapsed_seconds"]) in (float, int)
                and meta["elapsed_seconds"] >= 0, "Invalid execution metadata")
        require(isinstance(meta["warnings"], tuple) and all(isinstance(w, str) for w in meta["warnings"]), "Invalid warnings")
        names = set(self.niches)
        require(0 < len(names) <= 100 and all(valid_text(name, 200) for name in names)
                and len({name.strip().casefold() for name in names}) == len(names), "Invalid niche names")
        require(set(self.source_statuses) == names == set(meta["quality_assessments"]) == set(meta["ai_validation"]), "Niche views disagree")
        require(set(meta["source_health"]) == set(SOURCE_RECORDS), "Missing source health")
        if "research_input" in meta:
            from src.models.research_request import ResearchRequest
            intent = ResearchRequest.from_dict(thaw_json(meta["research_input"]))
            require(same_view(intent.to_dict(), meta["research_input"]) and intent.category == meta["category"]
                    and intent.mode == meta["requested_mode"] and tuple(niche.name for niche in intent.niches) == tuple(self.niches),
                    "Research intent and published context disagree")
            for selected in intent.niches:
                niche = self.niches[selected.name]
                require(all(keyword["geo"] == intent.geo and keyword["timeframe"] == intent.timeframe for keyword in niche["keywords"]),
                        "Trend context and requested geo/timeframe disagree")
                seeds = {seed.casefold() for seed in selected.seed_keywords}
                require(all(keyword["keyword"].strip().casefold() in seeds for keyword in niche["keywords"]),
                        "Trend keywords and requested seeds disagree")
        modes = []
        for name, niche in self.niches.items():
            validate_record_views(thaw_json(niche))
            validate_quality_view(niche, self.source_statuses[name])
            require(niche["name"] == niche["niche_name"] == name, "Niche identity mismatch")
            require(same_view(niche["source_statuses"], self.source_statuses[name]), "Source status views disagree")
            require(same_view(niche["quality_assessment"], meta["quality_assessments"][name])
                    and niche["data_quality"] == niche["quality_assessment"]["status"], "Quality views disagree")
            require(same_view(niche["ai_validation"], meta["ai_validation"][name]), "Analysis validation views disagree")
            require(all(isinstance(niche[key], str) for key in ("keywords_content", "analysis_text", "ideas_content")), "Missing rendered sections")
            require(niche["analysis_status"] in {"success", "failed", "invalid_output", "insufficient_data", "not_requested", "context_rejected"}, "Invalid analysis status")
            modes.append(niche["generation_mode"])
            require(modes[-1] in {"deterministic", "ollama"}, "Invalid generation mode")
            quality = niche["quality_assessment"]
            gate = quality["gate_passed"] is True and quality["status"] in {"partial", "sufficient"}
            if niche["generation_mode"] == "ollama":
                grounded = niche["grounded_analysis"]
                require(gate and niche["analysis_status"] == "success" and isinstance(grounded, Mapping)
                        and grounded["evidence_digest"] == quality["data_digest"]
                        and niche["ai_validation"]["outcome"] == "source_references_verified", "Ungrounded AI publication")
                require(same_view(niche["ideas"], grounded["ideas"]), "Idea views disagree")
            else:
                require(not niche["ideas"] and niche["grounded_analysis"] is None, "Deterministic result cannot invent ideas")
            require(set(self.source_statuses[name]) == set(SOURCE_RECORDS), "Missing source statuses")
            for source, field in SOURCE_RECORDS.items():
                records = niche[field]
                state = self.source_statuses[name][source]
                require(isinstance(records, tuple) and isinstance(state, Mapping), "Invalid records/status")
                require(state["source"] == source and state["status"] in {"success", "partial", "failed", "not_configured"}
                        and type(state["record_count"]) is int and state["record_count"] == len(records), "Source record counts disagree")
                require(not records or state["status"] in {"success", "partial"}, "Failed source contains records")
                require(state["cached_record_count"] == sum(record["provenance"]["from_cache"] for record in records),
                        "Source cache counts disagree with provenance")
                for identity in state["request_ids"]:
                    trace = self.request_metadata.get(identity)
                    require(trace is not None and trace["source"] == source, "Source request references disagree")
                for record in records:
                    require(record["provenance"]["source"] == source, "Record source mismatch")
        actual_mode = "deterministic" if "ollama" not in modes else ("ollama" if all(m == "ollama" for m in modes) else "mixed")
        require(meta["mode"] == actual_mode, "Actual execution mode disagrees")
        require((meta["model_name"] is not None) == (actual_mode != "deterministic"), "Model use disagrees")
        for key in ("model_name", "model_attempted"):
            require(meta[key] is None or valid_text(meta[key], 200), "Invalid model metadata")
        require(actual_mode == "deterministic" or (meta["requested_mode"] == "ollama" and meta["model_name"] == meta["model_attempted"]), "Model attempt disagrees")
        require(meta["requested_mode"] != "deterministic" or meta["model_attempted"] is None, "Unexpected model attempt")
        counts = {field: sum(len(niche[field]) for niche in self.niches.values()) for field in SOURCE_RECORDS.values()}
        for key, count in {"total_niches": len(names), **{f"total_{field}": count for field, count in counts.items()}}.items():
            require(type(meta[key]) is int and meta[key] == count, "Metadata count disagrees")
        qualities = [n["data_quality"] for n in self.niches.values()]
        quality = "sufficient" if all(q == "sufficient" for q in qualities) else ("partial" if any(q != "insufficient" for q in qualities) else "insufficient")
        require(meta["data_quality"] == quality, "Aggregate quality disagrees")
        complete = quality == "sufficient" and (meta["requested_mode"] == "deterministic" or all(n["analysis_status"] == "success" for n in self.niches.values()))
        require(meta["status"] == ("success" if complete else ("partial" if sum(counts.values()) else "failed")), "Aggregate status disagrees")
        self._validate_references()
        validate_health_view(meta["source_health"], self.source_statuses)
        validate_summary_view(self.analysis_summary, self.niches, self.ranking_assessment)

    def _validate_references(self):
        for identity, trace in self.request_metadata.items():
            require(IDENTIFIER.fullmatch(identity) is not None and identity == trace["request_id"]
                    and trace["source"] in SOURCE_RECORDS and is_http_url(trace["url"])
                    and aware_timestamp(trace["completed_at"]) is not None, "Invalid request reference")
        for item in self.evidence:
            require(IDENTIFIER.fullmatch(item["evidence_id"]) is not None and is_http_url(item["source_url"])
                    and aware_timestamp(item["retrieved_at"]) is not None and item["is_live"] is True
                    and type(item["from_cache"]) is bool, "Invalid evidence reference")
            require(item["request_ids"] and item["request_id"] in item["request_ids"], "Missing evidence dependency")
            for identity in item["request_ids"]:
                trace = self.request_metadata.get(identity)
                require(trace is not None and trace["source"] == item["source"], "Missing evidence request")
            require(self.request_metadata[item["request_id"]]["completed_at"] == item["retrieved_at"], "Evidence timestamp disagrees")
        rows = [*self.ranking_assessment["ranking"], *self.ranking_assessment["unranked"]]
        evidence_by_id = {(item["niche"], item["evidence_id"]): item for item in self.evidence}
        require(len(rows) == len(self.niches) and {r["niche"] for r in rows} == set(self.niches), "Ranking niche views disagree")
        for row in rows:
            quality = self.niches[row["niche"]]["quality_assessment"]
            require(row["evidence_digest"] == (quality["data_digest"] if quality["gate_passed"] else None), "Stale ranking")
            for component in row["components"]:
                for item in component["inputs"]:
                    origin = evidence_by_id.get((row["niche"], item["evidence_id"]))
                    keys = ("source", "source_url", "retrieved_at", "request_id", "from_cache")
                    require(origin is not None and same_view({key: item[key] for key in keys},
                                                            {key: origin[key] for key in keys}), "Ranking evidence references disagree")
        for field, key in (("ranking_status", "status"), ("ranking_method", "method"), ("ranking_policy_id", "policy_id")):
            require(self.metadata[field] == self.ranking_assessment[key], "Ranking metadata disagrees")
        require(self.metadata["top_ideas_status"] == self.analysis_summary["status"], "Summary status disagrees")

    def to_dict(self) -> dict:
        """Only this serializer supplies compatibility aliases; they share list identity."""
        data = {name: thaw_json(getattr(self, name)) for name in (
            "metadata", "niches", "source_statuses", "request_metadata", "ranking_assessment", "analysis_summary")}
        success = self.metadata["status"] == "success"
        return {"schema_version": self.schema_version, "success": success, "status": self.metadata["status"],
                "message": "Đã thu thập và xuất báo cáo." if success else "Đã xuất báo cáo dữ liệu chưa đầy đủ; xem tình trạng nguồn.",
                **data, "source_health": data["metadata"]["source_health"],
                "evidence": thaw_json(self.evidence), "ranking": data["ranking_assessment"]["ranking"],
                "top_ideas": data["analysis_summary"]["top_ideas"]}

    @classmethod
    def from_dict(cls, data: dict):
        require(data.get("schema_version") == SCHEMA_VERSION, "Incompatible research schema")
        return cls(**{name: data[name] for name in (
            "metadata", "niches", "source_statuses", "request_metadata", "ranking_assessment", "analysis_summary")})
