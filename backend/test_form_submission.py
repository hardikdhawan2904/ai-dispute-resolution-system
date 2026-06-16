#!/usr/bin/env python3
"""Test script to verify DB seed data and attempt form submissions."""

import requests
import json
from database.database import SessionLocal
from database.models import BankCustomer, Transaction

# 1. Verify DB data
db = SessionLocal()
cust = db.query(BankCustomer).filter(BankCustomer.customer_id == 'CUST-00001').first()
txn = db.query(Transaction).filter(Transaction.transaction_id == 'TXN-00000001').first()

print("=" * 60)
print("DATABASE VERIFICATION")
print("=" * 60)
if cust:
    print(f"✓ Customer found: {cust.full_name} ({cust.customer_id})")
else:
    print("✗ Customer CUST-00001 NOT FOUND")

if txn:
    print(f"✓ Transaction found: {txn.transaction_id}")
    print(f"  - Amount: {txn.amount} {txn.currency}")
    print(f"  - Merchant: {txn.merchant_name}")
    print(f"  - Customer: {txn.customer_id}")
else:
    print("✗ Transaction TXN-00000001 NOT FOUND")

db.close()

# 2. Get auth token for customer
print("\n" + "=" * 60)
print("AUTHENTICATION")
print("=" * 60)
try:
    auth_response = requests.post(
        "http://localhost:8000/auth/login",
        json={"email": "customer@bank.com", "password": "customer123"},
        timeout=10
    )
    if auth_response.status_code == 200:
        token = auth_response.json()["access_token"]
        print(f"✓ Auth token obtained")
    else:
        print(f"✗ Auth failed ({auth_response.status_code}): {auth_response.text}")
        exit(1)
except Exception as e:
    print(f"✗ Connection error: {e}")
    print("  Ensure backend is running on http://localhost:8000")
    exit(1)

# 3. Test 3 form submissions with different dispute categories
headers = {"Authorization": f"Bearer {token}"}

test_cases = [
    {
        "name": "Test 1: Unauthorized Transaction",
        "data": {
            "customer_id": "CUST-00001",
            "transaction_id": "TXN-00001947",
            "customer_comment": "I did not authorize this transaction. My card was not in my possession.",
            "dispute_reason": "Unauthorized transaction",
            "fraud_selected": True,
            "otp_received": False,
            "card_blocked": True,
            "bank_contacted": False,
            "transaction_location": "Unknown"
        }
    },
    {
        "name": "Test 2: Duplicate Transaction",
        "data": {
            "customer_id": "CUST-00001",
            "transaction_id": "TXN-00002136",
            "customer_comment": "This transaction appears to be a duplicate. I was charged twice for the same order.",
            "dispute_reason": "Duplicate transaction",
            "fraud_selected": False,
            "otp_received": True,
            "card_blocked": False,
            "bank_contacted": True,
            "transaction_location": "New Delhi"
        }
    },
    {
        "name": "Test 3: Refund Not Received",
        "data": {
            "customer_id": "CUST-00001",
            "transaction_id": "TXN-00004228",
            "customer_comment": "I returned the item last month but the refund is still pending.",
            "dispute_reason": "Refund not received",
            "fraud_selected": False,
            "otp_received": True,
            "card_blocked": False,
            "bank_contacted": True,
            "transaction_location": "Mumbai"
        }
    }
]

print("\n" + "=" * 60)
print("FORM SUBMISSION TESTS")
print("=" * 60)

for i, test_case in enumerate(test_cases, 1):
    print(f"\n{test_case['name']}")
    print("-" * 60)
    
    response = requests.post(
        "http://localhost:8000/api/customer/disputes/submit",
        json=test_case['data'],
        headers=headers
    )
    
    if response.status_code == 201:
        result = response.json()
        print(f"✓ SUBMITTED - Case ID: {result.get('case_id')}")
        print(f"  Message: {result.get('message')}")
    elif response.status_code == 403:
        print(f"✗ FAILED (403 Forbidden): {response.json().get('detail')}")
    elif response.status_code == 404:
        print(f"✗ FAILED (404 Not Found): {response.json().get('detail')}")
    elif response.status_code == 422:
        errors = response.json().get('detail', {})
        print(f"✗ FAILED (422 Validation): {errors}")
    else:
        print(f"✗ FAILED ({response.status_code}): {response.text}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
