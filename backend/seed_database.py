import os
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from faker import Faker
import psycopg2
from datetime import date

load_dotenv()

fake = Faker("en_IN")

db_url = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(db_url)

cur = conn.cursor()

for i in range(1, 1001):

    customer_id = f"CUST{i:06}"

    cur.execute(
        """
        INSERT INTO bank_customers
        (
            customer_id,
            full_name,
            email,
            phone,
            joining_date
        )
        VALUES (%s,%s,%s,%s,%s)
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

print("1000 Customers Inserted")

cur.close()
conn.close()