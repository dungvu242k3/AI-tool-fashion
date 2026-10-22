"""Reject unsupported claims instead of trying to make model prose sound true."""
import hashlib
import json
import re
import unicodedata

from src.analyzers.evidence_catalog import EvidenceCatalog, METRICS
from src.analyzers.grounded_schema import VALIDATOR
from src.analyzers.strict_json import AnalysisValidationError, strict_loads
from src.collectors.evidence_validation import valid_text
from src.models.analysis import GroundedAnalysis, GroundedFact, GroundedIdea, GroundedQuote


# Free text is only a design/audience proposal, never a channel for metrics,
# prices, URLs, causal/predictive claims or new citations. Factual language is
# rendered from typed facts. This is conservative, not a semantic truth oracle.
_CLAIM_LANGUAGE = re.compile(
    r"(?:https?\s*:|www\.|://|@|[%$€£¥₫]|\b(?:USD|VND|EUR)\b|"
    r"\b(?:profit\w*|margin\w*|revenue\w*|bestsell\w*|best.seller\w*|guarantee\w*|"
    r"growth|percent\w*|sales|sold|upvotes?|million\w*|billion\w*|hundred\w*|thousand\w*|"
    r"double\w*|triple\w*|twofold|threefold|majority|most.popular|number.one|rank\w*)\b|"
    r"lợi\s*nhuận|biên\s*lãi|doanh\s*(?:thu|số)|giá\s*vốn|bán\s*chạy|tăng\s*trưởng|"
    r"phần\s*trăm|gấp\s*(?:đôi|ba|bốn|nhiều)|đa\s*số|hầu\s*hết|cam\s*kết|đảm\s*bảo|"
    r"triệu|nghìn|ngàn|tỷ|tỉ\b|xếp\s*hạng|thứ\s*hạng|xu\s*hướng\s*(?:tăng|giảm)|"
    r"ignore\s+(?:all|previous)|system\s*prompt|api\s*key|mật\s*khẩu)", re.IGNORECASE,
)
_NUMBER_WORDS = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười|trăm|chục)\b", re.IGNORECASE,
)


def _proposal_text(value, path):
    normal = unicodedata.normalize("NFKC", value)
    if (not valid_text(value, 400) or normal != value or any(unicodedata.category(char).startswith("N") for char in value)
            or any(unicodedata.category(char) in {"Cf", "Cs", "Co"} for char in value)
            or any(char.isalpha() and "LATIN" not in unicodedata.name(char, "") for char in value)
            or _CLAIM_LANGUAGE.search(value) or _NUMBER_WORDS.search(value)
            or any(char in value for char in "<>[]{}\\`")):
        raise AnalysisValidationError("proposal_contains_unverified_claim_or_markup", path)
    return value.strip()


def _same_value(actual, expected):
    if isinstance(actual, bool) or isinstance(expected, bool):
        return False
    if isinstance(expected, str):
        return isinstance(actual, str) and actual == expected
    return isinstance(actual, (int, float)) and actual == expected


def _source_refs(ids, catalog, path):
    for key in ids:
        if key not in catalog.records:
            raise AnalysisValidationError("unknown_evidence_id", path)
    return tuple(sorted(ids))


def validate_analysis(text: str, catalog: EvidenceCatalog, *, max_bytes=65536) -> GroundedAnalysis:
    payload = strict_loads(text, max_bytes=max_bytes)
    error = next(VALIDATOR.iter_errors(payload), None)
    if error is not None:
        safe_keys = {"facts", "quotes", "ideas", "limitations", "schema_version", "fact_id", "quote_id", "kind", "metric",
                     "value", "evidence_ids", "name", "what_to_sell", "target_audience", "basis_fact_ids", "basis_quote_ids", "quote"}
        path = "$" + "".join(f"[{item}]" if isinstance(item, int) else "." + (item if item in safe_keys else "?") for item in error.absolute_path)
        raise AnalysisValidationError("schema_" + str(error.validator), path[:180])
    facts, quotes, ideas = {}, {}, []
    seen_facts, seen_quotes, seen_ideas = set(), set(), set()
    for index, item in enumerate(payload["facts"]):
        path = f"$.facts[{index}]"
        ids = _source_refs(item["evidence_ids"], catalog, path)
        metric, value = item["metric"], item["value"]
        source, label, unit = METRICS[metric]
        for key in ids:
            record = catalog.records[key]
            values = dict(record.metrics)
            if record.source != source or metric not in values or not _same_value(value, values[metric]):
                raise AnalysisValidationError("metric_value_or_source_mismatch", path)
        if item["fact_id"] in facts or (metric, ids) in seen_facts:
            raise AnalysisValidationError("duplicate_fact", path)
        seen_facts.add((metric, ids))
        identities = []
        for key in ids:
            record = catalog.records[key]
            context = dict(record.context)
            scope = (f"; geo={context['geo'] or 'toàn cầu'}; kỳ gần đây {context['recent_start']} → {context['recent_end']}"
                     if source == "google_trends" else "")
            identities.append(f"{record.identity} (snapshot {record.retrieved_at}{scope})")
        # Use the source's original numeric type/value, not a model coercion.
        observed = dict(catalog.records[ids[0]].metrics)[metric]
        fact_text = f"{', '.join(identities)}: {label} = {observed}{unit}."
        facts[item["fact_id"]] = GroundedFact(item["fact_id"], metric, observed, ids, fact_text)
    for index, item in enumerate(payload["quotes"]):
        path = f"$.quotes[{index}]"
        ids = _source_refs(item["evidence_ids"], catalog, path)
        quote = item["quote"]
        if not valid_text(quote, 500, multiline=True):
            raise AnalysisValidationError("invalid_quote_text", path)
        if any(catalog.records[key].source != "reddit" or not any(quote in part for part in catalog.records[key].quote_context) for key in ids):
            raise AnalysisValidationError("quote_not_in_cited_prompt_context", path)
        if item["quote_id"] in quotes or (quote, ids) in seen_quotes:
            raise AnalysisValidationError("duplicate_quote", path)
        seen_quotes.add((quote, ids))
        quotes[item["quote_id"]] = GroundedQuote(item["quote_id"], quote, ids)
    if len(payload["ideas"]) == 1:
        raise AnalysisValidationError("ideas_require_abstention_or_two_to_three", "$.ideas")
    for index, item in enumerate(payload["ideas"]):
        path = f"$.ideas[{index}]"
        ids = _source_refs(item["evidence_ids"], catalog, path)
        fact_ids, quote_ids = tuple(sorted(item["basis_fact_ids"])), tuple(sorted(item["basis_quote_ids"]))
        if any(key not in facts for key in fact_ids) or any(key not in quotes for key in quote_ids):
            raise AnalysisValidationError("unknown_basis_reference", path)
        expected_ids = {key for fact_id in fact_ids for key in facts[fact_id].evidence_ids}
        expected_ids.update(key for quote_id in quote_ids for key in quotes[quote_id].evidence_ids)
        if set(ids) != expected_ids:
            raise AnalysisValidationError("idea_evidence_must_equal_cited_basis", path)
        if (not any(facts[key].metric.startswith("trend.") for key in fact_ids)
                or not any(catalog.records[key].source in {"amazon", "reddit"} for key in ids)):
            raise AnalysisValidationError("idea_requires_trend_and_supporting_basis", path)
        name = _proposal_text(item["name"], path + ".name")
        design = _proposal_text(item["what_to_sell"], path + ".what_to_sell")
        audience = _proposal_text(item["target_audience"], path + ".target_audience")
        identity = (name.casefold(), design.casefold(), audience.casefold())
        if identity in seen_ideas:
            raise AnalysisValidationError("duplicate_proposal", path)
        seen_ideas.add(identity)
        fingerprint = json.dumps([catalog.niche_name, identity, ids, fact_ids, quote_ids], ensure_ascii=False)
        idea_id = "idea_" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
        why_now = "Quan sát liên quan (không chứng minh nên bán ngay): " + " ".join(facts[key].text for key in fact_ids)
        ideas.append(GroundedIdea(idea_id, name, design, audience, why_now, ids, fact_ids, quote_ids))
    return GroundedAnalysis(catalog.niche_name, catalog.evidence_digest,
                            tuple(facts.values()), tuple(quotes.values()), tuple(ideas), tuple(payload["limitations"]))
