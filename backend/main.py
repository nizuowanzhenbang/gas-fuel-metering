"""FastAPI 入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .auth import Role, hash_password
from .config import get_settings
from .database import SessionLocal, init_db
from .models.users import User
from .routers import alerts as alerts_router
from .routers import auth as auth_router
from .routers import dashboard as dashboard_router
from .routers import gas_sources as gas_sources_router
from .routers import gc_analyzers as gc_analyzers_router
from .routers import metering_stations as metering_stations_router
from .routers import readings as readings_router
from .routers import reconciliation as reconciliation_router
from .routers import upload as upload_router
from .routers import users as users_router
from .scheduler import shutdown_scheduler, start_scheduler

_settings = get_settings()


def ensure_default_admin() -> None:
    """用户表为空时按 .env 配置建第一个 ADMIN 账户，方便联调与首次登录。"""
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)):
            return
        admin = User(
            username=_settings.default_admin_username,
            password_hash=hash_password(_settings.default_admin_password),
            full_name=_settings.default_admin_full_name,
            role=Role.ADMIN.value,
            is_active=True,
        )
        db.add(admin)
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ensure_default_admin()
    if _settings.enable_scheduler:
        start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title="Gas Fuel Metering API",
    version="0.1.0",
    description="燃气电厂燃料计量与气源管理系统",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(gas_sources_router.router)
app.include_router(metering_stations_router.router)
app.include_router(gc_analyzers_router.router)
app.include_router(readings_router.router)
app.include_router(reconciliation_router.router)
app.include_router(alerts_router.router)
app.include_router(upload_router.router)
app.include_router(dashboard_router.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": _settings.app_name, "version": "0.1.0"}
