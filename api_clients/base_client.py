"""Base class for every API client in the suite.

Tests never call ``requests`` directly (ARCHITECTURE.md section 6); they go
through a client that subclasses ``BaseClient``.

**The one thing to understand about this target API.** automationexercise.com
answers *every* request with HTTP 200 and reports the real outcome inside the
JSON body's ``responseCode`` field. A missing parameter comes back as
``HTTP 200`` with ``{"responseCode": 400, "message": "Bad request, ..."}``.

That is not a detail we can paper over: a suite that asserted on
``response.status_code`` would see 200 everywhere and every negative test would
pass without testing anything. So ``ApiResponse.status`` deliberately means the
*body* code, and ``http_status`` is kept separately for the rare assertion that
genuinely cares about the transport layer. Verified against the live API on
2026-09-09; see ARCHITECTURE.md section 3.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

import requests
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError

from config.settings import settings


@dataclass(frozen=True)
class ApiResponse:
    """A parsed response from the target API.

    ``status`` is the body's ``responseCode`` when present, falling back to the
    HTTP status for endpoints that do not use the envelope.
    """

    http_status: int
    status: int | None
    body: dict[str, Any]
    message: str | None
    elapsed_ms: float
    raw: requests.Response

    @classmethod
    def from_response(cls, response: requests.Response) -> "ApiResponse":
        try:
            # The API sometimes serves JSON with a text/html content type, so
            # parse the text rather than trusting response.json()'s dispatch.
            body = json.loads(response.text)
        except ValueError:
            body = {}

        if not isinstance(body, dict):
            body = {"data": body}

        return cls(
            http_status=response.status_code,
            status=body.get("responseCode", response.status_code),
            body=body,
            message=body.get("message"),
            elapsed_ms=response.elapsed.total_seconds() * 1000,
            raw=response,
        )

    @property
    def json_decodable(self) -> bool:
        return bool(self.body)

    def assert_status(self, expected: int) -> "ApiResponse":
        """Assert the API-level status, with a message that shows the body.

        Returned so calls can chain; raises AssertionError on mismatch.
        """
        assert self.status == expected, (
            f"expected responseCode {expected}, got {self.status} "
            f"(HTTP {self.http_status}); message={self.message!r}; body={self.body!r}"
        )
        return self

    def matches_schema(self, schema: Mapping[str, Any]) -> bool:
        """Whether the body satisfies a JSON Schema, without raising."""
        return Draft202012Validator(schema).is_valid(self.body)

    def validate_schema(self, schema: Mapping[str, Any]) -> "ApiResponse":
        """Validate the body against a JSON Schema.

        Reports *every* violation at once rather than only the first, so a
        broken contract is diagnosable from one failure message.
        """
        errors = sorted(
            Draft202012Validator(schema).iter_errors(self.body),
            key=lambda e: list(e.path),
        )
        if errors:
            detail = "\n".join(
                f"  - {'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
                for e in errors
            )
            raise JsonSchemaValidationError(
                f"response body failed schema validation "
                f"({len(errors)} violation(s)):\n{detail}"
            )
        return self


class BaseClient:
    """Thin, session-reusing wrapper around one API surface.

    Subclasses set ``ENDPOINT`` (or pass explicit paths) and expose one
    intent-named method per operation.
    """

    #: Default endpoint path, relative to the API base URL.
    ENDPOINT: str = ""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.timeout_s = settings.timeout_ms / 1000

    # ------------------------------------------------------------------
    # verbs
    # ------------------------------------------------------------------
    def get(self, path: str | None = None, **kwargs: Any) -> ApiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str | None = None, **kwargs: Any) -> ApiResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str | None = None, **kwargs: Any) -> ApiResponse:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str | None = None, **kwargs: Any) -> ApiResponse:
        return self.request("DELETE", path, **kwargs)

    def request(self, method: str, path: str | None = None, **kwargs: Any) -> ApiResponse:
        """Issue a request and parse it into an ApiResponse."""
        kwargs.setdefault("timeout", self.timeout_s)
        response = self.session.request(method, self._url(path), **kwargs)
        return ApiResponse.from_response(response)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _url(self, path: str | None = None) -> str:
        return settings.api_url_for(self.ENDPOINT if path is None else path)
