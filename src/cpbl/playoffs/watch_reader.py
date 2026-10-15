"""第 4 區 watch 讀取面（#289 S08 WP2）：4A 近期使用負荷＋官方先發投手狀態＋4B 未發布占位。

分兩層（沿 :mod:`cpbl.postseason_contract` 慣例）：

- :func:`read_watch_inputs`：薄 I/O，呼叫端已開好單一 ``REPEATABLE READ READ ONLY`` 交易；只 SELECT。
  查詢次數與名單人數無關（``ANY`` 批次）。
- :func:`compute_watch`：純組裝，同輸入同輸出；燈號規則全在 :mod:`cpbl.playoffs.watch_rules`。

紅線：

1. GET ⛔ 寫入、⛔ 觸發爬取；⛔ 讀 ``reports/background``／``reports/assembler``（#272 共享區）。
2. 名單未提交 ⇒ 不列投手，⛔ 以出賽紀錄反推名單（S03 三表是唯一來源）。
3. 覆蓋先判：該隊 D−3～D 每天的正式場都已完賽且有該隊投手 box，才算有證據；否則灰＋理由。
4. 4B：S09 未啟用 ⇒ A、B 兩格 ``not_published``「賽前快照尚未發布」，⛔ 包裝成已鎖定 B。
   指定已完賽場 ⇒ 歷史版本由 S09 提供（尚未發布），⛔ 以現在資料重算冒充當時版本。
6. 官方先發投手：來源歸 S11（#292），定案前恆 ``unknown``＋固定灰字（需求方裁定 E1／E2，
   issuecomment-6184481637）。本模組 ⛔ 讀 074（只有打序、沒有先發投手）、⛔ 讀 ``games.*_starter_id``，
   ⛔ 自建替代來源；S11 定案後只換 :func:`_starters` 的來源。
   ⚠️ 間接讀取仍在：:func:`read_watch_inputs` 經 S02 ``postseason_contract.read_series_inputs`` 會讀 074，
   列入 source manifest 並計入 ``context_version``；畫面不呈現。依需求方裁定 R2 乙（issuecomment-6184818006）
   暫留，待 S11（#292）定案時處理；⛔ 在本模組攔截（會讓 context_version 與 overview 永遠不一致）。
5. 當場 28 人登錄：S11 交付前恆 ``unknown``，⛔ 由名單或出賽推算。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from cpbl.api.between_games import date_trusted
from cpbl.api.helpers import _dicts
from cpbl.completion import completed_games_sql_with_evidence
from cpbl.coverage import taipei_date
from cpbl.playoffs import watch_rules as rules
from cpbl.playoffs.watch_rules import Appearance, DayCoverage

CONTRACT = "playoffs-watch/v1"

#: 預設展開的名單角色（PRD 4A）；其他投手可展開，不因角色未標記被刪除。
DEFAULT_ROLES = ("終結", "勝利組", "長中繼")
_ROLE_ORDER = {r: i for i, r in enumerate((*DEFAULT_ROLES, "輪值", "主力", "待命", "代打", "守備"))}

#: 負荷讀取涵蓋的正式賽別：一軍 A／E／C，加上可靠逐場紀錄的二軍 D（以 *022 隊碼對應）。
LOAD_KINDS = ("A", "E", "C", "D")
SCOPE_NOTE = ("近三日含一軍例行賽 A、季後 E／C 與二軍 D 已完賽正式場的投手逐場球數；"
              "未觀測熱身球與牛棚練投，不納入")

NOT_PUBLISHED_TEXT = "賽前快照尚未發布"
REGISTRATION_TEXT = "未知（當場登錄來源尚未接入）"
STARTER_UNKNOWN_TEXT = "官方先發投手：未知（來源尚未接入，S11）"


def farm_code(team_code: str) -> str | None:
    """一軍隊碼 → 二軍隊碼（``AAA011`` → ``AAA022``）。非 ``*011`` 形狀 ⇒ None。"""
    return team_code[:-3] + "022" if team_code and team_code.endswith("011") else None


@dataclass
class WatchInputs:
    """一次唯讀交易讀到的全部事實（測試可直接構造）。"""

    year: int
    series: str
    context: dict                                           # S02 compute_series_context 輸出
    requested_game: int | None = None
    rosters: dict[str, dict | None] | None = None          # team → 名單（只含投手）；None ⇒ 來源不可用
    window_games: list[dict] | None = None                 # 兩隊（含二軍）窗口內場次；None ⇒ 不可用
    appearances: dict[str, list[Appearance]] = field(default_factory=dict)
    appearances_ok: bool = True
    manifest: list[dict] = field(default_factory=list)


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def _key(gk: dict | None) -> tuple[int, str, int] | None:
    return (int(gk["year"]), str(gk["kind_code"]), int(gk["game_sno"])) if gk else None


def _as_date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


# —— 覆蓋判定（純） ——————————————————————————————————————————————————


def day_coverage(team_code: str, day: date, games: list[dict], *, target_key, target_date: date,
                 target_status: str | None) -> DayCoverage:
    """該隊（含二軍）某台北日期的覆蓋。

    - 當日無正式場 ⇒ 完整（有證據的 0）。
    - 完賽且有該隊 box ⇒ 完整；完賽但無 box ⇒ ``box_missing``。
    - 未完賽：目標場在 D 當天且尚未開打（scheduled／postponed）⇒ 以 0 計；進行中 ⇒ ``live_unobserved``
      （本版不接逐球即時球數）；其餘 ⇒ ``game_not_final``／``schedule_unavailable``。
    - 保留賽以開賽日 ``orig_date`` 與續賽日 ``game_date`` 都算該場的可能日期。
    """
    sides = {team_code, farm_code(team_code)}
    reasons: list[str] = []
    live = False
    for g in games:
        if g["away_team_code"] in sides:
            side = "away"
        elif g["home_team_code"] in sides:
            side = "home"
        else:
            continue
        dates = {_as_date(g["game_date"])}
        if g.get("delay_kind") == "保留" and g.get("orig_date") is not None:
            dates.add(_as_date(g["orig_date"]))
        if day not in dates:
            continue
        key = (int(g["year"]), g["kind_code"], int(g["game_sno"]))
        if g["completed"]:
            if not g[f"box_{side}"]:
                reasons.append("box_missing")
            continue
        if key == target_key and day == target_date:
            if target_status in ("scheduled", "postponed"):
                continue
            if target_status == "live":
                reasons.append("live_unobserved")
                live = True
            elif target_status == "unknown" or target_status is None:
                reasons.append("schedule_unavailable")
            else:
                reasons.append("game_not_final")
            continue
        reasons.append("game_not_final")
    reasons = list(dict.fromkeys(reasons))
    return DayCoverage(day, not reasons, tuple(reasons), live)


def appearance_of(row: dict) -> Appearance:
    """pitching_gamelog⋈games 一列 → :class:`Appearance`（保留賽列出兩個可能日期）。"""
    trusted = date_trusted(row)
    gd, od = _as_date(row["game_date"]), _as_date(row.get("orig_date"))
    possible = () if trusted else tuple(sorted({d for d in (od, gd) if d is not None}))
    cnt, div3 = row.get("inning_pitched_cnt"), row.get("inning_pitched_div3")
    outs = None if cnt is None and div3 is None else (cnt or 0) * 3 + (div3 or 0)
    return Appearance(
        game_key=(int(row["year"]), row["kind_code"], int(row["game_sno"])),
        date=gd, date_trusted=trusted, pitch_cnt=row.get("pitch_cnt"), outs=outs,
        er=row.get("earned_runs"), role_type=row.get("role_type"), possible_dates=possible,
    )


# —— 組裝（純） ——————————————————————————————————————————————————————


def _appearance_json(a: Appearance) -> dict:
    return {
        "game_key": {"year": a.game_key[0], "kind_code": a.game_key[1], "game_sno": a.game_key[2]},
        "date": a.date.isoformat() if a.date else None,
        "date_trusted": a.date_trusted,
        "role_type": a.role_type,
        "pitches": a.pitch_cnt,
        "outs": a.outs,
        "ip": None if a.outs is None else f"{a.outs // 3}.{a.outs % 3}",
    }


def _pitcher(member: dict, apps: list[Appearance], cov: dict, target_date: date) -> dict:
    role = member.get("tactical_role")
    load = rules.bullpen_load(target_date, apps, cov, tactical_role=role)
    out = {
        "player_id": member["player_id"],
        "name": member.get("announced_name"),
        "tactical_role": role,
        "role_source": "本站註記（非官方數據）",
        "default_visible": role in DEFAULT_ROLES,
        "load": load,
        "recent": [_appearance_json(a) for a in rules.recent_appearances(apps, 3)],
        "registration": {"status": "unknown", "text": REGISTRATION_TEXT},
        "consecutive_era": None,
    }
    if (load["metrics"].get("C") or 0) >= 2:
        out["consecutive_era"] = rules.consecutive_day_era([a for a in apps if a.game_key[1] == "A"])
    return out


def _starters(teams: list[str]) -> list[dict]:
    """官方先發投手：S11 來源定案前，每隊固定 unknown（⛔ 推測、⛔ 讀 074 打序或 games.*_starter_id）。"""
    return [{"team_code": t, "status": "unknown", "reason": "starter_source_not_delivered",
             "text": STARTER_UNKNOWN_TEXT} for t in teams]


def _publication() -> dict:
    return {
        "status": "not_published",
        "reason": "s09_not_enabled",
        "slots": [{"slot": s, "status": "not_published", "text": NOT_PUBLISHED_TEXT} for s in ("A", "B")],
    }


def compute_watch(inputs: WatchInputs, *, now: datetime) -> dict:
    """``playoffs-watch/v1``（JSON-able）。``now`` 只用於 ``as_of``，不影響燈號以外的判定。"""
    ctx = inputs.context
    series = inputs.series
    s = (ctx.get("series") or {}).get(series)
    st = ((ctx.get("state") or {}).get("by_series") or {}).get(series) or {}
    games_by_key = {_key(g["game_key"]): g for g in ctx.get("games") or []}
    target_key = _key(st.get("target_game_key"))
    envelope = {
        "contract": CONTRACT,
        "policy_version": rules.POLICY_VERSION,
        "year": inputs.year,
        "series": series,
        "series_id": s.get("series_id") if s else None,
        "context_version": ctx.get("context_version"),
        "target_game_key": st.get("target_game_key"),
        "requested_game_key": None,
        "as_of": {
            "now": now.isoformat(),
            "taipei_date": taipei_date(now).isoformat(),
            "last_refresh_at": (ctx.get("as_of") or {}).get("last_refresh_at"),
            "last_completed_game_date": (ctx.get("as_of") or {}).get("last_completed_game_date"),
        },
        "scope": {"kinds": list(LOAD_KINDS), "note": SCOPE_NOTE},
        "publication": _publication(),
        "registration": {"status": "unknown", "reason": "registration_source_not_delivered",
                         "text": REGISTRATION_TEXT},
    }

    def finish(status: str, missing: list[str], **body) -> dict:
        manifest = [*ctx.get("source_manifest", []), *inputs.manifest]
        out = {**envelope, "status": status, "missing_reason": list(dict.fromkeys(missing)),
               "source_manifest": manifest, **body}
        out["watch_version"] = _hash({k: v for k, v in out.items() if k not in ("as_of",)}
                                     | {"manifest": [{k: v for k, v in m.items() if k != "observed_at"}
                                                     for m in manifest]})
        return out

    if s is None:
        return finish("series_unknown", ["series_not_in_context"], coverage="unknown", teams=[])

    if inputs.requested_game is not None:
        req = (inputs.year, series, int(inputs.requested_game))
        envelope["requested_game_key"] = {"year": req[0], "kind_code": req[1], "game_sno": req[2]}
        g = games_by_key.get(req)
        if g is None:
            return finish("game_unknown", ["game_not_in_series"], coverage="unknown", teams=[])
        if req != target_key:
            if g.get("completed"):
                return finish("historical_not_published", ["s09_not_enabled"], coverage="unknown", teams=[],
                              text="歷史賽前版本由 S09 提供，尚未發布")
            return finish("not_target", ["only_current_target_supported"], coverage="unknown", teams=[],
                          text="只提供系列目前目標場")

    if target_key is None or target_key not in games_by_key:
        return finish("no_target", ["target_game_pending"], coverage="unknown", teams=[],
                      text="下一場安排待定")
    tg = games_by_key[target_key]
    if tg.get("completed"):
        # 系列已決定時 S02 目標停在最後一場已完賽場：同樣不以現在資料重算冒充當時賽前版本。
        return finish("historical_not_published", ["s09_not_enabled"], coverage="unknown", teams=[],
                      text="歷史賽前版本由 S09 提供，尚未發布")
    target_date = _as_date(tg.get("game_date"))
    target_status = tg.get("target_status")
    teams = [tg["away_team_code"], tg["home_team_code"]]
    missing: list[str] = ["s09_not_enabled", "registration_source_not_delivered", "starter_source_not_delivered"]
    if target_date is None:
        missing.append("target_date_unknown")

    team_out = []
    complete_flags: list[bool] = []
    for side, code in zip(("away", "home"), teams, strict=True):
        if inputs.rosters is None:
            roster, roster_status = None, "unavailable"
        else:
            roster = inputs.rosters.get(code)
            roster_status = "submitted" if roster else "missing"
        if roster_status != "submitted":
            missing.append(f"roster_{roster_status}:{code}")
        days = []
        cov: dict[date, DayCoverage] = {}
        if target_date is not None:
            for k in rules.WINDOW_OFFSETS:
                d = target_date - timedelta(days=k)
                if inputs.window_games is None:
                    cov[d] = DayCoverage(d, False, ("schedule_unavailable",))
                else:
                    cov[d] = day_coverage(code, d, inputs.window_games, target_key=target_key,
                                          target_date=target_date, target_status=target_status)
                c = cov[d]
                days.append({"date": d.isoformat(), "offset": k, "complete": c.complete,
                             "reasons": list(c.reasons), "text": [rules.REASON_TEXT[r] for r in c.reasons],
                             "live": c.live})
        pitchers = []
        if roster and target_date is not None:
            for m in roster["members"]:
                apps = inputs.appearances.get(m["player_id"], []) if inputs.appearances_ok else []
                pcov = cov if inputs.appearances_ok else {
                    d: DayCoverage(d, False, ("no_source",)) for d in cov}
                p = _pitcher(m, apps, pcov, target_date)
                pitchers.append(p)
                complete_flags.append(p["load"]["complete"])
            pitchers.sort(key=lambda p: (not p["default_visible"], _ROLE_ORDER.get(p["tactical_role"] or "", 99),
                                         p["player_id"]))
        for d in days:
            missing.extend(d["reasons"])
        team_out.append({
            "side": side,
            "team_code": code,
            "roster_status": roster_status,
            "roster": None if not roster else {
                "roster_id": roster["roster_id"], "published_date": roster.get("published_date"),
                "source_url": roster.get("source_url"), "annotation_version": roster.get("annotation_version"),
                "note": "資格名單：不代表先發、當場 28 人登錄或可用",
            },
            "roster_text": None if roster else "32 人名單尚未提交" if roster_status == "missing"
            else "名單來源暫時無法讀取",
            "days": days,
            "pitchers": pitchers,
        })
    if not inputs.appearances_ok:
        missing.append("pitching_gamelog_unavailable")
    coverage = ("unknown" if not complete_flags else "complete" if all(complete_flags)
                else "partial" if any(complete_flags) else "incomplete")
    return finish(
        "ok", missing,
        coverage=coverage,
        target={"game_key": st.get("target_game_key"), "game_date": target_date.isoformat() if target_date else None,
                "target_status": target_status, "away_team_code": teams[0], "home_team_code": teams[1]},
        starters=_starters(teams),
        teams=team_out,
    )


# —— 讀取（薄 I/O） ————————————————————————————————————————————————————

_DONE = completed_games_sql_with_evidence("g", "%(as_of)s")

ROSTER_SQL = """
    SELECT r.team_code, r.roster_id::text AS roster_id, r.published_date, r.source_url,
           lv.rev AS annotation_version, m.player_id, m.announced_name, a.tactical_role
      FROM cpbl.series_roster r
      JOIN cpbl.series_roster_member m ON m.roster_id = r.roster_id AND m.official_position = '投手'
      LEFT JOIN LATERAL (SELECT max(x.revision) AS rev FROM cpbl.roster_annotation_revision x
                          WHERE x.roster_id = r.roster_id) lv ON TRUE
      LEFT JOIN cpbl.roster_annotation_revision a
             ON a.roster_id = r.roster_id AND a.player_id = m.player_id AND a.revision = lv.rev
     WHERE r.year = %(year)s AND r.kind_code = %(kind)s AND r.team_code = ANY(%(teams)s)
     ORDER BY r.team_code, m.player_id
"""

WINDOW_GAMES_SQL = f"""
    SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.orig_date, g.delay_kind,
           g.away_team_code, g.home_team_code,
           COALESCE({_DONE}, FALSE) AS completed,
           EXISTS (SELECT 1 FROM cpbl.pitching_gamelog p
                    WHERE p.year = g.year AND p.kind_code = g.kind_code AND p.game_sno = g.game_sno
                      AND p.visiting_home_type = '1') AS box_away,
           EXISTS (SELECT 1 FROM cpbl.pitching_gamelog p
                    WHERE p.year = g.year AND p.kind_code = g.kind_code AND p.game_sno = g.game_sno
                      AND p.visiting_home_type = '2') AS box_home
      FROM cpbl.games g
     WHERE g.kind_code = ANY(%(kinds)s)
       AND (g.away_team_code = ANY(%(teams)s) OR g.home_team_code = ANY(%(teams)s))
       AND (g.game_date BETWEEN %(lo)s AND %(hi)s
            OR (g.delay_kind = '保留' AND g.orig_date BETWEEN %(lo)s AND %(hi)s))
     ORDER BY g.game_date, g.kind_code, g.game_sno
"""

# 登板讀取：已完賽場之外，**也收**「有投球紀錄但缺 games 列或缺 game_date」的列——這些列日期不可判定，
# 交給規則層判灰（date_missing）。⛔ 以 JOIN／日期條件先濾掉它們：濾掉後窗口看起來無投球，負荷會誤綠
# （#289 審核 R1）。未完賽但有日期的場次照舊不收，其窗口日由 day_coverage 判 game_not_final。
APPEARANCES_SQL = f"""
    SELECT p.pitcher_acnt, p.year, p.kind_code, p.game_sno, g.game_date, g.orig_date, g.delay_kind,
           p.pitch_cnt, p.inning_pitched_cnt, p.inning_pitched_div3, p.earned_runs, p.role_type
      FROM cpbl.pitching_gamelog p
      LEFT JOIN cpbl.games g ON g.year = p.year AND g.kind_code = p.kind_code AND g.game_sno = p.game_sno
     WHERE p.year = %(year)s AND p.kind_code = ANY(%(kinds)s) AND p.pitcher_acnt = ANY(%(ids)s)
       AND (g.game_sno IS NULL OR g.game_date IS NULL OR {_DONE})
     ORDER BY p.pitcher_acnt, g.game_date NULLS FIRST, p.kind_code, p.game_sno
"""

def _optional(cur, fn):
    """非核心來源失敗只降級（回 None），以 SAVEPOINT 隔離，不讓交易進入 aborted。"""
    connection = getattr(cur, "connection", None)
    try:
        if connection is not None and hasattr(connection, "transaction"):
            with connection.transaction():
                return fn()
        return fn()
    except Exception:  # noqa: BLE001 — 缺表／權限：該來源 unavailable＋missing_reason
        return None


def read_watch_inputs(cur, year: int, series: str, *, now: datetime, requested_game: int | None = None,
                      live_reader=None) -> WatchInputs:
    """讀 S02 context＋名單＋窗口場次＋投手登板；查詢次數與投手人數無關。"""
    from cpbl import postseason_contract as contract

    ctx = contract.compute_series_context(
        contract.read_series_inputs(cur, year, now=now, live_reader=live_reader), now=now)
    inputs = WatchInputs(year=year, series=series, context=ctx, requested_game=requested_game)
    observed = now.isoformat()
    st = ((ctx.get("state") or {}).get("by_series") or {}).get(series) or {}
    target = _key(st.get("target_game_key"))
    tg = next((g for g in ctx.get("games") or [] if _key(g["game_key"]) == target), None)
    if tg is None or target is None or (requested_game is not None and int(requested_game) != target[2]):
        return inputs
    teams = [tg["away_team_code"], tg["home_team_code"]]
    target_date = _as_date(tg["game_date"])
    as_of = taipei_date(now)

    def roster_read():
        cur.execute(ROSTER_SQL, {"year": year, "kind": series, "teams": teams})
        out: dict[str, dict | None] = {t: None for t in teams}
        for r in _dicts(cur):
            ros = out.get(r["team_code"]) or {
                "roster_id": r["roster_id"], "published_date": str(r["published_date"]),
                "source_url": r["source_url"], "annotation_version": r["annotation_version"], "members": []}
            ros["members"].append({"player_id": r["player_id"], "announced_name": r["announced_name"],
                                   "tactical_role": r["tactical_role"]})
            out[r["team_code"]] = ros
        return out

    inputs.rosters = _optional(cur, roster_read)
    inputs.manifest.append({"source": "series_roster", "scope": f"{year}/{series}/{','.join(teams)}",
                            "version_or_hash": _hash(inputs.rosters), "observed_at": observed,
                            "status": "ok" if inputs.rosters is not None else "unavailable"})

    codes = [c for t in teams for c in (t, farm_code(t)) if c]
    if target_date is not None:
        def window_read():
            cur.execute(WINDOW_GAMES_SQL, {"kinds": list(LOAD_KINDS), "teams": codes, "as_of": as_of,
                                           "lo": target_date - timedelta(days=3), "hi": target_date})
            return _dicts(cur)
        inputs.window_games = _optional(cur, window_read)
    inputs.manifest.append({"source": "window_games", "scope": f"{target_date}-3d/{','.join(codes)}",
                            "version_or_hash": _hash(inputs.window_games), "observed_at": observed,
                            "status": "ok" if inputs.window_games is not None else "unavailable"})

    ids = sorted({m["player_id"] for r in (inputs.rosters or {}).values() if r for m in r["members"]})
    if ids:
        def apps_read():
            cur.execute(APPEARANCES_SQL, {"year": year, "kinds": list(LOAD_KINDS), "ids": ids, "as_of": as_of})
            return _dicts(cur)
        rows = _optional(cur, apps_read)
        inputs.appearances_ok = rows is not None
        for r in rows or []:
            inputs.appearances.setdefault(r["pitcher_acnt"], []).append(appearance_of(r))
        inputs.manifest.append({"source": "pitching_gamelog", "scope": f"{year}/{','.join(LOAD_KINDS)}",
                                "version_or_hash": _hash(rows), "observed_at": observed,
                                "status": "ok" if rows is not None else "unavailable"})

    return inputs


READ_ONLY_TXN = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"


def playoffs_watch(year: int, series: str, *, game: int | None = None, now: datetime | None = None,
                   connect: Callable | None = None, live_reader=None) -> dict:
    """``playoffs-watch/v1``：單一 REPEATABLE READ READ ONLY 交易讀完全部來源。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(READ_ONLY_TXN)
            inputs = read_watch_inputs(cur, year, series, now=now, requested_game=game, live_reader=live_reader)
    return compute_watch(inputs, now=now)
