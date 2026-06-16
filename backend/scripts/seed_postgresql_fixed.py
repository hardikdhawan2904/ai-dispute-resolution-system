import os
from dotenv import load_dotenv
import psycopg2
import random
from datetime import datetime, timedelta
# pyrefly: ignore [missing-import]
from faker import Faker

load_dotenv()

fake = Faker("en_IN")

print("Connecting to PostgreSQL database...")
db_url = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(db_url)
cur = conn.cursor()

try:
    print("Clearing existing data from tables...")
    cur.execute("TRUNCATE TABLE bank_customers, merchant_profiles, transactions, dispute_history RESTART IDENTITY CASCADE;")
    conn.commit()
    print("Existing data cleared.")

    # 1. Seed bank_customers (using CUST-00001 format with 5 digits)
    print("Seeding 1000 Customers...")
    for i in range(1, 1001):
        customer_id = f"CUST-{i:05}"
        cur.execute(
            """
            INSERT INTO bank_customers (customer_id, full_name, email, phone, joining_date)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                customer_id,
                fake.name(),
                fake.email(),
                str(fake.random_number(digits=10)).zfill(10),
                fake.date_between(start_date="-5y", end_date="today")
            )
        )
    conn.commit()
    print("1000 Customers Seeded Successfully.")

    # 2. Seed merchant_profiles
    print("Seeding 100 Merchants...")
    merchants_templates = [
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
        merchant_id = f"MER-{i:04}"
        merchant_name, category = random.choice(merchants_templates)
        cur.execute(
            """
            INSERT INTO merchant_profiles (
                merchant_id, merchant_name, merchant_category, total_transactions, 
                total_disputes, fraud_complaints, resolved_customer_favor, 
                resolved_merchant_favor, risk_level, blacklisted, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                merchant_id,
                merchant_name,
                category,
                random.randint(100, 5000),
                random.randint(0, 50),
                random.randint(0, 20),
                random.randint(0, 25),
                random.randint(0, 25),
                random.choice(["LOW", "MEDIUM", "HIGH"]),
                False
            )
        )
    conn.commit()
    print("100 Merchants Seeded Successfully.")

    # 3. Seed transactions
    print("Seeding 10000 Transactions...")
    transaction_types = ["UPI", "NEFT", "Credit Card", "Debit Card", "ATM", "POS"]
    statuses = ["Success", "Failed", "Pending", "Reversed"]
    cities = ["Delhi", "Mumbai", "Bangalore", "Hyderabad", "Pune", "Chennai", "Kolkata"]

    for i in range(1, 10001):
        transaction_id = f"TXN-{i:08}"
        customer_id = f"CUST-{random.randint(1, 1000):05}"
        merchant_num = random.randint(1, 100)
        merchant_id = f"MER-{merchant_num:04}"
        amount = round(random.uniform(100, 50000), 2)
        transaction_date = datetime.now() - timedelta(days=random.randint(0, 365))

        cur.execute(
            """
            INSERT INTO transactions (
                transaction_id, customer_id, merchant_id, merchant_name, amount, 
                currency, transaction_type, transaction_date, status, location, 
                device_id, is_disputed, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
                f"DEV{random.randint(1000, 9999)}",
                False
            )
        )
        if i % 2000 == 0:
            conn.commit()
            print(f"{i} transactions inserted...")

    conn.commit()
    print("10000 Transactions Seeded Successfully.")

    # 4. Seed dispute_history
    print("Seeding 600 Dispute History records...")
    categories = [
        "Unauthorized Transaction", "ATM Cash Not Dispensed", "Duplicate Debit",
        "Merchant Dispute", "Chargeback", "Friendly Fraud", "Card Skimming"
    ]
    resolutions = ["customer", "merchant", "partial"]

    for i in range(1, 601):
        case_id = f"CASE-{i:06}"
        customer_id = f"CUST-{random.randint(1, 1000):05}"
        merchant_id = f"MER-{random.randint(1, 100):04}"
        transaction_id = f"TXN-{random.randint(1, 10000):08}"
        amount = round(random.uniform(100, 50000), 2)
        created_at = datetime.now() - timedelta(days=random.randint(30, 365))
        resolution_days = random.randint(1, 15)
        resolved_at = created_at + timedelta(days=resolution_days)

        cur.execute(
            """
            INSERT INTO dispute_history (
                case_id, customer_id, merchant_id, transaction_id, dispute_category, 
                fraud_claim, amount, resolution, resolved_in_favor_of, 
                resolution_days, status, created_at, resolved_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    conn.commit()
    print("600 Dispute History records Seeded Successfully.")

except Exception as err:
    conn.rollback()
    print(f"Error occurred: {err}")
finally:
    cur.close()
    conn.close()
    print("Database connection closed.")
