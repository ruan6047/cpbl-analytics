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
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Query

from cpbl.api.helpers import _dicts, kinds_of
from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.outcome_simple import ORIENT, load_artifact, load_outcome_rows

router = APIRouter()

# 超過此時數未成功 refresh 視為 stale（排程為每日一次；OPS-REFRESH1 擁有排程本身）。
STALE_AFTER_HOURS = 24
# 只把近期的未定案場次當成刷新落後訊號；更早的 0–0 屬歷史資料問題，不在本契約範圍。
UNRESOLVED_WINDOW_DAYS = 30
# 賽前模型（outcome_simple／game_features）只涵蓋一軍例行賽。
PREGAME_KIND = "A"

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


def _pregame_source() -> tuple[dict | None, dict]:
    """載入 outcome_simple artifact → (artifact, availability meta)。缺席不阻塞賽程。"""
    path = settings.artifact_dir / "outcome_simple.joblib"
    if not path.exists():
        return None, {"status": "artifact_missing", "reason": "outcome_simple artifact 未建置",
                      "trained_through": None, "signals": None}
    try:
        artifact = load_artifact(path)
    except Exception as exc:  # noqa: BLE001 — artifact 損毀時回傳賽程，不回 50% 假數字
        return None, {"status": "error", "reason": type(exc).__name__,
                      "trained_through": None, "signals": None}
    return artifact, {"status": "available", "reason": None,
                      "trained_through": artifact["trained_through"],
                      "signals": artifact["signals"]}


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


@router.get("/api/v1/daily/summary")
def daily_summary(
    season: int | None = Query(None, description="限定年份；省略＝跨年度找最近的資料"),
    kind_code: str = Query("A", description="層級：A 一軍（含季後 E／C）、D 二軍（含 F）"),
) -> dict:
    """首頁單一聚合契約：最近比賽日、下一批賽事、freshness 與 availability。

    以 4 次唯讀查詢（日期界線、兩天的場次、未定案場次、refresh_log）取代首頁的十餘組
    請求；模型可用時再加 1 次 game_features 查詢。DB 失效時讓錯誤上浮（500）而非回空
    陣列——空白會被讀成「今天沒比賽」。
    """
    kinds = kinds_of(kind_code)
    as_of = date.today()
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            WITH scoped AS (
                SELECT game_date,
                       home_score + away_score > 0 AND game_date <= %(as_of)s AS completed
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

        days = [d for d in (latest_day, next_day) if d is not None]
        by_day: dict[date, list[dict]] = {d: [] for d in days}
        if days:
            cur.execute(
                f"""
                SELECT {_GAME_COLUMNS}
                FROM cpbl.games g
                WHERE g.kind_code = ANY(%s) AND g.game_date = ANY(%s)
                ORDER BY g.game_date, g.kind_code, g.game_sno
                """,
                (kinds, days),
            )
            for row in _dicts(cur):
                by_day[row["game_date"]].append(row)

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
        last_refresh = _last_refresh(cur)

    latest_games = [_serialize(row, as_of) for row in by_day.get(latest_day, [])]
    next_games = [_serialize(row, as_of) for row in by_day.get(next_day, [])]

    artifact, pregame_meta = _pregame_source()
    pregame = _pregame_by_game(artifact, by_day.get(next_day, [])) if artifact else {}
    for row in next_games:
        if row["kind_code"] != PREGAME_KIND:
            row["pregame"] = {"status": "unsupported", "home_win_probability": None,
                              "signals": None}
        elif pregame_meta["status"] != "available":
            row["pregame"] = {"status": pregame_meta["status"], "home_win_probability": None,
                              "signals": None}
        else:
            row["pregame"] = pregame.get((row["season"], row["game_sno"]), {
                "status": "no_features", "home_win_probability": None, "signals": None})

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
            # 過去日期卻仍無比分：可能是刷新落後，也可能是延賽未更新新日期。兩者在
            # cpbl.games 無法區分，故 status 一律 unknown（fail closed），由
            # GAME-RECAP-STATUS1 的官方狀態接手定案；此處只做維運 fail-fast 訊號。
            "unresolved_games": [{**_serialize(row, as_of), "status": "unknown"}
                                 for row in unresolved],
        },
        "availability": {
            "schedule": schedule_status,
            "results": results_status,
            "pregame_model": pregame_meta,
        },
    }
