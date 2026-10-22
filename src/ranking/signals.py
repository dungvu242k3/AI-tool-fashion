"""Independent bounded transforms of validated observations; no source I/O."""
from dataclasses import replace
import math
from statistics import median

from src.models.ranking import RankingComponent, RankingInput
from src.models.schemas import NicheData
from src.processors.commerce_scope import is_niche_listing
from src.ranking.policy import PRECISION, RankingPolicy


LABELS = {
    "momentum": "Động lượng Trends", "recent_interest": "Interest gần đây (cùng thang đo)",
    "commerce": "Rating có hỗ trợ review Amazon (proxy)", "community": "Tương tác mẫu Reddit (proxy)",
    "competition": "Rào cản review mẫu Search (proxy, cao = thấp hơn)",
}
SOURCES = {"momentum": "google_trends", "recent_interest": "google_trends", "commerce": "amazon",
           "community": "reddit", "competition": "amazon"}


def _input(record, identity, measurements) -> RankingInput:
    provenance = record.provenance
    return RankingInput(
        provenance.evidence_id, provenance.source, provenance.source_url, provenance.retrieved_at,
        provenance.request_id, provenance.from_cache, identity, tuple(measurements.items()),
    )


def _component(policy, key, scores, inputs, candidate_count, minimum, formula, tie_value=None, context=()):
    weight = dict(policy.weights)[key]
    # Consistent ordering makes serialization independent of collector/config order.
    inputs = tuple(sorted(inputs, key=lambda item: (item.identity.casefold(), item.evidence_id)))
    usable = len(scores) >= minimum
    score = round(float(median(scores)), PRECISION) if usable else None
    status = "available" if usable and len(scores) == candidate_count else ("partial" if usable else "unavailable")
    reason = ("observed_sample_only" if usable else "insufficient_measured_sample")
    return RankingComponent(
        key=key, label=LABELS[key], source=SOURCES[key], weight=weight, score=score,
        contribution=round(score * weight, PRECISION) if score is not None else None,
        status=status, reason=reason, formula=formula, sample_size=len(scores), candidate_count=candidate_count,
        inputs=inputs, context=tuple(context) + (("minimum_sample_size", minimum),),
        tie_break_value=round(float(tie_value), PRECISION) if usable and tie_value is not None else None,
    )


def unavailable(component: RankingComponent, reason: str) -> RankingComponent:
    """Keep observed inputs, but exclude an incomparable or blocked transform."""
    return replace(component, score=None, contribution=None, status="unavailable", reason=reason, tie_break_value=None)


def empty_components(policy: RankingPolicy, reason: str) -> tuple[RankingComponent, ...]:
    return tuple(RankingComponent(
        key, LABELS[key], SOURCES[key], weight, None, None, "unavailable", reason,
        "not_evaluated_without_validated_evidence", 0, 0, (),
    ) for key, weight in policy.weights)


def trend_context(data: NicheData) -> tuple | None:
    """Compare actual metric windows, not just a relative 'today 3-m' label."""
    contexts = {
        (item.geo, item.timeframe, item.metrics.previous_start, item.metrics.previous_end,
         item.metrics.recent_start, item.metrics.recent_end, item.metrics.window_points_used, item.metrics.method)
        for item in data.keywords if item.metrics is not None
    }
    return next(iter(contexts)) if len(contexts) == 1 else None


def interest_scales(data: NicheData) -> set[tuple]:
    # A website request rescales to 0..100. Even matching query labels alone
    # are not proof that separately sampled responses use the same scale.
    return {(item.provenance.request_id, tuple(sorted(item.comparison_keywords)))
            for item in data.keywords if item.metrics is not None}


def community_windows(data: NicheData) -> set[tuple]:
    windows = set()
    for item in data.discussions:
        query = item.provenance.query
        duration = (round(query["window_end_utc"] - query["window_start_utc"], 3)
                    if query["window_start_utc"] is not None else None)
        windows.add((query["sort"], query["time_filter"], duration))
    return windows


def calculate_components(data: NicheData, policy: RankingPolicy) -> tuple[RankingComponent, ...]:
    trend_inputs, momentum, recent = [], [], []
    for item in data.keywords:
        metric = item.metrics
        if metric is None:
            continue
        trend_inputs.append(_input(item, item.keyword, {
            "previous_mean": metric.previous_mean, "recent_mean": metric.recent_mean,
            "growth_percent": metric.growth_percent, "geo": item.geo, "timeframe": item.timeframe,
            "previous_start": metric.previous_start, "previous_end": metric.previous_end,
            "recent_start": metric.recent_start, "recent_end": metric.recent_end,
            "window_points_used": metric.window_points_used, "comparison_keywords": tuple(item.comparison_keywords),
        }))
        denominator = metric.previous_mean + metric.recent_mean
        if denominator > 0:
            momentum.append(100 * metric.recent_mean / denominator)
        recent.append(metric.recent_mean)
    context = trend_context(data)
    trend_scope = (("geo", context[0]), ("timeframe", context[1]), ("previous_start", context[2]),
                   ("previous_end", context[3]), ("recent_start", context[4]), ("recent_end", context[5])) if context else ()

    commerce_inputs, commerce_scores, ratings, competition_inputs, review_counts = [], [], [], [], []
    for item in data.products:
        # Scalars belong to the primary snapshot. A later search listing must
        # not turn an unrelated hub's rating into niche-specific evidence.
        if item.is_sponsored is True or not is_niche_listing(item.source_type, item.listing_url):
            continue
        observations = _input(item, item.asin, {
            "rating": item.rating, "reviews_count": item.reviews_count,
            "source_type": item.source_type, "listing_url": item.listing_url,
            "is_sponsored": item.is_sponsored,
        })
        commerce_inputs.append(observations)
        if item.rating is not None and item.reviews_count is not None:
            commerce_scores.append(20 * item.rating * item.reviews_count / (item.reviews_count + policy.review_reference))
            ratings.append(item.rating)
        if item.source_type == "search" and item.is_sponsored is False:
            competition_inputs.append(observations)
            if item.reviews_count is not None:
                review_counts.append(item.reviews_count)

    community_inputs, community_scores, comments = [], [], []
    for item in data.discussions:
        community_inputs.append(_input(item, item.post_id, {
            "score": item.score, "comments": item.comments, "created_utc": item.created_utc,
            "subreddit": item.subreddit, "time_filter": item.provenance.query["time_filter"],
            "window_start_utc": item.provenance.query["window_start_utc"],
            "window_end_utc": item.provenance.query["window_end_utc"],
        }))
        if item.score is not None and item.comments is not None:
            # Only the derived transform clips negative Reddit scores; raw
            # score is retained, and is never labelled a count of upvotes.
            engagement = max(item.score, 0) + item.comments
            community_scores.append(100 * min(math.log1p(engagement) / math.log1p(policy.community_reference), 1))
            comments.append(item.comments)

    competition_score = ([100 * policy.review_reference / (median(review_counts) + policy.review_reference)]
                         * len(review_counts)) if review_counts else []
    return (
        _component(policy, "momentum", momentum, trend_inputs, len(data.keywords), policy.min_trend_keywords,
                   "median(100*recent_mean/(previous_mean+recent_mean)); 0+0 => unavailable",
                   median(momentum) - 50 if momentum else None, trend_scope),
        _component(policy, "recent_interest", recent, trend_inputs, len(data.keywords), policy.min_trend_keywords,
                   "median(recent_mean); only one shared normalisation request across eligible niches",
                   median(recent) if recent else None, trend_scope),
        _component(policy, "commerce", commerce_scores, commerce_inputs, len(data.products), policy.min_commerce_products,
                   "median(20*rating*reviews_count/(reviews_count+review_reference)); scoped primary snapshots; exclude flagged Sponsored",
                   median(ratings) if ratings else None, (("review_reference", policy.review_reference),
                                                         ("marketplace", "www.amazon.com"))),
        _component(policy, "community", community_scores, community_inputs, len(data.discussions), policy.min_community_posts,
                   "median(100*min(log1p(max(score,0)+comments)/log1p(community_reference),1))",
                   median(comments) if comments else None, (("community_reference", policy.community_reference),)),
        _component(policy, "competition", competition_score, competition_inputs, len(data.products), policy.min_competition_products,
                   "100*review_reference/(median(reviews_count)+review_reference); organic Search sample, not total competitors",
                   -median(review_counts) if review_counts else None, (("review_reference", policy.review_reference),)),
    )
