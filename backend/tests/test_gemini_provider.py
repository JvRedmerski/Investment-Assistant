"""Tests for `GeminiProvider`, built from payloads captured live.

Written **after** the first real call and not before, which is the whole
point. Wave 12 deliberately shipped this provider with no unit test at
all: every fixture would have been a payload written from the published
contract by the same person who wrote the parser from it, and
`docs/planning/IMPLEMENTATION_GUIDE.md` has the Wave 06 scar to show
what that is worth — *a mock built from an assumption does not check the
assumption, it reproduces it*.

The payloads below were captured on 2026-08-22 from
`gemini-flash-latest`, which resolved to `gemini-3.7-flash`. Field
spellings are exactly as they came off the wire, including the ones the
parser ignores.

What the live calls actually caught is locked in by
`test_a_truncated_answer_is_flagged_rather_than_passed_off_as_complete`:
the previous default of 1.024 output tokens was spent 981 tokens on
reasoning and returned a sentence cut mid-list, and because `MAX_TOKENS`
was treated as a normal finish, the fragment reached the reader as a
finished explanation.
"""

import json

import httpx
import pytest

from app.integrations.ai.exceptions import (
    AINotConfiguredError,
    AIResponseBlockedError,
    InvalidAIResponseError,
)
from app.integrations.ai.gemini import GeminiProvider
from app.integrations.ai.schemas import CompletionRequest

REQUEST = CompletionRequest(
    system="Voce explica numeros ja calculados. Nunca calcule.",
    user="Fatos:\n- Retorno da carteira: 12,40%\nPergunta: estou batendo o CDI?",
    temperature=0.2,
    max_output_tokens=2048,
)


def _provider(handler, **kwargs) -> GeminiProvider:
    return GeminiProvider(
        api_key="test-key",
        base_url="https://gemini.test/v1beta",
        model="gemini-flash-latest",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def _static(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return handler


# -- the captured payloads --------------------------------------------

#: A complete answer. `thoughtSignature` rides inside the same part as
#: `text` and is ignored; `thoughtsTokenCount` is 3.6x the prose it paid
#: for, which is the figure that made `thinking_tokens` necessary.
LIVE_COMPLETE = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": (
                            "Sim, voce esta superando o CDI no periodo "
                            "avaliado. O retorno da carteira foi de 12,40%."
                        ),
                        "thoughtSignature": "EscECsQEARFNMg+3+I0qHbRD0vvzyJG7zHM0",
                    }
                ],
                "role": "model",
            },
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 180,
        "candidatesTokenCount": 153,
        "totalTokenCount": 881,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 180}],
        "thoughtsTokenCount": 548,
        "serviceTier": "standard",
    },
    "modelVersion": "gemini-3.7-flash",
    "responseId": "oxCJaprBCKuYqtsPjZfHqQ4",
}

#: The defect, exactly as observed at the old default of 1.024 tokens on
#: a realistic 28-fact contribution-plan pack. `finishReason` is the
#: *only* signal: the text reads like prose right up to the colon that
#: promises a list which never arrives.
LIVE_TRUNCATED = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": (
                            "O plano de aporte da sua carteira alocou "
                            "R$ 742,30 do total de R$ 1.000,00 a distribuir "
                            "entre tres ativos:"
                        )
                    }
                ],
                "role": "model",
            },
            "finishReason": "MAX_TOKENS",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 1298,
        "candidatesTokenCount": 39,
        "totalTokenCount": 2318,
        "thoughtsTokenCount": 981,
    },
    "modelVersion": "gemini-3.7-flash",
}

#: Budget gone before the first word, shape one: a part with no `text`
#: key at all. `candidatesTokenCount` is *absent*, not zero.
LIVE_STARVED_EMPTY_PART = {
    "candidates": [
        {"content": {"parts": [{}], "role": "model"}, "finishReason": "MAX_TOKENS"}
    ],
    "usageMetadata": {"promptTokenCount": 180, "totalTokenCount": 180},
    "modelVersion": "gemini-3.7-flash",
}

#: Shape two, same cause: `parts` missing altogether.
LIVE_STARVED_NO_PARTS = {
    "candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS"}],
    "usageMetadata": {
        "promptTokenCount": 180,
        "thoughtsTokenCount": 147,
        "totalTokenCount": 327,
    },
    "modelVersion": "gemini-3.7-flash",
}


# -- the regression lock ----------------------------------------------


def test_regression_against_the_real_gemini_response():
    """Locks in every field name verified live on 2026-08-22.

    If Google renames one, this fails loudly rather than quietly
    reporting `None` — the failure mode that cost Wave 06 two silently
    null fundamentals fields.
    """
    completion = _provider(_static(LIVE_COMPLETE)).complete(REQUEST)

    assert completion.text.startswith("Sim, voce esta superando o CDI")
    # The alias resolved server-side. The audit trail needs what
    # actually answered, never what was asked for.
    assert completion.model == "gemini-3.7-flash"
    assert completion.finish_reason == "STOP"
    assert completion.prompt_tokens == 180
    assert completion.output_tokens == 153
    assert completion.thinking_tokens == 548
    assert completion.truncated is False


def test_reasoning_tokens_are_reported_beside_the_prose_and_not_inside_it():
    """The request paid for 701 output tokens and the reader got 153.

    Summing them would misstate the answer's length; dropping the
    reasoning would misstate its cost. Both travel, separately.
    """
    completion = _provider(_static(LIVE_COMPLETE)).complete(REQUEST)

    assert completion.output_tokens == 153
    assert completion.thinking_tokens == 548
    assert completion.thinking_tokens > 3 * completion.output_tokens


# -- the defect the live calls found ----------------------------------


def test_a_truncated_answer_is_flagged_rather_than_passed_off_as_complete():
    """`MAX_TOKENS` is truncation, not completion (ADR-033).

    This is the regression that matters: with `MAX_TOKENS` treated as a
    normal finish, the fragment below was returned as an ordinary
    `Completion` and rendered to the reader as a finished explanation.
    """
    completion = _provider(_static(LIVE_TRUNCATED)).complete(REQUEST)

    assert completion.truncated is True
    assert completion.finish_reason == "MAX_TOKENS"
    # The text is kept: it is correct as far as it goes, and discarding
    # it would also spend one of 20 daily free-tier calls for nothing.
    assert completion.text.endswith("entre tres ativos:")
    assert completion.thinking_tokens == 981


def test_truncation_is_reported_and_never_silently_repaired():
    """No ellipsis, no apology appended, no sentence trimmed off.

    The text is handed over exactly as generated. Editing it would put
    words in the model's mouth that no fact backs, and trimming to the
    last full stop would hide the truncation the flag exists to expose.
    """
    completion = _provider(_static(LIVE_TRUNCATED)).complete(REQUEST)

    expected = LIVE_TRUNCATED["candidates"][0]["content"]["parts"][0]["text"]
    assert completion.text == expected


@pytest.mark.parametrize(
    "payload",
    [LIVE_STARVED_EMPTY_PART, LIVE_STARVED_NO_PARTS],
    ids=["part-without-text", "no-parts-at-all"],
)
def test_a_budget_spent_before_the_first_word_names_the_setting_to_change(payload):
    """Both observed no-text shapes raise, and say what to do about it.

    An empty `Completion` is what rule 44 forbids. The message names
    `AI_MAX_OUTPUT_TOKENS` because the fault is in a setting, and
    "returned no text" alone sends an operator hunting through the
    prompt instead.
    """
    with pytest.raises(AIResponseBlockedError) as excinfo:
        _provider(_static(payload)).complete(REQUEST)

    assert "AI_MAX_OUTPUT_TOKENS" in str(excinfo.value)
    assert "MAX_TOKENS" in str(excinfo.value)


def test_an_absent_token_count_stays_absent():
    """`candidatesTokenCount` is missing on a starved response.

    `None` means "not measured". A substituted zero would read as a
    request that produced nothing at no cost, and one of those two is a
    lie.
    """
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 180},
        "modelVersion": "gemini-3.7-flash",
    }
    completion = _provider(_static(payload)).complete(REQUEST)

    assert completion.output_tokens is None
    assert completion.thinking_tokens is None
    assert completion.prompt_tokens == 180


# -- the rest of the envelope -----------------------------------------


def test_the_request_carries_the_documented_shape():
    """Verified live: system instruction, one user turn, generation config."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["_headers"] = dict(request.headers)
        seen["_url"] = str(request.url)
        return httpx.Response(200, json=LIVE_COMPLETE)

    _provider(handler).complete(REQUEST)

    assert seen["systemInstruction"]["parts"][0]["text"] == REQUEST.system
    assert seen["contents"][0]["role"] == "user"
    assert seen["contents"][0]["parts"][0]["text"] == REQUEST.user
    assert seen["generationConfig"]["maxOutputTokens"] == 2048
    assert seen["generationConfig"]["temperature"] == pytest.approx(0.2)
    assert seen["_url"].endswith("/models/gemini-flash-latest:generateContent")
    # The key authenticates by header, never as `?key=` in the URL.
    assert seen["_headers"]["x-goog-api-key"] == "test-key"
    assert "key=" not in seen["_url"]


def test_a_refused_prompt_is_blocked_and_not_empty():
    payload = {"promptFeedback": {"blockReason": "SAFETY"}}

    with pytest.raises(AIResponseBlockedError, match="SAFETY"):
        _provider(_static(payload)).complete(REQUEST)


def test_no_candidates_and_no_block_reason_is_a_malformed_response():
    with pytest.raises(InvalidAIResponseError):
        _provider(_static({"modelVersion": "gemini-3.7-flash"})).complete(REQUEST)


def test_a_missing_key_fails_before_any_request_is_made():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be attempted without a key")

    provider = GeminiProvider(
        api_key="",
        base_url="https://gemini.test/v1beta",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AINotConfiguredError, match="GEMINI_API_KEY"):
        provider.complete(REQUEST)
