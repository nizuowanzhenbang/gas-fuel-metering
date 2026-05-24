"""Pydantic schema 集中导出。

v0.1 覆盖范围：认证 + 档案三件套（气源 / 计量站 / GC）+ 时序读数（计量 / GC）。
对账、告警等 schema 待路由层接入时再补。
"""
from .auth import LoginRequest, TokenResponse
from .common import PagedResult, PageParams
from .gas_sources import GasSourceCreate, GasSourceRead, GasSourceUpdate
from .gc_analyzers import GCAnalyzerCreate, GCAnalyzerRead, GCAnalyzerUpdate
from .metering_stations import (
    MeteringStationCreate,
    MeteringStationRead,
    MeteringStationUpdate,
)
from .readings import (
    GCReadingCreate,
    GCReadingRead,
    MeteringReadingCreate,
    MeteringReadingRead,
)

__all__ = [
    "GCAnalyzerCreate",
    "GCAnalyzerRead",
    "GCAnalyzerUpdate",
    "GCReadingCreate",
    "GCReadingRead",
    "GasSourceCreate",
    "GasSourceRead",
    "GasSourceUpdate",
    "LoginRequest",
    "MeteringReadingCreate",
    "MeteringReadingRead",
    "MeteringStationCreate",
    "MeteringStationRead",
    "MeteringStationUpdate",
    "PageParams",
    "PagedResult",
    "TokenResponse",
]
