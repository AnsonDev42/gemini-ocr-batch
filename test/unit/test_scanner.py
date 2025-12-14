from __future__ import annotations

from pathlib import Path

from src.models import PageId
from src.scanner import scan_runnable_pages


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_scan_empty_directory(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=None,
        year_start=None,
        year_end=None,
        failure_counts={},
        inflight_records=set(),
        max_retries=3,
        batch_size_limit=100,
    )
    assert result.runnable == []


def test_scan_single_book_no_output_returns_first_page(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    for page in [1, 2, 3]:
        _touch(label_dir / "Alabama" / "School" / "1850" / f"{page}.json")

    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=None,
        year_start=None,
        year_end=None,
        failure_counts={},
        inflight_records=set(),
        max_retries=3,
        batch_size_limit=100,
    )
    assert result.runnable == [
        PageId(state="Alabama", school="School", year=1850, page=1)
    ]


def test_scan_partial_completion_returns_next_page(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    for page in [1, 2, 3]:
        _touch(label_dir / "Alabama" / "School" / "1850" / f"{page}.json")

    done = PageId(state="Alabama", school="School", year=1850, page=1)
    _touch(done.output_path(output_dir))

    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=None,
        year_start=None,
        year_end=None,
        failure_counts={},
        inflight_records=set(),
        max_retries=3,
        batch_size_limit=100,
    )
    assert result.runnable == [
        PageId(state="Alabama", school="School", year=1850, page=2)
    ]


def test_scan_gap_in_pages_allows_new_chain_start(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    for page in [1, 2, 5]:
        _touch(label_dir / "Alabama" / "School" / "1850" / f"{page}.json")

    _touch(
        PageId(state="Alabama", school="School", year=1850, page=1).output_path(
            output_dir
        )
    )
    _touch(
        PageId(state="Alabama", school="School", year=1850, page=2).output_path(
            output_dir
        )
    )

    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=None,
        year_start=None,
        year_end=None,
        failure_counts={},
        inflight_records=set(),
        max_retries=3,
        batch_size_limit=100,
    )
    assert result.runnable == [
        PageId(state="Alabama", school="School", year=1850, page=5)
    ]


def test_scan_multiple_books_returns_first_page_of_each(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    _touch(label_dir / "Alabama" / "A" / "1850" / "1.json")
    _touch(label_dir / "Alabama" / "A" / "1850" / "2.json")
    _touch(label_dir / "California" / "B" / "1851" / "1.json")
    _touch(label_dir / "California" / "B" / "1851" / "2.json")

    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=None,
        year_start=None,
        year_end=None,
        failure_counts={},
        inflight_records=set(),
        max_retries=3,
        batch_size_limit=100,
    )

    keys = {pid.key() for pid in result.runnable}
    assert keys == {"Alabama:A:1850:1", "California:B:1851:1"}


def test_scan_filters_state_and_year(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    _touch(label_dir / "Alabama" / "A" / "1850" / "1.json")
    _touch(label_dir / "California" / "B" / "1900" / "1.json")

    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=["Alabama"],
        year_start=1849,
        year_end=1852,
        failure_counts={},
        inflight_records=set(),
        max_retries=3,
        batch_size_limit=100,
    )

    assert result.runnable == [PageId(state="Alabama", school="A", year=1850, page=1)]


def test_scan_skips_dead_letter(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    _touch(label_dir / "Alabama" / "A" / "1850" / "1.json")

    page = PageId(state="Alabama", school="A", year=1850, page=1)
    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=None,
        year_start=None,
        year_end=None,
        failure_counts={page.key(): 3},
        inflight_records=set(),
        max_retries=3,
        batch_size_limit=100,
    )
    assert result.runnable == []


def test_scan_skips_inflight(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "out"
    label_dir.mkdir()
    output_dir.mkdir()

    page = PageId(state="Alabama", school="A", year=1850, page=1)
    _touch(page.label_path(label_dir))

    result = scan_runnable_pages(
        label_source_dir=label_dir,
        output_dir=output_dir,
        target_states=None,
        year_start=None,
        year_end=None,
        failure_counts={},
        inflight_records={page.key()},
        max_retries=3,
        batch_size_limit=100,
    )
    assert result.runnable == []
