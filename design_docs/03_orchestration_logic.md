# 03. Orchestration Logic

## 1. The Prefect Flow: `orchestrate_gemini_batch`

This flow is designed to be run frequently (e.g., every 5-10 minutes). It is a **State Machine** and supports multiple concurrent batches.

### Step 1: Initialization
*   Load configuration from YAML file (see [Configuration](./06_configuration.md)).
*   Load secrets from `.env` file (API key).
*   Initialize SQLite database connection and read state:
    *   `active_batches` table (list of active batch IDs)
    *   `batch_record_keys` table (mapping batch -> record keys)
    *   `inflight_records` table (set of record keys already scheduled)
    *   `failure_counts` table (retry counts per record)

### Step 2: Service Active Batches (poll + refill loop)
*   The flow loops until there are no active batches and no runnable work.
*   For each `active_batch_id`:
    1.  **Task: `wait_for_batch_completion`**
        *   Poll Gemini Batch API until a terminal state or timeout (includes `JOB_STATE_PARTIALLY_SUCCEEDED`).
    2.  **Task: `process_batch_results` (when terminal success/partial)**
        *   Download results JSONL, validate each record, write successes to `output_results_dir`.
        *   Increment `failure_counts` table on failures.
        *   Cleanup: remove batch from `active_batches` table, drop its `batch_record_keys`, and free its `inflight_records`.
    3.  **If terminal failure/cancel/expire:** remove the batch ID and inflight record keys so the scanner can re-queue.
    4.  **If still running/pending after timeout:** leave the batch in `active_batches` table; it will be re-polled in the next loop iteration.

### Step 3: Submit New Batches (keep slots full)
*   After servicing active batches, the flow attempts to fill available slots up to `max_concurrent_batches`.
*   Loop while slots remain:
    *   **Task: `scan_runnable_pages`**
        *   Input: configuration paths, `output_results_dir`, `failure_counts` from database, and `inflight_records` from database.
        *   Logic:
            *   Glob `.json` files in `label_to_curricular` (filtered by config state/year).
            *   Group by Book (State/School/Year), sort pages.
            *   For each page:
                *   Skip if already in `output_results`.
                *   Skip if failure count > `max_retries`.
                *   Skip if page key is in `inflight_records` (already scheduled).
                *   Dependency rule: page can run if it is the first in the book OR previous page exists in `output_results`.
            *   Output limited to `batch_size_limit`.
    *   **Task: `submit_new_batch`**
        *   Upload images to File API (with retries/backoff).
        *   Build JSONL payload with prompt and file references.
        *   Upload JSONL, create a Gemini Batch job.
        *   Return `{batch_id, record_keys}`.
    *   Add the new batch ID to `active_batches` table, insert `batch_record_keys` entries, and add `record_keys` to `inflight_records` table.
* If batches are still running but no progress was made in this pass, the flow sleeps for `batch.poll_interval_seconds` and continues polling/submitting in-process; it exits only when no active batches remain and no runnable work is found.

## 2. Retry Logic & Error Handling

### File Upload Retry Strategy
When uploading images to File API:
*   If upload fails (network error, timeout, etc.), retry with exponential backoff.
*   Maximum retries configured in settings.
*   On retry, always re-upload the image file (no need to verify if previously uploaded file still exists).
*   This simplifies file lifecycle management - we don't need to track file expiration or verify file validity.

### Batch-Level Failure (System Crash)
If the Python script/Prefect agent crashes while batches are submitted:
1.  **Recovery:** Next time the flow runs, it reads `active_batches` table from SQLite database.
2.  **Action:** It queries each batch in `active_batches`. If a batch state is terminal, it processes results (if available) and removes it from state. We do not lose track of batches.

### Record-Level Failure (Bad Output)
If Gemini returns invalid JSON for a specific page:
1.  **Processing:** The validation fails. We do not write the file.
2.  **Marking:** We increment `failure_counts` table in SQLite database.
3.  **Retrying:** In the next `scan_runnable_pages`, the file is missing from output, so it is a candidate. The scanner checks the failure count from database. If `< Max`, it is included in the new batch.
4.  **Re-upload:** When retrying, the image is re-uploaded to File API as part of the batch submission process.

## 3. Data Models

### PageIdentifier
Represents a single page to be processed:
*   `state`: State name (e.g., "Alabama")
*   `school`: School name (e.g., "Howard College")
*   `year`: Year (e.g., 1849)
*   `page`: Page number (e.g., 14)
*   `id_string`: Unique identifier string format: `"{state}:{school}:{year}:{page}"`

### BatchResult
Summary of batch processing results:
*   `batch_id`: The Gemini batch job ID/name
*   `total_records`: Total number of records in the batch
*   `successful_records`: Number of successfully processed records
*   `failed_records`: Number of failed records
*   `errors`: List of error messages for Prefect Artifacts
