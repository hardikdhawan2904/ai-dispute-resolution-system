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
    **({"pool_size": 20, "max_overflow": 40, "pool_timeout": 30, "pool_recycle": 1800} if not _is_sqlite else {}),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables and apply incremental column migrations."""
    # pyrefly: ignore [missing-import]
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
        # GPS coordinates on transactions
        if "transactions" in inspector.get_table_names():
            txn_cols = {c["name"] for c in inspector.get_columns("transactions")}
            if "latitude" not in txn_cols:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN latitude FLOAT"))
                conn.commit()
                db_logger.info("Migration applied: transactions.latitude added.")
            if "longitude" not in txn_cols:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN longitude FLOAT"))
                conn.commit()
                db_logger.info("Migration applied: transactions.longitude added.")

        if "workflow_plan" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN workflow_plan JSON"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.workflow_plan column added.")

        # Identity & Trust Agent columns
        if "trust_intelligence" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN trust_intelligence JSON"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.trust_intelligence column added.")

        if "user_trust_score" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN user_trust_score FLOAT DEFAULT 1.0"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.user_trust_score column added.")

        if "behavioral_risk_score" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN behavioral_risk_score FLOAT DEFAULT 0.0"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.behavioral_risk_score column added.")

        if "identity_status" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN identity_status VARCHAR(64) DEFAULT 'PENDING'"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.identity_status column added.")

        # Fraud Reasoning Agent columns
        if "fraud_reasoning_brief" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN fraud_reasoning_brief JSON"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.fraud_reasoning_brief column added.")

        if "fraud_probability" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN fraud_probability FLOAT DEFAULT 0.0"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.fraud_probability column added.")

        if "fraud_risk_level" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN fraud_risk_level VARCHAR(32) DEFAULT 'LOW'"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.fraud_risk_level column added.")

        # Agent 4 — EIA: evidence_assessment column
        if "evidence_assessment" not in existing_cols:
            conn.execute(text("ALTER TABLE dispute_cases ADD COLUMN evidence_assessment JSON"))
            conn.commit()
            db_logger.info("Migration applied: dispute_cases.evidence_assessment column added.")

        # Communication logs table
        if "communication_logs" not in inspector.get_table_names():
            conn.execute(text("""
                CREATE TABLE communication_logs (
                    id SERIAL PRIMARY KEY,
                    case_id VARCHAR(64) NOT NULL REFERENCES dispute_cases(case_id) ON DELETE CASCADE,
                    notification_type VARCHAR(64) NOT NULL,
                    recipient VARCHAR(256) NOT NULL,
                    subject VARCHAR(512) NOT NULL,
                    body TEXT NOT NULL,
                    status VARCHAR(32) DEFAULT 'SENT',
                    sent_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_communication_logs_case_id ON communication_logs (case_id)"))
            conn.commit()
            db_logger.info("Migration applied: communication_logs table created.")

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
