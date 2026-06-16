import os
from dotenv import load_dotenv
import psycopg2
import random
from datetime import datetime, timedelta

load_dotenv()

db_url = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(db_url)

cur = conn.cursor()

transaction_types = [
    "UPI",
    "NEFT",
    "Credit Card",
    "Debit Card",
    "ATM",
    "POS"
]

statuses = [
    "Success",
    "Failed",
    "Pending",
    "Reversed"
]

cities = [
    "Delhi",
    "Mumbai",
    "Bangalore",
    "Hyderabad",
    "Pune",
    "Chennai",
    "Kolkata"
]

for i in range(1, 10001):

    transaction_id = f"TXN{i:08}"

    customer_id = f"CUST{random.randint(1,1000):06}"

    merchant_num = random.randint(1,100)
    merchant_id = f"MER{merchant_num:04}"

    amount = round(random.uniform(100, 50000), 2)

    transaction_date = datetime.now() - timedelta(
        days=random.randint(0, 365)
    )

    cur.execute(
        """
        INSERT INTO transactions
        (
            transaction_id,
            customer_id,
            merchant_id,
            merchant_name,
            amount,
            currency,
            transaction_type,
            transaction_date,
            status,
            location,
            device_id,
            is_disputed,
            created_at
        )
        VALUES
        (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
        )
        """,
        (
            transaction_id,
            customer_id,
            merchant_id,
            f"Merchant_{merchant_num}",
            amount,
            "INR",
            random.choice(transaction_types),
            transaction_date,
            random.choice(statuses),
            random.choice(cities),
            f"DEV{random.randint(1000,9999)}",
            False
        )
    )

    if i % 1000 == 0:
        conn.commit()
        print(f"{i} transactions inserted")

conn.commit()

print("10000 transactions inserted successfully")

cur.close()
conn.close()