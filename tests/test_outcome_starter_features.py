"""ML-OUTCOME-LEAK1：先發投手特徵的「賽前可得」合約測試。

舊版以 `(starter_id, year)` 讀同季彙總 → 歷史回測在賽前看見該季之後的表現。
本檔以離線 fake cursor 驗證新版的 running-state 合約（風格比照
`tests/test_winprob_strength.py`）：該場自身與該季未來場次都不得進入特徵。
"""

from __future__ import annotations

from datetime import date

import pytest

from cpbl.features import outcome as F

# ── 最小 fake DB（依 SQL 內容分派）─────────────────────────────────────────
GAMES_COLS = ("year", "kind_code", "game_season_code", "game_sno", "game_date",
              "home_team_code", "home_team_name", "away_team_code", "away_team_name",
              "home_score", "away_score", "home_starter_id", "away_starter_id")


class _FakeCursor:
    def __init__(self, store: dict):
        self._s, self._rows = store, []

    def execute(self, sql, params=None):
        if "pitcher_acnt, earned_runs" in sql:
            self._rows = self._s["pglog"]
        elif "player_id, year, er, h, bb, so, ip" in sql:
            self._rows = self._s["pseasons"]
        elif "FROM cpbl.batting_seasons" in sql or "FROM cpbl.pitching_seasons GROUP BY" in sql:
            self._rows = []
        elif "FROM cpbl.batting_gamelog" in sql or "sum(wild_pitch)" in sql:
            self._rows = []
        elif "FROM cpbl.games" in sql:
            # `_prior_winpct` 與主迴圈都查 games；用 SELECT 首欄組合判別。
            self._rows = ([(g[0], g[5], g[7], g[9], g[10]) for g in self._s["games"]]
                          if "SELECT year, home_team_code" in sql else self._s["games"])
        else:  # pragma: no cover - 測試若打到未預期查詢應直接失敗
            raise AssertionError(f"未預期的查詢：{sql[:70]}")

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, store: dict):
        self._s = store

    def cursor(self):
        return _FakeCursor(self._s)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _use_fake_db(monkeypatch, *, games, pglog=(), pseasons=()):
    store = {"games": list(games), "pglog": list(pglog), "pseasons": list(pseasons)}
    monkeypatch.setattr(F, "conn", lambda: _FakeConn(store))


def _gm(year, sno, day, hsp, asp, hs=5, as_=3):
    return (year, "A", "01", sno, date(year, 4, day), "AAA", "主隊", "BBB", "客隊",
            hs, as_, hsp, asp)


def _pg(year, sno, pid, er, h, bb, so, ip):
    return (year, sno, pid, er, h, bb, so, ip, 0)


def _feat(rows, sno, key):
    return next(r[key] for r in rows if r["game_sno"] == sno)


# ── 合約 1：該場自身不得進入自己的賽前特徵 ────────────────────────────────
def test_starter_running_state_excludes_the_game_itself_and_future_games(monkeypatch):
    """主隊先發第 1 場被打爆、第 2 場完美。

    洩漏版（同季彙總）兩場會看到同一個「整季」ERA；賽前 as-of 版必須是：
    第 1 場完全沒有本季分母（＝退 prior/聯盟率、與客隊先發同值 → diff 為 0），
    第 2 場才反映第 1 場的慘況（主隊 ERA 較高 → diff > 0）。
    """
    games = [_gm(2019, 1, 1, "P1", "P2"), _gm(2019, 2, 8, "P1", "P2")]
    pglog = [
        _pg(2019, 1, "P1", er=9, h=12, bb=4, so=1, ip=5),    # 主隊先發第 1 場被打爆
        _pg(2019, 1, "P2", er=1, h=3, bb=1, so=8, ip=7),
        _pg(2019, 2, "P1", er=0, h=2, bb=0, so=11, ip=9),    # 第 2 場完美（未來資訊）
        _pg(2019, 2, "P2", er=1, h=4, bb=2, so=6, ip=6),
    ]
    _use_fake_db(monkeypatch, games=games, pglog=pglog)
    rows = F.build_game_features()

    # 第 1 場：雙方皆無本季分母 → 同樣退回（相同的）聯盟率 ⇒ 三欄皆恰為 0。
    for key in ("starter_era_diff", "starter_whip_diff", "starter_k9_diff"):
        assert _feat(rows, 1, key) == pytest.approx(0.0)

    # 第 2 場：只含第 1 場的量。逐項用同一支收縮式獨立重算，確認未混入第 2 場。
    lg = (F._LG_DEFAULT_ER_IP, F._LG_DEFAULT_WHIP, F._LG_DEFAULT_SO_IP)
    home = F._starter_rates(F._PitchCounts(er=9, h=12, bb=4, so=1, ip=5), None, lg)
    away = F._starter_rates(F._PitchCounts(er=1, h=3, bb=1, so=8, ip=7), None, lg)
    assert _feat(rows, 2, "starter_era_diff") == pytest.approx(home[0] - away[0])
    assert _feat(rows, 2, "starter_whip_diff") == pytest.approx(home[1] - away[1])
    assert _feat(rows, 2, "starter_k9_diff") == pytest.approx(home[2] - away[2])
    # 被打爆的主隊先發 ERA 必須高於客隊（方向性 sanity）。
    assert _feat(rows, 2, "starter_era_diff") > 0


# ── 合約 2：跨季歸零，前一季只能以 prior 身分進入 ─────────────────────────
def test_season_boundary_resets_running_state_and_prior_is_previous_year_only(monkeypatch):
    games = [_gm(2019, 1, 1, "P1", "P2"), _gm(2020, 1, 1, "P1", "P2")]
    pglog = [
        _pg(2019, 1, "P1", er=9, h=12, bb=4, so=1, ip=5),
        _pg(2019, 1, "P2", er=1, h=3, bb=1, so=8, ip=7),
        _pg(2020, 1, "P1", er=0, h=2, bb=0, so=11, ip=9),
        _pg(2020, 1, "P2", er=5, h=9, bb=3, so=2, ip=4),
    ]
    _use_fake_db(monkeypatch, games=games, pglog=pglog)
    rows = F.build_game_features()

    # 2020 開季首戰：當季分母歸零，值完全由「2019 總量 prior」決定。
    lg2019 = F._league_pitch_rates({(2019, "P1"): F._PitchCounts(er=9, h=12, bb=4, so=1, ip=5),
                                    (2019, "P2"): F._PitchCounts(er=1, h=3, bb=1, so=8, ip=7)})[2019]
    home = F._starter_rates(F._PitchCounts(),
                            F._PitchCounts(er=9, h=12, bb=4, so=1, ip=5), lg2019)
    away = F._starter_rates(F._PitchCounts(),
                            F._PitchCounts(er=1, h=3, bb=1, so=8, ip=7), lg2019)
    assert _feat(rows, 1, "starter_era_diff") == pytest.approx(0.0)   # 2019 首戰仍為 0
    got = next(r for r in rows if r["year"] == 2020)
    assert got["starter_era_diff"] == pytest.approx(home[0] - away[0])
    assert got["starter_era_diff"] > 0            # 2019 較差的 P1 在 2020 開季仍被判較弱


# ── 合約 3：收縮式的純函式行為 ────────────────────────────────────────────
def test_shrink_falls_back_to_prior_then_league_and_yields_to_current_season():
    lg = (4.5 / 9.0, 1.5, 4.5 / 9.0)      # ERA 4.5 / WHIP 1.5 / K9 4.5

    # 無當季、無前一季 → 恰為前一季聯盟率
    era, whip, k9 = F._starter_rates(F._PitchCounts(), None, lg)
    assert (era, whip, k9) == pytest.approx((4.5, 1.5, 4.5))

    # 無當季、有前一季（分母遠大於 kappa）→ 大幅偏向前一季自身率、仍留一點聯盟收縮
    prior = F._PitchCounts(er=30, h=200, bb=40, so=200, ip=300)
    era, whip, k9 = F._starter_rates(F._PitchCounts(), prior, lg)
    assert era == pytest.approx((30 + 30 * lg[0]) * 9 / 330)      # 兩層收縮的封閉解
    assert 30 * 9 / 300 < era < 4.5                                # 介於自身率與聯盟率之間
    assert 240 / 300 < whip < 1.5

    # 當季分母增加 → prior 讓位（單調趨近當季自身率）
    seq = [F._starter_rates(F._PitchCounts(er=0, h=1, bb=0, so=12, ip=ip), None, lg)[0]
           for ip in (0, 10, 60, 600)]
    assert seq == sorted(seq, reverse=True)        # 當季 0 責失 → ERA 單調下降
    assert seq[-1] == pytest.approx(0.0, abs=0.25)


def test_ip_notation_converts_thirds_not_decimals():
    """`pitching_seasons.ip` 是棒球記法：140.2 = 140⅔ 局，不是 140.2 局。"""
    assert F._ip_decimal(140.0) == pytest.approx(140.0)
    assert F._ip_decimal(140.1) == pytest.approx(140 + 1 / 3)
    assert F._ip_decimal(140.2) == pytest.approx(140 + 2 / 3)
    assert F._ip_decimal(None) == 0.0
