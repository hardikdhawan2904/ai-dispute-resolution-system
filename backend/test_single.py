import requests
import json

# Auth
auth_response = requests.post(
    "http://localhost:8000/auth/login",
    json={"email": "customer@bank.com", "password": "customer123"},
    timeout=10
)
token = auth_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Single test
data = {
    "customer_id": "CUST-00001",
    "transaction_id": "TXN-00001947",
    "customer_comment": "I did not authorize this transaction.",
    "dispute_reason": "Unauthorized transaction",
    "fraud_selected": True,
    "otp_received": False,
    "card_blocked": True,
    "bank_contacted": False,
    "transaction_location": "Unknown"
}

print("Submitting dispute form...")
response = requests.post(
    "http://localhost:8000/api/customer/disputes/submit",
    json=data,
    headers=headers,
    timeout=15
)

print(f"Status: {response.status_code}")
print(f"Response:")
print(json.dumps(response.json(), indent=2))
