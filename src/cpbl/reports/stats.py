"""三期背景的純組裝。輸入只接 reader 已核實的完成場，不用 current 作逐場替身。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cpbl.api.between_games import ip_text, pa_rates, pitching_rates, sum_batting

PITCH_KEYS = ("outs", "er", "h", "hr", "bb", "so", "pa", "pitch_cnt")


def sum_pitching(rows: Iterable[dict]) -> dict:
    items = list(rows)
    out: dict[str, Any] = {"g": len(items) if items else None}
    for key in PITCH_KEYS:
        values = [r.get(key) for r in items]
        out[key] = None if not values or any(v is None for v in values) else sum(values)
    out["gs"] = sum(r["role_type"] == "先發" for r in items) if items and all(r.get("role_type") for r in items) else None
    return {**out, "ip": ip_text(out["outs"]), **pitching_rates(out),
            **pa_rates(out["pa"], out["so"], out["bb"])}


def player_period(rows: list[dict], *, role: str, player_id: str, team: str,
                  expected_keys: list[str], source: str, cutoff: str,
                  complete_population: bool = False) -> dict:
    scoped = [r for r in rows if r["player_id"] == player_id and r["team_code"] == team
              and r["game_key"] in expected_keys]
    coverage = {r["game_key"] for r in rows if r["team_code"] == team}
    complete = bool(expected_keys) and set(expected_keys) <= coverage
    counts = (sum_pitching(scoped) if role == "pitching" else sum_batting(scoped))
    status = "available" if scoped else "not_appeared" if complete and complete_population else "missing"
    return {"status": status, "counts": counts,
            "sample": {"pa": counts.get("pa"), "ab": counts.get("ab"), "outs": counts.get("outs")},
            "covered_game_keys": sorted({r["game_key"] for r in scoped}),
            "expected_game_keys": expected_keys, "coverage_status": "complete" if complete else "partial",
            "source": source, "cutoff_label": cutoff}


def three_periods(*, series: list[dict], regular: list[dict], role: str, player_id: str,
                  team: str, opponent: str, series_keys: list[str], regular_keys: list[str],
                  cutoff: str, complete_population: bool, opponent_keys: list[str] | None = None) -> dict:
    opponent_rows = [r for r in regular if r["opponent_code"] == opponent]
    if opponent_keys is None:
        opponent_keys = sorted({r["game_key"] for r in opponent_rows if r["team_code"] == team})
    shared = {"role": role, "player_id": player_id, "team": team, "cutoff": cutoff,
              "complete_population": complete_population}
    return {
        "series": player_period(series, expected_keys=series_keys, source="gamelog_series", **shared),
        "regular": player_period(regular, expected_keys=regular_keys, source="gamelog_A", **shared),
        "opponent_regular": player_period(opponent_rows, expected_keys=opponent_keys,
                                          source="gamelog_A_vs_team", **shared),
    }


def field_candidates(fielding: list[dict], *, team: str, player_ids: set[str]) -> dict:
    """本季各守位最大 G；並列保留，不把缺守位的人當 DH。"""
    groups: dict[str, list[dict]] = {}
    for row in fielding:
        if row["team_code"] == team and row["player_id"] in player_ids and row.get("g") is not None:
            groups.setdefault(row["pos"], []).append(row)
    out = {}
    for pos, rows in groups.items():
        maximum = max(r["g"] for r in rows)
        leaders = sorted((r for r in rows if r["g"] == maximum), key=lambda r: r["player_id"])
        out[pos] = {"status": "tied" if len(leaders) > 1 else "known", "g": maximum,
                    "player_ids": [r["player_id"] for r in leaders]}
    return out


def watch_points(players: list[dict], *, team_codes: list[str], anchor_key: str) -> list[dict]:
    """每隊最多兩則：前場 → 系列 → 對特定先發。只按原計數排序，不合成評分。"""
    out = []
    for team in team_codes:
        candidates = []
        for p in players:
            if p["team_code"] != team:
                continue
            for origin, period in (("last_game", p.get("last_game")),
                                   ("series", p["periods"].get("series")),
                                   ("season_vs_pitcher", p.get("vs_starter"))):
                if not period or period.get("status") != "available":
                    continue
                c = period.get("counts", {})
                if p["role"] == "batting":
                    if not c.get("h") and not c.get("bb"):
                        continue
                    order = (-(c.get("xbh") or 0), -(c.get("h") or 0), -(c.get("bb") or 0))
                    line = {k: c.get(k) for k in ("pa", "h", "xbh", "bb")}
                else:
                    if not c.get("so") or c.get("bb") is None:
                        continue
                    order = (-c["so"], c["bb"], -(c.get("outs") or 0))
                    line = {k: c.get(k) for k in ("outs", "so", "bb")}
                priority = {"last_game": 0, "series": 1, "season_vs_pitcher": 2}[origin]
                candidates.append(((priority, *order, p["player_id"]), {
                    "team_code": team, "player_id": p["player_id"], "origin": origin,
                    "game_keys": [anchor_key] if origin == "last_game" else period.get("covered_game_keys", []),
                    "opponent_pitcher_id": period.get("pitcher_id"), "count_line": line,
                    "sample": period.get("sample"), "source_refs": [period.get("source")],
                    "question": "下一場能否延續這段表現？",
                }))
        seen = set()
        for _, point in sorted(candidates, key=lambda x: x[0]):
            if point["player_id"] not in seen:
                out.append(point)
                seen.add(point["player_id"])
            if len(seen) == 2:
                break
    return out
