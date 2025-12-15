from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from src.enums import BatchJobState


class BatchJobStatus(BaseModel):
    """Status of a batch job from Gemini API."""

    batch_id: str
    state: BatchJobState
    result_file_name: str | None = None

    model_config = {"frozen": True}


def create_batch_job(
    *, client: Any, model: str, src_file_name: str, display_name: str
) -> str:
    job = client.batches.create(
        model=model, src=src_file_name, config={"display_name": display_name}
    )
    return job.name


def get_batch_status(*, client: Any, batch_id: str) -> BatchJobStatus:
    job_info = client.batches.get(name=batch_id)
    state_str = job_info.state.name

    # Convert string to enum, handling unknown states gracefully
    try:
        state = BatchJobState(state_str)
    except ValueError:
        # If we get an unknown state, treat it as PROCESSING
        state = BatchJobState.PROCESSING

    result_file_name = None
    if state in BatchJobState.success_states():
        result_file_name = getattr(getattr(job_info, "dest", None), "file_name", None)
    return BatchJobStatus(
        batch_id=batch_id, state=state, result_file_name=result_file_name
    )


def wait_for_batch_completion(
    *,
    client: Any,
    batch_id: str,
    poll_interval_seconds: int,
    max_poll_attempts: int,
) -> BatchJobStatus:
    for _ in range(max_poll_attempts):
        status = get_batch_status(client=client, batch_id=batch_id)
        if status.state in BatchJobState.terminal_states():
            return status
        time.sleep(poll_interval_seconds)
    # Return timeout status instead of raising
    return BatchJobStatus(
        batch_id=batch_id, state=BatchJobState.TIMEOUT, result_file_name=None
    )


def download_result_file(*, client: Any, file_name: str) -> bytes:
    return client.files.download(file=file_name)
