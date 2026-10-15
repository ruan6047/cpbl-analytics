"""#287 S06 隊伍比較的純計算核心（無 DB、無時鐘；builder 與 reader 共用同一組函式）。

口徑（PLAN r2 §4，已核定）：

- 所有率＝**scope 內先加總原始計數，再一次算率**；⛔ 不平均球員率、⛔ 不平均單場 ERA、
  ⛔ 不用四捨五入後的 OBP／SLG 相加（G11）。本模組不做任何四捨五入；呈現層只捨入一次。
- 嚴格 NULL（G06）：任一參與計數未知（缺該隊 box、欄位 NULL、主客別未知）⇒ 該計數 ``None``
  並在 ``null_reasons`` 記原因（``box_missing:<game_key>``／``column_null:<col>``）；分母為 0 ⇒
  指標 ``None``＋``zero_denominator``。⛔ 缺值一律不補 0。
- 隊別歸屬：gamelog ``visiting_home_type`` '1'＝客、'2'＝主（與 ``standings._team_scoped_metrics``
  同一判準）；其他值⇒該場兩隊 box 計數皆 ``column_null:visiting_home_type``。
- 勝敗和由 games 比分判定；**和局計入 G**；連續紀錄依 (game_date, game_sno) 排序、和局中斷
  （``special_records._add_streaks`` 口徑），輸出結尾連續段。
- 球風七軸只重用 :mod:`cpbl.models.team_style` 的凍結純公式（不改該檔）。
- ⛔ 不讀 ``team_current``／``*_current``（G10）；本模組不碰 DB。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from cpbl.models import team_style as ts

GameKey = tuple[int, str, int]

# ---------------------------------------------------------------- 計數鍵（與 migration 077 欄位同序）

#: 打擊計數 ← batting_gamelog 欄位
BAT_MAP: dict[str, str] = {
    "bat_pa": "plate_appearances", "bat_ab": "at_bats", "bat_h": "hits", "bat_1b": "singles",
    "bat_tb": "total_bases", "bat_bb": "bb", "bat_hbp": "hbp", "bat_sf": "sac_fly",
    "bat_sh": "sac_hit", "bat_so": "so", "bat_sb": "sb", "bat_cs": "cs",
}
#: 投手計數 ← pitching_gamelog 欄位（outs／starter_outs 另算）
PIT_MAP: dict[str, str] = {
    "pit_bf": "plate_appearances", "pit_h": "hits", "pit_hr": "home_runs", "pit_bb": "bb",
    "pit_hbp": "hbp", "pit_so": "so", "pit_er": "earned_runs",
}
OUTS_COLUMNS = ("inning_pitched_cnt", "inning_pitched_div3")
STARTER_ROLE = "先發"

BAT_SOURCE_COLUMNS: tuple[str, ...] = ("visiting_home_type", *BAT_MAP.values())
PIT_SOURCE_COLUMNS: tuple[str, ...] = ("visiting_home_type", "role_type", *OUTS_COLUMNS, *PIT_MAP.values())

RESULT_KEYS = ("games", "wins", "losses", "ties", "runs_for", "runs_against")
BAT_KEYS = tuple(BAT_MAP)
PIT_KEYS = ("pit_outs", "pit_starter_outs", *PIT_MAP)
BOX_KEYS = (*BAT_KEYS, *PIT_KEYS)
COUNT_KEYS = (*RESULT_KEYS, *BOX_KEYS)

VHT_AWAY, VHT_HOME = "1", "2"

# ---------------------------------------------------------------- 指標定義（呈現層讀這份）

METRIC_DEFS: tuple[dict, ...] = (
    {"key": "ops", "label": "OPS", "unit": "", "higher_is_better": True, "decimals": 3},
    {"key": "rf_pg", "label": "得分／場", "unit": "分", "higher_is_better": True, "decimals": 2},
    {"key": "ra_pg", "label": "失分／場", "unit": "分", "higher_is_better": False, "decimals": 2},
    {"key": "era", "label": "ERA", "unit": "", "higher_is_better": False, "decimals": 2},
    {"key": "whip", "label": "WHIP", "unit": "", "higher_is_better": False, "decimals": 2},
    {"key": "der", "label": "DER", "unit": "", "higher_is_better": True, "decimals": 3},
)
METRIC_KEYS = tuple(d["key"] for d in METRIC_DEFS)

#: 每個指標使用的原始計數（null 原因由這些計數的原因聯集而來）
METRIC_INPUTS: dict[str, tuple[str, ...]] = {
    "ops": ("bat_h", "bat_bb", "bat_hbp", "bat_ab", "bat_sf", "bat_tb"),
    "rf_pg": ("runs_for", "games"),
    "ra_pg": ("runs_against", "games"),
    "era": ("pit_er", "pit_outs"),
    "whip": ("pit_h", "pit_bb", "pit_outs"),
    "der": ("pit_h", "pit_hr", "pit_bf", "pit_bb", "pit_hbp", "pit_so"),
}

#: 球風原始成分 → 使用的計數（team_style 凍結公式的輸入）
STYLE_INPUTS: dict[str, tuple[str, ...]] = {
    "sba_rate": ("bat_sb", "bat_cs", "bat_1b", "bat_bb", "bat_hbp"),
    "sh_rate": ("bat_sh", "bat_pa"),
    "iso": ("bat_tb", "bat_h", "bat_ab"),
    "bb_rate": ("bat_bb", "bat_pa"),
    "k_rate": ("bat_so", "bat_pa"),
    "starter_share": ("pit_starter_outs", "pit_outs"),
    "kpct": ("pit_so", "pit_bf"),
    "der": ("pit_h", "pit_hr", "pit_bf", "pit_bb", "pit_hbp", "pit_so"),
}
#: 軸 → 原始成分（discipline 複合軸在非全年 scope 分列 bb_rate／k_rate，D2）
AXIS_COMPONENTS: dict[str, tuple[str, ...]] = {
    "speed": ("sba_rate",), "smallball": ("sh_rate",), "power": ("iso",),
    "discipline": ("bb_rate", "k_rate"), "starter_ip": ("starter_share",),
    "pitch_k": ("kpct",), "defense": ("der",),
}
#: 本卡計數鍵 → team_style 凍結公式的鍵
_TS_KEY = {
    "bat_pa": "pa", "bat_ab": "ab", "bat_h": "h", "bat_1b": "singles", "bat_tb": "tb",
    "bat_sh": "sh", "bat_sf": "sf", "bat_bb": "bb", "bat_hbp": "hbp", "bat_so": "so",
    "bat_sb": "sb", "bat_cs": "cs", "pit_outs": "outs", "pit_starter_outs": "starter_outs",
    "pit_bf": "pa_against", "pit_h": "h_a", "pit_hr": "hr_a", "pit_bb": "bb_a",
    "pit_hbp": "hbp_a", "pit_so": "so_a",
}

Reasons = dict[str, list[str]]


def key_str(key: GameKey) -> str:
    """場次鍵字串 ``"Y/K/sno"``（連續紀錄 through、null 原因、coverage 共用）。"""
    return f"{key[0]}/{key[1]}/{key[2]}"


def _add(reasons: Reasons, k: str, reason: str) -> None:
    lst = reasons.setdefault(k, [])
    if reason not in lst:
        lst.append(reason)


def _merge(dst: Reasons, src: Mapping[str, Iterable[str]]) -> None:
    for k, rs in src.items():
        for r in rs:
            _add(dst, k, r)


def _sorted_reasons(reasons: Reasons) -> Reasons:
    return {k: sorted(v) for k, v in sorted(reasons.items()) if v}


# ---------------------------------------------------------------- 單場資料


@dataclass(frozen=True)
class GameRow:
    """一場已完成比賽（games 表事實；比分是完成場的正式比分）。"""
    key: GameKey
    game_date: date
    home: str
    away: str
    home_score: int | None
    away_score: int | None

    def result_for(self, team: str) -> str:
        if self.home_score is None or self.away_score is None:
            raise ValueError(f"{key_str(self.key)} 已完成卻無比分（資料不變量破壞）")
        us, them = ((self.home_score, self.away_score) if team == self.home
                    else (self.away_score, self.home_score))
        return "W" if us > them else "L" if us < them else "T"

    def opponent(self, team: str) -> str:
        return self.away if team == self.home else self.home


def sort_games(games: Iterable[GameRow]) -> list[GameRow]:
    return sorted(games, key=lambda g: (g.game_date, g.key[2]))


def side_box(bat_rows: Sequence[Mapping], pit_rows: Sequence[Mapping], key: GameKey,
             *, side_unknown: bool = False) -> tuple[dict[str, int | None], Reasons]:
    """一場一隊的 box 原始計數（嚴格 NULL）。``bat_rows``／``pit_rows`` 為該隊該場的 gamelog 列。"""
    counts: dict[str, int | None] = {}
    reasons: Reasons = {}
    if side_unknown:
        for k in BOX_KEYS:
            counts[k] = None
            _add(reasons, k, "column_null:visiting_home_type")
        return counts, reasons

    if not bat_rows:
        for k in BAT_KEYS:
            counts[k] = None
            _add(reasons, k, f"box_missing:{key_str(key)}")
    else:
        for k, col in BAT_MAP.items():
            vals = [r.get(col) for r in bat_rows]
            if any(v is None for v in vals):
                counts[k] = None
                _add(reasons, k, f"column_null:{col}")
            else:
                counts[k] = sum(int(v) for v in vals)

    if not pit_rows:
        for k in PIT_KEYS:
            counts[k] = None
            _add(reasons, k, f"box_missing:{key_str(key)}")
        return counts, reasons

    for k, col in PIT_MAP.items():
        vals = [r.get(col) for r in pit_rows]
        if any(v is None for v in vals):
            counts[k] = None
            _add(reasons, k, f"column_null:{col}")
        else:
            counts[k] = sum(int(v) for v in vals)

    outs_null = [c for c in OUTS_COLUMNS if any(r.get(c) is None for r in pit_rows)]
    if outs_null:
        for k in ("pit_outs", "pit_starter_outs"):
            counts[k] = None
            for c in outs_null:
                _add(reasons, k, f"column_null:{c}")
    else:
        outs = [int(r["inning_pitched_cnt"]) * 3 + int(r["inning_pitched_div3"]) for r in pit_rows]
        counts["pit_outs"] = sum(outs)
        if any(r.get("role_type") is None for r in pit_rows):
            counts["pit_starter_outs"] = None
            _add(reasons, "pit_starter_outs", "column_null:role_type")
        else:
            counts["pit_starter_outs"] = sum(
                o for o, r in zip(outs, pit_rows, strict=True) if r["role_type"] == STARTER_ROLE)
    return counts, reasons


BoxIndex = dict[tuple[GameKey, str], tuple[dict[str, int | None], Reasons]]


def box_index(games: Iterable[GameRow], bat_rows: Iterable[Mapping],
              pit_rows: Iterable[Mapping]) -> BoxIndex:
    """(場次鍵, 隊碼) → 該隊該場 box 計數。列需帶 ``year``／``kind_code``／``game_sno``。"""
    by_game: dict[GameKey, dict[str, dict[str, list]]] = defaultdict(
        lambda: {"bat": defaultdict(list), "pit": defaultdict(list)})
    for kind, rows in (("bat", bat_rows), ("pit", pit_rows)):
        for r in rows:
            k = (int(r["year"]), str(r["kind_code"]), int(r["game_sno"]))
            by_game[k][kind][r.get("visiting_home_type")].append(r)
    out: BoxIndex = {}
    for g in games:
        rec = by_game.get(g.key, {"bat": {}, "pit": {}})
        unknown = any(v not in (VHT_AWAY, VHT_HOME) for part in rec.values() for v in part)
        for team, vht in ((g.away, VHT_AWAY), (g.home, VHT_HOME)):
            out[(g.key, team)] = side_box(rec["bat"].get(vht, []), rec["pit"].get(vht, []), g.key,
                                          side_unknown=unknown)
    return out


def coverage(games: Iterable[GameRow], index: BoxIndex) -> dict:
    """逐場兩側 box 覆蓋（builder 停止條件 §12.1-1 與報告用）。"""
    games = sort_games(games)
    missing = []
    for g in games:
        for team in (g.away, g.home):
            counts, reasons = index[(g.key, team)]
            if any(counts[k] is None for k in BOX_KEYS):
                missing.append({"game_key": key_str(g.key), "team_code": team,
                                "reasons": sorted({r for rs in reasons.values() for r in rs})})
    expected = len(games)
    covered = expected - len({m["game_key"] for m in missing})
    return {"expected_games": expected, "covered_games": covered, "missing": missing}


# ---------------------------------------------------------------- scope 加總


@dataclass
class Totals:
    counts: dict[str, int | None]
    reasons: Reasons
    sequence: list[tuple[GameKey, str]]


def aggregate(team: str, games: Iterable[GameRow], index: BoxIndex,
              box_games: Iterable[GameKey] | None = None) -> Totals:
    """某隊在一組已完成場次的原始計數加總（嚴格 NULL）＋依日期的 W/L/T 序列。

    勝敗和、得失分、連續紀錄來自 ``games`` 全部場次；box 計數只加總 ``box_games``
    （預設＝全部場次）。本系列 scope 以此表達「box 只對 covered 場加總」（PLAN §5.3）。
    """
    box_set = None if box_games is None else set(box_games)
    games = sort_games(games)
    counts: dict[str, int | None] = {k: 0 for k in COUNT_KEYS}
    reasons: Reasons = {}
    seq: list[tuple[GameKey, str]] = []
    for g in games:
        if team not in (g.home, g.away):
            raise ValueError(f"{team} 不在 {key_str(g.key)}")
        res = g.result_for(team)
        seq.append((g.key, res))
        counts["games"] += 1
        counts[{"W": "wins", "L": "losses", "T": "ties"}[res]] += 1
        us, them = ((g.home_score, g.away_score) if team == g.home else (g.away_score, g.home_score))
        counts["runs_for"] += us
        counts["runs_against"] += them
        if box_set is not None and g.key not in box_set:
            continue
        box, box_reasons = index[(g.key, team)]
        _merge(reasons, box_reasons)
        for k in BOX_KEYS:
            v = box[k]
            counts[k] = None if (v is None or counts[k] is None) else counts[k] + v
    return Totals(counts, _sorted_reasons(reasons), seq)


# ---------------------------------------------------------------- 率（未四捨五入）


def _inputs_reasons(counts: Mapping[str, int | None], reasons: Mapping[str, list[str]],
                    keys: Iterable[str]) -> list[str] | None:
    """有任一輸入為 None ⇒ 回傳原因清單；全部已知 ⇒ None。"""
    out: list[str] = []
    for k in keys:
        if counts.get(k) is None:
            out.extend(reasons.get(k) or [f"column_null:{k}"])
    return sorted(set(out)) if out else None


def metrics(counts: Mapping[str, int | None],
            reasons: Mapping[str, list[str]] | None = None) -> tuple[dict[str, float | None], Reasons]:
    """§4.2 六個比較條指標；任一輸入未知或分母 0 ⇒ None＋原因。"""
    reasons = reasons or {}
    out: dict[str, float | None] = {}
    why: Reasons = {}
    for key, inputs in METRIC_INPUTS.items():
        missing = _inputs_reasons(counts, reasons, inputs)
        if missing:
            out[key] = None
            why[key] = missing
            continue
        c = {k: counts[k] for k in inputs}
        val: float | None
        if key == "ops":
            obp_den = c["bat_ab"] + c["bat_bb"] + c["bat_hbp"] + c["bat_sf"]
            val = ((c["bat_h"] + c["bat_bb"] + c["bat_hbp"]) / obp_den + c["bat_tb"] / c["bat_ab"]
                   if obp_den and c["bat_ab"] else None)
        elif key == "rf_pg":
            val = c["runs_for"] / c["games"] if c["games"] else None
        elif key == "ra_pg":
            val = c["runs_against"] / c["games"] if c["games"] else None
        elif key == "era":
            val = 27 * c["pit_er"] / c["pit_outs"] if c["pit_outs"] else None
        elif key == "whip":
            val = 3 * (c["pit_h"] + c["pit_bb"]) / c["pit_outs"] if c["pit_outs"] else None
        else:  # der
            bip = c["pit_bf"] - c["pit_bb"] - c["pit_hbp"] - c["pit_so"] - c["pit_hr"]
            val = 1 - (c["pit_h"] - c["pit_hr"]) / bip if bip > 0 else None
        out[key] = val
        if val is None:
            why[key] = ["zero_denominator"]
    return out, why


def style_raw(counts: Mapping[str, int | None],
              reasons: Mapping[str, list[str]] | None = None) -> tuple[dict[str, float | None], Reasons]:
    """球風原始成分（沿 team_style 凍結公式；未知輸入 ⇒ None＋原因，不補 0）。"""
    reasons = reasons or {}
    filled = {_TS_KEY[k]: (counts.get(k) or 0) for k in _TS_KEY}
    raw = {**ts.batting_axes_raw(filled), **ts.pitching_axes_raw(filled)}
    out: dict[str, float | None] = {}
    why: Reasons = {}
    for comp, inputs in STYLE_INPUTS.items():
        missing = _inputs_reasons(counts, reasons, inputs)
        if missing:
            out[comp], why[comp] = None, missing
        else:
            out[comp] = raw[comp]
            if raw[comp] is None:
                why[comp] = ["zero_denominator"]
    return out, why


def season_style(raw_by_team: Mapping[str, Mapping[str, float | None]]) -> dict[str, dict[str, dict]] | None:
    """全年 A 六隊 → 每隊七軸 {z, rank}（team_style 凍結公式）；任一成分未知 ⇒ None（整季不出）。"""
    if not raw_by_team or any(v is None for r in raw_by_team.values() for v in r.values()):
        return None
    z = ts.season_axis_z({t: dict(r) for t, r in raw_by_team.items()})
    return {
        team: {axis: {"z": z[team][axis], "rank": ts.rank_desc({t: z[t][axis] for t in z}, team)}
               for axis in ts.AXES}
        for team in z
    }


def league_mean(raw_by_team: Mapping[str, Mapping[str, float | None]], comp: str) -> float | None:
    """同年全年 A 六隊原始成分的算術平均（與 team_style ``league_raw_mean`` 同口徑）；有未知回 None。"""
    vals = [r.get(comp) for r in raw_by_team.values()]
    if not vals or any(v is None for v in vals):
        return None
    return sum(vals) / len(vals)


# ---------------------------------------------------------------- 連續紀錄


def trailing_streak(seq: Sequence[tuple[GameKey, str]]) -> dict | None:
    """結尾連續段：同結果連續場數（和局中斷 W／L，連續和局自成一段）。"""
    if not seq:
        return None
    last_key, last = seq[-1]
    n = 0
    for _, r in reversed(seq):
        if r != last:
            break
        n += 1
    return {"result": last, "len": n, "through": key_str(last_key)}


def max_streaks(seq: Sequence[tuple[GameKey, str]]) -> tuple[int, int]:
    """最大連勝／連敗（``special_records._add_streaks`` 口徑，供 E6 交叉驗證）。"""
    mw = ml = cw = cl = 0
    for _, r in seq:
        cw = cw + 1 if r == "W" else 0
        cl = cl + 1 if r == "L" else 0
        mw, ml = max(mw, cw), max(ml, cl)
    return mw, ml


# ---------------------------------------------------------------- 共享尺度


def shared_scale(season_values: Iterable[float | None],
                 scope_values: Iterable[float | None]) -> dict | None:
    """軸域＝同年全年 A 六隊值 [min, max]，再擴張涵蓋該 scope 兩隊值（⛔ 不裁切小樣本值）。"""
    base = [v for v in season_values if v is not None]
    extra = [v for v in scope_values if v is not None]
    vals = base + extra
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals)}


# ---------------------------------------------------------------- 列、雜湊


def row_from_totals(scope: str, team: str, opponent: str, t: Totals) -> dict:
    """摘要列（DB 欄位同名）：原始計數＋結尾連續段＋null 原因。"""
    st = trailing_streak(t.sequence)
    return {
        "scope": scope, "team_code": team, "opponent_code": opponent,
        **{k: t.counts[k] for k in COUNT_KEYS},
        "streak_result": st["result"] if st else None,
        "streak_len": st["len"] if st else None,
        "streak_through": st["through"] if st else None,
        "null_reasons": t.reasons,
    }


ROW_COLUMNS: tuple[str, ...] = ("scope", "team_code", "opponent_code", *COUNT_KEYS,
                                "streak_result", "streak_len", "streak_through", "null_reasons")


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_hex(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def rows_digest(rows: Iterable[Mapping]) -> str:
    """列內容雜湊（不含 build_id）；本機 builder 與同步對帳同一函式。"""
    body = sorted(([r[c] for c in ROW_COLUMNS] for r in rows),
                  key=lambda r: (r[0], r[1], r[2]))
    return sha256_hex({"label": "team-comparison-rows/v1", "columns": ROW_COLUMNS, "rows": body})


def games_payload(games: Iterable[GameRow]) -> list[list]:
    return [[g.key[2], g.game_date.isoformat(), g.away, g.home, g.away_score, g.home_score]
            for g in sorted(games, key=lambda g: g.key[2])]


def games_fingerprint(year: int, games: Iterable[GameRow]) -> str:
    """只含已完成 A 場清單（GET 只讀 games 即可廉價重算）。"""
    return sha256_hex({"label": "team-comparison-games/v1", "year": year, "games": games_payload(games)})
