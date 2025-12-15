from __future__ import annotations

from enum import Enum


class BatchJobState(str, Enum):
    """Gemini batch job states from the API."""

    PROCESSING = "JOB_STATE_PROCESSING"
    SUCCEEDED = "JOB_STATE_SUCCEEDED"
    PARTIALLY_SUCCEEDED = "JOB_STATE_PARTIALLY_SUCCEEDED"
    FAILED = "JOB_STATE_FAILED"
    CANCELLED = "JOB_STATE_CANCELLED"
    EXPIRED = "JOB_STATE_EXPIRED"
    TIMEOUT = "TIMEOUT"  # Internal state for polling timeouts

    @classmethod
    def terminal_states(cls) -> set[BatchJobState]:
        """Return set of terminal states (batch is complete)."""
        return {
            cls.SUCCEEDED,
            cls.PARTIALLY_SUCCEEDED,
            cls.FAILED,
            cls.CANCELLED,
            cls.EXPIRED,
            cls.TIMEOUT,
        }

    @classmethod
    def success_states(cls) -> set[BatchJobState]:
        """Return set of successful completion states."""
        return {
            cls.SUCCEEDED,
            cls.PARTIALLY_SUCCEEDED,
        }


class BatchStatus(str, Enum):
    """Internal batch status for tracking in database."""

    ACTIVE = "active"
    COMPLETED = "completed"


class ErrorType(str, Enum):
    """Error type classification for failure tracking."""

    JSON_DECODE_ERROR = "JSONDecodeError"
    API_ERROR = "APIError"
    MISSING_RESPONSE = "MissingResponse"
    VALIDATION_ERROR = "ValidationError"
    VALUE_ERROR = "ValueError"
    TIMEOUT_ERROR = "TimeoutError"
    FILE_NOT_FOUND = "FileNotFoundError"
    UNKNOWN = "UnknownError"
