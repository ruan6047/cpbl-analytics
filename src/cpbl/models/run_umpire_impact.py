"""ML-UMP1 離線研究 CLI；不寫 production table，也不由 API 觸發。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cpbl.db import conn
from cpbl.models.umpire_impact import (
    DEFAULT_PROXY_ZONE,
    RunValueModel,
    WinProbabilityModel,
    aggregate_teams,
    aggregate_umpires,
    bootstrap_metric_deltas,
    bootstrap_probability_deltas,
    bootstrap_umpire_aggregates,
    score_called_pitch,
    tune_alpha,
)
from cpbl.models.umpire_impact_data import (
    audit_tracking,
    load_called_pitches,
    load_run_observations,
)

ALPHA_CANDIDATES = (1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0)
ZONE_MARGINS_CM = (-5.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 5.0)
MODEL_VERSION = "count_run_v1_alpha250_2018_2025"


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"cannot serialize {type(value)!r}")


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))


def _audit(season: int, kind: str) -> dict[str, Any]:
    with conn() as connection:
        audit = audit_tracking(connection, season, kind)
        scoring = load_called_pitches(connection, season, kind)
    return {
        **audit.to_dict(),
        "scoring_eligible": len(scoring.pitches),
        "post_link_exclusions": scoring.exclusions,
    }


def _validate(kind: str, iterations: int) -> dict[str, Any]:
    with conn() as connection:
        data = load_run_observations(connection, 2018, 2025, kind)
    train = [row for row in data.observations if int(row.game_id[:4]) <= 2023]
    validation = [row for row in data.observations if row.game_id.startswith("2024-")]
    test_run = [row for row in data.observations if row.game_id.startswith("2025-")]
    test_win = [row for row in data.win_observations if row.game_id.startswith("2025-")]
    tuning = tune_alpha(train, validation, candidates=ALPHA_CANDIDATES)
    model = RunValueModel.fit([*train, *validation], alpha=tuning.alpha)
    run_candidate = model.metrics(test_run)
    run_baseline = model.metrics(test_run, parent_only=True)
    run_bootstrap = bootstrap_metric_deltas(
        model, test_run, iterations=iterations, seed=20260715
    )
    win_candidate_model = WinProbabilityModel(model, count_aware=True)
    win_baseline_model = WinProbabilityModel(model, count_aware=False)
    win_candidate = win_candidate_model.metrics(test_win)
    win_baseline = win_baseline_model.metrics(test_win)
    win_bootstrap = bootstrap_probability_deltas(
        win_candidate_model,
        win_baseline_model,
        test_win,
        iterations=iterations,
        seed=20260715,
    )
    wp_gate = (
        win_candidate.brier <= win_baseline.brier
        and win_candidate.log_loss <= win_baseline.log_loss
        and (
            win_bootstrap.brier_delta.high < 0
            or win_bootstrap.log_loss_delta.high < 0
        )
    )
    return {
        "split": {"train": len(train), "validation": len(validation), "test": len(test_run)},
        "alpha": tuning.alpha,
        "validation_by_alpha": tuning.metrics_by_alpha,
        "run_value": {
            "candidate": run_candidate,
            "baseline": run_baseline,
            "bootstrap": run_bootstrap,
            "gate_passed": run_candidate.nll < run_baseline.nll
            and run_candidate.mae <= run_baseline.mae,
        },
        "win_probability": {
            "candidate": win_candidate,
            "baseline": win_baseline,
            "bootstrap": win_bootstrap,
            "gate_passed": wp_gate,
        },
    }


def _sign_flipped(reference: float, alternatives: list[float]) -> bool:
    return any(reference * value < 0 for value in alternatives)


def _score(season: int, kind: str, iterations: int, output: Path) -> dict[str, Any]:
    with conn() as connection:
        historical = load_run_observations(connection, 2018, season - 1, kind)
        scoring = load_called_pitches(connection, season, kind)
        completed_rows = connection.execute(
            "SELECT venue, count(DISTINCT game_sno) FROM cpbl.games "
            "WHERE year=%s AND kind_code=%s AND home_score + away_score > 0 "
            "GROUP BY venue",
            (season, kind),
        ).fetchall()
    model = RunValueModel.fit(historical.observations, alpha=250.0)
    scores = [score_called_pitch(pitch, model) for pitch in scoring.pitches]
    umpire_rows = aggregate_umpires(scores)
    team_rows = aggregate_teams(scores)

    zone_by_umpire: dict[str, dict[str, float]] = {}
    zone_by_team: dict[str, dict[str, dict[str, float]]] = {}
    for margin in ZONE_MARGINS_CM:
        scenario = [
            score_called_pitch(pitch, model, DEFAULT_PROXY_ZONE.shifted(margin))
            for pitch in scoring.pitches
        ]
        for row in aggregate_umpires(scenario):
            zone_by_umpire.setdefault(row.umpire, {})[str(margin)] = row.sum_delta_runs_offense
        for row in aggregate_teams(scenario):
            values = zone_by_team.setdefault(row.team, {"for": {}, "against": {}})
            values["for"][str(margin)] = row.state_value_for
            values["against"][str(margin)] = row.state_value_against

    venue_alternatives: dict[str, list[float]] = {row.umpire: [] for row in umpire_rows}
    team_venue_for: dict[str, list[float]] = {row.team: [] for row in team_rows}
    team_venue_against: dict[str, list[float]] = {row.team: [] for row in team_rows}
    for venue in sorted({pitch.venue for pitch in scoring.pitches}):
        filtered = [score for score in scores if score.pitch.venue != venue]
        scenario = aggregate_umpires(filtered)
        values = {row.umpire: row.sum_delta_runs_offense for row in scenario}
        for umpire in venue_alternatives:
            venue_alternatives[umpire].append(values.get(umpire, 0.0))
        scenario_teams = {row.team: row for row in aggregate_teams(filtered)}
        for team in team_venue_for:
            row = scenario_teams.get(team)
            team_venue_for[team].append(row.state_value_for if row else 0.0)
            team_venue_against[team].append(row.state_value_against if row else 0.0)

    uncertainty = bootstrap_umpire_aggregates(
        historical.observations,
        scoring.pitches,
        alpha=250.0,
        iterations=iterations,
        seed=20260715,
    )
    uncertainty_by_umpire = {row.umpire: row for row in uncertainty}
    reference_by_umpire = {
        row.umpire: row.sum_delta_runs_offense for row in umpire_rows
    }
    sensitivity = {
        umpire: {
            "zone_sensitive": _sign_flipped(
                reference_by_umpire[umpire], list(zone_by_umpire[umpire].values())
            ),
            "coverage_sensitive": _sign_flipped(
                reference_by_umpire[umpire], venue_alternatives[umpire]
            ),
            "zone_totals": zone_by_umpire[umpire],
        }
        for umpire in reference_by_umpire
    }
    team_sensitivity = {
        row.team: {
            "for_zone_sensitive": _sign_flipped(
                row.state_value_for, list(zone_by_team[row.team]["for"].values())
            ),
            "against_zone_sensitive": _sign_flipped(
                row.state_value_against,
                list(zone_by_team[row.team]["against"].values()),
            ),
            "for_coverage_sensitive": _sign_flipped(
                row.state_value_for, team_venue_for[row.team]
            ),
            "against_coverage_sensitive": _sign_flipped(
                row.state_value_against, team_venue_against[row.team]
            ),
            "zone_totals": zone_by_team[row.team],
        }
        for row in team_rows
    }

    completed_by_venue = {str(venue): int(games) for venue, games in completed_rows}
    tracked_by_venue: dict[str, set[str]] = {}
    for pitch in scoring.pitches:
        tracked_by_venue.setdefault(pitch.venue, set()).add(pitch.game_id)
    coverage = {
        "tracked_games": len({pitch.game_id for pitch in scoring.pitches}),
        "completed_games": sum(completed_by_venue.values()),
        "by_venue": {
            venue: {
                "tracked_games": len(tracked_by_venue.get(venue, set())),
                "completed_games": completed_by_venue.get(venue, 0),
            }
            for venue in sorted(set(completed_by_venue) | set(tracked_by_venue))
        },
    }

    output.mkdir(parents=True, exist_ok=True)
    audit_path = output / "pitch_audit.jsonl"
    with audit_path.open("w", encoding="utf-8") as stream:
        for score in scores:
            pitch = score.pitch
            row = {
                "year": pitch.year,
                "kind_code": pitch.kind_code,
                "game_sno": pitch.game_sno,
                "pitcher_acnt": pitch.pitcher_acnt,
                "pitch_cnt": pitch.pitch_cnt,
                "umpire": pitch.umpire,
                "batting_team": pitch.batting_team,
                "fielding_team": pitch.fielding_team,
                "catcher_acnt": pitch.catcher_acnt,
                "venue": pitch.venue,
                "pre_call_state": asdict(pitch.state),
                "plate_loc_side": pitch.plate_loc_side,
                "plate_loc_height": pitch.plate_loc_height,
                "edge_distance_cm": score.edge_distance_cm,
                "observed_call": pitch.observed_call,
                "proxy_call": score.proxy_call,
                "proxy_disagreement": score.proxy_disagreement,
                "zone_definition": score.zone_definition,
                "run_value_ball": score.run_value_ball,
                "run_value_strike": score.run_value_strike,
                "delta_runs_offense": score.delta_runs_offense,
                "wp_ball": None,
                "wp_strike": None,
                "delta_wp_home": None,
                "link_status": "unique",
                "exclusion_reason": None,
                "model_span": f"2018-{season - 1}",
                "model_version": MODEL_VERSION,
            }
            stream.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")

    summary = {
        "model_version": MODEL_VERSION,
        "season": season,
        "kind": kind,
        "scored_pitches": len(scores),
        "post_link_exclusions": scoring.exclusions,
        "proxy_disagreements": sum(score.proxy_disagreement for score in scores),
        "backoffs": sum(score.backed_off for score in scores),
        "sum_delta_runs_offense": sum(score.delta_runs_offense for score in scores),
        "coverage": coverage,
        "umpires": [
            {
                **asdict(row),
                "bootstrap": asdict(uncertainty_by_umpire[row.umpire]),
                "sensitivity": sensitivity[row.umpire],
            }
            for row in umpire_rows
        ],
        "teams": [
            {**asdict(row), "sensitivity": team_sensitivity[row.team]}
            for row in team_rows
        ],
        "pitch_audit": str(audit_path),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ML-UMP1 好球帶判決差異離線研究")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--season", type=int, default=2026)
    audit.add_argument("--kind", default="A")
    validate = subparsers.add_parser("validate")
    validate.add_argument("--kind", default="A")
    validate.add_argument("--bootstrap", type=int, default=2_000)
    score = subparsers.add_parser("score")
    score.add_argument("--season", type=int, default=2026)
    score.add_argument("--kind", default="A")
    score.add_argument("--bootstrap", type=int, default=2_000)
    score.add_argument("--output", type=Path, default=Path("artifacts/umpire-impact"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "audit":
        _print_json(_audit(args.season, args.kind))
    elif args.command == "validate":
        _print_json(_validate(args.kind, args.bootstrap))
    else:
        summary = _score(args.season, args.kind, args.bootstrap, args.output)
        _print_json({key: value for key, value in summary.items() if key != "umpires"})


if __name__ == "__main__":
    main()
