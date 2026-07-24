"""GAME-RECAP-PA1-TAXONOMY1：canonical PA 狀態機 transition taxonomy 唯讀稽核。

本腳本**不**物化 PA、不寫資料庫、不改 schema。它只做三件事：

1. 以真實 ``action_name`` / ``batting_action_name`` / 計數變化 / 換人/特殊事件旗標，
   對每個 action 值產出**客觀效果剖面**（batter-out / hit / walk / reach-on-error /
   scored 的觀測比率），用來**驗證**（而非猜測）taxonomy 的分類指派。
2. 以 island detection（連續同 (game,inning,half,hitter)、排除換人列）重建候選 PA，
   並依 taxonomy 把每個 island 歸入 canonical 轉換類別，輸出完整分區計數。
3. 重現現行三套近似鍵（run_dist / winprob / frontend / 逐球三鍵，直接複用
   ``scripts.audit_game_recap_data`` 的實作）與 island truth 的誤配紅燈案例。

輸出：版本化 taxonomy JSON（builder 可直接消費）＋ Markdown 證據報告。

重跑：

    uv run python scripts/pa_transition_taxonomy.py \
        --from-year 2018 --to-year 2026 --kind A --kind C --kind D --kind E \
        --json docs/design/pa_transition_taxonomy.v1.json \
        --output docs/research/GAME-RECAP-PA1-TAXONOMY1_RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from cpbl.db import conn

# 複用 DATA1 稽核已定義、對照現行程式的近似鍵；紅燈案例即以此為對照組。
# 兼容兩種載入：直接跑 script（sys.path[0]=scripts/）或以 package 匯入。
try:
    from scripts.audit_game_recap_data import (  # type: ignore[import-not-found]
        _sequential_candidate_starts,
        frontend_moment_groups,
        legacy_pa_starts,
        pitch_linkage_risks,
    )
except ModuleNotFoundError:  # pragma: no cover - script 直跑路徑
    from audit_game_recap_data import (  # type: ignore[import-not-found, no-redef]
        _sequential_candidate_starts,
        frontend_moment_groups,
        legacy_pa_starts,
        pitch_linkage_risks,
    )

Event = dict[str, Any]

TAXONOMY_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# 版本化 transition taxonomy
# ---------------------------------------------------------------------------
# 說明：class 指派**必須**與下方 harness 觀測到的客觀效果一致；名稱只是標籤。
# 每個 action 標註 role（PA 生命週期角色）與 outcome_family（若為 PA 終結）。
#   role: pa_terminal | non_pa | ambiguous
#   outcome_family（僅 pa_terminal 有意義）:
#     out | hit | walk | hbp | reach_on_error | fielders_choice | sacrifice |
#     interference | uncaught_third_strike
# 「不以名稱猜測」的落實：harness 對每個 action 量測
#   batter_out_rate / hit_rate / walk_hbp_rate / reach_error_rate / scored_rate，
#   若觀測與指派矛盾（見 EXPECTED_SIGNAL），report 會標紅供 reviewer 複核。
TERMINAL_TAXONOMY: dict[str, dict[str, str]] = {
    # --- 出局 out ---
    "三振": {"role": "pa_terminal", "outcome_family": "out"},
    "飛球接殺": {"role": "pa_terminal", "outcome_family": "out"},
    "刺殺": {"role": "pa_terminal", "outcome_family": "out"},
    "界外飛球接殺": {"role": "pa_terminal", "outcome_family": "out"},
    "野手接球自踩壘包 一壘": {"role": "pa_terminal", "outcome_family": "out"},
    "雙殺打 刺殺": {"role": "pa_terminal", "outcome_family": "out"},
    "野手接球觸殺": {"role": "pa_terminal", "outcome_family": "out"},
    "內野高飛球": {"role": "pa_terminal", "outcome_family": "out"},
    "雙殺打 野手接球自踩壘包": {"role": "pa_terminal", "outcome_family": "out"},
    "雙殺打 野手接球觸殺": {"role": "pa_terminal", "outcome_family": "out"},
    "三殺打 刺殺": {"role": "pa_terminal", "outcome_family": "out"},
    "雙殺打 妨礙守備": {"role": "pa_terminal", "outcome_family": "out"},
    "跑離三呎線": {"role": "pa_terminal", "outcome_family": "out"},
    "跑一壘時，在三呎區外遭傳球觸及": {"role": "pa_terminal", "outcome_family": "out"},
    "違規被判出局": {"role": "pa_terminal", "outcome_family": "out"},
    "促請裁決/打序錯誤": {"role": "pa_terminal", "outcome_family": "out"},
    "擊球員碰觸界內球": {"role": "pa_terminal", "outcome_family": "out"},
    "妨礙守備": {"role": "pa_terminal", "outcome_family": "out"},
    "裁定三振": {"role": "pa_terminal", "outcome_family": "out"},
    "三振/妨礙": {"role": "pa_terminal", "outcome_family": "out"},
    # --- 三振後續（不死三振/捕手處理）：仍是 PA 終結，多數判出局 ---
    "三振/遭捕手傳一壘刺殺": {"role": "pa_terminal", "outcome_family": "out"},
    "三振/第三好球觸擊失敗": {"role": "pa_terminal", "outcome_family": "out"},
    "不死三振 暴投": {"role": "pa_terminal", "outcome_family": "uncaught_third_strike"},
    "不死三振 捕逸": {"role": "pa_terminal", "outcome_family": "uncaught_third_strike"},
    "不死三振 趁傳": {"role": "pa_terminal", "outcome_family": "uncaught_third_strike"},
    "不死三振 捕手傳一壘傳球失誤": {
        "role": "pa_terminal",
        "outcome_family": "uncaught_third_strike",
    },
    "不死三振 捕手傳一壘接球失誤": {
        "role": "pa_terminal",
        "outcome_family": "uncaught_third_strike",
    },
    # --- 安打 hit ---
    "一壘安打": {"role": "pa_terminal", "outcome_family": "hit"},
    "二壘安打": {"role": "pa_terminal", "outcome_family": "hit"},
    "三壘安打": {"role": "pa_terminal", "outcome_family": "hit"},
    "全壘打": {"role": "pa_terminal", "outcome_family": "hit"},
    "場內全壘打": {"role": "pa_terminal", "outcome_family": "hit"},
    "一壘安打 內野安打": {"role": "pa_terminal", "outcome_family": "hit"},
    "二壘安打 內野安打": {"role": "pa_terminal", "outcome_family": "hit"},
    "一壘安打 場地安打": {"role": "pa_terminal", "outcome_family": "hit"},
    "二壘安打 場地安打": {"role": "pa_terminal", "outcome_family": "hit"},
    "三壘安打 場地安打": {"role": "pa_terminal", "outcome_family": "hit"},
    # --- 保送 / 觸身 ---
    "四壞球": {"role": "pa_terminal", "outcome_family": "walk"},
    "故意四壞球": {"role": "pa_terminal", "outcome_family": "walk"},
    "裁定四壞球": {"role": "pa_terminal", "outcome_family": "walk"},
    "觸身死球": {"role": "pa_terminal", "outcome_family": "hbp"},
    # --- 上壘因失誤 reach_on_error ---
    "接球失誤": {"role": "pa_terminal", "outcome_family": "reach_on_error"},
    "傳球失誤": {"role": "pa_terminal", "outcome_family": "reach_on_error"},
    "雙殺打上壘-失誤": {"role": "pa_terminal", "outcome_family": "reach_on_error"},
    "犧牲短打上壘-失誤": {"role": "pa_terminal", "outcome_family": "reach_on_error"},
    "犧牲飛球上壘-失誤": {"role": "pa_terminal", "outcome_family": "reach_on_error"},
    # --- 野手選擇 / 趁傳 fielders_choice ---
    "野手選擇": {"role": "pa_terminal", "outcome_family": "fielders_choice"},
    "趁傳": {"role": "pa_terminal", "outcome_family": "fielders_choice"},
    "犧牲短打上壘-野選": {"role": "pa_terminal", "outcome_family": "fielders_choice"},
    "雙殺打上壘-趁傳": {"role": "pa_terminal", "outcome_family": "fielders_choice"},
    # --- 犧牲 sacrifice ---
    "犧牲飛球": {"role": "pa_terminal", "outcome_family": "sacrifice"},
    "犧牲界外飛球": {"role": "pa_terminal", "outcome_family": "sacrifice"},
    "犧牲短打 傳球": {"role": "pa_terminal", "outcome_family": "sacrifice"},
    "犧牲短打 野手接球觸殺": {"role": "pa_terminal", "outcome_family": "sacrifice"},
    "犧牲短打 野手接球自踩壘包": {"role": "pa_terminal", "outcome_family": "sacrifice"},
    "犧牲短打 野手跑離三呎線": {"role": "pa_terminal", "outcome_family": "sacrifice"},
    # --- 妨礙打擊（打者獲保送上壘）interference ---
    "妨礙打擊": {"role": "pa_terminal", "outcome_family": "interference"},
    # --- 非打席事件 non_pa ---
    # 突破僵局上壘＝延長賽突破僵局跑者放置規則，非打者結果、不含投球。
    "突破僵局上壘": {"role": "non_pa", "outcome_family": "tiebreak_runner"},
}

# 每個 outcome_family 對應的**客觀效果**期望（供 harness 對照觀測值抓矛盾）。
# key: outcome_family → (期望 batter_out 高?, 期望 hit 高?, 期望 walk/hbp 高?)
EXPECTED_SIGNAL: dict[str, dict[str, bool]] = {
    "out": {"batter_out": True, "hit": False, "walk_hbp": False},
    "hit": {"batter_out": False, "hit": True, "walk_hbp": False},
    "walk": {"batter_out": False, "hit": False, "walk_hbp": True},
    "hbp": {"batter_out": False, "hit": False, "walk_hbp": True},
    "reach_on_error": {"batter_out": False, "hit": False, "walk_hbp": False},
    "fielders_choice": {"batter_out": False, "hit": False, "walk_hbp": False},
    "sacrifice": {"batter_out": True, "hit": False, "walk_hbp": False},
    "interference": {"batter_out": False, "hit": False, "walk_hbp": False},
    "uncaught_third_strike": {"batter_out": False, "hit": False, "walk_hbp": False},
    "tiebreak_runner": {"batter_out": False, "hit": False, "walk_hbp": False},
}


@dataclass(frozen=True)
class ActionProfile:
    """單一 action 值的客觀效果剖面（以 island 終結列量測）。"""

    action_name: str
    islands: int
    rows: int
    batter_out_rate: float
    hit_rate: float
    walk_hbp_rate: float
    reach_error_rate: float
    scored_rate: float
    avg_pitches: float
    top_batting_actions: str


# ---------------------------------------------------------------------------
# SQL：island 重建 + 客觀效果量測
# ---------------------------------------------------------------------------
# 觀測訊號完全以 content 文字與 is_score 旗標判定，不引用 action_name 語意：
#   batter_out : content 出現「打者…出局」（打者本人出局宣告）
#   hit        : content 出現「安打」或「全壘打」
#   walk_hbp   : content 出現「四壞」或「死球」
#   reach_error: content 出現「失誤」或「野手選擇」或「趁傳」
# island 邊界排除 is_change_player 列（對齊 buildMoments 的 skip 行為）。
_ISLAND_SQL = """
WITH base AS (
    SELECT year, kind_code, game_sno, inning_seq,
           visiting_home_type AS vht,
           CASE WHEN main_event_no ~ '^[0-9]+$' THEN main_event_no::bigint END AS ev,
           main_event_no,
           hitter_acnt, pitcher_acnt, action_name, batting_action_name, content,
           is_strike, is_ball, is_score, is_special_event, pitch_cnt,
           LAG(hitter_acnt) OVER w AS prev_h,
           LAG(inning_seq) OVER w AS prev_inn,
           LAG(visiting_home_type) OVER w AS prev_vht
    FROM cpbl.game_livelog
    WHERE year BETWEEN %(from_year)s AND %(to_year)s
      AND kind_code = ANY(%(kinds)s)
      AND hitter_acnt IS NOT NULL AND hitter_acnt <> ''
      AND NOT COALESCE(is_change_player, false)
    WINDOW w AS (PARTITION BY year, kind_code, game_sno
                 ORDER BY CASE WHEN main_event_no ~ '^[0-9]+$'
                               THEN main_event_no::bigint END NULLS LAST, main_event_no)
),
isl AS (
    SELECT *,
        SUM(CASE WHEN hitter_acnt IS DISTINCT FROM prev_h
                   OR inning_seq IS DISTINCT FROM prev_inn
                   OR vht IS DISTINCT FROM prev_vht
                 THEN 1 ELSE 0 END)
            OVER (PARTITION BY year, kind_code, game_sno
                  ORDER BY ev NULLS LAST, main_event_no) AS isl_id
    FROM base
),
agg AS (
    SELECT year, kind_code, game_sno, isl_id,
        COUNT(*) AS rows,
        COUNT(DISTINCT pitch_cnt) FILTER (WHERE pitch_cnt > 0) AS distinct_pitches,
        BOOL_OR(is_score) AS scored,
        BOOL_OR(content ~ '打者[^。]*出局') AS batter_out,
        BOOL_OR(content LIKE '%%安打%%' OR content LIKE '%%全壘打%%') AS hit,
        BOOL_OR(content LIKE '%%四壞%%' OR content LIKE '%%死球%%') AS walk_hbp,
        BOOL_OR(content LIKE '%%失誤%%' OR content LIKE '%%野手選擇%%'
                OR content LIKE '%%趁傳%%') AS reach_error,
        (ARRAY_AGG(action_name ORDER BY ev DESC NULLS LAST, main_event_no DESC))[1] AS term_action,
        (ARRAY_AGG(batting_action_name ORDER BY ev DESC NULLS LAST, main_event_no DESC))[1]
            AS term_ban,
        (ARRAY_AGG(content ORDER BY ev DESC NULLS LAST, main_event_no DESC))[1] AS term_content
    FROM isl
    GROUP BY 1, 2, 3, 4
)
SELECT * FROM agg
"""


def _fetch_islands(cur: Any, params: dict[str, Any]) -> list[Event]:
    cur.execute(_ISLAND_SQL, params)
    return list(cur.fetchall())


def _action_profiles(islands: list[Event]) -> list[ActionProfile]:
    buckets: dict[str, list[Event]] = defaultdict(list)
    ban_counter: dict[str, Counter] = defaultdict(Counter)
    for row in islands:
        action = (row.get("term_action") or "").strip()
        key = action or "(blank)"
        buckets[key].append(row)
        ban_counter[key][(row.get("term_ban") or "").strip() or "(blank)"] += 1

    profiles: list[ActionProfile] = []
    for action, rows in buckets.items():
        n = len(rows)
        top = ", ".join(
            f"{name}:{count}" for name, count in ban_counter[action].most_common(3)
        )
        profiles.append(
            ActionProfile(
                action_name=action,
                islands=n,
                rows=sum(int(r["rows"]) for r in rows),
                batter_out_rate=sum(bool(r["batter_out"]) for r in rows) / n,
                hit_rate=sum(bool(r["hit"]) for r in rows) / n,
                walk_hbp_rate=sum(bool(r["walk_hbp"]) for r in rows) / n,
                reach_error_rate=sum(bool(r["reach_error"]) for r in rows) / n,
                scored_rate=sum(bool(r["scored"]) for r in rows) / n,
                avg_pitches=sum(int(r["distinct_pitches"] or 0) for r in rows) / n,
                top_batting_actions=top,
            )
        )
    profiles.sort(key=lambda p: p.islands, reverse=True)
    return profiles


def _classify_island(row: Event) -> str:
    """把 island 歸入 canonical 分區類別（fail-closed）。"""
    action = (row.get("term_action") or "").strip()
    has_pitch = int(row.get("distinct_pitches") or 0) > 0
    entry = TERMINAL_TAXONOMY.get(action)
    if entry is None:
        if not action:
            # 空 action：有投球＝截斷碎片；無投球＝純跑壘/暫停殘列（非 PA）。
            return "truncated_fragment" if has_pitch else "non_pa_running_fragment"
        return "unknown_action"  # 有 action 但未登錄 taxonomy → fail closed
    if entry["role"] == "non_pa":
        return "non_pa_tiebreak"
    # pa_terminal：無投球但為 award（故意四壞/妨礙打擊）仍是完成 PA。
    return "completed_pa"


def _classification_summary(islands: list[Event]) -> dict[str, Any]:
    per_class: Counter = Counter()
    per_year_kind: dict[tuple[int, str], Counter] = defaultdict(Counter)
    unknown_samples: list[Event] = []
    for row in islands:
        klass = _classify_island(row)
        per_class[klass] += 1
        per_year_kind[(row["year"], row["kind_code"])][klass] += 1
        if klass == "unknown_action" and len(unknown_samples) < 30:
            unknown_samples.append(row)
    return {
        "per_class": dict(per_class),
        "per_year_kind": {
            f"{y}/{k}": dict(counter) for (y, k), counter in sorted(per_year_kind.items())
        },
        "unknown_samples": unknown_samples,
    }


def _taxonomy_contradictions(profiles: list[ActionProfile]) -> list[Event]:
    """列出「觀測效果與指派 outcome_family 矛盾」的 action（reviewer 複核用）。"""
    out: list[Event] = []
    for p in profiles:
        entry = TERMINAL_TAXONOMY.get(p.action_name)
        if not entry:
            continue
        family = entry.get("outcome_family", "")
        expect = EXPECTED_SIGNAL.get(family)
        if not expect:
            continue
        flags: list[str] = []
        # 只在強訊號明顯反向時標記（門檻寬鬆，避免噪音）。
        if expect["batter_out"] and p.batter_out_rate < 0.5:
            flags.append(f"batter_out_rate={p.batter_out_rate:.2f}<0.5")
        if not expect["batter_out"] and p.batter_out_rate > 0.5:
            flags.append(f"batter_out_rate={p.batter_out_rate:.2f}>0.5")
        if expect["hit"] and p.hit_rate < 0.5:
            flags.append(f"hit_rate={p.hit_rate:.2f}<0.5")
        if expect["walk_hbp"] and p.walk_hbp_rate < 0.5:
            flags.append(f"walk_hbp_rate={p.walk_hbp_rate:.2f}<0.5")
        if flags:
            out.append(
                {
                    "action_name": p.action_name,
                    "outcome_family": family,
                    "islands": p.islands,
                    "flags": "; ".join(flags),
                }
            )
    return out


# ---------------------------------------------------------------------------
# 紅燈案例：近似鍵 vs island truth
# ---------------------------------------------------------------------------
def _game_events(cur: Any, year: int, kind: str, game: int) -> list[Event]:
    cur.execute(
        """
        SELECT year, kind_code, game_sno, main_event_no, inning_seq,
               visiting_home_type, batting_order, out_cnt, ball_cnt, strike_cnt,
               pitch_cnt, content, action_name, batting_action_name, hitter_acnt,
               hitter_name, pitcher_acnt, pitcher_name, is_score,
               is_change_player, is_special_event
        FROM cpbl.game_livelog
        WHERE year = %s AND kind_code = %s AND game_sno = %s
        ORDER BY CASE WHEN main_event_no ~ '^[0-9]+$'
                      THEN main_event_no::bigint END NULLS LAST, main_event_no
        """,
        (year, kind, game),
    )
    return list(cur.fetchall())


def _island_starts(events: list[Event]) -> list[list[Event]]:
    """canonical island（排除換人列、切界 (inning,half,hitter)）。"""
    islands: list[list[Event]] = []
    prev_key: tuple[Any, str, Any] | None = None
    for ev in events:
        if ev.get("is_change_player") or not ev.get("hitter_acnt"):
            if islands:
                islands[-1].append(ev)  # 換人列附掛於當前 PA，不切界
            continue
        key = (ev.get("inning_seq"), str(ev.get("visiting_home_type")), ev.get("hitter_acnt"))
        if key != prev_key:
            islands.append([])
            prev_key = key
        islands[-1].append(ev)
    return islands


def _redlight_repeat_batter(cur: Any) -> Event:
    """同局同打者二度上場：近似鍵合併 → 應為 2+ 個不同 pa。"""
    cur.execute(
        """
        WITH ev AS (
            SELECT year, kind_code, game_sno, inning_seq, visiting_home_type AS vht,
                   CASE WHEN main_event_no ~ '^[0-9]+$' THEN main_event_no::bigint END AS ev,
                   hitter_acnt,
                   LAG(hitter_acnt) OVER w AS prev_h
            FROM cpbl.game_livelog
            WHERE hitter_acnt IS NOT NULL AND hitter_acnt <> ''
              AND NOT COALESCE(is_change_player, false)
            WINDOW w AS (PARTITION BY year, kind_code, game_sno ORDER BY
                         CASE WHEN main_event_no ~ '^[0-9]+$' THEN main_event_no::bigint END)
        ),
        isl AS (
            SELECT *, SUM(CASE WHEN hitter_acnt IS DISTINCT FROM prev_h THEN 1 ELSE 0 END)
                OVER (PARTITION BY year, kind_code, game_sno ORDER BY ev) AS isl_id
            FROM ev
        )
        SELECT year, kind_code, game_sno, inning_seq, vht, hitter_acnt,
               COUNT(DISTINCT isl_id) AS islands
        FROM isl
        GROUP BY 1, 2, 3, 4, 5, 6
        HAVING COUNT(DISTINCT isl_id) >= 2
        ORDER BY islands DESC, year DESC, game_sno
        LIMIT 20
        """
    )
    rows = list(cur.fetchall())
    return {
        "total_scopes": len(rows),
        "max_islands": max((r["islands"] for r in rows), default=0),
        "samples": rows[:12],
    }


def _redlight_pitching_change(cur: Any) -> Event:
    """打席中換投：一個 island 面對 2+ 投手 → 近似三鍵把單一 PA 拆成多段。"""
    cur.execute(
        """
        WITH ev AS (
            SELECT year, kind_code, game_sno, inning_seq, visiting_home_type AS vht,
                   CASE WHEN main_event_no ~ '^[0-9]+$' THEN main_event_no::bigint END AS ev,
                   hitter_acnt, pitcher_acnt,
                   LAG(hitter_acnt) OVER w AS prev_h
            FROM cpbl.game_livelog
            WHERE hitter_acnt IS NOT NULL AND hitter_acnt <> ''
              AND NOT COALESCE(is_change_player, false)
            WINDOW w AS (PARTITION BY year, kind_code, game_sno ORDER BY
                         CASE WHEN main_event_no ~ '^[0-9]+$' THEN main_event_no::bigint END)
        ),
        isl AS (
            SELECT *, SUM(CASE WHEN hitter_acnt IS DISTINCT FROM prev_h THEN 1 ELSE 0 END)
                OVER (PARTITION BY year, kind_code, game_sno ORDER BY ev) AS isl_id
            FROM ev
        )
        SELECT year, kind_code, game_sno, inning_seq, vht, hitter_acnt,
               COUNT(DISTINCT pitcher_acnt) AS pitchers
        FROM isl
        GROUP BY 1, 2, 3, 4, 5, 6, isl_id
        HAVING COUNT(DISTINCT pitcher_acnt) >= 2
        ORDER BY pitchers DESC, year DESC, game_sno
        LIMIT 20
        """
    )
    rows = list(cur.fetchall())
    return {
        "total_pas": len(rows),
        "max_pitchers": max((r["pitchers"] for r in rows), default=0),
        "samples": rows[:12],
    }


def _redlight_legacy_key_delta(cur: Any, samples: list[tuple[int, str, int]]) -> list[Event]:
    """對抽樣場次，對照 island truth 與現行三套近似鍵的 PA 數/邊界。"""
    out: list[Event] = []
    for year, kind, game in samples:
        events = _game_events(cur, year, kind, game)
        if not events:
            continue
        starts = legacy_pa_starts(events)
        islands = _island_starts(events)
        # 真正的 PA island（有終結 action 或 award，非 tiebreak/ghost）
        canonical_pa = 0
        for isl in islands:
            non_change = [e for e in isl if not e.get("is_change_player")]
            if not non_change:
                continue
            term = next(
                (e for e in reversed(non_change) if (e.get("action_name") or "").strip()),
                None,
            )
            action = (term.get("action_name") or "").strip() if term else ""
            if action and TERMINAL_TAXONOMY.get(action, {}).get("role") == "pa_terminal":
                canonical_pa += 1
        linkage = pitch_linkage_risks(_sequential_candidate_starts(events))
        out.append(
            {
                "scope": f"{year}/{kind}/{game}",
                "canonical_pa": canonical_pa,
                "run_dist_pa": len(starts["run_dist"]),
                "winprob_pa": len(starts["winprob"]),
                "frontend_pa": len(frontend_moment_groups(events)),
                "ambiguous_pitch_keys": linkage.ambiguous_keys,
                "ambiguous_pitch_pas": linkage.ambiguous_plate_appearances,
            }
        )
    return out


def _redlight_pitch_multiplicity(cur: Any, params: dict[str, Any]) -> Event:
    """(game,pitcher,pitch_cnt) 對多列：pitch_cnt 非逐列唯一（牽制/暫停共用）。"""
    cur.execute(
        """
        SELECT rows_per_pitch, COUNT(*) AS pitch_keys
        FROM (
            SELECT year, kind_code, game_sno, pitcher_acnt, pitch_cnt,
                   COUNT(*) AS rows_per_pitch
            FROM cpbl.game_livelog
            WHERE year BETWEEN %(from_year)s AND %(to_year)s
              AND kind_code = ANY(%(kinds)s)
              AND pitcher_acnt IS NOT NULL AND pitcher_acnt <> '' AND pitch_cnt > 0
            GROUP BY 1, 2, 3, 4, 5
        ) t
        GROUP BY 1 ORDER BY 1
        """,
        params,
    )
    dist = list(cur.fetchall())
    total = sum(int(r["pitch_keys"]) for r in dist)
    multi = sum(int(r["pitch_keys"]) for r in dist if int(r["rows_per_pitch"]) > 1)
    return {"distribution": dist, "total_pitch_keys": total, "multi_row_pitch_keys": multi}


# ---------------------------------------------------------------------------
# collect + render
# ---------------------------------------------------------------------------
# 手工挑選、跨賽制的紅燈抽樣場次（reviewer 可以原始事件逐列複核）。
REDLIGHT_SCOPES: list[tuple[int, str, int]] = [
    (2026, "A", 54),  # 同局同打者二度上場（郭天信；12 分大局）
    (2025, "A", 52),  # 打席中兩次換投（陳思仲；一個保送對三投手）
    (2026, "A", 76),  # 跑壘牽制第三出局截斷打者（朱育賢 空 action 碎片）
    (2018, "A", 4),   # 同局多名打者各二度上場（大局；排除換人列後 max island=2）
    (2026, "D", 137),  # 延長賽突破僵局跑者（非 PA）
]


def collect(from_year: int, to_year: int, kinds: list[str]) -> Event:
    started = time.perf_counter()
    params = {"from_year": from_year, "to_year": to_year, "kinds": kinds}
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        islands = _fetch_islands(cur, params)
        profiles = _action_profiles(islands)
        classification = _classification_summary(islands)
        contradictions = _taxonomy_contradictions(profiles)
        repeat_batter = _redlight_repeat_batter(cur)
        pitching_change = _redlight_pitching_change(cur)
        legacy_delta = _redlight_legacy_key_delta(cur, REDLIGHT_SCOPES)
        pitch_multi = _redlight_pitch_multiplicity(cur, params)

    return {
        "parameters": params,
        "taxonomy_version": TAXONOMY_VERSION,
        "island_total": len(islands),
        "profiles": profiles,
        "classification": classification,
        "contradictions": contradictions,
        "redlight": {
            "repeat_batter": repeat_batter,
            "pitching_change": pitching_change,
            "legacy_delta": legacy_delta,
            "pitch_multiplicity": pitch_multi,
        },
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "generated_at": datetime.now().astimezone(),
    }


def build_taxonomy_json(report: Event) -> Event:
    """builder 可直接消費的版本化 taxonomy。"""
    profile_by_action = {p.action_name: p for p in report["profiles"]}
    actions = []
    for action, entry in sorted(TERMINAL_TAXONOMY.items()):
        prof = profile_by_action.get(action)
        actions.append(
            {
                "action_name": action,
                "role": entry["role"],
                "outcome_family": entry["outcome_family"],
                "observed_islands": prof.islands if prof else 0,
                "observed": {
                    "batter_out_rate": round(prof.batter_out_rate, 4) if prof else None,
                    "hit_rate": round(prof.hit_rate, 4) if prof else None,
                    "walk_hbp_rate": round(prof.walk_hbp_rate, 4) if prof else None,
                    "reach_error_rate": round(prof.reach_error_rate, 4) if prof else None,
                    "scored_rate": round(prof.scored_rate, 4) if prof else None,
                }
                if prof
                else None,
            }
        )
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "generated_at": str(report["generated_at"]),
        "parameters": report["parameters"],
        "island_rule": {
            "boundary_key": ["year", "kind_code", "game_sno", "inning_seq",
                             "visiting_home_type", "hitter_acnt"],
            "exclude_from_boundary": "is_change_player rows (attached as members, never seed/split)",
            "ordering": "main_event_no::bigint (strict total order)",
        },
        "island_classes": {
            "completed_pa": "≥1 island with a registered pa_terminal action (含無投球 award)",
            "truncated_fragment": "空 action 但含投球：打者被跑壘/局終出局截斷，非終結 PA",
            "non_pa_tiebreak": "突破僵局上壘：延長賽跑者放置規則，非打席",
            "non_pa_running_fragment": "空 action 且無投球：純跑壘/暫停殘列",
            "unknown_action": "非空 action 但未登錄 taxonomy → fail closed（unreliable）",
        },
        "fail_closed": {
            "unknown_action": "unreliable：pa 保留成員事件，WP/WPA 與逐球映射回 null + reason",
            "truncated_fragment": "not_a_pa：不產出 credited outcome；逐球歸屬 mapping_failed",
            "ambiguous_pitch_key": "(inning,pitcher,hitter) 候選>1 → mapping_state=failed",
        },
        "actions": actions,
    }


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(rows: list[Event], columns: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_cell(row.get(key)) for _, key in columns) + " |" for row in rows
    ]
    return "\n".join([header, divider, *body]) if body else "_無資料。_"


def render(report: Event) -> str:
    params = report["parameters"]
    rl = report["redlight"]
    profile_rows = [
        {
            "action_name": p.action_name,
            "islands": p.islands,
            "role": TERMINAL_TAXONOMY.get(p.action_name, {}).get("role", "unregistered"),
            "outcome_family": TERMINAL_TAXONOMY.get(p.action_name, {}).get(
                "outcome_family", "—"
            ),
            "batter_out_rate": p.batter_out_rate,
            "hit_rate": p.hit_rate,
            "walk_hbp_rate": p.walk_hbp_rate,
            "reach_error_rate": p.reach_error_rate,
            "scored_rate": p.scored_rate,
            "avg_pitches": p.avg_pitches,
            "top_batting_actions": p.top_batting_actions,
        }
        for p in report["profiles"]
    ]
    parts = [
        "---",
        'title: "GAME-RECAP-PA1-TAXONOMY1 canonical PA transition taxonomy 稽核結果"',
        "card_id: GAME-RECAP-PA1-TAXONOMY1",
        "status: awaiting-independent-review",
        f"taxonomy_version: {report['taxonomy_version']}",
        f"date: {date.today()}",
        "tags:",
        "  - cpbl",
        "  - data-audit",
        "  - game-recap",
        "  - pa-taxonomy",
        "---",
        "",
        "# GAME-RECAP-PA1-TAXONOMY1 稽核結果",
        "",
        "關聯：[[GAME-RECAP-PA1]]、[[GAME-RECAP-PA1_CONTRACT]]、[[GAME-RECAP-DATA1]]、"
        "[[GAME-RECAP-PA1-EXPAND1]]、[[GAME-RECAP-PA1-BUILD1]]。",
        "",
        "> [!info] 本檔是**自動產生的證據**，taxonomy 規範文本見 "
        "[`docs/design/GAME-RECAP-PA1-TAXONOMY1.md`](../design/GAME-RECAP-PA1-TAXONOMY1.md)，"
        "builder 消費的版本化輸出見 "
        "[`docs/design/pa_transition_taxonomy.v1.json`](../design/pa_transition_taxonomy.v1.json)。",
        "",
        "## 方法",
        "",
        f"- 範圍：{params['from_year']}–{params['to_year']}，kind={','.join(params['kinds'])}；"
        f"taxonomy_version={report['taxonomy_version']}。",
        "- 全程 PostgreSQL `READ ONLY` transaction、psycopg 參數化；不寫任何資料。",
        f"- 重建 island 總數：{report['island_total']}；耗時 {report['elapsed_seconds']} 秒；"
        f"產生時間 {report['generated_at']}。",
        "- **反名稱猜測**：每個 action 的 `outcome_family` 由 taxonomy 指派，但下表同時列出"
        "純以 content 文字/`is_score` 量測的客觀效果比率（batter_out/hit/walk_hbp/"
        "reach_error/scored），供 reviewer falsify。",
        "",
        "重跑：",
        "",
        "```bash",
        "uv run python scripts/pa_transition_taxonomy.py --from-year "
        f"{params['from_year']} --to-year {params['to_year']} "
        + " ".join(f"--kind {k}" for k in params["kinds"])
        + " --json docs/design/pa_transition_taxonomy.v1.json"
        + " --output docs/research/GAME-RECAP-PA1-TAXONOMY1_RESULTS.md",
        "```",
        "",
        "## island 分區（fail-closed 分類）",
        "",
        _table(
            [{"class": k, "islands": v} for k, v in sorted(
                report["classification"]["per_class"].items())],
            [("分類", "class"), ("island 數", "islands")],
        ),
        "",
        "分類語意：`completed_pa`＝有登錄 pa_terminal action（含故意四壞等無投球 award）；"
        "`truncated_fragment`＝空 action 但有投球（打者被跑壘/局終出局截斷）；"
        "`non_pa_tiebreak`＝突破僵局跑者；`non_pa_running_fragment`＝空 action 無投球純跑壘殘列；"
        "`unknown_action`＝有 action 但未登錄 → **fail closed**。",
        "",
        "### 年 × 賽制分區",
        "",
        _table(
            [{"scope": k, **v} for k, v in report["classification"]["per_year_kind"].items()],
            [("scope", "scope"), ("completed_pa", "completed_pa"),
             ("truncated", "truncated_fragment"), ("tiebreak", "non_pa_tiebreak"),
             ("run_frag", "non_pa_running_fragment"), ("unknown", "unknown_action")],
        ),
        "",
        "## action 值域客觀效果剖面（完整）",
        "",
        "> `outcome_family` 是 taxonomy 指派；後五欄是**觀測值**。若指派為 `out` 卻 "
        "`batter_out_rate` 偏低，或指派為 `hit` 卻 `hit_rate` 偏低，即為需複核的矛盾"
        "（見下節）。",
        "",
        _table(
            profile_rows,
            [("action_name", "action_name"), ("islands", "islands"), ("role", "role"),
             ("outcome_family", "outcome_family"), ("batter_out", "batter_out_rate"),
             ("hit", "hit_rate"), ("walk_hbp", "walk_hbp_rate"),
             ("reach_err", "reach_error_rate"), ("scored", "scored_rate"),
             ("avg_pitch", "avg_pitches"), ("top batting_action", "top_batting_actions")],
        ),
        "",
        "### taxonomy 指派 vs 觀測矛盾（reviewer 複核重點）",
        "",
        _table(
            report["contradictions"],
            [("action_name", "action_name"), ("outcome_family", "outcome_family"),
             ("islands", "islands"), ("矛盾訊號", "flags")],
        ) if report["contradictions"] else "_無強矛盾（所有登錄 action 的觀測效果與指派一致）。_",
        "",
        "### 未登錄 action 抽樣（fail-closed）",
        "",
        _table(
            report["classification"]["unknown_samples"],
            [("年", "year"), ("kind", "kind_code"), ("場", "game_sno"),
             ("局", "inning_seq"), ("action", "term_action"), ("內容", "term_content")],
        ),
        "",
        "## 紅燈案例：現行近似鍵 vs island truth",
        "",
        "### (A) 同局同打者二度上場（近似鍵合併 → 應為 2+ pa）",
        "",
        f"- 全史命中 scope：{rl['repeat_batter']['total_scopes']}；"
        f"單 scope 最多 island：{rl['repeat_batter']['max_islands']}。",
        f"- 現行 `(inning,pitcher,hitter)` 逐球三鍵在這些 scope 會把 {rl['repeat_batter']['max_islands']} "
        "個不同 PA 的球綁到同一鍵。",
        "",
        _table(
            rl["repeat_batter"]["samples"],
            [("年", "year"), ("kind", "kind_code"), ("場", "game_sno"),
             ("局", "inning_seq"), ("半", "vht"), ("打者", "hitter_acnt"),
             ("island 數", "islands")],
        ),
        "",
        "### (B) 打席中換投（近似三鍵拆單一 PA）",
        "",
        f"- 全史命中 PA：{rl['pitching_change']['total_pas']}；"
        f"單一 PA 最多投手數：{rl['pitching_change']['max_pitchers']}。",
        "- `pitch_cnt` 為**逐投手**累加，換投即歸零；`(inning,pitcher,hitter)` 會把一個保送/"
        "打席拆成 2–3 段，且逐球序不可用單一 pitch_cnt 還原。",
        "",
        _table(
            rl["pitching_change"]["samples"],
            [("年", "year"), ("kind", "kind_code"), ("場", "game_sno"),
             ("局", "inning_seq"), ("半", "vht"), ("打者", "hitter_acnt"),
             ("投手數", "pitchers")],
        ),
        "",
        "### (C) 抽樣場次：island truth vs 三套近似鍵 PA 數",
        "",
        "canonical_pa＝本 taxonomy 認定的完成 PA；其餘為現行近似鍵。差值即誤配證據。",
        "",
        _table(
            rl["legacy_delta"],
            [("scope", "scope"), ("canonical_pa", "canonical_pa"),
             ("run_dist", "run_dist_pa"), ("winprob", "winprob_pa"),
             ("frontend", "frontend_pa"), ("歧義逐球鍵", "ambiguous_pitch_keys"),
             ("歧義逐球 PA", "ambiguous_pitch_pas")],
        ),
        "",
        "### (D) pitch_cnt 非逐列唯一（逐球映射候選多對一）",
        "",
        f"- 共 {rl['pitch_multiplicity']['total_pitch_keys']} 個 "
        "`(year,kind,game,pitcher,pitch_cnt)` 鍵，其中 "
        f"{rl['pitch_multiplicity']['multi_row_pitch_keys']} 個對到 2+ livelog 列"
        "（牽制/暫停/暴投共用前一 pitch_cnt）。builder 映射逐球時須挑「真正投球列」，"
        "不可假設一個 pitch_cnt 對一列。",
        "",
        _table(
            rl["pitch_multiplicity"]["distribution"],
            [("每 pitch_cnt 列數", "rows_per_pitch"), ("pitch 鍵數", "pitch_keys")],
        ),
        "",
        "## Checkpoint",
        "",
        "- taxonomy 規範與 fail-closed 行為見 design doc；本證據供跨模型家族/人工 reviewer "
        "以原始事件複核後，才可解除 EXPAND1 的 transition schema 前置。",
        "- 未登錄 action、truncated fragment、歧義逐球鍵一律 fail closed；builder 不得以名稱猜測補值。",
        "",
    ]
    return "\n".join(parts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2018)
    parser.add_argument("--to-year", type=int, default=date.today().year)
    parser.add_argument("--kind", action="append", dest="kinds")
    parser.add_argument("--json", type=Path, help="版本化 taxonomy JSON 輸出路徑")
    parser.add_argument("--output", type=Path, help="Markdown 證據報告輸出路徑")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    kinds = args.kinds or ["A", "C", "D", "E"]
    report = collect(args.from_year, args.to_year, kinds)
    if args.json:
        args.json.write_text(
            json.dumps(build_taxonomy_json(report), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    text = render(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
