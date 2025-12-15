from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class PageId(BaseModel):
    """Identifier for a single page in the dataset."""

    state: str
    school: str
    year: int
    page: int

    model_config = {"frozen": True}

    def key(self) -> str:
        """Generate a unique key string for this page ID."""
        return f"{self.state}:{self.school}:{self.year}:{self.page}"

    @classmethod
    def from_key(cls, key: str) -> "PageId":
        """Parse a PageId from a key string."""
        parts = key.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid PageId key: {key}")
        state, school, year_str, page_str = parts
        return cls(state=state, school=school, year=int(year_str), page=int(page_str))

    def output_path(self, output_root: Path) -> Path:
        """Get the output file path for this page."""
        return (
            output_root
            / self.state
            / self.school
            / str(self.year)
            / f"{self.page}.json"
        )

    def label_path(self, label_root: Path) -> Path:
        """Get the label file path for this page."""
        return (
            label_root / self.state / self.school / str(self.year) / f"{self.page}.json"
        )

    def image_path(self, image_root: Path) -> Path:
        """Get the image file path for this page."""
        return (
            image_root / self.state / self.school / str(self.year) / f"{self.page}.jpg"
        )

    def __hash__(self) -> int:
        """Make PageId hashable for use as dict keys."""
        return hash((self.state, self.school, self.year, self.page))


class TextBlock(BaseModel):
    block_id: int
    position: str
    text: str
    font_style: str


class RawOcr(BaseModel):
    text_blocks: list[TextBlock]
    layout_description: str


class PageInfo(BaseModel):
    page_number: str | None
    is_complete_page: bool
    content_type: str


class Textbook(BaseModel):
    title: str | None
    author: str | None


class Course(BaseModel):
    course_name: str | None
    department: str | None
    level: str | None
    topics: list[str] | None
    textbooks: list[Textbook]
    term: str | None
    instructors: list[str] | None
    description: str | None


class OcrPageResult(BaseModel):
    raw_ocr: RawOcr
    page_info: PageInfo
    school_name: str | None
    catalog_year: str | None
    academic_year: str | None
    courses: list[Course]


def extract_last_ocr_chars(result: OcrPageResult, limit: int = 500) -> str:
    combined = "\n".join(
        block.text for block in result.raw_ocr.text_blocks if block.text
    )
    if len(combined) <= limit:
        return combined
    return combined[-limit:]


def format_previous_context(result: OcrPageResult) -> str:
    last_text = extract_last_ocr_chars(result, limit=500)
    last_courses = result.courses[-3:] if result.courses else []

    lines: list[str] = []
    if last_text:
        lines.append("LAST_500_CHARS:")
        lines.append(last_text)

    lines.append("")
    lines.append("LAST_3_COURSES:")
    if not last_courses:
        lines.append("(none)")
    else:
        for idx, course in enumerate(last_courses, start=1):
            lines.append(
                f"{idx}. {course.course_name} (department={course.department}, "
                f"level={course.level}, term={course.term})"
            )

    return "\n".join(lines).strip()
