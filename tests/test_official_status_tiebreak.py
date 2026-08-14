"""選列規則的不變量（`DATA-OFFICIAL-STATUS-TIEBREAK1`）。

釘的是**規則的性質**——全序、與輸入順序無關、三條讀路徑共用同一份、最終決勝鍵不是兩機
各自配號的 `id`——而不是今天資料算出來的那個答案。後者每天被爬蟲改寫，釘它等於釘一張
快照：明天資料一動測試就紅，紅的還不是真的壞掉。

本卡的服務目標是「同一筆事實在本機與生產必須得到相同答案，且該相同性要有結構理由」。
「目前兩機一致」不是理由，所以這裡沒有任何一條測試長成「等於某個實測值」。

⚠️ **這一組不是每一條都釘得住本卡的修法**，實測分兩類（對修法前的實作逐條跑過）：

- **迴歸釘**（修法前紅、修法後綠）：`…does_not_depend_on_the_order…`（修法前 3 種排列
  給 3 種答案）、`…survives_rows_with_no_observation_timestamps`（修法前 `TypeError`），
  以及本檔第二、三節的全部結構斷言（修法前那些常數根本不存在）。
- **特性測試**（修法前也綠）：`…superseded_row_never_wins…`、`…falls_back_to_the_whole_pool`、
  `…content_hash_only_breaks_ties…`。它們釘的不是新行為，而是**這次重寫不准動到的舊語意**
  （現行列優先、無現行列時退回全池、業務鍵壓過雜湊）——把 `active or pool` 的分支改寫成
  排序鍵時，這三條是唯一擋得住語意漂移的東西。不要把它們當成修法有效的證據。
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, date, datetime
from itertools import permutations

import pytest

from cpbl.api.helpers import (
    _SCHEDULE_SELECTION_KEYS,
    OFFICIAL_SCHEDULE_ORDER_BY,
    SOURCE_REVISION_ORDER_BY,
    official_status,
)
from cpbl.api.routers import daily, games

_SEEN = datetime(2026, 8, 14, 2, 10, tzinfo=UTC)


def _row(*, present: int = 1, result: str = "0", day: date = date(2026, 8, 9),
         payload_hash: str = "0" * 64, seen: datetime = _SEEN) -> dict:
    """一列 `cpbl.game_schedule_status_revisions`（投影後的樣子）。"""
    return {
        "raw_present_status": present,
        "raw_game_result": result,
        "raw_game_date": day,
        "payload_hash": payload_hash,
        "fetched_at": seen,
        "last_seen_at": seen,
    }


# --------------------------------------------------------------------------
# 一、規則本身：全序、與輸入順序無關


def test_selection_does_not_depend_on_the_order_rows_were_handed_in() -> None:
    """**本卡的核心不變量。** 業務鍵全部打平時，舊實作的 `max()` 取迭代順序的第一項——
    等於把判定交給呼叫端的列序（`daily.py` 當時連 `ORDER BY` 都沒有，那就是儲存層的
    heap 序）。新實作必須對**每一種排列**給出同一列。"""
    rows = [_row(payload_hash=h * 64) for h in ("a", "b", "c")]

    picked = {official_status(list(order))[1]["payload_hash"]
              for order in permutations(rows)}

    assert len(picked) == 1, f"輸入順序改變了答案：{picked}"


def test_a_superseded_row_never_wins_however_the_rows_arrive() -> None:
    """2026/D/165 的形狀：作廢列（`PresentStatus=0`）在生產端的純 SQL 序裡排第一，
    全表掃描的 heap 序也把它排第一。這裡把它做成**對抗版**——作廢列在後續每一個鍵上
    都贏（日期更新、觀測更晚、雜湊更大），唯一能擋下它的就是「現行列優先」這一條。"""
    current = _row(present=1, day=date(2026, 7, 17), payload_hash="0" * 64,
                   seen=datetime(2026, 8, 1, tzinfo=UTC))
    superseded = _row(present=0, day=date(2026, 9, 15), payload_hash="f" * 64,
                      seen=datetime(2026, 8, 14, tzinfo=UTC))

    for order in ([superseded, current], [current, superseded]):
        _, selected = official_status(order)
        assert selected["raw_present_status"] == 1


def test_every_row_superseded_falls_back_to_the_whole_pool() -> None:
    """沒有任何現行列時不得回 `None`：規則退回全部列裡最好的那一筆（與舊實作的
    `pool = active or schedule_rows` 同語意，改寫成排序鍵之後仍須成立）。"""
    rows = [_row(present=0, day=date(2026, 7, 1), payload_hash="a" * 64),
            _row(present=0, day=date(2026, 9, 1), payload_hash="b" * 64)]

    _, selected = official_status(rows)

    assert selected["raw_game_date"] == date(2026, 9, 1)


def test_the_content_hash_only_breaks_ties_the_business_keys_left_open() -> None:
    """雜湊字典序**沒有業務意義**，它只是唯一有結構保證的最終錨。所以任何一個業務鍵
    分得開的時候，都不許讓雜湊翻盤——否則等於用一個沒有意義的順序覆蓋有意義的順序。"""
    stale_but_bigger_hash = _row(day=date(2026, 7, 1), payload_hash="f" * 64)
    fresh_but_smaller_hash = _row(day=date(2026, 9, 1), payload_hash="0" * 64)

    _, selected = official_status([stale_but_bigger_hash, fresh_but_smaller_hash])

    assert selected["raw_game_date"] == date(2026, 9, 1)


def test_selection_survives_rows_with_no_observation_timestamps() -> None:
    """`last_seen_at`／`fetched_at` 的 `NOT NULL` 保證只存在於 schema，程式端收得到
    任何 dict。缺值時排序鍵必須有定義（排最後），不得與 `datetime` 相比而 `TypeError`。"""
    timeless = {"raw_present_status": 1, "raw_game_result": "0",
                "raw_game_date": date(2026, 8, 9), "payload_hash": "f" * 64}
    normal = _row(day=date(2026, 8, 9), payload_hash="0" * 64)

    _, selected = official_status([timeless, normal])

    assert selected is normal


# --------------------------------------------------------------------------
# 二、「一份規則」是真的一份


def test_the_sql_fragment_is_generated_from_the_python_keys() -> None:
    """SQL 片段與 Python 排序鍵必須出自同一組 `(sql, key)`。這條斷言本身看起來像同義
    反覆——**那正是重點**：有人若把常數改寫成手打字串，或在 Python 端加了一個 SQL 端
    沒有的鍵，兩邊就會漂移，而漂移正是本卡要消滅的東西。"""
    assert OFFICIAL_SCHEDULE_ORDER_BY == ", ".join(sql for sql, _ in _SCHEDULE_SELECTION_KEYS)
    assert all(callable(key) for _, key in _SCHEDULE_SELECTION_KEYS)


def test_both_tables_end_on_a_content_hash_not_on_a_locally_assigned_id() -> None:
    """最終決勝鍵必須是內容雜湊。`id` 由各機自行配號（生產端的同步腳本顯式插入、不搬
    `id`），拿它收尾就等於「同一筆事實在兩台機器上可以有不同答案」。"""
    assert OFFICIAL_SCHEDULE_ORDER_BY.rstrip().endswith("payload_hash DESC")
    assert SOURCE_REVISION_ORDER_BY.rstrip().endswith("source_version DESC")
    for rule in (OFFICIAL_SCHEDULE_ORDER_BY, SOURCE_REVISION_ORDER_BY):
        assert "id DESC" not in rule


# --------------------------------------------------------------------------
# 三、三條讀路徑都套用了那一份規則


_TABLE_RULE = {
    "cpbl.game_schedule_status_revisions": "OFFICIAL_SCHEDULE_ORDER_BY",
    "cpbl.game_source_revisions": "SOURCE_REVISION_ORDER_BY",
}


def _sql_literals(module) -> list[tuple[str, set[str]]]:
    """module 原始碼裡的 SQL 字串 → (字面部分, 被內插的名字)。

    用 AST 而不是 regex：f-string 的內插在原始碼裡是 `FormattedValue` 節點，這樣才問得出
    「這支查詢有沒有真的把那個常數插進去」，而不是問「有沒有一段長得像的文字」。
    """
    tree = ast.parse(inspect.getsource(module))
    inside_fstring = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)
                      for part in node.values}
    out: list[tuple[str, set[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            text = "".join(p.value for p in node.values
                           if isinstance(p, ast.Constant) and isinstance(p.value, str))
            names = {p.value.id for p in node.values
                     if isinstance(p, ast.FormattedValue) and isinstance(p.value, ast.Name)}
            out.append((text, names))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and id(node) not in inside_fstring):
            out.append((node.value, set()))
    return [(text, names) for text, names in out if "SELECT" in text and "FROM" in text]


@pytest.mark.parametrize("module", [games, daily], ids=["games", "daily"])
def test_no_revision_read_path_picks_a_row_by_its_own_rule(module) -> None:
    """每一支讀 revision 表的查詢都必須內插共用常數。**特別是不得沒有 `ORDER BY`**——
    `daily.py` 原本就是那樣，而無序讀取連同一台機器都不保證（實測：同一場 D/165，走
    索引時第一列是現行列，全表掃描時第一列是已作廢的 `PresentStatus=0` 列）。"""
    checked = 0
    for text, names in _sql_literals(module):
        for table, rule in _TABLE_RULE.items():
            if table not in text:
                continue
            checked += 1
            assert rule in names, f"{module.__name__} 有一支讀 {table} 的查詢沒有套用 {rule}"
            assert "id DESC" not in text, f"{module.__name__} 仍以 id 收尾（{table}）"
    assert checked >= 1, f"{module.__name__} 找不到任何 revision 讀路徑——測試自己失效了"


def test_all_three_known_read_paths_are_covered() -> None:
    """守住「三條」這個數字：少於三代表有路徑被搬走而這組測試沒跟上（會靜默失效），
    多於三代表新增了讀路徑——上面那條 parametrize 會替新的那條把關。"""
    paths = [(m.__name__, table)
             for m in (games, daily)
             for text, _ in _sql_literals(m)
             for table in _TABLE_RULE
             if table in text]

    assert len(paths) >= 3, f"讀路徑少於三條，測試可能已與程式碼脫節：{paths}"
