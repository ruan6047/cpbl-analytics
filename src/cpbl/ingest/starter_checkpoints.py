"""#292 A1：先發查核時點（開賽前 1h／0.5h、比賽結束後 1h）的純函式。

掛在 #268 晚間鏈（需求方 D1＝H1）：``postseason_evening.plan`` 在旗標開啟時呼叫本模組決定
「這次喚醒要不要為先發查核抓一次 www」，抓取本身仍是既有 ``_postseason_games_step``（www
getgamedatas，整賽別一次），寫入仍是既有 ``games``＋``game_schedule_status_revisions``，送達仍是
既有 ``POSTSEASON_RESULTS_ONLY`` 同步。本模組**不連網、不碰 DB、不 import 晚間鏈**；閘門
（讓位 10:10、挑戰停、冷卻）由呼叫端判斷後傳入。

時點（需求已鎖，#292 6184111089；容許窗 D9、有界重送 D2，規劃確認 6184976448）：

* ``S-60``：S−60 分起、最遲 S−40 分（保留 S−30 的 20 分冷卻）；失敗不重送（S−30 即下一次）。
* ``S-30``：S−30 分起、須早於開賽（S 本身不含）；失敗於 ≥20 分後重送 1 次，仍須早於 S。
* ``F+60``：F+60 分起、最遲 F+90 分；失敗於 ≥20 分後重送 1 次，仍須在 F+90 之前。
* 挑戰類失敗一律不重送；鎖被占、冷卻、讓位只延後、不計次；超過最遲時刻記 ``missed``
  （或被挑戰停／對帳停擋下時記 ``blocked``），⛔ 事後補打。

S＝狀態檔中最近一次 stats ``PreExeDate``（台北無時區字串）；www ``GameDateTimeS`` 只並列記錄，
不一致時以 stats 為準（``start_mismatch``）。取不到 S ⇒ ``start_time_unknown``、不觸發。
F＝**本機首次觀測**到 stats ``FINISHED`` 的時刻（官方結束時刻不可得；最多晚約一個喚醒間隔）。
S−60／S−30 只對未開打場次；F+60 只對已完賽場次；延賽／保留沒有完賽 ⇒ F+60 記 ``no_final``，
改期後以新的 S 產生新的時點（紀錄 id 含錨點時刻）。

⚠️ 時間語意：本模組產出的每個時刻都是**本機**的查詢或觀測時刻（``fired_at``、``attempts[].at``、
``finished_first_seen``），⛔ 不是官方公布時刻，也⛔ 不產生任何「公布時刻」欄位。F+60 的觀測
標 ``phase=postgame``，不是賽前公告。
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
RETRY_AFTER = timedelta(minutes=20)
# stats GameStatus 中「已不是賽前」的官方原字（其餘一律視為未開打；未知字串寧可多查一次）。
NOT_PREGAME = frozenset({"START", "FINISHED", "POSTPONED", "RESERVED"})
NO_FINAL = frozenset({"POSTPONED", "RESERVED"})
# 等待原因中屬「被停止機制擋下」者：逾時記 blocked，其餘逾時記 missed。
BLOCKING_WAITS = frozenset({"www_blocked", "sync_blocked"})


@dataclass(frozen=True)
class Point:
    name: str
    anchor: str             # start（S）／final（F）
    offset: timedelta       # 需求時點＝錨點＋offset
    deadline: timedelta     # 容許窗最遲＝錨點＋deadline（D9）
    retry: bool             # D2：失敗後 ≥20 分可再試 1 次
    phase: str              # pregame／postgame
    # 最遲時刻本身算不算窗內。D9 原話：1h「最遲到開賽前 40 分」、終場後「最遲 90 分」含端點；
    # 0.5h「最遲開賽前」＝必須早於開賽，開賽整點已不是賽前（#292 審核阻擋 2）。
    deadline_inclusive: bool = True


POINTS: tuple[Point, ...] = (
    Point("S-60", "start", timedelta(minutes=-60), timedelta(minutes=-40), False, "pregame"),
    Point("S-30", "start", timedelta(minutes=-30), timedelta(0), True, "pregame",
          deadline_inclusive=False),
    Point("F+60", "final", timedelta(minutes=60), timedelta(minutes=90), True, "postgame"),
)
_BY_NAME = {p.name: p for p in POINTS}


def flag_path() -> Path:
    """旗標檔：存在＝開啟。啟停是單一步驟（touch／rm），下次喚醒生效、不需重新 bootstrap。"""
    return Path(os.environ.get("POSTSEASON_STARTER_FLAG",
                               "logs/postseason-starter-checkpoints.enabled"))


def _iso(at: datetime | None) -> str | None:
    return at.astimezone(UTC).isoformat() if at else None


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    at = datetime.fromisoformat(ts)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _starts(raw: object) -> datetime | None:
    """stats PreExeDate（台北無時區）→ aware。解析不了＝未知（不猜）。"""
    if not raw:
        return None
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return at.replace(tzinfo=TAIPEI) if at.tzinfo is None else at


def _key(g: Mapping) -> str:
    return f"{g['year']}-{g['kind_code']}-{g['game_sno']}"


def kind_of(record_id: str) -> str:
    return record_id.split("|", 1)[0].split("-")[1]


def _hhmm(raw: object) -> str | None:
    m = re.search(r"(\d{1,2}):(\d{2})", str(raw or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def note_finished(finished: dict, schedule: Iterable[Mapping], now: datetime) -> None:
    """F 的近似：每場第一次在 stats 看到 FINISHED 的本機時刻（只記第一次，之後不改）。"""
    for g in schedule:
        if g.get("status") == "FINISHED":
            finished.setdefault(_key(g), _iso(now))


def _new_record(key: str, point: Point, anchor: datetime | None, g: Mapping,
                www_starts: Mapping[str, str | None] | None) -> dict[str, Any]:
    due = anchor + point.offset if anchor else None
    rec: dict[str, Any] = {
        "key": key, "point": point.name, "phase": point.phase,
        "anchor": point.anchor, "anchor_at": _iso(anchor),
        "due_at": _iso(due), "deadline_at": _iso(anchor + point.deadline) if anchor else None,
        "deadline_inclusive": point.deadline_inclusive,
        "fired_at": None, "kinds": [str(g["kind_code"])], "outcome": None, "sync_code": None,
        "reason": None, "wait_reason": None, "done": False, "attempts": [],
        "stats_starts_at": g.get("starts_at"),
    }
    if www_starts is not None:
        www = www_starts.get(key)
        stats_hhmm, www_hhmm = _hhmm(g.get("starts_at")), _hhmm(www)
        rec["www_start_raw"] = www
        rec["start_mismatch"] = (None if stats_hhmm is None or www_hhmm is None
                                 else stats_hhmm != www_hhmm)
    return rec


def _finish(rec: dict, outcome: str, reason: str | None) -> None:
    rec.update(done=True, outcome=outcome, reason=reason)


def _in_window(rec: Mapping, now: datetime) -> bool:
    at, deadline = _parse(rec.get("due_at")), _parse(rec.get("deadline_at"))
    if at is None or deadline is None or now < at:
        return False
    return now <= deadline if _BY_NAME[rec["point"]].deadline_inclusive else now < deadline


def _past_deadline(rec: Mapping, now: datetime) -> bool:
    deadline = _parse(rec.get("deadline_at"))
    if deadline is None:
        return False
    return now > deadline if _BY_NAME[rec["point"]].deadline_inclusive else now >= deadline


def materialize(checkpoints: dict, schedule: Iterable[Mapping], finished: Mapping[str, str],
                now: datetime, since: datetime,
                www_starts: Mapping[str, str | None] | None = None) -> None:
    """依目前已知賽程產生「已到時點」的紀錄（到點才建；旗標開啟前就到點的不補建）。

    同一場改期 ⇒ 錨點不同 ⇒ 新紀錄；舊錨點的待辦紀錄**一看到新時程就結清**（未查過 missed、等重送
    failed，原因 ``rescheduled``；開賽時刻消失則 ``start_time_unknown``），不刪、不改寫歷史，也⛔ 再以
    舊錨點抓取（PLAN §5：依最新 PreExeDate 重排；#292 審核阻擋 1）。
    已不在賽前狀態（開打、完賽、延賽、保留）的場次，其賽前待辦紀錄立即結清（未查過 missed、等重送 failed）。"""
    for g in schedule:
        key, status = _key(g), str(g.get("status") or "")
        start = _starts(g.get("starts_at"))
        pregame = status not in NOT_PREGAME
        current = _iso(start)
        for rec in checkpoints.values():
            if (rec["key"] == key and not rec["done"] and rec["anchor"] == "start"
                    and rec.get("anchor_at") != current):
                _finish(rec, "failed" if rec["attempts"] else "missed",
                        "rescheduled" if start is not None else "start_time_unknown")
        for point in POINTS:
            if point.anchor == "start":
                if start is None:
                    rid = f"{key}|{point.name}|unknown"
                    if pregame and rid not in checkpoints:
                        rec = _new_record(key, point, None, g, www_starts)
                        _finish(rec, "start_time_unknown", "stats_preexedate_missing")
                        checkpoints[rid] = rec
                    continue
                rid = f"{key}|{point.name}|{_iso(start)}"
                due_at = start + point.offset
                if pregame and rid not in checkpoints and due_at >= since and now >= due_at:
                    checkpoints[rid] = _new_record(key, point, start, g, www_starts)
                continue
            # final 錨點
            if status == "FINISHED" and finished.get(key):
                final = _parse(finished[key])
                rid = f"{key}|{point.name}|{_iso(final)}"
                due_at = final + point.offset
                if rid not in checkpoints and due_at >= since and now >= due_at:
                    checkpoints[rid] = _new_record(key, point, final, g, www_starts)
            elif status in NO_FINAL and start is not None and start >= since and now >= start:
                rid = f"{key}|{point.name}|{_iso(start)}"
                if rid not in checkpoints:
                    rec = _new_record(key, point, None, g, www_starts)
                    rec["anchor_at"] = _iso(start)
                    _finish(rec, "no_final", f"status_{status}")
                    checkpoints[rid] = rec
        if not pregame:
            for rec in checkpoints.values():
                if rec["key"] == key and not rec["done"] and rec["phase"] == "pregame":
                    # 等重送中的也一併結清：開打後再查就不是賽前觀測。
                    _finish(rec, "failed" if rec["attempts"] else "missed", f"game_status_{status}")


def expire(checkpoints: dict, now: datetime) -> None:
    """超過容許窗最遲時刻仍未完成者結清：未試過 → missed／blocked；試過且等重送 → failed。"""
    for rec in checkpoints.values():
        if rec["done"] or not _past_deadline(rec, now):
            continue
        if rec["attempts"]:
            _finish(rec, "failed", "retry_window_passed")
        elif rec.get("wait_reason") in BLOCKING_WAITS:
            _finish(rec, "blocked", rec["wait_reason"])
        else:
            _finish(rec, "missed", rec.get("wait_reason") or "no_wake_in_window")


def due(checkpoints: Mapping[str, Mapping], now: datetime) -> list[str]:
    """此刻應查的紀錄 id：首次（到點、未逾時）或 D2 重送（失敗 1 次、非挑戰、≥20 分、未逾時）。"""
    out = []
    for rid, rec in checkpoints.items():
        if rec["done"]:
            continue
        if not _in_window(rec, now):
            continue
        attempts = rec["attempts"]
        if not attempts:
            out.append(rid)
        elif (_BY_NAME[rec["point"]].retry and len(attempts) == 1
              and now >= _parse(attempts[-1]["at"]) + RETRY_AFTER):
            out.append(rid)
    return sorted(out)


def note_wait(checkpoints: dict, ids: Iterable[str], reason: str) -> None:
    """到點但這次不能查（讓位、冷卻、挑戰停、對帳停…）：只記原因，不計次。"""
    for rid in ids:
        if rid in checkpoints and not checkpoints[rid]["done"]:
            checkpoints[rid]["wait_reason"] = reason


def record_attempt(checkpoints: dict, ids: Iterable[str], now: datetime, *, changed: bool,
                   failed_kinds: Iterable[str], challenge_kinds: Iterable[str]) -> None:
    """一次 www 抓取的結果入帳。``changed``＝本機 E／C 可同步指紋是否變了（整次抓取一個值）。"""
    failed, challenged = set(failed_kinds), set(challenge_kinds)
    for rid in ids:
        rec = checkpoints.get(rid)
        if rec is None or rec["done"]:
            continue
        kind = kind_of(rid)
        challenge = kind in challenged
        outcome = "failed" if kind in failed else ("changed" if changed else "unchanged")
        rec["attempts"].append({"at": _iso(now), "outcome": outcome, "challenge": challenge,
                                "sync_code": None})
        rec["fired_at"] = rec["fired_at"] or _iso(now)
        rec["outcome"], rec["wait_reason"] = outcome, None
        if outcome != "failed":
            _finish(rec, outcome, None)
        elif challenge:
            _finish(rec, "failed", "challenge_no_retry")
        elif not _BY_NAME[rec["point"]].retry:
            _finish(rec, "failed", "no_retry_for_point")
        elif len(rec["attempts"]) >= 2:
            _finish(rec, "failed", "retry_exhausted")
        else:
            rec["reason"] = "retry_pending"


def record_sync(checkpoints: dict, ids: Iterable[str], code: int) -> None:
    """同一次喚醒的同步結果（refresh 退出碼）掛到本次抓到變化的紀錄上。"""
    for rid in ids:
        rec = checkpoints.get(rid)
        if rec and rec["attempts"] and rec["attempts"][-1]["outcome"] == "changed":
            rec["attempts"][-1]["sync_code"] = code
            rec["sync_code"] = code


def timeline(checkpoints: Mapping[str, Mapping]) -> list[dict]:
    """時點紀錄摘要（寫進 last-postseason-evening.json）。時刻皆為本機時刻。"""
    keep = ("key", "point", "phase", "anchor_at", "due_at", "deadline_at", "deadline_inclusive",
            "fired_at", "kinds",
            "outcome", "sync_code", "reason", "wait_reason", "stats_starts_at", "www_start_raw",
            "start_mismatch")
    rows = [{**{k: rec.get(k) for k in keep}, "attempts": len(rec.get("attempts") or [])}
            for rec in checkpoints.values()]
    return sorted(rows, key=lambda r: (r["due_at"] or r["anchor_at"] or "", r["key"], r["point"]))


def preview(schedule: Iterable[Mapping], finished: Mapping[str, str], now: datetime) -> list[dict]:
    """``plan --dry``：列出尚未逾時的時點（台北時刻）。不連網、不碰 DB、不寫狀態。"""
    def tpe(at: datetime | None) -> str | None:
        return at.astimezone(TAIPEI).isoformat() if at else None

    rows = []
    for g in schedule:
        key, status = _key(g), str(g.get("status") or "")
        start = _starts(g.get("starts_at"))
        final = _parse(finished.get(key))
        for point in POINTS:
            anchor = start if point.anchor == "start" else final
            row = {"key": key, "point": point.name, "phase": point.phase, "status": status,
                   "stats_starts_at": g.get("starts_at")}
            if point.anchor == "start":
                if status in NOT_PREGAME:
                    continue
                if anchor is None:
                    rows.append({**row, "note": "start_time_unknown"})
                    continue
            elif anchor is None:
                if status in NO_FINAL:
                    rows.append({**row, "note": "no_final"})
                elif status != "FINISHED":
                    rows.append({**row, "note": "F＝本機首次觀測 stats FINISHED 的時刻；F+60 起、最遲 F+90"})
                continue
            deadline = anchor + point.deadline
            if deadline < now or (deadline == now and not point.deadline_inclusive):
                continue
            rows.append({**row, "due_at": tpe(anchor + point.offset), "deadline_at": tpe(deadline),
                         "deadline_inclusive": point.deadline_inclusive})
    return rows
