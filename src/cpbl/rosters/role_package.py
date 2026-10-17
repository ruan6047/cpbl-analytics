"""多重角色 JSON 輸入；只接受兩隊完整、已明示預期基準的版本。"""

from __future__ import annotations

import re
from uuid import UUID

from cpbl.rosters.canonical import (
    APPROVAL_KEYS,
    ROSTER_SIZE,
    norm,
    revision_hash_v2,
    validate_roles_v2,
)


def _keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{label} 欄位不完整或包含未定義欄位")


def _hash(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} 必須是 SHA-256")


def parse_package(doc: dict) -> dict:
    """純驗證；拒絕換序／重複角色，不猜測或改正會員身份。"""
    _keys(doc, ("format", "year", "kind_code", "approval", "teams"), "package")
    if (doc["format"] != "roster-roles/v2" or type(doc["year"]) is not int
            or not 1990 <= doc["year"] <= 2100 or doc["kind_code"] not in ("E", "C")):
        raise ValueError("package 格式／年度／賽別不合法")
    _keys(doc["approval"], APPROVAL_KEYS, "approval")
    if not isinstance(doc["teams"], list) or len(doc["teams"]) != 2:
        raise ValueError("package 必須同時包含兩隊完整名單")
    teams = []
    codes, ids = set(), set()
    for team in doc["teams"]:
        _keys(team, ("team_code", "roster_id", "membership_hash", "source_hash",
                     "expected_latest_revision", "expected_latest_hash", "members"), "team")
        code, rid = team["team_code"], team["roster_id"]
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9]{6}", code) or code in codes:
            raise ValueError("team_code 不合法或重複")
        try:
            if not isinstance(rid, str) or str(UUID(rid)) != rid or rid in ids:
                raise ValueError
        except (ValueError, AttributeError) as exc:
            raise ValueError("roster_id 不合法或重複") from exc
        codes.add(code)
        ids.add(rid)
        for key in ("membership_hash", "source_hash", "expected_latest_hash"):
            _hash(team[key], key)
        if type(team["expected_latest_revision"]) is not int or team["expected_latest_revision"] < 1:
            raise ValueError("預期角色版號必須為正整數")
        members = team["members"]
        if not isinstance(members, list) or len(members) != ROSTER_SIZE:
            raise ValueError("每隊必須有完整32名會員")
        for member in members:
            _keys(member, ("player_id", "announced_name", "official_position", "tactical_roles",
                           "role_provenance"), "member")
            name = member["announced_name"]
            if not isinstance(name, str) or not norm(name) or norm(name) != name:
                raise ValueError("公告姓名必須為非空NFC字串且無首尾空白")
            roles = member["tactical_roles"]
            provenance = member["role_provenance"]
            ordered = validate_roles_v2(member["official_position"], roles, provenance)
            if list(ordered) != roles:
                raise ValueError("角色順序須符合固定語彙序；順序不代表主次")
            if {k: provenance[k] for k in APPROVAL_KEYS} != doc["approval"]:
                raise ValueError("逐人來源與package全表核准不一致")
        h = revision_hash_v2([(m["player_id"], m["tactical_roles"], m["role_provenance"])
                              for m in members])
        teams.append({**team, "revision_hash": h})
    return {**doc, "teams": sorted(teams, key=lambda t: t["roster_id"])}
