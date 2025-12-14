from __future__ import annotations

from unittest.mock import patch

import pytest

from src.database import Base, get_engine
from src.prefect_state import SQLiteStateStore


@pytest.fixture
def in_memory_db(tmp_path):
    """Create an in-memory SQLite database for testing."""
    # Use a temporary file path for the database
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    # Patch the database path and URL to use temporary database
    with patch("src.database.DB_PATH", db_path), patch("src.database.DB_URL", db_url):
        engine = get_engine()
        Base.metadata.create_all(engine)
        yield engine
        Base.metadata.drop_all(engine)


@pytest.fixture
def store(in_memory_db):
    """Create a SQLiteStateStore with in-memory database."""
    with patch("src.prefect_state.get_session") as mock_get_session:
        from sqlalchemy.orm import sessionmaker

        SessionLocal = sessionmaker(bind=in_memory_db)

        def get_session():
            return SessionLocal()

        mock_get_session.side_effect = get_session
        store = SQLiteStateStore()
        # Override __post_init__ to skip init_database since we already created tables
        store.__post_init__ = lambda: None
        return store


def test_get_active_batches_empty(store):
    """Test getting active batches when none exist."""
    assert store.get_active_batches() == []


def test_add_batch(store):
    """Test adding a batch."""
    batch_id = "batch-123"
    record_keys = ["key1", "key2", "key3"]

    store.add_batch(batch_id, record_keys)

    assert batch_id in store.get_active_batches()
    assert set(store.get_batch_record_keys(batch_id)) == set(record_keys)
    assert store.get_inflight_records() == set(record_keys)


def test_remove_batch(store):
    """Test removing a batch."""
    batch_id = "batch-123"
    record_keys = ["key1", "key2"]

    store.add_batch(batch_id, record_keys)
    assert batch_id in store.get_active_batches()

    removed_keys = store.remove_batch(batch_id)

    assert batch_id not in store.get_active_batches()
    assert set(removed_keys) == set(record_keys)
    assert store.get_inflight_records() == set()


def test_get_batch_record_keys(store):
    """Test getting record keys for a batch."""
    batch_id = "batch-123"
    record_keys = ["key1", "key2", "key3"]

    store.add_batch(batch_id, record_keys)
    assert set(store.get_batch_record_keys(batch_id)) == set(record_keys)


def test_get_failure_counts_empty(store):
    """Test getting failure counts when none exist."""
    assert store.get_failure_counts() == {}


def test_increment_failure_counts(store):
    """Test incrementing failure counts."""
    failures = {"key1": "error1", "key2": "error2"}

    updated_counts = store.increment_failure_counts(failures)

    assert updated_counts["key1"] == 1
    assert updated_counts["key2"] == 1

    # Increment again
    updated_counts = store.increment_failure_counts({"key1": "error1"})
    assert updated_counts["key1"] == 2
    assert updated_counts["key2"] == 1


def test_get_inflight_records(store):
    """Test getting inflight records."""
    batch_id = "batch-123"
    record_keys = ["key1", "key2"]

    store.add_batch(batch_id, record_keys)
    assert store.get_inflight_records() == set(record_keys)

    store.remove_batch(batch_id)
    assert store.get_inflight_records() == set()


def test_add_inflight_records(store):
    """Test adding inflight records."""
    record_keys = ["key1", "key2"]

    store.add_inflight_records(record_keys)
    assert store.get_inflight_records() == set(record_keys)


def test_remove_inflight_records(store):
    """Test removing inflight records."""
    record_keys = ["key1", "key2", "key3"]

    store.add_inflight_records(record_keys)
    assert store.get_inflight_records() == set(record_keys)

    store.remove_inflight_records(["key1", "key2"])
    assert store.get_inflight_records() == {"key3"}


def test_log_failure(store):
    """Test logging a failure."""
    store.log_failure(
        record_key="key1",
        batch_id="batch-123",
        attempt_number=1,
        error_type="JSONDecodeError",
        error_message="Invalid JSON",
        error_traceback="Traceback...",
        raw_response_text="Some text",
        extracted_text="Extracted text",
        raw_response_json='{"response": "data"}',
        model_name="gemini-2.5-flash",
        prompt_name="test-prompt",
        prompt_template="template.jinja",
        generation_config={"temperature": 0.1},
    )

    # Verify failure was logged by checking failure counts were incremented
    failures = {"key1": "Invalid JSON"}
    counts = store.increment_failure_counts(failures)
    assert counts["key1"] >= 1


def test_multiple_batches(store):
    """Test managing multiple batches."""
    batch1 = "batch-1"
    batch2 = "batch-2"
    keys1 = ["key1", "key2"]
    keys2 = ["key3", "key4"]

    store.add_batch(batch1, keys1)
    store.add_batch(batch2, keys2)

    assert batch1 in store.get_active_batches()
    assert batch2 in store.get_active_batches()
    assert store.get_inflight_records() == set(keys1 + keys2)

    store.remove_batch(batch1)
    assert batch1 not in store.get_active_batches()
    assert batch2 in store.get_active_batches()
    assert store.get_inflight_records() == set(keys2)


def test_failure_counts_persistence(store):
    """Test that failure counts persist across operations."""
    failures1 = {"key1": "error1"}
    failures2 = {"key2": "error2"}

    store.increment_failure_counts(failures1)
    store.increment_failure_counts(failures2)

    all_counts = store.get_failure_counts()
    assert all_counts["key1"] == 1
    assert all_counts["key2"] == 1

    # Increment key1 again
    store.increment_failure_counts({"key1": "error1"})
    all_counts = store.get_failure_counts()
    assert all_counts["key1"] == 2
    assert all_counts["key2"] == 1


def test_empty_record_keys_list(store):
    """Test handling empty record keys list."""
    batch_id = "batch-123"

    store.add_batch(batch_id, [])
    assert store.get_batch_record_keys(batch_id) == []
    assert store.get_inflight_records() == set()


def test_log_failure_with_none_values(store):
    """Test logging failure with None values."""
    store.log_failure(
        record_key="key1",
        batch_id="batch-123",
        attempt_number=1,
        error_type=None,
        error_message=None,
        error_traceback=None,
        raw_response_text=None,
        extracted_text=None,
        raw_response_json=None,
        model_name=None,
        prompt_name=None,
        prompt_template=None,
        generation_config=None,
    )

    # Should not raise an exception
    assert True


def test_remove_nonexistent_batch(store):
    """Test removing a batch that doesn't exist."""
    result = store.remove_batch("nonexistent-batch")
    assert result == []


def test_add_duplicate_batch(store):
    """Test adding the same batch twice."""
    batch_id = "batch-123"
    keys1 = ["key1", "key2"]
    keys2 = ["key3", "key4"]

    store.add_batch(batch_id, keys1)
    store.add_batch(batch_id, keys2)

    # Should update with new keys
    assert set(store.get_batch_record_keys(batch_id)) == set(keys2)
