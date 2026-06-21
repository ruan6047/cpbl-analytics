"""特殊戰績：從逐場 games + 逐局 game_scoreboard 即時計算（隊級）。

定義（由使用者定調確認）：
- 場地：人工草皮（天母/大巨蛋）/ 天然草皮 / 室內（僅大巨蛋）。
- 得分先馳 / 先失分：我方 / 對方全場最先得分的場次戰績。
- 一分差：最終分差＝1；大勝大敗：分差 ≥5。
- 完封：完封勝（對手 0 分）/ 被完封（我方 0 分），計次。
- 逆轉：逆轉勝（曾落後仍勝）/ 被逆轉（曾領先卻敗），計次。
- 戰況激烈：領先後被追平、最終才分勝負。
- 順風 / 逆風：比賽中曾領先 / 落後 ≥3 分。
- 大局：我方單局曾得 ≥4 分。
- 延長賽：打超過 9 局。
- 救援守成：第 8 局結束領先 1–3 分（救援情境），最終守成獲勝＝成功、否則失敗。
  逐場資料無官方 save 旗標，故以逐局重建救援情境（全覆蓋、定義透明）。
- 失誤場：我方該場有失誤（≥1）。
- 平日 / 假日：週六日＝假日，其餘平日。
- vs 左投 / vs 右投：對手先發投手慣用手（players.throws；未知不計）。
- 系列賽：連戰（同對手、間隔 ≤2 天）拿多數場＝系列勝；3-0＝橫掃、0-3＝被橫掃。
- 月份趨勢：各月 W-L。

皆用逐場 + 逐局（覆蓋完整），不依賴有設備限制的逐球。和局（hs==as）不計入 W-L。
"""

from __future__ import annotations

from cpbl.db import conn
from cpbl.venues import is_artificial, is_indoor

LEAD_MARGIN = 3       # 順風/逆風門檻
BLOWOUT_MARGIN = 5    # 大勝/大敗門檻
BIG_INNING = 4        # 大局門檻（單局得分）

# 各情境鍵：W-L 或 [正向次數, 反向次數] 配對
_PAIR_KEYS = (
    "natural", "artificial", "indoor",
    "scored_first", "scored_first_against",
    "one_run", "blowout", "shutout", "comeback",
    "intense", "tailwind", "headwind", "big_inning",
    "extra", "save", "errorful",
    "weekday", "weekend", "vs_lhp", "vs_rhp", "series",
)


def _trajectory(rows: list[tuple[int, int, int]]) -> dict:
    """rows: 已排序 (inning_seq, vht, score)；vht 1=客 2=主。回該場逐局軌跡標記。"""
    away = home = 0
    first_scorer: str | None = None
    ever_nonzero_lead = False
    tied_after_lead = False
    max_away_lead = 0
    max_home_lead = 0
    home_ever_led = False
    away_ever_led = False
    home_big = away_big = False
    max_inning = 0
    lead_after8: int | None = None       # 第 8 局打完時 home-away
    for inn, vht, sc in rows:
        max_inning = max(max_inning, inn)
        if vht == 1:
            away += sc
            away_big = away_big or sc >= BIG_INNING
        else:
            home += sc
            home_big = home_big or sc >= BIG_INNING
        if first_scorer is None and (away > 0 or home > 0):
            first_scorer = "away" if away > home else "home" if home > away else None
        diff = away - home
        max_away_lead = max(max_away_lead, diff)
        max_home_lead = max(max_home_lead, -diff)
        home_ever_led = home_ever_led or home > away
        away_ever_led = away_ever_led or away > home
        if diff != 0:
            ever_nonzero_lead = True
        elif ever_nonzero_lead and (away > 0 or home > 0):
            tied_after_lead = True
        if inn == 8:
            lead_after8 = home - away
    return {
        "first_scorer": first_scorer,
        "intense": tied_after_lead,
        "away_max_lead": max_away_lead,
        "home_max_lead": max_home_lead,
        "home_ever_led": home_ever_led,
        "away_ever_led": away_ever_led,
        "home_big": home_big,
        "away_big": away_big,
        "max_inning": max_inning,
        "lead_after8": lead_after8,
    }


def _blank() -> dict:
    out: dict = {k: [0, 0] for k in _PAIR_KEYS}
    out["sweeps"] = 0
    out["swept"] = 0
    out["months"] = {}
    return out


def team_situational(season: int, kind_code: str = "A") -> dict[str, dict]:
    """回 {team_code: {各情境: [..]}}（含系列/橫掃/月份）。"""
    with conn() as c:
        games = c.execute(
            "SELECT g.game_sno, g.game_date, g.venue, g.home_team_code, g.away_team_code, "
            "       g.home_score, g.away_score, ph.throws AS home_sp, pa.throws AS away_sp "
            "FROM cpbl.games g "
            "LEFT JOIN cpbl.players ph ON ph.id = g.home_starter_id "
            "LEFT JOIN cpbl.players pa ON pa.id = g.away_starter_id "
            "WHERE g.year=%s AND g.kind_code=%s AND g.home_score+g.away_score>0",
            (season, kind_code),
        ).fetchall()
        sb = c.execute(
            "SELECT game_sno, visiting_home_type, inning_seq, COALESCE(score_cnt,0), COALESCE(error_cnt,0) "
            "FROM cpbl.game_scoreboard WHERE year=%s AND kind_code=%s",
            (season, kind_code),
        ).fetchall()

    # 逐場彙整逐局事件 + 雙方失誤
    by_game: dict[int, list[tuple]] = {}
    errs: dict[int, list[int]] = {}   # game_sno -> [away_err, home_err]
    for sno, vht, inn, sc, err in sb:
        vht = int(vht)
        by_game.setdefault(sno, []).append((int(inn), vht, int(sc)))
        e = errs.setdefault(sno, [0, 0])
        e[0 if vht == 1 else 1] += int(err)

    out: dict[str, dict] = {}

    def rec(team: str, cat: str, idx: int) -> None:
        out.setdefault(team, _blank())[cat][idx] += 1

    def wl(team: str, cat: str, win: bool) -> None:
        rec(team, cat, 0 if win else 1)

    for sno, gdate, venue, hc, ac, hs, as_, home_sp, away_sp in games:
        if hs == as_:
            continue   # 和局不計入 W-L
        home_win = hs > as_
        margin = abs(hs - as_)
        rows = sorted(by_game.get(sno, []), key=lambda r: (r[0], r[1]))
        f = _trajectory(rows)
        a_err, h_err = errs.get(sno, [0, 0])

        # 場地
        wl(hc, "artificial" if is_artificial(venue) else "natural", home_win)
        wl(ac, "artificial" if is_artificial(venue) else "natural", not home_win)
        if is_indoor(venue):
            wl(hc, "indoor", home_win)
            wl(ac, "indoor", not home_win)

        # 得分先馳 / 先失分
        if f["first_scorer"] == "home":
            wl(hc, "scored_first", home_win)
            wl(ac, "scored_first_against", not home_win)
        elif f["first_scorer"] == "away":
            wl(ac, "scored_first", not home_win)
            wl(hc, "scored_first_against", home_win)

        # 一分差 / 大勝大敗
        if margin == 1:
            wl(hc, "one_run", home_win)
            wl(ac, "one_run", not home_win)
        if margin >= BLOWOUT_MARGIN:
            wl(hc, "blowout", home_win)
            wl(ac, "blowout", not home_win)

        # 完封（勝-被）
        if as_ == 0:
            rec(hc, "shutout", 0)   # 主隊完封勝
            rec(ac, "shutout", 1)   # 客隊被完封
        if hs == 0:
            rec(ac, "shutout", 0)
            rec(hc, "shutout", 1)

        # 逆轉（勝-被）：曾落後仍勝 / 曾領先卻敗
        if home_win and f["away_ever_led"]:
            rec(hc, "comeback", 0)
        if (not home_win) and f["home_ever_led"]:
            rec(hc, "comeback", 1)
        if (not home_win) and f["home_ever_led"]:
            rec(ac, "comeback", 0)
        if home_win and f["away_ever_led"]:
            rec(ac, "comeback", 1)

        # 戰況激烈（雙方同記）
        if f["intense"]:
            wl(hc, "intense", home_win)
            wl(ac, "intense", not home_win)

        # 順風（曾領先≥3）/ 逆風（曾落後≥3）
        if f["home_max_lead"] >= LEAD_MARGIN:
            wl(hc, "tailwind", home_win)
        if f["away_max_lead"] >= LEAD_MARGIN:
            wl(ac, "tailwind", not home_win)
        if f["away_max_lead"] >= LEAD_MARGIN:   # 主隊曾落後＝客隊曾領先幅度
            wl(hc, "headwind", home_win)
        if f["home_max_lead"] >= LEAD_MARGIN:
            wl(ac, "headwind", not home_win)

        # 大局
        if f["home_big"]:
            wl(hc, "big_inning", home_win)
        if f["away_big"]:
            wl(ac, "big_inning", not home_win)

        # 延長賽
        if f["max_inning"] > 9:
            wl(hc, "extra", home_win)
            wl(ac, "extra", not home_win)

        # 救援守成：第8局結束領先 1–3 分 → 救援情境
        la = f["lead_after8"]
        if la is not None:
            if 1 <= la <= LEAD_MARGIN:       # 主隊領先 1–3
                rec(hc, "save", 0 if home_win else 1)
            elif 1 <= -la <= LEAD_MARGIN:    # 客隊領先 1–3
                rec(ac, "save", 0 if not home_win else 1)

        # 失誤場（我方有失誤）
        if h_err > 0:
            wl(hc, "errorful", home_win)
        if a_err > 0:
            wl(ac, "errorful", not home_win)

        # 平日 / 假日
        if gdate is not None:
            cat = "weekend" if gdate.weekday() >= 5 else "weekday"
            wl(hc, cat, home_win)
            wl(ac, cat, not home_win)
            m = gdate.month
            for tc, win in ((hc, home_win), (ac, not home_win)):
                mo = out.setdefault(tc, _blank())["months"].setdefault(m, [0, 0])
                mo[0 if win else 1] += 1

        # vs 左/右投先發（對手先發慣用手）
        if away_sp in ("左投", "右投"):
            wl(hc, "vs_lhp" if away_sp == "左投" else "vs_rhp", home_win)
        if home_sp in ("左投", "右投"):
            wl(ac, "vs_lhp" if home_sp == "左投" else "vs_rhp", not home_win)

    _add_series(season, kind_code, out)
    return out


def _add_series(season: int, kind_code: str, out: dict[str, dict]) -> None:
    """系列賽戰績：同 (主隊,客隊) 連戰（相鄰日期間隔 ≤2 天）分組，拿多數場＝系列勝。"""
    with conn() as c:
        games = c.execute(
            "SELECT game_date, home_team_code, away_team_code, home_score, away_score "
            "FROM cpbl.games WHERE year=%s AND kind_code=%s AND home_score+away_score>0 "
            "ORDER BY home_team_code, away_team_code, game_date, game_sno",
            (season, kind_code),
        ).fetchall()

    series: list[tuple] = []
    cur: list[tuple] = []
    prev_key = None
    prev_date = None
    for gd, hc, ac, hs, as_ in games:
        key = (hc, ac)
        gap = (gd - prev_date).days if (prev_date and key == prev_key) else 99
        if key != prev_key or gap > 2:
            if cur:
                series.append((prev_key, cur))
            cur = []
        cur.append((hs, as_))
        prev_key, prev_date = key, gd
    if cur:
        series.append((prev_key, cur))

    for (hc, ac), gms in series:
        hw = sum(1 for hs, as_ in gms if hs > as_)
        aw = sum(1 for hs, as_ in gms if as_ > hs)
        if hw > aw:
            out.setdefault(hc, _blank())["series"][0] += 1
            out.setdefault(ac, _blank())["series"][1] += 1
        elif aw > hw:
            out.setdefault(ac, _blank())["series"][0] += 1
            out.setdefault(hc, _blank())["series"][1] += 1
        if len(gms) == 3 and hw == 3:
            out.setdefault(hc, _blank())["sweeps"] += 1
            out.setdefault(ac, _blank())["swept"] += 1
        elif len(gms) == 3 and aw == 3:
            out.setdefault(ac, _blank())["sweeps"] += 1
            out.setdefault(hc, _blank())["swept"] += 1
