#!/usr/bin/env python3
"""Create the missing dispute_case_seq sequence in PostgreSQL."""

from sqlalchemy import text, create_engine
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

print("Creating dispute_case_seq sequence...")
with engine.connect() as conn:
    try:
        # Create sequence if it doesn't exist
        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS dispute_case_seq START WITH 1"))
        conn.commit()
        print("✓ Sequence created successfully")
        
        # Verify it works
        result = conn.execute(text("SELECT nextval('dispute_case_seq')")).scalar()
        print(f"✓ Sequence test: nextval returned {result}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()

engine.dispose()
print("Done!")
