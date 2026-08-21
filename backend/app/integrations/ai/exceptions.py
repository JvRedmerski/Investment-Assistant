class AIError(Exception):
    """Base class for all AI integration failures."""


class AINotConfiguredError(AIError):
    """No AI provider is usable: none selected, or its credential is absent.

    Distinct from `AIUnavailableError` because retrying cannot fix it and
    the operator action differs — this one means "set a key", not "the
    service is down".
    """


class AIUnavailableError(AIError):
    """The provider could not be reached, or kept failing, after retries."""


class InvalidAIResponseError(AIError):
    """The provider responded, but its payload could not be parsed/validated."""


class AIResponseBlockedError(AIError):
    """The provider accepted the request and deliberately returned no text.

    A safety filter, a recitation block, or a refusal. Kept apart from
    `InvalidAIResponseError` because nothing is malformed: the API did
    exactly what it promises. It matters that this never degrades into an
    empty string, which would surface to the user as an explanation that
    silently explains nothing (AGENTS.md rule 44).
    """
