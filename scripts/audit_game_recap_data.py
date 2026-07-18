"""GAME-RECAP-DATA1：賽事復盤資料覆蓋與 canonical 打席契約唯讀稽核。"""

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

Event = dict[str, Any]


@dataclass(frozen=True)
class PitchLinkageRisks:
    unique_keys: int
    ambiguous_keys: int
    ambiguous_plate_appearances: int


@dataclass(frozen=True)
class GameEventAudit:
    box_pa: int
    run_dist_pa: int
    winprob_pa: int
    frontend_pa: int
    blank_action_rows: int
    change_rows: int
    pitching_change_rows: int
    repeated_matchup_keys: int
    repeated_matchup_pas: int


def _usable(event: Event) -> bool:
    return not event.get("is_change_player") and bool(event.get("hitter_acnt"))


def legacy_pa_starts(events: list[Event]) -> dict[str, list[str]]:
    """重現三套現行近似分組；回傳各自認定的打席首事件。

    run_dist 在每半局以 (batting_order, hitter) 去重；WP 再加 inning/half，
    實際效果相同但 scope 不同；buildMoments 的起點直接沿用 WP points。
    """
    run_dist: list[str] = []
    winprob: list[str] = []
    frontend: list[str] = []
    run_seen: dict[tuple[Any, str], set[tuple[Any, Any]]] = {}
    wp_seen: set[tuple[Any, str, Any, Any]] = set()
    half_order = list(
        dict.fromkeys(
            (event.get("inning_seq"), str(event.get("visiting_home_type"))) for event in events
        )
    )
    last_half = half_order[-1] if half_order else None

    for event in events:
        half = (event.get("inning_seq"), str(event.get("visiting_home_type")))
        if not _usable(event):
            continue

        event_no = str(event["main_event_no"])
        hitter = event.get("hitter_acnt")
        compact_key = (event.get("batting_order"), hitter)
        if half != last_half:
            half_seen = run_seen.setdefault(half, set())
            if compact_key not in half_seen:
                half_seen.add(compact_key)
                run_dist.append(event_no)

        wp_key = (*half, *compact_key)
        if wp_key not in wp_seen:
            wp_seen.add(wp_key)
            winprob.append(event_no)
            frontend.append(event_no)

    return {"run_dist": run_dist, "winprob": winprob, "frontend": frontend}


def frontend_moment_groups(events: list[Event]) -> list[tuple[str, str]]:
    """重現 buildMoments：起點沿用 WP，向後略過換人列並掃到最後一筆同打者事件。"""
    starts = legacy_pa_starts(events)["winprob"]
    by_no = {str(event["main_event_no"]): index for index, event in enumerate(events)}
    groups: list[tuple[str, str]] = []
    for start_no in starts:
        start = by_no[start_no]
        hitter = events[start].get("hitter_acnt")
        last = start
        for index in range(start, len(events)):
            event = events[index]
            if event.get("is_change_player"):
                continue
            if str(event.get("hitter_acnt")) != str(hitter):
                break
            last = index
        groups.append((start_no, str(events[last]["main_event_no"])))
    return groups


def _sequential_candidate_starts(events: list[Event]) -> list[Event]:
    """逐球歧義偵測用候選島；不是 canonical，也不是 buildMoments 起點。"""
    output: list[Event] = []
    previous_half: tuple[Any, str] | None = None
    previous_hitter: Any = None
    for event in events:
        half = (event.get("inning_seq"), str(event.get("visiting_home_type")))
        if half != previous_half:
            previous_half = half
            previous_hitter = None
        if not _usable(event):
            previous_hitter = None
            continue
        if event.get("hitter_acnt") != previous_hitter:
            output.append(event)
        previous_hitter = event.get("hitter_acnt")
    return output


def pitch_linkage_risks(pa_starts: list[Event]) -> PitchLinkageRisks:
    """量化現行 (inning, pitcher, hitter) 逐球鍵可指向幾個近似打席。"""
    keys = Counter(
        (
            event.get("inning_seq"),
            event.get("pitcher_acnt"),
            event.get("hitter_acnt"),
        )
        for event in pa_starts
        if event.get("pitcher_acnt") and event.get("hitter_acnt")
    )
    return PitchLinkageRisks(
        unique_keys=sum(count == 1 for count in keys.values()),
        ambiguous_keys=sum(count > 1 for count in keys.values()),
        ambiguous_plate_appearances=sum(count for count in keys.values() if count > 1),
    )


def classify_tracking_availability(
    *,
    game_started: bool,
    game_pitch_count: int,
    scope_tracked_games: int,
    venue_tracked_games: int,
) -> str:
    """只依觀測證據分類，不把「未觀測到」冒充官方設備清冊。"""
    if not game_started:
        return "not_expected_yet"
    if game_pitch_count > 0:
        return "available"
    if scope_tracked_games == 0:
        return "source_not_collected"
    if venue_tracked_games > 0:
        return "expected_missing"
    return "equipment_unobserved"


def audit_game_events(events: list[Event], *, box_pa: int) -> GameEventAudit:
    """彙整單場三套近似 PA 分母與資料風險，不宣稱任何一套是 canonical。"""
    starts = legacy_pa_starts(events)
    linkage = pitch_linkage_risks(_sequential_candidate_starts(events))
    usable = [event for event in events if _usable(event)]
    change_rows = [event for event in events if event.get("is_change_player")]
    return GameEventAudit(
        box_pa=box_pa,
        run_dist_pa=len(starts["run_dist"]),
        winprob_pa=len(starts["winprob"]),
        frontend_pa=len(frontend_moment_groups(events)),
        blank_action_rows=sum(not str(event.get("action_name") or "").strip() for event in usable),
        change_rows=len(change_rows),
        pitching_change_rows=sum("投手" in str(event.get("content") or "") for event in change_rows),
        repeated_matchup_keys=linkage.ambiguous_keys,
        repeated_matchup_pas=linkage.ambiguous_plate_appearances,
    )


def _coverage_rows(cur: Any, from_year: int, to_year: int, kinds: list[str]) -> list[Event]:
    cur.execute(
        """
        WITH game_dim AS (
            SELECT year, kind_code, game_sno, max(game_date) AS game_date,
                   max(venue) AS venue, max(present_status) AS present_status,
                   max(home_score) AS home_score, max(away_score) AS away_score,
                   max(delay_kind) AS delay_kind, min(orig_date) AS orig_date
            FROM cpbl.games
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
            GROUP BY year, kind_code, game_sno
        ), scoreboard AS (
            SELECT year, kind_code, game_sno, count(*) AS scoreboard_rows,
                   max(inning_seq) AS scoreboard_max_inning
            FROM cpbl.game_scoreboard
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
            GROUP BY year, kind_code, game_sno
        ), livelog AS (
            SELECT year, kind_code, game_sno, count(*) AS livelog_rows,
                   max(inning_seq) AS livelog_max_inning
            FROM cpbl.game_livelog
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
            GROUP BY year, kind_code, game_sno
        ), last_score AS (
            SELECT DISTINCT ON (year, kind_code, game_sno)
                   year, kind_code, game_sno, inning_seq AS last_score_inning,
                   visiting_home_type AS last_score_half
            FROM cpbl.game_livelog
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s) AND is_score
            ORDER BY year, kind_code, game_sno,
                     CASE WHEN main_event_no ~ '^\\d+$' THEN main_event_no::bigint END DESC NULLS LAST,
                     main_event_no DESC
        ), box AS (
            SELECT year, kind_code, game_sno, count(*) AS box_rows,
                   coalesce(sum(plate_appearances), 0) AS box_pa
            FROM cpbl.batting_gamelog
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
            GROUP BY year, kind_code, game_sno
        ), tracking AS (
            SELECT year, kind_code, game_sno, count(*) AS tracking_pitches
            FROM cpbl.pitch_tracking
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
            GROUP BY year, kind_code, game_sno
        )
        SELECT g.*, coalesce(s.scoreboard_rows, 0) AS scoreboard_rows,
               s.scoreboard_max_inning, coalesce(l.livelog_rows, 0) AS livelog_rows,
               l.livelog_max_inning, ls.last_score_inning, ls.last_score_half,
               coalesce(b.box_rows, 0) AS box_rows,
               coalesce(b.box_pa, 0) AS box_pa,
               coalesce(t.tracking_pitches, 0) AS tracking_pitches
        FROM game_dim g
        LEFT JOIN scoreboard s USING (year, kind_code, game_sno)
        LEFT JOIN livelog l USING (year, kind_code, game_sno)
        LEFT JOIN last_score ls USING (year, kind_code, game_sno)
        LEFT JOIN box b USING (year, kind_code, game_sno)
        LEFT JOIN tracking t USING (year, kind_code, game_sno)
        ORDER BY g.year, g.kind_code, g.game_sno
        """,
        (from_year, to_year, kinds) * 6,
    )
    return list(cur.fetchall())


def _event_audits(
    c: Any,
    from_year: int,
    to_year: int,
    kinds: list[str],
    box_pa: dict[tuple[int, str, int], int],
) -> tuple[dict[tuple[int, str, int], GameEventAudit], dict[tuple[int, str, int], Counter]]:
    audits: dict[tuple[int, str, int], GameEventAudit] = {}
    linkage_keys: dict[tuple[int, str, int], Counter] = {}
    query = """
        SELECT year, kind_code, game_sno, main_event_no, inning_seq,
               visiting_home_type, batting_order, out_cnt, ball_cnt, strike_cnt,
               pitch_cnt, content, action_name, batting_action_name, hitter_acnt,
               pitcher_acnt, first_base, second_base, third_base, is_score,
               is_change_player, is_special_event, visiting_score, home_score
        FROM cpbl.game_livelog
        WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
        ORDER BY year, kind_code, game_sno,
                 CASE WHEN main_event_no ~ '^\\d+$' THEN main_event_no::bigint END NULLS LAST,
                 main_event_no
    """
    cur = c.cursor(name="game_recap_data1_events", row_factory=dict_row)
    cur.itersize = 10_000
    cur.execute(query, (from_year, to_year, kinds))
    current_key: tuple[int, str, int] | None = None
    events: list[Event] = []

    def flush() -> None:
        if current_key is None:
            return
        audit = audit_game_events(events, box_pa=box_pa.get(current_key, 0))
        audits[current_key] = audit
        linkage_keys[current_key] = Counter(
            (
                event.get("inning_seq"),
                event.get("pitcher_acnt"),
                event.get("hitter_acnt"),
            )
            for event in _sequential_candidate_starts(events)
            if event.get("pitcher_acnt") and event.get("hitter_acnt")
        )

    for event in cur:
        key = (event["year"], event["kind_code"], event["game_sno"])
        if key != current_key:
            flush()
            current_key = key
            events = []
        events.append(event)
    flush()
    cur.close()
    return audits, linkage_keys


def _pct(numerator: int, denominator: int) -> str:
    return "—" if denominator == 0 else f"{numerator / denominator:.1%}"


def _is_started(row: Event) -> bool:
    score = int(row.get("home_score") or 0) + int(row.get("away_score") or 0)
    return score > 0 or int(row.get("box_pa") or 0) > 0 or int(row.get("livelog_rows") or 0) > 0


def _aggregate_coverage(rows: list[Event], keys: tuple[str, ...]) -> list[Event]:
    groups: dict[tuple[Any, ...], list[Event]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(key) for key in keys)].append(row)
    output: list[Event] = []
    for group_key, games in sorted(groups.items(), key=lambda item: tuple(str(v) for v in item[0])):
        started = [game for game in games if _is_started(game)]
        result = dict(zip(keys, group_key, strict=True))
        result.update(
            games=len(games),
            started=len(started),
            scoreboard=sum(int(game["scoreboard_rows"]) > 0 for game in started),
            livelog=sum(int(game["livelog_rows"]) > 0 for game in started),
            box=sum(int(game["box_rows"]) > 0 for game in started),
            tracking=sum(int(game["tracking_pitches"]) > 0 for game in started),
        )
        result["scoreboard_pct"] = _pct(result["scoreboard"], result["started"])
        result["livelog_pct"] = _pct(result["livelog"], result["started"])
        result["box_pct"] = _pct(result["box"], result["started"])
        result["tracking_pct"] = _pct(result["tracking"], result["started"])
        output.append(result)
    return output


def _aggregate_pa(
    coverage: list[Event], audits: dict[tuple[int, str, int], GameEventAudit]
) -> list[Event]:
    groups: dict[tuple[int, str], list[tuple[Event, GameEventAudit]]] = defaultdict(list)
    for row in coverage:
        key = (row["year"], row["kind_code"], row["game_sno"])
        if key in audits:
            groups[(row["year"], row["kind_code"])].append((row, audits[key]))
    output: list[Event] = []
    for (year, kind), games in sorted(groups.items()):
        box_pa = sum(audit.box_pa for _, audit in games)
        run_pa = sum(audit.run_dist_pa for _, audit in games)
        wp_pa = sum(audit.winprob_pa for _, audit in games)
        frontend_pa = sum(audit.frontend_pa for _, audit in games)
        output.append(
            {
                "year": year,
                "kind_code": kind,
                "games": len(games),
                "box_pa": box_pa,
                "run_dist_pa": run_pa,
                "winprob_pa": wp_pa,
                "frontend_pa": frontend_pa,
                "run_delta": run_pa - box_pa,
                "wp_delta": wp_pa - box_pa,
                "frontend_delta": frontend_pa - box_pa,
                "exact_box_games": sum(audit.frontend_pa == audit.box_pa for _, audit in games),
                "blank_action_rows": sum(audit.blank_action_rows for _, audit in games),
                "change_rows": sum(audit.change_rows for _, audit in games),
                "pitching_change_rows": sum(audit.pitching_change_rows for _, audit in games),
                "repeated_matchup_keys": sum(audit.repeated_matchup_keys for _, audit in games),
            }
        )
    return output


def _tracking_linkage(
    cur: Any,
    from_year: int,
    to_year: int,
    kinds: list[str],
    linkage_keys: dict[tuple[int, str, int], Counter],
) -> Event:
    cur.execute(
        """
        SELECT year, kind_code, game_sno, inning_seq, pitcher_acnt, hitter_acnt,
               count(*) AS pitches
        FROM cpbl.pitch_tracking
        WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
        GROUP BY year, kind_code, game_sno, inning_seq, pitcher_acnt, hitter_acnt
        """,
        (from_year, to_year, kinds),
    )
    result: Event = {
        "keys": 0,
        "pitches": 0,
        "unique_keys": 0,
        "unique_pitches": 0,
        "ambiguous_keys": 0,
        "ambiguous_pitches": 0,
        "unmatched_keys": 0,
        "unmatched_pitches": 0,
    }
    samples: list[Event] = []
    for row in cur.fetchall():
        game_key = (row["year"], row["kind_code"], row["game_sno"])
        pitch_key = (row["inning_seq"], row["pitcher_acnt"], row["hitter_acnt"])
        candidates = linkage_keys.get(game_key, Counter()).get(pitch_key, 0)
        pitches = int(row["pitches"])
        result["keys"] += 1
        result["pitches"] += pitches
        if candidates == 1:
            result["unique_keys"] += 1
            result["unique_pitches"] += pitches
        elif candidates > 1:
            result["ambiguous_keys"] += 1
            result["ambiguous_pitches"] += pitches
        else:
            result["unmatched_keys"] += 1
            result["unmatched_pitches"] += pitches
        if candidates != 1 and len(samples) < 30:
            samples.append({**row, "candidate_pas": candidates})
    result["samples"] = samples
    return result


def collect_audit(from_year: int, to_year: int, kinds: list[str], as_of: date) -> Event:
    started_at = time.perf_counter()
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        coverage = _coverage_rows(cur, from_year, to_year, kinds)
        box_pa = {
            (row["year"], row["kind_code"], row["game_sno"]): int(row["box_pa"])
            for row in coverage
        }
        audits, linkage_keys = _event_audits(c, from_year, to_year, kinds, box_pa)
        tracking_linkage = _tracking_linkage(
            cur, from_year, to_year, kinds, linkage_keys
        )

        cur.execute(
            """
            SELECT coalesce(nullif(action_name, ''), '(blank)') AS action_name, count(*) AS rows
            FROM cpbl.game_livelog
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
              AND NOT coalesce(is_change_player, false) AND hitter_acnt IS NOT NULL
            GROUP BY 1 ORDER BY count(*) DESC, 1
            """,
            (from_year, to_year, kinds),
        )
        actions = list(cur.fetchall())
        cur.execute(
            """
            SELECT year, kind_code, game_sno, main_event_no, inning_seq,
                   visiting_home_type, hitter_acnt, pitcher_acnt, content
            FROM cpbl.game_livelog
            WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
              AND NOT coalesce(is_change_player, false) AND hitter_acnt IS NOT NULL
              AND nullif(trim(action_name), '') IS NULL
            ORDER BY year DESC, kind_code, game_sno, main_event_no
            LIMIT %s
            """,
            (from_year, to_year, kinds, 30),
        )
        blank_action_samples = list(cur.fetchall())
        cur.execute(
            """
            SELECT refreshed_at, scope, from_date, to_date, games_total,
                   games_completed, ok, note, detail
            FROM cpbl.refresh_log ORDER BY refreshed_at DESC LIMIT %s
            """,
            (20,),
        )
        refresh_rows = list(cur.fetchall())
        cur.execute(
            """
            SELECT relname AS table_name, pg_total_relation_size(c.oid) AS bytes
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND relname = ANY(%s)
            ORDER BY relname
            """,
            ("cpbl", ["games", "game_scoreboard", "game_livelog", "pitch_tracking"]),
        )
        relation_sizes = list(cur.fetchall())

    venue_tracking_games = Counter(
        (row["year"], row["kind_code"], row.get("venue"))
        for row in coverage
        if _is_started(row) and int(row["tracking_pitches"]) > 0
    )
    scope_tracking_games = Counter(
        (row["year"], row["kind_code"])
        for row in coverage
        if _is_started(row) and int(row["tracking_pitches"]) > 0
    )
    tracking_classes = Counter()
    for row in coverage:
        observed = venue_tracking_games[(row["year"], row["kind_code"], row.get("venue"))]
        classification = classify_tracking_availability(
            game_started=_is_started(row),
            game_pitch_count=int(row["tracking_pitches"]),
            scope_tracked_games=scope_tracking_games[(row["year"], row["kind_code"])],
            venue_tracked_games=observed,
        )
        row["tracking_classification"] = classification
        tracking_classes[classification] += 1

    mismatch_samples: list[Event] = []
    risk_samples: list[Event] = []
    for key, audit in audits.items():
        sample = {"year": key[0], "kind_code": key[1], "game_sno": key[2], **audit.__dict__}
        if audit.frontend_pa != audit.box_pa and len(mismatch_samples) < 30:
            mismatch_samples.append(sample)
        if (audit.repeated_matchup_keys or audit.pitching_change_rows) and len(risk_samples) < 30:
            risk_samples.append(sample)

    zero_zero = [
        {
            **row,
            "boundary_class": (
                "future_schedule"
                if row.get("game_date") and row["game_date"] > as_of
                else (str(row.get("delay_kind")) if row.get("delay_kind") else "stale_or_unplayed")
            ),
        }
        for row in coverage
        if not _is_started(row)
        and int(row.get("home_score") or 0) == 0
        and int(row.get("away_score") or 0) == 0
    ]
    walkoff = [
        row
        for row in coverage
        if _is_started(row)
        and int(row.get("home_score") or 0) > int(row.get("away_score") or 0)
        and str(row.get("last_score_half")) == "2"
        and int(row.get("last_score_inning") or 0) >= 9
    ]
    extra_inning = [row for row in coverage if int(row.get("livelog_max_inning") or 0) > 9]
    ties = [
        row
        for row in coverage
        if _is_started(row) and row.get("home_score") == row.get("away_score")
    ]
    delayed = [row for row in coverage if row.get("delay_kind")]
    no_tracking = [
        row
        for row in coverage
        if _is_started(row) and row["tracking_classification"] != "available"
    ]
    normal = [
        row
        for row in coverage
        if _is_started(row)
        and row.get("home_score") != row.get("away_score")
        and int(row.get("livelog_max_inning") or 0) <= 9
        and not row.get("delay_kind")
        and row not in walkoff
    ]
    edge_cases = {
        "normal_completed": normal[:30],
        "zero_zero": zero_zero[:30],
        "walkoff": walkoff[:30],
        "extra_inning": extra_inning[:30],
        "tie": ties[:30],
        "delayed_or_retained": delayed[:30],
        "no_tracking": no_tracking[:30],
        "mismatch": mismatch_samples,
        "grouping_risks": risk_samples,
        "blank_action": blank_action_samples,
    }
    return {
        "parameters": {
            "from_year": from_year,
            "to_year": to_year,
            "kinds": kinds,
            "as_of": as_of,
        },
        "coverage_by_year_kind": _aggregate_coverage(coverage, ("year", "kind_code")),
        "coverage_by_year_kind_venue": _aggregate_coverage(
            coverage, ("year", "kind_code", "venue")
        ),
        "pa_by_year_kind": _aggregate_pa(coverage, audits),
        "source_totals": {
            "scheduled_games": len(coverage),
            "started_games": sum(_is_started(row) for row in coverage),
            "scoreboard_rows": sum(int(row["scoreboard_rows"]) for row in coverage),
            "livelog_rows": sum(int(row["livelog_rows"]) for row in coverage),
            "box_pa": sum(int(row["box_pa"]) for row in coverage),
            "tracking_pitches": sum(int(row["tracking_pitches"]) for row in coverage),
        },
        "present_status_counts": [
            {
                "present_status": status,
                "games": len(rows),
                "started": sum(_is_started(row) for row in rows),
                "zero_zero": sum(
                    int(row.get("home_score") or 0) == 0
                    and int(row.get("away_score") or 0) == 0
                    for row in rows
                ),
            }
            for status, rows in sorted(
                (
                    (status, [row for row in coverage if row.get("present_status") == status])
                    for status in {row.get("present_status") for row in coverage}
                ),
                key=lambda item: str(item[0]),
            )
        ],
        "tracking_classes": dict(tracking_classes),
        "tracking_linkage": tracking_linkage,
        "actions": actions,
        "edge_cases": edge_cases,
        "edge_case_counts": {
            "normal_completed": len(normal),
            "zero_zero": len(zero_zero),
            "walkoff": len(walkoff),
            "extra_inning": len(extra_inning),
            "tie": len(ties),
            "delayed_or_retained": len(delayed),
            "no_tracking": len(no_tracking),
            "mismatch": sum(audit.frontend_pa != audit.box_pa for audit in audits.values()),
            "grouping_risks": sum(
                bool(audit.repeated_matchup_keys or audit.pitching_change_rows)
                for audit in audits.values()
            ),
        },
        "refresh_rows": refresh_rows,
        "relation_sizes": relation_sizes,
        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        "generated_at": datetime.now().astimezone(),
    }


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(rows: list[Event], columns: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_cell(row.get(key)) for _, key in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body]) if body else "_無資料。_"


def _scope_support(rows: list[Event]) -> list[Event]:
    output: list[Event] = []
    for row in rows:
        if row["started"] == 0:
            status = "unsupported"
            reason = "無已開打分母"
        elif row["livelog"] == row["started"] and row["box"] == row["started"]:
            status = "source_available"
            reason = "livelog/box 場次完整；仍不代表 canonical PA 可重建"
        else:
            status = "partial"
            reason = "livelog 或 box 有場次缺漏"
        output.append(
            {
                "scope": f"{row['year']}/{row['kind_code']}",
                "status": status,
                "reason": reason,
            }
        )
    return output


def render_report(report: Event) -> str:
    params = report["parameters"]
    tracking = report["tracking_linkage"]
    edges = report["edge_cases"]
    edge_counts = report.get("edge_case_counts", {})
    edge_index: list[Event] = []
    for case in (
        "normal_completed",
        "zero_zero",
        "walkoff",
        "extra_inning",
        "tie",
        "delayed_or_retained",
        "no_tracking",
    ):
        edge_index.extend({"case": case, **row} for row in edges.get(case, [])[:10])
    relation_rows = [
        {**row, "size_mib": f"{int(row['bytes']) / 1024 / 1024:.2f}"}
        for row in report["relation_sizes"]
    ]
    refresh_rows = [
        {**row, "detail": json.dumps(row.get("detail"), ensure_ascii=False, default=str)}
        for row in report["refresh_rows"]
    ]
    parts = [
        "---",
        'title: "GAME-RECAP-DATA1 賽事復盤資料覆蓋與 canonical 契約稽核"',
        "card_id: GAME-RECAP-DATA1",
        "status: awaiting-independent-review",
        f"date: {params['as_of']}",
        "tags:",
        "  - cpbl",
        "  - data-audit",
        "  - game-recap",
        "---",
        "",
        "# GAME-RECAP-DATA1 稽核結果",
        "",
        "關聯：[[GAME_RECAP_PRODUCT_SPEC]]、[[GAME-RECAP-DATA1]]、[[GAME-RECAP-PA1]]、[[GAME-RECAP-STATUS1]]。",
        "",
        "> [!danger] 結論：canonical PA：NO-GO",
        "> 現有欄位沒有不可變的官方打席識別碼；run distribution、WP API、前端 moment 與逐球三鍵使用不同近似邊界。即使某些 scope 的場次覆蓋率為 100%，仍不能把任一近似分組升格為 canonical。",
        "",
        "## 執行範圍與方法",
        "",
        f"- 範圍：{params['from_year']}–{params['to_year']}，kind={','.join(params['kinds'])}，as-of={params['as_of']}。",
        "- 所有查詢均在 PostgreSQL `READ ONLY` transaction 內執行；year/kind/limit 皆以 psycopg 參數傳入。",
        f"- 全量稽核耗時：{report['elapsed_seconds']} 秒；產生時間：{report['generated_at']}。",
        "- `started` 分母以正比分、box PA 或 livelog 任一實際活動證據判定；`present_status` 不作完成判準。",
        "",
        "重跑：",
        "",
        "```bash",
        "uv run python scripts/audit_game_recap_data.py --from-year "
        f"{params['from_year']} --to-year {params['to_year']} "
        + " ".join(f"--kind {kind}" for kind in params["kinds"])
        + f" --as-of {params['as_of']} --output docs/research/GAME-RECAP-DATA1_RESULTS.md",
        "```",
        "",
        "## 覆蓋矩陣",
        "",
        "### 年 × 賽制",
        "",
        _table(
            report["coverage_by_year_kind"],
            [("年", "year"), ("kind", "kind_code"), ("賽程", "games"), ("已開打", "started"),
             ("scoreboard", "scoreboard_pct"), ("livelog", "livelog_pct"),
             ("box", "box_pct"), ("tracking", "tracking_pct")],
        ),
        "",
        "### 年 × 賽制 × 球場（完整矩陣）",
        "",
        _table(
            report["coverage_by_year_kind_venue"],
            [("年", "year"), ("kind", "kind_code"), ("球場", "venue"), ("賽程", "games"),
             ("已開打", "started"), ("scoreboard", "scoreboard_pct"),
             ("livelog", "livelog_pct"), ("box", "box_pct"), ("tracking", "tracking_pct")],
        ),
        "",
        "### TrackMan availability 分類",
        "",
        "`source_not_collected` 表示該 year/kind 完全沒有逐球 ingest；只有 scope 已收集逐球後，球場從未觀測到 tracking 才列 `equipment_unobserved`，曾有 tracking 的同球場缺資料才列 `expected_missing`。這仍不是官方設備清冊。",
        "",
        _table(
            [{"classification": key, "games": value} for key, value in sorted(report["tracking_classes"].items())],
            [("分類", "classification"), ("場次", "games")],
        ),
        "",
        "## PA 分母對帳與三套近似分組",
        "",
        _table(
            report["pa_by_year_kind"],
            [("年", "year"), ("kind", "kind_code"), ("場", "games"), ("box PA", "box_pa"),
             ("run_dist", "run_dist_pa"), ("Δbox", "run_delta"), ("WP", "winprob_pa"),
             ("Δbox", "wp_delta"), ("frontend", "frontend_pa"), ("Δbox", "frontend_delta"),
             ("逐場精確相等", "exact_box_games"), ("換人列", "change_rows"),
             ("換投列", "pitching_change_rows"), ("重複三鍵", "repeated_matchup_keys")],
        ),
        "",
        "現行語意：",
        "",
        "1. `build_run_dist()`：排除每場最後半局，再於各半局以 `(batting_order, hitter)` 去重；分母本來就不能與全場 box PA 直接等量，單一半局打線輪轉仍會吞掉第二次打席。",
        "2. WP API：`(inning, half, batting_order, hitter)` 去重，具有同一輪轉缺陷。",
        "3. 前端 `buildMoments()`：起點直接沿用 WP points，再略過換人列向後掃同打者作終點；因此無法補回 WP 已吞掉的打席，代打／缺事件也會改變終點。",
        "4. PlayByPlay 另用連續打者島，而逐球 UI 以 `(inning, pitcher, hitter)` 取球；同局重複對戰會把多個 PA 的球合併。",
        "",
        "### 逐球三鍵實際對應",
        "",
        _table(
            [{
                "pitches": tracking.get("pitches", 0),
                "unique": tracking.get("unique_pitches", 0),
                "ambiguous": tracking.get("ambiguous_pitches", 0),
                "unmatched": tracking.get("unmatched_pitches", 0),
            }],
            [("逐球", "pitches"), ("唯一 PA 候選", "unique"),
             ("多 PA 歧義", "ambiguous"), ("無 PA 候選", "unmatched")],
        ),
        "",
        _table(
            tracking.get("samples", []),
            [("年", "year"), ("kind", "kind_code"), ("場", "game_sno"),
             ("局", "inning_seq"), ("投手", "pitcher_acnt"), ("打者", "hitter_acnt"),
             ("球", "pitches"), ("PA 候選", "candidate_pas")],
        ),
        "",
        "## 邊界案例與未知 action",
        "",
        f"- 一般完賽：{edge_counts.get('normal_completed', len(edges.get('normal_completed', [])))} 場。",
        f"- 0–0／未開打候選：{edge_counts.get('zero_zero', len(edges['zero_zero']))} 場。",
        f"- 再見：{edge_counts.get('walkoff', len(edges.get('walkoff', [])))} 場；延長：{edge_counts.get('extra_inning', len(edges['extra_inning']))} 場；和局：{edge_counts.get('tie', len(edges['tie']))} 場。",
        f"- 延賽／保留：{edge_counts.get('delayed_or_retained', len(edges['delayed_or_retained']))} 場；已開打但無 TrackMan：{edge_counts.get('no_tracking', len(edges.get('no_tracking', [])))} 場。",
        f"- box 與前端近似 PA 不一致：{edge_counts.get('mismatch', len(edges['mismatch']))} 場。",
        f"- 換投或同局重複投打：{edge_counts.get('grouping_risks', len(edges['grouping_risks']))} 場。",
        "",
        "每類最多列 10 場抽查索引：",
        "",
        _table(
            edge_index,
            [("案例", "case"), ("年", "year"), ("kind", "kind_code"), ("場", "game_sno"),
             ("日期", "game_date"), ("球場", "venue"), ("客分", "away_score"),
             ("主分", "home_score"), ("最終局", "livelog_max_inning"),
             ("延賽", "delay_kind"), ("0–0 分類", "boundary_class"),
             ("tracking", "tracking_classification")],
        ),
        "",
        "空白 `action_name` 不能被當成合法終局 action；以下保留原始事件供 PA1 對帳：",
        "",
        _table(
            edges["blank_action"],
            [("年", "year"), ("kind", "kind_code"), ("場", "game_sno"),
             ("事件", "main_event_no"), ("局", "inning_seq"), ("半", "visiting_home_type"),
             ("內容", "content")],
        ),
        "",
        "action 值域（完整）：",
        "",
        _table(report["actions"], [("action_name", "action_name"), ("事件列", "rows")]),
        "",
        "`present_status` 值域與 0–0 交叉證據：",
        "",
        _table(
            report.get("present_status_counts", []),
            [("present_status", "present_status"), ("賽程", "games"),
             ("有活動證據", "started"), ("0–0", "zero_zero")],
        ),
        "",
        "抽樣索引：",
        "",
        _table(
            edges["grouping_risks"],
            [("年", "year"), ("kind", "kind_code"), ("場", "game_sno"),
             ("box PA", "box_pa"), ("frontend PA", "frontend_pa"),
             ("換投列", "pitching_change_rows"), ("重複三鍵", "repeated_matchup_keys")],
        ),
        "",
        "## canonical 資料契約",
        "",
        "PA1 必須由單一 server-side state machine 產出並持久化；最低欄位：",
        "",
        "| 類別 | 欄位 | 規則 |",
        "| --- | --- | --- |",
        "| 身分 | `pa_id`, `year`, `kind_code`, `game_sno`, `pa_index` | `pa_id` 為持久化 opaque ID；不可由目前三套近似鍵臨時計算 |",
        "| 事件 | `start_event_no`, `end_event_no`, `event_nos`, `event_order_version` | 全序、可重跑；晚到事件須 reconciliation，不靜默換 ID |",
        "| 投打 | `batter_start_id`, `credited_batter_id`, `pitcher_start_id`, `pitcher_end_id` | 明確處理代打與打席中換投 |",
        "| 前狀態 | `inning`, `half`, `balls_before`, `strikes_before`, `outs_before`, `bases_before`, `away_score_before`, `home_score_before` | 只取 start 前快照 |",
        "| 後狀態 | `outs_after`, `bases_after`, `away_score_after`, `home_score_after`, `result_action` | 終點無法確認即 fail closed |",
        "| 逐球 | `tracking_availability`, `mapping_reason`, ordered `pitch_id`s | `available / source_not_collected / equipment_unobserved / expected_missing / source_pending / mapping_failed` 分開 |",
        "| 新鮮度 | `source_fetched_at`, `source_version`, `built_at`, `build_source_max_event` | 現有事件表無 row-level freshness，需另卡補 schema/ingest |",
        "",
        "現有欄位可提供 game key、事件序、局／半局、投打者、球數、出局、壘況與比分快照；但無官方 PA ID、不可變 pitch ID、row-level 抓取時間與完成狀態來源，因此不能可靠產生完整契約。需要 schema 時必須另開 expand 卡，本卡不改 migration。",
        "",
        "## 支援邊界與 fail-closed",
        "",
        _table(_scope_support(report["coverage_by_year_kind"]), [("scope", "scope"), ("資料狀態", "status"), ("理由", "reason")]),
        "",
        "- 一軍例行賽、季後賽、二軍只可各自依矩陣宣告 source availability；不得把 A 的 PA/WP 模型套到 C/E/D。",
        "- `home_score + away_score == 0` 一律不是 completed 證據；延賽、保留、未刷新、未開打與可能的 0–0 必須維持不同狀態。",
        "- PA 邊界、事件終點或逐球對應不唯一時，保留事件但 `tracking_availability=mapping_failed`，WP/WPA 回 `null`。",
        "- `source_not_collected`、`equipment_unobserved` 與 `expected_missing` 必須分開；若要顯示「球場無設備」，STATUS1 仍需官方設備來源或明確人工清冊。",
        "",
        "## 物化決策",
        "",
        "**單一推薦：每日 refresh 後批次物化 canonical PA，API 只讀物化結果；逐球內容按 `pa_id` 延遲查詢。**",
        "",
        f"資料量：{report.get('source_totals', {}).get('livelog_rows', 0)} 個 livelog 事件、"
        f"{report.get('source_totals', {}).get('tracking_pitches', 0)} 顆逐球；"
        f"候選物化列數：{report.get('source_totals', {}).get('box_pa', 0)}（以官方 box PA 作容量估計，不代表已能 canonical 重建）。",
        "",
        "| 方案 | 一致性 | 延遲／成本 | 維護 | 結論 |",
        "| --- | --- | --- | --- | --- |",
        "| 每日批次物化 | 所有 WP/API/UI 共用同一 build version，可對帳、可 fail closed | refresh 多一次線性掃描與儲存 | 單一 state machine；可監控與重跑 | 推薦 |",
        "| request-time | 每個 consumer 容易重複近似邏輯；晚到事件造成同場不同結果 | 首請求重算、需 cache invalidation | 三層邏輯與快取失效成本高 | 不採用 |",
        "",
        "目前 `refresh_log` 沒有 phase 起訖或 duration，不能誠實量化增量 build 時間；本次全量稽核耗時僅是研究上界，不可冒充 production refresh SLA。先由 STATUS1／獨立維運卡補可觀測性，再設定批次預算。",
        "",
        "資料表體積：",
        "",
        _table(relation_rows, [("表", "table_name"), ("MiB", "size_mib")]),
        "",
        "最近 refresh evidence（最多 20）：",
        "",
        _table(refresh_rows, [("時間", "refreshed_at"), ("scope", "scope"), ("ok", "ok"),
                              ("games", "games_total"), ("completed", "games_completed"),
                              ("note", "note"), ("detail", "detail")]),
        "",
        "## Checkpoint 決策",
        "",
        "- `GAME-RECAP-PA1`：可進入設計／expand 拆卡，但不得以現有近似鍵直接實作 public canonical PA。",
        "- `GAME-RECAP-STATUS1`：須先定義官方狀態與 row-level freshness 來源；`present_status=1` 不能單獨判定完成。",
        "- WP/WPA 與精確逐球 UI：維持阻塞，直到 PA1 materialized contract 與獨立資料正確性查核通過。",
        "- 本報告仍需跨模型家族或人工 reviewer 重跑抽樣、核對分母後，才可由需求方核可 Checkpoint 1。",
        "",
    ]
    return "\n".join(parts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2018)
    parser.add_argument("--to-year", type=int, default=date.today().year)
    parser.add_argument("--kind", action="append", dest="kinds")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    kinds = args.kinds or ["A", "C", "D", "E"]
    report = collect_audit(args.from_year, args.to_year, kinds, args.as_of)
    text = render_report(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
