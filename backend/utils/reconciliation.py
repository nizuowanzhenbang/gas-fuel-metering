"""三方对账与计量回路偏差容差判定。

业务定义（CLAUDE.md / README）：
- **日对账**：厂内 vs 上游公司日报，容差 0.5%（基准 = 上游日报）
- **月对账**：厂内 vs 上游月结算单，容差 0.3%（基准 = 上游月结算单）
- **主备回路**：同一计量站的主用 / 备用流量计，容差 0.3%（基准 = 两者平均值）

三档判定：
- **PASS** ：|相对偏差| ≤ 容差
- **WARN** ：容差 < |相对偏差| ≤ 容差 × FAIL_MULTIPLIER，需要人工复核但不锁单
- **FAIL** ：|相对偏差| > 容差 × FAIL_MULTIPLIER，锁单待处置

相对偏差有方向：正 = 被测大于基准，负 = 被测小于基准。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

DAILY_TOLERANCE_PCT = 0.5
MONTHLY_TOLERANCE_PCT = 0.3
DUAL_LOOP_TOLERANCE_PCT = 0.3

FAIL_MULTIPLIER = 2.0


class Verdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ReconciliationResult:
    """厂内 vs 上游（日报 / 月结算）对账结果。"""

    plant_volume_nm3: float
    upstream_volume_nm3: float
    absolute_diff_nm3: float
    relative_diff_pct: float
    tolerance_pct: float
    verdict: Verdict
    reason: str


@dataclass(frozen=True)
class DualLoopResult:
    """主备计量回路对比结果。基准 = 两者平均值。"""

    primary_volume_nm3: float
    backup_volume_nm3: float
    absolute_diff_nm3: float
    relative_diff_pct: float
    tolerance_pct: float
    verdict: Verdict
    reason: str


def _judge(abs_relative_pct: float, tolerance_pct: float) -> tuple[Verdict, str]:
    if abs_relative_pct <= tolerance_pct:
        return Verdict.PASS, f"偏差 {abs_relative_pct:.3f}% 在容差 {tolerance_pct}% 内"
    if abs_relative_pct <= tolerance_pct * FAIL_MULTIPLIER:
        return (
            Verdict.WARN,
            f"偏差 {abs_relative_pct:.3f}% 超容差 {tolerance_pct}% 但未超 "
            f"{FAIL_MULTIPLIER}×，需人工复核",
        )
    return (
        Verdict.FAIL,
        f"偏差 {abs_relative_pct:.3f}% 超容差 {FAIL_MULTIPLIER}× "
        f"({tolerance_pct * FAIL_MULTIPLIER}%)，锁单待处置",
    )


def _reconcile(
    plant_nm3: float,
    upstream_nm3: float,
    tolerance_pct: float,
) -> ReconciliationResult:
    if not all(isfinite(v) for v in (plant_nm3, upstream_nm3)):
        raise ValueError('volumes must be finite')
    if plant_nm3 < 0 or upstream_nm3 < 0:
        raise ValueError("volumes must be non-negative")
    if upstream_nm3 == 0:
        raise ValueError("upstream baseline volume must be positive")

    diff = plant_nm3 - upstream_nm3
    relative_pct = diff / upstream_nm3 * 100.0
    verdict, reason = _judge(abs(relative_pct), tolerance_pct)

    return ReconciliationResult(
        plant_volume_nm3=plant_nm3,
        upstream_volume_nm3=upstream_nm3,
        absolute_diff_nm3=diff,
        relative_diff_pct=relative_pct,
        tolerance_pct=tolerance_pct,
        verdict=verdict,
        reason=reason,
    )


def reconcile_daily(plant_nm3: float, upstream_nm3: float) -> ReconciliationResult:
    """日对账：厂内 vs 上游日报，容差 0.5%。"""
    return _reconcile(plant_nm3, upstream_nm3, DAILY_TOLERANCE_PCT)


def reconcile_monthly(plant_nm3: float, upstream_nm3: float) -> ReconciliationResult:
    """月对账：厂内 vs 上游月结算单，容差 0.3%。"""
    return _reconcile(plant_nm3, upstream_nm3, MONTHLY_TOLERANCE_PCT)


def reconcile_dual_loop(primary_nm3: float, backup_nm3: float) -> DualLoopResult:
    """主备计量回路偏差，基准 = (主 + 备) / 2，容差 0.3%。

    两路都是厂内计量，谁错不知道，所以用平均值做基准。
    """
    if not all(isfinite(v) for v in (primary_nm3, backup_nm3)):
        raise ValueError('volumes must be finite')
    if primary_nm3 < 0 or backup_nm3 < 0:
        raise ValueError("volumes must be non-negative")
    mean = (primary_nm3 + backup_nm3) / 2.0
    if mean == 0:
        raise ValueError("mean baseline volume must be positive")

    diff = primary_nm3 - backup_nm3
    relative_pct = diff / mean * 100.0
    verdict, reason = _judge(abs(relative_pct), DUAL_LOOP_TOLERANCE_PCT)

    return DualLoopResult(
        primary_volume_nm3=primary_nm3,
        backup_volume_nm3=backup_nm3,
        absolute_diff_nm3=diff,
        relative_diff_pct=relative_pct,
        tolerance_pct=DUAL_LOOP_TOLERANCE_PCT,
        verdict=verdict,
        reason=reason,
    )
