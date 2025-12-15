from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.file_api import UploadedFile
from src.models import OcrPageResult, PageId, format_previous_context
from src.prompting import PromptTemplate


class BatchRecord(BaseModel):
    """A single record in a batch request JSONL file."""

    key: str
    request: dict[str, Any]

    model_config = {"frozen": True}


def build_request(
    *,
    page_id: PageId,
    image: UploadedFile,
    prompt: str,
    generation_config: dict | None,
) -> BatchRecord:
    contents = [
        {
            "parts": [
                {"text": prompt},
                {"file_data": {"file_uri": image.uri, "mime_type": image.mime_type}},
            ]
        }
    ]

    request: dict = {"contents": contents}
    if generation_config:
        request["generation_config"] = generation_config

    return BatchRecord(key=page_id.key(), request=request)


def write_jsonl(records: list[BatchRecord], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(
                json.dumps(
                    {"key": record.key, "request": record.request}, ensure_ascii=False
                )
            )
            f.write("\n")


def load_previous_result(output_path: Path) -> OcrPageResult:
    raw = json.loads(output_path.read_text(encoding="utf-8"))
    return OcrPageResult.model_validate(raw)


def build_batch_records(
    *,
    page_ids: list[PageId],
    uploaded_images: dict[PageId, UploadedFile],
    prompt_template: PromptTemplate,
    output_dir: Path,
    generation_config: dict | None,
    label_source_dir: Path,
) -> list[BatchRecord]:
    allowed_pages_by_book: dict[tuple[str, str, int], set[int]] = {}
    for page_id in page_ids:
        book = (page_id.state, page_id.school, page_id.year)
        allowed_pages_by_book.setdefault(book, set())

    for book in allowed_pages_by_book:
        state, school, year = book
        pages: set[int] = set()
        for path in (label_source_dir / state / school / str(year)).glob("*.json"):
            try:
                pages.add(int(path.stem))
            except ValueError:
                continue
        allowed_pages_by_book[book] = pages

    records: list[BatchRecord] = []
    for page_id in page_ids:
        image = uploaded_images[page_id]

        book = (page_id.state, page_id.school, page_id.year)
        allowed_pages = allowed_pages_by_book.get(book, set())
        dependency_page = (
            page_id.page - 1 if (page_id.page - 1) in allowed_pages else None
        )

        previous_context: str | None = None
        if dependency_page is not None:
            dep_id = PageId(
                state=page_id.state,
                school=page_id.school,
                year=page_id.year,
                page=dependency_page,
            )
            dep_output = dep_id.output_path(output_dir)
            if dep_output.exists():
                previous_result = load_previous_result(dep_output)
                previous_context = format_previous_context(previous_result)

        prompt = prompt_template.render(previous_context=previous_context)
        records.append(
            build_request(
                page_id=page_id,
                image=image,
                prompt=prompt,
                generation_config=generation_config,
            )
        )

    return records
