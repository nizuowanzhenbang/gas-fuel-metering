"""气源档案 schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.gas_sources import GasSourceStatus, GasType


class GasSourceCreate(BaseModel):
    code: str = Field(pattern=r"^SRC-\d{3}$", description="编号 SRC-NNN")
    name: str = Field(min_length=1, max_length=128)
    supplier: str = Field(min_length=1, max_length=64)
    gas_type: GasType
    contract_no: str | None = None
    contract_base_price: float | None = Field(default=None, ge=0)
    daily_volume_plan_nm3: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=512)


class GasSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    supplier: str | None = Field(default=None, min_length=1, max_length=64)
    contract_no: str | None = None
    contract_base_price: float | None = Field(default=None, ge=0)
    daily_volume_plan_nm3: float | None = Field(default=None, ge=0)
    status: GasSourceStatus | None = None
    notes: str | None = Field(default=None, max_length=512)


class GasSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    supplier: str
    gas_type: GasType
    contract_no: str | None
    contract_base_price: float | None
    daily_volume_plan_nm3: float | None
    status: GasSourceStatus
    notes: str | None
    created_at: datetime
