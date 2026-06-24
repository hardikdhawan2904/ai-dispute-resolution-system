"""
FastAPI dependency injection for authentication and role-based access control.
"""
from typing import Optional, Set
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth.auth import decode_token, DEMO_USERS, Role, BANK_ROLES

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("sub")
    user = DEMO_USERS.get(email or "")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


def require_roles(allowed: Set[Role]):
    """Factory that returns a dependency enforcing one of the allowed roles."""
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied — required roles: {[r.value for r in allowed]}",
            )
        return user
    return _check


# ── Convenience role guards ────────────────────────────────────────────────────

def bank_staff_only(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in BANK_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bank staff access only")
    return user


def customer_only(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != Role.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer access only")
    return user


def analyst_or_above(user: dict = Depends(get_current_user)) -> dict:
    allowed = {Role.FRAUD_ANALYST, Role.DISPUTE_INVESTIGATOR, Role.COMPLIANCE_OFFICER, Role.OPERATIONS_ADMIN}
    if user["role"] not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Analyst or above required")
    return user


def admin_only(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != Role.OPERATIONS_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access only")
    return user

