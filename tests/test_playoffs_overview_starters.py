"""#285 批次 E：第 1 區下一場預告接 S11 官方先發（E-Q2 甲）＋累計榜只給所選系列（方案 A）。

場次取 2026 真實 E1–E4、C1–C7（``tests/fixtures/postseason_real_years.json``）；官方賽程列形狀同
``test_playoffs_watch_reader.py`` 的 ``rev``（本機真實 ``game_schedule_status_revisions`` 投影），先發 acnt 為注入值。
"""

from __future__ import annotations

from datetime import date, datetime

from postseason_context_inputs import BRO, DRAGON, NOW_2026, inputs

from cpbl import postseason_contract as pc
from cpbl.playoffs import overview as ov
from cpbl.playoffs import series_summary as ss
from cpbl.playoffs import watch_reader as wr


def rev(day, vt, ht, vpa=None, hpa=None, *, vpn=None, hpn=None, present=1, h="h", fetched="2026-10-16T02:10:12+00:00"):
    return {"raw_present_status": present, "raw_game_result": None, "raw_game_date": date.fromisoformat(day),
            "visiting_team_code": vt, "home_team_code": ht, "visiting_pitcher_acnt": vpa, "home_pitcher_acnt": hpa,
            "visiting_pitcher_name": vpn, "home_pitcher_name": hpn, "payload_hash": h,
            "fetched_at": datetime.fromisoformat(fetched), "last_seen_at": datetime.fromisoformat(fetched)}


CTX = pc.compute_series_context(inputs(2026), now=NOW_2026)


def _ov(starters=None, series=None):
    i = ov.OverviewInputs(context=CTX, names={}, series_summary=ss.aggregate_all(CTX, None), summary_names={},
                          starters=starters or {})
    return ov.compute_overview(i, series)


def _texts(o):
    return [(s["team_code"], s["status"], s["text"]) for s in o["series_section"]["next_game"]["starters"]]


ANNOUNCED = [rev("2026-10-17", BRO, DRAGON, "0000005604", "0000002345", vpn="勝騎士", h="a1")]


def test_three_states_pass_through_and_match_watch_reader():
    assert CTX["state"]["by_series"]["C"]["target_game_key"]["game_sno"] == 1
    a = _ov({"C": (ANNOUNCED, {"0000002345": {"player_name": "鄭浩均"}})})
    assert _texts(a) == [(BRO, "announced", "勝騎士"), (DRAGON, "announced", "鄭浩均")]
    p = _ov({"C": ([rev("2026-10-17", BRO, DRAGON)], {})})
    assert _texts(p) == [(BRO, "pending", "待公告"), (DRAGON, "pending", "待公告")]
    u = _ov({"C": (None, {})})                                       # 讀取失敗只降級
    assert _texts(u) == [(BRO, "unknown", "暫時無法取得"), (DRAGON, "unknown", "暫時無法取得")]
    # 與第 4 區同一份純函式、同一份輸入 ⇒ 同字
    w, _ = wr.official_starters(ANNOUNCED, target_date=date(2026, 10, 17), teams=[BRO, DRAGON],
                                names={"0000002345": {"player_name": "鄭浩均"}})
    assert a["series_section"]["next_game"]["starters"] == w


def test_starters_only_on_next_game_not_chips_and_not_in_context_version():
    a = _ov({"C": (ANNOUNCED, {})})
    b = _ov({"C": (None, {})})
    assert a["context_version"] == b["context_version"] == CTX["context_version"]
    assert all("starters" not in c for c in a["series_section"]["current"]["games"])
    assert {k: v for k, v in a["series_section"]["next_game"].items() if k != "starters"} == \
        a["series_section"]["current"]["games"][0]
    # 降級不影響第 1 區其他欄位
    assert {k: v for k, v in a["series_section"].items() if k != "next_game"} == \
        {k: v for k, v in b["series_section"].items() if k != "next_game"}
    m = {x["source"]: x for x in a["source_manifest"]}
    assert m["official_starters"]["status"] == "ok" and m["official_starters"]["scope"] == "targets:C"
    assert {x["source"]: x for x in b["source_manifest"]}["official_starters"]["status"] == "unavailable"
    assert [x["source"] for x in a["source_manifest"]][-2:] == ["pa_published", "players"]


def test_date_or_team_mismatch_is_pending_and_e_page_has_no_preview():
    wrong = _ov({"C": ([rev("2026-10-18", BRO, DRAGON, "0000005604", "0000002345")], {})})
    assert [s["status"] for s in wrong["series_section"]["next_game"]["starters"]] == ["pending", "pending"]
    e = _ov({"C": (ANNOUNCED, {})}, "E")
    assert e["series_section"]["next_game"] is None


def test_series_summary_previous_is_none_on_c_and_e_page_unchanged():
    c, e = _ov(), _ov(series="E")
    assert c["series_summary"]["previous"] is None and c["series_summary"]["current"]["kind_code"] == "C"
    aggs = ss.aggregate_all(CTX, None)
    # E 頁與改前相同：改前 E 頁 previous 本來就是 None（E 之前沒有系列）
    assert e["series_summary"] == ss.summary_json(aggs, {}, current="E", previous=None)
    assert c["series_section"]["previous"]["kind_code"] == "E"           # E-Q1 不停送
