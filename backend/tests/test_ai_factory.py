"""Tests for `app.integrations.ai.factory` and the shared POST transport.

The factory tests are the usual selection checks. The transport tests
cover what Wave 12 *added* to `RetryingJsonClient` — POST bodies and
default headers — because those are shared by every future integration
that authenticates by header, and a credential that quietly fails to be
sent is the kind of bug that looks like "the vendor is down".
"""

import json

import httpx
import pytest

from app.core.config import settings
from app.integrations.ai.exceptions import AINotConfiguredError
from app.integrations.ai.factory import (
    DISABLED_MODEL,
    DisabledAIProvider,
    build_ai_provider,
)
from app.integrations.ai.gemini import API_KEY_HEADER, GeminiProvider
from app.integrations.ai.ollama import OllamaProvider
from app.integrations.ai.schemas import CompletionRequest
from app.integrations.http import RetryingJsonClient


@pytest.fixture
def _restore_provider():
    original = settings.AI_PROVIDER
    yield
    settings.AI_PROVIDER = original


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("gemini", GeminiProvider),
        ("ollama", OllamaProvider),
        ("none", DisabledAIProvider),
        ("GEMINI", GeminiProvider),
    ],
)
def test_the_factory_selects_by_setting(_restore_provider, name, expected):
    settings.AI_PROVIDER = name
    provider = build_ai_provider()
    try:
        assert isinstance(provider, expected)
    finally:
        provider.close()


def test_an_unknown_provider_name_fails_loudly(_restore_provider):
    settings.AI_PROVIDER = "chatgpt"
    with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
        build_ai_provider()


def test_the_disabled_provider_refuses_with_a_named_error():
    """Switching explanations off is a deployment, not a breakage."""
    provider = DisabledAIProvider()
    assert provider.model == DISABLED_MODEL
    with pytest.raises(AINotConfiguredError, match="AI_PROVIDER"):
        provider.complete(CompletionRequest(system="s", user="u"))


def test_gemini_without_a_key_refuses_before_reaching_the_network():
    """A 401 round trip tells the operator less than this message does."""
    provider = GeminiProvider(api_key="")
    with pytest.raises(AINotConfiguredError, match="GEMINI_API_KEY"):
        provider.complete(CompletionRequest(system="s", user="u"))
    provider.close()


# -- the transport additions ------------------------------------------


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _transport(handler, **kwargs) -> RetryingJsonClient:
    return RetryingJsonClient(
        base_url="https://example.test",
        timeout=1.0,
        max_retries=1,
        min_request_interval=0.0,
        not_found_error=RuntimeError,
        unavailable_error=RuntimeError,
        invalid_response_error=ValueError,
        logger=__import__("logging").getLogger("test"),
        client=_client(handler),
        **kwargs,
    )


def test_post_json_sends_the_body_and_returns_the_parsed_document():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.read())
        seen["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, json={"ok": True})

    with _transport(handler) as http:
        assert http.post_json("/api/chat", {"model": "x"}) == {"ok": True}

    assert seen["method"] == "POST"
    assert seen["url"] == "https://example.test/api/chat"
    assert seen["body"] == {"model": "x"}
    assert seen["content_type"] == "application/json"


def test_default_headers_ride_on_every_request():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get(API_KEY_HEADER))
        return httpx.Response(200, json={})

    with _transport(handler, default_headers={API_KEY_HEADER: "secret"}) as http:
        http.post_json("/one", {})
        http.get_json("/two")

    assert seen == ["secret", "secret"]


def test_get_still_sends_no_body_after_the_refactor():
    """The POST support must not have turned every GET into a POST."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["body"] = request.read()
        return httpx.Response(200, json=[1, 2])

    with _transport(handler) as http:
        assert http.get_json("/series", {"format": "json"}) == [1, 2]

    assert seen["method"] == "GET"
    assert seen["body"] == b""
