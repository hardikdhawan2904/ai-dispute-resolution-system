import os
from dotenv import load_dotenv
import psycopg2
import random
from datetime import datetime, timedelta

load_dotenv()

db_url = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(db_url)

cur = conn.cursor()

categories = [
    "Unauthorized Transaction",
    "ATM Cash Not Dispensed",
    "Duplicate Debit",
    "Merchant Dispute",
    "Chargeback",
    "Friendly Fraud",
    "Card Skimming"
]

resolutions = [
    "customer",
    "merchant",
    "partial"
]

for i in range(1, 601):

    case_id = f"CASE{i:06}"

    customer_id = f"CUST{random.randint(1,1000):06}"

    merchant_id = f"MER{random.randint(1,100):04}"

    transaction_id = f"TXN{random.randint(1,10000):08}"

    amount = round(random.uniform(100, 50000), 2)

    created_at = datetime.now() - timedelta(
        days=random.randint(30, 365)
    )

    resolution_days = random.randint(1, 15)

    resolved_at = created_at + timedelta(
        days=resolution_days
    )

    cur.execute(
        """
        INSERT INTO dispute_history
        (
            case_id,
            customer_id,
            merchant_id,
            transaction_id,
            dispute_category,
            fraud_claim,
            amount,
            resolution,
            resolved_in_favor_of,
            resolution_days,
            status,
            created_at,
            resolved_at
        )
        VALUES
        (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        """,
        (
            case_id,
            customer_id,
            merchant_id,
            transaction_id,
            random.choice(categories),
            random.choice([True, False]),
            amount,
            "Historical dispute resolved",
            random.choice(resolutions),
            resolution_days,
            "Resolved",
            created_at,
            resolved_at
        )
    )

    if i % 100 == 0:
        conn.commit()
        print(f"{i} disputes inserted")

conn.commit()

print("600 dispute history records inserted")

cur.close()
conn.close()