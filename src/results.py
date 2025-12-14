from __future__ import annotations

import json
import traceback
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
    error_type: str | None = None
    raw_response_text: str | None = None
    extracted_text: str | None = None
    raw_response_json: str | None = None
    error_traceback: str | None = None


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

    for idx, raw_line in enumerate(
        jsonl_bytes.decode("utf-8", errors="replace").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            outcomes.append(
                RecordOutcome(
                    key=f"<invalid-json-line-{idx}>",
                    success=False,
                    error=f"Invalid JSON on line {idx}: {exc}",
                    output_path=None,
                    error_type="JSONDecodeError",
                    error_traceback=traceback.format_exc(),
                )
            )
            continue

        key = record.get("key")
        if not isinstance(key, str):
            outcomes.append(
                RecordOutcome(
                    key=f"<missing-key-line-{idx}>",
                    success=False,
                    error="Missing or invalid record key",
                    output_path=None,
                    error_type="ValueError",
                )
            )
            continue

        if "error" in record:
            outcomes.append(
                RecordOutcome(
                    key=key,
                    success=False,
                    error=str(record.get("error")),
                    output_path=None,
                    error_type="APIError",
                    raw_response_json=json.dumps(record, ensure_ascii=False),
                )
            )
            continue

        response = record.get("response")
        if not isinstance(response, dict):
            outcomes.append(
                RecordOutcome(
                    key=key,
                    success=False,
                    error="Missing response",
                    output_path=None,
                    error_type="MissingResponse",
                    raw_response_json=json.dumps(record, ensure_ascii=False),
                )
            )
            continue

        # Store raw response JSON for failure analysis
        raw_response_json = json.dumps(response, ensure_ascii=False)

        try:
            extracted_text = extract_text_from_response(response)
            payload = parse_json_from_text(extracted_text)
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
        except ValueError as exc:
            # ValueError from extract_text_from_response or parse_json_from_text
            error_type = type(exc).__name__
            outcomes.append(
                RecordOutcome(
                    key=key,
                    success=False,
                    error=str(exc),
                    output_path=None,
                    error_type=error_type,
                    raw_response_text=None,  # Failed before extraction
                    extracted_text=None,
                    raw_response_json=raw_response_json,
                    error_traceback=traceback.format_exc(),
                )
            )
        except json.JSONDecodeError as exc:
            # JSONDecodeError from parse_json_from_text
            try:
                extracted_text = extract_text_from_response(response)
            except Exception:
                extracted_text = None

            outcomes.append(
                RecordOutcome(
                    key=key,
                    success=False,
                    error=str(exc),
                    output_path=None,
                    error_type="JSONDecodeError",
                    raw_response_text=extracted_text,
                    extracted_text=extracted_text,
                    raw_response_json=raw_response_json,
                    error_traceback=traceback.format_exc(),
                )
            )
        except ValidationError as exc:
            # ValidationError from model_validate
            try:
                extracted_text = extract_text_from_response(response)
                payload = parse_json_from_text(extracted_text)
            except Exception:
                extracted_text = None
                payload = None

            outcomes.append(
                RecordOutcome(
                    key=key,
                    success=False,
                    error=str(exc),
                    output_path=None,
                    error_type="ValidationError",
                    raw_response_text=extracted_text,
                    extracted_text=extracted_text,
                    raw_response_json=raw_response_json,
                    error_traceback=traceback.format_exc(),
                )
            )

    return outcomes, successes
