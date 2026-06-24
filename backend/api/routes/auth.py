"""
Authentication routes — login and current user info.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from auth.auth import authenticate_user, create_access_token
from auth.dependencies import get_current_user
from schemas.auth_schemas import LoginRequest, TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = authenticate_user(body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": user["email"], "role": user["role"].value})
    return TokenResponse(
        access_token=token,
        role=user["role"].value,
        name=user["name"],
        email=user["email"],
        customer_id=user.get("customer_id"),
    )


@router.get("/me", response_model=UserInfo)
def me(user: dict = Depends(get_current_user)):
    return UserInfo(
        email=user["email"],
        name=user["name"],
        role=user["role"].value,
        customer_id=user.get("customer_id"),
    )

