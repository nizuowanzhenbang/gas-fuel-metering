"""对账 API：质量检查先于容差判定，返回可复核的计量依据。"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..auth import CurrentUser, DbSession, Role, require_roles
from ..models.gas_sources import GasSource
from ..models.metering_stations import MeteringStation
from ..schemas.reconciliation import (
    DailyReconciliationRequest, DailyReconciliationResponse,
    DualLoopReconciliationRequest, DualLoopReconciliationResponse,
)
from ..services.metering_quality import DataQualityError, day_window, dual_loop_volume, source_daily_volume
from ..utils.reconciliation import reconcile_daily, reconcile_dual_loop

router = APIRouter(prefix='/api/reconciliation', tags=['reconciliation'])
require_reconciler = require_roles(Role.ADMIN, Role.METER_ENG, Role.ACCOUNTANT)


@router.post('/daily', response_model=DailyReconciliationResponse)
def reconcile_daily_endpoint(payload: DailyReconciliationRequest, db: DbSession,
    _: Annotated[CurrentUser, Depends(require_reconciler)]) -> DailyReconciliationResponse:
    source = db.get(GasSource, payload.source_id)
    if not source:
        raise HTTPException(404, 'gas source not found')
    try:
        total, count, evidence = source_daily_volume(db, source.id, payload.business_date)
        result = reconcile_daily(total, payload.upstream_volume_nm3)
    except DataQualityError as exc:
        raise HTTPException(409, exc.detail()) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return DailyReconciliationResponse(source_id=source.id, source_code=source.code,
        business_date=payload.business_date, **vars(result), sample_count=count, stations=evidence)


@router.post('/dual-loop', response_model=DualLoopReconciliationResponse)
def reconcile_dual_loop_endpoint(payload: DualLoopReconciliationRequest, db: DbSession,
    _: Annotated[CurrentUser, Depends(require_reconciler)]) -> DualLoopReconciliationResponse:
    station = db.get(MeteringStation, payload.station_id)
    if not station:
        raise HTTPException(404, 'metering station not found')
    try:
        start, end = day_window(payload.business_date)
        primary, backup = dual_loop_volume(db, station.id, start, end)
        result = reconcile_dual_loop(primary.volume_nm3, backup.volume_nm3)
    except DataQualityError as exc:
        raise HTTPException(409, exc.detail()) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return DualLoopReconciliationResponse(station_id=station.id, station_code=station.code,
        business_date=payload.business_date, **vars(result), primary_sample_count=primary.sample_count,
        backup_sample_count=backup.sample_count, stations=[primary, backup])
