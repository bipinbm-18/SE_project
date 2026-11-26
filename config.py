"""Environment-backed configuration for FinSpec AI."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_file()

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "data" / "finspec.db"))
KB_PATH = Path(os.getenv("KB_PATH", BASE_DIR / "kb_docs"))
ARTIFACT_PATH = Path(os.getenv("ARTIFACT_PATH", BASE_DIR / "artifacts"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
