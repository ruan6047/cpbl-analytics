"""沿既有能力／球風／特性算法；年度 A 來源不符時不輸出能力結論。"""
from __future__ import annotations

from collections import defaultdict

from cpbl.api.helpers import _dicts
from cpbl.api.routers.ability import _ADV_GATE, ability_cards
from cpbl.api.routers.players import _player_traits, _player_traits_many
from cpbl.api.team_style import build_team_style
from cpbl.models import team_style as ts


def current_matches(cur, season: int, boxes: dict[str, list[dict]]) -> dict[str, bool]:
    """current 核心計數須逐人與完整 A 完成集合一致，才可沿用原年度能力。"""
    out = {}
    for role in ('batting', 'pitching'):
        query = ("SELECT player_id,ab,h,bb,so FROM cpbl.batting_current WHERE year=%s"
                 if role == 'batting' else
                 "SELECT player_id,(trunc(ip)*3+(ip-trunc(ip))*10)::int AS outs,h,bb,so "
                 "FROM cpbl.pitching_current WHERE year=%s")
        cur.execute(query, (season,))
        current = {r['player_id']: r for r in _dicts(cur)}
        keys = ('ab', 'h', 'bb', 'so') if role == 'batting' else ('outs', 'h', 'bb', 'so')
        grouped = defaultdict(list)
        for row in boxes[role]:
            grouped[row['player_id']].append(row)
        out[role] = bool(current) and set(current) == set(grouped) and all(
            all(all(r.get(k) is not None for r in rows)
                and current[pid].get(k) == sum(r[k] for r in rows) for k in keys)
            for pid, rows in grouped.items())
    return out


def player_background(cur, pid: str, role: str, season: int, verified: bool, card: dict | None = None,
                      *, trait_league_cache: dict | None = None, prefetched: dict | None = None) -> dict:
    if not verified:
        return {'ability': {'available': False, 'status': 'source_unverified'},
                'official_pr': None, 'traits': None, 'splits': []}
    if prefetched is not None:
        return {'ability': card or {'available': False, 'role': role, 'scope': 'season'},
                'official_pr': prefetched['official_pr'], 'traits': prefetched['traits'],
                'splits': prefetched['splits']}
    cur.execute(
        f"SELECT a.* FROM cpbl.advanced_stats a WHERE a.acnt=%s AND a.year=%s "
        f"AND a.role=%s AND a.kind_code='A' AND {_ADV_GATE}", (pid, season, role))
    advanced = _dicts(cur)
    table = 'pitching_splits' if role == 'pitching' else 'batting_splits'
    cur.execute(  # noqa: S608 — 固定投打白名單
        f"SELECT * FROM cpbl.{table} WHERE acnt=%s AND year=%s AND kind_code='A' "
        "AND item_group_code='3' ORDER BY item_index", (pid, season))
    splits = _dicts(cur)
    return {'ability': card or {'available': False, 'role': role, 'scope': 'season'},
            'official_pr': advanced[0] if advanced else None,
            'traits': _player_traits(cur, pid, season, role, league_cache=trait_league_cache), 'splits': splits}


def prefetch_player_backgrounds(cur, season: int, verified: dict[str, bool],
                                pids_by_role: dict[str, list[str]], *,
                                trait_league_cache: dict | None = None) -> dict[tuple[str, str], dict]:
    """逐人三表改為每個 role 各一次 ANY 讀取；逐人結果與 player_background 單人查詢相同。

    advanced_stats PK＝(year,kind_code,acnt,role)、traits PK＝(year,kind_code,player_id)，
    所以每人至多一列；splits 依 acnt 分組後保留 item_index 排序。未核實的 role 不讀（同單人路徑）。
    """
    out: dict[tuple[str, str], dict] = {}
    for role, pids in pids_by_role.items():
        if not verified.get(role) or not pids:
            continue
        cur.execute(
            f"SELECT a.* FROM cpbl.advanced_stats a WHERE a.acnt=ANY(%s) AND a.year=%s "
            f"AND a.role=%s AND a.kind_code='A' AND {_ADV_GATE}", (list(pids), season, role))
        advanced: dict[str, dict] = {}
        for row in _dicts(cur):
            advanced.setdefault(row['acnt'], row)
        table = 'pitching_splits' if role == 'pitching' else 'batting_splits'
        cur.execute(  # noqa: S608 — 固定投打白名單
            f"SELECT * FROM cpbl.{table} WHERE acnt=ANY(%s) AND year=%s AND kind_code='A' "
            "AND item_group_code='3' ORDER BY acnt, item_index", (list(pids), season))
        splits = defaultdict(list)
        for row in _dicts(cur):
            splits[row['acnt']].append(row)
        traits = _player_traits_many(cur, pids, season, role, league_cache=trait_league_cache)
        for pid in pids:
            out[(pid, role)] = {'official_pr': advanced.get(pid), 'traits': traits[pid],
                                'splits': splits.get(pid, [])}
    return out


def team_background(season: int, games: list[dict], boxes: dict[str, list[dict]], teams: list[str]) -> list[dict]:
    """全聯盟完整 A box 才沿共享球風算法，缺計數不交給其零值容錯。"""
    grouped = {role: defaultdict(list) for role in ('batting', 'pitching')}
    for role, index in grouped.items():
        for r in boxes[role]:
            index[(r['game_key'], r['team_code'])].append(r)
    by_team = defaultdict(list)
    for game in games:
        for team in (game['away_team_code'], game['home_team_code']):
            identity = f"{season}/A/{game['game_sno']}"
            bat = grouped['batting'].get((identity, team), [])
            pit = grouped['pitching'].get((identity, team), [])
            if not bat or not pit:
                return []
            record = {}
            mapping = {'outs': 'outs', 'pa_against': 'pa', 'h_a': 'h', 'hr_a': 'hr',
                       'bb_a': 'bb', 'hbp_a': 'hbp', 'so_a': 'so'}
            for k in ts.BAT_KEYS:
                if any(r.get(k) is None for r in bat):
                    return []
                record[k] = sum(r[k] for r in bat)
            for k, source in mapping.items():
                if any(r.get(source) is None for r in pit):
                    return []
                record[k] = sum(r[source] for r in pit)
            if any(not r.get('role_type') for r in pit):
                return []
            record['starter_outs'] = sum(r['outs'] for r in pit if r['role_type'] == '先發')
            by_team[(season, team)].append(record)
    return [build_team_style(team, dict(by_team), {}, set(), {}) for team in teams]


def cards(cur, ids: list[str], season: int, verified: dict[str, bool]) -> dict:
    return {role: ability_cards(cur, ids, role, season) if verified.get(role) else {}
            for role in ('batting', 'pitching')}
