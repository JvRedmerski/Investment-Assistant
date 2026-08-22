"""Application logging, and the guarantee that a credential never reaches it.

## The defect this exists to prevent

`basicConfig(level=INFO)` configures the **root** logger, so every
third-party library that logs at INFO logs through this application's
handler. `httpx` does, and what it logs is the full request URL:

    httpx INFO HTTP Request: GET https://brapi.dev/api/quote/PETR4
    ?token=<the real token>&range=3mo&interval=15m "HTTP/1.1 200 OK"

Brapi authenticates by **query parameter**, so the token is in that URL.
It had been printed in clear text on every market data, fundamentals and
CNPJ-resolution call since Wave 05. `RetryingJsonClient` already warned
about exactly this hazard in its own docstring — "a credential in a URL
leaks into logs and proxies" — and the warning was about the case that
was live.

## Why redaction rather than silencing httpx

Setting `httpx` to WARNING would also close the leak, and would throw
away a genuinely useful line: which URL was called and what it answered.
Redaction keeps the line and removes the secret from it, so the log
reads `?token=[REDACTED]`.

It is also the broader fix. Silencing one library protects against that
library; redacting at format time protects against **any** record that
happens to carry a configured secret — a future integration, an
exception message that embeds a URL, a traceback. It runs on the fully
rendered string, which is what makes tracebacks covered too.

## The boundary of the guarantee

This redacts records formatted by the handler installed here. Records
that reach a handler this module did not install are not covered — under
uvicorn that means `uvicorn.access`, which logs *inbound* requests to
this API and never an outbound provider URL. The channel that actually
leaked (`httpx`, which has no handler of its own and propagates to root)
is covered.
"""

import logging
import sys
from collections.abc import Iterable

from app.core.config import settings

REDACTION_MARKER = "[REDACTED]"

#: Values shorter than this are never redacted.
#:
#: A guard, not a tuning knob. Redaction is a blind string replacement,
#: so an empty or one-character value — an unset `BRAPI_TOKEN`, a `.env`
#: left at a placeholder — would turn every log line into confetti and
#: hide the very messages someone is reading to debug the unset value.
#: Real credentials are far longer: the Brapi token in use is 22
#: characters, a Gemini API key is 39.
MIN_REDACTABLE_LENGTH = 8

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def configured_secrets() -> tuple[str, ...]:
    """The secrets that can plausibly reach a log line.

    Read at format time rather than captured at startup, so a test (or a
    reload) that changes a setting is honoured rather than silently
    ignored.

    `GEMINI_API_KEY` is listed even though `GeminiProvider` sends it as
    the `x-goog-api-key` **header** and headers are not logged: listing
    it costs nothing and means the guarantee does not depend on that
    provider continuing to make the right choice.

    `SECRET_KEY` is deliberately absent — it signs JWTs locally and is
    never placed in a request, so it has no path into a log line.
    """
    return (settings.BRAPI_TOKEN, settings.GEMINI_API_KEY)


def redact_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of each secret in `text`.

    Pure and order-independent: secrets are disjoint credentials, not
    substrings of one another, so no replacement can create or destroy a
    match for another.
    """
    for secret in secrets:
        if secret and len(secret) >= MIN_REDACTABLE_LENGTH:
            text = text.replace(secret, REDACTION_MARKER)
    return text


class SecretRedactingFormatter(logging.Formatter):
    """A formatter that removes configured secrets from its output.

    Redacts the **rendered** string rather than `record.msg`, because
    the secret usually is not in `msg` at all: `httpx` logs
    `"HTTP Request: %s %s ..."` and puts the URL in `record.args`.
    Rendering first catches the message, every argument, and the
    traceback of an exception, in one place.

    The record itself is left untouched, so nothing here can corrupt
    what another handler sees.
    """

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record), configured_secrets())


def setup_logging() -> None:
    """Install the application's root handler, redaction included.

    `force=True` is what makes the redaction a guarantee rather than a
    hope. Without it `basicConfig` is a **no-op whenever the root logger
    already has a handler**, so anything that configured logging before
    this ran — a library at import time, a test harness — would leave the
    plain formatter in place and the token back in the clear. Measured:
    with a `basicConfig` call ahead of it, the root handler kept the
    stdlib `Formatter`.

    It removes root handlers only. Uvicorn configures `uvicorn`,
    `uvicorn.error` and `uvicorn.access` as named loggers with their own
    handlers, and those are untouched.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SecretRedactingFormatter(LOG_FORMAT))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


logger = logging.getLogger("investment_assistant")
