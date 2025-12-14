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

### Variable A: `active_batch_ids`

* **Type:** List[string]
* **Purpose:** Track all in-flight batch IDs (supports multiple concurrent batches).
* **Logic:** Append on submission; remove when a batch reaches a terminal state.

### Variable B: `batch_record_keys`

* **Type:** Dict[batch_id, List[string]]
* **Purpose:** Map batch IDs to their record keys so we can clear inflight records when a batch completes or fails.

### Variable C: `inflight_record_ids`

* **Type:** List[string]
* **Purpose:** Record keys that are already scheduled in an active batch. The scanner skips these to avoid double-sending while a batch is pending.

### Variable D: `record_failure_counts`

* **Type:** JSON Dictionary
* **Purpose:** Tracks how many times a specific page has failed.
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
