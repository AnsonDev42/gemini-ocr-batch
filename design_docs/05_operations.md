# 05. Operations, Failure Handling & Observability

## 1. Failure Modes & Strategy

| Failure Type | Description | System Response | Operational Action |
| :--- | :--- | :--- | :--- |
| **Network / 5xx** | Transient HTTP error during submission or polling. | **Prefect Task Retry.** The specific task retries automatically (e.g., 3 times). | None. |
| **File Upload Failure** | Image file upload to File API fails (network, timeout, size limit). | **Retry with Exponential Backoff.** Re-upload the image file up to configured max retries. | None. If all retries fail, the page is skipped for this batch cycle. |
| **Batch Job Fail** | Gemini Batch API returns `JOB_STATE_FAILED`. | **Flow Logic.** Logs error, removes batch ID from `active_batches` table, frees inflight records. | None. Next scheduled run will re-submit. |
| **Batch Job Cancelled** | Batch job is cancelled (manual or timeout). | **Flow Logic.** Logs warning, removes batch ID from `active_batches` table, frees inflight records. | None. Next scheduled run will re-submit. |
| **Batch Job Expired** | Batch job expires before completion. | **Flow Logic.** Logs warning, removes batch ID from `active_batches` table, frees inflight records. | None. Next scheduled run will re-submit. |
| **Validation Error** | Model returns valid JSON, but schema validation fails (e.g., missing fields). | **Partial Failure.** Output NOT written. `failure_counts` table incremented. | None. Scanner will re-queue pending retry limit. |
| **Max Retries** | Specific Page fails validation > configured `max_retries`. | **Dead Letter.** Scanner sees count > limit and skips this page. | **Manual Intervention** required. Use `scripts/clear_failure_counts.py` to reset retry counts. |
| **Worker Crash** | Python/Prefect process dies mid-execution. | **State Recovery.** `active_batches` table persists in SQLite database. | **Restart Flow.** It checks all batches in `active_batches` and resumes polling each one. |

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
The system is driven by a SQLite database (`data/gemini_batches.db`) that tracks:
- `active_batches`: Currently running batch IDs
- `batch_record_keys`: Mapping of batch IDs to record keys
- `inflight_records`: Record keys currently being processed
- `failure_counts`: Retry counts for each record
- `failure_logs`: Detailed failure logs for debugging

1.  Ensure the Prefect Agent/Worker is running.
2.  The next scheduled Flow run will detect any active batches and resume polling/processing.

### B. How to Force-Retry a "Done" Page
If a page is marked "Success" (exists in `dataset/output_results`) but you want to re-run it:
1.  **Delete the JSON file** from `dataset/output_results`.
2.  (Optional) If it had previous failures, clear its failure count using the utility script:
    ```bash
    uv run python scripts/clear_failure_counts.py --states <state> --schools <school> --year-start <year> --year-end <year>
    ```
    Or clear all failure counts:
    ```bash
    uv run python scripts/clear_failure_counts.py --all
    ```
3.  **Result:** The Scanner will detect it as missing and queue it in the next batch.

### C. How to Unblock a "Dead Letter" (Max Retries Exceeded)
If a page has failed 3 times (or whatever max is set), the Scanner stops picking it up to save money.

**Option 1: Clear specific failure counts**
```bash
# Clear for a specific state
uv run python scripts/clear_failure_counts.py --states California

# Clear for specific schools in a state
uv run python scripts/clear_failure_counts.py --states California --schools LincolnHigh RooseveltHigh

# Clear for a year range
uv run python scripts/clear_failure_counts.py --states California --year-start 2020 --year-end 2023
```

**Option 2: Clear all failure counts**
```bash
python scripts/clear_failure_counts.py --all
```

**Result:** The Scanner will treat cleared records as fresh candidates.

### D. How to Clear a "Stuck" Batch
If a batch ID is stuck in `active_batches`, but you know the job is dead/irrelevant and want to force a new submission:

**Option 1: Use the nuke script to clear everything**
```bash
# Dry run first to see what would be deleted
python scripts/nuke_database.py --dry-run

# Actually clear everything
python scripts/nuke_database.py --confirm
```

**Option 2: Manually clear via SQLite**
```bash
sqlite3 data/gemini_batches.db "DELETE FROM active_batches WHERE batch_id = '<batch_id>';"
sqlite3 data/gemini_batches.db "DELETE FROM batch_record_keys WHERE batch_id = '<batch_id>';"
sqlite3 data/gemini_batches.db "DELETE FROM inflight_records WHERE batch_id = '<batch_id>';"
```

**Result:** The next Flow run will see open capacity and create new batches.

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

### 3. Database State
The current snapshot of the system state is stored in the SQLite database (`data/gemini_batches.db`):
*   `active_batches`: Which batches are in flight?
*   `batch_record_keys`: Which records belong to each batch?
*   `inflight_records`: Which record keys are already scheduled?
*   `failure_counts`: Which pages are struggling (retry counts)?
*   `failure_logs`: Detailed failure logs for debugging

You can query the database directly or use utility scripts:
```bash
# Analyze failures
uv run python scripts/analyze_failures.py --summary
uv run python scripts/analyze_failures.py --by-error-type
uv run python scripts/analyze_failures.py --by-state

# Export failures to CSV
uv run python scripts/analyze_failures.py --export-csv failures.csv
```

## 5. Maintenance

### Pruning Failure Counts
Over months, `failure_counts` table might grow large.
*   **Recommendation:** Use the utility script to clear failure counts for records that have succeeded:
    ```bash
    # Clear all failure counts (use with caution)
    uv run python scripts/clear_failure_counts.py --all
    
    # Or clear specific states/schools
    uv run python scripts/clear_failure_counts.py --states California --year-start 2020 --year-end 2023
    ```

### Utility Scripts
The `scripts/` directory contains utility scripts for common operations:

1. **`clear_failure_counts.py`**: Clear failure counts with flexible filtering
   - Clear all: `--all`
   - Filter by states: `--states California Texas`
   - Filter by schools: `--schools LincolnHigh RooseveltHigh`
   - Filter by year range: `--year-start 2020 --year-end 2023`
   - Dry run: `--dry-run`

2. **`analyze_failures.py`**: Analyze failure reasons and patterns
   - Summary: `--summary`
   - By error type: `--by-error-type`
   - By state: `--by-state`
   - By school: `--by-school`
   - Specific record: `--record-key "California:LincolnHigh:2023:4"`
   - Export to CSV: `--export-csv failures.csv`

3. **`nuke_database.py`**: Completely reset the database
   - Dry run: `--dry-run`
   - Clear everything: `--confirm`
   - Recreate tables: `--recreate-tables`
