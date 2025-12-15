from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.enums import BatchStatus


def _find_project_root() -> Path:
    """Find the project root by looking for pyproject.toml or .git directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() or (current / ".git").exists():
            return current
        current = current.parent
    # Fallback to current directory if we can't find project root
    return Path.cwd()


# Database path - stored in project_root/data/gemini_batches.db
_project_root = _find_project_root()
DB_PATH = _project_root / "data" / "gemini_batches.db"
DB_URL = f"sqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    pass


class ActiveBatch(Base):
    __tablename__ = "active_batches"

    batch_id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    status = Column(String, default=BatchStatus.ACTIVE.value, nullable=False)

    __table_args__ = (
        Index("idx_active_batches_created_at", "created_at"),
        Index("idx_active_batches_status", "status"),
    )


class BatchRecordKey(Base):
    __tablename__ = "batch_record_keys"

    batch_id = Column(String, primary_key=True)
    record_key = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_batch_record_keys_batch_id", "batch_id"),
        Index("idx_batch_record_keys_record_key", "record_key"),
    )


class FailureCount(Base):
    __tablename__ = "failure_counts"

    record_key = Column(String, primary_key=True)
    count = Column(Integer, default=0, nullable=False)
    last_updated = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (Index("idx_failure_counts_record_key", "record_key"),)


class InflightRecord(Base):
    __tablename__ = "inflight_records"

    record_key = Column(String, primary_key=True)
    batch_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_inflight_records_batch_id", "batch_id"),
        Index("idx_inflight_records_record_key", "record_key"),
    )


class FailureLog(Base):
    __tablename__ = "failure_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_key = Column(String, nullable=False)
    batch_id = Column(String, nullable=False)
    attempt_number = Column(Integer, nullable=False)
    error_type = Column(String)
    error_message = Column(Text)
    error_traceback = Column(Text)
    raw_response_text = Column(Text)
    extracted_text = Column(Text)
    raw_response_json = Column(Text)
    model_name = Column(String)
    prompt_name = Column(String)
    prompt_template = Column(String)
    generation_config = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_failure_logs_record_key", "record_key"),
        Index("idx_failure_logs_batch_id", "batch_id"),
        Index("idx_failure_logs_created_at", "created_at"),
        Index("idx_failure_logs_error_type", "error_type"),
    )


def get_engine():
    """Get SQLAlchemy engine for the database."""
    # Ensure data directory exists in project root
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(DB_URL, connect_args={"check_same_thread": False})


def init_database():
    """Initialize database schema (create tables if they don't exist)."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Get a database session."""
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
