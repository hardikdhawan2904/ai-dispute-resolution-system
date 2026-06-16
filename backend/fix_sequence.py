#!/usr/bin/env python3
"""Fix dispute_case_seq by resetting it to start after existing case IDs."""

from sqlalchemy import text, create_engine
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

print("Checking existing case IDs and resetting sequence...")
with engine.connect() as conn:
    try:
        # Get the highest case ID number
        result = conn.execute(text("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(case_id, 6) AS INTEGER)), 0) as max_id
            FROM dispute_cases
            WHERE case_id LIKE 'CASE-%'
        """)).scalar()
        
        max_id = result if result else 0
        next_id = max_id + 1
        
        print(f"Highest existing case ID number: {max_id}")
        print(f"Resetting sequence to start at: {next_id}")
        
        # Drop and recreate the sequence with correct start value
        conn.execute(text("DROP SEQUENCE IF EXISTS dispute_case_seq CASCADE"))
        conn.execute(text(f"CREATE SEQUENCE dispute_case_seq START WITH {next_id}"))
        conn.commit()
        print("✓ Sequence reset successfully")
        
        # Test it
        result = conn.execute(text("SELECT nextval('dispute_case_seq')")).scalar()
        print(f"✓ Sequence test: nextval returned {result}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()

engine.dispose()
print("Done!")
