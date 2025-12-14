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

## 3. SQLite Database State Management

State is managed using a dedicated SQLite database located at `data/gemini_batches.db`. This provides scalable storage for batch tracking, failure counts, and comprehensive failure logging.

### Database Location and Initialization

* **Path:** `data/gemini_batches.db`
* **Initialization:** Database schema is automatically created on first use
* **Connection:** Uses SQLAlchemy with connection pooling for efficient access

### State Management Tables

#### Table A: `active_batches`

* **Purpose:** Track all in-flight batch IDs (supports multiple concurrent batches)
* **Schema:**
  * `batch_id` (TEXT PRIMARY KEY)
  * `created_at` (TIMESTAMP)
  * `updated_at` (TIMESTAMP)
  * `status` (TEXT) - 'active', 'completed', 'failed'
* **Logic:** Insert on submission; update status to 'completed' when batch reaches terminal state
* **Indexes:** `created_at`, `status`

#### Table B: `batch_record_keys`

* **Purpose:** Map batch IDs to their record keys so we can clear inflight records when a batch completes or fails
* **Schema:**
  * `batch_id` (TEXT)
  * `record_key` (TEXT)
  * `created_at` (TIMESTAMP)
  * PRIMARY KEY (`batch_id`, `record_key`)
* **Indexes:** `batch_id`, `record_key`

#### Table C: `inflight_records`

* **Purpose:** Record keys that are already scheduled in an active batch. The scanner skips these to avoid double-sending while a batch is pending
* **Schema:**
  * `record_key` (TEXT PRIMARY KEY)
  * `batch_id` (TEXT)
  * `created_at` (TIMESTAMP)
* **Indexes:** `batch_id`, `record_key`

#### Table D: `failure_counts`

* **Purpose:** Tracks how many times a specific page has failed
* **Schema:**
  * `record_key` (TEXT PRIMARY KEY)
  * `count` (INTEGER DEFAULT 0)
  * `last_updated` (TIMESTAMP)
* **Logic:**
  * Incremented when a record returns 400/500 from Gemini OR fails Pydantic validation after parsing
  * If `count > max_retries`, the Scanner ignores this ID (Dead Letter logic)
* **Index:** `record_key`

### Failure Logging Table

#### Table E: `failure_logs`

* **Purpose:** Comprehensive logging of all failures with full context for debugging and analysis
* **Schema:**
  * `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  * `record_key` (TEXT NOT NULL)
  * `batch_id` (TEXT NOT NULL)
  * `attempt_number` (INTEGER NOT NULL)
  * `error_type` (TEXT) - 'JSONDecodeError', 'ValidationError', 'ValueError', 'MissingResponse', etc.
  * `error_message` (TEXT)
  * `error_traceback` (TEXT) - Full traceback for debugging
  * `raw_response_text` (TEXT) - Full LLM response text extracted from candidates
  * `extracted_text` (TEXT) - Text after extraction but before JSON parsing
  * `raw_response_json` (TEXT) - JSON string of full response dict (for context)
  * `model_name` (TEXT)
  * `prompt_name` (TEXT)
  * `prompt_template` (TEXT)
  * `generation_config` (TEXT) - JSON string
  * `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
* **Indexes:** `record_key`, `batch_id`, `created_at`, `error_type`
* **Use Cases:**
  * Analyze JSON parsing failures offline without re-running batches
  * Identify patterns in LLM response formats that cause parsing issues
  * Debug validation errors with full context of what the model returned
  * Track failure trends over time by error type

### State Store Implementation

The `SQLiteStateStore` class implements the `StateStore` protocol and provides:

* **Scalability:** Handles millions of records efficiently with proper indexing
* **Atomic Operations:** All state changes are transactional
* **Concurrent Access:** SQLite supports concurrent reads and serialized writes
* **Failure Logging:** Integrated failure logging with full context capture

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
