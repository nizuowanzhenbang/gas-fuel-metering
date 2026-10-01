"""Versioned daily input snapshots. Hashes detect differences, not authenticity."""
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import and_, select

from ..models import GasSource, MeteringReading, MeteringStation, ReconciliationRun
from ..utils import reconciliation as math
from .business_day import BusinessDayPolicy, BusinessWindow, current_policy
from .metering_quality import as_utc, reading_evidence, DataQualityError


def digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def replay(snapshot):
    if snapshot['algorithm']['version'] != 'daily-volume-v1':
        raise ValueError('unsupported archive algorithm')
    window = BusinessWindow.model_validate(snapshot['window'])
    evidence = []
    for station in snapshot['stations']:
        rows = [SimpleNamespace(ts=datetime.fromisoformat(r['ts']),
                                accumulated_volume_nm3=Decimal(r['counter']), validity=r['validity'])
                for r in station['readings']]
        evidence.append(reading_evidence(rows, station['id'], 'PRIMARY', window.start_utc,
                                         window.end_utc, full_day=True))
    if not evidence:
        raise ValueError('gas source has no metering stations bound; nothing to reconcile')
    if any(e.issues for e in evidence):
        raise DataQualityError(evidence)
    total = float(sum((Decimal(str(e.volume_nm3)) for e in evidence), Decimal(0)))
    result = vars(math._reconcile(total, snapshot['upstream_volume_nm3'],
                                 snapshot['algorithm']['tolerance_pct'], snapshot['algorithm']['fail_multiplier']))
    return {**result, 'sample_count': sum(e.sample_count for e in evidence),
            'stations': [e.model_dump(mode='json') for e in evidence]}


def verify(run):
    if digest(run.snapshot_json) != run.snapshot_sha256 or replay(run.snapshot_json) != run.snapshot_json['result']:
        raise ValueError('archive hash or replay result mismatch')


def public(run, *, full=True):
    data = dict(id=run.id, parent_run_id=run.parent_run_id, source_id=run.source_id,
                business_date=run.business_date, created_at=as_utc(run.created_at),
                created_by=run.created_by, snapshot_sha256=run.snapshot_sha256)
    data['snapshot' if full else 'result'] = run.snapshot_json if full else run.snapshot_json['result']
    return data


def archive(db, source_id, business_date, upstream, username, parent=None):
    if parent:
        verify(parent)
    policy = BusinessDayPolicy.model_validate(parent.snapshot_json['window']['policy']) if parent else current_policy()
    window = policy.window(business_date)
    # Source identity, station membership and input readings captured in one statement.
    rows = db.execute(select(GasSource.id, GasSource.code, MeteringStation.id, MeteringStation.code,
                             MeteringReading.id, MeteringReading.ts, MeteringReading.accumulated_volume_nm3,
                             MeteringReading.validity)
        .outerjoin(MeteringStation, MeteringStation.source_id == GasSource.id)
        .outerjoin(MeteringReading, and_(MeteringReading.station_id == MeteringStation.id,
                   MeteringReading.source == 'PRIMARY', MeteringReading.ts >= window.start_utc,
                   MeteringReading.ts <= window.end_utc))
        .where(GasSource.id == source_id)
        .order_by(MeteringStation.id, MeteringReading.ts, MeteringReading.id)).all()
    if not rows:
        raise ValueError('gas source not found')
    stations = {}
    for _, _, station_id, code, rid, ts, counter, validity in rows:
        if station_id is None:
            continue
        station = stations.setdefault(station_id, dict(id=station_id, code=code, source='PRIMARY', readings=[]))
        if rid is not None:
            station['readings'].append(dict(id=rid, ts=as_utc(ts).isoformat(), counter=str(counter), validity=validity))
    snapshot = dict(source_id=source_id, source_code=rows[0][1], business_date=business_date.isoformat(),
                    upstream_volume_nm3=upstream, window=window.model_dump(mode='json'),
                    stations=list(stations.values()),
                    algorithm=dict(parent.snapshot_json['algorithm']) if parent else dict(
                        version='daily-volume-v1', tolerance_pct=math.DAILY_TOLERANCE_PCT, fail_multiplier=math.FAIL_MULTIPLIER))
    snapshot['result'] = replay(snapshot)
    snapshot['delta_plant_nm3'] = (snapshot['result']['plant_volume_nm3'] -
                                 parent.snapshot_json['result']['plant_volume_nm3']) if parent else None
    run = ReconciliationRun(id=str(uuid4()), parent_run_id=parent.id if parent else None,
                            source_id=source_id, business_date=business_date,
                            created_at=datetime.now(timezone.utc), created_by=username,
                            snapshot_json=snapshot, snapshot_sha256=digest(snapshot))
    db.add(run)
    db.commit()
    db.refresh(run)
    return public(run)
