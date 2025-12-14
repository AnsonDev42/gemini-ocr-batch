from __future__ import annotations

import json
from pathlib import Path

from src.results import (
    extract_text_from_response,
    parse_json_from_text,
    process_results_jsonl,
)


def test_extract_text_from_response_concatenates_text_parts() -> None:
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "hello "},
                        {"text": "world"},
                    ]
                }
            }
        ]
    }
    assert extract_text_from_response(response) == "hello world"


def test_parse_json_from_text_handles_code_fences() -> None:
    assert parse_json_from_text('```json\n{"a": 1}\n```') == {"a": 1}


def test_process_results_jsonl_writes_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    payload = {
        "raw_ocr": {
            "text_blocks": [
                {
                    "block_id": 1,
                    "position": "top",
                    "text": "hello",
                    "font_style": "normal",
                    "text_alignment": "left",
                }
            ],
            "layout_description": "single column",
        },
        "page_info": {
            "page_number": "1",
            "is_complete_page": True,
            "content_type": "courses",
        },
        "school_name": None,
        "catalog_year": None,
        "academic_year": None,
        "courses": [],
    }
    line_success = {
        "key": "A:B:2020:1",
        "response": {
            "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]
        },
    }
    line_error = {"key": "A:B:2020:2", "error": {"message": "bad"}}
    blob = (json.dumps(line_success) + "\n" + json.dumps(line_error) + "\n").encode(
        "utf-8"
    )

    outcomes, successes = process_results_jsonl(jsonl_bytes=blob, output_dir=output_dir)
    assert len(outcomes) == 2
    assert len(successes) == 1
    assert (output_dir / "A" / "B" / "2020" / "1.json").exists()
