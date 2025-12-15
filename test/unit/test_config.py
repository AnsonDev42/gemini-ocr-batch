from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import load_config


def test_load_config_creates_output_dir(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    image_dir = tmp_path / "images"
    output_dir = tmp_path / "out" / "nested"
    label_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "label_source_dir": str(label_dir),
                    "image_source_dir": str(image_dir),
                    "output_dir": str(output_dir),
                },
                "model": {"name": "gemini-2.5-flash"},
                "prompt": {"name": "page_ocr", "template_file": "v1.jinja"},
            }
        ),
        encoding="utf-8",
    )

    result = load_config(config_path)
    assert result.config.paths.output_dir.exists()
    assert result.config.model.name == "gemini-2.5-flash"


def test_load_config_invalid_yaml_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("paths: [", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Invalid YAML"):
        load_config(config_path)


def test_load_config_missing_required_field_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {},
                "model": {"name": "x"},
                "prompt": {"name": "page_ocr", "template_file": "v1.jinja"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Config validation failed"):
        load_config(config_path)


def test_load_config_invalid_path_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "label_source_dir": str(tmp_path / "missing"),
                    "image_source_dir": str(tmp_path / "images"),
                    "output_dir": str(tmp_path / "out"),
                },
                "model": {"name": "gemini-2.5-flash"},
                "prompt": {"name": "page_ocr", "template_file": "v1.jinja"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Directory does not exist"):
        load_config(config_path)


def test_load_config_invalid_year_range_raises(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    image_dir = tmp_path / "images"
    label_dir.mkdir()
    image_dir.mkdir()

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "label_source_dir": str(label_dir),
                    "image_source_dir": str(image_dir),
                    "output_dir": str(tmp_path / "out"),
                },
                "filters": {"target_years": {"start": 1900, "end": 1800}},
                "model": {"name": "gemini-2.5-flash"},
                "prompt": {"name": "page_ocr", "template_file": "v1.jinja"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="target_years.end"):
        load_config(config_path)
