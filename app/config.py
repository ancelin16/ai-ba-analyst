"""Application settings loaded from environment variables.

API keys are read only from the environment (or a local .env file) and are
never hard-coded or written to logs.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Input limits (characters). Kept here so the UI, validation and tests agree.
MAX_REQUEST_CHARS = 6000
MIN_REQUEST_WORDS = 5
MAX_OPTIONAL_FIELD_CHARS = 1000
MAX_PROJECT_NAME_CHARS = 100


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    model: str
    max_output_tokens: int
    database_path: Path
    demo_mode: bool

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return (
            f"Settings(model={self.model!r}, has_api_key={self.has_api_key}, "
            f"demo_mode={self.demo_mode}, database_path={str(self.database_path)!r})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    db_path = Path(os.getenv("DATABASE_PATH", "data/analyses.db"))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        model=os.getenv("CLAUDE_MODEL", "claude-opus-5"),
        max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "16000")),
        database_path=db_path,
        demo_mode=_as_bool(os.getenv("DEMO_MODE")),
    )
