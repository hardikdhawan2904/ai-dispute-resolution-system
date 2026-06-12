"""
Database engine and session management for the BFSI Dispute Resolution Platform.
PostgreSQL via psycopg2.
"""
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from dotenv import load_dotenv

from utils.logger import db_logger

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    # SQLite doesn't support connection pooling — use StaticPool for dev
    **({"pool_size": 10, "max_overflow": 20, "pool_timeout": 10} if not _is_sqlite else {}),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables and apply incremental column migrations."""
    import database.models  # noqa: F401 — registers all ORM models
    Base.metadata.create_all(bind=engine)
    _apply_column_migrations()
    db_logger.info("Database initialized — all tables created/verified.")


def _apply_column_migrations() -> None:
    """Safely add columns and indexes that don't exist yet (idempotent)."""
    from sqlalchemy import text, inspect as sa_inspect

    inspector = sa_inspect(engine)
    with engine.connect() as conn:
        if "dispute_cases" not in inspector.get_table_names():
            return

        existing_cols = {c["name"] for c in inspector.get_columns("dispute_cases")}

        # Agent 3 — WOA: workflow_plan column
        if "workflow_plan" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN workflow_plan JSON"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.workflow_plan column added.")

        # Agent 4 — EIA: evidence_assessment column
        if "evidence_assessment" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN evidence_assessment JSON"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.evidence_assessment column added.")

        # Performance indexes for list/filter queries
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("dispute_cases")}
        index_defs = [
            ("ix_dispute_cases_status",       "status"),
            ("ix_dispute_cases_priority",     "priority"),
            ("ix_dispute_cases_created_at",   "created_at"),
            ("ix_dispute_cases_fraud_suspicion", "fraud_suspicion"),
            ("ix_dispute_cases_dispute_category", "dispute_category"),
        ]
        for idx_name, col in index_defs:
            if idx_name not in existing_indexes:
                try:
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON dispute_cases ({col})"))
                    conn.commit()
                    db_logger.info(f"Index created: {idx_name}")
                except Exception as e:
                    db_logger.warning(f"Index {idx_name} skipped: {e}")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        db.rollback()
        db_logger.error(f"DB session error: {exc}", exc_info=True)
        raise
    finally:
        db.close()


@contextmanager
def db_session():
    """Context-manager session for use outside FastAPI request scope."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as exc:
        db.rollback()
        db_logger.error(f"DB context error: {exc}", exc_info=True)
        raise
    finally:
        db.close()
