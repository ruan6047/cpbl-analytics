"""#470 教練團奪冠紀錄：純函式（載入／驗證／過濾／歸戶）與資料檔結構測試（不碰 DB）。"""

from __future__ import annotations

import copy

from cpbl.api.staff_championships import staff_for_name, staff_for_player, validate

VERIFIED = {2023: "AAA011", 2025: "AJL011"}


def _data() -> dict:
    tw = {"site": "twbsball", "title": "味全龍隊/味全龍隊的職棒十五年",
          "url": "https://twbsball.dils.tku.edu.tw/wiki/index.php/味全龍隊/味全龍隊的職棒十五年",
          "revid": 1, "timestamp": "2026-03-23T03:18:23Z"}
    zh = {"site": "zhwiki", "title": "Template:味全龍2023年中華職棒總冠軍",
          "url": "https://zh.wikipedia.org/wiki/Template:味全龍2023年中華職棒總冠軍",
          "revid": 2, "timestamp": "2025-10-28T04:45:13Z"}
    return {
        "schema_version": 1,
        "through_year": 2025,
        "generated_at": "2026-11-29T00:00:00+08:00",
        "generator": {"script": "scripts/build_championship_staff.py", "commit": "x"},
        "note": "名單不保證完整",
        "team_years": [
            {"year": 2023, "champion_team_code": "AAA011", "team_name": "味全龍",
             "status": "listed", "sources": [tw, zh],
             "staff": [
                 {"name": "張泰山", "wiki_title": "張泰山", "aliases": [], "level": "一軍",
                  "title": "打擊教練", "sources": ["twbsball", "zhwiki"], "single_source": False,
                  "supplement_urls": [], "note": None, "player_id": None},
                 {"name": "王昊", "wiki_title": "王昊", "aliases": [], "level": "一軍",
                  "title": None, "sources": ["twbsball"], "single_source": True,
                  "supplement_urls": [], "note": None, "player_id": None},
                 {"name": "賈西", "wiki_title": None, "aliases": ["賈　西"], "level": "二軍",
                  "title": "投手教練", "sources": ["twbsball", "zhwiki"], "single_source": False,
                  "supplement_urls": [], "note": "層級衝突", "player_id": None},
             ]},
            {"year": 2025, "champion_team_code": "AJL011", "team_name": "樂天桃猿",
             "status": "missing", "sources": [], "staff": []},
        ],
    }


def test_player_gets_staff_title_by_unique_name():
    out = staff_for_player(_data(), VERIFIED, "0000000486", "張泰山", name_unique=True)
    assert out is not None
    assert out["through_year"] == 2025
    assert [(i["year"], i["team_code"], i["level"], i["title"]) for i in out["items"]] == [
        (2023, "AAA011", "一軍", "打擊教練")]
    item = out["items"][0]
    assert item["team_name"] == "味全龍"
    assert item["single_source"] is False
    assert {s["site"] for s in item["sources"]} == {"twbsball", "zhwiki"}
    assert all(s["url"].startswith("https://") for s in item["sources"])
    assert out["missing_years"] == [2025]


def test_player_ambiguous_name_not_attributed():
    assert staff_for_player(_data(), VERIFIED, "0000000486", "張泰山", name_unique=False) is None


def test_explicit_player_id_wins_over_name():
    d = _data()
    d["team_years"][0]["staff"][1]["player_id"] = "P1"
    # 明填 player_id：只歸該 id，不再以姓名歸到別人
    assert staff_for_player(d, VERIFIED, "P1", "別名", name_unique=True)["items"][0]["year"] == 2023
    assert staff_for_player(d, VERIFIED, "P2", "王昊", name_unique=True) is None


def test_unverified_or_mismatched_year_filtered():
    assert staff_for_player(_data(), {2025: "AJL011"}, "x", "張泰山", True) is None
    assert staff_for_player(_data(), {2023: "ACN011"}, "x", "張泰山", True) is None


def test_coach_page_by_name_and_alias_normalised():
    out = staff_for_name(_data(), VERIFIED, "王昊")
    assert out["items"][0]["single_source"] is True
    # 全形空白／間隔號正規化，別名也命中
    assert staff_for_name(_data(), VERIFIED, "賈　西")["items"][0]["level"] == "二軍"
    assert staff_for_name(_data(), VERIFIED, "賈西")["items"][0]["note"] == "層級衝突"
    assert staff_for_name(_data(), VERIFIED, "無此人") is None


def test_validate_accepts_fixture_and_rejects_bad_level():
    assert validate(_data()) == []
    bad = copy.deepcopy(_data())
    bad["team_years"][0]["staff"][0]["level"] = "三軍"
    assert validate(bad)
    bad = copy.deepcopy(_data())
    bad["team_years"][0]["staff"][0]["sources"] = ["nowhere"]
    assert validate(bad)


# ---------------------------------------------------------------------------
# 打包資料檔（resources/championship_staff.v1.json）的結構與驗收不變量
# ---------------------------------------------------------------------------


def test_resource_file_valid_and_has_zhang_taishan_2023():
    from cpbl.api.staff_championships import load

    data = load()
    assert validate(data) == []
    out = staff_for_player(data, {2023: "AAA011"}, "0000000486", "張泰山", name_unique=True)
    assert out is not None
    assert any(i["year"] == 2023 and i["team_code"] == "AAA011" and i["level"] == "一軍"
               for i in out["items"])


class _Cur:
    """假 cursor：依 SQL 片段回固定列（不碰 DB）。"""

    def __init__(self, players: dict[str, str]):
        self.players = players
        self._rows: list = []

    def execute(self, sql, params=None):
        if "FROM cpbl.championships" in sql:
            self._rows = [(2023, "AAA011")]
        elif "WHERE id = %s" in sql:
            self._rows = [(self.players[params[0]],)] if params[0] in self.players else []
        elif "count(*) FROM cpbl.players" in sql:
            self._rows = [(sum(1 for n in self.players.values() if n == params[0]),)]
        else:  # pragma: no cover
            raise AssertionError(sql)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_fetch_wrappers_use_verified_years_and_unique_name():
    from cpbl.api.staff_championships import fetch_for_coach, fetch_for_player

    out = fetch_for_player(_Cur({"0000000486": "張泰山"}), "0000000486")
    assert out and out["items"][0]["year"] == 2023
    # 同名兩人 → 不歸戶
    assert fetch_for_player(_Cur({"A": "張泰山", "B": "張泰山"}), "A") is None
    assert fetch_for_coach(_Cur({}), "王昊")["items"][0]["single_source"] is True
