"""业务单据编号生成。

约定（CLAUDE.md）：
- 告警  AL-YYYYMMDD-NNNN
- 计量批次 GAS-YYYYMMDD-NNNN
- 月结算 SETTLE-YYYYMM-NN

实现策略：按"日（或月）前缀 + 当日已存在序号 + 1"在 DB 内生成。
SQLite 与 PostgreSQL 都支持 LIKE 前缀扫描，对单日量级（≤9999）足够。
高并发场景由 v0.2 引入数据库序列改造，不在 v1.0 范围内。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Type

from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _next_seq(db: Session, column: InstrumentedAttribute, prefix: str, width: int) -> str:
    """通用：扫描以 prefix 开头的最大编号，序号 +1 后拼成完整字符串。"""
    existing = db.scalar(
        select(func.max(column)).where(column.like(f"{prefix}%"))
    )
    if existing is None:
        seq = 1
    else:
        tail = str(existing).rsplit("-", 1)[-1]
        try:
            seq = int(tail) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:0{width}d}"


def next_alert_no(db: Session, *, today: date | None = None) -> str:
    """AL-YYYYMMDD-NNNN，日序号 4 位。"""
    from ..models.alerts import Alert  # 延迟导入避免循环依赖

    d = today or _today_utc()
    return _next_seq(
        db,
        column=Alert.alert_no,
        prefix=f"AL-{d.strftime('%Y%m%d')}-",
        width=4,
    )


def next_settlement_no(db: Session, *, month: date | None = None) -> str:
    """SETTLE-YYYYMM-NN，月序号 2 位。"""
    from ..models.settlement_records import SettlementRecord

    m = month or _today_utc()
    return _next_seq(
        db,
        column=SettlementRecord.settlement_no,
        prefix=f"SETTLE-{m.strftime('%Y%m')}-",
        width=2,
    )
