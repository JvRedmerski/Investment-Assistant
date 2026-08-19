"""Tests for settings loading.

The one behaviour worth pinning here is where `.env` is read from. A
relative `env_file` is resolved against the process working directory, so
running anything from `backend/` — pytest, alembic, a validation script —
loaded no file at all and left `BRAPI_TOKEN` empty, with no error to show
for it: requests simply went out unauthenticated.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import _PROJECT_ROOT, ENV_FILES, Settings


def test_project_root_is_the_repository_root():
    """Anchored to this file's location, not to the working directory."""
    assert (_PROJECT_ROOT / "docker-compose.yml").is_file()
    assert (_PROJECT_ROOT / "AGENTS.md").is_file()
    assert (_PROJECT_ROOT / "backend").is_dir()


def test_the_root_env_file_is_an_absolute_path():
    """An absolute path resolves the same from any cwd, which is the point."""
    root_env = ENV_FILES[0]
    assert isinstance(root_env, Path)
    assert root_env.is_absolute()
    assert root_env == _PROJECT_ROOT / ".env"


def test_a_local_env_file_still_takes_precedence():
    """Later entries win in pydantic-settings, so a per-checkout override
    keeps working — the root file is a floor, not a lock."""
    assert ENV_FILES[-1] == ".env"
    assert Settings.model_config["env_file"] == ENV_FILES


def test_values_are_read_from_a_file_outside_the_working_directory(tmp_path):
    """The mechanism itself: a file elsewhere on disk is loaded."""
    env_file = tmp_path / "elsewhere.env"
    env_file.write_text("BRAPI_TOKEN=token-from-another-directory\n", encoding="utf-8")

    class _Probe(BaseSettings):
        BRAPI_TOKEN: str = ""
        model_config = SettingsConfigDict(
            case_sensitive=True, env_file=env_file, extra="ignore"
        )

    assert _Probe().BRAPI_TOKEN == "token-from-another-directory"
