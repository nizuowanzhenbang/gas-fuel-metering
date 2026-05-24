"""热值计算单元测试。例题来自 GB/T 11062 + 典型管道气组分。"""
from __future__ import annotations

import math

import pytest

from backend.utils.heating_value import (
    AIR_DENSITY_NM3,
    Composition,
    compute_heating_value,
)


def test_pure_methane_matches_reference():
    """100% CH4 应当还原到单组分参考值。"""
    result = compute_heating_value(Composition(ch4_pct=100.0))
    assert math.isclose(result.hhv_mj_nm3, 37.694, rel_tol=1e-6)
    assert math.isclose(result.lhv_mj_nm3, 33.948, rel_tol=1e-6)
    assert math.isclose(result.density_kg_nm3, 0.6680, rel_tol=1e-6)
    assert math.isclose(result.relative_density, 0.6680 / AIR_DENSITY_NM3, rel_tol=1e-6)
    expected_wobbe = 37.694 / math.sqrt(0.6680 / AIR_DENSITY_NM3)
    assert math.isclose(result.wobbe_mj_nm3, expected_wobbe, rel_tol=1e-6)


def test_typical_chinese_pipeline_gas():
    """典型西气东输组分：CH4 96 / C2H6 2 / C3H8 0.5 / N2 0.5 / CO2 1。

    手算 HHV = 0.96×37.694 + 0.02×66.067 + 0.005×93.936 = 37.977 MJ/Nm³
    """
    result = compute_heating_value(
        Composition(ch4_pct=96.0, c2h6_pct=2.0, c3h8_pct=0.5, n2_pct=0.5, co2_pct=1.0)
    )
    expected_hhv = 0.96 * 37.694 + 0.02 * 66.067 + 0.005 * 93.936
    assert math.isclose(result.hhv_mj_nm3, expected_hhv, rel_tol=1e-9)
    assert 37.5 < result.hhv_mj_nm3 < 38.5
    # Wobbe 工程经验区间 49 ~ 53 MJ/Nm³
    assert 49.0 < result.wobbe_mj_nm3 < 53.0


def test_lhv_is_less_than_hhv():
    """LHV 不含水蒸气凝结潜热，比 HHV 小 8~12%。"""
    result = compute_heating_value(
        Composition(ch4_pct=90.0, c2h6_pct=5.0, c3h8_pct=3.0, n2_pct=1.0, co2_pct=1.0)
    )
    assert result.lhv_mj_nm3 < result.hhv_mj_nm3
    ratio = result.lhv_mj_nm3 / result.hhv_mj_nm3
    assert 0.88 < ratio < 0.92


def test_inert_only_returns_zero_hhv():
    """100% 惰性气体 (N2+CO2) 热值为 0，但密度仍为正。"""
    result = compute_heating_value(Composition(n2_pct=50.0, co2_pct=50.0))
    assert result.hhv_mj_nm3 == 0.0
    assert result.lhv_mj_nm3 == 0.0
    assert result.density_kg_nm3 > 0.0
    assert result.wobbe_mj_nm3 == 0.0


def test_rejects_composition_sum_too_far_from_100():
    """组分和偏离 100% 超过 ±1% 视为脏数据。"""
    with pytest.raises(ValueError, match="deviates from 100"):
        compute_heating_value(Composition(ch4_pct=80.0))


def test_accepts_composition_within_tolerance():
    r_low = compute_heating_value(Composition(ch4_pct=99.5))
    r_high = compute_heating_value(Composition(ch4_pct=100.5))
    assert r_low.hhv_mj_nm3 > 0
    assert r_high.hhv_mj_nm3 > 0


def test_rejects_negative_component():
    with pytest.raises(ValueError, match="negative"):
        compute_heating_value(Composition(ch4_pct=100.0, c2h6_pct=-0.5, n2_pct=0.5))


def test_wobbe_formula():
    """Wobbe = HHV / √(相对密度) — 用纯丙烷验证。"""
    result = compute_heating_value(Composition(c3h8_pct=100.0))
    expected_d = 1.8641 / AIR_DENSITY_NM3
    expected_wobbe = 93.936 / math.sqrt(expected_d)
    assert math.isclose(result.wobbe_mj_nm3, expected_wobbe, rel_tol=1e-6)
