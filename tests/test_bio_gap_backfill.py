"""INGEST-PLAYER-BIO-GAP1 的寫入邊界守衛。

**為什麼是測試**：本卡只該補 `country`／`birthday` 兩欄，但 canonical
`cpbl_player_bio._upsert` 的語意是「用 person 頁全量更新一列」——它無條件以
`EXCLUDED` 覆蓋 height/weight/debut/education/birthplace/draft，並用頁面姓名改寫
`name`。iteration 1 曾試圖用「列舉不可寫的徵狀」來擋，結果證實會漏：擋了挑戰頁與
查無此人頁，仍漏掉**部分解析頁**（有姓名、只有 country 有值 → 其餘欄被 None 覆蓋）
與**姓名不符頁**（寫入後把目標列改成別人）。

iteration 2 改為限制寫入語句能觸及的範圍（專用窄 UPDATE + COALESCE）。本檔因此
斷言兩件事，而非斷言分類字串：
1. `FILL_SQL` 的欄位邊界——只碰兩個資料欄與時間戳，且都是 COALESCE。
2. 實際跑 `_loop`，斷言寫入函式**有沒有被呼叫、帶什麼參數**。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill_player_bio_gap1", ROOT / "scripts" / "backfill_player_bio_gap1.py")
assert SPEC and SPEC.loader
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)

# 本卡絕對不可被寫入語句碰到的欄位（iteration 1 的實際損害面）
FORBIDDEN_COLUMNS = ("height_cm", "weight_kg", "debut", "education",
                     "birthplace", "draft", "name", "bats", "throws")

CHALLENGE = "<html><body><script>challenge()</script></body></html>"
NO_PERSON = '<html><body><div class="footer">中華職棒全球資訊網</div></body></html>'


def _person(name: str, *, country: str | None = "美國",
            birthday: str | None = "1995/04/21", height: bool = True) -> str:
    """組一個 person 頁；可分別關掉國籍／生日／身高體重以模擬部分解析。"""
    parts = ['<div class="footer">中華職棒全球資訊網</div>', f'<div class="name">{name}</div>']
    if height:
        parts.append('<dd><div class="label">身高/體重</div>'
                     '<div class="desc">190 (CM) / 95 (KG)</div></dd>')
    if country:
        parts.append(f'<dd><div class="label">國籍/出生地</div>'
                     f'<div class="desc">{country}</div></dd>')
    if birthday:
        parts.append(f'<dd><div class="label">生日</div><div class="desc">{birthday}</div></dd>')
    return f"<html><body>{''.join(parts)}</body></html>"


# ───────────────────── 1. 寫入語句的欄位邊界 ─────────────────────

def test_fill_sql_touches_only_the_two_target_columns_and_timestamp():
    sql = backfill.FILL_SQL
    assert sql.strip().upper().startswith("UPDATE")
    set_clause = re.search(r"\bSET\b(.*?)\bWHERE\b", sql, re.S | re.I).group(1)
    assigned = {m.group(1) for m in re.finditer(r"(\w+)\s*=", set_clause)}
    assert assigned == {"country", "birthday", "bio_updated_at"}, (
        f"寫入語句多碰了欄位：{assigned}")


def test_fill_sql_never_mentions_the_columns_upsert_would_have_wiped():
    for col in FORBIDDEN_COLUMNS:
        assert not re.search(rf"\b{col}\b", backfill.FILL_SQL), (
            f"{col} 不得出現在本卡的寫入語句——這正是 iteration 1 的資料損害面")


def test_fill_sql_uses_coalesce_so_existing_values_are_never_overwritten():
    for col in ("country", "birthday"):
        assert re.search(rf"{col}\s*=\s*COALESCE\(\s*{col}\s*,", backfill.FILL_SQL, re.I), (
            f"{col} 必須是 COALESCE(既有, 新值)，否則會覆蓋既有非空值")


# ───────────────────── 2. 實際寫入呼叫（驅動 _loop） ─────────────────────

def _run_loop(monkeypatch, tmp_path, pages: dict[str, str],
              targets: list[tuple[str, str]], *, dry_run: bool = False):
    """跑 _loop，攔截 fetch 與 fill_gap；回 (fill_gap 呼叫紀錄, rows)。"""
    calls: list[tuple] = []
    monkeypatch.setattr(backfill, "fetch", lambda acnt: (pages[acnt], "stub"))
    monkeypatch.setattr(backfill, "fill_gap",
                        lambda acnt, country, birthday: calls.append((acnt, country, birthday)))
    args = SimpleNamespace(delay=0, html_dir=tmp_path, dry_run=dry_run)
    rows: list[dict] = []
    backfill._loop(args, targets, rows)
    return calls, rows


def test_degraded_pages_never_reach_the_write(monkeypatch, tmp_path):
    """挑戰頁與查無此人頁：一次寫入都不得發生。"""
    pages = {"A": CHALLENGE, "B": NO_PERSON}
    calls, rows = _run_loop(monkeypatch, tmp_path, pages, [("A", "力亞士"), ("B", "龍聖")])
    assert calls == []
    assert [r["write_reason"] for r in rows] == ["no_person_on_page"] * 2


def test_partial_page_writes_only_the_parsed_field_and_cannot_wipe_others(
        monkeypatch, tmp_path):
    """iteration 1 的漏洞①：有姓名、只有國籍 → 仍可寫，但只能碰那兩欄。

    生日為 None 會原樣傳入 COALESCE，既有值不受影響；其餘欄位連出現在語句裡都不會。
    """
    pages = {"A": _person("力亞士", birthday=None, height=False)}
    calls, rows = _run_loop(monkeypatch, tmp_path, pages, [("A", "力亞士")])
    assert calls == [("A", "美國", None)]
    assert rows[0]["wrote"] is True


def test_name_mismatch_is_refused(monkeypatch, tmp_path):
    """iteration 1 的漏洞②：抓到別人的頁 → 值不是這個人的，拒寫並記錄。"""
    pages = {"A": _person("另一個人")}
    calls, rows = _run_loop(monkeypatch, tmp_path, pages, [("A", "力亞士")])
    assert calls == []
    assert rows[0]["write_reason"] == "name_mismatch"
    assert rows[0]["page_name"] == "另一個人"


def test_person_page_without_either_field_is_not_written(monkeypatch, tmp_path):
    pages = {"A": _person("力亞士", country=None, birthday=None)}
    calls, rows = _run_loop(monkeypatch, tmp_path, pages, [("A", "力亞士")])
    assert calls == []
    assert rows[0]["write_reason"] == "nothing_to_fill"


def test_good_page_writes_both_fields(monkeypatch, tmp_path):
    pages = {"A": _person("力亞士")}
    calls, _ = _run_loop(monkeypatch, tmp_path, pages, [("A", "力亞士")])
    assert calls == [("A", "美國", "1995-04-21")]


def test_dry_run_never_writes(monkeypatch, tmp_path):
    pages = {"A": _person("力亞士")}
    calls, rows = _run_loop(monkeypatch, tmp_path, pages, [("A", "力亞士")], dry_run=True)
    assert calls == []
    assert rows[0]["wrote"] is False
    assert rows[0]["write_reason"] == "ok"  # 判定可寫，但 dry-run 不執行


def test_consecutive_challenge_pages_trip_the_circuit(monkeypatch, tmp_path):
    """節流時官網回的是「成功的挑戰頁」而非例外——必須照樣中止整輪。"""
    pages = {c: CHALLENGE for c in "ABC"}
    with pytest.raises(RuntimeError, match="疑似反爬節流"):
        _run_loop(monkeypatch, tmp_path, pages,
                  [("A", "甲"), ("B", "乙"), ("C", "丙")])


# ───────────────────── 3. 範圍閘門（F3；非對稱） ─────────────────────
#
# 兩個方向的差集意義相反，閘門必須非對稱：
#   found - expected（DB 有、卡面無）＝ 未授權的新缺值球員 → 硬中止
#   expected - found（卡面有、DB 無）＝ 已補滿 → 進度，跳過
# iteration 2 曾對稱地要求「集合完全相同」，直接打死兩個合法情境：斷路器中止後
# 冷卻續跑（剩下的必然少於 14），以及補完後重跑（卡面要求可重跑的冪等 no-op）。

class _FakeCursor:
    """無寫入的假 cursor：只餵 target_ids 的 SELECT 結果。"""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=None):
        assert sql.strip().upper().startswith("SELECT"), "target_ids 只該讀"
        return self

    def fetchall(self):
        return self._rows


def _rows_for(ids):
    return [(pid, backfill.EXPECTED_GAP_IDS[pid]) for pid in sorted(ids)]


def test_resume_after_circuit_breaker_runs_the_remaining_players():
    """①部分完成後可續跑——斷路器的意義就是冷卻後續跑，閘門不得擋死。"""
    remaining = sorted(backfill.EXPECTED_GAP_IDS)[1:]      # 已補 1 人，剩 13
    targets = backfill.target_ids(_FakeCursor(_rows_for(remaining)))
    assert len(targets) == 13
    assert [pid for pid, _ in targets] == remaining


def test_rerun_after_full_completion_is_a_successful_noop():
    """②全部補完後重跑＝成功的 no-op，不是失敗（卡面：寫入冪等、可重跑）。"""
    targets = backfill.target_ids(_FakeCursor([]))
    assert targets == []


def test_unauthorized_extra_id_still_hard_aborts():
    """③新登錄球員缺 bio ＝ 未授權的範圍擴張 → 硬中止，維持現狀。"""
    with pytest.raises(SystemExit, match="未授權"):
        backfill.target_ids(_FakeCursor(
            _rows_for(backfill.EXPECTED_GAP_IDS) + [("0000009999", "新人")]))


def test_extra_id_aborts_even_when_others_are_already_done():
    """未授權 ID 的中止不因「其他人已補滿」而被稀釋。"""
    remaining = sorted(backfill.EXPECTED_GAP_IDS)[5:]
    with pytest.raises(SystemExit, match="未授權"):
        backfill.target_ids(_FakeCursor(_rows_for(remaining) + [("0000009999", "新人")]))


def test_check_scope_reports_which_players_are_already_done():
    remaining = sorted(backfill.EXPECTED_GAP_IDS)[3:]
    done = backfill.check_scope(set(remaining))
    assert done == set(sorted(backfill.EXPECTED_GAP_IDS)[:3])


def test_scope_matching_the_card_exactly_reports_nothing_done():
    assert backfill.check_scope(set(backfill.EXPECTED_GAP_IDS)) == set()


def test_expected_ids_are_exactly_the_fourteen_from_the_card():
    assert len(backfill.EXPECTED_GAP_IDS) == 14
