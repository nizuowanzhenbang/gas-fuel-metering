"""跨系统出站调用客户端。

约定（CLAUDE.md）：
- 所有出站调用统一走本模块，**不允许** 在 router/scheduler 中散落 httpx
- 鉴权头：`X-Integration-Secret: <env.INTEGRATION_SECRET>`
- 超时 3 秒，失败重试 2 次（指数退避 1s / 2s）
- 调用失败 **不抛错**，返回 None；调用方决定降级策略
- 响应统一约定 `{ "code": 200, "message": "ok", "data": {...} }`，本模块只解 data
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S = 3.0
_RETRY_BACKOFFS_S = (1.0, 2.0)  # 重试 2 次，指数退避


def _headers() -> dict[str, str]:
    return {"X-Integration-Secret": get_settings().integration_secret}


def _get(url: str) -> dict[str, Any] | None:
    """带重试的 GET。统一抽出 data 字段；失败返回 None。"""
    last_exc: Exception | None = None
    attempts = (0.0,) + _RETRY_BACKOFFS_S
    for backoff in attempts:
        if backoff:
            time.sleep(backoff)
        try:
            resp = httpx.get(url, headers=_headers(), timeout=_REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                logger.warning("integration: %s returned non-object payload", url)
                return None
            if payload.get("code", 200) != 200:
                logger.warning("integration: %s business error %s", url, payload.get("message"))
                return None
            return payload.get("data")
        except Exception as exc:  # noqa: BLE001  网络层故障吞掉
            last_exc = exc
    logger.warning("integration: %s failed after retries: %s", url, last_exc)
    return None


def _post(url: str, body: dict[str, Any]) -> dict[str, Any] | None:
    last_exc: Exception | None = None
    attempts = (0.0,) + _RETRY_BACKOFFS_S
    for backoff in attempts:
        if backoff:
            time.sleep(backoff)
        try:
            resp = httpx.post(url, json=body, headers=_headers(), timeout=_REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and payload.get("code", 200) != 200:
                logger.warning("integration: %s business error %s", url, payload.get("message"))
                return None
            return payload.get("data") if isinstance(payload, dict) else None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    logger.warning("integration: %s failed after retries: %s", url, last_exc)
    return None


# ---------------------------- 出站接口（六枚） ----------------------------


def fetch_turbine_output() -> dict[str, Any] | None:
    """gas-turbine-performance：拉燃机实时出力，算热效率用。"""
    base = get_settings().gas_turbine_base.rstrip("/")
    return _get(f"{base}/api/integration/turbine-output")


def fetch_gas_contract(source_code: str) -> dict[str, Any] | None:
    """fuel-procurement：按气源 code 拉合同基准（价格 / 日计划量 / 月底限）。"""
    base = get_settings().fuel_procurement_base.rstrip("/")
    return _get(f"{base}/api/integration/gas-contract?source_code={source_code}")


def report_monthly_settlement(settlement: dict[str, Any]) -> dict[str, Any] | None:
    """fuel-procurement：月度计量回写。"""
    base = get_settings().fuel_procurement_base.rstrip("/")
    return _post(f"{base}/api/webhook/gas-delivered", settlement)


def fetch_equipment_health(equipment_code: str) -> dict[str, Any] | None:
    """equipment-inspection：拉计量站 / GC 的点检状态。"""
    base = get_settings().equipment_inspection_base.rstrip("/")
    return _get(f"{base}/api/integration/equipment-health?code={equipment_code}")


def push_hazard(payload: dict[str, Any]) -> dict[str, Any] | None:
    """plant-safety：把计量故障 / 管网异常推为隐患。"""
    base = get_settings().plant_safety_base.rstrip("/")
    return _post(f"{base}/api/integration/hazards", payload)
