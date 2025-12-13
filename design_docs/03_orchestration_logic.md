# 03. Orchestration Logic

## 1. The Prefect Flow: `orchestrate_gemini_batch`

This flow is designed to be run frequently (e.g., every 5-10 minutes). It is a **State Machine**.

### Step 1: Initialization & Resume Check
*   Load configuration from YAML file (see [Configuration](./06_configuration.md)).
*   Load secrets from `.env` file (API key).
*   Fetch Prefect Variable `GEMINI_CURRENT_BATCH_ID`.

### Step 2 (Branch A): Active Batch Exists
**Condition:** `GEMINI_CURRENT_BATCH_ID` is not None.

1.  **Task: `check_batch_status`**
    *   Query Gemini Batch API using the stored batch ID.
    *   Check batch job state:
        *   **Case: `JOB_STATE_PROCESSING`:** Log "Waiting for Batch X" and Exit Flow (Wait for next schedule).
        *   **Case: `JOB_STATE_FAILED`:** Log Error, Clear `GEMINI_CURRENT_BATCH_ID`, Exit (Will retry submission next tick).
        *   **Case: `JOB_STATE_CANCELLED`:** Log Warning, Clear `GEMINI_CURRENT_BATCH_ID`, Exit.
        *   **Case: `JOB_STATE_EXPIRED`:** Log Warning, Clear `GEMINI_CURRENT_BATCH_ID`, Exit.
        *   **Case: `JOB_STATE_SUCCEEDED`:** Proceed to Result Processing.
    *   Batch job state is accessed via the batch job object's `state.name` property.

2.  **Task: `process_batch_results`**
    *   Retrieve the result file name from the completed batch job's destination configuration.
    *   Download the results JSONL file from Gemini File API.
    *   Parse the JSONL file line by line:
        *   Each line contains a JSON object with a `key` (matching the request key) and either a `response` (success) or `error` (failure).
        *   Extract the text content from successful responses.
        *   **Validation:** Parse output against Pydantic Schema.
        *   **On Success:** Write JSON to `output_results_dir`. Log Info.
        *   **On Failure:**
            *   Log Error in Prefect UI with the specific record key.
            *   Load `RECORD_FAILURE_COUNTS` variable.
            *   Increment count for this record ID.
            *   Save variable.
            *   *Do NOT write to output dir.* (This ensures retry).
    *   **Cleanup:**
        *   Clear `GEMINI_CURRENT_BATCH_ID`.
        *   Create **Prefect Artifact** (Report).

### Step 3 (Branch B): No Active Batch
**Condition:** `GEMINI_CURRENT_BATCH_ID` is None.

1.  **Task: `scan_and_build_dag`**
    *   **Input:** Configuration paths, `output_results_dir`, `RECORD_FAILURE_COUNTS`.
    *   **Logic:**
        1.  Glob all `.json` files in `label_to_curricular` directory (Filtered by Config state/year).
        2.  Group by Book (State/School/Year).
        3.  Sort Pages Numerically.
        4.  **Iterate Pages:**
            *   If exists in `output_results`: **SKIP**.
            *   If failure count > `max_retries`: **SKIP** (Dead Letter).
            *   If Page Num == Minimum in directory: **ADD** (Start of book).
            *   If `(Page Num - 1)` exists in `output_results`: **ADD** (Dependency Met).
            *   Else: **BREAK** book loop (Wait for dependency).
    *   **Output:** List of `runnable_ids` (page identifiers).

2.  **Task: `submit_new_batch`**
    *   **Input:** `runnable_ids`.
    *   **Logic:**
        *   If list is empty: Log "No work pending" and Exit.
        *   **Phase 1: Upload Images via File API**
            *   For each runnable page, upload the corresponding image file to Gemini File API.
            *   Store the returned file URI and metadata for each image.
            *   If upload fails, retry with exponential backoff (up to configured max retries).
            *   On retry, always re-upload the image (simplifies file verification - no need to check if file still exists).
        *   **Phase 2: Build Batch Request JSONL**
            *   For each runnable page:
                *   Load context from previous page JSON in `output_results` if dependency exists.
                *   Construct the prompt text (including context if available).
                *   Build a request object with:
                    *   `key`: Unique identifier for this record (e.g., `"{state}:{school}:{year}:{page}"`)
                    *   `request`: Contains `contents` array with:
                        *   Text part: The prompt
                        *   File data part: Reference to the uploaded image file URI
            *   Write all requests to a JSONL file (one JSON object per line).
        *   **Phase 3: Upload JSONL File**
            *   Upload the JSONL file containing batch requests to Gemini File API.
            *   Store the returned file name/URI.
        *   **Phase 4: Create Batch Job**
            *   Submit batch job to Gemini Batch API:
                *   Specify the model name (from configuration).
                *   Reference the uploaded JSONL file as the input source.
                *   Optionally set display name and other metadata.
            *   Store the returned batch job ID/name.
        *   **Save Batch ID** to `GEMINI_CURRENT_BATCH_ID` Prefect Variable.

## 2. Retry Logic & Error Handling

### File Upload Retry Strategy
When uploading images to File API:
*   If upload fails (network error, timeout, etc.), retry with exponential backoff.
*   Maximum retries configured in settings.
*   On retry, always re-upload the image file (no need to verify if previously uploaded file still exists).
*   This simplifies file lifecycle management - we don't need to track file expiration or verify file validity.

### Batch-Level Failure (System Crash)
If the Python script/Prefect agent crashes while a batch is submitted:
1.  **Recovery:** Next time the flow runs, it reads `GEMINI_CURRENT_BATCH_ID`.
2.  **Action:** It queries Gemini Batch API. If batch state is `JOB_STATE_SUCCEEDED`, we process results. We do not lose track of the batch.

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