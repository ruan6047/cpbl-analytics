"""官網選手頁「對戰各隊成績」+「分項成績」爬蟲。

實測契約（與投打對決同屬 ASP.NET MVC anti-forgery，token 走 header）：
- 對戰各隊：POST /team/getfighterscore（token 取自 person 頁 getFighterScore 區塊）
    data = {acnt, year, defendStation}；defendStation="" → 打擊 vs 各隊；
    defendStation="投手" → 投球 vs 各隊。**官網僅 A 例行賽、逐年、無生涯累計(9999)**。
- 分項成績：POST /team/getapartscore（token 取自 apart 頁 getApartScore 區塊）
    data = {acnt, kindCode, position, year}；position=01 打者 / 02 投手。
    一次回傳所有分項（主客場/左右投打/本土外籍/壘上/出局/局數/比分/月份/球場/打序）。
    支援 A/C/E + 生涯(9999)。

偶發回 Big5 的 500（anti-forgery/限流），故重試退避＋重建 session。冪等 UPSERT。
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from cpbl.db import conn
from cpbl.ingest.cpbl_fighting import BASE, _f, _i, _token_in

log = logging.getLogger("cpbl.detail")

PERSON_PAGE = f"{BASE}/team/person"
APART_PAGE = f"{BASE}/team/apart"
FIGHTER_EP = f"{BASE}/team/getfighterscore"
APART_EP = f"{BASE}/team/getapartscore"

DEFEND_PITCHER = "投手"  # defendStation 值為中文守位字串


class _Session:
    """單一選手 session：person 頁 + apart 頁各取一個 token，必要時重建。"""

    def __init__(self, acnt: str, delay: float):
        self.acnt = acnt
        self.delay = delay
        self.person_path = f"/team/person?acnt={acnt}"
        self.apart_path = f"/team/apart?Acnt={acnt}"
        self._open()

    def _open(self) -> None:
        from cpbl.ingest._browser import session
        s = session()
        self.fighter_token = _token_in(s.page_html(self.person_path), "getFighterScore: function")
        self.apart_token = _token_in(s.page_html(self.apart_path), "getApartScore: function")

    def close(self) -> None:
        pass  # 共用 browser session，不在此關閉

    def _post(self, page_path: str, api_path: str, token_attr: str, data: dict,
              key: str, retries: int = 4) -> list[dict]:
        from cpbl.ingest._browser import session
        for attempt in range(retries):
            time.sleep(self.delay)
            try:
                status, text = session().post(
                    page_path, api_path, data,
                    headers={"RequestVerificationToken": getattr(self, token_attr)},
                )
                if status == 200:
                    try:
                        return json.loads(json.loads(text).get(key) or "[]")
                    except (json.JSONDecodeError, ValueError):
                        pass
                log.warning("非 JSON (%s) acnt=%s %s attempt=%d", status, self.acnt, api_path, attempt + 1)
            except Exception as e:  # noqa: BLE001 — 退避重試
                log.warning("例外 acnt=%s: %s", self.acnt, e)
            time.sleep(2.0 * (attempt + 1))
            if attempt == retries - 2:
                self._open()
        raise RuntimeError(f"{api_path} 連續失敗 acnt={self.acnt}")

    def vs_team(self, year: int, defend: str) -> list[dict]:
        return self._post(self.person_path, "/team/getfighterscore", "fighter_token",
                          {"acnt": self.acnt, "year": str(year), "defendStation": defend}, "FighterScore")

    def apart(self, year: int, kind: str, position: str) -> list[dict]:
        return self._post(self.apart_path, "/team/getapartscore", "apart_token",
                          {"acnt": self.acnt, "kindCode": kind, "position": position, "year": str(year)},
                          "ApartScore")


# ---------- 欄位映射 ----------

def _bvt_rec(g: dict, year: int, kind: str, acnt: str) -> tuple:
    return (
        year, kind, acnt, g.get("FightTeamCode"), g.get("FightTeamName"), g.get("TeamNo"),
        _i(g.get("TotalGames")), _i(g.get("PlateAppearances")), _i(g.get("HitCnt")),
        _i(g.get("HittingCnt")), _i(g.get("RunBattedINCnt")), _i(g.get("ScoreCnt")),
        _i(g.get("OneBaseHitCnt")), _i(g.get("TwoBaseHitCnt")), _i(g.get("ThreeBaseHitCnt")),
        _i(g.get("HomeRunCnt")), _i(g.get("TotalBases")), _i(g.get("DoublePlayBatCnt")),
        _i(g.get("SacrificeHitCnt")), _i(g.get("SacrificeFlyCnt")), _i(g.get("BasesONBallsCnt")),
        _i(g.get("IntentionalBasesONBallsCnt")), _i(g.get("HitBYPitchCnt")), _i(g.get("StrikeOutCnt")),
        _i(g.get("StealBaseOKCnt")), _i(g.get("StealBaseFailCnt")), _f(g.get("SB")),
        _f(g.get("Avg")), _f(g.get("Obp")), _f(g.get("Slg")), _f(g.get("TA")), _f(g.get("Ops")),
    )


_BVT_COLS = ("year,kind_code,acnt,fight_team_code,fight_team_name,team_no,total_games,plate_appearances,"
             "at_bats,hits,rbi,runs,singles,doubles,triples,home_runs,total_bases,gidp,sac_hit,sac_fly,"
             "bb,ibb,hbp,so,sb_ok,sb_fail,sb_pct,avg,obp,slg,ta,ops")


def _pvt_rec(g: dict, year: int, kind: str, acnt: str) -> tuple:
    return (
        year, kind, acnt, g.get("FightTeamCode"), g.get("FightTeamName"), g.get("TeamNo"),
        _i(g.get("TotalGames")), _i(g.get("PitchStarting")), _i(g.get("PitchCloser")),
        _i(g.get("CompleteGames")), _i(g.get("ShoutOut")), _i(g.get("Wins")), _i(g.get("Loses")),
        _i(g.get("SaveOK")), _i(g.get("SaveFail")), _i(g.get("ReliefPointCnt")),
        _i(g.get("InningPitchedCnt")), _i(g.get("InningPitchedDiv3Cnt")), _f(g.get("Whip")), _f(g.get("Era")),
        _i(g.get("PlateAppearances")), _i(g.get("PitchCnt")), _i(g.get("HittingCnt")), _i(g.get("HomeRunCnt")),
        _i(g.get("BasesONBallsCnt")), _i(g.get("IntentionalBasesONBallsCnt")), _i(g.get("HitBYPitchCnt")),
        _i(g.get("StrikeOutCnt")), _i(g.get("WildPitchCnt")), _i(g.get("BalkCnt")),
        _i(g.get("RunCnt")), _i(g.get("EarnedRunCnt")),
    )


_PVT_COLS = ("year,kind_code,acnt,fight_team_code,fight_team_name,team_no,total_games,starts,closes,"
             "complete_games,shutouts,wins,loses,save_ok,save_fail,holds,inning_pitched_cnt,"
             "inning_pitched_div3,whip,era,plate_appearances,pitch_cnt,hits,home_runs,bb,ibb,hbp,so,"
             "wild_pitch,balk,runs,earned_runs")


def _bsplit_rec(g: dict, year: int, kind: str) -> tuple:
    return (
        year, kind, g.get("HitterAcnt"), g.get("ItemGroupCode"), _i(g.get("ItemIndex")),
        g.get("ItemName") or "", g.get("ItemNote"),
        _i(g.get("PlateAppearances")), _i(g.get("HitCnt")), _i(g.get("HittingCnt")),
        _i(g.get("RunBattedINCnt")), _i(g.get("OneBaseHitCnt")), _i(g.get("TwoBaseHitCnt")),
        _i(g.get("ThreeBaseHitCnt")), _i(g.get("HomeRunCnt")), _i(g.get("TotalBases")),
        _i(g.get("SacrificeHitCnt")), _i(g.get("SacrificeFlyCnt")), _i(g.get("BasesONBallsCnt")),
        _i(g.get("IntentionalBasesONBallsCnt")), _i(g.get("HitBYPitchCnt")), _i(g.get("StrikeOutCnt")),
        _i(g.get("GroundOuts")), _i(g.get("FlyOuts")), _f(g.get("Goao")),
        _f(g.get("Avg")), _f(g.get("Obp")), _f(g.get("Slg")), _f(g.get("Ops")),
    )


_BSPLIT_COLS = ("year,kind_code,acnt,item_group_code,item_index,item_name,item_note,plate_appearances,"
                "at_bats,hits,rbi,singles,doubles,triples,home_runs,total_bases,sac_hit,sac_fly,bb,ibb,"
                "hbp,so,ground_outs,fly_outs,goao,avg,obp,slg,ops")


def _psplit_rec(g: dict, year: int, kind: str) -> tuple:
    return (
        year, kind, g.get("PitcherAcnt"), g.get("ItemGroupCode"), _i(g.get("ItemIndex")),
        g.get("ItemName") or "", g.get("ItemNote"),
        _i(g.get("GameResultWCnt")), _i(g.get("GameResultLCnt")), _i(g.get("SPCnt")),
        _i(g.get("CompleteGameCnt")), _i(g.get("ShoutOutCnt")), _i(g.get("SaveOKCnt")),
        _i(g.get("InningPitchedCnt")), _i(g.get("InningPitchedDiv3Cnt")),
        _i(g.get("PlateAppearances")), _i(g.get("PitchCnt")), _i(g.get("StrikeCnt")), _i(g.get("BallCnt")),
        _i(g.get("HittingCnt")), _i(g.get("HomeRunCnt")), _i(g.get("SacrificeHitCnt")),
        _i(g.get("SacrificeFlyCnt")), _i(g.get("BasesONBallsCnt")), _i(g.get("IntentionalBasesONBallsCnt")),
        _i(g.get("HitBYPitchCnt")), _i(g.get("StrikeOutCnt")), _i(g.get("WildPitchCnt")),
        _i(g.get("BalkCnt")), _i(g.get("RunCnt")), _i(g.get("EarnedRunCnt")),
    )


_PSPLIT_COLS = ("year,kind_code,acnt,item_group_code,item_index,item_name,item_note,wins,loses,starts,"
                "complete_games,shutouts,save_ok,inning_pitched_cnt,inning_pitched_div3,plate_appearances,"
                "pitch_cnt,strikes,balls,hits,home_runs,sac_hit,sac_fly,bb,ibb,hbp,so,wild_pitch,balk,"
                "runs,earned_runs")


def _upsert(table: str, cols: str, n_pk: int, records: list[tuple]) -> int:
    records = [r for r in records if all(r[i] is not None for i in range(n_pk))]
    if not records:
        return 0
    col_list = [c.strip() for c in cols.split(",")]
    ph = "(" + ",".join(["%s"] * len(col_list)) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_list[n_pk:]) + ", updated_at=now()"
    pk = ", ".join(col_list[:n_pk])
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.{table} ({cols}) VALUES {ph} "
            f"ON CONFLICT ({pk}) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def _ids(table: str) -> list[str]:
    with conn() as c:
        return [r[0] for r in c.execute(
            f"SELECT DISTINCT player_id FROM cpbl.{table} ORDER BY player_id").fetchall()]


# 分項：本季只有 A 有資料；生涯(9999) A/C/E 皆有
APART_COMBOS = [(2026, "A"), (9999, "A"), (9999, "C"), (9999, "E")]
VS_TEAM_YEAR = 2026  # 對戰各隊官網僅本季 A、逐年


def scrape(delay: float = 1.2, apart_combos: list[tuple[int, str]] | None = None,
           groups: tuple[str, ...] = ("batters", "pitchers"),
           batter_ids: list[str] | None = None, pitcher_ids: list[str] | None = None) -> dict:
    """爬本季登錄打者(154)+投手(190) 的對戰各隊 + 分項。回傳各表寫入列數。

    `groups` 控制要跑哪些對象：("batters",) 只跑打者、("pitchers",) 只跑投手（續跑用）。
    `batter_ids`/`pitcher_ids` 不為 None 時，只跑指定選手（增量更新用）。
    """
    apart_combos = apart_combos or APART_COMBOS
    if batter_ids is not None:
        batters = batter_ids
    else:
        batters = _ids("batting_current") if "batters" in groups else []
    if pitcher_ids is not None:
        pitchers = pitcher_ids
    else:
        pitchers = _ids("pitching_current") if "pitchers" in groups else []
    out = {"bvt": 0, "pvt": 0, "bsplit": 0, "psplit": 0}
    log.info("選手細項：打者 %d / 投手 %d，delay=%.1fs，apart 組合=%s",
             len(batters), len(pitchers), delay, apart_combos)

    def run(acnt: str, idx: int, total: int, is_pitcher: bool) -> None:
        try:
            s = _Session(acnt, delay)
        except (httpx.HTTPError, RuntimeError) as e:
            log.error("[%s %d/%d] acnt=%s session 失敗，略過：%s",
                      "P" if is_pitcher else "B", idx, total, acnt, e)
            return
        try:
            if is_pitcher:
                rows = s.vs_team(VS_TEAM_YEAR, DEFEND_PITCHER)
                out["pvt"] += _upsert("pitching_vs_team", _PVT_COLS, 4,
                                      [_pvt_rec(g, VS_TEAM_YEAR, "A", acnt) for g in rows])
                for y, k in apart_combos:
                    rs = s.apart(y, k, "02")
                    out["psplit"] += _upsert("pitching_splits", _PSPLIT_COLS, 6,
                                             [_psplit_rec(g, y, k) for g in rs])
            else:
                rows = s.vs_team(VS_TEAM_YEAR, "")
                out["bvt"] += _upsert("batting_vs_team", _BVT_COLS, 4,
                                      [_bvt_rec(g, VS_TEAM_YEAR, "A", acnt) for g in rows])
                for y, k in apart_combos:
                    rs = s.apart(y, k, "01")
                    out["bsplit"] += _upsert("batting_splits", _BSPLIT_COLS, 6,
                                             [_bsplit_rec(g, y, k) for g in rs])
            log.info("[%s %d/%d] acnt=%s 完成（bvt=%d pvt=%d bs=%d ps=%d）",
                     "P" if is_pitcher else "B", idx, total, acnt,
                     out["bvt"], out["pvt"], out["bsplit"], out["psplit"])
        except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as e:
            log.error("[%s %d/%d] acnt=%s 抓取失敗，略過：%s",
                      "P" if is_pitcher else "B", idx, total, acnt, e)
        finally:
            s.close()

    for i, acnt in enumerate(batters, 1):
        run(acnt, i, len(batters), is_pitcher=False)
    for i, acnt in enumerate(pitchers, 1):
        run(acnt, i, len(pitchers), is_pitcher=True)
    return out
