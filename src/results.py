from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import OcrPageResult, PageId


@dataclass(frozen=True, slots=True)
class RecordOutcome:
    key: str
    success: bool
    error: str | None
    output_path: Path | None


def extract_text_from_response(response: dict[str, Any]) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        raise ValueError("No candidates in response")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts = [
        part.get("text") for part in parts if isinstance(part, dict) and "text" in part
    ]
    text = "".join(texts).strip()
    if not text:
        raise ValueError("Empty text in response parts")
    return text


def parse_json_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if (
            len(lines) >= 3
            and lines[0].startswith("```")
            and lines[-1].startswith("```")
        ):
            stripped = "\n".join(lines[1:-1]).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        initial_error = exc

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output") from initial_error
    candidate = stripped[start : end + 1]
    return json.loads(candidate)


def process_results_jsonl(
    *,
    jsonl_bytes: bytes,
    output_dir: Path,
) -> tuple[list[RecordOutcome], dict[str, OcrPageResult]]:
    outcomes: list[RecordOutcome] = []
    successes: dict[str, OcrPageResult] = {}

    for raw_line in jsonl_bytes.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        record = json.loads(line)
        key = record.get("key")
        if not isinstance(key, str):
            continue

        if "error" in record:
            outcomes.append(
                RecordOutcome(
                    key=key,
                    success=False,
                    error=str(record.get("error")),
                    output_path=None,
                )
            )
            continue

        response = record.get("response")
        if not isinstance(response, dict):
            outcomes.append(
                RecordOutcome(
                    key=key, success=False, error="Missing response", output_path=None
                )
            )
            continue

        try:
            text = extract_text_from_response(response)
            payload = parse_json_from_text(text)
            validated = OcrPageResult.model_validate(payload)
            page_id = PageId.from_key(key)
            out_path = page_id.output_path(output_dir)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(
                    validated.model_dump(mode="json"), ensure_ascii=False, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
            outcomes.append(
                RecordOutcome(key=key, success=True, error=None, output_path=out_path)
            )
            successes[key] = validated
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            outcomes.append(
                RecordOutcome(key=key, success=False, error=str(exc), output_path=None)
            )

    return outcomes, successes
