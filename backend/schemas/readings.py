"""时序读数 schema。

设计原则：创建时只接收原始观测量（工况体积/压力/温度、组分摩尔百分比），
后端调 utils 自动算补偿后的标准体积 / HHV / LHV / Wobbe / 密度，避免上位机
错算后污染历史。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.metering_readings import MeteringSource, Validity


class MeteringReadingCreate(BaseModel):
    station_id: int
    ts: datetime
    actual_volume_rate_m3h: float = Field(ge=0)
    gauge_pressure_kpa: float = Field(description="表压，可为负（真空）")
    temperature_c: float
    accumulated_volume_nm3: float = Field(ge=0, description="DCS 上报的累计量，后端不再累加")
    atmospheric_kpa: float | None = Field(default=None, gt=0, description="缺省取 101.325")
    validity: Validity = Validity.VALID
    source: MeteringSource = MeteringSource.PRIMARY


class MeteringReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    ts: datetime
    actual_volume_rate_m3h: float
    normal_volume_rate_nm3h: float
    pressure_kpa: float
    temperature_c: float
    accumulated_volume_nm3: float
    validity: Validity
    source: MeteringSource
    created_at: datetime


class GCReadingCreate(BaseModel):
    gc_id: int
    station_id: int | None = None
    ts: datetime
    ch4_pct: float = Field(ge=0, le=100)
    c2h6_pct: float = Field(default=0.0, ge=0, le=100)
    c3h8_pct: float = Field(default=0.0, ge=0, le=100)
    ic4h10_pct: float = Field(default=0.0, ge=0, le=100)
    nc4h10_pct: float = Field(default=0.0, ge=0, le=100)
    n2_pct: float = Field(default=0.0, ge=0, le=100)
    co2_pct: float = Field(default=0.0, ge=0, le=100)
    others_pct: float = Field(default=0.0, ge=0, le=100)
    validity: Validity = Validity.VALID


class GCReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gc_id: int
    station_id: int | None
    ts: datetime
    ch4_pct: float
    c2h6_pct: float
    c3h8_pct: float
    ic4h10_pct: float
    nc4h10_pct: float
    n2_pct: float
    co2_pct: float
    others_pct: float
    hhv_mj_nm3: float
    lhv_mj_nm3: float
    wobbe_mj_nm3: float
    density_kg_nm3: float
    validity: Validity
    created_at: datetime
