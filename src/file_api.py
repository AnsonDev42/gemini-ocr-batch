from __future__ import annotations

import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from google.genai import types
from pydantic import BaseModel


class UploadedFile(BaseModel):
    """Metadata for a file uploaded to Gemini File API."""

    name: str
    uri: str
    mime_type: str | None = None

    model_config = {"frozen": True}


def guess_mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.as_posix())
    return guessed or "application/octet-stream"


def upload_file_with_retries(
    *,
    client: Any,
    path: Path,
    display_name: str | None,
    mime_type: str | None,
    attempts: int,
    backoff_seconds: float,
) -> UploadedFile:
    if not path.exists():
        raise FileNotFoundError(path)

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if mime_type or display_name:
                config = types.UploadFileConfig(
                    display_name=display_name,
                    mime_type=mime_type,
                )
                uploaded = client.files.upload(file=path.as_posix(), config=config)
            else:
                uploaded = client.files.upload(file=path.as_posix())
            uploaded_mime = (
                getattr(uploaded, "mime_type", None)
                or mime_type
                or guess_mime_type(path)
            )
            return UploadedFile(
                name=uploaded.name, uri=uploaded.uri, mime_type=uploaded_mime
            )
        except Exception as exc:  # noqa: BLE001 - retry boundary
            last_exc = exc
            if attempt == attempts:
                break
            sleep_for = backoff_seconds * (2 ** (attempt - 1))
            time.sleep(sleep_for)

    assert last_exc is not None
    raise last_exc


def upload_files_in_parallel(
    *,
    worker: Callable[[Path], UploadedFile],
    paths: list[Path],
    concurrency: int,
) -> tuple[dict[Path, UploadedFile], dict[Path, str]]:
    successes: dict[Path, UploadedFile] = {}
    failures: dict[Path, str] = {}

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(worker, path): path for path in paths}
        for future in as_completed(futures):
            path = futures[future]
            try:
                successes[path] = future.result()
            except Exception as exc:  # noqa: BLE001 - boundary
                failures[path] = str(exc)

    return successes, failures
