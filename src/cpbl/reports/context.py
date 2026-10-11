"""#238 有界 journey 輸入；系列／Y 判定仍只在既有網頁 journey。"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from cpbl.api.between_games import _started_obs, order_series, through


def jsonable(value):
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def key(game: dict) -> str:
    return f"{game['year']}/{game['kind_code']}/{game['game_sno']}"


def bounded_context(anchor: dict, games: list[dict], schedules: list[dict]) -> dict:
    year, kind, sno = anchor["year"], anchor["kind_code"], anchor["game_sno"]
    series, order_ok = order_series(g for g in games if g["year"] == year
                                   and g["kind_code"] == kind and g["completed"])
    upto = through(series, sno) or []
    e_games = [g for g in games if kind == "C" and g["kind_code"] == "E" and g["completed"]
               and g["game_date"] <= anchor["game_date"]]
    included = [*e_games, *upto]
    groups = {}
    for game in included:
        group = groups.setdefault(game["kind_code"], {
            "kind_code": game["kind_code"], "team1_code": game["away_team_code"],
            "team2_code": game["home_team_code"], "games": [],
        })
        group["games"].append({"game_no": len(group["games"]) + 1,
                               "game_sno": game["game_sno"], "date": game["game_date"],
                               "away_code": game["away_team_code"], "home_code": game["home_team_code"],
                               "away_score": game["away_score"], "home_score": game["home_score"]})
    revisions = {}
    for row in schedules:
        if row["year"] == year:
            revisions.setdefault((row["kind_code"], row["game_sno"]), []).append(row)
    rows, sources = [], []
    for identity, versions in sorted(revisions.items()):
        first_started = min((v["fetched_at"] for v in versions
                             if _started_obs(v) and v.get("fetched_at")), default=None)
        pre = [v for v in versions if v.get("raw_present_status") == 1
               and v.get("raw_game_result") in (None, "") and v.get("is_play_ball") == "N"
               and v.get("raw_game_date") and v.get("fetched_at")
               and (first_started is None or v["fetched_at"] < first_started)]
        selected = max(pre, key=lambda v: (v["fetched_at"], v["payload_hash"]), default=None)
        if not selected:
            continue
        raw = selected["raw_payload"]
        away, home = raw.get("VisitingTeamCode"), raw.get("HomeTeamCode")
        if not away or not home:
            continue
        rows.append({"year": year, "kind_code": identity[0], "game_sno": identity[1],
                     "game_date": selected["raw_game_date"], "venue": raw.get("FieldAbbe"),
                     "away_team_code": away, "home_team_code": home,
                     "away_score": 0, "home_score": 0, "completed": False})
        sources.append({"source": "official_schedule", "game_key": f"{year}/{identity[0]}/{identity[1]}",
                        "source_version": selected["payload_hash"], "fetched_at": selected["fetched_at"],
                        "reference": "https://www.cpbl.com.tw/schedule", "cutoff_basis": "positive_pregame"})
    context = jsonable({"summary": list(groups.values()), "rows": rows, "sources": sources,
                        "through_game_keys": [key(g) for g in upto],
                        "order_consistent": order_ok, "cutoff_date": anchor["game_date"],
                        "season": year, "kind_code": kind, "game_sno": sno})
    context["context_hash"] = hashlib.sha256(json.dumps(
        context, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return context


def validate_target(context: dict, kind: str, sno: int, supplied_hash: str) -> dict:
    if supplied_hash != context["context_hash"]:
        raise ContextChanged("報告來源已更新，請重新讀取")
    candidate = next((r for r in context["rows"] if r["kind_code"] == kind and r["game_sno"] == sno), None)
    if candidate is None or f"{context['season']}/{kind}/{sno}" in context["through_game_keys"]:
        raise ValueError("下一場不是此背景的正式來源候選")
    if candidate["game_date"] < context["cutoff_date"]:
        raise ValueError("下一場日期早於截至場")
    return candidate


class ContextChanged(ValueError):
    pass
