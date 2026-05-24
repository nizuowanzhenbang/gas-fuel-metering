"""温压补偿单元测试。用 GB/T 22634 公式手算结果对齐。"""
from __future__ import annotations

import math

import pytest

from backend.utils.pressure_temp_compensation import (
    P_STD_KPA,
    T_STD_K,
    CompensationInput,
    compensate,
    lookup_z_factor,
)


def test_standard_state_returns_input():
    """标准状态下：V_n = V / Z（P 比 = 1, T 比 = 1）。"""
    inp = CompensationInput(
        actual_volume_rate_m3h=1000.0,
        gauge_pressure_kpa=0.0,
        temperature_c=20.0,
        atmospheric_kpa=P_STD_KPA,
    )
    result = compensate(inp)
    assert math.isclose(result.absolute_pressure_kpa, P_STD_KPA, rel_tol=1e-9)
    assert math.isclose(result.absolute_temperature_k, T_STD_K, rel_tol=1e-9)
    assert math.isclose(
        result.normal_volume_rate_nm3h,
        1000.0 / result.z_factor,
        rel_tol=1e-9,
    )


def test_compensation_at_2mpa_20c():
    """P_abs=2.0 MPa, T=20℃ 精确落在 Z 表网格 → Z=0.9790。

    V_n = 1000 × (2000/101.325) × 1 × (1/0.9790)
    """
    inp = CompensationInput(
        actual_volume_rate_m3h=1000.0,
        gauge_pressure_kpa=2000.0 - 101.325,
        temperature_c=20.0,
    )
    result = compensate(inp)
    expected = 1000.0 * (2000.0 / 101.325) * 1.0 * (1.0 / 0.9790)
    assert math.isclose(result.z_factor, 0.9790, rel_tol=1e-6)
    assert math.isclose(result.normal_volume_rate_nm3h, expected, rel_tol=1e-6)
    assert 20100 < result.normal_volume_rate_nm3h < 20200


def test_compensation_at_1mpa_30c():
    """P_abs=1.0 MPa, T=30℃ → Z=0.9910，T 偏离标准。"""
    inp = CompensationInput(
        actual_volume_rate_m3h=500.0,
        gauge_pressure_kpa=1000.0 - 101.325,
        temperature_c=30.0,
    )
    result = compensate(inp)
    expected = (
        500.0
        * (1000.0 / 101.325)
        * (293.15 / 303.15)
        * (1.0 / 0.9910)
    )
    assert math.isclose(result.z_factor, 0.9910, rel_tol=1e-6)
    assert math.isclose(result.normal_volume_rate_nm3h, expected, rel_tol=1e-6)


def test_z_lookup_at_grid_points():
    assert lookup_z_factor(2000.0, 20.0) == pytest.approx(0.9790)
    assert lookup_z_factor(5000.0, 40.0) == pytest.approx(0.9640)
    assert lookup_z_factor(500.0, -10.0) == pytest.approx(0.9920)


def test_z_lookup_between_grid_points_is_monotonic():
    """温度升高 Z 单调上升；压力升高 Z 单调下降（在我们这张表覆盖范围内）。"""
    z_low_t = lookup_z_factor(3000.0, 0.0)
    z_high_t = lookup_z_factor(3000.0, 30.0)
    assert z_high_t > z_low_t

    z_low_p = lookup_z_factor(1000.0, 20.0)
    z_high_p = lookup_z_factor(5000.0, 20.0)
    assert z_low_p > z_high_p


def test_z_lookup_clamps_out_of_range():
    """超出表范围不外推，取边界值。"""
    from backend.utils.pressure_temp_compensation import _Z_TABLE

    assert lookup_z_factor(100.0, 20.0) == pytest.approx(_Z_TABLE[0][3])
    assert lookup_z_factor(10000.0, 20.0) == pytest.approx(_Z_TABLE[6][3])
    assert lookup_z_factor(2000.0, -50.0) == pytest.approx(_Z_TABLE[2][0])
    assert lookup_z_factor(2000.0, 100.0) == pytest.approx(_Z_TABLE[2][6])


def test_rejects_negative_absolute_pressure():
    inp = CompensationInput(
        actual_volume_rate_m3h=100.0,
        gauge_pressure_kpa=-200.0,
        temperature_c=20.0,
    )
    with pytest.raises(ValueError, match="absolute pressure"):
        compensate(inp)


def test_rejects_absolute_zero_temperature():
    inp = CompensationInput(
        actual_volume_rate_m3h=100.0,
        gauge_pressure_kpa=1000.0,
        temperature_c=-300.0,
    )
    with pytest.raises(ValueError, match="absolute temperature"):
        compensate(inp)
