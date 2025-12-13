# 07. Testing Strategy

## Overview

Testing is organized into unit tests, integration tests, and end-to-end tests. Unit tests focus on isolated components with mocked dependencies, while integration tests verify interactions between components. End-to-end tests validate the complete workflow with real or near-real API calls.

## Test Structure

### Test Directory Layout

```
tests/
├── unit/
│   ├── test_scanner.py          # DAG building and dependency resolution
│   ├── test_config.py            # Configuration loading and validation
│   ├── test_file_upload.py       # File API upload logic (mocked)
│   ├── test_batch_builder.py    # JSONL construction and batch request building
│   └── test_result_processor.py  # Result parsing and validation
├── integration/
│   ├── test_file_api_integration.py  # Real File API calls (with test credentials)
│   ├── test_batch_api_integration.py # Real Batch API calls (with test credentials)
│   └── test_prefect_flow.py          # Prefect flow execution (local backend)
└── fixtures/
    ├── sample_images/            # Sample image files for testing
    ├── sample_labels/            # Sample label JSON files
    └── sample_results/           # Sample output JSON files
```

## Unit Tests

### 1. Scanner Tests (`test_scanner.py`)

**Purpose**: Test the DAG building logic and dependency resolution.

**Test Cases**:

*   **Test: Scan Empty Directory**
    *   Input: Empty `label_to_curricular` directory
    *   Expected: Returns empty list of runnable pages

*   **Test: Scan Single Book - No Dependencies**
    *   Input: Book with pages 1, 2, 3, no output files
    *   Expected: Returns page 1 only (first page, no dependency)

*   **Test: Scan Single Book - Partial Completion**
    *   Input: Book with pages 1, 2, 3, output has page 1
    *   Expected: Returns page 2 (dependency on page 1 met)

*   **Test: Scan Single Book - Gap in Pages**
    *   Input: Book with pages 1, 2, 5 (missing 3, 4), output has page 2
    *   Expected: Returns page 5 (dependency on page 4 not met, but page 2 exists, so page 5 can start)

*   **Test: Scan Multiple Books - Parallel Execution**
    *   Input: Book A (pages 1,2,3), Book B (pages 1,2), no output
    *   Expected: Returns page 1 from Book A and page 1 from Book B (can run in parallel)

*   **Test: Filter by State**
    *   Input: Books from Alabama and California, config filters to Alabama only
    *   Expected: Returns only pages from Alabama books

*   **Test: Filter by Year Range**
    *   Input: Books from 1849, 1850, 1851, config filters to 1849-1850
    *   Expected: Returns only pages from 1849 and 1850 books

*   **Test: Skip Max Retries**
    *   Input: Page with failure count > max_retries in Prefect Variable
    *   Expected: Page is excluded from runnable list (dead letter)

*   **Test: Skip Already Completed**
    *   Input: Page exists in output directory
    *   Expected: Page is excluded from runnable list

### 2. Configuration Tests (`test_config.py`)

**Purpose**: Test configuration loading, validation, and error handling.

**Test Cases**:

*   **Test: Load Valid Config**
    *   Input: Valid YAML file with all required fields
    *   Expected: Configuration object created successfully

*   **Test: Load Config with Missing Required Field**
    *   Input: YAML missing `paths.label_source_dir`
    *   Expected: Pydantic validation error with specific field name

*   **Test: Load Config with Invalid Path**
    *   Input: YAML with non-existent directory path
    *   Expected: Validation error indicating path does not exist

*   **Test: Load Config with Invalid Year Range**
    *   Input: YAML with `target_years.end < target_years.start`
    *   Expected: Validation error for invalid range

*   **Test: Load Config with Invalid Model Name**
    *   Input: YAML with model name that doesn't match expected pattern
    *   Expected: Validation error (if pattern validation is implemented)

*   **Test: Load Config with Missing .env File**
    *   Input: No `.env` file in project root
    *   Expected: Error message indicating `GEMINI_API_KEY` is required

*   **Test: Load Config with Empty API Key**
    *   Input: `.env` file with empty `GEMINI_API_KEY=`
    *   Expected: Error message indicating API key cannot be empty

*   **Test: Load Config with Invalid YAML Syntax**
    *   Input: YAML file with syntax errors
    *   Expected: YAML parsing error with line number

### 3. File Upload Tests (`test_file_upload.py`)

**Purpose**: Test file upload logic with mocked File API.

**Test Cases**:

*   **Test: Upload Single Image Success**
    *   Input: Valid image file path
    *   Mock: File API returns success with file URI
    *   Expected: Returns file URI and metadata

*   **Test: Upload Image Retry on Network Error**
    *   Input: Valid image file path
    *   Mock: First attempt fails with network error, second succeeds
    *   Expected: Retries with exponential backoff, returns file URI on success

*   **Test: Upload Image Max Retries Exceeded**
    *   Input: Valid image file path
    *   Mock: All upload attempts fail
    *   Expected: Raises exception after max retries

*   **Test: Upload Multiple Images**
    *   Input: List of image file paths
    *   Mock: All uploads succeed
    *   Expected: Returns list of file URIs in same order

*   **Test: Upload Image File Not Found**
    *   Input: Non-existent file path
    *   Expected: Raises FileNotFoundError before API call

### 4. Batch Builder Tests (`test_batch_builder.py`)

**Purpose**: Test JSONL construction and batch request building.

**Test Cases**:

*   **Test: Build Single Request**
    *   Input: Page identifier, file URI, prompt text
    *   Expected: Correct JSON object with `key` and `request` structure

*   **Test: Build Request with Context**
    *   Input: Page identifier, file URI, prompt text, previous page context
    *   Expected: Prompt text includes context from previous page

*   **Test: Build JSONL File**
    *   Input: List of requests
    *   Expected: Valid JSONL file (one JSON object per line)

*   **Test: Build Batch with Multiple Pages**
    *   Input: Multiple page identifiers with file URIs
    *   Expected: JSONL file with all requests, each with unique key

*   **Test: Request Key Format**
    *   Input: Page identifier
    *   Expected: Key format matches `"{state}:{school}:{year}:{page}"`

*   **Test: File URI Format**
    *   Input: File URI from upload
    *   Expected: File URI correctly embedded in request structure

### 5. Result Processor Tests (`test_result_processor.py`)

**Purpose**: Test result parsing, validation, and error handling.

**Test Cases**:

*   **Test: Parse Successful Result**
    *   Input: JSONL line with valid response
    *   Expected: Extracts text content, validates against schema, returns parsed object

*   **Test: Parse Failed Result**
    *   Input: JSONL line with error field
    *   Expected: Identifies error, returns error information

*   **Test: Parse Invalid JSON**
    *   Input: Malformed JSONL line
    *   Expected: Handles JSON parsing error gracefully

*   **Test: Validate Result Against Schema**
    *   Input: Valid response text, Pydantic schema
    *   Expected: Validation succeeds, returns validated object

*   **Test: Validate Result Missing Required Field**
    *   Input: Response text missing required field
    *   Expected: Pydantic validation error with field name

*   **Test: Process Batch Results**
    *   Input: JSONL file with multiple results (some success, some failure)
    *   Expected: Returns dictionary mapping page IDs to success/failure status

*   **Test: Extract Text from Response**
    *   Input: Response object with nested content structure
    *   Expected: Correctly extracts text from `response.candidates[0].content.parts`

## Integration Tests

### 1. File API Integration Tests (`test_file_api_integration.py`)

**Purpose**: Test real File API calls with test credentials.

**Requirements**:

*   Uses test API key from environment variable `GEMINI_API_TEST_KEY`
*   Cleans up uploaded files after tests
*   Uses small test images to minimize API costs

**Test Cases**:

*   **Test: Upload Real Image File**
    *   Upload small test image
    *   Verify file URI is returned
    *   Clean up file after test

*   **Test: Upload JSONL File**
    *   Upload test JSONL file
    *   Verify file name/URI is returned
    *   Clean up file after test

*   **Test: File Expiration Handling**
    *   Upload file, wait, verify file still accessible (or handle expiration)

### 2. Batch API Integration Tests (`test_batch_api_integration.py`)

**Purpose**: Test real Batch API calls with test credentials.

**Requirements**:

*   Uses test API key
*   Uses minimal batch size (1-2 records)
*   Waits for batch completion (or times out gracefully)
*   Cleans up batch jobs and files

**Test Cases**:

*   **Test: Create Batch Job**
    *   Upload test images and JSONL
    *   Create batch job
    *   Verify batch job ID is returned

*   **Test: Poll Batch Status**
    *   Create batch job
    *   Poll until completion
    *   Verify status transitions correctly

*   **Test: Download Batch Results**
    *   Create batch job, wait for completion
    *   Download results JSONL
    *   Verify results structure

*   **Test: Handle Batch Failure**
    *   Create batch with invalid request (if possible)
    *   Verify failure is detected and handled

### 3. Prefect Flow Integration Tests (`test_prefect_flow.py`)

**Purpose**: Test Prefect flow execution with local backend.

**Requirements**:

*   Uses Prefect SQLite backend (local)
*   Mocks File API and Batch API calls
*   Verifies Prefect Variables are set correctly

**Test Cases**:

*   **Test: Flow Initialization**
    *   Load config, initialize flow
    *   Verify flow is created successfully

*   **Test: Flow with No Active Batch**
    *   No `GEMINI_CURRENT_BATCH_ID` variable set
    *   Mock scanner returns runnable pages
    *   Verify batch is submitted and variable is set

*   **Test: Flow with Active Batch**
    *   `GEMINI_CURRENT_BATCH_ID` variable set
    *   Mock batch status as processing
    *   Verify flow exits without submitting new batch

*   **Test: Flow Processes Completed Batch**
    *   `GEMINI_CURRENT_BATCH_ID` variable set
    *   Mock batch status as succeeded
    *   Mock results download
    *   Verify results are processed and variable is cleared

## Test Fixtures

### Sample Data

*   **Sample Images**: Small test images (e.g., 100x100 pixels) for file upload tests
*   **Sample Labels**: Valid label JSON files matching expected structure
*   **Sample Results**: Valid output JSON files for validation tests
*   **Sample Configs**: Valid and invalid configuration YAML files

### Mock Data

*   **Mock File API Responses**: File upload success/failure responses
*   **Mock Batch API Responses**: Batch job status, creation, result download responses
*   **Mock Prefect Variables**: Prefect Variable get/set operations

## Test Execution

### Running Unit Tests

```bash
# Run all unit tests
pytest tests/unit/

# Run specific test file
pytest tests/unit/test_scanner.py

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html
```

### Running Integration Tests

```bash
# Run integration tests (requires test API key)
GEMINI_API_TEST_KEY=test_key pytest tests/integration/

# Run specific integration test
pytest tests/integration/test_file_api_integration.py
```

### Running All Tests

```bash
# Run all tests except integration (for CI/CD)
pytest tests/unit/

# Run all tests including integration (requires credentials)
pytest tests/
```

## Continuous Integration

### CI Pipeline

1. **Lint**: Run code formatters and linters
2. **Unit Tests**: Run all unit tests (no external dependencies)
3. **Integration Tests**: Run integration tests if test credentials are available
4. **Coverage Report**: Generate and upload coverage report

### Test Coverage Goals

*   **Unit Tests**: Aim for >90% code coverage
*   **Critical Paths**: 100% coverage for scanner, config loading, result processing
*   **Integration Tests**: Cover happy path and common failure scenarios

## Test Data Management

### Test Credentials

*   Use separate test API key (not production key)
*   Store in CI/CD secrets, not in repository
*   Rotate test credentials periodically

### Test File Cleanup

*   Delete uploaded files after integration tests
*   Cancel or clean up batch jobs created during tests
*   Use temporary directories for test outputs

## Debugging Tests

### Common Issues

*   **Flaky Tests**: Use proper waiting/retry logic, avoid timing dependencies
*   **Test Isolation**: Ensure tests don't depend on execution order
*   **Mock Configuration**: Verify mocks match actual API responses

### Test Utilities

*   **Test Helpers**: Helper functions for creating test data, mocking APIs
*   **Fixtures**: Pytest fixtures for common test setup (config, clients, etc.)
*   **Assertions**: Custom assertion helpers for validating complex structures

