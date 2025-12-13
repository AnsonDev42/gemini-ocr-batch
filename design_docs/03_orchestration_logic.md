# 03. Orchestration Logic

## 1. The Prefect Flow: `orchestrate_gemini_batch`

This flow is designed to be run frequently (e.g., every 5-10 minutes). It is a **State Machine**.

### Step 1: Initialization & Resume Check
*   Load `GlobalConfig`.
*   Fetch Prefect Variable `GEMINI_CURRENT_BATCH_ID`.

### Step 2 (Branch A): Active Batch Exists
**Condition:** `GEMINI_CURRENT_BATCH_ID` is not None.

1.  **Task: `check_batch_status`**
    *   Call Gemini API.
    *   **Case: RUNNING:** Log "Waiting for Batch X" and Exit Flow (Wait for next schedule).
    *   **Case: FAILED:** Log Error, Clear `GEMINI_CURRENT_BATCH_ID`, Exit (Will retry submission next tick).
    *   **Case: COMPLETED:** Proceed to Result Processing.

2.  **Task: `process_batch_results`**
    *   Download `.jsonl` results.
    *   Iterate through records:
        *   **Validation:** parsing output against Pydantic Schema.
        *   **On Success:** Write JSON to `output_results_dir`. Log Info.
        *   **On Failure:**
            *   Log Error in Prefect UI.
            *   Load `RECORD_FAILURE_COUNTS` variable.
            *   Increment count for this ID.
            *   Save variable.
            *   *Do NOT write to output dir.* (This ensures retry).
    *   **Cleanup:**
        *   Clear `GEMINI_CURRENT_BATCH_ID`.
        *   Create **Prefect Artifact** (Report).

### Step 3 (Branch B): No Active Batch
**Condition:** `GEMINI_CURRENT_BATCH_ID` is None.

1.  **Task: `scan_and_build_dag`**
    *   **Input:** `label_to_curricular_dir`, `output_results_dir`, `RECORD_FAILURE_COUNTS`.
    *   **Logic:**
        1.  Glob all `.json` files in `label_to_curricular` (Filtered by Config state/year).
        2.  Group by Book (State/School/Year).
        3.  Sort Pages Numerically.
        4.  **Iterate Pages:**
            *   If exists in `output_results`: **SKIP**.
            *   If failure count > `max_retries`: **SKIP** (Dead Letter).
            *   If Page Num == Minimum in directory: **ADD** (Start of book).
            *   If `(Page Num - 1)` exists in `output_results`: **ADD** (Dependency Met).
            *   Else: **BREAK** book loop (Wait for dependency).
    *   **Output:** List of `runnable_ids`.

2.  **Task: `submit_new_batch`**
    *   **Input:** `runnable_ids`.
    *   **Logic:**
        *   If list is empty: Log "No work pending" and Exit.
        *   Load Image Assets.
        *   Load Context (Previous page JSON from `output_results`) if needed.
        *   Construct Gemini Requests.
        *   **Submit to Gemini API.**
        *   **Save Batch ID** to `GEMINI_CURRENT_BATCH_ID` Prefect Variable.

## 2. Retry Logic & Error Handling

### Batch-Level Failure (System Crash)
If the Python script/Prefect agent crashes while a batch is submitted:
1.  **Recovery:** Next time the flow runs, it reads `GEMINI_CURRENT_BATCH_ID`.
2.  **Action:** It queries Google. If Google says "Done", we process. We do not lose track of the batch.

### Record-Level Failure (Bad Output)
If Gemini returns invalid JSON for a specific page:
1.  **Processing:** The validation fails. We do not write the file.
2.  **Marking:** We increment `RECORD_FAILURE_COUNTS` in Prefect.
3.  **Retrying:** In the next `scan_and_build_dag`, the file is missing from output, so it is a candidate. The scanner checks the failure count. If `< Max`, it is included in the new batch.

## 3. Pydantic Models for Tasks

```python
class PageIdentifier(BaseModel):
    state: str
    school: str
    year: int
    page: int
    
    @property
    def id_string(self):
        return f"{self.state}:{self.school}:{self.year}:{self.page}"

class BatchResult(BaseModel):
    batch_id: str
    total_records: int
    successful_records: int
    failed_records: int
    errors: list[str] # For Prefect Artifacts
```