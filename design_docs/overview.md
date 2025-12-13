Design Document
Prefect-Powered Gemini Batch Inference Orchestrator

Status: MVP-ready
Audience: ML / AI Engineers, Platform Engineers
Scope: Offline, large-scale Gemini batch inference with partial failure handling

1. Problem Statement

We currently operate a real-time Gemini inference path (e.g. Curricular-Gemini.py) with the following properties:

Single request

Single image + prompt

Synchronous execution

Immediate success or failure

This model breaks down for offline, large-scale workloads, specifically:

Thousands of page-level inferences

Multi-book datasets

Partial failures at record level

Retryable vs fatal errors

Page-to-page dependencies

Long-running execution (hours)

Gemini’s Batch API introduces a fundamentally different execution and failure model:

Batches almost never fail atomically

Individual records fail independently

Retrying a whole batch is incorrect and wasteful

Correctness requires record-level state

This document proposes a Prefect-orchestrated batch inference system that:

Preserves the semantics of real-time inference

Explicitly models record-level state and retries

Supports dependency-aware execution

Is resumable, inspectable, and debuggable

2. Design Principles

Record state is domain state, not orchestration state

Batching is an optimization, not a correctness boundary

Retries are record-scoped, never batch-scoped

The DAG is immutable once execution starts

Prefect orchestrates execution, not business logic

3. Goals & Non-Goals
   Goals

Batch Gemini inference across large datasets

Page-level dependency support

Partial failure handling with selective retries

Resume execution without recomputation

Clear observability in Prefect UI

Deterministic reconstruction of inference inputs

Non-Goals

Real-time or low-latency inference

Streaming inference

Exactly-once semantics

Full prompt lifecycle management platform

Automatic recovery from fatal semantic errors

4. Dataset Model & Implicit Filtering
   Filesystem Layout (Source of Truth)

Images

images_root/
└── {state}/{school}/{year}/
├── 1.jpg
├── 2.jpg
├── 3.jpg
├── ...


First-Pass Results (Filter Source)

first_pass_results/
└── label_to_curricular/
└── {state}/{school}/{year}/
├── 3.json
├── 4.json
├── 5.json
└── 12.json

Key Rule (Critical)

Only pages with a corresponding xxx.json are eligible for inference.

The .json files act as an implicit allow-list

Images without a matching JSON are ignored entirely

Dependencies are resolved only within this filtered set

This rule applies to:

DAG construction

Dependency resolution

Retry logic

5. Dependency Model
   Page Ordering Rules

For each {state}/{school}/{year} group:

Enumerate available xxx.json files

Extract page numbers from JSON filenames

Sort pages numerically

Define dependencies based on adjacent filtered pages

Example

Available files:

Images: 1.jpg → 20.jpg
JSONs:  3.json, 4.json, 5.json, 12.json


Derived DAG:

3 → 4 → 5 
12


Page 12 has no depends_on, as 11 not in allow list

Missing pages are irrelevant

6. External DAG Construction
   Why an External DAG?

Avoid filesystem rescans

Enable crash recovery

Decouple orchestration from I/O discovery

Provide a stable execution plan

DAG Generation (One-Time)

Input:

Images root

First-pass JSON root

Output:

Immutable DAG JSON

DAG Representation
{
"nodes": {
"California:LincolnHigh:2023:3": {
"image_path": ".../3.jpg",
"filter_json": ".../3.json"
},
"California:LincolnHigh:2023:4": {
"image_path": ".../4.jpg",
"filter_json": ".../4.json"
}
},
"deps": {
"California:LincolnHigh:2023:3": null,
"California:LincolnHigh:2023:4": "California:LincolnHigh:2023:3"
}
}


The DAG is read-only during execution.

7. Execution Model
   Conceptual Layers
   Layer	Responsibility
   Domain	Record (single page inference)
   Execution	Gemini batch submission
   Orchestration	Prefect flow

Important:
A record is not a Prefect task.

8. Record-Level State Model

Gemini Batch APIs return per-record outcomes, therefore record state must be tracked explicitly.

Record Status
class RecordStatus(str, Enum):
PENDING
RUNNING
SUCCESS
RETRYABLE_FAILURE
FATAL_FAILURE

Persisted Record State
{
"California:LincolnHigh:2023:4": {
"status": "retryable_failure",
"attempts": 2,
"last_error": "timeout",
"prompt": {
"name": "page_ocr",
"version": "v2",
"vars_hash": "a8f3..."
},
"model": "gemini-1.5-pro"
}
}


This state is:

Durable

Restart-safe

Independent of Prefect retries

9. Prompt Management
   Core Principle

Store prompt identity, not rendered text.

What Is Stored Per Record

Prompt name

Prompt version

Prompt variable hash

Model version

Prompt Registry
prompts/
└── page_ocr/
├── v1.jinja
├── v2.jinja
└── README.md


Rendered prompts are reconstructed at execution time.

This mirrors real-time inference behavior while avoiding duplication.

10. Batch Construction & Retry Strategy
    Record Eligibility

A record is runnable if:

status ∈ {PENDING, RETRYABLE_FAILURE}

attempts < max_attempts

Dependency status is SUCCESS or null

Batch Lifecycle

Select runnable records

Group into batch (size-bounded)

Submit to Gemini Batch API

Parse per-record results

Update record states

Persist state

Repeat

Retry Rules
Outcome	Action
SUCCESS	Terminal
RETRYABLE_FAILURE	Eligible for regrouping
FATAL_FAILURE	Terminal
Dependency failed	Never scheduled

No successful record is ever resent.

11. Prefect’s Role (Strictly Limited)
    Prefect Handles

Flow lifecycle

Infrastructure retries

Crash recovery

Logging

Execution timeline

UI visibility

Prefect Does Not Handle

Record retries

Partial batch semantics

Dependency resolution

Domain state transitions

This avoids abusing Prefect as a state machine.

12. Observability & UI Integration
    Pattern

Batch = Prefect task

Records = artifacts

Example artifact:

create_table_artifact(
key=f"batch-{batch_id}-results",
table=[{
"state": "California",
"school": "LincolnHigh",
"year": 2023,
"page": 4,
"status": "retryable_failure",
"error": "timeout",
"attempt": 2
}]
)

Benefits

Inspect batch history

Trace record retries

Debug failures without logs

Final execution state visible

13. End-to-End Flow

Load persisted DAG

Load or initialize record state

Identify runnable records

Build batch

Submit batch

Process results

Persist state

Repeat until all records terminal

14. Failure Modes & Guarantees
    Supported

Partial batch failures

Retryable API/network errors

Resume after crash

Dependency-aware execution

Not Guaranteed

Exactly-once inference

Automatic semantic error recovery

Prompt reproducibility without registry integrity

15. Summary

This design deliberately:

Treats record state as the source of truth

Uses Prefect as an orchestrator, not a brain

Aligns batch inference semantics with real-time inference

Scales without sacrificing correctness

It is intentionally boring, explicit, and debuggable — which is exactly what you want for large-scale LLM batch systems.