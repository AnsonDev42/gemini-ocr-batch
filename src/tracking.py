from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from braintrust import init_logger, start_span

from .models import OcrPageResult, PageId

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TrackingContext:
    batch_id: str
    page_id: PageId
    prompt: str
    previous_context: str | None
    model: str
    prompt_name: str
    prompt_template: str
    generation_config: dict | None
    attempt: int
    output: OcrPageResult | None
    error: str | None


class BatchBraintrustTracker:
    """Thin wrapper around braintrust spans that is safe in batch flows."""

    def __init__(self, project: str | None = None) -> None:
        self.project = project or os.getenv("BRAINTRUST_PROJECT_NAME")
        self._enabled = False
        self._disabled_reason: str | None = None

        if init_logger is None or start_span is None:
            self._disabled_reason = "braintrust package not available"
            return
        if not self.project:
            self._disabled_reason = "BRAINTRUST_PROJECT_NAME not set"
            return

        try:
            init_logger(project=self.project)
            self._enabled = True
        except Exception as exc:  # noqa: BLE001 - observability should not fail the run
            self._disabled_reason = f"Failed to init braintrust logger: {exc}"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def disabled_reason(self) -> str | None:
        return self._disabled_reason

    def log_record(self, ctx: TrackingContext) -> None:
        if not self._enabled:
            return

        try:
            with start_span() as span:  # type: ignore[misc] - guarded above
                span.log(
                    input={
                        "page_id": ctx.page_id.key(),
                        "prompt": ctx.prompt,
                        "previous_context": ctx.previous_context,
                        "generation_config": ctx.generation_config,
                    },
                    output=(ctx.output.model_dump(mode="json") if ctx.output else None),
                    metadata={
                        "batch_id": ctx.batch_id,
                        "state": ctx.page_id.state,
                        "school": ctx.page_id.school,
                        "year": ctx.page_id.year,
                        "page": ctx.page_id.page,
                        "model": ctx.model,
                        "prompt_name": ctx.prompt_name,
                        "prompt_template": ctx.prompt_template,
                        "error": ctx.error,
                    },
                    metrics={
                        "success": 1 if ctx.output is not None else 0,
                        "attempt": ctx.attempt,
                    },
                )
        except Exception as exc:  # noqa: BLE001 - never fail the batch on tracking issues
            logger.debug("Braintrust logging failed for %s: %s", ctx.page_id.key(), exc)
