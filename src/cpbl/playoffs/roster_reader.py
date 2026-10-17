"""第 3 區 32 人資格名單背景讀取面（#286 S05）：名單、本站角色、出賽 G、官方 PR≥90、A／D 背景。

分兩層（沿 :mod:`cpbl.playoffs.watch_reader` 慣例）：

- :func:`read_roster_inputs`：薄 I/O，呼叫端已開好單一 ``REPEATABLE READ READ ONLY`` 交易；只 SELECT。
  查詢次數與名單人數無關（``ANY`` 批次）：一隊 32 人與兩隊 64 人是同一組查詢。
- :func:`compute_roster`：純組裝，同輸入同輸出。

紅線：

1. GET ⛔ 寫入、⛔ 觸發爬取或重建；⛔ 讀／import ``reports/background``、``reports/assembler``（#272 共享區）。
2. 名單與本站角色只讀 S03 三表（``series_roster``／``series_roster_member``／``roster_annotation_revision``）；
   ⛔ 以出賽紀錄反推名單。名單未提交 ⇒ 該隊 ``missing``、不列球員。
3. 當場 28 人登錄：S11 交付前恆 unknown，⛔ 由 32 人名單或先發推算；說明只走頁尾（需求方 Q4）。
4. 出賽 G＝本季逐場 box（gamelog）去重 ``game_sno``：代跑、守備出場（PA=0）也有列，保留續賽同一場只算一次。
   投手讀投球 box、其餘守位讀打擊 box。與官方季累計 ``*_current.g`` 對帳（規劃 §1：本機 0 不符）。
5. 背景層級：本季一軍 A 有出賽 ⇒ ``A``；沒有但二軍 D 有 ⇒ ``D``（只給傳統計數，⛔ PR／OPS+）；都沒有 ⇒ ``none``。
6. PR≥90 標籤只採官方進階 ``advanced_stats`` 的一軍 A 列，與球員頁同閘門（``ability._ADV_GATE``）、同一組欄；
   官方沒有就不標，⛔ 自行排名。
8. 本系列實戰（PR2）：只計所選系列（E／C 隔離）已正式完賽（S02 ``completed``）的場次；逐場 box 去重
   ``game_sno``，代跑／守備出場也算 G。完賽但缺該隊 box 的場列 ``pending_games``（來源歸 #293，⛔ 新增爬取）。
   ⛔ 混入例行賽或另一系列。
7. 冷熱箭頭（PRD 第五節，proposed）：一軍例行賽 A 最近 15 次個人出賽（W1）對緊接在前的 15 次（W0），
   出賽定義、窗長、聯盟基準都取自 :mod:`cpbl.api.routers.trend`（球員頁走勢同一份）；先加總原始計數再算、
   未四捨五入比較。門檻只住 :data:`ARROW_POLICY`，⛔ 私改、⛔ 依單系列結果調整。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cpbl.api.helpers import _dicts
from cpbl.coverage import taipei_date
from cpbl.rosters.canonical import role_fields

CONTRACT = "playoffs-roster/v1"
READ_ONLY_TXN = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"

POSITION_ORDER = {p: i for i, p in enumerate(("投手", "捕手", "內野手", "外野手"))}

#: 球員頁「官方進階・百分位 PR」同一組欄（``web/src/app/players/[id]/lib.ts`` ``ADV``，同順序）；
#: ``brl_pr`` 是 ``brlp_pr`` 的計數重複，球員頁去重不列（season.tsx ``fused``），這裡同樣不列。
PR_COLUMNS = ("ev_pr", "max_ev_pr", "brlp_pr", "hardhitp_pr", "woba_pr", "ba_pr", "iso_pr", "slg_pr",
              "obp_pr", "chasep_pr", "whiffp_pr", "kp_pr", "bbp_pr")
PR_TAG_MIN = 90

#: PRD v2 第五節建議值（proposed，版本化）。⛔ 私改；⛔ 依單系列結果調整（G12）。
ARROW_POLICY = {
    "version": "playoffs-arrow/prd-v2-proposed",
    "status": "proposed",
    "window": 15,
    "bat_min_ab": 30,
    "pit_min_outs": 30,
    "ops_plus_delta": 15,
    "era_plus_delta": 20,
}


def role_of(position: str) -> str:
    """官方守位 → 讀哪一種 box：投手讀投球，其餘讀打擊。"""
    return "pitching" if position == "投手" else "batting"


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


@dataclass
class RosterInputs:
    """一次唯讀交易讀到的全部事實（測試可直接構造）。"""

    year: int
    series: str
    context: dict                                         # S02 compute_series_context 輸出
    rosters: dict[str, dict | None] | None = None         # team → 名單；None ⇒ 來源不可用
    team_names: dict[str, str] = field(default_factory=dict)
    # (player_id, role, kind) → 原始計數（kind ∈ A／D；g＝去重 game_sno）
    counts: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    # (player_id, role) → {pr 欄: 值}（一軍 A、已過閘門）
    advanced: dict[tuple[str, str], dict] = field(default_factory=dict)
    background_cutoff: str | None = None                  # 本季一軍最後一個有 box 的比賽日
    # player_id → 最近 2×window 次 A 出賽原始計數（新到舊）；角色依官方守位
    recent: dict[str, list[dict]] = field(default_factory=dict)
    lg_obp: float | None = None
    lg_slg: float | None = None
    lg_era: float | None = None
    # 本系列（所選 series）已完賽場次的逐人原始計數：(player_id, role) → counts；None ⇒ 未讀（無完賽場）
    series_counts: dict[tuple[str, str], dict] | None = None
    # 已完賽場次 game_sno → {"away": {已送達的來源}, "home": …}；來源 ∈ {"batting", "pitching"}。
    # 兩種來源分開記：打擊與投球由爬蟲分別提交，可能只到一份（review-3 F1）。
    series_box: dict[int, dict[str, set[str]]] = field(default_factory=dict)


# —— 純計算 ——————————————————————————————————————————————————————————


def _r(v: float | None, n: int) -> float | None:
    return None if v is None else round(v, n)


def batting_line(c: dict) -> dict:
    """打擊原始計數 → 率（先加總計數再算；分母 0 ⇒ None）。"""
    ab, h, bb, hbp, sf, tb = (c.get(k) or 0 for k in ("ab", "h", "bb", "hbp", "sf", "tb"))
    den = ab + bb + hbp + sf
    obp = (h + bb + hbp) / den if den else None
    slg = tb / ab if ab else None
    return {
        "pa": c.get("pa") or 0, "ab": ab, "h": h, "hr": c.get("hr") or 0, "bb": bb,
        "avg": _r(h / ab if ab else None, 3), "obp": _r(obp, 3), "slg": _r(slg, 3),
        "ops": _r(obp + slg, 3) if obp is not None and slg is not None else None,
    }


def pitching_line(c: dict) -> dict:
    """投球原始計數（outs）→ 局數字串與 ERA（outs=0 ⇒ ERA None）。"""
    outs, er = c.get("outs") or 0, c.get("er") or 0
    return {
        "outs": outs, "ip": f"{outs // 3}.{outs % 3}", "er": er, "so": c.get("so") or 0, "bb": c.get("bb") or 0,
        "era": _r(er * 27 / outs, 2) if outs else None,
    }


def pr_tags(adv: dict | None) -> list[dict]:
    """官方 PR≥90 的欄（高到低；同值依球員頁欄序）。無官方列 ⇒ 空。"""
    if not adv:
        return []
    tags = [{"key": k, "value": int(adv[k])} for k in PR_COLUMNS
            if adv.get(k) is not None and int(adv[k]) >= PR_TAG_MIN]
    order = {k: i for i, k in enumerate(PR_COLUMNS)}
    return sorted(tags, key=lambda t: (-t["value"], order[t["key"]]))


#: 箭頭比較的浮點容差（OPS+／ERA+ 點）。由原始計數算出的 OPS+／ERA+ 帶二進位浮點誤差（約 1e-14），
#: 精確等於門檻的差值會算成 14.99999999999999 而誤判平穩（review-1 F1）。刻意：只吸收浮點誤差，
#: 遠小於畫面顯示精度（0.1 點）；⛔ 拿來放寬門檻或改用顯示取整後的值比較。
ARROW_EPS = 1e-9


def arrow_status(v1: float, v0: float, threshold: float) -> str:
    """W1−W0 ≥ 門檻 ⇒ up；≤ −門檻 ⇒ down；其餘 flat（未四捨五入比較，容許 :data:`ARROW_EPS` 浮點誤差）。"""
    d = v1 - v0
    return "up" if d >= threshold - ARROW_EPS else "down" if d <= -threshold + ARROW_EPS else "flat"


def _bat_window(rows: list[dict]) -> dict:
    c = {k: sum(r.get(k) or 0 for r in rows) for k in ("ab", "h", "bb", "hbp", "sf", "tb")}
    den = c["ab"] + c["bb"] + c["hbp"] + c["sf"]
    c["obp"] = (c["h"] + c["bb"] + c["hbp"]) / den if den else None
    c["slg"] = c["tb"] / c["ab"] if c["ab"] else None
    return c


def _pit_window(rows: list[dict]) -> dict:
    outs = sum((r.get("ipc") or 0) * 3 + (r.get("ip3") or 0) for r in rows)
    er = sum(r.get("er") or 0 for r in rows)
    return {"outs": outs, "er": er, "era": er * 27 / outs if outs else None}


def arrow_of(rows: list[dict], role: str, *, lg_obp: float | None, lg_slg: float | None, lg_era: float | None,
             policy: dict = ARROW_POLICY) -> dict:
    """冷熱箭頭（A08）。``rows``＝最近出賽原始計數，新到舊。

    - 不足 2×window 次出賽 ⇒ ``insufficient``（``appearances``）。
    - 任一窗打數／出局數未達底線，或率分母無效 ⇒ ``insufficient``（``sample``）。
    - 聯盟基準缺、或任一窗 ERA=0（ERA+ 不可定義）⇒ ``undefined``；保留 ERA 0.00 與樣本，⛔ ∞／999。
    """
    from cpbl.api.routers.trend import era_plus_raw, ops_plus_raw

    n = policy["window"]
    metric = "ops_plus" if role == "batting" else "era_plus"
    base = {"metric": metric, "appearances": min(len(rows), 2 * n), "w1": None, "w0": None, "delta": None}
    if len(rows) < 2 * n:
        return {**base, "status": "insufficient", "reason": "appearances"}
    w1_rows, w0_rows = rows[:n], rows[n:2 * n]
    if role == "batting":
        w1, w0 = _bat_window(w1_rows), _bat_window(w0_rows)
        enough = all(w["ab"] >= policy["bat_min_ab"] and w["obp"] is not None and w["slg"] is not None
                     for w in (w1, w0))
        v1 = ops_plus_raw(w1["obp"], w1["slg"], lg_obp, lg_slg) if enough else None
        v0 = ops_plus_raw(w0["obp"], w0["slg"], lg_obp, lg_slg) if enough else None
        threshold = policy["ops_plus_delta"]
        out_w = [{"ab": w["ab"], "h": w["h"], "bb": w["bb"], "hbp": w["hbp"], "sf": w["sf"], "tb": w["tb"],
                  "obp": _r(w["obp"], 3), "slg": _r(w["slg"], 3)} for w in (w1, w0)]
    else:
        w1, w0 = _pit_window(w1_rows), _pit_window(w0_rows)
        enough = all(w["outs"] >= policy["pit_min_outs"] for w in (w1, w0))
        v1 = era_plus_raw(w1["era"], lg_era) if enough else None
        v0 = era_plus_raw(w0["era"], lg_era) if enough else None
        threshold = policy["era_plus_delta"]
        out_w = [{"outs": w["outs"], "ip": f"{w['outs'] // 3}.{w['outs'] % 3}", "er": w["er"],
                  "era": _r(w["era"], 2)} for w in (w1, w0)]
    for w, v in zip(out_w, (v1, v0), strict=True):
        w["value"] = _r(v, 1)
    base.update(w1=out_w[0], w0=out_w[1])
    if not enough:
        return {**base, "status": "insufficient", "reason": "sample"}
    if v1 is None or v0 is None:
        reason = "era_zero" if role == "pitching" and lg_era and 0 in (w1["era"], w0["era"]) else "baseline"
        return {**base, "status": "undefined", "reason": reason}
    return {**base, "status": arrow_status(v1, v0, threshold), "reason": None, "delta": _r(v1 - v0, 1)}


def background_of(pid: str, role: str, inputs: RosterInputs) -> dict:
    """一名球員的例行賽背景：A 優先；無 A 改 D（只給傳統計數）；都沒有 ⇒ none。"""
    line = batting_line if role == "batting" else pitching_line
    arrow = arrow_of(inputs.recent.get(pid, []), role, lg_obp=inputs.lg_obp, lg_slg=inputs.lg_slg,
                     lg_era=inputs.lg_era)
    a = inputs.counts.get((pid, role, "A"))
    if a and a.get("g"):
        return {"level": "A", "g": a["g"], "line": line(a), "pr_tags": pr_tags(inputs.advanced.get((pid, role))),
                "arrow": arrow}
    d = inputs.counts.get((pid, role, "D"))
    if d and d.get("g"):
        return {"level": "D", "g": d["g"], "line": line(d), "pr_tags": [], "arrow": arrow}
    return {"level": "none", "g": None, "line": None, "pr_tags": [], "arrow": arrow}


def _series_games(inputs: RosterInputs) -> list[dict]:
    """所選系列已正式完賽的場次（S02 原值），依系列場序。"""
    games = [g for g in inputs.context.get("games") or []
             if (g.get("game_key") or {}).get("kind_code") == inputs.series and g.get("completed")]
    return sorted(games, key=lambda g: (g.get("series_game_no") or 0, g["game_key"]["game_sno"]))


SERIES_SOURCES = ("batting", "pitching")


def series_scope(inputs: RosterInputs, teams: list[str]) -> dict:
    """``scopes.series``：完賽場數、各隊缺 box 的場（以系列場序 G1、G2… 表示）、各隊缺哪種來源、狀態。

    一場一隊要「打擊」與「投球」兩種來源都已送達才算完整；只到一份照樣列待送達（review-3 F1）。

    - 尚無完賽場 ⇒ ``no_games``（格內「—」）。
    - 有完賽場但任一隊缺任一來源 ⇒ ``pending_source``（該隊格內「待更新」、頁尾列場次）。
    - 其餘 ⇒ ``ok``。
    """
    games = _series_games(inputs)
    if not games:
        return {"status": "no_games", "completed_games": 0, "pending_games": [], "pending_by_team": {},
                "missing_roles": {}}
    pending: dict[str, list[int]] = {t: [] for t in teams}
    missing_roles: dict[str, set[str]] = {t: set() for t in teams}
    for g in games:
        box = inputs.series_box.get(int(g["game_key"]["game_sno"]), {})
        for side in ("away", "home"):
            code = g.get(f"{side}_team_code")
            if code not in pending:
                continue
            lacking = set(SERIES_SOURCES) - set(box.get(side) or ())
            if lacking:
                pending[code].append(g.get("series_game_no") or g["game_key"]["game_sno"])
                missing_roles[code] |= lacking
    all_pending = sorted({n for v in pending.values() for n in v})
    return {"status": "pending_source" if all_pending else "ok", "completed_games": len(games),
            "pending_games": all_pending, "pending_by_team": {t: v for t, v in pending.items() if v},
            "missing_roles": {t: v for t, v in missing_roles.items() if v}}


def series_of(pid: str, role: str, inputs: RosterInputs, *, source_missing: bool = False) -> dict | None:
    """一名球員的本系列實戰：G 與傳統計數。

    - 無完賽場 ⇒ None。
    - 該隊有任一完賽場缺這名球員角色的來源（打者缺打擊、投手缺投球）⇒ ``pending``：G 與計數不給
      （格內「待更新」）。⛔ 把查無列讀成 0G，⛔ 用部分場次的計數冒充完整數字（review-3 F1）。
    - 來源齊、未出賽 ⇒ g=0、line None。
    - 打者 line 帶 ``so``（WP6；review-3 F2）。
    """
    if inputs.series_counts is None:
        return None
    if source_missing:
        return {"g": None, "line": None, "pending": True}
    c = inputs.series_counts.get((pid, role))
    if not c or not c.get("g"):
        return {"g": 0, "line": None, "pending": False}
    if role == "batting":
        return {"g": c["g"], "line": {**batting_line(c), "so": c.get("so") or 0}, "pending": False}
    return {"g": c["g"], "line": pitching_line(c), "pending": False}


def default_scope_of(inputs: RosterInputs) -> str:
    """PRD 第 3 區：系列已決定（S02 layout T5）預設「本系列實戰」，其餘預設背景。"""
    st = (((inputs.context.get("state") or {}).get("by_series") or {}).get(inputs.series) or {})
    return "series" if st.get("layout_state") == "T5" else "background"


def compute_roster(inputs: RosterInputs, *, now: datetime) -> dict:
    """``playoffs-roster/v1``（JSON-able）。``now`` 只用於 ``as_of``。"""
    ctx = inputs.context
    s = (ctx.get("series") or {}).get(inputs.series)
    sid = s.get("series_id") if s else None
    teams = [t for t in ((sid or {}).get("teams") or []) if t]
    out = {
        "contract": CONTRACT,
        "context_version": ctx.get("context_version"),
        "series_id": sid,
        "series": inputs.series,
        "year": inputs.year,
        "as_of": {
            "now": now.isoformat(),
            "taipei_date": taipei_date(now).isoformat(),
            "last_refresh_at": (ctx.get("as_of") or {}).get("last_refresh_at"),
            "last_completed_game_date": (ctx.get("as_of") or {}).get("last_completed_game_date"),
            "background_cutoff": inputs.background_cutoff,
        },
        "default_scope": default_scope_of(inputs),
        "arrow_policy": dict(ARROW_POLICY),
        "scopes": {"background": {"status": "ok"}, "series": {"status": "not_provided"}},
        "registration": {"status": "unknown", "reason": "registration_source_not_delivered"},
        "roster_version": _hash(inputs.rosters),
    }
    missing: list[str] = ["registration_source_not_delivered"]
    if not teams:
        return {**out, "status": "series_unknown", "teams": [], "missing_reason": [*missing, "series_teams_unknown"]}

    sc = series_scope(inputs, teams)
    out["scopes"] = {"background": {"status": "ok"},
                     "series": {k: v for k, v in sc.items() if k not in ("pending_by_team", "missing_roles")}}
    if sc["status"] == "pending_source":
        missing.append("series_box_pending")
    team_out = []
    for code in teams:
        roster = None if inputs.rosters is None else inputs.rosters.get(code)
        status = "unavailable" if inputs.rosters is None else "submitted" if roster else "missing"
        if status != "submitted":
            missing.append(f"roster_{status}:{code}")
        members = []
        for m in (roster or {}).get("members", []):
            role = role_of(m["official_position"])
            members.append({
                "player_id": m["player_id"],
                "name": m["announced_name"],
                "official_position": m["official_position"],
                **role_fields(m),
                "role": role,
                "background": background_of(m["player_id"], role, inputs),
                "series": series_of(m["player_id"], role, inputs,
                                    source_missing=role in sc["missing_roles"].get(code, set())),
            })
        members.sort(key=lambda x: (POSITION_ORDER.get(x["official_position"], 99), x["player_id"]))
        team_out.append({
            "team_code": code,
            "team_name": inputs.team_names.get(code),
            "roster_status": status,
            "roster": None if not roster else {
                "roster_id": roster["roster_id"], "published_date": roster.get("published_date"),
                "source_url": roster.get("source_url"), "annotation_version": roster.get("annotation_version"),
                "role_format_version": roster.get("role_format_version", 1),
                "revision_hash": roster.get("revision_hash"),
            },
            "members": members,
            "series_pending_games": sc["pending_by_team"].get(code, []),
            "series_pending_roles": sorted(sc["missing_roles"].get(code, set())),
        })
    statuses = {t["roster_status"] for t in team_out}
    status = ("unavailable" if "unavailable" in statuses else "ok" if statuses == {"submitted"}
              else "roster_missing" if "submitted" not in statuses else "partial")
    if any(m["background"]["level"] == "none" for t in team_out for m in t["members"]):
        missing.append("background_none")
    return {**out, "status": status, "teams": team_out, "missing_reason": list(dict.fromkeys(missing))}


# —— 讀取（薄 I/O） ————————————————————————————————————————————————————

ROSTER_SQL = """
    SELECT r.team_code, r.roster_id::text AS roster_id, r.published_date, r.source_url,
           lv.rev AS annotation_version, m.player_id, m.announced_name, m.official_position, a.tactical_role,
           a.role_format_version, a.tactical_roles, a.role_provenance, a.revision_hash
      FROM cpbl.series_roster r
      JOIN cpbl.series_roster_member m ON m.roster_id = r.roster_id
      LEFT JOIN LATERAL (SELECT max(x.revision) AS rev FROM cpbl.roster_annotation_revision x
                          WHERE x.roster_id = r.roster_id) lv ON TRUE
      LEFT JOIN cpbl.roster_annotation_revision a
             ON a.roster_id = r.roster_id AND a.player_id = m.player_id AND a.revision = lv.rev
     WHERE r.year = %(year)s AND r.kind_code = %(kind)s AND r.team_code = ANY(%(teams)s)
     ORDER BY r.team_code, m.player_id
"""

TEAM_NAMES_SQL = "SELECT team_code, short FROM cpbl.team_dim WHERE team_code = ANY(%(teams)s)"

# 出賽 G＝去重 game_sno（保留續賽同一場只算一次）；PA=0 的代跑／守備出場也有列。
BAT_COUNTS_SQL = """
    SELECT b.hitter_acnt AS pid, b.kind_code, count(DISTINCT b.game_sno) AS g,
           sum(b.plate_appearances) AS pa, sum(b.at_bats) AS ab, sum(b.hits) AS h, sum(b.bb) AS bb,
           sum(b.hbp) AS hbp, sum(b.sac_fly) AS sf, sum(b.total_bases) AS tb, sum(b.home_runs) AS hr
      FROM cpbl.batting_gamelog b
     WHERE b.year = %(year)s AND b.kind_code IN ('A', 'D') AND b.hitter_acnt = ANY(%(ids)s)
     GROUP BY 1, 2
"""

PIT_COUNTS_SQL = """
    SELECT p.pitcher_acnt AS pid, p.kind_code, count(DISTINCT p.game_sno) AS g,
           sum(COALESCE(p.inning_pitched_cnt, 0) * 3 + COALESCE(p.inning_pitched_div3, 0)) AS outs,
           sum(p.earned_runs) AS er, sum(p.so) AS so, sum(p.bb) AS bb
      FROM cpbl.pitching_gamelog p
     WHERE p.year = %(year)s AND p.kind_code IN ('A', 'D') AND p.pitcher_acnt = ANY(%(ids)s)
     GROUP BY 1, 2
"""

# 本系列：只取所選系列（kind_code＝series）且為 S02 已完賽的 game_sno（⛔ 混入例行賽或另一系列）。
SERIES_BAT_SQL = """
    SELECT b.hitter_acnt AS pid, count(DISTINCT b.game_sno) AS g,
           sum(b.plate_appearances) AS pa, sum(b.at_bats) AS ab, sum(b.hits) AS h, sum(b.bb) AS bb,
           sum(b.hbp) AS hbp, sum(b.sac_fly) AS sf, sum(b.total_bases) AS tb, sum(b.home_runs) AS hr,
           sum(b.so) AS so
      FROM cpbl.batting_gamelog b
     WHERE b.year = %(year)s AND b.kind_code = %(kind)s AND b.game_sno = ANY(%(snos)s)
       AND b.hitter_acnt = ANY(%(ids)s)
     GROUP BY 1
"""

SERIES_PIT_SQL = """
    SELECT p.pitcher_acnt AS pid, count(DISTINCT p.game_sno) AS g,
           sum(COALESCE(p.inning_pitched_cnt, 0) * 3 + COALESCE(p.inning_pitched_div3, 0)) AS outs,
           sum(p.earned_runs) AS er, sum(p.so) AS so, sum(p.bb) AS bb
      FROM cpbl.pitching_gamelog p
     WHERE p.year = %(year)s AND p.kind_code = %(kind)s AND p.game_sno = ANY(%(snos)s)
       AND p.pitcher_acnt = ANY(%(ids)s)
     GROUP BY 1
"""

# 各場兩隊各自已送達哪種來源（打擊／投球分開，⛔ 合併成「任一有列」——review-3 F1）；
# visiting_home_type '1'＝客、'2'＝主。
SERIES_BOX_SQL = """
    SELECT DISTINCT game_sno, visiting_home_type, 'batting' AS source FROM cpbl.batting_gamelog
     WHERE year = %(year)s AND kind_code = %(kind)s AND game_sno = ANY(%(snos)s)
    UNION
    SELECT DISTINCT game_sno, visiting_home_type, 'pitching' AS source FROM cpbl.pitching_gamelog
     WHERE year = %(year)s AND kind_code = %(kind)s AND game_sno = ANY(%(snos)s)
"""

CUTOFF_SQL = """
    SELECT max(g.game_date) FROM cpbl.games g
     WHERE g.year = %(year)s AND g.kind_code = 'A'
       AND EXISTS (SELECT 1 FROM cpbl.batting_gamelog b
                    WHERE b.year = g.year AND b.kind_code = g.kind_code AND b.game_sno = g.game_sno)
"""


def _adv_sql() -> str:
    from cpbl.api.routers.ability import _ADV_GATE  # 與球員頁／能力卡同一閘門（只 import，不改）

    return (f"SELECT a.acnt, a.role, {', '.join('a.' + c for c in PR_COLUMNS)} FROM cpbl.advanced_stats a "
            f"WHERE a.acnt = ANY(%(ids)s) AND a.year = %(year)s AND a.kind_code = 'A' AND {_ADV_GATE}")


def _optional(cur, fn):
    """名單來源失敗只降級（回 None），以 SAVEPOINT 隔離，不讓交易進入 aborted（同 watch_reader）。"""
    connection = getattr(cur, "connection", None)
    try:
        if connection is not None and hasattr(connection, "transaction"):
            with connection.transaction():
                return fn()
        return fn()
    except Exception:  # noqa: BLE001 — 缺表／權限：該來源 unavailable＋missing_reason
        return None


def read_context(cur, year: int, *, now: datetime, live_reader=None) -> dict:
    """S02 context（與 overview／watch 同一呼叫 ⇒ ``context_version`` 同源可比）。"""
    from cpbl import postseason_contract as contract

    return contract.compute_series_context(
        contract.read_series_inputs(cur, year, now=now, live_reader=live_reader), now=now)


def read_rosters(cur, year: int, series: str, teams: list[str]) -> dict[str, dict | None]:
    cur.execute(ROSTER_SQL, {"year": year, "kind": series, "teams": teams})
    out: dict[str, dict | None] = {t: None for t in teams}
    for r in _dicts(cur):
        ros = out.get(r["team_code"]) or {
            "roster_id": r["roster_id"], "published_date": str(r["published_date"]),
            "source_url": r["source_url"], "annotation_version": r["annotation_version"],
            "role_format_version": r.get("role_format_version", 1),
            "revision_hash": r.get("revision_hash"), "members": []}
        ros["members"].append({"player_id": r["player_id"], "announced_name": r["announced_name"],
                               "official_position": r["official_position"], **role_fields(r)})
        out[r["team_code"]] = ros
    return out


def read_background(cur, inputs: RosterInputs) -> None:
    """A／D 計數、官方 PR、背景截止日：每項一次 ``ANY`` 批次（與人數無關）。"""
    members = [m for r in (inputs.rosters or {}).values() if r for m in r["members"]]
    bat = sorted({m["player_id"] for m in members if role_of(m["official_position"]) == "batting"})
    pit = sorted({m["player_id"] for m in members if role_of(m["official_position"]) == "pitching"})
    ids = sorted({*bat, *pit})
    cur.execute(CUTOFF_SQL, {"year": inputs.year})
    row = cur.fetchone()
    inputs.background_cutoff = row[0].isoformat() if row and row[0] else None
    if not ids:
        return
    for role, sql, pids in (("batting", BAT_COUNTS_SQL, bat), ("pitching", PIT_COUNTS_SQL, pit)):
        cur.execute(sql, {"year": inputs.year, "ids": pids})
        for r in _dicts(cur):
            key = (r.pop("pid"), role, r.pop("kind_code"))
            inputs.counts[key] = {k: (int(v) if v is not None else None) for k, v in r.items()}
    cur.execute(_adv_sql(), {"ids": ids, "year": inputs.year})
    for r in _dicts(cur):
        inputs.advanced[(r.pop("acnt"), r.pop("role"))] = r
    # 冷熱箭頭：與球員頁走勢同一份聯盟基準與出賽定義（trend.py），各一次批次。
    from cpbl.api.routers import trend

    inputs.lg_obp, inputs.lg_slg = trend.league_batting_baseline(cur, inputs.year)
    inputs.lg_era = trend.league_era(cur, inputs.year)
    n = 2 * ARROW_POLICY["window"]
    inputs.recent = {**trend.recent_appearances(cur, bat, "batting", inputs.year, n=n),
                     **trend.recent_appearances(cur, pit, "pitching", inputs.year, n=n)}


def read_series(cur, inputs: RosterInputs) -> None:
    """本系列已完賽場次的各場兩隊 box 有無與逐人計數：各一次批次（與人數無關）。

    無完賽場 ⇒ 不查；box 有無與名單無關（名單缺席也照讀，否則會把已送達的場誤列待更新）。
    """
    snos = sorted({int(g["game_key"]["game_sno"]) for g in _series_games(inputs)})
    if not snos:
        return
    members = [m for r in (inputs.rosters or {}).values() if r for m in r["members"]]
    bat = sorted({m["player_id"] for m in members if role_of(m["official_position"]) == "batting"})
    pit = sorted({m["player_id"] for m in members if role_of(m["official_position"]) == "pitching"})
    args = {"year": inputs.year, "kind": inputs.series, "snos": snos}
    cur.execute(SERIES_BOX_SQL, args)
    for sno, vht, source in cur.fetchall():
        side = "away" if str(vht) == "1" else "home"
        inputs.series_box.setdefault(int(sno), {}).setdefault(side, set()).add(source)
    inputs.series_counts = {}
    for role, sql, pids in (("batting", SERIES_BAT_SQL, bat), ("pitching", SERIES_PIT_SQL, pit)):
        if not pids:
            continue
        cur.execute(sql, {**args, "ids": pids})
        for r in _dicts(cur):
            key = (r.pop("pid"), role)
            inputs.series_counts[key] = {k: (int(v) if v is not None else None) for k, v in r.items()}


def read_roster_inputs(cur, year: int, series: str, *, now: datetime, live_reader=None) -> RosterInputs:
    """讀 S02 context＋兩隊名單＋背景；查詢次數與名單人數無關。"""
    ctx = read_context(cur, year, now=now, live_reader=live_reader)
    inputs = RosterInputs(year=year, series=series, context=ctx)
    s = (ctx.get("series") or {}).get(series)
    teams = [t for t in (((s or {}).get("series_id") or {}).get("teams") or []) if t]
    if not teams:
        return inputs
    inputs.rosters = _optional(cur, lambda: read_rosters(cur, year, series, teams))
    cur.execute(TEAM_NAMES_SQL, {"teams": teams})
    inputs.team_names = {r[0]: r[1] for r in cur.fetchall()}
    read_background(cur, inputs)
    read_series(cur, inputs)
    return inputs


def playoffs_roster(year: int, series: str, *, now: datetime | None = None, connect: Callable | None = None,
                    live_reader=None) -> dict:
    """``playoffs-roster/v1``：單一 REPEATABLE READ READ ONLY 交易讀完全部來源。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(READ_ONLY_TXN)
            inputs = read_roster_inputs(cur, year, series, now=now, live_reader=live_reader)
    return compute_roster(inputs, now=now)


# —— 按需詳情（抽屜；契約 §2.2） ——————————————————————————————————————————

DETAIL_CONTRACT = "playoffs-roster-player/v1"


class NotInRoster(LookupError):
    """球員不在該系列兩隊已提交的名單內（或名單來源不可用）。"""


def player_detail_in_txn(cur, year: int, series: str, player_id: str, *, now: datetime, live_reader=None) -> dict:
    """單人能力卡＋本季走勢，與摘要同源 ``context_version``（同一交易讀 S02 context）。

    能力卡呼叫既有 ``ability._ability_card``（只 import、不改；⛔ 讀 reports/background）；走勢呼叫
    ``trend.trend_items``（球員頁同一份）。背景層級 A ⇒ 一軍走勢；D ⇒ 二軍走勢；none ⇒ 無走勢。
    """
    from cpbl.api.routers.ability import _ability_card
    from cpbl.api.routers.trend import trend_items

    ctx = read_context(cur, year, now=now, live_reader=live_reader)
    s = (ctx.get("series") or {}).get(series)
    teams = [t for t in (((s or {}).get("series_id") or {}).get("teams") or []) if t]
    rosters = _optional(cur, lambda: read_rosters(cur, year, series, teams)) if teams else None
    hit = next(((code, m) for code, r in (rosters or {}).items() if r for m in r["members"]
                if m["player_id"] == player_id), None)
    if hit is None:
        raise NotInRoster(player_id)
    team_code, m = hit
    role = role_of(m["official_position"])
    one = RosterInputs(year=year, series=series, context=ctx, rosters={team_code: {"members": [m]}})
    cur.execute(BAT_COUNTS_SQL if role == "batting" else PIT_COUNTS_SQL, {"year": year, "ids": [player_id]})
    for r in _dicts(cur):
        key = (r.pop("pid"), role, r.pop("kind_code"))
        one.counts[key] = {k: (int(v) if v is not None else None) for k, v in r.items()}
    level = ("A" if (one.counts.get((player_id, role, "A")) or {}).get("g")
             else "D" if (one.counts.get((player_id, role, "D")) or {}).get("g") else "none")
    trend = trend_items(cur, player_id, role, year, level) if level != "none" else None
    return {
        "contract": DETAIL_CONTRACT,
        "context_version": ctx.get("context_version"),
        "roster_version": _hash(rosters),
        "series": series,
        "year": year,
        "team_code": team_code,
        "player": {"player_id": player_id, "name": m["announced_name"], "official_position": m["official_position"],
                   **role_fields(m), "role": role, "level": level},
        "ability": {"season": _ability_card(cur, player_id, role, "season", year),
                    "career": _ability_card(cur, player_id, role, "career", year)},
        "trend": trend,
    }


def playoffs_roster_player(year: int, series: str, player_id: str, *, now: datetime | None = None,
                           connect: Callable | None = None, live_reader=None) -> dict:
    """``playoffs-roster-player/v1``：單一 REPEATABLE READ READ ONLY 交易。不在名單 ⇒ :class:`NotInRoster`。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(READ_ONLY_TXN)
            return player_detail_in_txn(cur, year, series, player_id, now=now, live_reader=live_reader)
