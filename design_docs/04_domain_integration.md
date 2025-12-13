# 04. Implementation Plan

## Phase 1: Setup & Configuration
1.  Define `pydantic_models.py` (Config, PageID, Schema).
2.  Set up Prefect profile and ensure SQLite/Postgres is running.
3.  Create helper functions to read/write Prefect Variables (`get_variable`, `set_variable`).

## Phase 2: The Scanner (Local Logic)
1.  Implement `scan_directory` function using `pathlib`.
2.  Implement the DAG logic (group by book -> sort -> check dependency).
3.  Unit test the scanner:
    *   Case: Book with pages 1, 2, 3. No output. -> Returns [1].
    *   Case: Book with pages 1, 2, 3. Output has 1. -> Returns [2].
    *   Case: Output has 1. Page 2 failed 5 times. -> Returns [].

## Phase 3: Gemini Integration (Remote Logic)
1.  Implement `submit_batch_job` (Upload file, Create job).
2.  Implement `check_job_status`.
3.  Implement `download_results`.

## Phase 4: The Prefect Flow
1.  Combine Scanner and Gemini logic into the `@flow`.
2.  Add `@task` decorators with retries (for network calls).
3.  Implement the Artifact generation logic for the UI.

## Phase 5: Testing & Deployment
1.  Run with `dry_run=True` (mocking Gemini) to verify DAG logic in Prefect UI.
2.  Run with small subset (1 book).
3.  Deploy scheduler (Cron: `*/10 * * * *`).