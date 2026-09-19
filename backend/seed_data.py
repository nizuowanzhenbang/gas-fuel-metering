"""演示数据 seed —— 一键 reset 数据库后填一个完整的可演示场景。

执行方式：
    python -m backend.seed_data            # 不删表，向已有库写
    python -m backend.seed_data --reset    # drop_all + create_all 后再写

落地内容：
- 5 个角色账号（密码统一 demo123，正式部署务必改）
- 3 个气源（西气东输 / 川气东送 / LNG 接收站气化）
- 2 个计量站（MS-01 / MS-02）+ 检定到期（一个 20 天内，一个远期）
- 2 台 GC（GC-01 RUNNING / GC-02 CALIBRATING）
- 24h × 5min 主回路读数，含 1 段 PT_OUT_OF_RANGE + 1 段 FAULT
- 同期备份回路读数（主备差控制在 0.1% 内，留出 PASS 场景）
- 24h 内每小时 1 条 GC 组分
- 1 张 DRAFT 月结算 + 1 张 APPROVED 月结算
- 3 条不同等级的告警
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .auth import Role, hash_password
from .database import Base, SessionLocal, engine, init_db
from .models.alerts import Alert, AlertCategory, AlertLevel, AlertStatus
from .models.gas_sources import GasSource, GasSourceStatus, GasType
from .models.gc_analyzers import GCAnalyzer, GCStatus
from .models.gc_readings import GCReading
from .models.metering_readings import MeteringReading, MeteringSource, Validity
from .models.metering_stations import MeteringStation, StationStatus
from .models.settlement_records import SettlementRecord, SettlementStatus
from .models.users import User
from .utils.heating_value import Composition, compute_heating_value
from .utils.numbering import next_alert_no, next_settlement_no

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


USERS = [
    ("admin", "demo123", "默认管理员", Role.ADMIN),
    ("operator", "demo123", "运行值班员", Role.OPERATOR),
    ("engineer", "demo123", "计量工程师", Role.METER_ENG),
    ("accountant", "demo123", "财务结算", Role.ACCOUNTANT),
    ("viewer", "demo123", "数据浏览员", Role.VIEWER),
]

SOURCES = [
    {
        "code": "SRC-001",
        "name": "西气东输三线",
        "supplier": "中石油",
        "gas_type": GasType.PIPELINE,
        "contract_no": "PIPECHINA-2026-NG-001",
        "contract_base_price": 2.58,
        "daily_volume_plan_nm3": 1_200_000.0,
    },
    {
        "code": "SRC-002",
        "name": "川气东送",
        "supplier": "中石化",
        "gas_type": GasType.PIPELINE,
        "contract_no": "SINOPEC-2026-NG-008",
        "contract_base_price": 2.42,
        "daily_volume_plan_nm3": 800_000.0,
    },
    {
        "code": "SRC-003",
        "name": "如东 LNG 接收站气化",
        "supplier": "中海油",
        "gas_type": GasType.LNG,
        "contract_no": "CNOOC-2026-LNG-015",
        "contract_base_price": 3.06,
        "daily_volume_plan_nm3": 600_000.0,
    },
]

# 典型管道气组分（CH4 ~95%，符合 GB/T 11062 算例）
TYPICAL_COMP = Composition(
    ch4_pct=95.0,
    c2h6_pct=2.5,
    c3h8_pct=1.0,
    ic4h10_pct=0.2,
    nc4h10_pct=0.3,
    n2_pct=0.5,
    co2_pct=0.5,
    others_pct=0.0,
)


def _seed_users(db) -> None:
    for username, pwd, name, role in USERS:
        if db.scalar(select(User).where(User.username == username)):
            continue
        db.add(
            User(
                username=username,
                password_hash=hash_password(pwd),
                full_name=name,
                role=role.value,
                is_active=True,
            )
        )
    db.commit()


def _seed_sources(db) -> dict[str, int]:
    out = {}
    for s in SOURCES:
        existing = db.scalar(select(GasSource).where(GasSource.code == s["code"]))
        if existing:
            out[s["code"]] = existing.id
            continue
        obj = GasSource(**s, status=GasSourceStatus.ACTIVE)
        db.add(obj)
        db.flush()
        out[s["code"]] = obj.id
    db.commit()
    return out


def _seed_stations(db, src_ids: dict[str, int]) -> dict[str, int]:
    now = _now()
    plans = [
        {
            "code": "MS-01",
            "name": "1#计量站",
            "source_code": "SRC-001",
            "verified_until": now + timedelta(days=20),  # 进入 30 天预警
        },
        {
            "code": "MS-02",
            "name": "2#计量站",
            "source_code": "SRC-002",
            "verified_until": now + timedelta(days=200),
        },
    ]
    out = {}
    for p in plans:
        existing = db.scalar(select(MeteringStation).where(MeteringStation.code == p["code"]))
        if existing:
            out[p["code"]] = existing.id
            continue
        obj = MeteringStation(
            code=p["code"],
            name=p["name"],
            location=f"厂区进气界区 {p['code']}",
            source_id=src_ids[p["source_code"]],
            design_pressure_kpa=3500.0,
            design_flow_min_nm3h=5000.0,
            design_flow_max_nm3h=80000.0,
            verified_until=p["verified_until"],
            status=StationStatus.RUNNING,
        )
        db.add(obj)
        db.flush()
        out[p["code"]] = obj.id
    db.commit()
    return out


def _seed_gcs(db, station_ids: dict[str, int]) -> dict[str, int]:
    now = _now()
    plans = [
        {
            "code": "GC-01",
            "model": "ABB NGC8200",
            "station_code": "MS-01",
            "status": GCStatus.RUNNING,
            "last_calibration_at": now - timedelta(days=30),
            "next_calibration_at": now + timedelta(days=60),
        },
        {
            "code": "GC-02",
            "model": "Siemens Maxum II",
            "station_code": "MS-02",
            "status": GCStatus.CALIBRATING,
            "last_calibration_at": now - timedelta(days=89),
            "next_calibration_at": now + timedelta(days=3),  # 7 天内
        },
    ]
    out = {}
    for p in plans:
        existing = db.scalar(select(GCAnalyzer).where(GCAnalyzer.code == p["code"]))
        if existing:
            out[p["code"]] = existing.id
            continue
        obj = GCAnalyzer(
            code=p["code"],
            model=p["model"],
            station_id=station_ids[p["station_code"]],
            status=p["status"],
            last_calibration_at=p["last_calibration_at"],
            next_calibration_at=p["next_calibration_at"],
        )
        db.add(obj)
        db.flush()
        out[p["code"]] = obj.id
    db.commit()
    return out


def _seed_readings(db, station_ids: dict[str, int]) -> None:
    """从昨日 UTC 零点到当前的 5min 主备读数，覆盖完整昨日对账边界。"""
    now = _now()
    # 截到分钟，避免边界尾数
    end = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    step = timedelta(minutes=5)
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    samples = int((end - start) / step) + 1

    for code, sid in station_ids.items():
        # 已有读数则跳过
        if db.scalar(select(MeteringReading).where(MeteringReading.station_id == sid).limit(1)):
            continue
        base = 1_000_000.0 if code == "MS-01" else 500_000.0
        rate_nm3h = 30_000.0 if code == "MS-01" else 20_000.0
        per_step_nm3 = rate_nm3h * 5 / 60  # 每 5 分钟累计增量

        accum_primary = base
        accum_backup = base * 1.0001  # 留 0.01% 起始偏置
        for i in range(samples):
            ts = end - step * (samples - 1 - i)

            # 中间 1h（10 步）模拟 FAULT 段
            primary_validity = Validity.VALID
            if code == "MS-01" and 100 <= i < 110:
                primary_validity = Validity.FAULT
                primary_pressure = 800.0  # 触发 PT_OUT_OF_RANGE
            else:
                primary_pressure = 1500.0

            accum_primary += per_step_nm3
            accum_backup += per_step_nm3 * (1 + 0.0008)  # 0.08% 缓增偏置

            db.add(
                MeteringReading(
                    station_id=sid,
                    ts=ts,
                    actual_volume_rate_m3h=rate_nm3h / 0.85,  # 工况体积反推
                    normal_volume_rate_nm3h=rate_nm3h,
                    pressure_kpa=primary_pressure,
                    temperature_c=20.0,
                    accumulated_volume_nm3=accum_primary,
                    validity=primary_validity,
                    source=MeteringSource.PRIMARY,
                )
            )
            db.add(
                MeteringReading(
                    station_id=sid,
                    ts=ts,
                    actual_volume_rate_m3h=rate_nm3h / 0.85,
                    normal_volume_rate_nm3h=rate_nm3h,
                    pressure_kpa=1500.0,
                    temperature_c=20.0,
                    accumulated_volume_nm3=accum_backup,
                    validity=Validity.VALID,
                    source=MeteringSource.BACKUP,
                )
            )
        db.commit()


def _seed_gc_readings(db, gc_ids: dict[str, int], station_ids: dict[str, int]) -> None:
    """24h × 1h 组分读数。"""
    now = _now().replace(minute=0, second=0, microsecond=0)
    hv = compute_heating_value(TYPICAL_COMP)
    for gc_code, gc_id in gc_ids.items():
        if db.scalar(select(GCReading).where(GCReading.gc_id == gc_id).limit(1)):
            continue
        station_code = "MS-01" if gc_code == "GC-01" else "MS-02"
        for h in range(24, 0, -1):
            ts = now - timedelta(hours=h - 1)
            db.add(
                GCReading(
                    gc_id=gc_id,
                    station_id=station_ids[station_code],
                    ts=ts,
                    ch4_pct=TYPICAL_COMP.ch4_pct,
                    c2h6_pct=TYPICAL_COMP.c2h6_pct,
                    c3h8_pct=TYPICAL_COMP.c3h8_pct,
                    ic4h10_pct=TYPICAL_COMP.ic4h10_pct,
                    nc4h10_pct=TYPICAL_COMP.nc4h10_pct,
                    n2_pct=TYPICAL_COMP.n2_pct,
                    co2_pct=TYPICAL_COMP.co2_pct,
                    others_pct=TYPICAL_COMP.others_pct,
                    hhv_mj_nm3=hv.hhv_mj_nm3,
                    lhv_mj_nm3=hv.lhv_mj_nm3,
                    wobbe_mj_nm3=hv.wobbe_mj_nm3,
                    density_kg_nm3=hv.density_kg_nm3,
                    validity=Validity.VALID,
                )
            )
        db.commit()


def _seed_settlements(db, src_ids: dict[str, int]) -> None:
    if db.scalar(select(SettlementRecord).limit(1)):
        return
    now = _now()
    last_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    last_month_end = now.replace(day=1) - timedelta(days=1)
    this_month_start = now.replace(day=1)

    db.add(
        SettlementRecord(
            settlement_no=next_settlement_no(db, month=last_month_end.date()),
            source_id=src_ids["SRC-001"],
            period_start=last_month_start.date(),
            period_end=last_month_end.date(),
            plant_volume_nm3=35_800_000.0,
            upstream_volume_nm3=35_905_000.0,
            diff_pct=-0.293,
            avg_hhv_mj_nm3=38.123,
            total_energy_gj=1_365_000.0,
            contract_price=2.58,
            amount=92_364_000.0,
            status=SettlementStatus.APPROVED,
            approved_at=now - timedelta(days=2),
            notes="上月正式结算，差异在 0.3% 内，已审批。",
        )
    )
    db.flush()
    db.add(
        SettlementRecord(
            settlement_no=next_settlement_no(db, month=this_month_start.date()),
            source_id=src_ids["SRC-001"],
            period_start=this_month_start.date(),
            period_end=now.date(),
            plant_volume_nm3=12_400_000.0,
            upstream_volume_nm3=None,
            status=SettlementStatus.DRAFT,
            notes="当月进行中，等上游月单。",
        )
    )
    db.commit()


def _seed_alerts(db, station_ids: dict[str, int], gc_ids: dict[str, int]) -> None:
    if db.scalar(select(Alert).limit(1)):
        return
    now = _now()
    samples = [
        dict(
            level=AlertLevel.CRITICAL,
            category=AlertCategory.METER_OFFLINE,
            message="MS-01 上游隔离阀检修，计量暂停",
            station_id=station_ids["MS-01"],
            status=AlertStatus.OPEN,
        ),
        dict(
            level=AlertLevel.WARN,
            category=AlertCategory.GC_CALIBRATION_DUE,
            message="GC-02 校准 3 天内到期",
            gc_id=gc_ids["GC-02"],
            status=AlertStatus.OPEN,
        ),
        dict(
            level=AlertLevel.INFO,
            category=AlertCategory.PT_OUT_OF_RANGE,
            message="MS-01 压力短时低于下限，已自动恢复",
            station_id=station_ids["MS-01"],
            status=AlertStatus.RESOLVED,
        ),
    ]
    for s in samples:
        a = Alert(
            alert_no=next_alert_no(db),
            opened_at=now - timedelta(hours=2),
            **s,
        )
        if a.status == AlertStatus.RESOLVED:
            a.resolved_at = now - timedelta(hours=1)
            a.acked_at = a.resolved_at
        db.add(a)
        db.flush()  # 序号需要看到前一条已落库，否则连续插入会撞唯一索引
    db.commit()


def run(*, reset: bool = False) -> None:
    if reset:
        logger.warning("--reset: drop_all + create_all")
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    else:
        init_db()

    with SessionLocal() as db:
        _seed_users(db)
        src_ids = _seed_sources(db)
        station_ids = _seed_stations(db, src_ids)
        gc_ids = _seed_gcs(db, station_ids)
        _seed_readings(db, station_ids)
        _seed_gc_readings(db, gc_ids, station_ids)
        _seed_settlements(db, src_ids)
        _seed_alerts(db, station_ids, gc_ids)
    logger.warning("seed completed: 5 users / %d sources / %d stations / %d gcs",
                   len(SOURCES), 2, 2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop_all 后重建")
    args = parser.parse_args()
    run(reset=args.reset)
