"""第 4 區 watch 讀取面（#289 S08 WP2）：4A 近期使用負荷＋官方先發投手狀態。

分兩層（沿 :mod:`cpbl.postseason_contract` 慣例）：

- :func:`read_watch_inputs`：薄 I/O，呼叫端已開好單一 ``REPEATABLE READ READ ONLY`` 交易；只 SELECT。
  查詢次數與名單人數無關（``ANY`` 批次）。
- :func:`compute_watch`：純組裝，同輸入同輸出；燈號規則全在 :mod:`cpbl.playoffs.watch_rules`。

紅線：

1. GET ⛔ 寫入、⛔ 觸發爬取；⛔ 讀 ``reports/background``／``reports/assembler``（#272 共享區）。
2. 名單未提交 ⇒ 不列投手，⛔ 以出賽紀錄反推名單（S03 三表是唯一來源）。
3. 覆蓋先判：該隊 D−3～D 每天的正式場都已完賽且有該隊投手 box，才算有證據；否則灰＋理由。
4. 4B 賽前快照（S09）已停止（#290；#314 移除占位與 ``s09_not_enabled``），回應不再帶 ``publication``。
   指定已完賽場或系列已結束 ⇒ 只回固定文字（``historical_not_supported``），⛔ 以現在資料重算冒充當時版本。
6. 官方先發投手（#314）：讀 S11（#292）已送達的 ``game_schedule_status_revisions`` 目標場**現行列**
   （選列＝``OFFICIAL_SCHEDULE_ORDER_BY``／:func:`cpbl.api.helpers.official_status` 同一份規則）。
   現行列不是賽前（延賽／保留／終場／未知）、日期或主客隊不符、先發欄空 ⇒「待公告」；讀取失敗 ⇒
   ``unknown``「暫時無法取得」（⛔ 冒充待公告或已公告）。只顯示最新一筆，⛔ 標更換、⛔ 呈現歷程；官方
   沒有公告時刻欄，``fetched_at``／``last_seen_at`` 只是本站觀測時刻 ⇒ 回應 ⛔ 帶任何公告時間。
   本模組 ⛔ 讀 074（只有打序、沒有先發投手）、⛔ 讀 ``games.*_starter_id``（原地覆寫、看不出屬哪一版官方
   狀態）、⛔ 推測。姓名順位：官方列姓名 → ``players.name`` → ``pitching_gamelog.pitcher_name``；
   三者皆無 ⇒「已公告（姓名待更新）」，⛔ 顯示 acnt。
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

from cpbl.api.helpers import OFFICIAL_SCHEDULE_ORDER_BY, _dicts, official_status
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

REGISTRATION_TEXT = "未知（當場登錄來源尚未接入）"
STARTER_PENDING_TEXT = "待公告"
STARTER_NAME_MISSING_TEXT = "已公告（姓名待更新）"
STARTER_UNAVAILABLE_TEXT = "暫時無法取得"
HISTORICAL_TEXT = "本場已完賽，觀戰重點只提供系列下一場"


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
    #: 目標場官方賽程修訂列（全部版本，選列交 :func:`official_starters`）；None ⇒ 來源不可用或未讀。
    official_schedule: list[dict] | None = None
    #: acnt → {"player_name", "gamelog_name"}（姓名第二、三順位）。
    starter_names: dict[str, dict] = field(default_factory=dict)
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
    - 未完賽的場次只有一種情況可當「有證據的 0」：它是目標場、在 D 當天、官方仍為 scheduled／postponed，
      **而且該隊沒有任何投球紀錄**。已有紀錄卻未核定完賽 ⇒ ``target_box_unverified``（灰，已知球數照列；
      ⛔ 當成完整的賽前數值——#289 審核第 3 輪）。進行中 ⇒ ``live_unobserved``＋即時標記（本版不接逐球
      即時球數）；狀態未知 ⇒ ``schedule_unavailable``；其餘未完賽 ⇒ ``game_not_final``。
    - 保留賽以 [開賽日 ``orig_date``, 續賽日 ``game_date``] 整段區間都算該場的可能日期（與
      :func:`pitch_dates` 同一判準）。
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
        gd, od = _as_date(g["game_date"]), _as_date(g.get("orig_date"))
        if g.get("delay_kind") == "保留" and od is not None and gd is not None and od <= gd:
            in_day = od <= day <= gd
        else:
            in_day = day in {gd, od} if g.get("delay_kind") == "保留" else day == gd
        if not in_day:
            continue
        key = (int(g["year"]), g["kind_code"], int(g["game_sno"]))
        if g["completed"]:
            if not g[f"box_{side}"]:
                reasons.append("box_missing")
            continue
        if key == target_key and day == target_date:
            if target_status in ("scheduled", "postponed"):
                if g[f"box_{side}"]:
                    reasons.append("target_box_unverified")
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


#: 實際比賽日＝``game_date`` 的 delay_kind（migration 041：``'延賽' | '保留' | NULL``）。延賽的 ``orig_date``
#: 是原定日、不是投球日；保留賽跨日。值域外的 delay_kind 語意未知 ⇒ 不可信。
_ACTUAL_DATE_KINDS = (None, "延賽")


def pitch_dates(row: dict) -> tuple[bool, tuple[date, ...]]:
    """一筆登板的實際投球日證據 → (日期可信, 完整候選日集合)。

    投球日只能由 ``games`` 的 ``game_date``／``delay_kind``／``orig_date`` 推出（``pitching_gamelog``
    沒有日期欄）。**不變量**：日期不可信時，回傳的候選集合必須是「完整的」，空 tuple 表示無界（任何日期都
    可能）。規則層只在候選集合完整、且全部落在窗口外時才把它排除（#289 審核 R1／第 2 輪：只放
    ``orig_date`` 這種不完整的集合會讓缺實際日期的登板被當成窗口外而誤綠）。

    - 可信：``game_date`` 有值，且 delay_kind 為 NULL 或延賽 ⇒ 投球日＝``game_date``。
    - 保留賽且 ``orig_date <= game_date`` 都有值 ⇒ 候選＝[開賽日, 續賽日] 整段區間（中途可能再中止，
      中間日期也算候選）。
    - 其他一律無界：缺 games 列、缺 ``game_date``（不論 orig_date 有無、在不在窗口）、保留賽缺開賽日或
      開賽日晚於續賽日、值域外 delay_kind。
    """
    gd, od, dk = _as_date(row.get("game_date")), _as_date(row.get("orig_date")), row.get("delay_kind")
    if gd is not None and dk in _ACTUAL_DATE_KINDS:
        return True, ()
    if gd is not None and dk == "保留" and od is not None and od <= gd:
        return False, tuple(od + timedelta(days=i) for i in range((gd - od).days + 1))
    return False, ()


def appearance_of(row: dict) -> Appearance:
    """pitching_gamelog⟕games 一列 → :class:`Appearance`（日期證據見 :func:`pitch_dates`）。"""
    trusted, possible = pitch_dates(row)
    cnt, div3 = row.get("inning_pitched_cnt"), row.get("inning_pitched_div3")
    outs = None if cnt is None and div3 is None else (cnt or 0) * 3 + (div3 or 0)
    return Appearance(
        game_key=(int(row["year"]), row["kind_code"], int(row["game_sno"])),
        date=_as_date(row.get("game_date")), date_trusted=trusted, pitch_cnt=row.get("pitch_cnt"), outs=outs,
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


def _clean(v) -> str | None:
    v = str(v).strip() if v is not None else ""
    return v or None


def official_starters(rows: list[dict] | None, *, target_date: date | None, teams: list[str],
                      names: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """官方賽程現行列 → 兩隊（客、主）先發投手狀態＋missing_reason（純，紅線 6）。

    - ``rows`` 為 None（讀取失敗）⇒ 兩隊 ``unknown``「暫時無法取得」。
    - 現行列（:func:`official_status` 選列）不是 ``scheduled``、日期≠目標日、主客隊碼≠目標場 ⇒ 兩隊「待公告」。
    - 否則逐隊：先發欄空 ⇒「待公告」；有 acnt ⇒ ``announced``，姓名依三順位，皆無 ⇒「已公告（姓名待更新）」。
    """
    if rows is None:
        return ([{"team_code": t, "status": "unknown", "reason": "starter_source_unavailable", "player_id": None,
                  "name": None, "text": STARTER_UNAVAILABLE_TEXT} for t in teams], ["starter_source_unavailable"])
    status, row = official_status(rows)
    gate = None
    if row is None:
        gate = "official_schedule_missing"
    elif status != "scheduled":
        gate = f"official_schedule_{status}"
    elif target_date is None or _as_date(row.get("raw_game_date")) != target_date:
        gate = "official_schedule_date_mismatch"
    elif [row.get("visiting_team_code"), row.get("home_team_code")] != list(teams):
        gate = "official_schedule_team_mismatch"
    out: list[dict] = []
    missing: list[str] = []
    for side, code in zip(("visiting", "home"), teams, strict=True):
        acnt = None if gate else _clean(row.get(f"{side}_pitcher_acnt"))
        if acnt is None:
            out.append({"team_code": code, "status": "pending", "reason": gate or "starter_not_announced",
                        "player_id": None, "name": None, "text": STARTER_PENDING_TEXT})
            missing.append(f"starter_not_announced:{code}")
            continue
        n = names.get(acnt) or {}
        name = (_clean(row.get(f"{side}_pitcher_name")) or _clean(n.get("player_name"))
                or _clean(n.get("gamelog_name")))
        out.append({"team_code": code, "status": "announced", "reason": None if name else "starter_name_missing",
                    "player_id": acnt, "name": name, "text": name or STARTER_NAME_MISSING_TEXT})
        if name is None:
            missing.append(f"starter_name_missing:{code}")
    return out, missing


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
                return finish("historical_not_published", ["historical_not_supported"], coverage="unknown",
                              teams=[], text=HISTORICAL_TEXT)
            return finish("not_target", ["only_current_target_supported"], coverage="unknown", teams=[],
                          text="只提供系列目前目標場")

    if target_key is None or target_key not in games_by_key:
        return finish("no_target", ["target_game_pending"], coverage="unknown", teams=[],
                      text="下一場安排待定")
    tg = games_by_key[target_key]
    if tg.get("completed"):
        # 系列已決定時 S02 目標停在最後一場已完賽場：同樣不以現在資料重算冒充當時賽前版本。
        return finish("historical_not_published", ["historical_not_supported"], coverage="unknown", teams=[],
                      text=HISTORICAL_TEXT)
    target_date = _as_date(tg.get("game_date"))
    target_status = tg.get("target_status")
    teams = [tg["away_team_code"], tg["home_team_code"]]
    starters, starter_missing = official_starters(inputs.official_schedule, target_date=target_date, teams=teams,
                                                  names=inputs.starter_names)
    missing: list[str] = ["registration_source_not_delivered", *starter_missing]
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
        starters=starters,
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

# 登板讀取：名單投手本季**所有**登板列都收，⛔ 以 JOIN、日期或完賽條件先濾掉（#289 審核 R1）。被濾掉的
# 登板在窗口裡看起來就是「沒投」，負荷會誤綠。日期是否可信交給 :func:`pitch_dates`＋規則層判；
# 未完賽場次的窗口日另由 :func:`day_coverage` 判 game_not_final（灰，已知球數照列）。
APPEARANCES_SQL = """
    SELECT p.pitcher_acnt, p.year, p.kind_code, p.game_sno, g.game_date, g.orig_date, g.delay_kind,
           p.pitch_cnt, p.inning_pitched_cnt, p.inning_pitched_div3, p.earned_runs, p.role_type
      FROM cpbl.pitching_gamelog p
      LEFT JOIN cpbl.games g ON g.year = p.year AND g.kind_code = p.kind_code AND g.game_sno = p.game_sno
     WHERE p.year = %(year)s AND p.kind_code = ANY(%(kinds)s) AND p.pitcher_acnt = ANY(%(ids)s)
     ORDER BY p.pitcher_acnt, g.game_date NULLS FIRST, p.kind_code, p.game_sno
"""

# 官方先發（紅線 6）：目標場全部修訂列（單場通常 1–3 列，走 idx_game_schedule_status_revisions_latest），
# 以同一份選列規則排序；選列在 :func:`official_starters` 經 :func:`official_status` 再做一次（防呆，同構全序）。
OFFICIAL_SCHEDULE_SQL = f"""
    SELECT raw_present_status, raw_game_result, raw_game_date, payload_hash, fetched_at, last_seen_at,
           raw_payload->>'VisitingTeamCode' AS visiting_team_code,
           raw_payload->>'HomeTeamCode' AS home_team_code,
           NULLIF(btrim(raw_payload->>'VisitingPitcherAcnt'), '') AS visiting_pitcher_acnt,
           NULLIF(btrim(raw_payload->>'HomePitcherAcnt'), '') AS home_pitcher_acnt,
           NULLIF(btrim(raw_payload->>'VisitingPitcherName'), '') AS visiting_pitcher_name,
           NULLIF(btrim(raw_payload->>'HomePitcherName'), '') AS home_pitcher_name
      FROM cpbl.game_schedule_status_revisions
     WHERE year = %(year)s AND kind_code = %(kind)s AND game_sno = %(sno)s
     ORDER BY {OFFICIAL_SCHEDULE_ORDER_BY}
"""

# 姓名第二、三順位（批次 ANY，次數固定）：players.name；缺者以 pitching_gamelog 最近一筆非空姓名補
# （逐場表無日期欄，「最近」＝year、game_sno 遞減，跨賽別時只是近似；只用於補名，不影響狀態）。
STARTER_NAMES_SQL = """
    SELECT a.acnt, p.name AS player_name, gl.pitcher_name AS gamelog_name
      FROM unnest(%(ids)s::text[]) AS a(acnt)
      LEFT JOIN cpbl.players p ON p.id = a.acnt
      LEFT JOIN LATERAL (SELECT x.pitcher_name FROM cpbl.pitching_gamelog x
                          WHERE x.pitcher_acnt = a.acnt AND NULLIF(btrim(x.pitcher_name), '') IS NOT NULL
                          ORDER BY x.year DESC, x.game_sno DESC LIMIT 1) gl ON TRUE
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

    def starters_read():
        cur.execute(OFFICIAL_SCHEDULE_SQL, {"year": target[0], "kind": target[1], "sno": target[2]})
        rows = _dicts(cur)
        _, sel = official_status(rows)
        ids = sorted({a for a in ((sel or {}).get("visiting_pitcher_acnt"), (sel or {}).get("home_pitcher_acnt"))
                      if a})
        names: dict[str, dict] = {}
        if ids:
            cur.execute(STARTER_NAMES_SQL, {"ids": ids})
            names = {r["acnt"]: r for r in _dicts(cur)}
        return rows, names

    got = _optional(cur, starters_read)
    if got is not None:
        inputs.official_schedule, inputs.starter_names = got
    sel = official_status(inputs.official_schedule)[1] if inputs.official_schedule else None
    inputs.manifest.append({"source": "official_starters", "scope": f"{target[0]}/{target[1]}/{target[2]}",
                            "version_or_hash": (sel or {}).get("payload_hash") or _hash(inputs.official_schedule),
                            "observed_at": observed,
                            "status": "ok" if inputs.official_schedule is not None else "unavailable"})

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
