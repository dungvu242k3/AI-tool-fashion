"""Consistency checks for publication metadata; never adjust source measurements."""
from collections import Counter
from collections.abc import Mapping


def _check(condition, message):
    if not condition:
        raise ValueError(message)


def _count(value):
    return type(value) is int and value >= 0


def validate_quality_view(niche: Mapping, states: Mapping) -> None:
    quality = niche["quality_assessment"]
    _check(quality["status"] in {"sufficient", "partial", "insufficient"}
           and type(quality["gate_passed"]) is bool
           and quality["gate_passed"] == (quality["status"] != "insufficient"), "Invalid gate state")
    for key in ("qualifying_keyword_count", "supporting_record_count", "configured_source_count", "observed_source_count",
                "candidate_count", "valid_count", "rejected_count", "duplicate_count", "retained_count"):
        _check(_count(quality[key]), "Invalid quality count")
    ratio = quality["valid_ratio"]
    _check(ratio is None or (type(ratio) in (int, float) and 0 <= ratio <= 1), "Invalid quality ratio")
    _check(set(quality["sources"]) == set(states), "Quality source set mismatch")
    for source, state in states.items():
        _check(quality["sources"][source]["status"] == state["status"], "Quality source status disagrees")
        for key in ("request_count", "cached_request_count", "cached_record_count"):
            _check(_count(state[key]), "Invalid source count")
        _check(state["request_count"] + state["cached_request_count"] == len(state["request_ids"])
               and state["cached_record_count"] <= state["record_count"], "Source provenance counts disagree")


def validate_health_view(health: Mapping, statuses: Mapping) -> None:
    for source, row in health.items():
        states = [sources[source] for sources in statuses.values()]
        counts = Counter(state["status"] for state in states)
        _check(row["source"] == source and _count(row["niche_count"]) and row["niche_count"] == len(states), "Health source context disagrees")
        _check(all(_count(count) for count in row["status_counts"].values()), "Invalid health status counts")
        _check(dict(row["status_counts"]) == {key: counts[key] for key in ("success", "partial", "failed", "not_configured")},
               "Health status counts disagree")
        for key in ("record_count", "request_count", "cached_request_count", "cached_record_count"):
            _check(_count(row[key]) and row[key] == sum(state[key] for state in states), "Health totals disagree")
        _check(_count(row["retry_count"]), "Invalid retry count")
        status = ("not_configured" if counts["not_configured"] == len(states) else
                  "success" if counts["success"] == len(states) else "partial" if row["record_count"] else "failed")
        _check(row["status"] == status, "Health status disagrees")


def validate_summary_view(summary: Mapping, niches: Mapping, ranking: Mapping) -> None:
    _check(summary["ranking_policy_id"] == ranking["policy_id"] and len(summary["top_ideas"]) <= 3, "Invalid summary context")
    ranked = {row["niche"]: row for row in ranking["ranking"]}
    seen = set()
    for position, idea in enumerate(summary["top_ideas"], 1):
        niche = niches.get(idea["niche"])
        candidate = next((row for row in niche["ideas"] if row["idea_id"] == idea["idea_id"]), None) if niche else None
        _check(candidate is not None and idea["niche"] in ranked, "Summary idea not grounded/ranked")
        _check(all(idea[key] == value for key, value in candidate.items()), "Summary idea content disagrees")
        _check(idea["title"] == candidate["name"] and idea["what_to_sell"] == candidate["rationale"]
               and type(idea["niche_rank"]) is int and idea["niche_rank"] == ranked[idea["niche"]]["rank"]
               and type(idea["selection_position"]) is int and idea["selection_position"] == position, "Summary selection metadata disagrees")
        identity = idea["niche"], idea["idea_id"]
        _check(identity not in seen, "Duplicate summary idea")
        seen.add(identity)
        records = {record["provenance"]["evidence_id"]: record["provenance"] for field in ("keywords", "products", "discussions")
                   for record in niche[field]}
        links = tuple({"evidence_id": key, "url": records[key]["source_url"], "retrieved_at": records[key]["retrieved_at"]}
                      for key in candidate["evidence_ids"])
        _check(idea["source_links"] == links, "Summary evidence links disagree")
