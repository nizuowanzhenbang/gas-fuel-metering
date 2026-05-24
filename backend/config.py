"""集中配置读取。生产部署时从 .env 注入。"""
from __future__ import annotations

from functools import lru_cache

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

    gas_turbine_base: str = "http://gas-turbine-performance:8011"
    fuel_procurement_base: str = "http://fuel-procurement:8005"
    equipment_inspection_base: str = "http://equipment-inspection:8006"
    emission_monitoring_base: str = "http://emission-monitoring:8008"
    plant_safety_base: str = "http://plant-safety:8004"


@lru_cache
def get_settings() -> Settings:
    return Settings()
