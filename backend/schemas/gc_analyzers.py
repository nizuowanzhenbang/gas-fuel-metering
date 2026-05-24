"""GC 档案 schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.gc_analyzers import GCStatus


class GCAnalyzerCreate(BaseModel):
    code: str = Field(pattern=r"^GC-\d{2}$", description="编号 GC-NN")
    model: str = Field(min_length=1, max_length=64, description="型号，例如 Daniel 700XA")
    serial_no: str | None = Field(default=None, max_length=64)
    station_id: int | None = None
    last_calibration_at: datetime | None = None
    next_calibration_at: datetime | None = None


class GCAnalyzerUpdate(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=64)
    serial_no: str | None = Field(default=None, max_length=64)
    station_id: int | None = None
    last_calibration_at: datetime | None = None
    next_calibration_at: datetime | None = None
    status: GCStatus | None = None


class GCAnalyzerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    model: str
    serial_no: str | None
    station_id: int | None
    last_calibration_at: datetime | None
    next_calibration_at: datetime | None
    status: GCStatus
    created_at: datetime
