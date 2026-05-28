"""
Database engine and session management for the BFSI Dispute Resolution Platform.
Supports SQLite (MVP) and PostgreSQL (production).
"""
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from dotenv import load_dotenv

from utils.logger import db_logger

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dispute_resolution.db")

# SQLite-specific: enable WAL mode and foreign keys
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,         # Set True for SQL query logging in dev
    pool_pre_ping=True,
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables if they don't exist."""
    import database.models  # noqa: F401 — import triggers table registration
    Base.metadata.create_all(bind=engine)
    db_logger.info("Database initialized — all tables created/verified.")


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
