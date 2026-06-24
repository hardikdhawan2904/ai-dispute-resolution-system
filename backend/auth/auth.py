"""
JWT authentication and RBAC for the BFSI Dispute Resolution Platform.

Demo users (hardcoded for MVP — replace with DB-backed users in production):
  customer@bank.com   / customer123   → CUSTOMER
  analyst@bank.com    / analyst123    → FRAUD_ANALYST
  investigator@bank.com / invest123   → DISPUTE_INVESTIGATOR
  compliance@bank.com / comply123    → COMPLIANCE_OFFICER
  admin@bank.com      / admin123     → OPERATIONS_ADMIN
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "bfsi-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours for bank staff

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Role(str, Enum):
    CUSTOMER             = "CUSTOMER"
    FRAUD_ANALYST        = "FRAUD_ANALYST"
    DISPUTE_INVESTIGATOR = "DISPUTE_INVESTIGATOR"
    COMPLIANCE_OFFICER   = "COMPLIANCE_OFFICER"
    OPERATIONS_ADMIN     = "OPERATIONS_ADMIN"


# ── Demo user store ────────────────────────────────────────────────────────────

DEMO_USERS = {
    "customer@bank.com": {
        "name": "Rahul Verma",
        "email": "customer@bank.com",
        "hashed_password": pwd_context.hash("customer123"),
        "role": Role.CUSTOMER,
        "customer_id": "CUST-DEMO-001",
    },
    "analyst@bank.com": {
        "name": "Sneha Kapoor",
        "email": "analyst@bank.com",
        "hashed_password": pwd_context.hash("analyst123"),
        "role": Role.FRAUD_ANALYST,
        "customer_id": None,
    },
    "investigator@bank.com": {
        "name": "Vikram Nair",
        "email": "investigator@bank.com",
        "hashed_password": pwd_context.hash("invest123"),
        "role": Role.DISPUTE_INVESTIGATOR,
        "customer_id": None,
    },
    "compliance@bank.com": {
        "name": "Anjali Mehta",
        "email": "compliance@bank.com",
        "hashed_password": pwd_context.hash("comply123"),
        "role": Role.COMPLIANCE_OFFICER,
        "customer_id": None,
    },
    "admin@bank.com": {
        "name": "Arjun Singh",
        "email": "admin@bank.com",
        "hashed_password": pwd_context.hash("admin123"),
        "role": Role.OPERATIONS_ADMIN,
        "customer_id": None,
    },
}

BANK_ROLES = {Role.FRAUD_ANALYST, Role.DISPUTE_INVESTIGATOR, Role.COMPLIANCE_OFFICER, Role.OPERATIONS_ADMIN}


# ── Auth helpers ───────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = DEMO_USERS.get(email.lower())
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

