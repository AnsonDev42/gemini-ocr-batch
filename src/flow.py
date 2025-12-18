from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact
from prefect.cache_policies import NO_CACHE

from src.batch_api import (
    create_batch_job,
    download_result_file,
    wait_for_batch_completion,
)
from src.enums import BatchJobState
from src.batch_builder import build_batch_records, load_previous_result, write_jsonl
from src.config import AppConfig
from src.env import get_gemini_api_key
from src.file_api import (
    guess_mime_type,
    upload_file_with_retries,
    upload_files_in_parallel,
)
from src.gemini_client import create_gemini_client
from src.models import PageId, format_previous_context
from src.prefect_state import SQLiteStateStore
from src.prompting import load_prompt_template
from src.results import process_results_jsonl
from src.scanner import scan_runnable_pages
from src.tracking import BatchBraintrustTracker, TrackingContext


def _generation_config_dict(config: AppConfig) -> dict | None:
    if config.model.generation_config is None:
        return None
    payload = config.model.generation_config.model_dump(exclude_none=True)
    return payload or None


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "artifact"


def _render_prompt_for_tracking(
    *,
    page_id: PageId,
    prompt_template,
    label_source_dir: Path,
    output_dir: Path,
    logger,
) -> tuple[str, str | None]:
    dependency_page = page_id.page - 1
    previous_context: str | None = None

    if dependency_page > 0:
        dep_label = (
            label_source_dir
            / page_id.state
            / page_id.school
            / str(page_id.year)
            / f"{dependency_page}.json"
        )
        if dep_label.exists():
            dep_id = PageId(
                state=page_id.state,
                school=page_id.school,
                year=page_id.year,
                page=dependency_page,
            )
            dep_output = dep_id.output_path(output_dir)
            if dep_output.exists():
                try:
                    previous_result = load_previous_result(dep_output)
                    previous_context = format_previous_context(previous_result)
                except Exception as exc:  # noqa: BLE001 - observability
                    logger.debug(
                        "Failed to load previous context for %s: %s",
                        dep_id.key(),
                        exc,
                    )

    try:
        prompt = prompt_template.render(previous_context=previous_context)
    except Exception as exc:  # noqa: BLE001 - observability
        logger.debug("Failed to render prompt for %s: %s", page_id.key(), exc)
        prompt = ""
    return prompt, previous_context


@task(cache_policy=NO_CACHE, persist_result=False)
def task_process_batch_results(
    *,
    config: AppConfig,
    batch_id: str,
    store: SQLiteStateStore,
    result_file_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    logger = get_run_logger()
    generation_config = _generation_config_dict(config)
    client = create_gemini_client(get_gemini_api_key())
    blob = download_result_file(client=client.client, file_name=result_file_name)
    outcomes, successes = process_results_jsonl(jsonl_bytes=blob, output_dir=output_dir)

    initial_failure_counts = store.get_failure_counts()
    failures: dict[str, str] = {
        o.key: (o.error or "unknown error") for o in outcomes if not o.success
    }
    updated_failure_counts = (
        store.increment_failure_counts(failures) if failures else initial_failure_counts
    )

    # Log detailed failure information to database
    for outcome in outcomes:
        if not outcome.success:
            attempt_number = initial_failure_counts.get(outcome.key, 0) + 1
            try:
                store.log_failure(
                    record_key=outcome.key,
                    batch_id=batch_id,
                    attempt_number=attempt_number,
                    error_type=outcome.error_type.value if outcome.error_type else None,
                    error_message=outcome.error,
                    error_traceback=outcome.error_traceback,
                    raw_response_text=outcome.raw_response_text,
                    extracted_text=outcome.extracted_text,
                    raw_response_json=outcome.raw_response_json,
                    model_name=config.model.name,
                    prompt_name=config.prompt.name,
                    prompt_template=config.prompt.template_file,
                    generation_config=generation_config,
                )
            except Exception as exc:  # noqa: BLE001 - don't fail the task if logging fails
                logger.warning(
                    "Failed to log failure for record %s: %s", outcome.key, exc
                )

    store.remove_batch(batch_id)

    success_count = sum(1 for o in outcomes if o.success)
    failure_count = len(outcomes) - success_count

    report = [
        "# Batch Summary",
        f"- Records: {len(outcomes)}",
        f"- Success: {success_count}",
        f"- Failures: {failure_count}",
    ]
    if failures:
        report.append("")
        report.append("## Failures")
        for key, error in failures.items():
            retry = updated_failure_counts.get(key, 0)
            report.append(f"- `{key}` (retry {retry}): {error}")

    rows = []
    for outcome in outcomes:
        try:
            pid = PageId.from_key(outcome.key)
        except ValueError:
            pid = None
        row: dict[str, Any] = {
            "batch_id": batch_id,
            "record_key": outcome.key,
            "status": "success" if outcome.success else "failure",
            "error": outcome.error or "",
        }
        if pid:
            row.update(
                {
                    "state": pid.state,
                    "school": pid.school,
                    "year": pid.year,
                    "page": pid.page,
                }
            )
        rows.append(row)

    try:
        create_markdown_artifact(markdown="\n".join(report))
    except Exception as exc:  # noqa: BLE001 - optional observability
        logger.warning("Failed to create Prefect markdown artifact: %s", exc)

    try:
        create_table_artifact(
            key=_slug(f"batch-{batch_id}-results"),
            table=rows,
        )
    except Exception as exc:  # noqa: BLE001 - optional observability
        logger.warning("Failed to create Prefect table artifact: %s", exc)

    tracker = BatchBraintrustTracker()
    if tracker.enabled:
        prompt_template = load_prompt_template(
            registry_dir=config.prompt.registry_dir,
            name=config.prompt.name,
            template_file=config.prompt.template_file,
        )

        for outcome in outcomes:
            try:
                pid = PageId.from_key(outcome.key)
            except ValueError:
                logger.debug(
                    "Skipping Braintrust log; invalid record key: %s", outcome.key
                )
                continue
            prompt, previous_context = _render_prompt_for_tracking(
                page_id=pid,
                prompt_template=prompt_template,
                label_source_dir=config.paths.label_source_dir,
                output_dir=output_dir,
                logger=logger,
            )
            attempt = initial_failure_counts.get(outcome.key, 0) + 1

            tracker.log_record(
                TrackingContext(
                    batch_id=batch_id,
                    page_id=pid,
                    prompt=prompt,
                    previous_context=previous_context,
                    model=config.model.name,
                    prompt_name=config.prompt.name,
                    prompt_template=config.prompt.template_file,
                    generation_config=generation_config,
                    attempt=attempt,
                    output=successes.get(outcome.key),
                    error=outcome.error,
                    raw_response_json=outcome.raw_response_json,
                    raw_response_text=outcome.raw_response_text,
                )
            )
    elif tracker.disabled_reason:
        logger.info("Braintrust tracker disabled: %s", tracker.disabled_reason)

    logger.info(
        "Processed batch results: %s success, %s failure", success_count, failure_count
    )
    return {"success": success_count, "failure": failure_count}


@task(cache_policy=NO_CACHE, persist_result=False)
def task_scan_for_work(config: AppConfig, store: SQLiteStateStore) -> list[PageId]:
    logger = get_run_logger()
    failure_counts = store.get_failure_counts()
    inflight_records = store.get_inflight_records()
    year_start = (
        config.filters.target_years.start if config.filters.target_years else None
    )
    year_end = config.filters.target_years.end if config.filters.target_years else None

    result = scan_runnable_pages(
        label_source_dir=config.paths.label_source_dir,
        output_dir=config.paths.output_dir,
        target_states=config.filters.target_states,
        year_start=year_start,
        year_end=year_end,
        failure_counts=failure_counts,
        inflight_records=inflight_records,
        max_retries=config.execution.max_retries,
        batch_size_limit=config.execution.batch_size_limit,
    )
    logger.info(
        "Scan found %s runnable pages (%s candidates)",
        len(result.runnable),
        result.total_candidates,
    )
    return result.runnable


@task(cache_policy=NO_CACHE, persist_result=False)
def task_submit_new_batch(
    *,
    config: AppConfig,
    page_ids: list[PageId],
) -> dict[str, Any] | None:
    logger = get_run_logger()
    if not page_ids:
        logger.info("No work pending")
        return None

    if config.execution.dry_run:
        logger.warning("Dry run enabled: skipping remote Gemini calls")
        return None

    client = create_gemini_client(get_gemini_api_key())
    image_paths = [pid.image_path(config.paths.image_source_dir) for pid in page_ids]

    def worker(path: Path):
        return upload_file_with_retries(
            client=client.client,
            path=path,
            display_name=path.name,
            mime_type=guess_mime_type(path),
            attempts=config.files.upload_retry_attempts,
            backoff_seconds=config.files.upload_retry_backoff_seconds,
        )

    uploaded_by_path, upload_failures = upload_files_in_parallel(
        worker=worker,
        paths=image_paths,
        concurrency=config.files.upload_concurrency,
    )

    if upload_failures:
        # Convert Path keys to strings for JSON serialization
        serializable_failures = {
            str(path): error for path, error in upload_failures.items()
        }
        logger.warning(
            "Image upload failures: %s",
            json.dumps(serializable_failures, ensure_ascii=False),
        )

    uploaded_images = {
        pid: uploaded_by_path[pid.image_path(config.paths.image_source_dir)]
        for pid in page_ids
        if pid.image_path(config.paths.image_source_dir) in uploaded_by_path
    }
    ready_pages = [pid for pid in page_ids if pid in uploaded_images]

    if not ready_pages:
        logger.warning("No pages ready after upload failures")
        return None

    prompt_template = load_prompt_template(
        registry_dir=config.prompt.registry_dir,
        name=config.prompt.name,
        template_file=config.prompt.template_file,
    )

    records = build_batch_records(
        page_ids=ready_pages,
        uploaded_images=uploaded_images,
        prompt_template=prompt_template,
        output_dir=config.paths.output_dir,
        generation_config=_generation_config_dict(config),
        label_source_dir=config.paths.label_source_dir,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "batch_requests.jsonl"
        write_jsonl(records, jsonl_path)

        uploaded_jsonl = upload_file_with_retries(
            client=client.client,
            path=jsonl_path,
            display_name=f"{config.batch.display_name_prefix}-requests",
            mime_type="jsonl",
            attempts=config.files.upload_retry_attempts,
            backoff_seconds=config.files.upload_retry_backoff_seconds,
        )

    display_name = f"{config.batch.display_name_prefix}-{len(records)}"
    batch_id = create_batch_job(
        client=client.client,
        model=config.model.name,
        src_file_name=uploaded_jsonl.name,
        display_name=display_name,
    )

    logger.info("Submitted batch %s (%s records)", batch_id, len(records))

    submission_rows = []
    for pid in ready_pages:
        submission_rows.append(
            {
                "batch_id": batch_id,
                "record_key": pid.key(),
                "state": pid.state,
                "school": pid.school,
                "year": pid.year,
                "page": pid.page,
                "prompt_name": config.prompt.name,
                "prompt_template": config.prompt.template_file,
                "model": config.model.name,
            }
        )
    try:
        create_table_artifact(
            key=_slug(f"batch-{batch_id}-submitted"),
            table=submission_rows,
        )
    except Exception as exc:  # noqa: BLE001 - optional observability
        logger.warning("Failed to create Prefect submission artifact: %s", exc)

    return {"batch_id": batch_id, "record_keys": [pid.key() for pid in ready_pages]}


@task(cache_policy=NO_CACHE, persist_result=False)
def task_wait_for_batch_completion(
    *,
    batch_id: str,
    poll_interval_seconds: int,
    max_poll_attempts: int,
) -> dict[str, Any]:
    logger = get_run_logger()
    client = create_gemini_client(get_gemini_api_key())
    status = wait_for_batch_completion(
        client=client.client,
        batch_id=batch_id,
        poll_interval_seconds=poll_interval_seconds,
        max_poll_attempts=max_poll_attempts,
    )
    logger.info("Batch %s reached state %s", batch_id, status.state.value)
    return {
        "active": True,
        "batch_id": batch_id,
        "state": status.state,
        "result_file_name": status.result_file_name,
    }


@flow(name="orchestrate_gemini_batch")
def orchestrate_gemini_batch(*, config: AppConfig) -> None:
    logger = get_run_logger()
    store = SQLiteStateStore()

    while True:
        made_progress = False

        # Handle existing batches
        active_batches = store.get_active_batches()
        for batch_id in list(active_batches):
            status = task_wait_for_batch_completion(
                batch_id=batch_id,
                poll_interval_seconds=config.batch.poll_interval_seconds,
                max_poll_attempts=config.batch.max_poll_attempts,
            )
            state: BatchJobState = status.get("state")
            if state in BatchJobState.terminal_states():
                made_progress = True
                if state in BatchJobState.success_states():
                    result_file_name = status.get("result_file_name")
                    if not result_file_name:
                        logger.error(
                            "Batch %s succeeded but no result file name available",
                            batch_id,
                        )
                    else:
                        task_process_batch_results(
                            config=config,
                            batch_id=batch_id,
                            store=store,
                            result_file_name=result_file_name,
                            output_dir=config.paths.output_dir,
                        )
                else:
                    logger.warning(
                        "Batch %s ended in state %s; clearing", batch_id, state.value
                    )
                    store.remove_batch(batch_id)
            else:
                logger.info("Batch %s still in state %s", batch_id, state.value)

        # Submit new batches if slots are available
        while True:
            active_count = len(store.get_active_batches())
            available_slots = config.execution.max_concurrent_batches - active_count
            if available_slots <= 0:
                logger.info("Max concurrent batches in flight (%s)", active_count)
                break

            runnable = task_scan_for_work(config, store)
            if not runnable:
                logger.info("No runnable pages available")
                break

            submission = task_submit_new_batch(config=config, page_ids=runnable)
            if not submission:
                logger.info("Submission returned no batch id")
                break

            store.add_batch(submission["batch_id"], submission["record_keys"])
            made_progress = True
            logger.info("Active batches: %s", store.get_active_batches())

        if store.get_active_batches():
            if not made_progress:
                logger.info(
                    "Batches still running; sleeping %ss",
                    config.batch.poll_interval_seconds,
                )
                time.sleep(config.batch.poll_interval_seconds)
            continue

        if not made_progress:
            logger.info("No active batches and no runnable work; exiting")
            break
