"""名單的正規化與三種雜湊（hash_version=1）。

序列化沿用 repo 既有 roster_version 指紋慣例：
``json.dumps(…, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`` → UTF-8 → SHA-256 hex。

- membership_hash：年度／賽別／隊伍＋[官方守位, player_id]（依守位序、ID 排序）。
  忽略空白、列序、戰術角色與公告姓名（PRD「canonical membership」）。
- source_hash：來源網址、公告日期與精度、[player_id, 公告姓名]（依 ID 排序）。
  來源差異必須明示，故網址／日期／公告姓名不同即不同；raw_text 不入雜湊。
- revision_hash：[player_id, 戰術角色]（依 ID 排序）；同一版 32 列同值。

字串正規化只做 Unicode NFC＋去首尾空白。⛔ 不替換間隔號等字元、不做模糊比對。
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable

HASH_VERSION = 1

POSITIONS = ("投手", "捕手", "內野手", "外野手")
POSITION_ORDER = {p: i for i, p in enumerate(POSITIONS)}

PITCHER_ROLES = ("輪值", "終結", "勝利組", "長中繼")
FIELDER_ROLES = ("主力", "代打", "守備", "待命")
UNCLASSIFIED = "unclassified"
ROLES = PITCHER_ROLES + FIELDER_ROLES

ROSTER_SIZE = 32
IMPORT_LIMIT = 3


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def role_compatible(position: str, role: str | None) -> bool:
    """投手只能投手四角色、野手（捕手／內野手／外野手）只能野手四角色；未標＝相容。"""
    if role is None or role == UNCLASSIFIED:
        return True
    return role in (PITCHER_ROLES if position == "投手" else FIELDER_ROLES)


def _digest(doc: dict) -> str:
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def membership_hash(year: int, kind_code: str, team_code: str,
                    members: Iterable[tuple[str, str]]) -> str:
    """members＝(official_position, player_id)。"""
    rows = sorted(((norm(p), norm(pid)) for p, pid in members),
                  key=lambda r: (POSITION_ORDER.get(r[0], 99), r[1]))
    return _digest({
        "hash": "series-roster-membership/v1",
        "year": int(year),
        "kind_code": norm(kind_code),
        "team_code": norm(team_code),
        "members": [list(r) for r in rows],
    })


def source_hash(source_url: str, published_date: str, published_precision: str,
                announced: Iterable[tuple[str, str]]) -> str:
    """announced＝(player_id, 公告姓名)；published_date 為 ISO 日期字串。"""
    rows = sorted((norm(pid), norm(name)) for pid, name in announced)
    return _digest({
        "hash": "series-roster-source/v1",
        "source_url": norm(source_url),
        "published_date": norm(str(published_date)),
        "published_precision": norm(published_precision),
        "announced": [list(r) for r in rows],
    })


def revision_hash(roles: Iterable[tuple[str, str]]) -> str:
    """roles＝(player_id, tactical_role)；未標角色以 'unclassified' 傳入。"""
    rows = sorted((norm(pid), norm(role)) for pid, role in roles)
    return _digest({"hash": "roster-annotation/v1", "roles": [list(r) for r in rows]})
