# 08. Build Plan & Implementation Order

## Overview

This document outlines the recommended order for building the system components. The plan prioritizes building and testing foundational components first, then layering on more complex functionality. Each phase includes unit tests to ensure correctness before moving to the next phase.

## Build Phases

### Phase 1: Configuration & DAG Building (Foundation)

**Goal**: Build the core scanning and dependency resolution logic.

**Components to Build**:

1. **Configuration Loading**
   *   YAML config file parser
   *   `.env` file loader for secrets
   *   Pydantic models for configuration validation
   *   Error handling for missing/invalid config

2. **DAG Scanner**
   *   Filesystem scanner for `label_to_curricular` directory
   *   Dependency resolution logic (page N depends on page N-1)
   *   Filtering by state and year range
   *   Integration with Prefect Variables for failure counts
   *   Output: List of runnable page identifiers

**Why First**: This is the foundation that defines what work needs to be done. All other components depend on knowing which pages to process.

**Unit Tests**:

*   Test configuration loading with valid/invalid YAML
*   Test scanner with various directory structures
*   Test dependency resolution logic
*   Test filtering logic
*   Test integration with Prefect Variables (mocked)

**Acceptance Criteria**:

*   Scanner correctly identifies runnable pages based on dependencies
*   Configuration loads and validates correctly
*   All unit tests pass
*   Can scan real dataset structure and produce expected output

**Estimated Time**: 2-3 days

---

### Phase 2: File API Integration

**Goal**: Implement image file upload to Gemini File API.

**Components to Build**:

1. **File Upload Module**
   *   Gemini File API client initialization
   *   Image file upload function
   *   Retry logic with exponential backoff
   *   Error handling for upload failures
   *   File metadata tracking (URI, MIME type)

2. **File Upload Batch Processing**
   *   Upload multiple images in parallel (with concurrency limits)
   *   Track upload status per file
   *   Handle partial failures

**Why Second**: File uploads are required before batch submission. This is a relatively isolated component that can be tested independently.

**Unit Tests**:

*   Test file upload with mocked File API
*   Test retry logic on failures
*   Test batch upload with mixed success/failure
*   Test error handling

**Integration Tests**:

*   Test real file upload with test API key
*   Test file cleanup after upload

**Acceptance Criteria**:

*   Can upload single image file successfully
*   Retry logic works correctly on failures
*   Can upload multiple files
*   All tests pass


---

### Phase 3: Batch Request Building

**Goal**: Construct batch request JSONL files.

**Components to Build**:

1. **Prompt Construction**
   *   Load prompt template (from domain integration)
   *   Inject previous page context if dependency exists
   *   Build complete prompt text

2. **Batch Request Builder**
   *   Create request objects with:
     *   Unique key per page
     *   Request structure with file URI and prompt
   *   Build JSONL file from requests
   *   Validate JSONL format

3. **JSONL File Upload**
   *   Upload JSONL file to File API
   *   Get file reference for batch job creation

**Why Third**: Batch requests need file URIs (from Phase 2) and page identifiers (from Phase 1). This connects the two.

**Unit Tests**:

*   Test prompt construction with/without context
*   Test request object structure
*   Test JSONL file format
*   Test JSONL upload (mocked)

**Acceptance Criteria**:

*   Can build valid batch request JSONL
*   Prompts include context correctly
*   JSONL format matches Gemini API requirements
*   All tests pass


---

### Phase 4: Batch API Integration

**Goal**: Submit batch jobs and poll for completion.

**Components to Build**:

1. **Batch Job Creation**
   *   Gemini Batch API client initialization
   *   Create batch job with model name and JSONL file reference
   *   Store batch job ID

2. **Batch Status Polling**
   *   Poll batch job status
   *   Handle all batch states (`JOB_STATE_PROCESSING`, `JOB_STATE_SUCCEEDED`, `JOB_STATE_FAILED`, etc.)
   *   Implement polling with configurable interval
   *   Timeout handling

3. **Result Download**
   *   Download results JSONL file from completed batch
   *   Parse JSONL line by line
   *   Extract response/error per record

**Why Fourth**: Batch API is the core processing mechanism. Needs file uploads (Phase 2) and request building (Phase 3) to be complete.

**Unit Tests**:

*   Test batch job creation (mocked)
*   Test status polling logic
*   Test result download and parsing
*   Test error handling for failed batches

**Integration Tests**:

*   Test real batch job creation with test API key
*   Test polling until completion
*   Test result download

**Acceptance Criteria**:

*   Can create batch job successfully
*   Can poll batch status correctly
*   Can download and parse results
*   Handles all batch states correctly
*   All tests pass


---

### Phase 5: Result Processing & Validation

**Goal**: Process batch results and validate outputs.

**Components to Build**:

1. **Result Parser**
   *   Parse JSONL results line by line
   *   Extract text content from successful responses
   *   Identify errors in failed responses
   *   Map results back to page identifiers

2. **Result Validator**
   *   Parse JSON output from model
   *   Validate against Pydantic schema
   *   Identify validation errors

3. **Result Writer**
   *   Write successful results to output directory
   *   Maintain directory structure (`{state}/{school}/{year}/{page}.json`)
   *   Handle write failures

4. **Failure Tracking**
   *   Update `failure_counts` table in SQLite database
   *   Increment failure counts
   *   Log detailed failure information to `failure_logs` table
   *   Identify dead letters (max retries exceeded)

**Why Fifth**: Results need to be processed after batch completion. This completes the processing pipeline.

**Unit Tests**:

*   Test result parsing with various response formats
*   Test validation against schema
*   Test failure tracking logic
*   Test result writing

**Acceptance Criteria**:

*   Can parse batch results correctly
*   Validation catches invalid outputs
*   Successful results written to correct locations
*   Failure counts updated correctly
*   All tests pass


---

### Phase 6: Prefect Flow Orchestration

**Goal**: Integrate all components into Prefect flow.

**Components to Build**:

1. **Prefect Flow Structure**
   *   Main flow function
   *   State machine logic with multiple concurrent batches (poll/process existing, then submit new if slots available)
   *   Task definitions for each phase

2. **SQLite Database Integration**
   *   Read/write `active_batches` table
   *   Read/write `batch_record_keys` table
   *   Read/write `inflight_records` table
   *   Read/write `failure_counts` table
   *   Log failures to `failure_logs` table
   *   Handle database initialization

3. **Flow Scheduling**
   *   Configure flow schedule (e.g., every 10 minutes)
   *   Set up Prefect deployment

4. **Error Handling & Logging**
   *   Structured logging for flow execution
   *   Error handling at flow level
   *   Prefect artifact generation for batch summaries

**Why Sixth**: Orchestration brings all components together. Needs all previous phases to be complete.

**Unit Tests**:

*   Test flow initialization
*   Test state machine logic (mocked components)
*   Test SQLite database operations
*   Test error handling

**Integration Tests**:

*   Test complete flow execution with mocked APIs
*   Test flow with Prefect local backend

**Acceptance Criteria**:

*   Flow executes correctly end-to-end
*   State machine logic works correctly
*   SQLite database state is managed correctly
*   Logging and artifacts work
*   All tests pass


---

### Phase 7: End-to-End Testing & Refinement

**Goal**: Test complete system with real APIs and refine based on results.

**Components**:

1. **End-to-End Tests**
   *   Test complete workflow with small dataset
   *   Test error scenarios
   *   Test recovery from failures

2. **Performance Testing**
   *   Measure batch processing time
   *   Identify bottlenecks
   *   Optimize if needed

3. **Documentation**
   *   Update documentation based on implementation
   *   Add operational runbooks
   *   Document known issues and workarounds

4. **Refinement**
   *   Fix bugs discovered during testing
   *   Improve error messages
   *   Optimize performance

**Why Last**: Final validation and polish before production use.

**Acceptance Criteria**:

*   End-to-end tests pass with real APIs
*   System handles errors gracefully
*   Performance is acceptable
*   Documentation is complete
*   Ready for production use


---

## Implementation Checklist

### Phase 1: Configuration & DAG Building
- [ ] Create configuration YAML schema
- [ ] Implement config loader with Pydantic validation
- [ ] Implement `.env` file loader
- [ ] Create filesystem scanner
- [ ] Implement dependency resolution logic
- [ ] Implement filtering by state/year
- [ ] Integrate with SQLite database
- [ ] Write unit tests for all components
- [ ] Test with real dataset structure

### Phase 2: File API Integration
- [ ] Initialize Gemini File API client
- [ ] Implement single file upload
- [ ] Implement retry logic
- [ ] Implement batch file upload
- [ ] Write unit tests (mocked API)
- [ ] Write integration tests (real API)
- [ ] Test error handling

### Phase 3: Batch Request Building
- [ ] Implement prompt template loading
- [ ] Implement context injection
- [ ] Build request objects
- [ ] Generate JSONL file
- [ ] Upload JSONL to File API
- [ ] Write unit tests
- [ ] Validate JSONL format

### Phase 4: Batch API Integration
- [ ] Initialize Gemini Batch API client
- [ ] Implement batch job creation
- [ ] Implement status polling
- [ ] Implement result download
- [ ] Write unit tests (mocked API)
- [ ] Write integration tests (real API)
- [ ] Test all batch states

### Phase 5: Result Processing & Validation
- [ ] Implement result parser
- [ ] Implement JSON validation
- [ ] Implement result writer
- [ ] Implement failure tracking
- [ ] Write unit tests
- [ ] Test with sample results

### Phase 6: Prefect Flow Orchestration
- [ ] Create Prefect flow structure
- [ ] Implement state machine logic
- [ ] Integrate SQLite database state store
- [ ] Configure flow scheduling
- [ ] Implement logging and artifacts
- [ ] Write unit tests
- [ ] Write integration tests

### Phase 7: End-to-End Testing & Refinement
- [ ] Run end-to-end tests
- [ ] Performance testing
- [ ] Bug fixes and refinements
- [ ] Documentation updates
- [ ] Final validation

## Dependencies Between Phases

```
Phase 1 (Config & DAG) 
    ↓
Phase 2 (File API) ──┐
    ↓                 │
Phase 3 (Batch Builder) ──┐
    ↓                     │
Phase 4 (Batch API) ──────┼──┐
    ↓                     │  │
Phase 5 (Result Processing) ─┘
    ↓
Phase 6 (Prefect Flow)
    ↓
Phase 7 (E2E Testing)
```

## Testing Strategy Per Phase

Each phase should have:
1. **Unit Tests**: Test components in isolation with mocked dependencies
2. **Integration Tests**: Test interactions between components (if applicable)
3. **Manual Testing**: Test with real data/files (before moving to next phase)

## Risk Mitigation

### High-Risk Areas

*   **Dependency Resolution**: Complex logic, many edge cases → Extensive unit tests
*   **Batch API Integration**: External API, async behavior → Integration tests, error handling
*   **Prefect Flow**: State management complexity → Careful testing of state transitions

### Mitigation Strategies

*   Build incrementally with tests at each step
*   Use mocks extensively for unit tests
*   Test with real APIs early (integration tests)
*   Review design docs before implementation
*   Pair programming or code review for complex logic


