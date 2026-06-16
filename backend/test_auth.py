import requests
import time

# Longer timeout
timeout = 10
try:
    print(f"Attempting /auth/login with {timeout}s timeout...")
    start = time.time()
    r = requests.post(
        "http://localhost:8000/auth/login", 
        json={"email": "customer@bank.com", "password": "customer123"}, 
        timeout=timeout
    )
    elapsed = time.time() - start
    print(f"✓ Response: {r.status_code} (took {elapsed:.2f}s)")
    if r.status_code == 200:
        print(f"✓ Access token: {r.json()['access_token'][:50]}...")
    else:
        print(f"Response: {r.text}")
except Exception as e:
    print(f"✗ Error: {e}")
