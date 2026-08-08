"""DATA-TZ-BOUNDARY1：日期界線時區語意回歸（AUDIT1 C12 殘項）。

DB ``SHOW timezone`` = UTC，而 game_date 與球季作息全是台北日。台北 00:00–07:59
這段 ``CURRENT_DATE`` 仍停在前一日 → 日期界線偏移一天。

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
    """
    from cpbl.completion import completed_games_sql

    assert "CURRENT_DATE" in completed_games_sql()
    assert "Asia/Taipei" not in completed_games_sql()
    # 呼叫端仍可注入台北日界線
    assert TAIPEI_TODAY_SQL in completed_games_sql(TAIPEI_TODAY_SQL)


# ────────────────────────────────── DB 唯讀：窗口存在即可，不斷言「現在」


def test_db_confirms_dual_timezone_day_divergence_window_exists() -> None:
    """DB 端以**定值時刻**證明日界差窗口存在（不依賴執行當下）。"""
    try:
        from cpbl.db import conn

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

    assert tz.upper() == "UTC", f"DB timezone 已非 UTC（{tz}），本卡前提需重新評估"
    (morning_utc, morning_tpe), (evening_utc, evening_tpe) = rows
    assert morning_utc != morning_tpe, "台北凌晨應與 UTC 不同日"
    assert evening_utc == evening_tpe, "台北晚間應與 UTC 同日"
