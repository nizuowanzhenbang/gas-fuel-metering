"""对账 API：质量检查先于容差判定，返回可复核的计量依据。"""
from typing import Annotated
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth import CurrentUser, DbSession, Role, require_roles, get_current_user
from ..models.gas_sources import GasSource
from ..models.metering_stations import MeteringStation
from ..schemas.reconciliation import (
    DailyReconciliationRequest, DailyReconciliationResponse,
    DualLoopReconciliationRequest, DualLoopReconciliationResponse,
)
from ..services.metering_quality import DataQualityError, day_window, dual_loop_volume, source_daily_volume
from ..services.business_day import current_policy
from ..utils.reconciliation import reconcile_daily, reconcile_dual_loop
from ..models import ReconciliationRun
from ..services import reconciliation_archive as archives

router = APIRouter(prefix='/api/reconciliation', tags=['reconciliation'])
require_reconciler = require_roles(Role.ADMIN, Role.METER_ENG, Role.ACCOUNTANT)


class RecalculateRequest(BaseModel):
    upstream_volume_nm3: float | None = Field(default=None, gt=0, allow_inf_nan=False)


def _run(db, run_id):
    run = db.get(ReconciliationRun, run_id)
    if not run:
        raise HTTPException(404, 'reconciliation run not found')
    return run


def _archive(db, source_id, business_date, upstream, username, parent=None):
    try:
        return archives.archive(db, source_id, business_date, upstream, username, parent)
    except DataQualityError as exc:
        raise HTTPException(409, exc.detail()) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/runs', status_code=201)
def create_run(payload: DailyReconciliationRequest, db: DbSession,
               user: Annotated[CurrentUser, Depends(require_reconciler)]):
    return _archive(db, payload.source_id, payload.business_date, payload.upstream_volume_nm3, user.username)


@router.get('/runs')
def list_runs(db: DbSession, _: Annotated[CurrentUser, Depends(get_current_user)],
              source_id: int | None = None, business_date: date | None = None,
              limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    query = select(ReconciliationRun)
    if source_id is not None:
        query = query.where(ReconciliationRun.source_id == source_id)
    if business_date is not None:
        query = query.where(ReconciliationRun.business_date == business_date)
    runs = db.scalars(query.order_by(ReconciliationRun.created_at.desc(), ReconciliationRun.id).offset(offset).limit(limit))
    return [archives.public(run, full=False) for run in runs]


@router.get('/runs/{run_id}')
def get_run(run_id: str, db: DbSession, _: Annotated[CurrentUser, Depends(get_current_user)]):
    return archives.public(_run(db, run_id))


@router.get('/runs/{run_id}/verify')
def verify_run(run_id: str, db: DbSession, _: Annotated[CurrentUser, Depends(get_current_user)]):
    try:
        archives.verify(_run(db, run_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'matches': True}


@router.post('/runs/{run_id}/recalculate', status_code=201)
def recalculate_run(run_id: str, payload: RecalculateRequest, db: DbSession,
                    user: Annotated[CurrentUser, Depends(require_reconciler)]):
    parent = _run(db, run_id)
    upstream = payload.upstream_volume_nm3 if payload.upstream_volume_nm3 is not None else parent.snapshot_json['upstream_volume_nm3']
    return _archive(db, parent.source_id, parent.business_date, upstream, user.username, parent)


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
        business_date=payload.business_date, **vars(result), sample_count=count, stations=evidence, window=current_policy().window(payload.business_date))


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
        backup_sample_count=backup.sample_count, stations=[primary, backup], window=current_policy().window(payload.business_date))


@router.get('/policy')
def reconciliation_policy(_: Annotated[CurrentUser, Depends(get_current_user)]):
    policy = current_policy()
    return {**policy.model_dump(), "latest_completed_date": policy.latest_completed_date(datetime.now(timezone.utc))}
