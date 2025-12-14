from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class PathsConfig(BaseModel):
    label_source_dir: Path
    image_source_dir: Path
    output_dir: Path

    @field_validator("label_source_dir", "image_source_dir")
    @classmethod
    def _require_existing_dir(cls, value: Path) -> Path:
        if not value.exists() or not value.is_dir():
            raise ValueError(f"Directory does not exist: {value}")
        return value


class TargetYears(BaseModel):
    start: int
    end: int

    @model_validator(mode="after")
    def _validate_range(self) -> "TargetYears":
        if self.end < self.start:
            raise ValueError(
                "filters.target_years.end must be >= filters.target_years.start"
            )
        return self


class FiltersConfig(BaseModel):
    target_states: list[str] | None = None
    target_years: TargetYears | None = None


class ExecutionConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    batch_size_limit: int = Field(default=100, ge=1)
    dry_run: bool = False
    max_concurrent_batches: int = Field(default=1, ge=1)


class GenerationConfig(BaseModel):
    temperature: float | None = Field(default=None, ge=0.0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    response_mime_type: str | None = None


class ModelConfig(BaseModel):
    name: str
    generation_config: GenerationConfig | None = None


class BatchConfig(BaseModel):
    poll_interval_seconds: int = Field(default=10, ge=1)
    max_poll_attempts: int = Field(default=360, ge=1)
    display_name_prefix: str = "ocr-batch-job"


class FilesConfig(BaseModel):
    upload_retry_attempts: int = Field(default=3, ge=1)
    upload_retry_backoff_seconds: float = Field(default=2.0, ge=0.0)
    upload_concurrency: int = Field(default=4, ge=1)


class PromptConfig(BaseModel):
    registry_dir: Path = Path("prompts")
    name: str
    template_file: str


class PrefectConfig(BaseModel):
    flow_name: str = "orchestrate_gemini_batch"
    schedule_interval_minutes: int = Field(default=10, ge=1)


class AppConfig(BaseModel):
    paths: PathsConfig
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    model: ModelConfig
    batch: BatchConfig = Field(default_factory=BatchConfig)
    files: FilesConfig = Field(default_factory=FilesConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    prefect: PrefectConfig = Field(default_factory=PrefectConfig)


@dataclass(frozen=True)
class ConfigLoadResult:
    config: AppConfig
    path: Path


def load_config(config_path: Path) -> ConfigLoadResult:
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Config file not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Invalid YAML in {config_path}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"Invalid config root in {config_path}: expected mapping, got {type(raw)}"
        )

    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(
            f"Config validation failed for {config_path}:\n{exc}"
        ) from exc

    output_dir = config.paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    return ConfigLoadResult(config=config, path=config_path)


def resolve_config_path(project_root: Path, cli_path: Path | None) -> Path:
    if cli_path is not None:
        return cli_path

    env_raw = os.getenv("CONFIG_FILE_PATH")
    if env_raw:
        env_path = Path(env_raw)
        return env_path

    return project_root / "config.yaml"
