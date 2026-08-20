"""球隊頁「近日焦點」素材 2：近期球員熱區（UX-TEAM-HOTZONE1；唯讀）。

取代 UX-TEAM-FOCUS2 的 OPS 熱區。理由不是「跟官方一致」而是指標選擇：12 個打席的
OPS 幾乎是純噪音，一支內野安打就能翻掉排名。改採**過程型**指標（擊球初速／揮空率），
這類指標在小樣本下仍有訊號，這正是 Statcast 系指標存在的理由（見 docs/tasks/UX-TEAM-HOTZONE1.md）。

## 資料邊界（紅線 5）

一律取自 `cpbl.pitch_tracking`（官方逐球 TrackMan），**目前僅 2026 年起有資料**。
這是資料邊界不是「近期」的語意限制——不同球季不可比較，也不應被誤讀為可回溯的
生涯指標。前端須明示資料來源與年限（不得只靠本模組的退化語意隱性帶過）。

## 口徑（2026-07-28 需求方定案，記於 docs/tasks/UX-TEAM-HOTZONE1.md，不得自行更動）

- **窗口＝近 14 個日曆天**（非沿用 UX-TEAM-FOCUS2 的 7 天）：以該隊「本季最後一場
  完賽日」回推，完賽判定沿用 completed-game-judgment 慣例（score>0 且
  game_date<=CURRENT_DATE）。7 天窗口下，擊球事件（BIP）比打席稀疏得多，實測
  2026-07-28 抓取時有球隊整個 7 天窗口剛好客場打大巨蛋系列（無 TrackMan 設備）
  → 整隊 0 筆擊球事件，14 天窗口才能重新納入足量樣本（同時仍可能出現同樣情況，
  故仍須有覆蓋揭露機制，見下方 `_coverage`，不是靠拉長窗口就能保證解決）。
- **打者「擊球品質」門檻**＝窗口內擊球事件（BIP，`pitch_call='InPlay'` 且
  `hit_exit_speed` 有值）>= `MIN_BIP`；排序＝平均擊球初速（Avg Exit Velocity）
  由高到低，取前 `TOP_N`。只計「InPlay」不計界外球——界外球雖然也有時錄到
  擊球初速，但那是「打者想避開的球」不是打者選擇擊出的球，混入平均會失真
  （Statcast 慣例亦僅計 in-play 的 batted-ball events）。
- **投手「投球宰制力」門檻**＝窗口內投球數 >= `MIN_PITCHES`；排序＝揮空率
  （SwStr / 出棒數，非除以總球數；出棒集合沿用 `cpbl.api.routers.tracking._SWING`
  同一口徑：InPlay/FoulBallNotFieldable/FoulBallFieldable/StrikeSwinging）
  由高到低，取前 `TOP_N`。次要顯示「被擊球初速 Avg」（該投手窗口內被擊出球的
  平均初速，越低代表越能限制硬擊球，與打者卡的擊球初速互為鏡像指標，唯方向相反）。
- **不沿用官方名稱**：官方 stats.cpbl 首頁「近期表現良好選手」用「出色擊球」
  （排序鍵）＋擊球初速 Avg/Max/擊球事件數（打者）、對戰加權上壘率/揮空%/三振%/
  保送%/打席（投手）。「出色擊球」的 EV/LA 判準未公開查無來源，故不沿用該名稱；
  wOBA 對戰需要完整 PA 結果模型（本卡唯讀、M 級規模不做），三振%/保送%需 PA
  分母而非逐球分母，同樣不做。本模組只用「擊球初速」「揮空率」這類欄位本身
  即為定義、可逐球對帳重現的指標，並用自訂名稱「擊球品質」「投球宰制力」呈現。
- **樣本數同列顯示**（紅線 4）：打者卡標示擊球事件數，投手卡標示投球數＋
  被擊球事件數。
- **覆蓋缺口揭露**（紅線 1）：`coverage` 回傳窗口內該隊完賽場數與其中「整場零
  逐球紀錄」場數（球場端 TrackMan 設備覆蓋不全，如大巨蛋/嘉義市/台東等，見
  `cpbl-check-coverage`）。全數未覆蓋時 `batters.items`/`pitchers.items` 必為空，
  前端須用「窗口內無追蹤資料」文案，不得與「有資料但無人達門檻」共用同一句話。

`available=False`＝本季尚無完賽（球季未開打／已結束前的空窗）。`available=True`
時一定有 `window` 與 `coverage`；`items` 是否為空要搭配 `coverage` 判斷退化原因
（見上）。
"""

from __future__ import annotations

from datetime import date, timedelta

from cpbl.completion import completed_games_sql_with_evidence
from cpbl.db import conn

WINDOW_DAYS = 14
MIN_BIP = 5
MIN_PITCHES = 20
TOP_N = 3

# 出棒集合：與 cpbl.api.routers.tracking._SWING 同一口徑（單一事實來源用意相同，
# 但避免跨 router/模組互相 import 造成耦合，此處保留字面量並在文件互相標注）。
_SWING_CALLS = ("InPlay", "FoulBallNotFieldable", "FoulBallFieldable", "StrikeSwinging")

_BAT_TEAM_EXPR = "CASE bg.visiting_home_type WHEN '2' THEN g.home_team_code ELSE g.away_team_code END"
_PIT_TEAM_EXPR = "CASE pg.visiting_home_type WHEN '2' THEN g.home_team_code ELSE g.away_team_code END"

# 完成場判準（證據感知）的 `g` 別名版，供 `_coverage` 的子查詢使用。
# 日界吃 helper 的台北預設，與同檔 `_last_completed_game_date` 一致——原本兩者不同
# 只因這裡明示傳了 UTC 以等需求方裁決；裁決已於 2026-08-21 下達
# （業務日期一律台北，DATA-TZ-BOUNDARY-SUCCESSION1），落差就此消失。
_DONE_G = completed_games_sql_with_evidence("g")


def _last_completed_game_date(cur, code: str, season: int) -> date | None:
    cur.execute(
        "SELECT max(game_date) FROM cpbl.games "
        f"WHERE year=%s AND kind_code='A' AND {completed_games_sql_with_evidence('games')} "
        "AND (home_team_code=%s OR away_team_code=%s)",
        (season, code, code),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _coverage(cur, code: str, season: int, start: date, end: date) -> dict:
    """窗口內該隊完賽場數 vs. 其中整場零逐球紀錄場數（球場設備覆蓋缺口）。"""
    cur.execute(
        f"""
        SELECT count(*) AS games_in_window,
               count(*) FILTER (WHERE tracked = 0) AS untracked_games
        FROM (
            SELECT g.game_sno,
                   (SELECT count(*) FROM cpbl.pitch_tracking pt
                      WHERE pt.year=g.year AND pt.kind_code=g.kind_code AND pt.game_sno=g.game_sno) AS tracked
            FROM cpbl.games g
            WHERE g.year=%s AND g.kind_code='A' AND {_DONE_G}
              AND g.game_date BETWEEN %s AND %s
              AND (g.home_team_code=%s OR g.away_team_code=%s)
        ) q
        """,
        (season, start, end, code, code),
    )
    games_in_window, untracked_games = cur.fetchone()
    return {"games_in_window": int(games_in_window or 0), "untracked_games": int(untracked_games or 0)}


def _hot_batters(cur, code: str, season: int, start: date, end: date) -> list[dict]:
    cur.execute(
        f"""
        SELECT bg.hitter_acnt,
               (array_agg(bg.hitter_name ORDER BY g.game_date DESC))[1] AS name,
               count(*) AS bip,
               round(avg(pt.hit_exit_speed)::numeric, 1) AS avg_ev,
               round(max(pt.hit_exit_speed)::numeric, 1) AS max_ev
        FROM cpbl.pitch_tracking pt
        JOIN cpbl.games g ON g.year=pt.year AND g.kind_code=pt.kind_code AND g.game_sno=pt.game_sno
        JOIN cpbl.batting_gamelog bg ON bg.year=pt.year AND bg.kind_code=pt.kind_code
             AND bg.game_sno=pt.game_sno AND bg.hitter_acnt=pt.hitter_acnt
        WHERE pt.year=%s AND pt.kind_code='A' AND pt.pitch_call='InPlay' AND pt.hit_exit_speed IS NOT NULL
          AND g.game_date BETWEEN %s AND %s
          AND {_BAT_TEAM_EXPR}=%s
        GROUP BY bg.hitter_acnt
        HAVING count(*) >= %s
        ORDER BY avg_ev DESC
        LIMIT %s
        """,
        (season, start, end, code, MIN_BIP, TOP_N),
    )
    return [
        {"player_id": acnt, "name": name, "bip": int(bip), "avg_ev": float(avg_ev), "max_ev": float(max_ev)}
        for acnt, name, bip, avg_ev, max_ev in cur.fetchall()
    ]


def _hot_pitchers(cur, code: str, season: int, start: date, end: date) -> list[dict]:
    cur.execute(
        f"""
        SELECT pg.pitcher_acnt,
               (array_agg(pg.pitcher_name ORDER BY g.game_date DESC))[1] AS name,
               count(*) AS pitches,
               count(*) FILTER (WHERE pt.pitch_call IN {_SWING_CALLS}) AS swings,
               count(*) FILTER (WHERE pt.pitch_call = 'StrikeSwinging') AS whiffs,
               count(*) FILTER (WHERE pt.pitch_call='InPlay' AND pt.hit_exit_speed IS NOT NULL) AS bip_against,
               round(avg(pt.hit_exit_speed) FILTER (WHERE pt.pitch_call='InPlay')::numeric, 1) AS avg_ev_against
        FROM cpbl.pitch_tracking pt
        JOIN cpbl.games g ON g.year=pt.year AND g.kind_code=pt.kind_code AND g.game_sno=pt.game_sno
        JOIN cpbl.pitching_gamelog pg ON pg.year=pt.year AND pg.kind_code=pt.kind_code
             AND pg.game_sno=pt.game_sno AND pg.pitcher_acnt=pt.pitcher_acnt
        WHERE pt.year=%s AND pt.kind_code='A'
          AND g.game_date BETWEEN %s AND %s
          AND {_PIT_TEAM_EXPR}=%s
        GROUP BY pg.pitcher_acnt
        HAVING count(*) >= %s AND count(*) FILTER (WHERE pt.pitch_call IN {_SWING_CALLS}) > 0
        ORDER BY (count(*) FILTER (WHERE pt.pitch_call = 'StrikeSwinging')::float
                  / count(*) FILTER (WHERE pt.pitch_call IN {_SWING_CALLS})) DESC
        LIMIT %s
        """,
        (season, start, end, code, MIN_PITCHES, TOP_N),
    )
    items = []
    for acnt, name, pitches, swings, whiffs, bip_against, avg_ev_against in cur.fetchall():
        items.append({
            "player_id": acnt, "name": name, "pitches": int(pitches), "swings": int(swings),
            "whiffs": int(whiffs), "whiff_pct": round(whiffs / swings * 100, 1),
            "bip_against": int(bip_against),
            "avg_ev_against": float(avg_ev_against) if avg_ev_against is not None else None,
        })
    return items


def hot_zone(code: str, season: int) -> dict:
    """球隊頁「近期球員熱區」：擊球品質（打者）＋投球宰制力（投手），近 14 日窗口。"""
    with conn() as c:
        cur = c.cursor()
        last_date = _last_completed_game_date(cur, code, season)
        if last_date is None:
            return {
                "season": season, "window_days": WINDOW_DAYS, "available": False,
                "window": None, "coverage": None,
                "batters": {"min_bip": MIN_BIP, "items": []},
                "pitchers": {"min_pitches": MIN_PITCHES, "items": []},
            }

        start = last_date - timedelta(days=WINDOW_DAYS - 1)
        coverage = _coverage(cur, code, season, start, last_date)
        batters = _hot_batters(cur, code, season, start, last_date)
        pitchers = _hot_pitchers(cur, code, season, start, last_date)

        return {
            "season": season,
            "window_days": WINDOW_DAYS,
            "available": True,
            "window": {"start": start.isoformat(), "end": last_date.isoformat()},
            "coverage": coverage,
            "batters": {"min_bip": MIN_BIP, "items": batters},
            "pitchers": {"min_pitches": MIN_PITCHES, "items": pitchers},
        }
