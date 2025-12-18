from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from src.models import PageId


class ScanResult(BaseModel):
    """Result of scanning for runnable pages."""

    runnable: list[PageId]
    total_candidates: int

    model_config = {"frozen": True}


def _parse_page_id(label_root: Path, label_file: Path) -> PageId | None:
    try:
        rel = label_file.relative_to(label_root)
    except ValueError:
        return None

    parts = rel.parts
    if len(parts) != 4:
        return None

    state, school, year_str, filename = parts
    if not filename.endswith(".json"):
        return None
    try:
        year = int(year_str)
        page = int(Path(filename).stem)
    except ValueError:
        return None

    return PageId(state=state, school=school, year=year, page=page)


def scan_runnable_pages(
    *,
    label_source_dir: Path,
    output_dir: Path,
    target_states: list[str] | None,
    year_start: int | None,
    year_end: int | None,
    failure_counts: dict[str, int],
    inflight_records: set[str],
    max_retries: int,
    batch_size_limit: int,
) -> ScanResult:
    label_files = list(label_source_dir.rglob("*.json"))

    grouped: dict[tuple[str, str, int], set[int]] = defaultdict(set)
    for label_file in label_files:
        page_id = _parse_page_id(label_source_dir, label_file)
        if page_id is None:
            continue

        if target_states and page_id.state not in target_states:
            continue
        if year_start is not None and page_id.year < year_start:
            continue
        if year_end is not None and page_id.year > year_end:
            continue

        grouped[(page_id.state, page_id.school, page_id.year)].add(page_id.page)

    runnable: list[PageId] = []
    total_candidates = 0

    for (state, school, year), pages in sorted(grouped.items()):
        if not pages:
            continue

        pages_sorted = sorted(pages)
        allowed_pages = set(pages_sorted)
        for page in pages_sorted:
            total_candidates += 1
            page_id = PageId(state=state, school=school, year=year, page=page)

            if page_id.key() in inflight_records:
                continue

            if failure_counts.get(page_id.key(), 0) >= max_retries:
                continue

            if page_id.output_path(output_dir).exists():
                continue

            dependency_page = page - 1 if (page - 1) in allowed_pages else None
            if dependency_page is not None:
                dep_id = PageId(
                    state=state, school=school, year=year, page=dependency_page
                )
                if not dep_id.output_path(output_dir).exists():
                    continue

            runnable.append(page_id)
            if len(runnable) >= batch_size_limit:
                return ScanResult(runnable=runnable, total_candidates=total_candidates)

    return ScanResult(runnable=runnable, total_candidates=total_candidates)
