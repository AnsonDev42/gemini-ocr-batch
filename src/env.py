from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


class Env(BaseModel):
    """Environment configuration."""

    gemini_api_key: str

    model_config = {"frozen": True}


def get_gemini_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment or .env")
    return api_key


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key:
            continue
        os.environ.setdefault(key, value)


def load_env(project_root: Path) -> Env:
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        message = (
            "Missing GEMINI_API_KEY. Set it in environment or create a .env file at "
            f"{dotenv_path} with GEMINI_API_KEY=..."
        )
        raise RuntimeError(message)

    return Env(gemini_api_key=api_key)
