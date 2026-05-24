"""认证相关 schema。"""
from __future__ import annotations

from pydantic import BaseModel

from ..auth import Role


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    role: Role
    username: str
