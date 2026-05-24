"""计量站档案 schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models.metering_stations import StationStatus


class MeteringStationCreate(BaseModel):
    code: str = Field(pattern=r"^MS-\d{2}$", description="编号 MS-NN")
    name: str = Field(min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    source_id: int | None = None
    design_pressure_kpa: float = Field(gt=0)
    design_flow_min_nm3h: float = Field(ge=0)
    design_flow_max_nm3h: float = Field(gt=0)
    verified_until: datetime | None = None

    @model_validator(mode="after")
    def _check_flow_range(self):
        if self.design_flow_max_nm3h <= self.design_flow_min_nm3h:
            raise ValueError("design_flow_max must be greater than design_flow_min")
        return self


class MeteringStationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    source_id: int | None = None
    design_pressure_kpa: float | None = Field(default=None, gt=0)
    design_flow_min_nm3h: float | None = Field(default=None, ge=0)
    design_flow_max_nm3h: float | None = Field(default=None, gt=0)
    verified_until: datetime | None = None
    status: StationStatus | None = None


class MeteringStationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    location: str | None
    source_id: int | None
    design_pressure_kpa: float
    design_flow_min_nm3h: float
    design_flow_max_nm3h: float
    verified_until: datetime | None
    status: StationStatus
    created_at: datetime
