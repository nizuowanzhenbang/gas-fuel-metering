"""scheduler job 函数的逻辑单测。

不启动 BackgroundScheduler，只调 job 函数本体，
验证：扫描出问题时调用 emit_alert，符合容差时不写告警，去重不开重复单。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models  # noqa: F401
from backend.database import Base
from backend.models.alerts import Alert, AlertCategory, AlertStatus
from backend.models.gc_analyzers import GCAnalyzer, GCStatus
from backend.models.metering_readings import MeteringReading, MeteringSource, Validity
from backend.models.metering_stations import MeteringStation, StationStatus
from sqlalchemy import create_engine

import pytest


@pytest.fixture
def engine_and_session_factory():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Factory = sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)
    yield eng, Factory
    eng.dispose()


@pytest.fixture
def patched_session(engine_and_session_factory):
    _, Factory = engine_and_session_factory
    with patch("backend.scheduler.SessionLocal", Factory):
        yield Factory


def _add_station(db, **kw):
    st = MeteringStation(
        code=kw.get("code", "MS-01"),
        name=kw.get("name", "S1"),
        design_pressure_kpa=3500.0,
        design_flow_min_nm3h=5000.0,
        design_flow_max_nm3h=50000.0,
        status=kw.get("status", StationStatus.RUNNING),
        verified_until=kw.get("verified_until"),
    )
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def _add_reading(db, st_id, ts, accum, src=MeteringSource.PRIMARY):
    db.add(
        MeteringReading(
            station_id=st_id,
            ts=ts,
            actual_volume_rate_m3h=1000.0,
            normal_volume_rate_nm3h=900.0,
            pressure_kpa=1500.0,
            temperature_c=20.0,
            accumulated_volume_nm3=accum,
            validity=Validity.VALID,
            source=src,
        )
    )
    db.commit()


def test_primary_backup_no_alert_when_within_tolerance(patched_session):
    from backend.scheduler import scan_primary_backup_deviation

    Factory = patched_session
    with Factory() as db:
        st = _add_station(db)
        now = datetime.now(timezone.utc)
        # 主备一小时各 +500，差 0%
        _add_reading(db, st.id, now - timedelta(minutes=50), 1_000_000.0, MeteringSource.PRIMARY)
        _add_reading(db, st.id, now - timedelta(minutes=1), 1_000_500.0, MeteringSource.PRIMARY)
        _add_reading(db, st.id, now - timedelta(minutes=50), 1_000_000.0, MeteringSource.BACKUP)
        _add_reading(db, st.id, now - timedelta(minutes=1), 1_000_500.0, MeteringSource.BACKUP)

    fired = scan_primary_backup_deviation()
    assert fired == 0
    with Factory() as db:
        assert db.scalar(select(Alert).limit(1)) is None


def test_counter_reset_does_not_create_misleading_deviation_alert(patched_session, caplog):
    from backend.scheduler import scan_primary_backup_deviation
    with patched_session() as db:
        st = _add_station(db)
        now = datetime.now(timezone.utc)
        for minutes, value in [(50, 1000), (25, 10), (1, 1100)]:
            _add_reading(db, st.id, now - timedelta(minutes=minutes), value, MeteringSource.PRIMARY)
        for minutes, value in [(50, 1000), (1, 1100)]:
            _add_reading(db, st.id, now - timedelta(minutes=minutes), value, MeteringSource.BACKUP)
    assert scan_primary_backup_deviation() == 0
    assert 'COUNTER_ROLLBACK' in caplog.text
    with patched_session() as db:
        assert db.scalar(select(Alert)) is None


def test_primary_backup_fires_alert_when_diff_exceeds_double_tolerance(patched_session):
    from backend.scheduler import scan_primary_backup_deviation

    Factory = patched_session
    with Factory() as db:
        st = _add_station(db)
        now = datetime.now(timezone.utc)
        _add_reading(db, st.id, now - timedelta(minutes=50), 1_000_000.0, MeteringSource.PRIMARY)
        _add_reading(db, st.id, now - timedelta(minutes=1), 1_001_000.0, MeteringSource.PRIMARY)
        _add_reading(db, st.id, now - timedelta(minutes=50), 1_000_000.0, MeteringSource.BACKUP)
        _add_reading(db, st.id, now - timedelta(minutes=1), 1_010_000.0, MeteringSource.BACKUP)  # 大偏差

    fired = scan_primary_backup_deviation()
    assert fired == 1
    with Factory() as db:
        alert = db.scalar(select(Alert))
        assert alert.category == AlertCategory.PRIMARY_BACKUP_DEVIATION
        assert alert.level == "CRITICAL"


def test_primary_backup_deduplicates_repeated_runs(patched_session):
    from backend.scheduler import scan_primary_backup_deviation

    Factory = patched_session
    with Factory() as db:
        st = _add_station(db)
        now = datetime.now(timezone.utc)
        _add_reading(db, st.id, now - timedelta(minutes=50), 1_000_000.0, MeteringSource.PRIMARY)
        _add_reading(db, st.id, now - timedelta(minutes=1), 1_001_000.0, MeteringSource.PRIMARY)
        _add_reading(db, st.id, now - timedelta(minutes=50), 1_000_000.0, MeteringSource.BACKUP)
        _add_reading(db, st.id, now - timedelta(minutes=1), 1_010_000.0, MeteringSource.BACKUP)

    scan_primary_backup_deviation()
    scan_primary_backup_deviation()
    with Factory() as db:
        opens = db.scalars(
            select(Alert).where(Alert.status == AlertStatus.OPEN)
        ).all()
        assert len(opens) == 1


def test_gc_status_fault_fires_critical(patched_session):
    from backend.scheduler import scan_gc_status

    Factory = patched_session
    with Factory() as db:
        gc = GCAnalyzer(code="GC-01", model="ABB NGC8200", status=GCStatus.FAULT)
        db.add(gc)
        db.commit()

    fired = scan_gc_status()
    assert fired == 1
    with Factory() as db:
        alert = db.scalar(select(Alert))
        assert alert.category == AlertCategory.GC_FAULT
        assert alert.level == "CRITICAL"


def test_gc_calibration_due_within_7d_fires_warn(patched_session):
    from backend.scheduler import scan_gc_status

    Factory = patched_session
    with Factory() as db:
        gc = GCAnalyzer(
            code="GC-02",
            model="ABB NGC8200",
            status=GCStatus.RUNNING,
            next_calibration_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db.add(gc)
        db.commit()

    fired = scan_gc_status()
    assert fired == 1
    with Factory() as db:
        alert = db.scalar(select(Alert))
        assert alert.category == AlertCategory.GC_CALIBRATION_DUE
        assert alert.level == "WARN"


def test_meter_verification_due_30d_warning(patched_session):
    from backend.scheduler import scan_meter_verification_due

    Factory = patched_session
    with Factory() as db:
        _add_station(
            db,
            code="MS-10",
            verified_until=datetime.now(timezone.utc) + timedelta(days=20),
        )
        # 远期不会触发
        _add_station(
            db,
            code="MS-11",
            verified_until=datetime.now(timezone.utc) + timedelta(days=180),
        )

    fired = scan_meter_verification_due()
    assert fired == 1
    with Factory() as db:
        alert = db.scalar(select(Alert))
        assert alert.station_id is not None
        assert alert.category == AlertCategory.METER_VERIFICATION_DUE
