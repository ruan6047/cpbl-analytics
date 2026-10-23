"""#357 今日切片：同一事件號多筆時，`game_livelog` 寫入「原文第一筆非結束標記列」。

被修的形狀：www `getlive` 的 `LiveLogJson` 在每場最後一個事件號下會出現兩筆——
先是實際打席／事件（PLAY），後面跟一筆「比賽結束」或「主審裁定比賽結束」標記。
`game_livelog` 以 (year, kind_code, game_sno, main_event_no) 為鍵，`_upsert` 用
`executemany` 逐列 `ON CONFLICT DO UPDATE`，同鍵後到者勝，於是每場最後事件的
content 被標記覆蓋（#343 研究 3、#357 研究 1／2：2026 共 608 場全為此形狀）。

fixture 是 #357 研究 2 抓下的 www 原文，逐位元複製、未改動（sha256 與
`~/.wf-evidence/cpbl-analytics/357/research-2/www-raw/SHA256SUMS` 相同，下方釘死）：
- 2026-C-4：再見一壘安打（標記＝比賽結束）
- 2026-D-118：盜壘刺（標記＝主審裁定比賽結束）
- 2026-D-163：教練暫停（標記＝主審裁定比賽結束）

負控：在舊規則（全部列照原文順序輸出、交給 `_upsert` 後到者勝）下，
`test_real_fixture_*` 的列數與最後事件 content 斷言必紅；紅綠紀錄見
`~/.wf-evidence/cpbl-analytics/357/exec-1/`。
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest.cpbl_gamelog import _LL_COLS, _livelog_rows

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "livelog_357_www"

# (檔名, sha256, 重複的事件號, 期望最後事件 content＝原文第一筆, 期望 is_special_event)
CASES = [
    ("2026-C-4.json.gz",
     "0dc78b821973d71ed8672d05124043cfeaf33a2de9923998479bb61d5937d916",
     "1120021000",
     "擊出左外野高飛球，一壘安打 。1分打點。 二壘跑者岳政華回本壘得分。",
     False),
    ("2026-D-118.json.gz",
     "ef03af1d1e3a882d91cec402c586b0fbc65cf9ee639d7ca45c6889e2ff9be80b",
     "0720019000",
     "壞球。 二壘跑者黃鈞麟出局-盜壘刺 3人出局。",
     False),  # 原文 IsSpecialEvent="2"，`_b()` 轉成 False（現行轉換不變）
    ("2026-D-163.json.gz",
     "437ecc3b7edd665ab1a6c74d02f109f375bbf3a1b2ce0fcdd922ca1906ecf57a",
     "0720032000",
     "教練暫停",
     False),  # 原文 IsSpecialEvent="3"
]

_PK = 4
# 測試端獨立寫死的標記字面（不 import 被測碼的判定，舊碼上才紅在內容斷言而非 AttributeError）
_MARKERS = {"比賽結束", "主審裁定比賽結束"}
_IDX_EVENT = _LL_COLS.split(",").index("main_event_no")
_IDX_CONTENT = _LL_COLS.split(",").index("content")
_IDX_SPECIAL = _LL_COLS.split(",").index("is_special_event")


def _load(name: str) -> list[dict]:
    payload = json.loads(gzip.decompress((FIXTURES / name).read_bytes()))
    return json.loads(payload["LiveLogJson"])


def _ident(name: str) -> tuple[int, str, int]:
    year, kind, sno = name.removesuffix(".json.gz").split("-")
    return int(year), kind, int(sno)


def _apply_upsert(rows: list[tuple]) -> dict[tuple, tuple]:
    """模擬 `_upsert` 對同一批 rows 的 DB 終態：逐列 ON CONFLICT DO UPDATE，後到者勝。"""
    state: dict[tuple, tuple] = {}
    for r in rows:
        state[r[:_PK]] = r
    return state


@pytest.mark.parametrize(("name", "sha", "_dup", "_content", "_special"), CASES)
def test_fixture_is_byte_identical_to_research_2(name, sha, _dup, _content, _special):
    assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == sha


@pytest.mark.parametrize(("name", "_sha", "dup", "content", "special"), CASES)
def test_real_fixture_last_event_content_after_upsert(name, _sha, dup, content, special):
    """DB 終態（後到者勝）下，最後事件 content＝原文第一筆。舊規則下此處得到結束標記。"""
    raw = _load(name)
    group = [r for r in raw if r.get("MainEventNo") == dup]
    assert len(group) == 2 and group[0]["Content"] == content  # 前提：原文形狀＝PLAY 在前、標記在後
    assert group[1]["Content"] in _MARKERS

    last = _apply_upsert(_livelog_rows(*_ident(name), raw))[(*_ident(name), dup)]
    assert last[_IDX_CONTENT] == content
    assert last[_IDX_SPECIAL] is special


@pytest.mark.parametrize(("name", "_sha", "_dup", "_content", "_special"), CASES)
def test_real_fixture_one_row_per_event_no(name, _sha, _dup, _content, _special):
    """送進 _upsert 的批次一號一列；結束標記列今天不入庫。"""
    raw = _load(name)
    rows = _livelog_rows(*_ident(name), raw)
    assert len(rows) == len({r.get("MainEventNo") for r in raw if r.get("MainEventNo")})
    assert len({r[:_PK] for r in rows}) == len(rows)
    assert not any(r[_IDX_CONTENT] in _MARKERS for r in rows)


@pytest.mark.parametrize(("name", "_sha", "dup", "_content", "_special"), CASES)
def test_real_fixture_other_events_unchanged(name, _sha, dup, _content, _special):
    """不同號列零變動：每一列都等於現行轉換對該原文列單獨套用的結果。"""
    raw = _load(name)
    ident = _ident(name)
    rows = {r[_IDX_EVENT]: r for r in _livelog_rows(*ident, raw)}
    singles = [r for r in raw if r.get("MainEventNo") and r["MainEventNo"] != dup]
    assert len(singles) == len(rows) - 1
    for r in singles:
        assert rows[r["MainEventNo"]] == _livelog_rows(*ident, [r])[0]


def test_marker_before_play_still_keeps_play():
    """非預期形狀①（2026 未見）：標記在 PLAY 之前，仍取第一筆非標記列。"""
    name, _sha, dup, content, _special = CASES[0]
    raw = _load(name)
    i_play = next(i for i, r in enumerate(raw) if r.get("MainEventNo") == dup)
    swapped = raw[:i_play] + [raw[i_play + 1], raw[i_play]] + raw[i_play + 2:]
    final = _apply_upsert(_livelog_rows(*_ident(name), swapped))
    assert final[(*_ident(name), dup)][_IDX_CONTENT] == content


def test_group_of_only_markers_keeps_first_marker():
    """非預期形狀②：全組都是標記時取第一筆（不丟掉這個事件號）。"""
    name, _sha, dup, _content, _special = CASES[1]
    raw = _load(name)
    marker = next(r for r in raw if r.get("MainEventNo") == dup and r["Content"] == "主審裁定比賽結束")
    only_markers = [r for r in raw if r.get("MainEventNo") != dup] + [marker, {**marker, "Content": "比賽結束"}]
    rows = _livelog_rows(*_ident(name), only_markers)
    final = _apply_upsert(rows)
    assert final[(*_ident(name), dup)][_IDX_CONTENT] == "主審裁定比賽結束"
    assert len(rows) == len(final)


@pytest.mark.parametrize("text", ["比賽結束", "主審裁定比賽結束", " 比賽結束。", "主審裁定比賽結束。 "])
def test_end_marker_recognised(text):
    assert cpbl_gamelog._is_end_marker(text)


@pytest.mark.parametrize("text", [None, "", "教練暫停", "比賽結束前暫停", "擊出左外野高飛球，一壘安打 。"])
def test_non_marker_not_recognised(text):
    assert not cpbl_gamelog._is_end_marker(text)
