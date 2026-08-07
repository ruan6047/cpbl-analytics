"""在本機 Redis 塞出首頁「今日賽事」的各種情境，供需求方人工審（UX-HOME-LIVE-STRIP1）。

**這不是測試**（檔名不以 `test_` 開頭，pytest 不會收集），也不碰資料庫、不碰生產：
它只把假的 canonical live snapshot 寫進本機開發用的 Redis，讓首頁能在沒有真實比賽
進行中的時段呈現賽前／賽中／賽後與兩階中斷。場次身分取自本機 `cpbl.games` 今天那一天，
所以隊名、球場與連結都是真的。

用法（先起一個獨立的本機 Redis，勿用主站那顆）::

    docker run -d --name cpbl-home-live-review -p 6399:6379 redis:7-alpine
    # .env 內設 REDIS_URL=redis://localhost:6399/0

    uv run python tests/manual/seed_home_live_snapshots.py pregame   # 賽前（未達 lineup）
    uv run python tests/manual/seed_home_live_snapshots.py lineup    # 單邊打線公布→切換
    uv run python tests/manual/seed_home_live_snapshots.py live      # 三場進行中
    uv run python tests/manual/seed_home_live_snapshots.py stale1    # 一階：60 秒未更新
    uv run python tests/manual/seed_home_live_snapshots.py stale2    # 二階：5 分鐘未更新
    uv run python tests/manual/seed_home_live_snapshots.py final     # 今晚已結束
    uv run python tests/manual/seed_home_live_snapshots.py mixed     # 一場進行中＋一場終場＋一場賽前
    uv run python tests/manual/seed_home_live_snapshots.py clear     # 清空＝worker 不可用

清空後首頁應**靜默**退回「最近比賽日＋下一批賽事」的純日期版面，freshness 條上出現
維護者訊號，訪客面不得看到任何錯誤或「即時」字樣。
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta

import redis

from cpbl.config import settings
from cpbl.db import conn

SCENARIOS = ("pregame", "lineup", "live", "stale1", "stale2", "final", "mixed", "clear")


def _today_games() -> list[tuple[int, str, int, str, str]]:
    """今天的一軍場次 → (year, kind_code, game_sno, away_name, home_name)。"""
    with conn() as connection:
        cur = connection.cursor()
        cur.execute(
            """
            SELECT year, kind_code, game_sno, away_team_name, home_team_name
            FROM cpbl.games
            WHERE game_date = %s AND kind_code = ANY(%s)
            ORDER BY game_sno
            """,
            (date.today(), ["A", "E", "C"]),
        )
        return list(cur.fetchall())


def _event(inning: int, outs: int, bases: tuple[bool, bool, bool],
           away: int, home: int) -> dict:
    first, second, third = bases or (False, False, False)
    return {
        "MainEventNo": f"{inning}0010001", "InningSeq": inning, "VisitingHomeType": "2",
        "OutCnt": outs,
        "FirstBase": "壘上跑者" if first else None,
        "SecondBase": "壘上跑者" if second else None,
        "ThirdBase": "壘上跑者" if third else None,
        "VisitingScore": away, "HomeScore": home,
    }


def _snapshot(year: int, kind: str, sno: int, *, phase: str, away: int, home: int,
              inning: int, outs: int, bases: tuple[bool, bool, bool], events: int,
              age_seconds: int, lineup: str, decisions: dict | None,
              starts_at: str) -> dict:
    fetched = datetime.now(UTC) - timedelta(seconds=age_seconds)
    side = lambda availability: {  # noqa: E731 — 就地建兩隊，不值得一個模組層函式
        "team": {"code": None, "name": None}, "score": 0, "hits": None, "errors": None,
        "record": {"w": None, "l": None, "t": None},
        "probable_pitcher": {"availability": "not_announced", "player_id": None,
                             "name": None, "first_observed_at": None},
        "lineup": {"availability": availability, "items": [], "first_observed_at": None},
        "inning_score": [], "hitters": [], "pitchers": [],
    }
    away_side, home_side = side(lineup), side("not_announced")
    away_side["score"], home_side["score"] = away, home
    return {
        "game_id": f"{year}-{kind}-{sno}", "game_sno": sno, "kind_code": kind,
        "starts_at": starts_at,
        "phase": phase,
        "raw_status": {"live": "START", "final": "FINISHED"}.get(phase, "SCHEDULED"),
        "inning": inning, "half": "2",
        "away": away_side, "home": home_side,
        "decisions": decisions or {"winning_pitcher": None, "losing_pitcher": None,
                                   "closer": None, "mvp": None},
        "venue": None, "umpires": [], "skip_trackman": False,
        "livelog": [_event(inning, outs, bases, away, home)] if events else [],
        "event_count": events, "tracking_count": 0,
        "tracking_availability": "pending" if events else "not_announced",
        "source": {"fetched_at": fetched.isoformat(), "version": f"seed-{age_seconds}"},
    }


def _plan(scenario: str, index: int) -> dict:
    """每個情境對第 index 場（0 起）要塞什麼。"""
    live_common = dict(phase="live", away=2 + index, home=3, inning=5 + index, outs=1,
                       bases=(True, False, index == 0), events=120 + index,
                       lineup="announced", decisions=None)
    if scenario == "pregame":
        return dict(phase="scheduled", away=0, home=0, inning=1, outs=0, bases=(),
                    events=0, age_seconds=30, lineup="not_announced", decisions=None)
    if scenario == "lineup":
        return dict(phase="lineup_announced" if index == 0 else "scheduled",
                    away=0, home=0, inning=1, outs=0, bases=(), events=0, age_seconds=30,
                    lineup="partial" if index == 0 else "not_announced", decisions=None)
    if scenario == "live":
        return {**live_common, "age_seconds": 8}
    if scenario == "stale1":
        return {**live_common, "age_seconds": 60}
    if scenario == "stale2":
        return {**live_common, "age_seconds": 300}
    if scenario == "final":
        return dict(phase="final", away=2 + index, home=6, inning=9, outs=3, bases=(),
                    events=280, age_seconds=600, lineup="announced",
                    decisions={"winning_pitcher": {"player_id": "P001", "name": "官方勝投"},
                               "losing_pitcher": {"player_id": "P002", "name": "官方敗投"},
                               "closer": None,
                               "mvp": {"player_id": "P003", "name": "官方 MVP",
                                       "yearly_count": 3}} if index == 0 else None)
    # mixed：第 0 場進行中、第 1 場終場、其餘賽前
    if index == 0:
        return {**live_common, "age_seconds": 8}
    if index == 1:
        return dict(phase="final", away=1, home=0, inning=9, outs=3, bases=(), events=270,
                    age_seconds=900, lineup="announced",
                    decisions={"winning_pitcher": None, "losing_pitcher": None,
                               "closer": None,
                               "mvp": {"player_id": "P003", "name": "官方 MVP",
                                       "yearly_count": 1}})
    return dict(phase="lineup_announced", away=0, home=0, inning=1, outs=0, bases=(),
                events=0, age_seconds=30, lineup="partial", decisions=None)


def main(scenario: str) -> int:
    if scenario not in SCENARIOS:
        print(f"用法：seed_home_live_snapshots.py <{'|'.join(SCENARIOS)}>")
        return 2
    if not settings.redis_url:
        print("需要 REDIS_URL（見本檔 docstring）")
        return 2
    if "localhost" not in settings.redis_url and "127.0.0.1" not in settings.redis_url:
        print(f"拒絕寫入非本機 Redis：{settings.redis_url}")
        return 2

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    prefix = settings.live_game_cache_prefix.rstrip(":")
    games = _today_games()
    if not games:
        print(f"本機 cpbl.games 今天（{date.today()}）沒有一軍場次，無法示範今日賽事區塊")
        return 1

    keys = [f"{prefix}:{year}:{kind}:{sno}" for year, kind, sno, *_ in games]
    if scenario == "clear":
        removed = client.delete(*keys, *[f"{key}:health" for key in keys])
        print(f"已清空 {removed} 個 key → 首頁應靜默退回純日期版面")
        return 0

    for index, (year, kind, sno, away, home) in enumerate(games):
        plan = _plan(scenario, index)
        snapshot = _snapshot(year, kind, sno,
                             starts_at=f"{date.today().isoformat()}T"
                                       f"{17 + index}:{5 if index else 35:02d}:00+08:00",
                             **plan)
        client.set(f"{prefix}:{year}:{kind}:{sno}",
                   json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), ex=7200)
        client.delete(f"{prefix}:{year}:{kind}:{sno}:health")
        print(f"{year}-{kind}-{sno} {away} vs {home} → phase={plan['phase']} "
              f"age={plan['age_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
