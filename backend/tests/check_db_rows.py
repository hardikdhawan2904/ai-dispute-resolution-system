import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from database.database import SessionLocal
from database.models import BankCustomer, Transaction

db = SessionLocal()
try:
    customers = db.query(BankCustomer).limit(5).all()
    print("--- CUSTOMERS ---")
    if not customers:
        print("No customers found in database.")
    for c in customers:
        print(f"ID: '{c.customer_id}', Name: '{c.full_name}', Email: '{c.email}'")
        
    txns = db.query(Transaction).limit(5).all()
    print("\n--- TRANSACTIONS ---")
    if not txns:
        print("No transactions found in database.")
    for t in txns:
        print(f"TXN ID: '{t.transaction_id}', Cust ID: '{t.customer_id}', Amount: {t.amount}, Is Disputed: {t.is_disputed}")
finally:
    db.close()
