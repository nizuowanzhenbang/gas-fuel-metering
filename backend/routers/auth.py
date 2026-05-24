"""认证路由：登录换 JWT。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from ..auth import DbSession, Role, create_access_token, verify_password
from ..config import get_settings
from ..models.users import User
from ..schemas.auth import TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> TokenResponse:
    """OAuth2 password flow，方便 Swagger UI 直接登录。"""
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    role = Role(user.role) if not isinstance(user.role, Role) else user.role
    token = create_access_token(subject=user.username, role=role)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_expire_minutes,
        role=role,
        username=user.username,
    )
