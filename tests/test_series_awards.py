"""#288 S07 WP-AWARDS 官方系列獎項：輸入驗證、內容雜湊、呈現（純函式）＋接到累計榜的獨立性。

所有輸入都是合成值（官方系列獎項尚未公布；真實匯入另取授權）。DB 層不變量（冪等 migration、不可變、
得主只掛 published、同步語意）在 ``tests/test_series_awards_isolated.py``。
"""

from __future__ import annotations

import pytest

from cpbl.playoffs import series_awards as sa
from cpbl.playoffs import series_summary as ss

URL = "https://www.cpbl.com.tw/news/view?id=1"
TEAMS = {"ACN011", "AAA011"}


def raw(**kw):
    base = {"year": 2026, "kind_code": "C", "status": "published", "source_url": URL,
            "checked_at": "2026-10-26T21:00:00+08:00",
            "awards": [{"award_name": "台灣大賽最有價值球員", "award_type": "series_mvp",
                        "winners": [{"winner_name": "甲", "player_id": "0000000001", "team_code": "ACN011"}]}]}
    base.update(kw)
    return base


def errors_of(r) -> list[str]:
    with pytest.raises(sa.AwardInputError) as exc:
        sa.parse_input(r, team_codes=TEAMS)
    return exc.value.errors


# --- 拒收 ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(("patch", "needle"), [
    ({"source_url": None}, "缺 source_url"),
    ({"source_url": "  "}, "缺 source_url"),
    ({"source_url": "http://www.cpbl.com.tw/x"}, "不是官方站 https"),
    ({"source_url": "https://example.com/x"}, "不是官方站 https"),
    ({"source_url": "https://www.cpbl.com.tw.evil.com/x"}, "不是官方站 https"),
    ({"source_url": "https://www.cpbl.com.tw/a b"}, "不是官方站 https"),
    ({"kind_code": "A"}, "kind_code"),
    ({"status": "maybe"}, "status"),
    ({"checked_at": "2026-10-26T21:00:00"}, "必須帶時區"),
    ({"checked_at": "昨天"}, "ISO 8601"),
    ({"revision": 0}, "revision"),
    ({"year": True}, "year"),
    ({"extra": 1}, "未知欄位"),
])
def test_rejects_bad_header(patch, needle):
    assert any(needle in e for e in errors_of(raw(**patch)))


def test_not_published_must_not_carry_awards_and_published_needs_one():
    assert any("not_published 不能有 awards" in e for e in errors_of(raw(status="not_published")))
    assert any("至少要有一個獎項" in e for e in errors_of(raw(awards=[])))


def test_rejects_bad_awards_and_winners():
    errs = errors_of(raw(awards=[
        {"award_name": "X", "award_type": "series_mvp", "winners": []},
        {"award_name": "X", "award_type": "bogus", "winners": [{"winner_name": "甲"}]},
        {"award_name": "Y", "award_type": "other", "winners": [
            {"winner_name": "乙", "player_id": "123"}, {"winner_name": "丙", "team_code": "ZZZ999"},
            {"winner_name": "丁", "player_id": "0000000002"}, {"winner_name": "戊", "player_id": "0000000002"},
            {"player_id": "0000000003"}]},
    ]))
    for needle in ("至少要有一位得主", "獎項名稱重複", "award_type", "10 碼數字", "不在 team_dim",
                   "得主重複", "缺 winner_name"):
        assert any(needle in e for e in errs), needle


def test_all_errors_listed_at_once():
    errs = errors_of(raw(source_url=None, kind_code="Z", status="?"))
    assert len(errs) >= 3


# --- 接受：共同得主順序、雜湊 ----------------------------------------------------------------------

def test_co_winners_keep_official_order_and_optional_ids():
    item = sa.parse_input(raw(awards=[
        {"award_name": "台灣大賽最有價值球員", "award_type": "series_mvp", "winners": [
            {"winner_name": "乙", "player_id": "0000000002", "team_code": "ACN011"},
            {"winner_name": "甲"}]},
        {"award_name": "其他獎", "award_type": "other", "winners": [{"winner_name": "丙", "team_code": "AAA011"}]},
    ]), team_codes=TEAMS)
    assert [w.winner_name for w in item.awards[0].winners] == ["乙", "甲"]
    assert item.awards[0].winners[1].player_id is None and item.awards[0].winners[1].team_code is None
    assert [a.award_name for a in item.awards] == ["台灣大賽最有價值球員", "其他獎"]


def test_content_hash_ignores_checked_at_but_not_content_or_order():
    a = sa.parse_input(raw(), team_codes=TEAMS)
    b = sa.parse_input(raw(checked_at="2026-10-27T09:00:00+08:00"), team_codes=TEAMS)
    assert a.content_sha256() == b.content_sha256()
    two = [{"winner_name": "甲"}, {"winner_name": "乙"}]
    c = sa.parse_input(raw(awards=[{"award_name": "M", "award_type": "series_mvp", "winners": two}]), team_codes=TEAMS)
    d = sa.parse_input(raw(awards=[{"award_name": "M", "award_type": "series_mvp", "winners": two[::-1]}]),
                       team_codes=TEAMS)
    assert c.content_sha256() != d.content_sha256()
    nb = sa.parse_input(raw(status="not_published", awards=[]), team_codes=TEAMS)
    assert nb.content_sha256() != a.content_sha256()


# --- 呈現：未取得 vs 未公布 vs 已公布 ----------------------------------------------------------------

def rec(status="published", winners=None, revision=2):
    return {"revision": revision, "status": status, "source_url": URL, "checked_at": "2026-10-26T13:00:00+00:00",
            "winners": winners if winners is not None else [
                {"award_seq": 1, "ordinal": 1, "award_name": "MVP", "award_type": "series_mvp",
                 "player_id": "0000000002", "winner_name": "乙", "team_code": "ACN011"},
                {"award_seq": 1, "ordinal": 2, "award_name": "MVP", "award_type": "series_mvp",
                 "player_id": None, "winner_name": "甲", "team_code": None},
                {"award_seq": 2, "ordinal": 1, "award_name": "其他", "award_type": "other",
                 "player_id": None, "winner_name": "丙", "team_code": "AAA011"}]}


def test_awards_json_states():
    assert sa.awards_json(None, "C") == {"status": "pending_source"}          # 表未建／讀取失敗
    assert sa.awards_json({}, "C") == {"status": "pending_source"}            # 尚無 revision
    assert sa.awards_json({"E": rec()}, "C") == {"status": "pending_source"}  # 只有別系列
    nb = sa.awards_json({"C": rec(status="not_published", winners=[])}, "C")
    assert nb == {"status": "not_published", "revision": 2, "source_url": URL,
                  "checked_at": "2026-10-26T13:00:00+00:00"}
    assert sa.awards_json({"C": rec(winners=[])}, "C") == {"status": "pending_source"}   # fail closed


def test_awards_json_groups_co_winners_in_order():
    out = sa.awards_json({"C": rec()}, "C")
    assert out["status"] == "published" and out["revision"] == 2
    assert [a["award_name"] for a in out["awards"]] == ["MVP", "其他"]
    assert out["awards"][0]["winners"] == [{"player_id": "0000000002", "name": "乙", "team_code": "ACN011"},
                                           {"player_id": None, "name": "甲", "team_code": None}]


# --- 接到累計榜：與 PA 完整度獨立 --------------------------------------------------------------------

@pytest.fixture
def ctx():
    from postseason_context_inputs import NOW_2026, games, inputs

    from cpbl import postseason_contract as pc
    return pc.compute_series_context(inputs(2026, games_override=games(2026)), now=NOW_2026)


def test_awards_survive_pa_read_failure(ctx):
    rows = ss.SeriesRows(pa_ok=False, awards={"E": rec()})
    e = ss.aggregate(ctx, "E", rows)
    assert e.status == "unavailable"
    assert e.awards["status"] == "published"
    assert ss.summary_json(ss.aggregate_all(ctx, rows), {}, current="C", previous="E")["previous"]["awards"][
        "status"] == "published"


def test_awards_store_missing_is_pending(ctx):
    e = ss.aggregate(ctx, "E", ss.SeriesRows(awards=None))
    assert e.awards == {"status": "pending_source"}
    assert ss.aggregate(ctx, "E", None).awards == {"status": "pending_source"}
