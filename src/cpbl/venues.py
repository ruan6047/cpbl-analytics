"""球場屬性對照（場地材質 / 室內外）。

特殊戰績按場地分類用。規則由使用者定調：
- 人工草皮 [artificial turf]：**只有** 天母、大巨蛋。
- 室內 [indoor]：**只有** 大巨蛋。
- 其餘一律天然草皮 [natural turf]、露天。

venue 字串對齊 cpbl.games.venue（官網簡稱）。未知球場以 DEFAULT（天然、露天）處理。
"""

from __future__ import annotations

# turf: "artificial" | "natural"；indoor: bool
VENUES: dict[str, dict] = {
    "大巨蛋": {"turf": "artificial", "indoor": True},   # 台北大巨蛋：人工草皮 + 室內
    "天母": {"turf": "artificial", "indoor": False},    # 天母棒球場：人工草皮、露天
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


def attrs(venue: str | None) -> dict:
    return VENUES.get(venue or "", DEFAULT)


def turf_of(venue: str | None) -> str:
    return attrs(venue)["turf"]


def is_indoor(venue: str | None) -> bool:
    return attrs(venue)["indoor"]


def is_artificial(venue: str | None) -> bool:
    return turf_of(venue) == "artificial"
