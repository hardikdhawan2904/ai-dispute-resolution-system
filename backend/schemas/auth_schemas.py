"""
Auth request/response schemas.
"""
from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    email: str
    customer_id: Optional[str] = None


class UserInfo(BaseModel):
    email: str
    name: str
    role: str
    customer_id: Optional[str] = None
