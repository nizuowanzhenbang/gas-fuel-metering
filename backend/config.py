"""集中配置读取。生产部署时从 .env 注入。"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "gas-fuel-metering"
    app_port: int = 8010

    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    database_url: str = "sqlite:///./gas_fuel.db"

    integration_secret: str = "dev-integration-secret"

    # 启动 ensure：用户表为空时建第一个 ADMIN 账户。生产 .env 必须覆盖。
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"
    default_admin_full_name: str = "默认管理员"

    enable_scheduler: bool = True  # 测试环境通过 .env 关闭
    business_timezone: Literal['UTC', 'UTC+08:00'] = 'UTC'
    business_day_start_minute: int = Field(default=0, ge=0, le=1439)

    gas_turbine_base: str = "http://gas-turbine-performance:8011"
    fuel_procurement_base: str = "http://fuel-procurement:8005"
    equipment_inspection_base: str = "http://equipment-inspection:8006"
    emission_monitoring_base: str = "http://emission-monitoring:8008"
    plant_safety_base: str = "http://plant-safety:8004"


@lru_cache
def get_settings() -> Settings:
    return Settings()
