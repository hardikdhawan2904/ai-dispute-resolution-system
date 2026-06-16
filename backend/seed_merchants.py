import os
from dotenv import load_dotenv
import psycopg2
import random

load_dotenv()

db_url = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(db_url)

cur = conn.cursor()

merchants = [
    ("Amazon", "E-Commerce"),
    ("Flipkart", "E-Commerce"),
    ("Myntra", "Fashion"),
    ("Swiggy", "Food"),
    ("Zomato", "Food"),
    ("Uber", "Transport"),
    ("Ola", "Transport"),
    ("Paytm", "Fintech"),
    ("BigBasket", "Groceries"),
    ("Reliance Digital", "Electronics")
]

for i in range(1, 101):

    merchant_id = f"MER{i:04}"

    merchant_name, category = random.choice(merchants)

    cur.execute(
        """
        INSERT INTO merchant_profiles
        (
            merchant_id,
            merchant_name,
            merchant_category,
            total_transactions,
            total_disputes,
            fraud_complaints,
            resolved_customer_favor,
            resolved_merchant_favor,
            risk_level,
            blacklisted,
            created_at
        )
        VALUES
        (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
        )
        """,
        (
            merchant_id,
            merchant_name,
            category,
            0,
            0,
            0,
            0,
            0,
            "LOW",
            False
        )
    )

conn.commit()

print("100 Merchants Inserted Successfully")

cur.close()
conn.close()