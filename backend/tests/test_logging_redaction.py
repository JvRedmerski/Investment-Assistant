"""A credential must never reach a log line.

The defect these lock in was real and ten waves old: `basicConfig` sets
the **root** logger, `httpx` logs the full request URL at INFO, and Brapi
authenticates by query parameter - so every market data, fundamentals and
CNPJ call printed the token in clear text.

The end-to-end test at the bottom is the one that matters. It reproduces
the exact path that leaked - a real `RetryingJsonClient` making a real
`httpx` call through the handler `setup_logging` installs - rather than
asserting that a helper function replaces a string.
"""

import io
import logging

import httpx
import pytest

from app.core.config import settings
from app.core.logging import (
    LOG_FORMAT,
    MIN_REDACTABLE_LENGTH,
    REDACTION_MARKER,
    SecretRedactingFormatter,
    configured_secrets,
    redact_secrets,
    setup_logging,
)
from app.integrations.http import RetryingJsonClient

_TOKEN = "brapi-token-abcdefghij"


@pytest.fixture
def restore_root_logging():
    """`setup_logging` owns the root handler, so a test that calls it
    must put the harness's own logging back."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers = handlers
    root.setLevel(level)


def _record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=None,
    )


class TestRedactSecrets:
    def test_a_secret_is_replaced(self):
        assert redact_secrets(f"?token={_TOKEN}&x=1", [_TOKEN]) == (
            f"?token={REDACTION_MARKER}&x=1"
        )

    def test_every_occurrence_is_replaced(self):
        text = f"{_TOKEN} and again {_TOKEN}"
        assert _TOKEN not in redact_secrets(text, [_TOKEN])

    def test_several_secrets_are_replaced(self):
        other = "gemini-key-0123456789"
        text = f"a={_TOKEN} b={other}"
        redacted = redact_secrets(text, [_TOKEN, other])
        assert _TOKEN not in redacted
        assert other not in redacted

    def test_an_empty_secret_changes_nothing(self):
        """An unset credential must not turn every line into markers."""
        text = "nothing secret here"
        assert redact_secrets(text, [""]) == text

    def test_a_short_secret_is_left_alone(self):
        """The guard, and the reason it exists: a placeholder value would
        otherwise be replaced everywhere it happened to appear."""
        short = "a" * (MIN_REDACTABLE_LENGTH - 1)
        text = f"a placeholder {short} in ordinary prose"
        assert redact_secrets(text, [short]) == text

    def test_a_secret_at_the_length_boundary_is_redacted(self):
        boundary = "b" * MIN_REDACTABLE_LENGTH
        assert boundary not in redact_secrets(f"x={boundary}", [boundary])


class TestConfiguredSecrets:
    def test_it_reads_settings_at_call_time(self, monkeypatch):
        monkeypatch.setattr(settings, "BRAPI_TOKEN", _TOKEN)
        assert _TOKEN in configured_secrets()

    def test_the_jwt_signing_key_is_not_listed(self):
        """It never leaves the process, so it has no path into a log."""
        monkey = settings.SECRET_KEY
        assert monkey not in configured_secrets()


class TestTheFormatter:
    def test_a_secret_carried_in_args_is_redacted(self, monkeypatch):
        """The actual shape of the defect: `httpx` logs
        `"HTTP Request: %s %s ..."` and puts the URL in `record.args`, so
        redacting `record.msg` alone would have caught nothing."""
        monkeypatch.setattr(settings, "BRAPI_TOKEN", _TOKEN)
        record = _record(
            "HTTP Request: %s %s",
            "GET",
            f"https://brapi.dev/api/quote/PETR4?token={_TOKEN}&range=3mo",
        )

        rendered = SecretRedactingFormatter(LOG_FORMAT).format(record)

        assert _TOKEN not in rendered
        assert REDACTION_MARKER in rendered

    def test_the_rest_of_the_line_survives(self, monkeypatch):
        """Redaction, not silence: the URL and status still get logged."""
        monkeypatch.setattr(settings, "BRAPI_TOKEN", _TOKEN)
        record = _record(
            "HTTP Request: %s %s",
            "GET",
            f"https://brapi.dev/api/quote/PETR4?token={_TOKEN}&range=3mo",
        )

        rendered = SecretRedactingFormatter(LOG_FORMAT).format(record)

        assert "brapi.dev/api/quote/PETR4" in rendered
        assert "range=3mo" in rendered

    def test_a_secret_inside_a_traceback_is_redacted(self, monkeypatch):
        """Rendering first is what makes this reachable at all."""
        monkeypatch.setattr(settings, "BRAPI_TOKEN", _TOKEN)
        try:
            raise ValueError(f"failed for ?token={_TOKEN}")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="app",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="boom",
                args=(),
                exc_info=sys.exc_info(),
            )

        assert _TOKEN not in SecretRedactingFormatter(LOG_FORMAT).format(record)

    def test_the_record_itself_is_not_mutated(self, monkeypatch):
        """Nothing here may corrupt what another handler sees."""
        monkeypatch.setattr(settings, "BRAPI_TOKEN", _TOKEN)
        url = f"https://brapi.dev/api/quote/PETR4?token={_TOKEN}"
        record = _record("HTTP Request: %s %s", "GET", url)

        SecretRedactingFormatter(LOG_FORMAT).format(record)

        assert record.args == ("GET", url)


class TestSetupLogging:
    def test_it_installs_the_redacting_formatter(self, restore_root_logging):
        setup_logging()
        assert isinstance(
            logging.getLogger().handlers[0].formatter, SecretRedactingFormatter
        )

    def test_it_wins_even_when_logging_was_already_configured(
        self, restore_root_logging
    ):
        """Without `force=True` this is where the fix silently would not
        apply: `basicConfig` is a no-op once root has a handler, so the
        plain formatter would stay and the token would be back in the
        clear. Measured before the fix."""
        logging.basicConfig(level=logging.INFO)
        setup_logging()
        assert isinstance(
            logging.getLogger().handlers[0].formatter, SecretRedactingFormatter
        )


class TestTheLeakItself:
    def test_the_token_does_not_reach_the_log_of_a_real_request(
        self, monkeypatch, restore_root_logging
    ):
        """The regression, on the exact path that leaked.

        A real `RetryingJsonClient` making a real `httpx` request with
        the token where Brapi wants it - the query string - logged
        through the handler `setup_logging` installs.
        """
        monkeypatch.setattr(settings, "BRAPI_TOKEN", _TOKEN)
        setup_logging()
        captured = io.StringIO()
        logging.getLogger().handlers[0].stream = captured

        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"results": [{"symbol": "PETR4"}]})

        client = RetryingJsonClient(
            base_url="https://brapi.dev/api",
            timeout=5.0,
            max_retries=1,
            min_request_interval=0.0,
            not_found_error=ValueError,
            unavailable_error=RuntimeError,
            invalid_response_error=TypeError,
            logger=logging.getLogger("investment_assistant.test"),
            default_params={"token": settings.BRAPI_TOKEN},
            client=httpx.Client(transport=httpx.MockTransport(respond)),
        )
        client.get_json("/quote/PETR4", params={"range": "3mo"})

        logged = captured.getvalue()
        assert "HTTP Request" in logged, "httpx should still log the request"
        assert _TOKEN not in logged
        assert REDACTION_MARKER in logged
