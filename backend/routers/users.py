"""账户管理路由 —— 仅 ADMIN。

设计要点：
- 新增 / 修改 / 重置密码 / 软停用全部走 ADMIN 鉴权。
- 删除 = 软停用（`is_active=False`），防止已签发 JWT 立即失效后历史记录链路断裂。
- 不返回 password_hash；重置密码独立端点，避免在通用 PATCH 里混读敏感字段。
- ADMIN 不能停用 / 降级自己，避免误锁定唯一管理员。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from ..auth import CurrentUser, DbSession, Role, hash_password, require_admin
from ..models.users import User
from ..schemas.common import PagedResult
from ..schemas.users import PasswordResetRequest, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


def _to_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=Role(user.role) if not isinstance(user.role, Role) else user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _load_self(db, current: CurrentUser) -> User:
    obj = db.scalar(select(User).where(User.username == current.username))
    if not obj:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="current user not found")
    return obj


@router.get("", response_model=PagedResult[UserRead])
def list_users(
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_admin)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    role: Role | None = Query(None),
    is_active: bool | None = Query(None),
) -> PagedResult[UserRead]:
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if role is not None:
        stmt = stmt.where(User.role == role.value)
        count_stmt = count_stmt.where(User.role == role.value)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
        count_stmt = count_stmt.where(User.is_active == is_active)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(User.username).offset((page - 1) * size).limit(size)).all()
    return PagedResult[UserRead](
        total=total,
        page=page,
        size=size,
        items=[_to_read(r) for r in rows],
    )


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> UserRead:
    obj = db.get(User, user_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return _to_read(obj)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> UserRead:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"username {payload.username} already exists",
        )
    obj = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role.value,
        is_active=True,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _to_read(obj)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(require_admin)],
) -> UserRead:
    obj = db.get(User, user_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    data = payload.model_dump(exclude_unset=True)

    if obj.username == current.username:
        if data.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cannot deactivate yourself",
            )
        new_role = data.get("role")
        if new_role is not None and Role(new_role) != Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cannot demote yourself from ADMIN",
            )

    for k, v in data.items():
        if k == "role" and v is not None:
            obj.role = Role(v).value
        else:
            setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return _to_read(obj)


@router.post("/{user_id}/reset-password", response_model=UserRead)
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    db: DbSession,
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> UserRead:
    obj = db.get(User, user_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    obj.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(obj)
    return _to_read(obj)


@router.delete("/{user_id}", response_model=UserRead)
def deactivate_user(
    user_id: int,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(require_admin)],
) -> UserRead:
    """软停用：is_active=False，账户保留以维持历史 FK 链路。"""
    obj = db.get(User, user_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if obj.username == current.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot deactivate yourself",
        )
    obj.is_active = False
    db.commit()
    db.refresh(obj)
    return _to_read(obj)
