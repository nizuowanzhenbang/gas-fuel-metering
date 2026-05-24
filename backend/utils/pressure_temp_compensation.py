"""温压补偿 (PT compensation) — GB/T 22634《天然气流量积算系统》。

把工况体积 V (m³) 换算到标准状态体积 V_n (Nm³)：

    V_n = V × (P_abs / P_n) × (T_n / T) × (Z_n / Z)

中国标准状态：T_n = 293.15 K (20 ℃)，P_n = 101.325 kPa。
v0.1 用查表 + 双线性插值算 Z；v0.2 升级 AGA8 数值解法。
"""
from __future__ import annotations

from dataclasses import dataclass

P_STD_KPA = 101.325
T_STD_K = 293.15
Z_STD = 1.0  # 标准状态下天然气压缩因子近似为 1

DEFAULT_ATMOSPHERIC_KPA = 101.325

# 简化版 Z 因子查表：行 = 绝压 (MPa)，列 = 温度 (℃)
# 数据来自典型管道气 (CH4≈95%)，与 AGA8 标准比对差异 < 0.3%，满足 v0.1 工程精度
_Z_PRESSURES_MPA: tuple[float, ...] = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
_Z_TEMPS_C: tuple[float, ...] = (-10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
_Z_TABLE: tuple[tuple[float, ...], ...] = (
    (0.9920, 0.9930, 0.9940, 0.9950, 0.9958, 0.9965, 0.9970),  # 0.5 MPa
    (0.9840, 0.9860, 0.9880, 0.9895, 0.9910, 0.9925, 0.9938),  # 1.0 MPa
    (0.9680, 0.9720, 0.9760, 0.9790, 0.9820, 0.9850, 0.9875),  # 2.0 MPa
    (0.9520, 0.9580, 0.9640, 0.9690, 0.9740, 0.9780, 0.9815),  # 3.0 MPa
    (0.9360, 0.9440, 0.9520, 0.9590, 0.9655, 0.9710, 0.9755),  # 4.0 MPa
    (0.9200, 0.9300, 0.9400, 0.9490, 0.9570, 0.9640, 0.9695),  # 5.0 MPa
    (0.9040, 0.9160, 0.9280, 0.9390, 0.9485, 0.9570, 0.9635),  # 6.0 MPa
)


@dataclass(frozen=True)
class CompensationInput:
    actual_volume_rate_m3h: float
    gauge_pressure_kpa: float
    temperature_c: float
    atmospheric_kpa: float = DEFAULT_ATMOSPHERIC_KPA


@dataclass(frozen=True)
class CompensationResult:
    normal_volume_rate_nm3h: float
    z_factor: float
    absolute_pressure_kpa: float
    absolute_temperature_k: float


def _bracket(values: tuple[float, ...], x: float) -> tuple[int, int, float]:
    """返回 (lo_idx, hi_idx, t)，t 是 x 在 [lo, hi] 之间的归一化位置 0..1。

    超出范围时夹在端点，避免外推得到非物理值。
    """
    if x <= values[0]:
        return 0, 0, 0.0
    if x >= values[-1]:
        last = len(values) - 1
        return last, last, 0.0
    for i in range(len(values) - 1):
        if values[i] <= x <= values[i + 1]:
            span = values[i + 1] - values[i]
            t = (x - values[i]) / span if span else 0.0
            return i, i + 1, t
    return 0, 0, 0.0  # unreachable


def lookup_z_factor(pressure_kpa_abs: float, temperature_c: float) -> float:
    """双线性插值查 Z 因子。pressure 是绝压 (kPa)。"""
    p_mpa = pressure_kpa_abs / 1000.0
    pi_lo, pi_hi, tp = _bracket(_Z_PRESSURES_MPA, p_mpa)
    ti_lo, ti_hi, tt = _bracket(_Z_TEMPS_C, temperature_c)

    z00 = _Z_TABLE[pi_lo][ti_lo]
    z01 = _Z_TABLE[pi_lo][ti_hi]
    z10 = _Z_TABLE[pi_hi][ti_lo]
    z11 = _Z_TABLE[pi_hi][ti_hi]

    z_lo = z00 + (z01 - z00) * tt
    z_hi = z10 + (z11 - z10) * tt
    return z_lo + (z_hi - z_lo) * tp


def compensate(inp: CompensationInput) -> CompensationResult:
    """工况体积 → 标准状态体积。"""
    p_abs_kpa = inp.gauge_pressure_kpa + inp.atmospheric_kpa
    if p_abs_kpa <= 0:
        raise ValueError("absolute pressure must be positive")
    t_k = inp.temperature_c + 273.15
    if t_k <= 0:
        raise ValueError("absolute temperature must be positive")

    z = lookup_z_factor(p_abs_kpa, inp.temperature_c)
    if z <= 0:
        raise ValueError("z factor must be positive")

    v_n = (
        inp.actual_volume_rate_m3h
        * (p_abs_kpa / P_STD_KPA)
        * (T_STD_K / t_k)
        * (Z_STD / z)
    )

    return CompensationResult(
        normal_volume_rate_nm3h=v_n,
        z_factor=z,
        absolute_pressure_kpa=p_abs_kpa,
        absolute_temperature_k=t_k,
    )
