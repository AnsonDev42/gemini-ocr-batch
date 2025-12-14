# 03. Orchestration Logic

## 1. The Prefect Flow: `orchestrate_gemini_batch`

This flow is designed to be run frequently (e.g., every 5-10 minutes). It is a **State Machine** and supports multiple concurrent batches.

### Step 1: Initialization
*   Load configuration from YAML file (see [Configuration](./06_configuration.md)).
*   Load secrets from `.env` file (API key).
*   Read Prefect Variables:
    *   `active_batch_ids` (list)
    *   `batch_record_keys` (mapping batch -> record keys)
    *   `inflight_record_ids` (set of record keys already scheduled)
    *   `record_failure_counts`

### Step 2: Service Active Batches
For each `active_batch_id`:
1.  **Task: `wait_for_batch_completion`**
    *   Poll Gemini Batch API until a terminal state or timeout.
    *   Accepts and handles states including `JOB_STATE_PARTIALLY_SUCCEEDED`.
2.  **Task: `process_batch_results` (when terminal success/partial)**
    *   Download the results JSONL file from Gemini File API.
    *   Parse the JSONL file line by line:
        *   Each line contains a JSON object with a `key` (matching the request key) and either a `response` (success) or `error` (failure).
        *   Extract the text content from successful responses.
        *   **Validation:** Parse output against Pydantic Schema.
        *   **On Success:** Write JSON to `output_results_dir`. Log Info.
        *   **On Failure:** Increment `record_failure_counts` and skip writing (so it re-queues on the next scan).
    *   **Cleanup:** Remove the batch ID from `active_batch_ids`, delete its entry in `batch_record_keys`, and remove its record keys from `inflight_record_ids`.
3.  **If terminal failure/cancel/expire:** Remove the batch ID and inflight record keys so the scanner can re-queue them.
4.  **If still running/pending after timeout:** Leave the batch ID in `active_batch_ids` (will be picked up next run).

### Step 3: Submit New Batches (Fill Available Slots)
1.  Determine available slots: `max_concurrent_batches - len(active_batch_ids)`.
2.  Loop while slots remain:
    *   **Task: `scan_and_build_dag`**
        *   Input: configuration paths, `output_results_dir`, `record_failure_counts`, and `inflight_record_ids`.
        *   Logic:
            *   Glob `.json` files in `label_to_curricular` (filtered by config state/year).
            *   Group by Book (State/School/Year), sort pages.
            *   For each page:
                *   Skip if already in `output_results`.
                *   Skip if failure count > `max_retries`.
                *   Skip if page key is in `inflight_record_ids` (already scheduled).
                *   Dependency rule: page can run if it is the first in the book OR previous page exists in `output_results`.
            *   Output limited to `batch_size_limit`.
    *   **Task: `submit_new_batch`**
        *   Upload images to File API (with retries/backoff).
        *   Build JSONL payload with prompt and file references.
        *   Upload JSONL, create a Gemini Batch job.
        *   Return `{batch_id, record_keys}`.
    *   Add the new batch ID to `active_batch_ids`, map `batch_record_keys[batch_id] = record_keys`, and add `record_keys` to `inflight_record_ids`.
    *   Decrement available slots and repeat.

## 2. Retry Logic & Error Handling

### File Upload Retry Strategy
When uploading images to File API:
*   If upload fails (network error, timeout, etc.), retry with exponential backoff.
*   Maximum retries configured in settings.
*   On retry, always re-upload the image file (no need to verify if previously uploaded file still exists).
*   This simplifies file lifecycle management - we don't need to track file expiration or verify file validity.

### Batch-Level Failure (System Crash)
If the Python script/Prefect agent crashes while batches are submitted:
1.  **Recovery:** Next time the flow runs, it reads `active_batch_ids`.
2.  **Action:** It queries each batch in `active_batch_ids`. If a batch state is terminal, it processes results (if available) and removes it from state. We do not lose track of batches.

### Record-Level Failure (Bad Output)
If Gemini returns invalid JSON for a specific page:
1.  **Processing:** The validation fails. We do not write the file.
2.  **Marking:** We increment `RECORD_FAILURE_COUNTS` in Prefect.
3.  **Retrying:** In the next `scan_and_build_dag`, the file is missing from output, so it is a candidate. The scanner checks the failure count. If `< Max`, it is included in the new batch.
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
