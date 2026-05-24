"""JWT 签发/校验 + 5 角色 RBAC 依赖。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db

_settings = get_settings()
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# bcrypt 单算法 72 字节上限，预先 SHA-256 摘要再编 base64，
# 既绕过长度限制又不依赖已停更的 passlib。
import base64
import hashlib


def _prepare(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.b64encode(digest)


class Role(StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    METER_ENG = "METER_ENG"
    ACCOUNTANT = "ACCOUNTANT"
    VIEWER = "VIEWER"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(subject: str, role: Role, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or _settings.jwt_expire_minutes
    )
    payload = {"sub": subject, "role": role.value, "exp": expire}
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


class CurrentUser:
    """从 JWT 解出的当前用户信息。"""

    def __init__(self, username: str, role: Role):
        self.username = username
        self.role = role

    def __repr__(self) -> str:  # pragma: no cover
        return f"CurrentUser({self.username!r}, {self.role.value})"


def get_current_user(token: Annotated[str | None, Depends(_oauth2)]) -> CurrentUser:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    username = payload.get("sub")
    role_value = payload.get("role")
    if not username or not role_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed token")
    try:
        role = Role(role_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown role") from exc
    return CurrentUser(username=username, role=role)


def require_roles(*allowed: Role):
    """生成"必须是 allowed 中任一角色"的依赖。"""

    def _checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role {user.role.value} not allowed",
            )
        return user

    return _checker


require_admin = require_roles(Role.ADMIN)
require_meter_eng = require_roles(Role.ADMIN, Role.METER_ENG)
require_accountant = require_roles(Role.ADMIN, Role.ACCOUNTANT)
# 时序读数录入：运行人员、计量工程师、管理员都允许
require_operator = require_roles(Role.ADMIN, Role.METER_ENG, Role.OPERATOR)


def verify_integration_secret(header_value: str | None) -> None:
    """跨系统调用的暗号校验。"""
    if header_value != _settings.integration_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad integration secret")


DbSession = Annotated[Session, Depends(get_db)]
