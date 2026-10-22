"""Single canonical ranking service; LLMs/renderers never score or reorder."""
from dataclasses import replace
import math
from typing import Iterable

from src.collectors.evidence_validation import valid_text
from src.models.ranking import NicheRanking, RankingResult
from src.models.schemas import NicheData
from src.processors.data_quality import has_sufficient_evidence
from src.ranking.policy import MAX_NICHES, MAX_RECORDS_PER_SOURCE, PRECISION, RankingPolicy
from src.ranking.signals import (
    calculate_components, community_windows, empty_components, interest_scales, trend_context, unavailable,
)


NOTES = (
    "Điểm là quy tắc ưu tiên nghiên cứu từ mẫu quan sát, chưa được hiệu chỉnh bằng kết quả kinh doanh; không dự báo doanh số/lợi nhuận.",
    "Thiếu component giữ null, không chia lại trọng số; điểm quan sát là cận dưới theo quy ước 0–100, không coi unknown là số đo 0.",
    "Confidence chỉ đo độ đầy đủ input × valid ratio, không phải xác suất thành công hoặc chứng nhận đại diện thị trường.",
    "Ranking niche không tự chứng nhận ý tưởng; chỉ đề xuất đã qua kiểm tra evidence mới được xét trong summary riêng.",
)


class RankingService:
    def __init__(self, policy: RankingPolicy | None = None):
        self.policy = policy if policy is not None else RankingPolicy()
        if not isinstance(self.policy, RankingPolicy):
            raise TypeError("RankingService requires a validated RankingPolicy")

    def rank(self, niches: Iterable[NicheData]) -> RankingResult:
        """Pure deterministic operation on bounded, assessed evidence snapshots."""
        entries = []
        names = set()
        for data in niches:
            if len(entries) >= MAX_NICHES:
                raise ValueError("Too many niches for one ranking run")
            if not isinstance(data, NicheData) or not valid_text(data.niche_name, 200):
                raise ValueError("Ranking requires named NicheData snapshots")
            key = data.niche_name.strip().casefold()
            if key in names:
                raise ValueError("Ranking niche names must be unique")
            if any(not isinstance(items, list) or len(items) > MAX_RECORDS_PER_SOURCE
                   for items in (data.keywords, data.products, data.discussions)):
                raise ValueError("Ranking evidence lists exceed their bounded contract")
            names.add(key)
            entries.append(data)

        eligible = [data for data in entries if has_sufficient_evidence(data)]
        contexts = {trend_context(data) for data in eligible}
        shared_windows = bool(eligible) and len(contexts) == 1 and None not in contexts
        scales = set().union(*(interest_scales(data) for data in eligible)) if eligible else set()
        shared_interest = shared_windows and len(scales) == 1
        reddit_windows = set().union(*(community_windows(data) for data in eligible)) if eligible else set()
        eligible_names = {data.niche_name for data in eligible}
        scored, blocked = [], []
        for data in entries:
            valid = data.niche_name in eligible_names
            components = calculate_components(data, self.policy) if valid else empty_components(self.policy, "quality_gate_not_passed_or_evidence_changed")
            reasons = []
            if not valid:
                reasons.append("quality_gate_not_passed_or_evidence_changed")
            elif not shared_windows:
                reasons.append("incomparable_trend_windows_or_geography")
                components = tuple(unavailable(item, reasons[-1]) if item.source == "google_trends" else item for item in components)
            elif not shared_interest:
                components = tuple(unavailable(item, "different_google_normalisation_requests")
                                   if item.key == "recent_interest" else item for item in components)
            if valid and len(reddit_windows) > 1:
                components = tuple(unavailable(item, "different_reddit_collection_windows")
                                   if item.key == "community" else item for item in components)
            present = [item for item in components if item.score is not None]
            coverage = round(math.fsum(item.weight for item in present), PRECISION)
            observed = round(math.fsum(item.contribution for item in present), PRECISION) if present else None
            assessment = data.quality_assessment
            completeness = math.fsum(item.weight * item.sample_size / item.candidate_count
                                    for item in present if item.candidate_count)
            confidence = (round(100 * completeness * assessment.valid_ratio, PRECISION)
                          if valid and assessment.valid_ratio is not None else None)
            if valid and not any(item.source == "google_trends" for item in present):
                reasons.append("no_comparable_trend_component")
            if valid and not any(item.source in {"amazon", "reddit"} for item in present):
                reasons.append("insufficient_measured_supporting_sample")
            row = NicheRanking(
                niche=data.niche_name, rank=None, status="unranked" if reasons else "ranked",
                observed_score=observed, total_score=observed if len(present) == len(components) else None,
                score_upper_bound=round(min(100, observed + 100 * (1 - coverage)), PRECISION) if observed is not None else None,
                component_coverage=coverage, confidence=confidence,
                quality_status=assessment.status if assessment else "insufficient",
                evidence_digest=assessment.data_digest if valid else None,
                components=components, reasons=tuple(reasons), explanation="",
            )
            (blocked if reasons else scored).append(row)

        # A missing tie metric is tagged, not imputed as observed zero.
        def measured_key(row):
            metrics = tuple((item.tie_break_value is not None,
                             item.tie_break_value if item.tie_break_value is not None else 0) for item in row.components)
            return (row.observed_score, *metrics)

        scored.sort(key=lambda row: (tuple(_descending(value) for value in measured_key(row)), row.niche.casefold(), row.niche))
        ranked = []
        previous_key, previous_rank = None, None
        for position, row in enumerate(scored, 1):
            key = measured_key(row)
            rank = previous_rank if key == previous_key else position
            explanation = self._explain(row, ranked[-1] if ranked else None, key == previous_key)
            ranked.append(replace(row, rank=rank, explanation=explanation))
            previous_key, previous_rank = key, rank
        blocked.sort(key=lambda row: (row.niche.casefold(), row.niche))
        blocked = [replace(row, explanation="Chưa xếp hạng: " + "; ".join(row.reasons) + ".") for row in blocked]
        status = ("available" if not blocked and all(row.total_score is not None for row in ranked) else "partial") if ranked else "unavailable"
        return RankingResult(status, self.policy, tuple(ranked), tuple(blocked), NOTES)

    @staticmethod
    def _explain(row, previous, same_keys):
        text = f"Đóng góp quan sát {row.observed_score:.6f}/100; phủ trọng số {row.component_coverage:.1%}."
        if previous is not None:
            if same_keys:
                text += f" Đồng hạng với {previous.niche}: các metric phân hạng bằng nhau; tên chỉ ổn định hiển thị."
            elif row.observed_score == previous.observed_score:
                key = next(item.key for item, other in zip(row.components, previous.components)
                           if item.tie_break_value != other.tie_break_value)
                text += f" Bằng điểm quan sát với {previous.niche}; phân hạng bằng metric thật theo ưu tiên {key}."
            else:
                delta = previous.observed_score - row.observed_score
                text += f" Thấp hơn {previous.niche} {delta:.6f} điểm đóng góp quan sát; xem contribution từng nhóm để đối chiếu."
            if row.score_upper_bound >= previous.observed_score:
                text += " Khoảng điểm còn bất định chồng lấp; chưa kết luận niche trước có tiềm năng kinh doanh cao hơn."
        if row.total_score is None:
            text += " Thiếu nhóm: " + ", ".join(item.key for item in row.components if item.score is None) + "; không reweight."
        return text


def _descending(value):
    """Order tagged measured keys descending without a configuration-order tie."""
    if isinstance(value, tuple):
        return tuple(-part for part in value)
    return -value
