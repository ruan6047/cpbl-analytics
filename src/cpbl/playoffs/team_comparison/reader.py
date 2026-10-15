"""``playoffs-comparison/v1``：第 2 區三範圍比較的唯讀組裝（#287 WP3）。

GET 在**單一 REPEATABLE READ READ ONLY 交易**內只做四類查詢（PLAN r2 §5.2，A15）：

1. S02 ``read_series_inputs``／``compute_series_context``：系列隊伍與 ``counted_game_keys``（G09，不自算）。
2. current 指標＋build 中繼資料＋該年 ``season`` 列＋兩隊 ``head_to_head`` 列。
3. 該年已完成 A 場清單（只讀 games）重算 ``games_fingerprint`` 判斷是否待更新。
4. 本系列 counted 場次的 E／C gamelog（``game_sno = ANY(...)`` 一次批次）。

⛔ 不讀 A gamelog、⛔ 不寫、⛔ 不呼叫 builder、⛔ 無行程內快取；current 不存在 ⇒ ``summary_missing``，
⛔ 不回退全季重建。三 scope 各自 ``status``，一個缺漏不連坐另兩個。
路由與外層封套屬 S04 整合窗口（WP6），本模組只提供組裝函式。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from cpbl import postseason_contract as pc
from cpbl.completion import completed_games_sql_with_evidence
from cpbl.models import team_style as ts
from cpbl.playoffs.team_comparison import core
from cpbl.playoffs.team_comparison.builder import TABLES_EXIST_SQL

CONTRACT = "playoffs-comparison/v1"

#: 球風軸語意（判定沿球隊頁 ``cpbl.api.team_style.AXIS_SEMANTICS``；此處逐字同值，測試釘住一致）。
AXIS_SEMANTICS: dict[str, str] = {
    "speed": "usable", "smallball": "usable", "power": "usable",
    "discipline": "cross_season_stable", "starter_ip": "current_season_only",
    "pitch_k": "current_season_only", "defense": "numbers_only",
}

CURRENT_SQL = (
    "SELECT c.build_id, c.promoted_at, c.pending_source_hash, c.pending_since, "
    "b.builder_version, b.source_hash, b.games_fingerprint, b.built_at, b.completed_games "
    "FROM cpbl.team_comparison_current c JOIN cpbl.team_comparison_build b USING (build_id) "
    "WHERE c.year = %s AND c.kind_code = 'A'"
)
ROWS_SQL = (
    "SELECT " + ", ".join(core.ROW_COLUMNS) + " FROM cpbl.team_comparison_row "
    "WHERE build_id = %s AND (scope = 'season' OR (scope = 'head_to_head' "
    "AND team_code = ANY(%s) AND opponent_code = ANY(%s)))"
)
GAMES_A_SQL = (
    "SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.home_team_code, g.away_team_code, "
    "g.home_score, g.away_score FROM cpbl.games g "
    f"WHERE g.year = %s AND g.kind_code = 'A' AND {completed_games_sql_with_evidence('g')}"
)
SERIES_BAT_SQL = (
    "SELECT year, kind_code, game_sno, " + ", ".join(core.BAT_SOURCE_COLUMNS)
    + " FROM cpbl.batting_gamelog WHERE year = %s AND kind_code = %s AND game_sno = ANY(%s)"
)
SERIES_PIT_SQL = (
    "SELECT year, kind_code, game_sno, " + ", ".join(core.PIT_SOURCE_COLUMNS)
    + " FROM cpbl.pitching_gamelog WHERE year = %s AND kind_code = %s AND game_sno = ANY(%s)"
)


def _rows(cur, sql: str, params) -> list[dict]:
    cur.execute(sql, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def _iso(v) -> str | None:
    return v.isoformat() if v is not None else None


def _sample(counts: dict) -> dict:
    return {"games": counts.get("games"), "pa": counts.get("bat_pa"),
            "bf": counts.get("pit_bf"), "outs": counts.get("pit_outs")}


def _team_view(counts: dict, reasons: dict, streak: dict | None) -> dict:
    m, m_why = core.metrics(counts, reasons)
    raw, raw_why = core.style_raw(counts, reasons)
    return {
        "counts": {k: counts.get(k) for k in core.COUNT_KEYS},
        "metrics": m,
        "null_reasons": {**reasons, **{f"metric:{k}": v for k, v in m_why.items()},
                         **{f"style:{k}": v for k, v in raw_why.items()}},
        "sample": _sample(counts),
        "streak": streak,
        "_raw": raw,
    }


def _row_view(row: dict) -> dict:
    streak = ({"result": row["streak_result"], "len": row["streak_len"], "through": row["streak_through"]}
              if row["streak_result"] else None)
    return _team_view({k: row[k] for k in core.COUNT_KEYS}, row["null_reasons"] or {}, streak)


def _style_block(raw: dict, *, season_z: dict | None, league: dict[str, float | None]) -> dict:
    """D2：全年 A 帶季內 z＋排名；對戰／本系列只帶原始值＋同年聯盟平均參考（無排名）。"""
    out = {}
    for axis in ts.AXES:
        comps = core.AXIS_COMPONENTS[axis]
        entry = {"raw": {c: raw.get(c) for c in comps},
                 "league_raw_mean": {c: league.get(c) for c in comps}}
        if season_z is not None:
            entry["z"] = season_z[axis]["z"]
            entry["rank"] = season_z[axis]["rank"]
        out[axis] = entry
    return out


def _scales(season_views: dict[str, dict], scope_views: dict[str, dict]) -> dict:
    return {k: core.shared_scale([v["metrics"][k] for v in season_views.values()],
                                 [v["metrics"][k] for v in scope_views.values()])
            for k in core.METRIC_KEYS}


def _finish(views: dict[str, dict]) -> dict[str, dict]:
    for v in views.values():
        v.pop("_raw", None)
    return views


def build_payload(cur, year: int, kind: str, *, now: datetime) -> dict:
    """在呼叫端已開好的 REPEATABLE READ READ ONLY 交易內組裝（測試可傳記錄查詢的 cursor）。"""
    if kind not in pc.POSTSEASON_KINDS:
        raise ValueError(f"kind 必須是 {pc.POSTSEASON_KINDS}")
    ctx = pc.compute_series_context(pc.read_series_inputs(cur, year, now=now), now=now)
    series = ctx["series"][kind]
    teams = [t for t in series["series_id"]["teams"] if t]
    both_known = series["participants_status"] == "known" and len(teams) == 2

    # ---- 1) 全年 A／兩隊 A 對戰：current 指標下的摘要列（不碰 A gamelog）
    cur.execute(TABLES_EXIST_SQL)
    tables = bool(cur.fetchone()[0])
    meta = None
    if tables:
        found = _rows(cur, CURRENT_SQL, (year,))
        meta = found[0] if found else None
    season_scope: dict = {"status": "summary_missing", "source": None, "teams": {}, "scales": {},
                          "league": None}
    h2h_scope: dict = {"status": "summary_missing", "games": None, "teams": {}, "scales": {}}
    season_views: dict[str, dict] = {}
    league_raw: dict[str, float | None] = {}
    if meta:
        rows = _rows(cur, ROWS_SQL, (meta["build_id"], teams, teams))
        games_now = [core.GameRow((int(r["year"]), r["kind_code"], int(r["game_sno"])), r["game_date"],
                                  r["home_team_code"], r["away_team_code"], r["home_score"], r["away_score"])
                     for r in _rows(cur, GAMES_A_SQL, (year,))]
        fp_now = core.games_fingerprint(year, games_now)
        stale = fp_now != meta["games_fingerprint"] or meta["pending_since"] is not None
        status = "stale" if stale else "available"
        source = {
            "build_id": str(meta["build_id"]), "builder_version": meta["builder_version"],
            "source_hash": meta["source_hash"], "games_fingerprint": meta["games_fingerprint"],
            "built_at": _iso(meta["built_at"]), "promoted_at": _iso(meta["promoted_at"]),
            "pending_since": _iso(meta["pending_since"]), "completed_games": meta["completed_games"],
            "stale_reason": (None if not stale else "pending_rebuild" if meta["pending_since"] is not None
                             else "games_changed"),
        }
        season_views = {r["team_code"]: _row_view(r) for r in rows if r["scope"] == "season"}
        raw_by_team = {t: v["_raw"] for t, v in season_views.items()}
        z = core.season_style(raw_by_team)
        league_raw = {c: core.league_mean(raw_by_team, c) for c in core.STYLE_INPUTS}
        league = {
            "n_teams": len(season_views),
            "style_raw_mean": league_raw,
            "metrics_mean": {k: (None if any(v["metrics"][k] is None for v in season_views.values())
                                 or not season_views
                                 else sum(v["metrics"][k] for v in season_views.values()) / len(season_views))
                             for k in core.METRIC_KEYS},
        }
        picked = {t: season_views[t] for t in teams if t in season_views}
        for t, v in picked.items():
            v["style"] = _style_block(v["_raw"], season_z=z[t] if z else None, league=league_raw)
        season_scope = {"status": status, "source": source, "label": "例行賽結束時",
                        "teams": _finish({t: dict(v) for t, v in picked.items()}),
                        "scales": _scales(season_views, picked), "league": league}
        if both_known:
            h2h = {r["team_code"]: _row_view(r) for r in rows
                   if r["scope"] == "head_to_head" and r["team_code"] in teams and r["opponent_code"] in teams}
            if len(h2h) == 2:
                for v in h2h.values():
                    v["style"] = _style_block(v["_raw"], season_z=None, league=league_raw)
                h2h_scope = {"status": status, "games": h2h[teams[0]]["counts"]["games"],
                             "teams": _finish(h2h), "scales": _scales(season_views, h2h)}
            else:
                h2h_scope = {"status": "summary_missing", "games": None, "teams": {}, "scales": {}}
    if not both_known:
        h2h_scope = {"status": "participants_pending", "games": None, "teams": {}, "scales": {}}

    # ---- 2) 本系列：S02 counted 場次＋E/C gamelog 一次批次
    series_scope = _series_scope(cur, year, kind, ctx, teams, both_known, season_views, league_raw)

    return {
        "contract": CONTRACT,
        "series_id": series["series_id"],
        "participants_status": series["participants_status"],
        "context_version": ctx["context_version"],
        "as_of": now.isoformat(),
        "metric_defs": [dict(d) for d in core.METRIC_DEFS],
        "style_axes": [{"key": a, "label": ts.AXIS_LABELS[a], "semantics": AXIS_SEMANTICS[a],
                        "components": list(core.AXIS_COMPONENTS[a])} for a in ts.AXES],
        "scopes": {"season_a": season_scope, "head_to_head_a": h2h_scope, "series": series_scope},
    }


def _series_scope(cur, year: int, kind: str, ctx: dict, teams: list[str], both_known: bool,
                  season_views: dict[str, dict], league_raw: dict) -> dict:
    if not both_known:
        return {"status": "participants_pending", "label": "本系列", "expected_game_keys": [],
                "covered_game_keys": [], "missing_game_keys": [], "teams": {}, "scales": {}}
    counted = [g for g in ctx["games"] if g["game_key"]["kind_code"] == kind and g["counted_for_wins"]]
    games = [core.GameRow((year, kind, int(g["official_game_sno"])),
                          datetime.fromisoformat(g["game_date"]).date(),
                          g["home_team_code"], g["away_team_code"], g["home_score"], g["away_score"])
             for g in counted]
    expected = [core.key_str(g.key) for g in core.sort_games(games)]
    if not games:
        return {"status": "not_started", "label": "本系列", "expected_game_keys": [],
                "covered_game_keys": [], "missing_game_keys": [], "teams": {}, "scales": {}}
    snos = [g.key[2] for g in games]
    bat = _rows(cur, SERIES_BAT_SQL, (year, kind, snos))
    pit = _rows(cur, SERIES_PIT_SQL, (year, kind, snos))
    index = core.box_index(games, bat, pit)
    covered = [g.key for g in core.sort_games(games)
               if not any(r.startswith("box_missing:")
                          for t in (g.home, g.away) for rs in index[(g.key, t)][1].values() for r in rs)]
    views = {}
    for t in teams:
        tot = core.aggregate(t, games, index, box_games=covered)
        views[t] = _team_view(tot.counts, tot.reasons, core.trailing_streak(tot.sequence))
        views[t]["style"] = _style_block(views[t]["_raw"], season_z=None, league=league_raw)
    covered_s = [core.key_str(k) for k in covered]
    return {
        "status": "available" if len(covered) == len(games) else "pending_source",
        "label": "本系列",
        "expected_game_keys": expected,
        "covered_game_keys": covered_s,
        "missing_game_keys": [k for k in expected if k not in covered_s],
        "teams": _finish(views),
        "scales": _scales(season_views, views) if season_views else
        {k: core.shared_scale([], [v["metrics"][k] for v in views.values()]) for k in core.METRIC_KEYS},
    }


def comparison_payload(year: int, kind: str, *, now: datetime | None = None,
                       connect: Callable | None = None) -> dict:
    """IO 入口：單一 REPEATABLE READ READ ONLY 交易讀完全部來源。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(pc.READ_ONLY_TXN)
            return build_payload(cur, year, kind, now=now)
