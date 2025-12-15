from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from .database import (
    FailureLog,
    get_session,
    init_database,
)
from src.enums import BatchStatus


@dataclass
class SQLiteStateStore:
    """State store using SQLite database for scalable state management."""

    def __post_init__(self) -> None:
        """Initialize database schema on first use."""
        init_database()

    def get_active_batches(self) -> list[str]:
        """Get list of active batch IDs."""
        with get_session() as session:
            result = session.execute(
                text("SELECT batch_id FROM active_batches WHERE status = :status"),
                {"status": BatchStatus.ACTIVE.value},
            )
            return [row[0] for row in result]

    def add_batch(self, batch_id: str, record_keys: list[str]) -> None:
        """Add a new batch and its record keys."""
        now = datetime.utcnow()
        with get_session() as session:
            # Insert or update active batch
            session.execute(
                text("""
                    INSERT INTO active_batches (batch_id, created_at, updated_at, status)
                    VALUES (:batch_id, :created_at, :updated_at, :status)
                    ON CONFLICT(batch_id) DO UPDATE SET
                        status = :status,
                        updated_at = :updated_at
                """),
                {
                    "batch_id": batch_id,
                    "created_at": now,
                    "updated_at": now,
                    "status": BatchStatus.ACTIVE.value,
                },
            )

            # Get old record keys before deletion (to remove from inflight records)
            old_keys_result = session.execute(
                text(
                    "SELECT record_key FROM batch_record_keys WHERE batch_id = :batch_id"
                ),
                {"batch_id": batch_id},
            )
            old_keys = {row[0] for row in old_keys_result}
            new_keys_set = set(record_keys)
            keys_to_remove = old_keys - new_keys_set

            # Delete old batch record keys (to replace with new ones, consistent with InMemoryStateStore)
            session.execute(
                text("DELETE FROM batch_record_keys WHERE batch_id = :batch_id"),
                {"batch_id": batch_id},
            )

            # Insert batch record keys
            for record_key in record_keys:
                session.execute(
                    text("""
                        INSERT INTO batch_record_keys (batch_id, record_key, created_at)
                        VALUES (:batch_id, :record_key, :created_at)
                    """),
                    {"batch_id": batch_id, "record_key": record_key, "created_at": now},
                )

            # Remove old inflight records that are no longer in this batch
            if keys_to_remove:
                placeholders = ",".join(
                    [f":key{i}" for i in range(len(keys_to_remove))]
                )
                params = {f"key{i}": key for i, key in enumerate(keys_to_remove)}
                params["batch_id"] = batch_id
                session.execute(
                    text(f"""
                        DELETE FROM inflight_records 
                        WHERE record_key IN ({placeholders}) AND batch_id = :batch_id
                    """),
                    params,
                )

            # Add to inflight records with batch_id
            for record_key in record_keys:
                session.execute(
                    text("""
                        INSERT INTO inflight_records (record_key, batch_id, created_at)
                        VALUES (:record_key, :batch_id, :created_at)
                        ON CONFLICT(record_key) DO UPDATE SET batch_id = :batch_id
                    """),
                    {"record_key": record_key, "batch_id": batch_id, "created_at": now},
                )

            session.commit()

    def remove_batch(self, batch_id: str) -> list[str]:
        """Remove a batch and return its record keys."""
        with get_session() as session:
            # Get record keys before deletion
            result = session.execute(
                text(
                    "SELECT record_key FROM batch_record_keys WHERE batch_id = :batch_id"
                ),
                {"batch_id": batch_id},
            )
            record_keys = [row[0] for row in result]

            # Update batch status
            session.execute(
                text("""
                    UPDATE active_batches
                    SET status = :status, updated_at = :updated_at
                    WHERE batch_id = :batch_id
                """),
                {
                    "batch_id": batch_id,
                    "status": BatchStatus.COMPLETED.value,
                    "updated_at": datetime.utcnow(),
                },
            )

            # Delete batch record keys
            session.execute(
                text("DELETE FROM batch_record_keys WHERE batch_id = :batch_id"),
                {"batch_id": batch_id},
            )

            # Remove from inflight records (inline to avoid nested session)
            if record_keys:
                placeholders = ",".join([f":key{i}" for i in range(len(record_keys))])
                params = {f"key{i}": key for i, key in enumerate(record_keys)}
                session.execute(
                    text(
                        f"DELETE FROM inflight_records WHERE record_key IN ({placeholders})"
                    ),
                    params,
                )

            session.commit()
            return record_keys

    def get_batch_record_keys(self, batch_id: str) -> list[str]:
        """Get record keys for a specific batch."""
        with get_session() as session:
            result = session.execute(
                text(
                    "SELECT record_key FROM batch_record_keys WHERE batch_id = :batch_id"
                ),
                {"batch_id": batch_id},
            )
            return [row[0] for row in result]

    def get_failure_counts(self) -> dict[str, int]:
        """Get failure counts for all records."""
        with get_session() as session:
            result = session.execute(
                text("SELECT record_key, count FROM failure_counts")
            )
            return {row[0]: row[1] for row in result}

    def increment_failure_counts(self, failures: dict[str, str]) -> dict[str, int]:
        """Increment failure counts for given record keys."""
        now = datetime.utcnow()
        with get_session() as session:
            for record_key in failures:
                session.execute(
                    text("""
                        INSERT INTO failure_counts (record_key, count, last_updated)
                        VALUES (:record_key, 1, :last_updated)
                        ON CONFLICT(record_key) DO UPDATE SET
                            count = failure_counts.count + 1,
                            last_updated = :last_updated
                    """),
                    {"record_key": record_key, "last_updated": now},
                )

            # Return all failure counts (consistent with InMemoryStateStore)
            result = session.execute(
                text("SELECT record_key, count FROM failure_counts")
            )
            updated_counts = {row[0]: row[1] for row in result}

            session.commit()
            return updated_counts

    def get_inflight_records(self) -> set[str]:
        """Get set of all inflight record keys."""
        with get_session() as session:
            result = session.execute(text("SELECT record_key FROM inflight_records"))
            return {row[0] for row in result}

    def add_inflight_records(self, record_keys: list[str]) -> None:
        """Add record keys to inflight records.

        Note: This method is called from add_batch which already handles
        inflight records with batch_id. This method is kept for protocol
        compatibility but should not be called directly with batch context.
        """
        if not record_keys:
            return
        now = datetime.utcnow()
        with get_session() as session:
            for record_key in record_keys:
                session.execute(
                    text("""
                        INSERT INTO inflight_records (record_key, batch_id, created_at)
                        VALUES (:record_key, :batch_id, :created_at)
                        ON CONFLICT(record_key) DO UPDATE SET batch_id = :batch_id
                    """),
                    {"record_key": record_key, "batch_id": "", "created_at": now},
                )
            session.commit()

    def remove_inflight_records(self, record_keys: list[str]) -> None:
        """Remove record keys from inflight records."""
        if not record_keys:
            return
        with get_session() as session:
            # SQLite requires using placeholders for IN clause
            placeholders = ",".join([f":key{i}" for i in range(len(record_keys))])
            params = {f"key{i}": key for i, key in enumerate(record_keys)}
            session.execute(
                text(
                    f"DELETE FROM inflight_records WHERE record_key IN ({placeholders})"
                ),
                params,
            )
            session.commit()

    def log_failure(
        self,
        *,
        record_key: str,
        batch_id: str,
        attempt_number: int,
        error_type: str | None,
        error_message: str | None,
        error_traceback: str | None,
        raw_response_text: str | None,
        extracted_text: str | None,
        raw_response_json: str | None,
        model_name: str | None,
        prompt_name: str | None,
        prompt_template: str | None,
        generation_config: dict[str, Any] | None,
    ) -> None:
        """Log a failure with full context."""
        with get_session() as session:
            failure_log = FailureLog(
                record_key=record_key,
                batch_id=batch_id,
                attempt_number=attempt_number,
                error_type=error_type,
                error_message=error_message,
                error_traceback=error_traceback,
                raw_response_text=raw_response_text,
                extracted_text=extracted_text,
                raw_response_json=raw_response_json,
                model_name=model_name,
                prompt_name=prompt_name,
                prompt_template=prompt_template,
                generation_config=json.dumps(generation_config)
                if generation_config
                else None,
            )
            session.add(failure_log)
            session.commit()


@dataclass
class InMemoryStateStore:
    active_batches: list[str] | None = None
    batch_record_keys: dict[str, list[str]] | None = None
    failure_counts: dict[str, int] | None = None
    inflight_records: set[str] | None = None

    def __post_init__(self) -> None:
        if self.active_batches is None:
            self.active_batches = []
        if self.batch_record_keys is None:
            self.batch_record_keys = {}
        if self.failure_counts is None:
            self.failure_counts = {}
        if self.inflight_records is None:
            self.inflight_records = set()

    def get_active_batches(self) -> list[str]:
        return list(self.active_batches or [])

    def add_batch(self, batch_id: str, record_keys: list[str]) -> None:
        assert self.active_batches is not None
        assert self.batch_record_keys is not None
        if batch_id not in self.active_batches:
            self.active_batches.append(batch_id)
        self.batch_record_keys[batch_id] = list(record_keys)
        self.add_inflight_records(record_keys)

    def remove_batch(self, batch_id: str) -> list[str]:
        assert self.active_batches is not None
        assert self.batch_record_keys is not None
        if batch_id in self.active_batches:
            self.active_batches.remove(batch_id)
        record_keys = self.batch_record_keys.pop(batch_id, [])
        self.remove_inflight_records(record_keys)
        return list(record_keys)

    def get_batch_record_keys(self, batch_id: str) -> list[str]:
        assert self.batch_record_keys is not None
        return list(self.batch_record_keys.get(batch_id, []))

    def get_failure_counts(self) -> dict[str, int]:
        assert self.failure_counts is not None
        return dict(self.failure_counts)

    def increment_failure_counts(self, failures: dict[str, str]) -> dict[str, int]:
        assert self.failure_counts is not None
        for key in failures:
            self.failure_counts[key] = self.failure_counts.get(key, 0) + 1
        return dict(self.failure_counts)

    def get_inflight_records(self) -> set[str]:
        assert self.inflight_records is not None
        return set(self.inflight_records)

    def add_inflight_records(self, record_keys: list[str]) -> None:
        assert self.inflight_records is not None
        self.inflight_records.update(record_keys)

    def remove_inflight_records(self, record_keys: list[str]) -> None:
        assert self.inflight_records is not None
        self.inflight_records.difference_update(record_keys)
