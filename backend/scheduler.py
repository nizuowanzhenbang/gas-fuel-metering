"""APScheduler 定时任务编排。

四类任务（CLAUDE.md 约定）：
1. 每分钟扫描主备计量偏差 → 超 0.3% 写 PRIMARY_BACKUP_DEVIATION 告警
2. 每 5 分钟扫描 GC 状态 → CALIBRATING/FAULT 持续超阈值写 GC_FAULT/GC_CALIBRATION_DUE
3. 每天 08:00 扫描计量器具检定到期（30 天预警）→ METER_VERIFICATION_DUE
4. 每个业务日结束5分钟后 触发 **最近完整业务日** 主备回路自查（实际三方对账依赖上游日报，由 upload router 触发）

启动方式：main.py lifespan 内 start()，停机 shutdown()。
单元测试不启动调度，但 job 函数本身可直接被测试调用。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .database import SessionLocal
from .services.business_day import current_policy
from .models.alerts import AlertCategory, AlertLevel
from .models.gc_analyzers import GCAnalyzer, GCStatus
from .models.metering_readings import MeteringReading, MeteringSource, Validity
from .models.metering_stations import MeteringStation, StationStatus
from .services.alerting import emit_alert
from .utils.reconciliation import reconcile_dual_loop
from .services.metering_quality import DataQualityError, dual_loop_volume

logger = logging.getLogger(__name__)

PRIMARY_BACKUP_TOLERANCE_PCT = 0.3
GC_CALIBRATION_WARN_DAYS = 7
VERIFICATION_WARN_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """SQLite 取出来的 datetime 可能丢 tzinfo，统一按 UTC 补齐。"""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def scan_primary_backup_deviation() -> int:
    """每分钟：对每个 RUNNING 站点比较 **过去 1 小时** 内主备累计差。

    1 小时窗口让短期采样噪音被平滑，又不会让长时间偏差被掩盖。
    """
    fired = 0
    end = _now()
    start = end - timedelta(hours=1)
    with SessionLocal() as db:
        stations = db.scalars(
            select(MeteringStation).where(MeteringStation.status == StationStatus.RUNNING)
        ).all()
        for st in stations:
            try:
                primary, backup = dual_loop_volume(db, st.id, start, end, full_day=False)
            except DataQualityError as exc:
                logger.warning('%s: %s', st.code, exc)
                continue
            primary_vol = primary.volume_nm3
            backup_vol = backup.volume_nm3
            if primary_vol <= 0 or backup_vol <= 0:
                continue

            verdict = reconcile_dual_loop(primary_vol, backup_vol)
            if verdict.verdict.value in ("WARN", "FAIL"):
                level = AlertLevel.CRITICAL if verdict.verdict.value == "FAIL" else AlertLevel.WARN
                emit_alert(
                    db,
                    level=level,
                    category=AlertCategory.PRIMARY_BACKUP_DEVIATION,
                    message=f"{st.code} 主备回路 1h 偏差 {verdict.relative_diff_pct:.3f}%（容差 {PRIMARY_BACKUP_TOLERANCE_PCT}%）",
                    station_id=st.id,
                    payload_json={
                        "primary_nm3": primary_vol,
                        "backup_nm3": backup_vol,
                        "diff_pct": verdict.relative_diff_pct,
                    },
                )
                fired += 1
    return fired


def scan_gc_status() -> int:
    """每 5 分钟：扫 GC 状态与下次校准时间。"""
    fired = 0
    now = _now()
    soon = now + timedelta(days=GC_CALIBRATION_WARN_DAYS)
    with SessionLocal() as db:
        gcs = db.scalars(select(GCAnalyzer)).all()
        for gc in gcs:
            if gc.status == GCStatus.FAULT:
                emit_alert(
                    db,
                    level=AlertLevel.CRITICAL,
                    category=AlertCategory.GC_FAULT,
                    message=f"{gc.code} 色谱仪状态 FAULT",
                    gc_id=gc.id,
                )
                fired += 1
                continue
            if gc.next_calibration_at is not None:
                next_cal = _as_utc(gc.next_calibration_at)
                if next_cal <= soon:
                    days_left = (next_cal - now).days
                    emit_alert(
                        db,
                        level=AlertLevel.WARN if days_left >= 0 else AlertLevel.CRITICAL,
                        category=AlertCategory.GC_CALIBRATION_DUE,
                        message=f"{gc.code} 校准到期：{next_cal.date().isoformat()}（剩余 {days_left} 天）",
                        gc_id=gc.id,
                        payload_json={"days_left": days_left},
                    )
                    fired += 1
    return fired


def scan_meter_verification_due() -> int:
    """每天 08:00：法定计量器具检定 30 天预警。"""
    fired = 0
    now = _now()
    soon = now + timedelta(days=VERIFICATION_WARN_DAYS)
    with SessionLocal() as db:
        stations = db.scalars(
            select(MeteringStation).where(
                MeteringStation.verified_until.is_not(None),
                MeteringStation.verified_until <= soon,
            )
        ).all()
        for st in stations:
            verified_until = _as_utc(st.verified_until)  # type: ignore[arg-type]
            days_left = (verified_until - now).days
            emit_alert(
                db,
                level=AlertLevel.WARN if days_left >= 0 else AlertLevel.CRITICAL,
                category=AlertCategory.METER_VERIFICATION_DUE,
                message=f"{st.code} 计量器具检定到期 {verified_until.date().isoformat()}（剩余 {days_left} 天）",
                station_id=st.id,
                payload_json={"days_left": days_left},
            )
            fired += 1
    return fired


def scan_yesterday_dual_loop() -> int:
    """每个业务日结束5分钟后：对最近完整业务日每个有主备读数的站做回路对账。"""
    policy = current_policy()
    yesterday = policy.latest_completed_date(_now())
    window = policy.window(yesterday)
    start, end = window.start_utc, window.end_utc
    fired = 0
    with SessionLocal() as db:
        stations = db.scalars(
            select(MeteringStation).where(MeteringStation.status == StationStatus.RUNNING)
        ).all()
        for st in stations:
            try:
                primary, backup = dual_loop_volume(db, st.id, start, end, full_day=True)
            except DataQualityError as exc:
                logger.warning('%s: %s', st.code, exc)
                continue
            primary_vol = primary.volume_nm3
            backup_vol = backup.volume_nm3
            if primary_vol <= 0 or backup_vol <= 0:
                continue
            verdict = reconcile_dual_loop(primary_vol, backup_vol)
            if verdict.verdict.value != "PASS":
                emit_alert(
                    db,
                    level=AlertLevel.CRITICAL if verdict.verdict.value == "FAIL" else AlertLevel.WARN,
                    category=AlertCategory.PRIMARY_BACKUP_DEVIATION,
                    message=f"{st.code} 昨日主备偏差 {verdict.relative_diff_pct:.3f}%（{yesterday.isoformat()}）",
                    station_id=st.id,
                    payload_json={
                        "business_date": yesterday.isoformat(),
                        "window": window.model_dump(mode="json"),
                        "primary_nm3": primary_vol,
                        "backup_nm3": backup_vol,
                        "diff_pct": verdict.relative_diff_pct,
                    },
                )
                fired += 1
    return fired


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """启动调度。lifespan 调用，单例。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(scan_primary_backup_deviation, "interval", minutes=1, id="primary-backup", max_instances=1)
    sched.add_job(scan_gc_status, "interval", minutes=5, id="gc-status", max_instances=1)
    sched.add_job(scan_meter_verification_due, "cron", hour=8, minute=0, id="verification-due")
    cutoff = (current_policy().start_minute + 5) % 1440
    sched.add_job(scan_yesterday_dual_loop, "cron", hour=cutoff // 60, minute=cutoff % 60,
                  timezone=current_policy().tz, id="yesterday-dual-loop")
    sched.start()
    logger.info("scheduler started with 4 jobs")
    _scheduler = sched
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
