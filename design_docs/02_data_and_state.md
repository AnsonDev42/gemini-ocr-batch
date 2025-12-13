# 02. Data Strategy & State Management

## 1. Configuration

All logic is driven by a unified configuration loaded from a YAML file. See [Configuration](./06_configuration.md) for details on the configuration structure and how it is loaded.

The configuration includes:

* **Paths:** Source directories for labels, images, and output location
* **Scope Filters:** Target states and year ranges to process
* **Execution Logic:** Maximum retries, batch size limits
* **Model Configuration:** Gemini model name and generation parameters
* **API Settings:** Polling intervals, timeout values

Configuration is validated using Pydantic models at load time, ensuring type safety and proper path validation.

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
  * `Alabama:Lincoln:4` (JSON Decode Error) - *Retry #2*
  * `California:Adams:10` (Content Filtered) - *Retry #3 (Maxed)*

```

```
