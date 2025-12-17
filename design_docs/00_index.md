# Design Document: Prefect-Powered Gemini Batch Inference Orchestrator


| Metadata             | Details                                     |
| :------------------- | :------------------------------------------ |
| **Status**           | MVP Design                                  |
| **Scope**            | Offline, large-scale Gemini batch inference |
| **Storage Strategy** | **Filesystem-Native** (No Database)         |

## For LLMs

Read design_docs/agents.md for the development rules

## Overview

This system orchestrates the processing of historical course catalogs using Google's Gemini Batch API. It transitions the existing synchronous, single-threaded inference script into a robust, resumable batch processing pipeline.

## Core Problem Solved

Gemini's Batch API is asynchronous and non-atomic, which conflicts with our requirement for **page-to-page context dependency** (Page $N$ needs the output of Page $N-1$).

This design implements a **"Wave Execution"** strategy:

1. **Scan** the filesystem for pages whose dependencies are met.
2. **Batch** them across different books (parallelizing across width, not depth).
3. **Persist** results to disk to unlock the next page in the chain.
4. If a page has no previous page, just fire it without previous context

## Documentation Index

1. [Architecture & Principles](./01_architecture.md) - The conceptual model.
2. [Data Strategy & State](./02_data_and_state.md) - How we use the filesystem as the database.
3. [Orchestration Logic](./03_orchestration_logic.md) - The "Scanner" and the Prefect flow.
4. [Domain Integration](./04_domain_integration.md) - Context extraction and prompt management.
5. [Operations & Recovery](./05_operations.md) - Handling errors and restarts.
6. [Configuration](./06_configuration.md) - Configuration file structure and environment variables.
7. [Testing Strategy](./07_testing.md) - Unit tests, integration tests, and test structure.
8. [Build Plan](./08_build_plan.md) - Implementation order and phase-by-phase build plan.
