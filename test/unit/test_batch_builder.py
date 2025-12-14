from __future__ import annotations

import json
from pathlib import Path

from src.batch_builder import build_batch_records, build_request, write_jsonl
from src.file_api import UploadedFile
from src.models import PageId
from src.prompting import load_prompt_template


def _touch(path: Path, content: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_request_structure() -> None:
    page = PageId(state="A", school="B", year=2020, page=1)
    uploaded = UploadedFile(name="n", uri="u", mime_type="image/jpeg")
    record = build_request(
        page_id=page,
        image=uploaded,
        prompt="hello",
        generation_config={"temperature": 0.1},
    )

    assert record.key == "A:B:2020:1"
    parts = record.request["contents"][0]["parts"]
    assert parts[0]["text"] == "hello"
    assert parts[1]["file_data"]["file_uri"] == "u"
    assert record.request["generation_config"]["temperature"] == 0.1


def test_write_jsonl_writes_one_object_per_line(tmp_path: Path) -> None:
    page = PageId(state="A", school="B", year=2020, page=1)
    uploaded = UploadedFile(name="n", uri="u", mime_type="image/jpeg")
    records = [
        build_request(
            page_id=page, image=uploaded, prompt="hello", generation_config=None
        )
    ]

    path = tmp_path / "out.jsonl"
    write_jsonl(records, path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["key"] == "A:B:2020:1"
    assert "request" in payload


def test_build_batch_records_injects_previous_context(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    registry_dir = tmp_path / "prompts"
    output_dir.mkdir()

    _touch(label_dir / "A" / "B" / "2020" / "1.json")
    _touch(label_dir / "A" / "B" / "2020" / "2.json")

    previous_page = PageId(state="A", school="B", year=2020, page=1)
    previous_payload = {
        "raw_ocr": {
            "text_blocks": [
                {
                    "block_id": 1,
                    "position": "top",
                    "text": "hello world",
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
    _touch(previous_page.output_path(output_dir), json.dumps(previous_payload))

    template_dir = registry_dir / "page_ocr"
    template_dir.mkdir(parents=True)
    (template_dir / "t.jinja").write_text(
        "PREV={{ previous_context or 'NONE' }}", encoding="utf-8"
    )
    template = load_prompt_template(
        registry_dir=registry_dir, name="page_ocr", template_file="t.jinja"
    )

    page1 = previous_page
    page2 = PageId(state="A", school="B", year=2020, page=2)
    uploaded_images = {
        page1: UploadedFile(name="n1", uri="u1", mime_type="image/jpeg"),
        page2: UploadedFile(name="n2", uri="u2", mime_type="image/jpeg"),
    }

    records = build_batch_records(
        page_ids=[page1, page2],
        uploaded_images=uploaded_images,
        prompt_template=template,
        output_dir=output_dir,
        generation_config=None,
        label_source_dir=label_dir,
    )

    prompt1 = records[0].request["contents"][0]["parts"][0]["text"]
    prompt2 = records[1].request["contents"][0]["parts"][0]["text"]
    assert prompt1 == "PREV=NONE"
    assert "LAST_500_CHARS:" in prompt2
