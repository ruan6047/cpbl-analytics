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
import re
import unicodedata
from collections.abc import Iterable

HASH_VERSION = 1

POSITIONS = ("投手", "捕手", "內野手", "外野手")
POSITION_ORDER = {p: i for i, p in enumerate(POSITIONS)}

PITCHER_ROLES = ("輪值", "終結", "勝利組", "長中繼")
FIELDER_ROLES = ("主力", "代打", "守備", "待命")
UNCLASSIFIED = "unclassified"
ROLES = PITCHER_ROLES + FIELDER_ROLES

# v1 語彙與雜湊不改；固定順序只供序列化，不表示主次。
PITCHER_ROLES_V2 = ("先發", "中繼", "終結", "勝利組", "拆彈組", "長中繼")
FIELDER_ROLES_V2 = ("主力", "代打", "代跑", "守備替補", "工具人", "替補", "指定打擊")
ROLES_V2 = PITCHER_ROLES_V2 + FIELDER_ROLES_V2
APPROVAL_KEYS = ("approval_table_sha256", "approval_manifest_sha256", "approval_url")

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


def validate_roles_v2(position: str, roles: list[str], provenance: dict) -> tuple[str, ...]:
    """拒絕缺漏／重複／跨投野角色與不完整來源，不以猜值修正輸入。"""
    allowed = PITCHER_ROLES_V2 if position == "投手" else FIELDER_ROLES_V2
    if (position not in POSITIONS or not isinstance(roles, list) or not roles
            or any(not isinstance(r, str) or r not in allowed for r in roles)
            or len(set(roles)) != len(roles)):
        raise ValueError("v2 角色必須非空、無重複且與官方守位相容")
    if not isinstance(provenance, dict) or set(provenance) != {*APPROVAL_KEYS, "roles"}:
        raise ValueError("v2 來源須含核准表、manifest、核准留言及逐角色來源")
    for key in APPROVAL_KEYS[:2]:
        if not isinstance(provenance[key], str) or not re.fullmatch(r"[0-9a-f]{64}", provenance[key]):
            raise ValueError(f"v2 {key} 必須是 SHA-256")
    url = provenance["approval_url"]
    if (not isinstance(url, str) or not re.fullmatch(
            r"https://github\.com/ruan6047/cpbl-analytics/issues/\d+#issuecomment-\d+", url)):
        raise ValueError("v2 核准來源必須是本專案 Issue 留言")
    sources = provenance["roles"]
    if not isinstance(sources, dict) or set(sources) != set(roles):
        raise ValueError("v2 每個角色必須有且僅有對應來源")
    for source in sources.values():
        if (not isinstance(source, dict)
                or set(source) != {"origin", "source_ids", "original_basis", "original_evidence"}
                or source["origin"] not in ("human", "research")
                or not isinstance(source["source_ids"], list) or not source["source_ids"]
                or any(not isinstance(s, str) or not norm(s) for s in source["source_ids"])
                or len(set(source["source_ids"])) != len(source["source_ids"])
                or any(not isinstance(source[k], str) or not norm(source[k])
                       for k in ("original_basis", "original_evidence"))):
            raise ValueError("v2 逐角色來源格式不完整")
    return tuple(r for r in ROLES_V2 if r in roles)


def revision_hash_v2(rows: Iterable[tuple[str, list[str], dict]]) -> str:
    """v2 雜湊含核准與逐角色來源，不含版號／時間；角色集合無主次。"""
    result = []
    seen = set()
    approval = None
    for pid, roles, provenance in rows:
        pid = norm(pid)
        if not re.fullmatch(r"[0-9]{10}", pid) or pid in seen:
            raise ValueError("v2 球員 ID 必須為唯一十碼")
        seen.add(pid)
        # hash 亦驗完整契約；位置相容性由輸入／DB 以會員守位再驗。
        position = "投手" if roles and roles[0] in PITCHER_ROLES_V2 else "內野手"
        canonical_roles = validate_roles_v2(position, roles, provenance)
        current = {k: provenance[k] for k in APPROVAL_KEYS}
        if approval is not None and current != approval:
            raise ValueError("同一角色版須有相同全表核准來源")
        approval = current
        stable_provenance = {**current, "roles": {
            role: {**provenance["roles"][role],
                   "source_ids": sorted(norm(s) for s in provenance["roles"][role]["source_ids"]),
                   "original_basis": norm(provenance["roles"][role]["original_basis"]),
                   "original_evidence": norm(provenance["roles"][role]["original_evidence"])}
            for role in canonical_roles}}
        result.append([pid, list(canonical_roles), stable_provenance])
    if not result:
        raise ValueError("v2 版本不能為空")
    return _digest({"hash": "roster-annotation/v2", "role_format_version": 2,
                    "roles": sorted(result, key=lambda r: r[0])})
