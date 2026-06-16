import requests

endpoints = ['/auth/login', '/api/auth/login', '/login']
for e in endpoints:
    try:
        r = requests.post(f"http://localhost:8000{e}", json={"email": "test", "password": "test"}, timeout=2)
        print(f"{e}: {r.status_code}")
    except Exception as ex:
        print(f"{e}: ERROR - {ex}")
