"""#284 身分解析與規則檢查（純函式，佐證取自唯讀匯出 fixture；E04–E06、E08 邏輯面）。

DB 實作與同一組變異的隔離 DB 演練在 test_roster_integration.py。
"""

from __future__ import annotations

from roster_284_support import context_from_fixture

from cpbl.ingest.run_roster import _official_text
from cpbl.rosters.identity import (
    UNKNOWN,
    VERIFIED_IMPORT,
    VERIFIED_NON_IMPORT,
    PlayerRecord,
    check,
    import_status,
)
from cpbl.rosters.parser import parse


def prep(team: str, text: str | None = None, ctx=None):
    text = text or _official_text(2026, "E", team)[0]
    return check(parse(text), ctx or context_from_fixture(2026, team))


def test_real_e_rosters_resolve_ready_with_three_verified_imports():
    for team in ("ACN011", "ADD011"):
        p = prep(team)
        assert p.status == "ready", (team, p.violations, [r.problem for r in p.unresolved])
        assert len(p.import_check["verified_imports"]) == 3
        assert p.import_check["complete"] is True
    # 永田條款：髙塩將樹國籍日本但不占洋將名額（探針 P1）
    add = {r.player_id: r for r in prep("ADD011").rows}
    assert add["0000006818"].import_status == VERIFIED_NON_IMPORT


def test_e04_duplicate_id_is_violation():
    text = _official_text(2026, "E", "ACN011")[0]
    text = text.replace("[捕手]\n", "[捕手]\n羅戈 @id=0000005151\n")
    p = prep("ACN011", text)
    assert any("守位衝突" in v or "重複 ID" in v for v in p.violations)
    text2 = _official_text(2026, "E", "ACN011")[0].replace(
        "菲力士 @id=0000007560", "菲力士 @id=0000007560\n羅戈 @id=0000005151")
    assert any("重複 ID" in v for v in prep("ACN011", text2).violations)


def test_e05_same_name_without_id_lists_candidates_after_evidence_variant():
    ctx = context_from_fixture(2026, "ACN011")
    ctx.evidence.setdefault("0000000108", set()).add("team_roster")  # 佐證變異（probe P2 真實同名對）
    ctx.roster_names["0000000108"] = "勝騎士"
    text = _official_text(2026, "E", "ACN011")[0].replace("勝騎士 @id=0000005604", "勝騎士")
    p = prep("ACN011", text, ctx)
    assert p.status == "draft"
    (bad,) = p.unresolved
    assert {c["player_id"] for c in bad.candidates} == {"0000000108", "0000005604"}
    # 未加變異時，同年同隊範圍內唯一 → 自動解析
    assert prep("ACN011", text).status == "ready"


def test_e06_id_name_mismatch_is_draft_conflict():
    text = _official_text(2026, "E", "ACN011")[0].replace("勝騎士 @id=0000005604", "喬登 @id=0000005604")
    p = prep("ACN011", text)
    (bad,) = p.unresolved
    assert "ID/name 不符" in bad.problem and p.status == "draft"


def test_explicit_id_without_team_year_evidence_is_draft():
    text = _official_text(2026, "E", "ACN011")[0].replace("勝騎士 @id=0000005604", "勝騎士 @id=0000000108")
    (bad,) = prep("ACN011", text).unresolved
    assert "身份證據不足" in bad.problem


def test_e08_import_limit_and_unknown_are_three_state():
    ctx = context_from_fixture(2026, "ADD011")
    pid = "0000006716"  # 張翔，真實本土會員
    ctx.players[pid] = PlayerRecord(pid, ctx.players[pid].name, "美國")
    p = prep("ADD011", ctx=ctx)
    assert p.status == "violation"
    assert len(p.import_check["verified_imports"]) == 4
    assert any("已核洋將 4 人" in v for v in p.violations)
    ctx2 = context_from_fixture(2026, "ADD011")
    ctx2.players[pid] = PlayerRecord(pid, ctx2.players[pid].name, None)
    p2 = prep("ADD011", ctx=ctx2)
    assert p2.status == "ready" and p2.import_check["complete"] is False
    assert [u["player_id"] for u in p2.import_check["unknown"]] == [pid]


def test_import_status_never_guesses_null_as_local():
    assert import_status("0000000001", None) == UNKNOWN
    assert import_status("0000000001", "  ") == UNKNOWN
    assert import_status("0000000001", "中華民國") == VERIFIED_NON_IMPORT
    assert import_status("0000000001", "美國") == VERIFIED_IMPORT
    assert import_status("0000006818", "日本") == VERIFIED_NON_IMPORT   # 永田
    assert import_status("0000000121", "美國") == VERIFIED_NON_IMPORT   # 羅力
    # #284 R1 F2：條款球員國籍 NULL 也是 unknown，不得直接當已核
    for pid in ("0000006818", "0000000121", "0000000762"):
        assert import_status(pid, None) == UNKNOWN
        assert import_status(pid, "") == UNKNOWN


def test_clause_player_null_country_marks_check_incomplete():
    ctx = context_from_fixture(2026, "ADD011")
    pid = "0000006818"  # 髙塩將樹（永田條款），真實 ADD011 會員
    ctx.players[pid] = PlayerRecord(pid, ctx.players[pid].name, None)
    p = prep("ADD011", ctx=ctx)
    row = next(r for r in p.rows if r.player_id == pid)
    assert row.import_status == UNKNOWN
    assert p.status == "ready" and p.import_check["complete"] is False
    assert [u["player_id"] for u in p.import_check["unknown"]] == [pid]
    assert len(p.import_check["verified_imports"]) == 3


def test_count_31_and_33_are_violations():
    text = _official_text(2026, "E", "ACN011")[0]
    lines = text.splitlines()
    first_member = next(i for i, ln in enumerate(lines) if "@id=" in ln)
    p31 = prep("ACN011", "\n".join(lines[:first_member] + lines[first_member + 1:]))
    assert any("人數 31" in v for v in p31.violations)
