from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.file_api import upload_file_with_retries


@dataclass
class _Uploaded:
    name: str
    uri: str
    mime_type: str | None = None


class _Files:
    def __init__(self, effects: list[object]) -> None:
        self._effects = effects

    def upload(self, *, file: str, config=None):  # noqa: ANN001
        effect = self._effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _Client:
    def __init__(self, effects: list[object]) -> None:
        self.files = _Files(effects)


def test_upload_file_with_retries_retries_then_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_text("hi", encoding="utf-8")

    client = _Client(
        [RuntimeError("fail"), _Uploaded(name="n", uri="u", mime_type="text/plain")]
    )
    uploaded = upload_file_with_retries(
        client=client,
        path=path,
        display_name=None,
        mime_type=None,
        attempts=2,
        backoff_seconds=0.0,
    )
    assert uploaded.uri == "u"


def test_upload_file_with_retries_missing_file_raises(tmp_path: Path) -> None:
    client = _Client([])
    with pytest.raises(FileNotFoundError):
        upload_file_with_retries(
            client=client,
            path=tmp_path / "missing.txt",
            display_name=None,
            mime_type=None,
            attempts=1,
            backoff_seconds=0.0,
        )
