# 05. Operations, Failure Handling & Observability

## 1. Failure Modes & Strategy

| Failure Type | Description | System Response | Operational Action |
| :--- | :--- | :--- | :--- |
| **Network / 5xx** | Transient HTTP error during submission or polling. | **Prefect Task Retry.** The specific task retries automatically (e.g., 3 times). | None. |
| **File Upload Failure** | Image file upload to File API fails (network, timeout, size limit). | **Retry with Exponential Backoff.** Re-upload the image file up to configured max retries. | None. If all retries fail, the page is skipped for this batch cycle. |
| **Batch Job Fail** | Gemini Batch API returns `JOB_STATE_FAILED`. | **Flow Logic.** Logs error, clears `GEMINI_CURRENT_BATCH_ID` variable. | None. Next scheduled run will re-submit. |
| **Batch Job Cancelled** | Batch job is cancelled (manual or timeout). | **Flow Logic.** Logs warning, clears `GEMINI_CURRENT_BATCH_ID` variable. | None. Next scheduled run will re-submit. |
| **Batch Job Expired** | Batch job expires before completion. | **Flow Logic.** Logs warning, clears `GEMINI_CURRENT_BATCH_ID` variable. | None. Next scheduled run will re-submit. |
| **Validation Error** | Model returns valid JSON, but schema validation fails (e.g., missing fields). | **Partial Failure.** Output NOT written. `RECORD_FAILURE_COUNTS` var incremented. | None. Scanner will re-queue pending retry limit. |
| **Max Retries** | Specific Page fails validation > configured `max_retries`. | **Dead Letter.** Scanner sees count > limit and skips this page. | **Manual Intervention** required to fix prompt or source image. |
| **Worker Crash** | Python/Prefect process dies mid-execution. | **State Recovery.** `GEMINI_CURRENT_BATCH_ID` persists in Prefect Cloud/DB. | **Restart Flow.** It checks the variable and resumes polling. |

## 2. File Upload Retry Handling

When uploading images to the Gemini File API during batch submission:

*   **Retry Strategy**: Exponential backoff starting from configured `upload_retry_backoff_seconds`.
*   **Maximum Retries**: Configured via `upload_retry_attempts` in config file.
*   **Re-upload on Retry**: Always re-upload the image file on retry (no need to verify if previously uploaded file still exists or is valid).
*   **Failure Handling**: If all retry attempts fail, the page is skipped for the current batch cycle. It will be picked up in the next scan cycle.

This approach simplifies file lifecycle management:
*   No need to track file expiration (files expire after 48 hours).
*   No need to verify file validity before batch submission.
*   Each batch submission uses fresh file uploads, ensuring files are valid for the batch job duration.

## 3. Operational Playbook

### A. How to Resume
Since the system is a State Machine driven by the `GEMINI_CURRENT_BATCH_ID` Prefect Variable, you do not need to do anything special.
1.  Ensure the Prefect Agent/Worker is running.
2.  The next scheduled Flow run will detect the Variable and resume polling the remote batch.

### B. How to Force-Retry a "Done" Page
If a page is marked "Success" (exists in `dataset/output_results`) but you want to re-run it:
1.  **Delete the JSON file** from `dataset/output_results`.
2.  (Optional) If it had previous failures, clear its entry in the `RECORD_FAILURE_COUNTS` Prefect Variable.
3.  **Result:** The Scanner will detect it as missing and queue it in the next batch.

### C. How to Unblock a "Dead Letter" (Max Retries Exceeded)
If a page has failed 3 times (or whatever max is set), the Scanner stops picking it up to save money.
1.  Go to **Prefect UI -> Variables**.
2.  Edit `RECORD_FAILURE_COUNTS`.
3.  Remove the specific Key (e.g., `"CA:Lincoln:2023:4"`) or reset its value to `0`.
4.  **Result:** The Scanner will treat it as a fresh candidate.

### D. How to Clear a "Stuck" Batch
If `GEMINI_CURRENT_BATCH_ID` is set, but you know the job is dead/irrelevant and want to force a new submission:
1.  Go to **Prefect UI -> Variables**.
2.  Delete or clear the value of `GEMINI_CURRENT_BATCH_ID`.
3.  **Result:** The next Flow run will see `None` and switch to "Scanning Mode" to create a new batch.

## 4. Observability (Prefect UI)

We utilize Prefect features to minimize CLI checking.

### 1. Artifacts (Visual Reports)
After every batch processing run, the Flow generates a **Markdown Artifact** in the UI.
*   **Location:** Prefect UI -> Flow Run -> Artifacts.
*   **Content:**
    *   ✅ **Batch Summary:** "Processed 500 records. 495 Success, 5 Failed."
    *   ❌ **Failure List:** A table showing exactly which IDs failed and why.
    *   📊 **Retry Stats:** "Page X is on retry 2/3".

### 2. Logs
Standard logs are structured for filtering:
*   `INFO`: High-level state changes ("Batch Submitted", "Batch Complete").
*   `DEBUG`: Scanner decisions ("Skipping Page 5 (Dependency missing)").
*   `ERROR`: Stack traces for JSON parsing errors or API 500s.

### 3. Variables
The current snapshot of the system state is always visible in **Prefect UI -> Variables**:
*   `GEMINI_CURRENT_BATCH_ID`: Are we waiting on Google?
*   `RECORD_FAILURE_COUNTS`:Which pages are struggling?

## 5. Maintenance

### Pruning Failure Counts
Over months, `RECORD_FAILURE_COUNTS` might grow large.
*   **Recommendation:** Create a separate maintenance task (or manual script) that runs once a month to remove keys for IDs that currently exist in `dataset/output_results` (meaning they eventually succeeded)