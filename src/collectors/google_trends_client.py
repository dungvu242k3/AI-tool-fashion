"""Isolate pytrends 4.9.2 network hooks; keep its parsing and widget logic intact."""
import json
from typing import Any, Dict, List

from pytrends.request import BASE_TRENDS_URL, TrendReq

from src.collectors.context import CollectionContext
from src.collectors.errors import ResponseParseError
from src.collectors.http import HTTPResponse


class ObservedTrendReq(TrendReq):
    def __init__(self, context: CollectionContext, query: Dict[str, Any]):
        self._context = context
        self.query = query
        self.responses: Dict[str, List[HTTPResponse]] = {}
        super().__init__(hl="en-US", tz=0, timeout=context.http.policy.timeout, retries=0, backoff_factor=0)

    def begin_batch(self, query: Dict[str, Any]) -> None:
        self.query = query
        self.responses = {"bootstrap": self.responses.get("bootstrap", [])}
        self.interest_over_time_widget = {}
        self.related_queries_widget_list = []
        self.related_topics_widget_list = []

    def interest_payload(self):
        """Keep the original timeline fields instead of coercing them through pandas."""
        if not self.interest_over_time_widget:
            response = self.responses["explore"][-1]
            raise ResponseParseError(
                "missing_timeseries_widget", "Google Trends không trả widget time series.",
                request_id=response.request_id, operation="interest",
            )
        return self._get_data(
            self.INTEREST_OVER_TIME_URL, trim_chars=5,
            params={"req": json.dumps(self.interest_over_time_widget["request"]),
                    "token": self.interest_over_time_widget["token"], "tz": self.tz},
        )

    def GetGoogleCookie(self):
        response = self._context.fetch(
            "GET", f"{BASE_TRENDS_URL}/explore", operation="bootstrap",
            query={**self.query, "bootstrap_geo": self.hl[-2:]}, params={"geo": self.hl[-2:]},
        )
        self.responses.setdefault("bootstrap", []).append(response)
        return {key: value for key, value in response.cookies.items() if key == "NID"}

    def _get_data(self, url, method=TrendReq.GET_METHOD, trim_chars=0, **kwargs):
        operations = {
            self.GENERAL_URL: "explore", self.INTEREST_OVER_TIME_URL: "interest",
            self.RELATED_QUERIES_URL: "related_queries",
        }
        if url not in operations:
            raise ValueError("Unsupported pytrends operation")
        operation = operations[url]
        request_query = dict(self.query)
        if operation == "related_queries":
            payload = json.loads(kwargs["params"]["req"])
            request_query["related_keyword"] = payload["restriction"]["complexKeywordsRestriction"]["keyword"][0]["value"]
        response = self._context.fetch(
            method.upper(), url, operation=operation, query=request_query,
            headers=getattr(self, "headers", {}), cookies=self.cookies,
            retry_safe=url == self.GENERAL_URL, **kwargs,
        )
        content_type = response.headers.get("Content-Type", "").lower()
        if not any(kind in content_type for kind in ("application/json", "application/javascript", "text/javascript")):
            raise ResponseParseError(
                "invalid_content_type", "Google Trends trả nội dung không phải JSON.",
                request_id=response.request_id, operation=operation,
            )
        if len(response.text) > 2_000_000:
            raise ResponseParseError(
                "payload_too_large", "Google Trends trả JSON vượt giới hạn xử lý.",
                request_id=response.request_id, operation=operation,
            )
        payload = response.json(trim_chars)
        if not isinstance(payload, dict):
            raise ResponseParseError(
                "invalid_payload", "Google Trends trả cấu trúc JSON không hợp lệ.",
                request_id=response.request_id, operation=operation,
            )
        self.responses.setdefault(operation, []).append(response)
        return payload

    def successful_request_ids(self, keyword: str, *, include_related: bool) -> List[str]:
        return [
            response.request_id
            for operation, group in self.responses.items() for response in group
            if operation != "related_queries" or (
                include_related and response.trace.query.get("related_keyword") == keyword
            )
        ]
