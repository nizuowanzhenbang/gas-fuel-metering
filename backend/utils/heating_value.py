"""热值计算 — GB/T 11062《天然气 发热量、密度、相对密度和沃泊指数的计算方法》。

输入是天然气组分的摩尔百分比（mol%），输出 HHV、LHV、Wobbe、密度、相对密度。
参考状态：燃烧温度 25 ℃，计量参比状态 20 ℃、101.325 kPa，干基。
"""
from __future__ import annotations

from dataclasses import dataclass

AIR_DENSITY_NM3 = 1.2046  # kg/Nm³ at 20℃, 101.325 kPa

# GB/T 11062-2014 附录 B 表 B.1 主流组分参考值
_COMPONENT_REF: dict[str, dict[str, float]] = {
    "ch4":     {"hhv": 37.694, "lhv": 33.948, "rho": 0.6680},
    "c2h6":    {"hhv": 66.067, "lhv": 60.430, "rho": 1.2601},
    "c3h8":    {"hhv": 93.936, "lhv": 86.420, "rho": 1.8641},
    "ic4h10":  {"hhv": 121.408, "lhv": 112.000, "rho": 2.4972},
    "nc4h10":  {"hhv": 121.779, "lhv": 112.350, "rho": 2.4978},
    "n2":      {"hhv": 0.0,    "lhv": 0.0,    "rho": 1.1648},
    "co2":     {"hhv": 0.0,    "lhv": 0.0,    "rho": 1.8295},
    # others 当作惰性，避免脏数据被静默吸收；密度取 N2 保守值
    "others":  {"hhv": 0.0,    "lhv": 0.0,    "rho": 1.1648},
}

_SUM_TOLERANCE_PCT = 1.0  # 组分之和允许偏离 100% ±1%


@dataclass(frozen=True)
class Composition:
    ch4_pct: float = 0.0
    c2h6_pct: float = 0.0
    c3h8_pct: float = 0.0
    ic4h10_pct: float = 0.0
    nc4h10_pct: float = 0.0
    n2_pct: float = 0.0
    co2_pct: float = 0.0
    others_pct: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "ch4": self.ch4_pct,
            "c2h6": self.c2h6_pct,
            "c3h8": self.c3h8_pct,
            "ic4h10": self.ic4h10_pct,
            "nc4h10": self.nc4h10_pct,
            "n2": self.n2_pct,
            "co2": self.co2_pct,
            "others": self.others_pct,
        }


@dataclass(frozen=True)
class HeatingValueResult:
    hhv_mj_nm3: float
    lhv_mj_nm3: float
    wobbe_mj_nm3: float
    density_kg_nm3: float
    relative_density: float


def _validate_sum(comp_pct: dict[str, float]) -> None:
    total = sum(comp_pct.values())
    if abs(total - 100.0) > _SUM_TOLERANCE_PCT:
        raise ValueError(
            f"composition mol-percent sum {total:.3f} deviates from 100 by more than ±{_SUM_TOLERANCE_PCT}"
        )
    for name, v in comp_pct.items():
        if v < 0:
            raise ValueError(f"component {name} has negative percent {v}")


def compute_heating_value(comp: Composition) -> HeatingValueResult:
    """按 GB/T 11062 计算混合气体 HHV、LHV、Wobbe、密度、相对密度。"""
    comp_pct = comp.as_dict()
    _validate_sum(comp_pct)

    fractions = {k: v / 100.0 for k, v in comp_pct.items()}

    hhv = sum(fractions[k] * _COMPONENT_REF[k]["hhv"] for k in fractions)
    lhv = sum(fractions[k] * _COMPONENT_REF[k]["lhv"] for k in fractions)
    density = sum(fractions[k] * _COMPONENT_REF[k]["rho"] for k in fractions)

    if density <= 0:
        raise ValueError("mixture density must be positive")

    relative_density = density / AIR_DENSITY_NM3
    wobbe = hhv / (relative_density ** 0.5) if hhv > 0 else 0.0

    return HeatingValueResult(
        hhv_mj_nm3=hhv,
        lhv_mj_nm3=lhv,
        wobbe_mj_nm3=wobbe,
        density_kg_nm3=density,
        relative_density=relative_density,
    )
