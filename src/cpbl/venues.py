"""球場屬性對照（場地材質 / 室內外）。

**單一真值為 DB `cpbl.venue_dim`**（mig 024）；本模組於首次使用時載入並快取，
DB 不可用或未 seed 時回退至下方 _FALLBACK 硬編。規則：
- 人工草皮 [artificial turf]：**只有** 天母、大巨蛋。
- 室內 [indoor]：**只有** 大巨蛋。
- 其餘一律天然草皮 [natural turf]、露天。

venue 字串對齊 cpbl.games.venue（官網簡稱）。未知球場以 DEFAULT（天然、露天）處理。
"""

from __future__ import annotations

# DB 不可用時的回退（與 mig 024 venue_dim seed 同源）
_FALLBACK: dict[str, dict] = {
    "大巨蛋": {"turf": "artificial", "indoor": True},
    "天母": {"turf": "artificial", "indoor": False},
    "洲際": {"turf": "natural", "indoor": False},
    "澄清湖": {"turf": "natural", "indoor": False},
    "新莊": {"turf": "natural", "indoor": False},
    "樂天桃園": {"turf": "natural", "indoor": False},
    "亞太主": {"turf": "natural", "indoor": False},
    "嘉義市": {"turf": "natural", "indoor": False},
    "花蓮": {"turf": "natural", "indoor": False},
    "台南": {"turf": "natural", "indoor": False},
    "台東": {"turf": "natural", "indoor": False},
    "斗六": {"turf": "natural", "indoor": False},
}

DEFAULT = {"turf": "natural", "indoor": False}

_cache: dict[str, dict] | None = None


def _venues() -> dict[str, dict]:
    """從 venue_dim 載入並快取；DB 不可用/空表回退硬編。"""
    global _cache
    if _cache is not None:
        return _cache
    try:
        from cpbl.db import conn
        with conn() as c:
            rows = c.execute("SELECT venue, turf, indoor FROM cpbl.venue_dim").fetchall()
        _cache = {v: {"turf": t, "indoor": bool(i)} for v, t, i in rows} or _FALLBACK
    except Exception:  # noqa: BLE001 — DB 不可用時退回硬編
        _cache = _FALLBACK
    return _cache


def attrs(venue: str | None) -> dict:
    return _venues().get(venue or "", DEFAULT)


def turf_of(venue: str | None) -> str:
    return attrs(venue)["turf"]


def is_indoor(venue: str | None) -> bool:
    return attrs(venue)["indoor"]


def is_artificial(venue: str | None) -> bool:
    return turf_of(venue) == "artificial"
