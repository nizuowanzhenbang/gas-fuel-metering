"""router 集成测试公共 fixture。

每个测试函数独享一个 in-memory SQLite（StaticPool 让 router 与 fixture 共享同一连接），
不进入 app lifespan（避免污染本地 sqlite 文件），由 fixture 自己 seed 用户与表。
"""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models  # noqa: F401  确保所有 ORM 注册到 Base.metadata
from backend.auth import Role, hash_password
from backend.database import Base, get_db
from backend.main import app
from backend.models.users import User


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session_factory(engine: Engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture
def client(session_factory) -> Generator[TestClient, None, None]:
    def _override_get_db():
        db: Session = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_user(session_factory, username: str, password: str, role: Role) -> None:
    with session_factory() as db:
        db.add(
            User(
                username=username,
                password_hash=hash_password(password),
                full_name=username.upper(),
                role=role.value,
                is_active=True,
            )
        )
        db.commit()


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin_headers(client, session_factory) -> dict[str, str]:
    _create_user(session_factory, "admin", "admin123", Role.ADMIN)
    return {"Authorization": f"Bearer {_login(client, 'admin', 'admin123')}"}


@pytest.fixture
def meter_eng_headers(client, session_factory) -> dict[str, str]:
    _create_user(session_factory, "engineer", "eng123", Role.METER_ENG)
    return {"Authorization": f"Bearer {_login(client, 'engineer', 'eng123')}"}


@pytest.fixture
def viewer_headers(client, session_factory) -> dict[str, str]:
    _create_user(session_factory, "viewer", "view123", Role.VIEWER)
    return {"Authorization": f"Bearer {_login(client, 'viewer', 'view123')}"}
