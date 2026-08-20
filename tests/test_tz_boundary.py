"""DATA-TZ-BOUNDARY1：日期界線時區語意回歸（AUDIT1 C12 殘項）。

⚠️ **2026-08-21 前提變更（DATA-TZ-BOUNDARY-SUCCESSION1）**：DB session timezone 已由
``cpbl.db`` 的 pool ``configure`` 明示為 ``Asia/Taipei``，容器 ``TZ`` 亦已在 Dockerfile
設為 ``Asia/Taipei``。本檔下半的 DB 絆線因此改成斷言**新的**前提。上半的純邏輯測試
不受影響——它們證的是「兩個時區的日界會差一天、且方向不對稱」，那是**時區本身的性質**，
與哪一邊被選中無關，所以在新前提下仍然是有效的說明文件。

歷史前提（改動前）：DB ``SHOW timezone`` = UTC，而 game_date 與球季作息全是台北日。
台北 00:00–07:59 這段 ``CURRENT_DATE`` 仍停在前一日 → 日期界線偏移一天。

**方向決定嚴重度**（本卡實測補正 AUDIT1「range 一律無害」的說法）：

* ``<=`` 上界：UTC 落後 → 收得更少 → 保守，不會誤納未來場。
* ``>=`` 下界：UTC 落後 → 收得更多 → 把昨天算成「今天起」，方向不保守。
* ``=`` 精確等值：沒有緩衝，整個指到錯誤的一天。

測試紀律：**不依賴牆鐘**。純邏輯部分用可注入的時刻推導期望值；DB 部分只以定值
時刻證明「雙時區日界差窗口存在」，不斷言「現在是不是在窗口內」——那會讓測試
在一天之中某些時段才通過。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from cpbl.completion import TAIPEI_TODAY_SQL

_TAIPEI = timezone(timedelta(hours=8))
_UTC = UTC

# 台北 00:00–07:59＝與 UTC 日界不同的窗口；08:00 起兩者同日。
_MORNING = datetime(2026, 8, 5, 3, 0, tzinfo=_TAIPEI)
_AFTERNOON = datetime(2026, 8, 5, 21, 0, tzinfo=_TAIPEI)


def _utc_today(now: datetime) -> date:
    return now.astimezone(_UTC).date()


def _taipei_today(now: datetime) -> date:
    return now.astimezone(_TAIPEI).date()


# ────────────────────────────────── 純邏輯：注入時刻，不看牆鐘


@pytest.mark.parametrize(
    ("now", "expect_differ"),
    [
        (datetime(2026, 8, 5, 0, 0, tzinfo=_TAIPEI), True),
        (_MORNING, True),
        (datetime(2026, 8, 5, 7, 59, tzinfo=_TAIPEI), True),
        (datetime(2026, 8, 5, 8, 0, tzinfo=_TAIPEI), False),
        (_AFTERNOON, False),
    ],
)
def test_divergence_window_is_taipei_midnight_to_0800(
    now: datetime, expect_differ: bool,
) -> None:
    """日界差窗口恰為台北 00:00–07:59，08:00 起消失。"""
    assert (_utc_today(now) != _taipei_today(now)) is expect_differ


def test_utc_lag_is_exactly_one_day_inside_the_window() -> None:
    """窗口內 UTC 日恆為台北日的前一天——偏移量是 1 天，不是任意值。"""
    assert _taipei_today(_MORNING) - _utc_today(_MORNING) == timedelta(days=1)


@pytest.mark.parametrize(
    ("now", "boundary", "utc_is_conservative"),
    [
        # 上界：UTC 落後 → 收得更少 → 保守（不會誤納未來場）
        (_MORNING, "upper", True),
        # 下界：UTC 落後 → 收得更多 → 不保守（昨天被算成「今天起」）
        (_MORNING, "lower", False),
    ],
)
def test_boundary_direction_decides_whether_utc_lag_is_safe(
    now: datetime, boundary: str, utc_is_conservative: bool,
) -> None:
    """方向不對稱：同一個 UTC 落後，對上界是保守、對下界是過度納入。

    以「昨天的場次」為探針——它落在台北日的前一天。
    """
    utc_d, tpe_d = _utc_today(now), _taipei_today(now)
    yesterday = tpe_d - timedelta(days=1)   # ＝ 窗口內的 utc_d

    if boundary == "upper":
        # `game_date <= 界線`：UTC 界線較早 → 納入的集合較小
        assert (yesterday <= utc_d) and (yesterday <= tpe_d)
        today_game = tpe_d
        assert not (today_game <= utc_d), "UTC 上界應排除今天（保守）"
        assert today_game <= tpe_d
    else:
        # `game_date >= 界線`：UTC 界線較早 → 納入的集合較大
        assert yesterday >= utc_d, "UTC 下界會把昨天納入（過度納入）"
        assert not (yesterday >= tpe_d), "台北下界正確排除昨天"
    assert utc_is_conservative is (boundary == "upper")


def test_exact_equality_has_no_conservative_direction() -> None:
    """精確等值沒有緩衝：窗口內 UTC 與台北選到的是**互斥**的兩天。"""
    utc_d, tpe_d = _utc_today(_MORNING), _taipei_today(_MORNING)

    assert utc_d != tpe_d
    # 任何一場的 game_date 不可能同時等於兩者 → 必有一邊全錯
    for probe in (utc_d, tpe_d):
        assert (probe == utc_d) != (probe == tpe_d)


# ────────────────────────────────── SQL 形態：語意敏感點已改台北日


def test_taipei_today_sql_is_a_date_in_taipei_zone() -> None:
    """helper 常數本身的形態：轉台北時區後再取日期。"""
    assert "Asia/Taipei" in TAIPEI_TODAY_SQL
    assert TAIPEI_TODAY_SQL.strip().endswith("::date")


def test_predictions_today_metric_uses_taipei_day() -> None:
    """`/api/info` 的 predictions_today 是全庫唯一精確等值點，必須用台北日。

    以 monkeypatch 攔截查詢字串（不連 DB），檢查送出的 SQL 帶台北日界線、
    且不再是裸 `CURRENT_DATE`。
    """
    from cpbl.api.routers import info

    queries: list[str] = []

    def fake_scalar(sql, params=()):
        queries.append(sql)
        return 0

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(info, "_scalar", fake_scalar)
        info.info()

    today_q = [q for q in queries if "home_score + away_score = 0" in q]
    assert today_q, "找不到 predictions_today 查詢"
    sql = today_q[0]
    assert TAIPEI_TODAY_SQL in sql, "predictions_today 未使用台北日界線"
    assert "game_date = CURRENT_DATE" not in sql, "仍殘留 UTC 精確等值界線"


def test_in_progress_years_lower_bound_uses_taipei_day() -> None:
    """`_in_progress_years` 的 `>=` 下界必須用台北日（下界方向不保守）。"""
    from cpbl.api import team_style

    captured: list[str] = []

    class _FakeConn:
        def execute(self, sql, params=()):
            captured.append(sql)
            return self

        def fetchall(self):
            return []

    team_style._in_progress_years(_FakeConn())

    assert captured, "未捕捉到查詢"
    sql = captured[0]
    assert TAIPEI_TODAY_SQL in sql, "in_progress 下界未使用台北日"
    assert "game_date >= CURRENT_DATE" not in sql, "仍殘留 UTC 下界"


def test_legacy_chain_helper_deliberately_keeps_utc_default() -> None:
    """舊 helper 的預設值刻意留 UTC——鏈端切換待 #53 G4 Phase B 後另卡授權。

    這是**明確決定**而非遺漏：它是上界用法（保守），Phase 2 才隨判準一起切。

    ⚠️ **本測試釘的是字面，不是行為**，別把它讀成「鏈端仍走 UTC 日界」：session timezone
    自 SUCCESSION1 起為 ``Asia/Taipei``，所以這個 ``CURRENT_DATE`` 經 ``cpbl.db.conn()``
    求值時已等於台北日。留著字面是為了讓「有沒有人動過那個預設」這件事**看得見**——
    授權在 ``#53 G4 Phase B``。
    """
    from cpbl.completion import completed_games_sql

    assert "CURRENT_DATE" in completed_games_sql()
    assert "Asia/Taipei" not in completed_games_sql()
    # 呼叫端仍可注入台北日界線
    assert TAIPEI_TODAY_SQL in completed_games_sql(TAIPEI_TODAY_SQL)


# ────────────────────────────────── DB 唯讀：窗口存在即可，不斷言「現在」


def test_db_confirms_dual_timezone_day_divergence_window_exists() -> None:
    """DB 端以**定值時刻**證明日界差窗口存在（不依賴執行當下）。

    ⚠️ 這條斷言原本是 ``tz.upper() == "UTC"``——那是 DATA-TZ-BOUNDARY1 時期的前提絆線。
    SUCCESSION1（2026-08-21）把 session timezone 明示為 ``Asia/Taipei``，所以絆線改成
    斷言**新的**前提。它仍是絆線而不是裝飾：任何人把 pool 改回 UTC（或讓 `configure`
    失效）都會在這裡響，而不是在某支業務查詢裡靜靜地少一天。
    """
    try:
        from cpbl.db import SESSION_TIMEZONE, conn

        with conn() as c, c.cursor() as cur:
            cur.execute("SHOW timezone")
            tz = cur.fetchone()[0]
            cur.execute("""
                SELECT (ts AT TIME ZONE 'UTC')::date,
                       (ts AT TIME ZONE 'Asia/Taipei')::date
                FROM (VALUES (timestamptz '2026-08-05 03:00+08'),
                             (timestamptz '2026-08-05 21:00+08')) v(ts)
            """)
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")

    assert tz == SESSION_TIMEZONE == "Asia/Taipei", (
        f"DB session timezone 已非 Asia/Taipei（{tz}）——業務日期一律台北是"
        "DATA-TZ-BOUNDARY-SUCCESSION1 的前提，改動它等於改動全站日界"
    )
    (morning_utc, morning_tpe), (evening_utc, evening_tpe) = rows
    assert morning_utc != morning_tpe, "台北凌晨應與 UTC 不同日"
    assert evening_utc == evening_tpe, "台北晚間應與 UTC 同日"


def test_session_timezone_is_not_left_to_the_environment() -> None:
    """session timezone 必須贏過 ``PGTZ``——這是本卡最容易被悄悄還原的一點。

    實測（2026-08-21）：``PGTZ`` 會**蓋掉** startup packet 裡的 ``-c timezone=``，
    所以「寫進連線字串」其實仍是靠環境變數。本測試在行程內把 ``PGTZ`` 設成一個明顯
    錯誤的時區、丟掉既有 pool 再重連——若有人改用 ``options=``／連線字串參數，這裡會紅。
    """
    import os

    try:
        import cpbl.db as dbmod
        from cpbl.db import conn
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"需本機 DB：{exc}")

    old_pool, old_pgtz = dbmod._pool, os.environ.get("PGTZ")
    dbmod._pool = None
    os.environ["PGTZ"] = "America/New_York"
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute("SHOW timezone")
            tz = cur.fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"需本機 DB：{exc}")
    finally:
        if dbmod._pool is not None:
            dbmod._pool.close()
        dbmod._pool = old_pool
        if old_pgtz is None:
            os.environ.pop("PGTZ", None)
        else:
            os.environ["PGTZ"] = old_pgtz

    assert tz == "Asia/Taipei", (
        f"PGTZ 蓋掉了 session timezone（得到 {tz}）——連線層的台北日界不得可被環境變數改寫"
    )
