"""三期背景的純組裝。輸入只接 reader 已核實的完成場，不用 current 作逐場替身。"""

from __future__ import annotations

from collections import defaultdict
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


class BoxIndex:
    """同一份 box 列依 (player_id, team_code) 與 team_code 分組；只改查找方式，列與相對順序不變。"""

    __slots__ = ("rows", "by_player", "coverage", "_by_opponent")

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.by_player: dict[tuple, list[dict]] = defaultdict(list)
        self.coverage: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            self.by_player[(r["player_id"], r["team_code"])].append(r)
            self.coverage[r["team_code"]].add(r["game_key"])
        self._by_opponent: dict[str, BoxIndex] | None = None

    def player_rows(self, player_id: str, team: str) -> list[dict]:
        return self.by_player.get((player_id, team), [])

    def opponent(self, opponent: str) -> BoxIndex:
        """等同 `[r for r in rows if r["opponent_code"] == opponent]` 的索引。"""
        if self._by_opponent is None:
            groups: dict[str, list[dict]] = defaultdict(list)
            for r in self.rows:
                groups[r["opponent_code"]].append(r)
            self._by_opponent = {code: BoxIndex(items) for code, items in groups.items()}
        found = self._by_opponent.get(opponent)
        return found if found is not None else BoxIndex([])


def player_period(rows: list[dict], *, role: str, player_id: str, team: str,
                  expected_keys: list[str], source: str, cutoff: str,
                  complete_population: bool = False, index: BoxIndex | None = None) -> dict:
    """`index` 須由同一份 `rows` 建立；省略時現建，結果相同。"""
    index = index if index is not None else BoxIndex(rows)
    expected = set(expected_keys)
    scoped = [r for r in index.player_rows(player_id, team) if r["game_key"] in expected]
    coverage = index.coverage.get(team, set())
    complete = bool(expected_keys) and expected <= coverage
    counts = (sum_pitching(scoped) if role == "pitching" else sum_batting(scoped))
    status = "available" if scoped else "not_appeared" if complete and complete_population else "missing"
    return {"status": status, "counts": counts,
            "sample": {"pa": counts.get("pa"), "ab": counts.get("ab"), "outs": counts.get("outs")},
            "covered_game_keys": sorted({r["game_key"] for r in scoped}),
            "expected_game_keys": expected_keys, "coverage_status": "complete" if complete else "partial",
            "source": source, "cutoff_label": cutoff}


def three_periods(*, series: list[dict], regular: list[dict], role: str, player_id: str,
                  team: str, opponent: str, series_keys: list[str], regular_keys: list[str],
                  cutoff: str, complete_population: bool, opponent_keys: list[str] | None = None,
                  series_index: BoxIndex | None = None, regular_index: BoxIndex | None = None) -> dict:
    """`series_index`／`regular_index` 須分別由 `series`／`regular` 建立；省略時現建，結果相同。"""
    series_index = series_index if series_index is not None else BoxIndex(series)
    regular_index = regular_index if regular_index is not None else BoxIndex(regular)
    opponent_index = regular_index.opponent(opponent)
    if opponent_keys is None:
        opponent_keys = sorted({r["game_key"] for r in opponent_index.rows if r["team_code"] == team})
    shared = {"role": role, "player_id": player_id, "team": team, "cutoff": cutoff,
              "complete_population": complete_population}
    return {
        "series": player_period(series, expected_keys=series_keys, source="gamelog_series",
                                index=series_index, **shared),
        "regular": player_period(regular, expected_keys=regular_keys, source="gamelog_A",
                                 index=regular_index, **shared),
        "opponent_regular": player_period(opponent_index.rows, expected_keys=opponent_keys,
                                          source="gamelog_A_vs_team", index=opponent_index, **shared),
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
    """每隊最多兩則：前場 → 系列 → 對特定先發，不推測下一場狀態。

    同來源先各留一位打者／投手，不跨角色比較 SO 與長打數。
    打者以已知長打、多次安打或保送為正證；投手只列已投出局、
    零責失且保送有值的紀錄，再按局數／保送排序。SO 僅供呈現。
    零責失不是零失分；缺值不當零，也不建立新的綜合評分。
    """
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
                    if not any(c.get(k) is not None and c[k] >= minimum
                               for k, minimum in (("hr", 1), ("xbh", 1), ("h", 2), ("bb", 2))):
                        continue
                    # 未知只在排序落後已知，不改写原始 counts。
                    order = tuple(-(c[k] if c.get(k) is not None else -1)
                                  for k in ("hr", "xbh", "h", "bb"))
                    line = {k: c.get(k) for k in ("pa", "h", "hr", "xbh", "bb")}
                else:
                    if c.get("er") != 0 or c.get("outs") is None or c["outs"] <= 0 or c.get("bb") is None:
                        continue
                    order = (-c["outs"], c["bb"])
                    line = {k: c.get(k) for k in ("outs", "er", "h", "bb", "so")}
                priority = {"last_game": 0, "series": 1, "season_vs_pitcher": 2}[origin]
                candidates.append(((priority, 0 if p["role"] == "batting" else 1, *order, p["player_id"]), p["role"], {
                    "team_code": team, "player_id": p["player_id"], "origin": origin,
                    "game_keys": [anchor_key] if origin == "last_game" else period.get("covered_game_keys", []),
                    "opponent_pitcher_id": period.get("pitcher_id"), "count_line": line,
                    "sample": period.get("sample"), "source_refs": [period.get("source")],
                    "question": "下一場能否延續這段表現？",
                }))
        seen = set()
        ordered = sorted(candidates, key=lambda x: x[0])
        for priority in range(3):
            group = [c for c in ordered if c[0][0] == priority and c[2]["player_id"] not in seen]
            leads = [next((c for c in group if c[1] == role), None) for role in ("batting", "pitching")]
            for candidate in [c for c in leads if c is not None] + group:
                point = candidate[2]
                if point["player_id"] not in seen:
                    out.append(point)
                    seen.add(point["player_id"])
                if len(seen) == 2:
                    break
            if len(seen) == 2:
                break
    return out
