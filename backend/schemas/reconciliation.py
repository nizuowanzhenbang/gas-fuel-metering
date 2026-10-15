"""对账 schema。

业务约定：
- 日对账请求体 = 气源 + 业务日期 + 上游日报量；后端按该气源下所有计量站的
  主用回路 VALID 读数，必须具备配置业务日的首末边界，检查单调性后按末值减首值聚合。
- 主备回路对账请求体 = 计量站 + 业务日期；后端分别聚合 PRIMARY / BACKUP
  读数，调 utils.reconciliation.reconcile_dual_loop。
- 业务日期按配置的固定偏移与日切解释，读数 ts 仍为UTC。
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ..services.business_day import BusinessWindow
from ..utils.reconciliation import Verdict
from ..services.metering_quality import MeteringEvidence


class DailyReconciliationRequest(BaseModel):
    source_id: int
    business_date: date
    upstream_volume_nm3: float = Field(gt=0, allow_inf_nan=False, description="上游公司日报量，作为对账基准")


class DailyReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: int
    source_code: str
    business_date: date
    plant_volume_nm3: float
    upstream_volume_nm3: float
    absolute_diff_nm3: float
    relative_diff_pct: float
    tolerance_pct: float
    verdict: Verdict
    reason: str
    sample_count: int = Field(description="参与聚合的有效读数条数")
    stations: list[MeteringEvidence]
    window: BusinessWindow


class DualLoopReconciliationRequest(BaseModel):
    station_id: int
    business_date: date


class DualLoopReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    station_id: int
    station_code: str
    business_date: date
    primary_volume_nm3: float
    backup_volume_nm3: float
    absolute_diff_nm3: float
    relative_diff_pct: float
    tolerance_pct: float
    verdict: Verdict
    reason: str
    primary_sample_count: int
    backup_sample_count: int
    stations: list[MeteringEvidence]
    window: BusinessWindow
