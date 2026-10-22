"""Phase-5 contracts. Fixtures stay here; autouse HTTP guard forbids live test data."""
import copy
import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests

from src.analyzers.llm_analyzer import LLMAnalyzer
from src.analyzers.reddit_evidence import REDDIT_SECTION, parse_reddit_pain_points
from src.collectors.errors import CollectionError
from src.collectors.http_policy import HTTPPolicy
from src.collectors.reddit import RedditCollector
from src.collectors.reddit_provider import OAuthRedditProvider, PublicJSONRedditProvider, create_reddit_provider
from src.collectors.reddit_settings import RedditCredentials, RedditSettings, TIME_WINDOWS
from src.collectors.validation import validate_collection_result
from src.config import DATA_POLICY_VERSION
from src.models.schemas import KeywordSignal, NicheData, ProductItem
from src.pipeline import execute_pipeline
from src.processors.data_processor import DataProcessor
from src.reporters.evidence_renderer import EvidenceRenderer
from src.reporters.report_repository import ReportRepository

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
NICHE = {"name": "Fixture", "subreddits": ["fixture"], "seed_keywords": ["fixture term"]}


@pytest.fixture(autouse=True)
def isolated_reddit_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("REDDIT_", "TREND_REDDIT_")):
            monkeypatch.delenv(name)


def post(post_id="abc123", subreddit="fixture", **values):
    return {"kind": "t3", "data": {
        "id": post_id, "name": f"t3_{post_id}", "subreddit": subreddit,
        "title": "Fixture source title", "created_utc": NOW.timestamp() - 3600,
        "permalink": f"/r/{subreddit}/comments/{post_id}/fixture/",
        "selftext": "Fixture source body: I cannot find the right size.",
        "score": 0, "num_comments": 0, **values,
    }}


def listing(response_factory, *posts, headers=None):
    return response_factory(payload={"kind": "Listing", "data": {"children": list(posts)}}, headers=headers)


def run_collector(http_factory, script, *, niche=NICHE, settings=None, provider=None, policy=None):
    transport = http_factory(script, policy=policy)
    settings = settings or RedditSettings(mode="public_json")
    collector = RedditCollector(transport.client, settings=settings, provider=provider, utcnow=lambda: NOW)
    return collector.collect(niche), transport, collector


def token_response(response_factory, **values):
    return response_factory(payload={"access_token": "fixture-access-token", "token_type": "bearer", "expires_in": 3600, **values})


def oauth(settings=None, clock=lambda: 0):
    return OAuthRedditProvider(settings or RedditSettings(), RedditCredentials("fixture-client", "fixture-secret"), monotonic=clock)


def test_all_configured_searches_have_deterministic_order_and_first_snapshot(http_factory, response_factory):
    niche = {"name": "Fixture", "subreddits": ["fixture", "Other", "FIXTURE"], "seed_keywords": ["one", "two", "one"]}
    result, transport, _ = run_collector(http_factory, [
        listing(response_factory, post(score=0)), listing(response_factory, post(score=99, selftext="Changed later snapshot")),
        listing(response_factory, post("def456", "Other")), listing(response_factory, post("def456", "Other")),
    ], niche=niche)
    assert result.status == "success"
    assert [(trace.query["subreddit"], trace.query["search_term"]) for trace in result.request_metadata] == [
        ("fixture", "one"), ("fixture", "two"), ("Other", "one"), ("Other", "two")]
    assert transport.session.request.call_count == 4
    assert len(result.records) == 2  # Equal titles on different post IDs are not duplicates.
    assert result.records[0].score == 0
    assert "Changed" not in result.records[0].selftext
    assert result.records[0].provenance.request_id == result.request_metadata[0].request_id
    validated = validate_collection_result("reddit", result)
    assert validated.status == "success" and len(validated.records) == 2
    normalized = DataProcessor().process({"discussions_data": result.records + [copy.deepcopy(result.records[0])]})
    assert len(normalized.discussions) == 2
    assert result.records[0] is not normalized.discussions[0]


def test_record_cap_does_not_silently_skip_configured_queries(http_factory, response_factory):
    niche = {**NICHE, "seed_keywords": ["one", "two"]}
    result, transport, _ = run_collector(http_factory, [listing(response_factory, post(), post("def456")), listing(response_factory)],
                                         niche=niche, settings=RedditSettings(mode="public_json", max_posts=1))
    assert transport.session.request.call_count == 2
    assert result.status == "partial" and len(result.records) == 1
    assert result.warnings[0].code == "record_limit"


@pytest.mark.parametrize("time_filter", TIME_WINDOWS)
def test_time_window_is_enforced_locally_including_boundary(time_filter, http_factory, response_factory):
    seconds = TIME_WINDOWS[time_filter]
    start = NOW.timestamp() - seconds if seconds is not None else 1
    posts = [post(created_utc=start)]
    if seconds is not None:
        posts.append(post("def456", created_utc=start - 1))
    result, _, _ = run_collector(http_factory, [listing(response_factory, *posts)],
        settings=RedditSettings(mode="public_json", time_filter=time_filter))
    assert result.status == "success"
    assert [item.post_id for item in result.records] == ["abc123"]
    assert result.records[0].provenance.query["window_start_utc"] == (start if seconds is not None else None)


@pytest.mark.parametrize("created", [None, True, -1, 0, float("nan"), float("inf"), "1792454400", NOW.timestamp() + 1, 10**1000])
def test_invalid_timestamp_does_not_discard_other_posts(created, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post(created_utc=created), post("def456"))])
    assert result.status == "partial" and [item.post_id for item in result.records] == ["def456"]
    assert result.warnings[0].code == "invalid_created_utc"
    assert result.warnings[0].request_id == result.records[0].provenance.request_id


@pytest.mark.parametrize("values", [
    {"id": None}, {"id": "../bad"}, {"id": "ABC123"}, {"name": "t3_other"}, {"subreddit": "other"},
    {"title": None}, {"title": ""}, {"title": "bad\nheader"}, {"title": "x" * 501}, {"title": "bad\ud800"},
    {"permalink": "https://evil.test/r/fixture/comments/abc123/"}, {"permalink": "//evil.test/comments/abc123/"},
    {"permalink": "/r/fixture/comments/def456/fixture/"}, {"permalink": "/r/other/comments/abc123/fixture/"},
    {"permalink": "/r/fixture/comments/abc123/fixture/comment1/"}, {"permalink": "/r/fixture/comments/abc123/%2f../"},
    {"permalink": "/r/fixture/comments/abc123/fixture/?tracking=one"},
    {"permalink": "/r/fixture/comments/abc123/fixture/#fragment"}, {"selftext": 123},
    {"selftext": "x" * 40_001}, {"selftext": "bad\ud800"},
])
def test_invalid_post_fields_fail_closed(values, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post(**values), post("def456"))])
    assert [item.post_id for item in result.records] == ["def456"]
    assert result.status == "partial"


@pytest.mark.parametrize("score,comments,expected", [
    (None, None, (None, None)), (0, 0, (0, 0)), (-12, 10, (-12, 10)), (True, False, (None, None)),
    ("12", "20", (None, None)), (1.5, 3.0, (None, None)), (2**53, -2, (None, None)),
])
def test_counts_are_observed_json_integers_not_guesses(score, comments, expected, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post(score=score, num_comments=comments))])
    item = result.records[0]
    assert (item.score, item.comments) == expected
    assert validate_collection_result("reddit", result).status == "success"


@pytest.mark.parametrize("body", [None, "", "Exact body\nwith formatting. " * 60])
def test_store_full_actual_body_without_a_generated_summary(body, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post(selftext=body))])
    assert result.records[0].selftext == body
    if not body:
        assert result.records[0].content_summary == ""
    else:
        assert body.startswith(result.records[0].content_summary.removesuffix("..."))
    assert validate_collection_result("reddit", result).status == "success"


@pytest.mark.parametrize("values", [{"selftext": "[removed]"}, {"selftext": "[deleted]"}, {"removed_by_category": "moderator"}])
def test_deleted_source_content_is_not_republished(values, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post(**values))])
    assert result.status == "failed" and not result.records


@pytest.mark.parametrize("payload", [[], {}, {"data": {}}, {"data": {"children": "invalid"}}])
def test_bad_listing_schema_is_not_treated_as_success(payload, http_factory, response_factory):
    result, transport, _ = run_collector(http_factory, [response_factory(payload=payload)])
    assert result.status == "failed" and not result.records
    assert result.warnings[0].code == "invalid_payload" and transport.session.request.call_count == 1


def test_oversized_json_and_children_are_bounded(http_factory, response_factory):
    for settings, response, expected in [
        (RedditSettings(mode="public_json", max_json_chars=100), listing(response_factory, post()), "response_too_large"),
        (RedditSettings(mode="public_json", page_size=1), listing(response_factory, post(), post("def456")), "invalid_payload"),
    ]:
        result, _, _ = run_collector(http_factory, [response], settings=settings)
        assert result.status == "failed" and result.warnings[0].code == expected


@pytest.mark.parametrize("niche", [
    {**NICHE, "subreddits": "fixture"}, {**NICHE, "subreddits": ["../escape"]},
    {**NICHE, "subreddits": ["one+two"]}, {**NICHE, "subreddits": ["fixture\r\nHeader: x"]},
    {**NICHE, "seed_keywords": []}, {**NICHE, "seed_keywords": "term"},
    {**NICHE, "seed_keywords": [None]}, {**NICHE, "seed_keywords": ["x" * 201]},
    {**NICHE, "seed_keywords": ["term\x00"]},
    {**NICHE, "subreddits": ["s" + str(i) for i in range(8)], "seed_keywords": [str(i) for i in range(8)]},
])
def test_invalid_inputs_never_issue_http_requests(niche, http_factory):
    result, transport, _ = run_collector(http_factory, [], niche=niche)
    assert result.status == "failed" and result.warnings[0].code == "invalid_configuration"
    assert transport.session.request.call_count == 0


@pytest.mark.parametrize("values", [{"max_posts": 0}, {"max_queries": 65}, {"max_keywords": True},
    {"page_size": 101}, {"max_json_chars": 5_000_001}, {"time_filter": "forever"},
    {"sort": "random"}, {"mode": "proxy"}, {"user_agent": "Header\r\nInjected: yes"}])
def test_settings_are_validated(values):
    with pytest.raises(ValueError):
        RedditSettings(**values)


def test_env_errors_and_incomplete_credentials_are_source_failures(monkeypatch, http_factory):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "fixture-private-client")
    transport = http_factory([])
    result = RedditCollector(transport.client).collect(NICHE)
    assert result.status == "failed" and result.warnings[0].code == "invalid_configuration"
    assert "fixture-private" not in json.dumps(result.status_dict())
    assert transport.session.request.call_count == 0
    monkeypatch.delenv("REDDIT_CLIENT_ID")
    monkeypatch.setenv("TREND_REDDIT_PAGE_SIZE", "not-a-number")
    assert RedditCollector(transport.client).collect(NICHE).status == "failed"


def test_provider_selection_prefers_oauth_and_never_silently_downgrades(monkeypatch):
    assert isinstance(create_reddit_provider(RedditSettings()), PublicJSONRedditProvider)
    monkeypatch.setenv("REDDIT_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "fixture-secret")
    assert isinstance(create_reddit_provider(RedditSettings()), OAuthRedditProvider)
    assert type(create_reddit_provider(RedditSettings(mode="public_json"))) is PublicJSONRedditProvider
    assert create_reddit_provider(RedditSettings(mode="disabled")) is None
    monkeypatch.delenv("REDDIT_CLIENT_SECRET")
    with pytest.raises(ValueError):
        create_reddit_provider(RedditSettings())


def test_disabled_and_unconfigured_sources_do_not_call_network(http_factory):
    for settings, niche in [(RedditSettings(mode="disabled"), NICHE), (RedditSettings(), {"name": "Fixture", "subreddits": []})]:
        result, transport, _ = run_collector(http_factory, [], settings=settings, niche=niche)
        assert result.status == "not_configured" and not result.request_metadata
        assert transport.session.request.call_count == 0


def test_oauth_form_secrets_and_bearer_never_enter_audit_or_logs(http_factory, response_factory, caplog):
    caplog.set_level("INFO")
    result, transport, _ = run_collector(http_factory, [token_response(response_factory), listing(response_factory, post())], provider=oauth())
    assert result.status == "success" and validate_collection_result("reddit", result).status == "success"
    grant, search = transport.session.request.call_args_list
    assert grant.args == ("POST", "https://www.reddit.com/api/v1/access_token")
    assert grant.kwargs["data"] == {"grant_type": "client_credentials"}
    assert grant.kwargs["auth"].username == "fixture-client"
    assert grant.kwargs["auth"].password == "fixture-secret"
    assert search.args[1].startswith("https://oauth.reddit.com/")
    assert search.kwargs["headers"]["Authorization"] == "Bearer fixture-access-token"
    assert search.kwargs["allow_redirects"] is False
    assert result.records[0].provenance.request_ids == [result.request_metadata[1].request_id]
    audit = json.dumps(result.status_dict(include_requests=True)) + json.dumps(asdict(result)) + caplog.text
    for private in ("fixture-client", "fixture-secret", "fixture-access-token"):
        assert private not in audit and private not in repr(RedditCredentials("fixture-client", "fixture-secret"))


def test_oauth_token_is_reused_but_not_faked_as_a_new_request(http_factory, response_factory):
    result, transport, collector = run_collector(http_factory, [token_response(response_factory),
        listing(response_factory, post()), listing(response_factory, post("def456"))], provider=oauth())
    second = collector.collect(NICHE)
    assert result.status == second.status == "success"
    assert len(result.request_metadata) == 2 and len(second.request_metadata) == 1
    assert transport.session.request.call_count == 3


def test_expired_oauth_token_is_renewed_in_memory(http_factory, response_factory):
    clock = [0]
    result, transport, collector = run_collector(http_factory, [token_response(response_factory, expires_in=10),
        listing(response_factory, post()), token_response(response_factory, access_token="fixture-renewed"),
        listing(response_factory, post("def456"))], provider=oauth(clock=lambda: clock[0]))
    clock[0] = 11
    second = collector.collect(NICHE)
    assert result.status == second.status == "success"
    assert [trace.operation for trace in second.request_metadata] == ["oauth_token", "search"]
    assert transport.session.request.call_args_list[-1].kwargs["headers"]["Authorization"] == "Bearer fixture-renewed"


@pytest.mark.parametrize("final_status", [200, 401])
def test_401_allows_only_one_oauth_refresh_never_public_fallback(final_status, http_factory, response_factory):
    result, transport, _ = run_collector(http_factory, [token_response(response_factory), response_factory(401),
        token_response(response_factory, access_token="fixture-new-token"),
        listing(response_factory, post()) if final_status == 200 else response_factory(401)], provider=oauth())
    assert transport.session.request.call_count == 4
    assert [trace.status_code for trace in result.request_metadata] == [200, 401, 200, final_status]
    assert result.status == ("success" if final_status == 200 else "failed")
    assert all("oauth.reddit.com" in call.args[1] for call in transport.session.request.call_args_list if call.args[0] == "GET")


@pytest.mark.parametrize("values", [{"access_token": ""}, {"access_token": "bad\r\nInjected: x"},
    {"expires_in": None}, {"expires_in": True}, {"expires_in": 0}, {"expires_in": float("inf")},
    {"expires_in": 10**1000}, {"token_type": "not-bearer"}])
def test_invalid_token_response_never_reaches_search(values, http_factory, response_factory):
    result, transport, _ = run_collector(http_factory, [token_response(response_factory, **values)], provider=oauth())
    assert result.status == "failed" and result.warnings[0].code == "invalid_oauth_response"
    assert transport.session.request.call_count == 1


@pytest.mark.parametrize("stage", ["grant", "search"])
def test_oauth_redirects_are_rejected_before_forwarding_secrets(stage, http_factory, response_factory):
    script = [] if stage == "grant" else [token_response(response_factory)]
    origin = "www.reddit.com" if stage == "grant" else "oauth.reddit.com"
    script.append(response_factory(307, headers={"Location": f"https://{origin}/other"}))
    result, transport, _ = run_collector(http_factory, script, provider=oauth())
    assert result.warnings[0].code == "redirect_rejected"
    assert transport.session.request.call_count == (1 if stage == "grant" else 2)


def test_oauth_token_post_is_not_implicitly_retried(http_factory, response_factory):
    result, transport, _ = run_collector(http_factory, [response_factory(503)], provider=oauth(), policy=HTTPPolicy(max_attempts=3))
    assert result.status == "failed" and transport.session.request.call_count == 1
    assert result.warnings[0].operation == "oauth_token"


@pytest.mark.parametrize("failure", [403, 429, 503, "connection", "html"])
def test_blocked_source_stops_remaining_queries_without_mock_data(failure, http_factory, response_factory):
    response = requests.ConnectionError("private network details") if failure == "connection" else (
        response_factory(text="<html>Access blocked</html>") if failure == "html" else response_factory(failure))
    result, transport, _ = run_collector(http_factory, [response], niche={**NICHE, "seed_keywords": ["one", "two"]})
    assert result.status == "failed" and result.records == [] and transport.session.request.call_count == 1
    assert "private network" not in json.dumps(result.status_dict())


def test_partial_records_survive_a_later_block(http_factory, response_factory):
    result, transport, _ = run_collector(http_factory, [listing(response_factory, post()), response_factory(403)],
                                         niche={**NICHE, "seed_keywords": ["one", "two", "three"]})
    assert result.status == "partial" and len(result.records) == 1 and transport.session.request.call_count == 2
    assert validate_collection_result("reddit", result).status == "partial"


def test_quota_headers_stop_without_sleep_or_extra_http(http_factory, response_factory):
    provider = PublicJSONRedditProvider(RedditSettings(mode="public_json"), monotonic=lambda: 0)
    result, transport, collector = run_collector(http_factory, [listing(response_factory, post(), headers={
        "X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset": "60"})], provider=provider,
        niche={**NICHE, "seed_keywords": ["one", "two"]})
    assert result.status == "partial" and result.warnings[0].code == "source_cooldown"
    assert collector.collect(NICHE).status == "failed"
    assert transport.session.request.call_count == 1 and transport.clock.sleeps == []


@pytest.mark.parametrize("changes", [
    {"post_id": None}, {"post_id": "def456"}, {"subreddit": "other"}, {"provider": []}, {"provider": "mock"},
    {"score": True}, {"comments": -1}, {"score": 2**53}, {"created_utc": NOW.timestamp() + 100},
    {"created_utc": None}, {"selftext": "[deleted]"}, {"content_summary": "Invented pain point"},
    {"permalink": "/r/fixture/comments/abc123/elsewhere/comment/"}, {"url": "https://evil.test/post"},
])
def test_invalid_discussion_contract_has_no_legacy_bypass(changes, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post())])
    invalid = replace(copy.deepcopy(result.records[0]), **changes)
    invalid.provenance = replace(invalid.provenance, evidence_id=uuid4().hex, source_url=invalid.url)
    result.records.append(invalid)
    validated = validate_collection_result("reddit", result)
    assert validated.status == "partial" and len(validated.records) == 1
    assert validated.warnings[0].code == "invalid_discussion_evidence"


@pytest.mark.parametrize("changes", [{"time_filter": []}, {"subreddit": None}, {"provider": "mock"},
    {"window_end_utc": True}, {"window_end_utc": NOW.timestamp() + 100}, {"window_start_utc": None}, {"sort": "random"}])
def test_forged_query_contract_is_rejected(changes, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post())])
    query = {**result.request_metadata[0].query, **changes}
    result.request_metadata[0] = replace(result.request_metadata[0], query=query)
    result.records[0].provenance = replace(result.records[0].provenance, query=query)
    assert validate_collection_result("reddit", result).status == "failed"


def test_blocked_reddit_yields_partial_pipeline_with_other_real_evidence_contracts(tmp_path, http_factory, response_factory, collection_factory):
    transport = http_factory([response_factory(403)])
    collector = RedditCollector(transport.client, settings=RedditSettings(mode="public_json"), utcnow=lambda: NOW)
    sources = {
        "google_trends": SimpleNamespace(collect=lambda niche: collection_factory("google_trends", [
            KeywordSignal("one", score=0, source_url="https://trends.google.com/trends/explore?q=one"),
            KeywordSignal("two", score=20, source_url="https://trends.google.com/trends/explore?q=two")])) ,
        "amazon": SimpleNamespace(collect=lambda niche: collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])) ,
        "reddit": collector,
    }
    result = execute_pipeline(fast_mode=True, niche_list=[NICHE], output_dir=str(tmp_path), collectors=sources)
    assert result["status"] == "partial" and not result["success"]
    assert result["metadata"]["total_discussions"] == 0 and result["metadata"]["total_keywords"] == 2
    assert result["source_statuses"]["Fixture"]["reddit"]["status"] == "failed"
    assert result["niches"]["Fixture"]["reddit_pain_points"] == []


def test_v4_cache_is_not_silently_accepted_under_reddit_contract(tmp_path):
    repository = ReportRepository(tmp_path)
    repository.save_latest({"metadata": {"data_policy": "live-only-v4"}, "markdown_content": "Historical", "niches": {}})
    assert DATA_POLICY_VERSION != "live-only-v4" and repository.load_latest()["status"] == "legacy"


def test_markdown_escapes_reddit_source_strings_and_preserves_zero(http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post(title="<script>bad()</script> [link](javascript:bad)", selftext="<img src=x>"))])
    section = EvidenceRenderer.section(NicheData("Fixture", "", discussions=result.records), "not_requested")
    assert "<script>" not in section.analysis_content and "<img" not in section.analysis_content
    assert "điểm Reddit 0" in section.analysis_content and "bình luận 0" in section.analysis_content
    assert result.records[0].provenance.evidence_id in section.analysis_content
    assert "2026-10-20T23:00:00+00:00" in section.analysis_content


@pytest.fixture
def community_data(http_factory, response_factory, qualified_data_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post())])
    return qualified_data_factory(NicheData("Fixture", "", discussions=result.records, keywords=[
        KeywordSignal("one", score=0, trend="stable", source_url="https://trends.google.com/trends/explore?q=one"),
        KeywordSignal("two", score=20, trend="stable", source_url="https://trends.google.com/trends/explore?q=two")]))


def pain_payload(data, **changes):
    return {"pain_points": [{"quote": "I cannot find the right size.", "evidence_ids": [data.discussions[0].provenance.evidence_id], **changes}]}


def test_pain_point_contract_accepts_only_verbatim_quotes_with_reddit_ids(community_data):
    points = parse_reddit_pain_points(json.dumps(pain_payload(community_data)), community_data.discussions)
    assert len(points) == 1 and points[0].evidence_ids == (community_data.discussions[0].provenance.evidence_id,)
    assert points[0].to_dict()["evidence_ids"] == [community_data.discussions[0].provenance.evidence_id]


@pytest.mark.parametrize("changes", [
    {"evidence_ids": []}, {"evidence_ids": ["invented-id"]}, {"evidence_ids": "invalid"},
    {"quote": "Customers universally demand a new product."}, {"quote": ""}, {"quote": "x" * 501},
    {"claim": "Unverified market claim"},
])
def test_unsupported_pain_point_is_rejected(changes, community_data):
    with pytest.raises(ValueError):
        parse_reddit_pain_points(json.dumps(pain_payload(community_data, **changes)), community_data.discussions)


def llm_output():
    text = "### 1. Keyword\nFixture\n### 2. Phân tích\nUNSUPPORTED_COMMUNITY_ASSERTION\n### 3. Idea sản phẩm\n"
    for index in (1, 2):
        text += (f"{index}. **Fixture idea {index}**\n- **Bán cái gì**: Fixture design\n- **Cho ai**: Chưa xác minh\n"
                 "- **Vì sao nên bán bây giờ**: Suy luận, cần kiểm chứng\n- **Dựa trên**: Nguồn trong dữ liệu\n")
    return text


def test_ai_community_analysis_uses_grounded_quotes_not_free_prose(monkeypatch, community_data, grounded_payload_factory):
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: json.dumps(grounded_payload_factory(community_data)))
    section = analyzer.analyze("Fixture", community_data)
    assert section.analysis_status == "success" and section.generation_mode == "ollama"
    assert "UNSUPPORTED_COMMUNITY_ASSERTION" not in section.analysis_content
    assert "I cannot find the right size." in section.analysis_content
    assert section.reddit_pain_points[0].evidence_ids[0] in section.analysis_content
    assert section.to_dict()["reddit_pain_points"][0]["evidence_ids"]


@pytest.mark.parametrize("suffix", ["", REDDIT_SECTION + '\n{"pain_points":[{"quote":"Invented claim","evidence_ids":["unknown"]}]}'])
def test_ai_output_without_grounded_reddit_evidence_fails_closed(suffix, monkeypatch, community_data):
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: llm_output() + suffix)
    section = analyzer.analyze("Fixture", community_data)
    assert section.analysis_status == "invalid_output" and section.reddit_pain_points == []
    assert section.ideas == [] and "UNSUPPORTED_COMMUNITY_ASSERTION" not in section.analysis_content


@pytest.mark.parametrize("authenticated", [False, True])
def test_search_auth_does_not_load_ambient_netrc_or_session_credentials(authenticated, monkeypatch, http_factory, response_factory):
    monkeypatch.setattr(requests.sessions, "get_netrc_auth", lambda *a, **kw: pytest.fail("Ambient .netrc must not be read"))
    provider = oauth() if authenticated else PublicJSONRedditProvider(RedditSettings(mode="public_json"))
    script = ([token_response(response_factory)] if authenticated else []) + [listing(response_factory, post())]
    result, transport, _ = run_collector(http_factory, script, provider=provider)
    assert result.status == "success"
    call = transport.session.request.call_args_list[-1]
    with requests.Session() as session:
        session.headers["Authorization"] = "Basic ambient-session-secret"
        session.auth = ("ambient-user", "ambient-password")
        prepared = session.prepare_request(requests.Request("GET", call.args[1], headers=call.kwargs["headers"], auth=call.kwargs["auth"]))
    assert prepared.headers.get("Authorization") == ("Bearer fixture-access-token" if authenticated else None)


@pytest.mark.parametrize("slug", [".", ".."])
def test_permalink_dot_segments_are_not_post_urls(slug, http_factory, response_factory):
    result, _, _ = run_collector(http_factory, [listing(response_factory, post(permalink=f"/r/fixture/comments/abc123/{slug}/"))])
    assert result.status == "failed" and result.warnings[0].code == "invalid_record"


def test_oversized_oauth_bearer_is_not_forwarded_to_headers(http_factory, response_factory):
    result, transport, _ = run_collector(http_factory, [token_response(response_factory, access_token="x" + "=" * 5000)], provider=oauth())
    assert result.status == "failed" and result.warnings[0].code == "invalid_oauth_response"
    assert transport.session.request.call_count == 1


def test_explicit_public_mode_does_not_read_unused_credentials(monkeypatch):
    monkeypatch.setattr(RedditCredentials, "from_env", lambda: pytest.fail("Explicit public mode must not read credentials"))
    assert type(create_reddit_provider(RedditSettings(mode="public_json"))) is PublicJSONRedditProvider


@pytest.mark.parametrize("location", ["https://www.reddit.com/other", "https://evil.test/other"])
def test_shared_transport_never_redirects_a_credential_form_body(location, http_factory, response_factory):
    transport = http_factory([response_factory(307, headers={"Location": location})])
    journal = []
    with pytest.raises(CollectionError) as caught:
        transport.client.fetch("POST", "https://www.reddit.com/api/v1/access_token", source="reddit", operation="oauth_token",
                               query={"grant_type": "fixture"}, journal=journal, data={"secret": "fixture-form-secret"})
    assert caught.value.warning.code == "redirect_rejected" and transport.session.request.call_count == 1
    assert "fixture-form-secret" not in json.dumps([asdict(trace) for trace in journal])


def test_ai_cannot_publish_a_community_analysis_without_any_reddit_source(monkeypatch, qualified_data_factory, grounded_payload_factory):
    data = NicheData("Fixture", "", keywords=[
        KeywordSignal("one", trend="stable", score=0, source_url="https://trends.google.com/trends/explore?q=one"),
        KeywordSignal("two", trend="stable", score=20, source_url="https://trends.google.com/trends/explore?q=two"),
    ], products=[ProductItem("Fixture product", url="https://www.amazon.com/dp/B000000001")])
    data = qualified_data_factory(data)
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: json.dumps(grounded_payload_factory(data)))
    section = analyzer.analyze("Fixture", data)
    assert section.analysis_status == "success" and len(section.ideas) == 2
    assert "UNSUPPORTED_COMMUNITY_ASSERTION" not in section.analysis_content
    assert not section.reddit_pain_points
