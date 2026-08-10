"""首頁每日入口聚合：最近比賽日、下一批賽事、來源 freshness 與正交 availability。

語意紅線（PRODUCT_UX_BLUEPRINT §5.1）：不存在「昨天／今天」概念。日期一律由資料
推導——最近比賽日＝最近一個有結果的日子，下一批賽事＝`as_of` 起最早一個尚無結果的
排定日；休兵日、延賽、刷新落後只反映在日期距離與 freshness，不以 0–0 硬推敘事。

availability 三個來源彼此正交（§8.1）：賽程、結果、賽前模型各有自己的 status 與
reason，不共用文案。欄位刻意避開 GAME-RECAP-STATUS1 將擁有的
`official_game_status`／`play_by_play_availability`／`advanced_freshness`／
`tracking_availability`／`wp_availability`；該卡凍結字彙後由串接方對帳。

本端點唯讀（§8.4）：不觸發 refresh、不訓練、不寫入；賽前機率直接讀 outcome_simple
artifact，模型缺席時仍回傳賽程。首頁不放區間（模型敏感度區間留在賽事頁／方法頁）。

`today` 區塊（UX-HOME-LIVE-STRIP1，Design Gate 2026-08-07）補上 `cpbl.games` 自己推不出
的那一半事實：**開賽時間欄不存在、live worker 只寫 Redis 不寫 DB**，所以「今天這場開打
了沒」在 DB 裡永遠是 0–0。本區塊把 canonical live snapshot（唯讀）疊在今天的排程列上，
讓首頁能與單場頁用同一組 phase 判斷賽前／賽中／賽後，而不是拿 0–0 當賽前。

`today` 與 `latest_game_day`／`next_slate` 是**兩套並存的視角**，不是互斥資料：呈現端擇
一渲染（`today.started` 為真時只渲染 today），同一場比賽因此不會同時出現在兩個區塊。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from cpbl.api.helpers import _dicts, kinds_of, official_status
from cpbl.api.live_cache import get_public_live_snapshot
from cpbl.api.pregame_serving import serving_state
from cpbl.completion import completed_games_sql_with_evidence
from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.outcome_simple import ORIENT, load_outcome_rows

router = APIRouter()

# 完成場判準（證據感知），以呼叫端的 as_of 參數為日期界線：
# 0:0 真和局需外部證據才算完成，否則「最近比賽日」會跳過那一天（DATA-TIE-REMEDY1）。
_DONE_AS_OF = completed_games_sql_with_evidence("games", "%(as_of)s")

# 超過此時數未成功 refresh 視為 stale（排程為每日一次；OPS-REFRESH1 擁有排程本身）。
STALE_AFTER_HOURS = 24
# 只把近期的未定案場次當成刷新落後訊號；更早的 0–0 屬歷史資料問題，不在本契約範圍。
UNRESOLVED_WINDOW_DAYS = 30
# 賽前模型（outcome_simple／game_features）只涵蓋一軍例行賽。
PREGAME_KIND = "A"
# 主區塊切換到「今日賽事」的判準（Design Gate 第 8 項）：當天任一場走到打線公布或更後。
# 取 `lineup_announced` 而非 `live` 有兩個理由：打線公布時已經有新內容可看；而 `live`／
# `final` 自帶保險——worker 漏接打線公布不會讓首頁整晚卡在昨天。
# `postponed`（延賽，根本沒開打）與 `unknown` **不算開始**：沒有新的賽況可看，主位留在
# 昨天。`reserved`（保留賽）相反——依 GLOSSARY 它是**已開賽後中止**、場上有比分，那是
# 今天發生的事，主區塊該切過來。
LIVE_STARTED_PHASES = frozenset({"lineup_announced", "live", "final", "reserved"})
# 「已開打」＝不得再顯示賽前機率的判準。**與上面的日界線是兩件事**：打線公布只是有新
# 內容可看，那一場仍然是賽前態、仍然該掛 PregameCard；真正開打（或已終場、或開打後被
# 保留）才要收掉——一場 3:2 中止的比賽旁邊掛賽前勝率是同一個誤導的另一種樣子。
LIVE_UNDERWAY_PHASES = frozenset({"live", "final", "reserved"})

_GAME_COLUMNS = """
    g.year AS season, g.kind_code, g.game_sno, g.game_date, g.venue,
    g.away_team_code, g.away_team_name, g.away_score,
    g.home_team_code, g.home_team_name, g.home_score,
    g.home_score + g.away_score > 0 AS has_score,
    g.delay_kind, g.orig_date
"""


def refresh_status(last_at: datetime | None, ok: bool | None, now: datetime) -> tuple[str, float | None]:
    """refresh_log 最新一列 → (status, hours_ago)。純函式，無 DB。

    unknown＝沒有任何刷新紀錄（無證據，fail closed，不宣稱資料是新的）；
    failed＝最近一次刷新自陳失敗；fresh／stale 只描述時間，不宣稱資料正確。
    """
    if last_at is None:
        return "unknown", None
    hours = (now - last_at).total_seconds() / 3600
    if ok is False:
        return "failed", round(hours, 2)
    return ("fresh" if hours <= STALE_AFTER_HOURS else "stale"), round(hours, 2)


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize(row: dict, as_of: date) -> dict:
    """一場比賽算「已完成」＝有比分**且**日期不在未來。

    比分不是充分條件：二軍保留賽（`delay_kind='保留'`，全史 4 筆）在 cpbl.games 裡
    帶著比分但 game_date 指向未來的補賽時段，只看比分會讓「最近比賽日」跳到未來。
    日期不在未來是可證明的判準，官方保留賽語意留給 GAME-RECAP-STATUS1 定案。

    未完成場次的比分一律 null：DB 的 0–0 是「還沒有結果」的佔位，照原樣送出去等於
    邀請前端把它讀成一場 0 比 0 的比賽（§5.1 語意紅線）。
    """
    row = dict(row)
    row["completed"] = bool(row.pop("has_score")) and row["game_date"] <= as_of
    row["game_date"] = _iso(row["game_date"])
    row["orig_date"] = _iso(row["orig_date"])
    if not row["completed"]:
        row["home_score"] = None
        row["away_score"] = None
    return row


_TAIPEI = ZoneInfo("Asia/Taipei")


def _now() -> datetime:
    """現在（UTC-aware）。抽成函式**只為了讓時鐘可注入**——本機跑在台北時區，
    不注入就測不出「容器 UTC、台北凌晨」那個唯一會出錯的情境。"""
    return datetime.now(UTC)


def _today_local() -> date:
    """容器本地日。**語意刻意不動**：這是 `as_of`／`latest_day`／`next_slate` 的日界，
    屬 DATA-TZ-BOUNDARY1 明確擱置、排在 REMEDY1 Phase 2 一起切換的範圍
    （見 `cpbl.completion` 模組註解）。抽成函式同樣只為了可注入。"""
    return date.today()


def taipei_today(now: datetime) -> date:
    """台北日界的「今天」。

    **只給 `today` 區塊用**，刻意與同一支 response 裡的 `as_of` 走不同日界——這不是漏改：

    - `as_of` 的用途是 upper bound（「最近比賽日」「下一批賽事」的日期界線）。容器 TZ 未設
      而落後 8 小時時，那只是「晚 8 小時納入」，方向保守，故 DATA-TZ-BOUNDARY1 盤點後
      明確不改，與判準一起排到 REMEDY1 Phase 2。
    - 「今日賽事」不是 upper bound，**是一個標籤**。把昨天標成今日不是保守，是錯的：
      台北 00:00–08:00 之間 `date.today()` 在 UTC 容器上會回前一天。

    `cpbl.completion` 的 `completed_games_sql` docstring 已寫明「新程式碼請用
    `TAIPEI_TODAY_SQL`」；此處是那條指示在 Python 側的對應物。
    """
    return now.astimezone(_TAIPEI).date()


def _age_seconds(fetched_at: object, now: datetime) -> float | None:
    """snapshot 取得至今的秒數；無法解析回 None（＝無從證明新鮮）。"""
    if not isinstance(fetched_at, str):
        return None
    try:
        at = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return max(0.0, (now - at).total_seconds())


def _int_or_none(value: object) -> int | None:
    """缺值必須是 None 而非 0——出局數要能區分「沒有資料」與「零出局」。"""
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# 進行中場次的即時中斷兩階門檻（Design Gate 第 5 項）。一階＝保留數字並標示，
# 二階＝收掉所有會變的數字。一階門檻由 snapshot 自帶的 `stale_after_seconds` 決定
# （live 為 45 秒），二階固定為下列秒數的**總年齡**。
LIVE_BLACKOUT_AFTER_SECONDS = 180


def live_interrupt(phase: str | None, age_seconds: float | None, stale_after: float | None,
                   freshness: str | None, source_status: str | None) -> str:
    """即時中斷分級。純函式；前後端各算一次，取較嚴重者（見 web 端 `liveInterrupt`）。

    後端這一份存在的理由是**首屏**：呈現端在 SSR 與 hydration 時不能碰瀏覽器時鐘
    （兩邊時區與時鐘不同會畫出不同的卡），但一個已經死掉十分鐘的 worker 不該在首屏
    上先亮出十分鐘前的比分再等一個輪詢週期才收掉。所以首屏吃這一格。
    """
    if phase == "final":
        return "none"
    reported = freshness == "stale" or source_status == "error"
    if phase != "live":
        return "degraded" if reported else "none"
    if age_seconds is None:
        return "blackout"  # 無從證明新鮮 → fail closed
    if age_seconds > LIVE_BLACKOUT_AFTER_SECONDS:
        return "blackout"
    return "degraded" if age_seconds > (stale_after or 45) or reported else "none"


def live_view(snapshot: dict, *, now: datetime | None = None) -> dict:
    """canonical live snapshot → 首頁卡片需要的最小欄位。純函式，無 I/O。

    只攤事實（Design Gate 第 3 項）：局數／比分／壘包／出局數／最後更新／官方決勝。
    **刻意不帶**逐球、球數、Recent Plays 與任何 WP 欄位——場中 WP 修復是另一張卡，
    本區塊不得依賴、不得預告。

    兩條沿用單場頁的既有紅線：

    1. 未開打場次 worker 仍回 `inning=1`／`half=1` 佔位（`web/src/lib/live-game.ts`
       的 `hasStartedPlay` 註解記錄的生產實測）。只判 truthy 會讓首頁對一場還沒開打的
       比賽顯示「▲ 1 局」，故此處先以 phase／`event_count` 認定真的打過，否則送 None。
    2. 壘包與出局數取自最後一筆 livelog 事件，語意是**打席前**局面
       （`docs/reference/GLOSSARY.md`：`out_cnt` 為打席前出局數），與單場記分條同一套
       慣例。非進行中的場次一律不送，不拿上一個打席的局面充當現況。
    """
    phase = snapshot.get("phase")
    event_count = int(snapshot.get("event_count") or 0)
    started_play = phase in {"live", "final"} or event_count > 0
    livelog = snapshot.get("livelog")
    event = (livelog[-1] if isinstance(livelog, list) and livelog else {}) if phase == "live" else {}
    source = snapshot.get("source") or {}
    age = _age_seconds(source.get("fetched_at"), now or datetime.now(UTC))
    return {
        "phase": phase,
        "raw_status": snapshot.get("raw_status"),
        # 官方預定開賽時間。`cpbl.games` 沒有這一欄，排序的第一鍵只能來自 snapshot。
        "starts_at": snapshot.get("starts_at"),
        "inning": snapshot.get("inning") if started_play else None,
        "half": snapshot.get("half") if started_play else None,
        "outs": _int_or_none(event.get("OutCnt")),
        "bases": {
            "first": bool(event.get("FirstBase")),
            "second": bool(event.get("SecondBase")),
            "third": bool(event.get("ThirdBase")),
        } if phase == "live" else None,
        "away_score": (snapshot.get("away") or {}).get("score"),
        "home_score": (snapshot.get("home") or {}).get("score"),
        "event_count": event_count,
        # freshness 三值（fresh／stale／final）與門檻由 live_cache.public_snapshot 決定；
        # 呈現端另以 fetched_at 自行算年齡，才能在「連 API 都打不到」時繼續老化。
        "freshness": snapshot.get("freshness"),
        "stale_after_seconds": snapshot.get("stale_after_seconds"),
        "source_status": snapshot.get("source_status"),
        "fetched_at": source.get("fetched_at"),
        # 首屏用的中斷分級（呈現端掛載後改以瀏覽器時鐘重算，取較嚴重者）。
        "interrupt": live_interrupt(phase, age, snapshot.get("stale_after_seconds"),
                                    snapshot.get("freshness"), snapshot.get("source_status")),
        # 官方決勝（勝投／敗投／救援／MVP）。賽後卡的「一行官方事實」只吃這裡，
        # 零模型衍生；缺席時為 None，呈現端不得補猜。
        "decisions": snapshot.get("decisions"),
    }


def live_source_status(configured: bool, snapshots: int, games: int) -> tuple[str, str | None]:
    """今日場次的即時來源狀態。純函式，供 freshness 條的維護者訊號使用。

    刻意只描述**觀察到的事實**（今天有幾場拿得到 snapshot），不宣稱 worker 或 Redis 的
    健康狀態——API 這一側分不出「Redis 不通」「worker 沒跑」「該場不在抓取窗口」，
    講死任何一個都是超出證據的診斷。訪客面的降級是靜默的，這裡只給維護者訊號。

    `reason` 一律不帶實作字彙（元件名、環境變數名、「當機」之類的成因宣稱）：這份
    payload 瀏覽器也收得到。要分辨「未啟用」與「啟用了但拿不到」看的是 `status`
    （`disabled` vs `unavailable`），那是機器可讀的判別碼，不是給人看的文案。
    """
    if not configured:
        return "disabled", "即時來源未啟用"
    if games == 0:
        return "ok", None
    if snapshots == games:
        return "ok", None
    if snapshots == 0:
        return "unavailable", "今日場次皆無即時快照"
    return "partial", f"今日 {games} 場中 {snapshots} 場有即時快照"


def _last_refresh(cursor) -> dict:
    """refresh_log 最新一列。表可能尚未 migrate → source_error，不讓首頁整包掛掉。"""
    try:
        cursor.execute(
            "SELECT refreshed_at, ok, scope FROM cpbl.refresh_log ORDER BY refreshed_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 — 缺表／權限問題應顯示為來源錯誤而非假裝新鮮
        return {"at": None, "ok": None, "scope": None, "hours_ago": None,
                "status": "source_error", "reason": type(exc).__name__}
    if row is None:
        return {"at": None, "ok": None, "scope": None, "hours_ago": None,
                "status": "unknown", "reason": "refresh_log 無紀錄"}
    status, hours = refresh_status(row[0], row[1], datetime.now(UTC))
    return {"at": _iso(row[0]), "ok": row[1], "scope": row[2], "hours_ago": hours,
            "status": status, "reason": None}


def _unresolved_statuses(cursor, rows: list[dict]) -> dict[tuple[int, str, int], str]:
    """未定案場次 → 官方排程狀態（`helpers.official_status`，與單場狀態端點同一份判定）。

    這一格取代了原本硬編的 `"unknown"`，也結清 API-DAILY-SUMMARY1 登記的串接義務。**值得
    多這一次查詢的理由是它真的分得開三件事**——`cpbl.games` 一律只看得到 0–0：

    - `postponed`／`reserved`：官方已宣告延賽／保留，資料沒有落後，沒有人需要做事；
    - `scheduled`：官方那邊也還沒有結果（開賽前、或官網自己還沒更新）；
    - `final`：**官方說打完了、我們卻還是 0–0**——這才是真的刷新落後，是唯一要人去看的一格。

    `rows` 為空時完全不查（休兵日與絕大多數日子的常態就是 0 筆），所以首頁的查詢數只在
    真的有未定案場次時才 +1。表尚未 migrate／權限不足時整批退回 unknown，不讓首頁掛掉
    （同 `_last_refresh` 的立場：缺證據就別宣稱）。
    """
    if not rows:
        return {}
    years = [r["season"] for r in rows]
    kinds = [r["kind_code"] for r in rows]
    snos = [r["game_sno"] for r in rows]
    try:
        cursor.execute(
            """
            SELECT year, kind_code, game_sno, raw_present_status, raw_game_result,
                   raw_game_date, fetched_at, last_seen_at
            FROM cpbl.game_schedule_status_revisions
            WHERE (year, kind_code, game_sno)
                  IN (SELECT * FROM unnest(%s::int[], %s::text[], %s::int[]))
            """,
            (years, kinds, snos),
        )
        revisions = _dicts(cursor)
    except Exception:  # noqa: BLE001 — 缺表／權限問題退回 unknown，與硬編時的行為相同
        return {}
    by_game: dict[tuple[int, str, int], list[dict]] = {}
    for row in revisions:
        by_game.setdefault((row["year"], row["kind_code"], row["game_sno"]), []).append(row)
    return {key: official_status(group)[0] for key, group in by_game.items()}


def _pregame_source() -> tuple[dict | None, dict]:
    """載入 outcome_simple artifact → (artifact, availability meta)。缺席不阻塞賽程。

    status 由 `pregame_serving.serving_state()` 決定，與 `/api/v1/outcome/pregame` 共用
    同一份判定：`serving_current`／`serving_previous`／`unavailable`。**要不要揭露看的是
    `degradation` 而非 status**：`serving_previous` 代表點機率來自上一版模型（或無法證明
    不是），而 `serving_current` 也可能帶 `serving_gate_failed`——serving 就是最新回測那
    一版、但那次回測沒過閘門。兩者首頁都必須據此揭露，不得無聲照顯
    （ML-OUTCOME-SIMPLE-LEAK2 紅線 5）。
    """
    return serving_state()


def _pregame_by_game(artifact: dict, games: list[dict]) -> dict[tuple[int, int], dict]:
    """為指定場次算點機率。game_features 只有一軍例行賽，故 (season, game_sno) 唯一。"""
    wanted = {(g["season"], g["game_sno"]) for g in games if g["kind_code"] == PREGAME_KIND}
    if not wanted:
        return {}
    rows = [row for row in load_outcome_rows(completed_only=False)
            if (row.season, row.game_sno) in wanted]
    if not rows:
        return {}
    probabilities = artifact["model"].predict(rows)
    return {
        (row.season, row.game_sno): {
            "status": "available",
            "home_win_probability": round(float(probability), 4),
            # 首頁只顯示點機率＋1 個主要訊號；挑哪一個是 PregameCard 的產品決策，
            # 這裡原樣提供模型的語意群訊號，不在 API 端替模型排序。
            "signals": {
                group: {
                    "key": signal,
                    "raw": row.features.get(signal),
                    "direction": ("lower_favors_home" if ORIENT.get(signal) == -1
                                  else "higher_favors_home"),
                }
                for group, signal in artifact["signals"].items()
            },
        }
        for row, probability in zip(rows, probabilities, strict=True)
    }


def _attach_pregame(row: dict, pregame: dict, artifact: dict | None, meta: dict) -> None:
    """把逐場賽前欄位掛上一列（原地）。`next_slate` 與 `today` 共用同一條推導路徑。"""
    if row["kind_code"] != PREGAME_KIND:
        row["pregame"] = {"status": "unsupported", "home_win_probability": None, "signals": None}
    elif artifact is None:
        # 逐場欄位沿用既有字彙（artifact_missing／error）。任何帶 degradation 的狀態
        # 都不走這條：那時機率仍算得出來（來自上一版或未過閘門的模型），降級揭露在
        # availability.pregame_model，不是把每一場都變成無機率。
        row["pregame"] = {"status": meta.get("fault") or "error",
                          "home_win_probability": None, "signals": None}
    else:
        row["pregame"] = pregame.get((row["season"], row["game_sno"]), {
            "status": "no_features", "home_win_probability": None, "signals": None})


def _today_block(rows: list[dict], *, game_day: date, as_of: date, pregame: dict,
                 artifact: dict | None, meta: dict) -> dict:
    """今天的場次 ＋ 疊上 canonical live snapshot。

    **賽前機率只掛在還沒開打的場次上**（`pregame` 欄整個缺席＝已開打）。這是 fail
    closed：驗收條件「已開打場次一律不得再顯示賽前機率」如果只靠呈現端的 if 判斷，
    任何一次前端 regression 就會在一場 5 局下的比賽旁邊掛回賽前勝率；欄位不存在時，
    前端連渲染它的素材都沒有。打線公布（`lineup_announced`）仍是賽前，照掛。
    """
    configured = bool(settings.redis_url)
    games: list[dict] = []
    snapshots = 0
    for row in rows:
        game = _serialize(row, as_of)
        snapshot = (get_public_live_snapshot(game["season"], game["kind_code"], game["game_sno"])
                    if configured else None)
        live = live_view(snapshot) if snapshot is not None else None
        if live is not None:
            snapshots += 1
        game["live"] = live
        # DB 已有比分（隔日爬蟲已補、或當天早場已入庫）同樣算「已開打」——即使 worker
        # 整個不可用，那一場也不該再顯示賽前機率。
        if not (game["completed"] or (live or {}).get("phase") in LIVE_UNDERWAY_PHASES):
            _attach_pregame(game, pregame, artifact, meta)
        games.append(game)
    status, reason = live_source_status(configured, snapshots, len(games))
    return {
        # 台北日（`game_day`），不是同一份 response 裡那個容器本地的 `as_of`——見
        # `taipei_today` 的說明，兩者用不同日界是刻意的。
        "game_date": _iso(game_day),
        # 日界線判準；呈現端據此擇一渲染 today 或（最近比賽日＋下一批賽事）。
        "started": any(g["completed"] or (g["live"] or {}).get("phase") in LIVE_STARTED_PHASES
                       for g in games),
        "live_source": {"status": status, "reason": reason,
                        "snapshots": snapshots, "games": len(games)},
        "games": games,
    }


@router.get("/api/v1/daily/summary")
def daily_summary(
    season: int | None = Query(None, description="限定年份；省略＝跨年度找最近的資料"),
    kind_code: str = Query("A", description="層級：A 一軍（含季後 E／C）、D 二軍（含 F）"),
) -> dict:
    """首頁單一聚合契約：今日賽事、最近比賽日、下一批賽事、freshness 與 availability。

    以 4 次唯讀查詢（日期界線、相關日的場次、未定案場次、refresh_log）取代首頁的十餘組
    請求；模型可用時再加 1 次 game_features 查詢，**有**未定案場次時再加 1 次官方排程狀態
    （常態是 0 筆故不查，見 `_unresolved_statuses`）。今日場次另加最多 3 次 Redis GET（唯讀
    canonical snapshot，Redis 不可用時整段退化為 None）。DB 失效時讓錯誤上浮（500）
    而非回空陣列——空白會被讀成「今天沒比賽」。

    本端點同時是**首頁前景輪詢的目標**：SSR 首屏與瀏覽器輪詢打同一支，賽況數字與
    freshness／serving 揭露因此永遠出自同一份 response，不會出現「兩個來源、不同新鮮度」。
    """
    kinds = kinds_of(kind_code)
    as_of = _today_local()
    # 「今日賽事」單獨走台北日界；`as_of` 的語意一字不改（`taipei_today` 說明了為什麼
    # 同一支 response 裡會有兩個「今天」，以及為什麼那不是漏改）。
    game_day = taipei_today(_now())
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            WITH scoped AS (
                SELECT game_date,
                       {_DONE_AS_OF} AS completed
                FROM cpbl.games
                WHERE kind_code = ANY(%(kinds)s)
                  AND (%(season)s::int IS NULL OR year = %(season)s)
            )
            SELECT (SELECT max(game_date) FROM scoped WHERE completed),
                   (SELECT min(game_date) FROM scoped
                     WHERE NOT completed AND game_date >= %(as_of)s),
                   (SELECT count(*) FROM scoped)
            """,
            {"kinds": kinds, "season": season, "as_of": as_of},
        )
        latest_day, next_day, scoped_games = cur.fetchone()

        # as_of 一律入列：「今天有沒有比賽」是 today 區塊的前提，而它既不是最近比賽日
        # （今天還沒有結果）也未必是下一批（今天有場次早已入庫時 next_day 會跳到明天）。
        # 多帶一天不增加查詢次數，仍是同一支 `game_date = ANY(...)`。
        days = sorted({d for d in (latest_day, next_day, as_of, game_day) if d is not None})
        by_day: dict[date, list[dict]] = {d: [] for d in days}
        # season 條件不可省：`latest_day`／`next_day` 本來就是 season 範圍內推導出的日期，
        # 所以舊版只靠日期就隱含選中了正確的球季；但 `as_of` 是**外部給的**日期，它落在
        # 哪一季與請求的 season 無關。少了這一行，`?season=2020` 會讓 today 區塊裝進今天
        # 的 2026 場次，與 `scope.season` 自相矛盾。
        cur.execute(
            f"""
            SELECT {_GAME_COLUMNS}
            FROM cpbl.games g
            WHERE g.kind_code = ANY(%s) AND g.game_date = ANY(%s)
              AND (%s::int IS NULL OR g.year = %s)
            ORDER BY g.game_date, g.kind_code, g.game_sno
            """,
            (kinds, days, season, season),
        )
        for row in _dicts(cur):
            # setdefault 而非索引：查詢已限定在 days 內，但用索引的話任何意料外的日期
            # 都會讓首頁 500。多出來的桶沒有人讀，退化成沉默優於整頁掛掉。
            by_day.setdefault(row["game_date"], []).append(row)

        cur.execute(
            f"""
            SELECT {_GAME_COLUMNS}
            FROM cpbl.games g
            WHERE g.kind_code = ANY(%s)
              AND (%s::int IS NULL OR g.year = %s)
              AND g.game_date < %s AND g.game_date >= %s
              AND g.home_score + g.away_score = 0
            ORDER BY g.game_date DESC, g.game_sno
            """,
            (kinds, season, season, as_of, as_of.fromordinal(as_of.toordinal() - UNRESOLVED_WINDOW_DAYS)),
        )
        unresolved = _dicts(cur)
        unresolved_status = _unresolved_statuses(cur, unresolved)
        last_refresh = _last_refresh(cur)

    # `latest_game_day` 給的是**那一天所有排定場次**，不是「賽果集合」——同一天可以既有
    # 賽果也有未開打場次：延賽宣告與補賽日公布是兩個時點，空窗期內場次仍掛原定日
    # （`game_date == orig_date`，GLOSSARY〈保留賽／delay_kind〉），局部因雨延賽時那一天
    # 仍有比賽打完。那些場次進不了 `next_slate`（日期不在 as_of 之後），而
    # `unresolved_games` 是維護者訊號、呈現端不渲染，所以此處濾掉＝首頁宣稱那天只有一場
    # 比賽（需求方 2026-08-10 裁定保留）。比分照樣是 null，狀態由呈現端依 `delay_kind` 標。
    latest_games = [_serialize(row, as_of) for row in by_day.get(latest_day, [])]
    next_games = [_serialize(row, as_of) for row in by_day.get(next_day, [])]

    artifact, pregame_meta = _pregame_source()
    # next_slate 與 today 常是同一天，但不保證（今天早場已入庫時 next_day 會跳到明天）。
    # 兩邊的候選合併成一次查詢，避免為了 today 再掃一遍 game_features。
    pregame_rows: dict[tuple[int, str, int], dict] = {
        (r["season"], r["kind_code"], r["game_sno"]): r
        for r in (*by_day.get(next_day, []), *by_day.get(game_day, []))
    }
    pregame = _pregame_by_game(artifact, list(pregame_rows.values())) if artifact else {}
    for row in next_games:
        _attach_pregame(row, pregame, artifact, pregame_meta)

    today_rows = by_day.get(game_day, [])
    today = (_today_block(today_rows, game_day=game_day, as_of=as_of, pregame=pregame,
                          artifact=artifact, meta=pregame_meta)
             if today_rows else None)

    if scoped_games == 0:
        schedule_status = {"status": "source_missing", "reason": "範圍內無任何賽程列"}
        results_status = {"status": "source_missing", "reason": "範圍內無任何賽程列"}
    else:
        schedule_status = ({"status": "available", "reason": None} if next_day is not None
                           else {"status": "season_complete",
                                 "reason": f"{_iso(as_of)} 起無已排定場次"})
        results_status = ({"status": "available", "reason": None} if latest_day is not None
                          else {"status": "not_started", "reason": "範圍內尚無已完成場次"})

    return {
        "scope": {"season": season, "kind_code": kind_code, "kinds": kinds, "as_of": _iso(as_of)},
        # 今天沒有任何排定場次時整塊為 None——空陣列會被呈現端讀成「有今日賽事區塊但
        # 沒有比賽」，那正是驗收條件要求的「零空容器」的反面。
        "today": today,
        "latest_game_day": None if latest_day is None else {
            "game_date": _iso(latest_day), "games": latest_games,
        },
        "next_slate": None if next_day is None else {
            "game_date": _iso(next_day),
            "days_from_as_of": (next_day - as_of).days,
            "games": next_games,
        },
        "freshness": {
            "as_of": _iso(as_of),
            "last_completed_game_date": _iso(latest_day),
            "last_refresh": last_refresh,
            # 過去日期卻仍無比分。`cpbl.games` 只看得到 0–0，分不出刷新落後與延賽未更新
            # 新日期，所以 status 改引用**官方排程狀態**（`_unresolved_statuses`，與單場
            # 狀態端點共用同一份判定）——這是 API-DAILY-SUMMARY1 當初登記、等 STATUS1
            # 凍結後要結清的串接義務。官方狀態也讀不出來時才退回 unknown（fail closed）。
            "unresolved_games": [
                {**_serialize(row, as_of),
                 "status": unresolved_status.get(
                     (row["season"], row["kind_code"], row["game_sno"]), "unknown")}
                for row in unresolved
            ],
        },
        "availability": {
            "schedule": schedule_status,
            "results": results_status,
            "pregame_model": pregame_meta,
        },
    }
