"""三方对账 / 主备回路单元测试。

覆盖：日对账三档（PASS/WARN/FAIL）、月对账边界与失败、主备回路基准与 WARN、偏差
方向、入参校验。
"""
from __future__ import annotations

import math


def test_non_finite_volumes_cannot_receive_a_verdict():
    import pytest
    from backend.utils.reconciliation import reconcile_daily, reconcile_dual_loop
    for value in (math.nan, math.inf, -math.inf):
        for fn in (reconcile_daily, reconcile_dual_loop):
            with pytest.raises(ValueError):
                fn(value, 100)
            with pytest.raises(ValueError):
                fn(100, value)

import math

import pytest

from backend.utils.reconciliation import (
    DAILY_TOLERANCE_PCT,
    DUAL_LOOP_TOLERANCE_PCT,
    FAIL_MULTIPLIER,
    MONTHLY_TOLERANCE_PCT,
    Verdict,
    reconcile_daily,
    reconcile_dual_loop,
    reconcile_monthly,
)


def test_daily_pass_within_tolerance_with_negative_direction():
    """厂内 999_000 vs 上游 1_000_000 → -0.1%，PASS 且方向为负。"""
    r = reconcile_daily(plant_nm3=999_000.0, upstream_nm3=1_000_000.0)
    assert r.verdict == Verdict.PASS
    assert math.isclose(r.relative_diff_pct, -0.1, rel_tol=1e-9)
    assert r.absolute_diff_nm3 == -1_000.0
    assert r.tolerance_pct == DAILY_TOLERANCE_PCT


def test_daily_warn_just_over_tolerance():
    """厂内多 0.6%，超 0.5% 容差但未超 1%（=2×），WARN。"""
    r = reconcile_daily(plant_nm3=1_006_000.0, upstream_nm3=1_000_000.0)
    assert r.verdict == Verdict.WARN
    assert math.isclose(r.relative_diff_pct, 0.6, rel_tol=1e-9)
    assert "复核" in r.reason


def test_daily_fail_above_double_tolerance():
    """偏差 1.5% 超 2× 容差，FAIL，锁单。"""
    r = reconcile_daily(plant_nm3=1_015_000.0, upstream_nm3=1_000_000.0)
    assert r.verdict == Verdict.FAIL
    assert math.isclose(r.relative_diff_pct, 1.5, rel_tol=1e-9)
    assert "锁单" in r.reason


def test_monthly_pass_at_exact_boundary():
    """月对账恰好 0.3% 容差边界，按 ≤ 判定应为 PASS。"""
    r = reconcile_monthly(plant_nm3=1_003_000.0, upstream_nm3=1_000_000.0)
    assert r.verdict == Verdict.PASS
    assert math.isclose(r.relative_diff_pct, 0.3, rel_tol=1e-9)
    assert r.tolerance_pct == MONTHLY_TOLERANCE_PCT


def test_monthly_fail_exceeds_double_tolerance():
    """月对账 0.8% 偏差 > 0.6%（=2×0.3%），FAIL。"""
    r = reconcile_monthly(plant_nm3=1_008_000.0, upstream_nm3=1_000_000.0)
    assert r.verdict == Verdict.FAIL
    assert math.isclose(r.relative_diff_pct, 0.8, rel_tol=1e-9)


def test_dual_loop_baseline_is_mean_and_pass():
    """主备基准 = 平均值。主 1_000_200、备 999_800，平均 1_000_000，相对 +0.02%，PASS。"""
    r = reconcile_dual_loop(primary_nm3=1_000_200.0, backup_nm3=999_800.0)
    assert r.verdict == Verdict.PASS
    assert r.absolute_diff_nm3 == 400.0
    assert math.isclose(r.relative_diff_pct, 0.04, rel_tol=1e-9)
    assert r.tolerance_pct == DUAL_LOOP_TOLERANCE_PCT


def test_dual_loop_warn_between_tolerance_and_double():
    """主 502_250 vs 备 500_000 → 平均 501_125、差 2_250、相对 ≈ 0.449%，
    超 0.3% 容差但未超 0.6%（=2×），WARN。"""
    r = reconcile_dual_loop(primary_nm3=502_250.0, backup_nm3=500_000.0)
    assert r.verdict == Verdict.WARN
    assert DUAL_LOOP_TOLERANCE_PCT < abs(r.relative_diff_pct) <= DUAL_LOOP_TOLERANCE_PCT * FAIL_MULTIPLIER


def test_input_validation_rejects_zero_baseline_and_negative_volume():
    with pytest.raises(ValueError, match="upstream baseline"):
        reconcile_daily(plant_nm3=100.0, upstream_nm3=0.0)
    with pytest.raises(ValueError, match="non-negative"):
        reconcile_monthly(plant_nm3=-1.0, upstream_nm3=1000.0)
    with pytest.raises(ValueError, match="mean baseline"):
        reconcile_dual_loop(primary_nm3=0.0, backup_nm3=0.0)
    with pytest.raises(ValueError, match="non-negative"):
        reconcile_dual_loop(primary_nm3=-100.0, backup_nm3=100.0)
