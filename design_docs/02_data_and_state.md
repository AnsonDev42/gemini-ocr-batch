# 02. Data Strategy & State Management

## 1. Pydantic Configuration Model

All logic is driven by a unified configuration object.

```python
list[str] = ["Alabama", "California"]
    target_years: tuple[int, int] = (1849, 1852)from pydantic import BaseModel, DirectoryPath, Field

class GlobalConfig(BaseModel):
    # Paths
    label_source_dir: DirectoryPath = Field(..., description="Source of Truth (JSONs)")
    image_source_dir: DirectoryPath = Field(..., description="Raw Images")
    output_dir: DirectoryPath = Field(..., description="Where to save success results")
  
    # Scope Filters
    target_states: list[str] = ["Alabama", "California"]
    target_years: tuple[int, int] = (1849, 1852)
  
    # Execution Logic
    max_retries: int = 3
    batch_size_limit: int = 100
```

## 2. Filesystem Layout

### Input (The DAG Definition)

The scanner iterates **only** this directory structure.
`dataset/label_to_curricular/{state}/{school}/{year}/{page_num}.json`

### Output (The Success Marker)

`dataset/output_results/{state}/{school}/{year}/{page_num}.json`

## 3. Prefect Internal State (The Queue)

Instead of a local `metadata.json`, we use **Prefect Variables**.

### Variable A: `GEMINI_CURRENT_BATCH_ID`

* **Type:** String (Nullable)
* **Purpose:** Stores the ID of the currently running remote job.
* **Logic:**
  * If set: Flow goes into "Polling/Processing" mode.
  * If null: Flow goes into "Scanning/Submission" mode.

### Variable B: `RECORD_FAILURE_COUNTS`

* **Type:** JSON Dictionary
* **Purpose:** Tracks how many times a specific page has failed.
* **Structure:**
  ```json
  {
    "CA:Lincoln:2023:4": 1,
    "NY:Adams:1890:10": 3
  }
  ```
* **Logic:**
  * Incremented when a record returns 400/500 from Gemini OR fails Pydantic validation after parsing.
  * If `count > max_retries`, the Scanner ignores this ID (Dead Letter logic).

## 4. Observability (Prefect Artifacts)

At the end of every `Process Results` task, we generate a Markdown Artifact in the Prefect UI:

**Batch Summary Report:**

* **Batch ID:** `batch-123`
* **Total Requests:** 100
* **Success:** 95
* **Failures:** 5
* **Failed IDs:**
  * `CA:Lincoln:4` (JSON Decode Error) - *Retry #2*
  * `NY:Adams:10` (Content Filtered) - *Retry #3 (Maxed)*

```

```
