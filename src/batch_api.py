from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


@dataclass(frozen=True, slots=True)
class BatchStatus:
    batch_id: str
    state: str
    result_file_name: str | None


def create_batch_job(
    *, client: Any, model: str, src_file_name: str, display_name: str
) -> str:
    job = client.batches.create(
        model=model, src=src_file_name, config={"display_name": display_name}
    )
    return job.name


def get_batch_status(*, client: Any, batch_id: str) -> BatchStatus:
    job_info = client.batches.get(name=batch_id)
    state = job_info.state.name
    result_file_name = None
    if state in {"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"}:
        result_file_name = getattr(getattr(job_info, "dest", None), "file_name", None)
    return BatchStatus(
        batch_id=batch_id, state=state, result_file_name=result_file_name
    )


def wait_for_batch_completion(
    *,
    client: Any,
    batch_id: str,
    poll_interval_seconds: int,
    max_poll_attempts: int,
) -> BatchStatus:
    for _ in range(max_poll_attempts):
        status = get_batch_status(client=client, batch_id=batch_id)
        if status.state in TERMINAL_STATES:
            return status
        time.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"Batch {batch_id} did not complete after {max_poll_attempts} polls"
    )


def download_result_file(*, client: Any, file_name: str) -> bytes:
    return client.files.download(file=file_name)
