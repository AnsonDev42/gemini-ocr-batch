# 06. Configuration Management

## Overview

The system uses a YAML configuration file for all configurable parameters and a `.env` file in the project root for secrets (API keys). This separation ensures that sensitive credentials are not committed to version control while keeping all operational settings in a single, versioned configuration file.

## Configuration File Structure

### Location

The configuration file is a YAML file located at the project root (e.g., `config.yaml`). The exact path can be specified via environment variable or command-line argument.

### Configuration Schema

# Paths
paths:
label_source_dir: "dataset/label_to_curricular"  # Source of Truth (JSONs)
image_source_dir: "dataset/raw_image_dataset"    # Raw Images
output_dir: "dataset/output_results"             # Where to save success results

# Scope Filters

filters:
target_states:                                    # List of states to process
- "Alabama"
- "California"
target_years:                                     # Year range (inclusive)
start: 1849
end: 1852

# Execution Logic

execution:
max_retries: 3                                    # Maximum retry attempts per page
batch_size_limit: 100                             # Maximum records per batch

# Gemini Model Configuration

model:
name: "gemini-2.5-flash"                         # Model name for batch inference
generation_config:
temperature: 0.1
max_output_tokens: 8192

# Batch API Settings

batch:
poll_interval_seconds: 10                         # How often to check batch status
max_poll_attempts: 360                            # Maximum polling attempts (e.g., 1 hour at 10s intervals)
display_name_prefix: "ocr-batch-job"              # Prefix for batch job display names

# File API Settings

files:
upload_retry_attempts: 3                          # Retry attempts for file uploads
upload_retry_backoff_seconds: 2                   # Initial backoff for retries (exponential)

# Prefect Settings

prefect:
flow_name: "orchestrate_gemini_batch"             # Name of the Prefect flow
schedule_interval_minutes: 10                     # How often to run the flow

## Environment Variables (.env)

### Location

The `.env` file is located at the project root directory. This file should **never** be committed to version control (should be in `.gitignore`).

### Required Variables

```bash
# Google Gemini API Key
GEMINI_API_KEY=your_api_key_here
```

### Optional Variables

```bash
# Override config file path (if not using default)
CONFIG_FILE_PATH=/path/to/config.yaml

# Prefect settings (if using Prefect Cloud)
PREFECT_API_URL=https://api.prefect.cloud/api/accounts/[ACCOUNT_ID]/workspaces/[WORKSPACE_ID]
```

## Configuration Loading

### Initialization Flow

1. **Load Secrets**: Read `.env` file from project root to get `GEMINI_API_KEY` and other secrets.
2. **Load Config**: Read YAML configuration file (path from environment variable or default location).
3. **Validate**: Parse YAML and validate against Pydantic schema:
   * Paths must exist and be valid directories
   * Numeric values must be within valid ranges
   * Model name must be a valid Gemini model identifier
   * Lists must not be empty where required
4. **Initialize Clients**: Create Gemini client with API key from `.env`.

### Prefect Flow Integration

When the Prefect flow starts:

* Configuration is loaded once at flow initialization.
* Configuration object is passed to tasks as needed.
* Secrets are loaded from `.env` file (not from Prefect Variables or secrets).

### Error Handling

If configuration loading fails:

* **Missing `.env` file**: Raise error with clear message about required `GEMINI_API_KEY`.
* **Invalid YAML**: Raise parsing error with file path and line number.
* **Validation failure**: Raise Pydantic validation error with specific field issues.
* **Missing paths**: Raise error listing which directories do not exist.

## Configuration Parameters Reference

### Paths

* `label_source_dir`: Directory containing the source JSON files that define the workload. Only pages with corresponding JSON files in this directory are eligible for processing.
* `image_source_dir`: Directory containing the raw image files (JPG format) to be processed.
* `output_dir`: Directory where successful extraction results are written as JSON files.

### Filters

* `target_states`: List of state names to process. Only books from these states will be included.
* `target_years`: Year range filter. Only books from years within this range (inclusive) will be processed.

### Execution

* `max_retries`: Maximum number of times a failed page will be retried before being marked as a dead letter.
* `batch_size_limit`: Maximum number of records to include in a single batch job. This helps manage batch processing time and resource usage.

### Model

* `name`: The Gemini model identifier to use for batch inference (e.g., "gemini-2.5-flash", "gemini-1.5-pro").
* `generation_config`: Model generation parameters:
  * `temperature`: Controls randomness (0.0 = deterministic, higher = more creative).
  * `max_output_tokens`: Maximum tokens in the model's response.

### Batch

* `poll_interval_seconds`: How long to wait between batch status checks when polling for completion.
* `max_poll_attempts`: Maximum number of polling attempts before timing out (prevents infinite polling).
* `display_name_prefix`: Prefix used for batch job display names in Gemini API (helps identify jobs in UI).

### Files

* `upload_retry_attempts`: Number of times to retry a failed file upload before giving up.
* `upload_retry_backoff_seconds`: Initial backoff delay for retries (doubles on each retry - exponential backoff).

### Prefect

* `flow_name`: Name identifier for the Prefect flow (used in Prefect UI).
* `schedule_interval_minutes`: How frequently the Prefect flow should run (e.g., every 10 minutes).

## Example Configuration Files

### Minimal `config.yaml`

```yaml
paths:
  label_source_dir: "dataset/label_to_curricular"
  image_source_dir: "dataset/raw_image_dataset"
  output_dir: "dataset/output_results"

filters:
  target_states: ["Alabama"]
  target_years:
    start: 1849
    end: 1852

execution:
  max_retries: 3
  batch_size_limit: 100

model:
  name: "gemini-2.5-flash"
```

### Minimal `.env`

```bash
GEMINI_API_KEY=AIza...
```

## Configuration Updates

To change configuration:

1. Edit the `config.yaml` file.
2. Restart the Prefect flow (or wait for next scheduled run).
3. The new configuration will be loaded on the next flow execution.

To update secrets:

1. Edit the `.env` file.
2. Restart the Prefect flow (or wait for next scheduled run).
3. The new API key will be used for subsequent API calls.
