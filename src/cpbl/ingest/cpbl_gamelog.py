"""每場賽況爬蟲：box/getlive 的 ScoreboardJson（逐局比分）+ LiveLogJson（逐打席事件）。

一個 token 可重用於多場 getlive。冪等 UPSERT；偶發非 JSON 回應時重取 token。
"""

from __future__ import annotations

import json
import logging
import re
import time

import psycopg

from cpbl.db import conn
from cpbl.ingest.box_revisions import record_box_pitching_revisions
from cpbl.ingest.cpbl_site import BASE, KIND_REGULAR
from cpbl.ingest.game_source_revisions import record_source_revision

log = logging.getLogger("cpbl.gamelog")

BOX_PAGE = f"{BASE}/box"
LIVE_ENDPOINT = f"{BASE}/box/getlive"
_HIDDEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')

# 每日鏈（`run_refresh_recent`）在容忍逐場失敗時的專用退出碼——DATA-BOX-DEEP-SILENT-FAIL1
# Q3 裁定＝甲-2：逐場失敗必須看得見，但**不得擋住當天的生產同步**（擋同步只是把
# 「靜默失敗」換成「生產靜默落後」，兩者一樣沒人在看）。故需要一個與 0（完全成功）
# 和 1（硬失敗）都可區分的碼，讓 `scripts/scrape-daily.sh` 能只對它放行 SYNC 分支。
#
# 為什麼是 69：同一條鏈上的退出碼命名空間（$CODE／$SYNC_CODE／$OVERALL_CODE）已用掉
# 64（EX_USAGE）、65（`backup-prod-db.sh` 內容門檻）、66（備份/同步）、70（狀態檔寫入）、
# 75（鎖被佔用）、127（DB 容器沒開）、1／2（Python 硬失敗／argparse）。69＝EX_UNAVAILABLE
# （「服務不可用」）語意最貼近「官網部分場次這次抓不到」，且該命名空間內未被用過。
# ⚠️ `scripts/scrape-daily.sh` 對這個值有一份字面複本（shell 讀不到 Python 常數），
# 兩邊一致由 `tests/test_gamelog_reconcile.py` 機械比對，不靠人記得同步改。
EXIT_INCOMPLETE_SCRAPE = 69


class GamelogScrapeIncomplete(RuntimeError):
    """`scrape_gamelogs` 有逐場失敗且呼叫端未明示容忍時拋出。

    為什麼是例外而不是「回傳值多一個欄位」（DATA-BOX-DEEP-SILENT-FAIL1 Q4 裁定＝乙）：
    回傳值把正確性押在「每個呼叫端都記得檢查、以後新增的第七個也記得」這條人工紀律
    上，而 `run_refresh_recent.py` 的補缺迴圈今天就已經完全丟棄回傳值——沒有任何機械
    檢查會發現。`box_revisions.py` 的鎖已為同一問題寫過原則：正確性要放進寫入層本身。

    `result` 帶著該次執行的完整對帳（target／games／failed／failures），供容忍的
    呼叫端與 log 列舉失敗場號；不得只給計數。
    """

    def __init__(self, result: dict) -> None:
        self.result = result
        super().__init__(reconcile_line(result))


def reconcile_line(result: dict) -> str:
    """把一次 `scrape_gamelogs` 的結果攤成一行可 grep 的對帳字串。

    對帳的母體是函式自己第一行宣告的 `target`，不是成功數——本卡的缺陷正是
    「`done: {'games': 8}` 看在人眼裡無從判斷 8 是目標還是 39 分之 8」。
    """
    return (
        f"kind={result.get('kind_code')} target={result.get('target')} "
        f"ok={result.get('games')} failed={len(result.get('failed') or [])} "
        f"failed_snos={result.get('failed')}"
    )


def _i(v) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _b(v) -> bool | None:
    if v in (None, ""):
        return None
    return str(v) in ("1", "true", "True", "Y")


def _scoreboard_rows(year: int, kind: str, sno: int, data: list[dict]) -> list[tuple]:
    return [
        (year, kind, sno, r.get("TeamNo"), _i(r.get("InningSeq")), r.get("VisitingHomeType"),
         r.get("TeamName"), _i(r.get("ScoreCnt")), _i(r.get("HittingCnt")), _i(r.get("ErrorCnt")))
        for r in data if r.get("TeamNo") and r.get("InningSeq") is not None
    ]


def _livelog_rows(year: int, kind: str, sno: int, data: list[dict]) -> list[tuple]:
    out = []
    for r in data:
        if not r.get("MainEventNo"):
            continue
        out.append((
            year, kind, sno, r.get("MainEventNo"), _i(r.get("InningSeq")), r.get("VisitingHomeType"),
            _i(r.get("BattingOrder")), _i(r.get("OutCnt")), _i(r.get("BallCnt")), _i(r.get("StrikeCnt")),
            _i(r.get("PitchCnt")), r.get("Content"), r.get("ActionName"), r.get("BattingActionName"),
            r.get("DefendStationCode"), r.get("HitterAcnt"), r.get("HitterName"),
            r.get("PitcherAcnt"), r.get("PitcherName"), r.get("CatcherAcnt"), r.get("CatcherName"),
            r.get("FirstBase") or None, r.get("SecondBase") or None, r.get("ThirdBase") or None,
            _b(r.get("IsStrike")), _b(r.get("IsBall")), _b(r.get("IsScoreCnt")),
            _b(r.get("IsChangePlayer")), _b(r.get("IsSpecialEvent")),
            _i(r.get("VisitingScore")), _i(r.get("HomeScore")),
        ))
    return out


def _bbox_rows(year: int, kind: str, sno: int, data: list[dict]) -> list[tuple]:
    out = []
    for r in data:
        if not r.get("HitterAcnt"):
            continue
        out.append((
            year, kind, sno, r.get("HitterAcnt"), r.get("HitterName"), r.get("VisitingHomeType"),
            r.get("HitterUniformNo"), r.get("RoleType"), _i(r.get("PlateAppearances")),
            _i(r.get("HitCnt")), _i(r.get("HittingCnt")), _i(r.get("RunBattedINCnt")), _i(r.get("ScoreCnt")),
            _i(r.get("OneBaseHitCnt")), _i(r.get("TwoBaseHitCnt")), _i(r.get("ThreeBaseHitCnt")),
            _i(r.get("HomeRunCnt")), _i(r.get("GrandSlamHomerunCnt")), _i(r.get("TotalBases")),
            _i(r.get("DoublePlayBatCnt")), _i(r.get("SacrificeHitCnt")), _i(r.get("SacrificeFlyCnt")),
            _i(r.get("BasesONBallsCnt")), _i(r.get("IntentionalBasesONBallsCnt")), _i(r.get("HitBYPitchCnt")),
            _i(r.get("StrikeOutCnt")), _i(r.get("StealBaseOKCnt")), _i(r.get("StealBaseFailCnt")),
            _i(r.get("Lobs")), _i(r.get("ErrorCnt")), _i(r.get("GameWinningRbiCnt")), _b(r.get("IsMvp")),
        ))
    return out


def _pbox_rows(year: int, kind: str, sno: int, data: list[dict]) -> list[tuple]:
    out = []
    for r in data:
        if not r.get("PitcherAcnt"):
            continue
        out.append((
            year, kind, sno, r.get("PitcherAcnt"), r.get("PitcherName"), r.get("VisitingHomeType"),
            r.get("PitcherUniformNo"), r.get("RoleType"), r.get("GameResult"),
            _b(r.get("IsCompleteGame")), _b(r.get("IsShoutOut")),
            _i(r.get("InningPitchedCnt")), _i(r.get("InningPitchedDiv3Cnt")), _i(r.get("PlateAppearances")),
            _i(r.get("PitchCnt")), _i(r.get("StrikeCnt")), _i(r.get("BallCnt")), _i(r.get("HittingCnt")),
            _i(r.get("HomeRunCnt")), _i(r.get("SacrificeHitCnt")), _i(r.get("SacrificeFlyCnt")),
            _i(r.get("BasesONBallsCnt")), _i(r.get("IntentionalBasesONBallsCnt")), _i(r.get("HitBYPitchCnt")),
            _i(r.get("StrikeOutCnt")), _i(r.get("WildPitchCnt")), _i(r.get("BalkCnt")),
            _i(r.get("RunCnt")), _i(r.get("EarnedRunCnt")), _i(r.get("ReliefPointCnt")),
            _f(r.get("GameHigherSpeedPitch")), _b(r.get("IsMvp")),
        ))
    return out


_f = lambda v: (float(v) if v not in (None, "") else None)  # noqa: E731

_BBOX_COLS = ("year,kind_code,game_sno,hitter_acnt,hitter_name,visiting_home_type,uniform_no,role_type,"
              "plate_appearances,at_bats,hits,rbi,runs,singles,doubles,triples,home_runs,grand_slam,"
              "total_bases,gidp,sac_hit,sac_fly,bb,ibb,hbp,so,sb,cs,lob,errors,gw_rbi,is_mvp")
_PBOX_COLS = ("year,kind_code,game_sno,pitcher_acnt,pitcher_name,visiting_home_type,uniform_no,role_type,"
              "game_result,is_complete_game,is_shutout,inning_pitched_cnt,inning_pitched_div3,"
              "plate_appearances,pitch_cnt,strike_cnt,ball_cnt,hits,home_runs,sac_hit,sac_fly,bb,ibb,hbp,"
              "so,wild_pitch,balk,runs,earned_runs,relief_point,max_speed,is_mvp")

_SB_COLS = ("year,kind_code,game_sno,team_no,inning_seq,visiting_home_type,team_name,"
            "score_cnt,hitting_cnt,error_cnt")
_LL_COLS = ("year,kind_code,game_sno,main_event_no,inning_seq,visiting_home_type,batting_order,"
            "out_cnt,ball_cnt,strike_cnt,pitch_cnt,content,action_name,batting_action_name,"
            "defend_station_code,hitter_acnt,hitter_name,pitcher_acnt,pitcher_name,catcher_acnt,"
            "catcher_name,first_base,second_base,third_base,is_strike,is_ball,is_score,"
            "is_change_player,is_special_event,visiting_score,home_score")


_GD_COLS = ("year,kind_code,game_sno,attendance,game_time,"
            "head_umpire,first_umpire,second_umpire,third_umpire,left_umpire,right_umpire")
# 天氣/致勝型態（getlive CurtGameDetailJson；與 HTML 來源的欄位分開 upsert，互不覆蓋）
_GD_WX_COLS = "year,kind_code,game_sno,weather_code,weather_desc,winning_type,attendance_backend"


def _weather_row(year: int, kind: str, sno: int, payload: dict) -> tuple | None:
    """getlive payload 抽 CurtGameDetailJson 的天氣/致勝型態；無資料回 None。

    注意天氣在 **Curt**GameDetailJson（GameDetailJson 同名欄位恆 null，勿搞混）。
    """
    raw = payload.get("CurtGameDetailJson")
    if not raw:
        return None
    try:
        o = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(o, list):
        o = o[0] if o else None
    if not isinstance(o, dict):
        return None
    code, desc = o.get("WeatherCode"), o.get("WeatherDesc")
    wtype, aud = o.get("WinningType"), _i(o.get("AudienceCntBackend"))
    if code is None and desc is None and wtype is None and aud is None:
        return None
    return (year, kind, sno, str(code) if code is not None else None, desc,
            str(wtype) if wtype is not None else None, aud)
_GD_UMP = {"主審": "head", "一壘審": "first", "二壘審": "second", "三壘審": "third",
           "左外野審": "left", "右外野審": "right"}
_GD_LI = re.compile(r"<li><span>([^<]+)</span>([^<]*)</li>")


def _parse_game_detail(html: str) -> dict:
    """box 頁 HTML 的「裁判 / 比賽時間 / 觀眾人數」區（皆 <li><span>標籤</span>值</li>）。"""
    d: dict = {}
    for label, val in _GD_LI.findall(html):
        v = val.strip()
        if not v:
            continue
        if label in _GD_UMP:
            d[_GD_UMP[label] + "_umpire"] = v
        elif label == "時間":
            d["game_time"] = v
        elif label == "觀眾":
            d["attendance"] = _i(v)
    return d


def scrape_game_details(year: int, snos: list[int], kind_code: str = KIND_REGULAR, delay: float = 0.7) -> int:
    """每場觀眾人數 + 裁判 + 時長（box 頁 HTML）。冪等 UPSERT，回寫入場數。"""
    if not snos:
        return 0
    from cpbl.ingest._browser import session
    s = session()
    rows: list[tuple] = []
    for sno in snos:
        time.sleep(delay)
        try:
            d = _parse_game_detail(s.page_html(f"/box?year={year}&KindCode={kind_code}&gameSno={sno}"))
        except Exception as e:  # noqa: BLE001 — 單場失敗略過
            log.warning("box 細節失敗 sno=%s: %s", sno, e)
            continue
        if not d:
            continue
        rows.append((year, kind_code, sno, d.get("attendance"), d.get("game_time"),
                     d.get("head_umpire"), d.get("first_umpire"), d.get("second_umpire"),
                     d.get("third_umpire"), d.get("left_umpire"), d.get("right_umpire")))
    n = _upsert("game_detail", _GD_COLS, 3, rows)
    log.info("game_detail: %d 場 (year=%s kind=%s)", n, year, kind_code)
    return n


def _upsert(table: str, cols: str, n_pk: int, records: list[tuple]) -> int:
    if not records:
        return 0
    col_list = [c.strip() for c in cols.split(",")]
    ph = "(" + ",".join(["%s"] * len(col_list)) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_list[n_pk:])
    pk = ", ".join(col_list[:n_pk])
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.{table} ({cols}) VALUES {ph} "
            f"ON CONFLICT ({pk}) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def scrape_gamelogs(year: int, snos: list[int], kind_code: str = KIND_REGULAR,
                    delay: float = 0.7, *, allow_partial: bool = False) -> dict:
    """抓指定場次的賽況並 UPSERT。回傳含對帳欄的結果字典。

    回傳鍵：`target`（宣告要抓的場數，＝`len(snos)`）、`games`（成功場數）、
    `failed`（失敗場號清單）、`failures`（逐場 {sno, error_code}）、以及各表寫入列數。
    **`target == games + len(failed)` 恆成立**（迴圈每一輪不是計成功就是記失敗）。

    失敗語意（DATA-BOX-DEEP-SILENT-FAIL1，Q4 裁定＝乙／Q2 裁定＝甲）：

    - **預設拋 `GamelogScrapeIncomplete`**：有任何一場失敗就拋，不設容忍門檻、
      不分入口。呼叫端什麼都不做時得到的是硬失敗，不是靜默成功。
    - 要容忍的呼叫端必須**明確** `allow_partial=True`，並在該處寫下理由。
    - 兩種模式都會先印出對帳行（有失敗時是 WARNING），故失敗場號一律可列舉。

    四個內嵌來源（Scoreboard／LiveLog／Batting／Pitching）任一 JSON 壞掉即算**那一場
    失敗**（`invalid_source_json`），與請求失敗同級。第一版曾把它降級成不計入 `failed`
    的 `degraded`，於是 `ScoreboardJson='{broken'` 仍然 exit 0——本卡要消滅的靜默缺口
    等於留了一個（2026-08-19 跨家族查核 R1-01 退件）。

    ⚠️ 判失敗**不丟資料**：已解析成功的來源照常 UPSERT（冪等，下次重抓自然收斂），
    壞掉的那個寫 0 列。把整場寫入一起放棄會讓「scoreboard 壞掉」連帶弄丟同一場完好的
    livelog——那是拿資料換一個比較整齊的語意。

    取 token 階段失敗（`_token()` 拋 RuntimeError）不走這條路：那是整批一場都沒抓，
    例外原樣往上拋、`allow_partial` 不吃它——2026-08-10 的 kind=A 就是這個形狀，
    它本來就已經硬失敗 exit 1，本卡不放寬它。
    """
    out: dict = {"kind_code": kind_code, "target": len(snos), "games": 0,
                 "failed": [], "failures": [],
                 "scoreboard": 0, "livelog": 0, "batting_box": 0, "pitching_box": 0}
    if not snos:
        return out
    from cpbl.ingest._browser import session
    s = session()
    box_path = f"/box?year={year}&KindCode={kind_code}&gameSno=1"

    def _token() -> str:
        m = _HIDDEN_RE.search(s.page_html(box_path, require=_HIDDEN_RE))
        if not m:
            raise RuntimeError("box 頁找不到 token（官網可能改版）")
        return m.group(1)

    def _fail(sno: int, error_code: str) -> None:
        """記一場失敗。**唯一**的失敗登記入口——迴圈裡每個 `continue` 都要先過它，
        否則 `target == games + len(failed)` 就不再成立，對帳又會變成裝飾。"""
        out["failed"].append(sno)
        out["failures"].append({"sno": sno, "error_code": error_code})

    class _GameFailed(Exception):
        """單場失敗的內部訊號（**已知**成因）。`error_code` 進 `out["failures"]`。"""

        def __init__(self, error_code: str, *, renew_token: bool = False,
                     detail: str = "") -> None:
            self.error_code = error_code
            self.renew_token = renew_token
            self.detail = detail or error_code
            super().__init__(self.detail)

    def _scrape_one(sno: int) -> None:
        """抓一場並寫入。**正常返回＝那一場抓到了；任何其他離開方式都是那一場失敗。**

        這個函式存在的理由是控制流，不是整潔：它讓「一場可以在不被計入的情況下結束」
        變成**構造上不可能**——呼叫端只有兩個分支（返回／例外），不需要知道函式體內
        有幾個 `continue`、幾個型別檢查、將來又多了什麼步驟。

        為什麼不繼續補型別檢查（2026-08-19 PM 自審裁定）：同一族已經失守四次——原始
        缺陷、查核 R1 的兩條（`invalid_source_json`、box JSON 未保護）、PM 自審的第四條
        （`'[1,2,3]'` 是合法 JSON、合法 list，通過所有檢查後在 `r.get()` 炸掉）。逐個補
        是在追一個**開放集合**：下一個 payload 形狀還會有第五條。改成包住整個函式體是
        **封閉集合**：不論函式體將來長成什麼樣，離開方式永遠只有那兩種。
        """
        try:
            status, text = s.post(
                box_path, "/box/getlive",
                {"GameSno": str(sno), "KindCode": kind_code, "Year": str(year)},
                headers={"RequestVerificationToken": token},
            )
        except Exception as e:  # noqa: BLE001 — 請求層失敗＝這一場沒抓到
            for source in ("scoreboard", "livelog"):
                record_source_revision(
                    year=year, kind_code=kind_code, game_sno=sno, source=source,
                    outcome="error", row_count=0, error_code="request_error",
                    detail={"phase": "getlive", "exception_type": type(e).__name__},
                )
            raise _GameFailed("request_error", detail=str(e)) from e
        if status != 200:
            for source in ("scoreboard", "livelog"):
                record_source_revision(
                    year=year, kind_code=kind_code, game_sno=sno, source=source,
                    outcome="error", row_count=0, error_code=f"http_{status}",
                    detail={"phase": "getlive", "http_status": status},
                )
            raise _GameFailed(f"http_{status}", renew_token=True)
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            for source in ("scoreboard", "livelog"):
                record_source_revision(
                    year=year, kind_code=kind_code, game_sno=sno, source=source,
                    outcome="error", row_count=0, error_code="invalid_response_json",
                    detail={"phase": "getlive"},
                )
            raise _GameFailed("invalid_response_json", renew_token=True) from e

        def _source_rows(source: str, key: str) -> tuple[list[dict], bool]:
            try:
                rows = json.loads(payload.get(key) or "[]")
                if not isinstance(rows, list):
                    raise ValueError("source payload is not an array")
                return rows, False
            except (json.JSONDecodeError, TypeError, ValueError):
                record_source_revision(
                    year=year, kind_code=kind_code, game_sno=sno, source=source,
                    outcome="error", row_count=0, error_code="invalid_source_json",
                    detail={"phase": "getlive", "payload_key": key},
                )
                return [], True

        def _box_rows(key: str) -> tuple[list[dict], bool]:
            """`BattingJson`／`PitchingJson`：壞 JSON 不得逸出成未捕捉例外。

            這兩行原本在逐場 `try` 之外，壞掉會拋 `JSONDecodeError` 炸掉整批——後面
            每一場一場都不會抓，對帳行與 `GamelogScrapeIncomplete` 都不會產生，每日鏈
            拿到的是 exit 1 而不是 69，於是**單場壞資料擋掉整天的生產同步**，正是 Q3
            裁定要避免的事（2026-08-19 跨家族查核 R1-02 退件）。

            這兩個來源不寫 `game_source_revisions`：該表現行只記 scoreboard／livelog
            兩個 source，擴充它的值域是另一件事，不在本卡射程。失敗訊號走 `_fail()`。
            """
            try:
                rows = json.loads(payload.get(key) or "[]")
                if not isinstance(rows, list):
                    raise ValueError("box payload is not an array")
                return rows, False
            except (json.JSONDecodeError, TypeError, ValueError):
                log.warning("來源 JSON 壞掉 sno=%s key=%s", sno, key)
                return [], True

        sb, sb_error = _source_rows("scoreboard", "ScoreboardJson")
        ll, ll_error = _source_rows("livelog", "LiveLogJson")
        bb, bb_error = _box_rows("BattingJson")
        pp, pp_error = _box_rows("PitchingJson")
        out["scoreboard"] += _upsert("game_scoreboard", _SB_COLS, 5,
                                     _scoreboard_rows(year, kind_code, sno, sb))
        out["livelog"] += _upsert("game_livelog", _LL_COLS, 4,
                                  _livelog_rows(year, kind_code, sno, ll))
        if not sb_error:
            record_source_revision(
                year=year, kind_code=kind_code, game_sno=sno, source="scoreboard",
                outcome="available" if sb else "missing", row_count=len(sb), payload=sb,
                detail={"phase": "getlive"},
            )
        if not ll_error:
            record_source_revision(
                year=year, kind_code=kind_code, game_sno=sno, source="livelog",
                outcome="available" if ll else "missing", row_count=len(ll), payload=ll,
                detail={"phase": "getlive"},
            )
        out["batting_box"] += _upsert("batting_gamelog", _BBOX_COLS, 4,
                                      _bbox_rows(year, kind_code, sno, bb))
        out["pitching_box"] += _upsert("pitching_gamelog", _PBOX_COLS, 4,
                                       _pbox_rows(year, kind_code, sno, pp))
        # DATA-BOX-REVISION-SNAPSHOT1：逐投手 append-only 快照，內容雜湊去重。
        # 只存快照，不影響既有 pitching_gamelog UPSERT 或回傳值語意。
        record_box_pitching_revisions(year, kind_code, sno, pp)
        wx = _weather_row(year, kind_code, sno, payload)
        if wx:
            out["weather"] = out.get("weather", 0) + _upsert("game_detail", _GD_WX_COLS, 3, [wx])
        if sb_error or ll_error or bb_error or pp_error:
            # 放在 UPSERT 之後：解析成功的來源已經寫進去了（見 docstring 的取捨），
            # 但這一場沒抓齊。
            raise _GameFailed("invalid_source_json")
        log.info("sno=%s scoreboard=%d livelog=%d box(打%d投%d)",
                 sno, len(sb), len(ll), len(bb), len(pp))

    token = _token()
    for sno in snos:
        time.sleep(delay)
        try:
            _scrape_one(sno)
        except _GameFailed as failure:
            log.warning("getlive 失敗 sno=%s: %s", sno, failure.detail)
            _fail(sno, failure.error_code)
            if failure.renew_token:
                # ⚠️ 這一行**刻意**放在 except 區塊裡：重取 token 失敗＝整批性失敗
                #（官網／挑戰整個掛了，不是某一場的事），例外會直接往上拋而不被下面的
                # 攔截器降級成單場失敗。放回 try 裡曾造成同一場被 _fail() 記兩次、
                # target == games + len(failed) 不成立（2026-08-19 修正）。
                token = _token()
            continue
        except psycopg.OperationalError:
            # 連線層失敗（含 psycopg_pool 的 PoolTimeout／PoolClosed，兩者都繼承
            # OperationalError）＝整庫的問題，不是某一場的問題。若記成「每一場都失敗」，
            # 每日鏈會拿到 69 ⇒ 本機 DB 掛著卻照樣同步生產：用一個誠實的退出碼換一個
            # 錯誤的下游動作。分界用驅動自己的類別階層，不是我們列舉的症狀。
            raise
        except Exception as e:  # noqa: BLE001 — 構造性保證：未預期例外＝那一場失敗
            # ⚠️ 這裡也會吞掉「程式自己的 bug」（TypeError／KeyError…），這是**明知的
            # 取捨**：執行期分不出「資料造成的例外」與「碼寫錯的例外」，硬要分就又回到
            # 開放集合。代價由三件事補償——error_code 是獨立的 unexpected_error、
            # log.exception 留完整 traceback、整批仍非零退出（每日鏈 69、其餘拋例外）。
            # 換句話說碼有 bug 時的症狀是「每一場都 unexpected_error ＋ 滿 log 的
            # traceback」，比原本「一個 traceback 之後整批消失」更容易看見。
            log.exception("未預期例外，記為單場失敗 sno=%s（%s）", sno, type(e).__name__)
            _fail(sno, "unexpected_error")
            continue
        out["games"] += 1
    log.log(logging.WARNING if out["failed"] else logging.INFO,
            "reconcile: %s", reconcile_line(out))
    if out["failed"] and not allow_partial:
        raise GamelogScrapeIncomplete(out)
    return out


def completed_snos(year: int, kind_code: str = KIND_REGULAR) -> list[int]:
    """本季已完成場次的 game_sno。供 `cpbl-scrape-gamelog <year>` 全季回填用。

    completed 判定沿用專案慣例（見記憶 completed-game-judgment，比照
    `cpbl_pitch_tracking.completed_game_snos` 的寫法）：需同時 score>0 與
    game_date <= CURRENT_DATE，避免保留賽掛未來日卻帶著中止時的比分被誤判成
    已完成（DATA-BOX-REVISION-SNAPSHOT1 iteration 3：本函式先前漏了日期界線，
    是這條慣例目前已知的漏網者，回填時會把還沒續打完的保留賽也排進清單去抓
    box——不是每日鏈的問題，`_completed_snos` 另一支已經有窗）。

    方向刻意用 UTC／`CURRENT_DATE`，不轉台北時區：與 `cpbl_pitch_tracking.py`
    現行寫法一致；是否統一改台北日界是 REMEDY1 Phase 2 的範圍，這裡不搶著改。
    """
    with conn() as c:
        rows = c.execute(
            "SELECT game_sno FROM cpbl.games WHERE year = %s AND kind_code = %s "
            "AND home_score + away_score > 0 AND game_date <= CURRENT_DATE ORDER BY game_sno",
            (year, kind_code),
        ).fetchall()
    return [r[0] for r in rows]


def completed_snos_within_days(year: int, kind_code: str, days_back: int) -> list[int]:
    """近 days_back 天內完成（比分>0 且 game_date 不晚於今天）的 game_sno。

    給 DATA-BOX-REVISION-SNAPSHOT1 深度重抓層用：`completed_snos()` 是全季，
    這支限定近 N 天，讓深度層的請求量不隨球季累積而線性成長。
    """
    with conn() as c:
        rows = c.execute(
            "SELECT game_sno FROM cpbl.games WHERE year = %s AND kind_code = %s "
            "AND home_score + away_score > 0 AND game_date <= CURRENT_DATE "
            "AND game_date >= CURRENT_DATE - (%s * INTERVAL '1 day') "
            "ORDER BY game_sno",
            (year, kind_code, days_back),
        ).fetchall()
    return [r[0] for r in rows]
