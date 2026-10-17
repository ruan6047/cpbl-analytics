"""第 4 區 4A 牛棚近期使用負荷（#289 S08；PRD v2〈第 4 區 觀戰重點〉〈牛棚近期使用負荷門檻〉）。

純函式：輸入只有事實（投手登板、各日期的覆蓋判定、目標場台北日期）；不讀 DB、不讀時鐘、
不讀環境時區。讀取與覆蓋判定在 :mod:`cpbl.playoffs.watch_reader`。同一組函式供 GET 產生「目前」
4A，也供 S09 發布器離線呼叫產生凍結值。

紅線：

1. **完整性先於燈號**（PRD「判定優先序：資料是否完整 → 紅 → 橘 → 綠」）：D−3～D 任一日覆蓋不完整
   ⇒ 灰，仍列已知球數；⛔ 不把缺列當 0，⛔ 灰色不輸出觸發理由或可用性。
2. 門檻只住 :data:`THRESHOLDS`，版本 :data:`POLICY_VERSION`（``v2.0-proposed``，尚未經 CPBL 歷史校準）；
   ⛔ 不提供參數覆寫、⛔ 不因單系列結果自動調整（G12）。改值須另有批准的研究範圍並換版本字串。
3. 同日不同場分別計球數、日期只算一天；續賽同 game key 只算一次登板；保留賽無法拆分投球日 ⇒
   其可能日期在窗口內者灰，球數列為「未歸屬」。
4. 名單角色為輪值者（D4 裁定 issuecomment-6183958748）：本應綠時改為 ``starter_exempt``
   （「先發投手，不套用牛棚負荷燈號」），紅／橘照常；灰仍是灰。
5. 本模組只描述球數與出賽日，⛔ 不是健康判斷、可用性機率或教練調度。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType

POLICY_VERSION = "playoffs-policy/v2.0-proposed"

#: PRD 第五節牛棚近期使用負荷門檻（建議值，未校準）。唯一來源；⛔ 執行期不可覆寫。
THRESHOLDS = MappingProxyType({
    "high": MappingProxyType({"P0": 30, "P1": 30, "S2": 45, "S3": 60, "C": 3, "Q": 2}),
    "medium": MappingProxyType({"P0": 15, "P1": 15, "S2": 25, "S3": 40, "C": 2, "Q": 1}),
})

#: 觸發條件判定順序（輸出觸發理由清單的穩定順序）。
METRIC_ORDER = ("P0", "P1", "S2", "S3", "C", "Q")

#: 負荷窗口：D−3～D−1 與 D 當日。
WINDOW_OFFSETS = (3, 2, 1, 0)

LEVEL_LABEL = MappingProxyType({
    "high": "高", "medium": "中", "low": "低", "unknown": "未知",
    "starter_exempt": "先發投手，不套用牛棚負荷燈號",
})

#: 覆蓋不完整理由碼 → 固定文字。reader 與本模組只用這些碼；文字隨 policy 版本一起凍結。
REASON_TEXT = MappingProxyType({
    "no_source": "該日沒有可核對的來源",
    "game_not_final": "該隊當日正式場尚未完賽或尚未同步",
    "box_missing": "該隊當日正式場已完賽，但投手逐場紀錄尚未送達",
    "pitch_count_missing": "登板紀錄缺球數",
    "date_untrusted": "保留賽無法拆分實際投球日期",
    "date_missing": "實際投球日期不可判定（缺比賽日期或日期資料不一致）",
    "live_unobserved": "目標場進行中，即時已投未取得",
    "target_box_unverified": "目標場尚未核定完賽，卻已有投球紀錄（未核實，不當作賽前 0 球）",
    "schedule_unavailable": "賽程來源不可用",
    "duplicate_conflict": "同一場次出現互相矛盾的登板紀錄",
})

ROTATION_ROLE = "輪值"

GameKey = tuple[int, str, int]


@dataclass(frozen=True)
class Appearance:
    """一次正式登板（一位投手、一個 game key）。

    ``date`` 是台北日期；``date_trusted=False`` 時 ``possible_dates`` 必須是**完整**候選投球日集合，
    空 tuple ⇒ 無界（任何日期都可能）。⛔ 給不完整的集合：規則層只在候選全部落在窗口外時才排除這筆登板，
    集合不完整就會把缺實際日期的登板誤當成窗口外（#289 審核 R1）。產生方式見
    :func:`cpbl.playoffs.watch_reader.pitch_dates`。``live=True`` 表示球數來自
    目標場即時觀測（標「即時」）。``outs``／``er`` 只供連投 ERA 與最近登板展示。
    """

    game_key: GameKey
    date: date | None
    date_trusted: bool
    pitch_cnt: int | None
    outs: int | None = None
    er: int | None = None
    role_type: str | None = None
    possible_dates: tuple[date, ...] = ()
    live: bool = False


@dataclass(frozen=True)
class DayCoverage:
    """該隊某一台北日期的覆蓋判定（由 reader 依 games／box／即時觀測判定）。

    ``complete=True`` ⇒ 該隊當日所有正式場都已核對（含「當日無正式場」＝有證據的 0）。
    """

    date: date
    complete: bool
    reasons: tuple[str, ...] = ()
    live: bool = False


# —— 共用日期規則（WP4 A06 推測重用） ——————————————————————————————


def full_rest_days(target_date: date, last_pitch_date: date) -> int:
    """PRD：完整休息日＝max(0, 目標場台北日期−最後實際投球台北日期−1)。10/9 登板、10/14 比賽＝4。"""
    return max(0, (target_date - last_pitch_date).days - 1)


def dedupe_appearances(appearances: Iterable[Appearance]) -> tuple[list[Appearance], list[GameKey]]:
    """同 game key 只留一次登板（續賽同 key 不重計）。

    回傳 (去重後清單, 矛盾的 game key)。同 key 但球數／日期不同 ⇒ 列為矛盾，呼叫端判灰。
    """
    seen: dict[GameKey, Appearance] = {}
    conflicts: list[GameKey] = []
    for a in appearances:
        prev = seen.get(a.game_key)
        if prev is None:
            seen[a.game_key] = a
        elif prev != a and a.game_key not in conflicts:
            conflicts.append(a.game_key)
    return list(seen.values()), conflicts


def last_pitch_date(appearances: Iterable[Appearance], *, before: date) -> tuple[date | None, str | None]:
    """``before`` 之前（不含）最後一次實際投球的台北日期。

    回傳 (日期, 不可判定理由)。保留賽的可能日期晚於或等於最後可信日期（或完全未知）⇒ 無法確定
    最後投球日 ⇒ (None, "date_untrusted")；登板完全沒有日期 ⇒ (None, "date_missing")。沒有任何登板 ⇒ (None, None)。
    """
    trusted = [a.date for a in appearances if a.date_trusted and a.date is not None and a.date < before]
    last = max(trusted, default=None)
    for a in appearances:
        if a.date_trusted:
            continue
        cands = [d for d in a.possible_dates if d < before]
        if not a.possible_dates:
            return None, "date_missing"
        if cands and (last is None or max(cands) >= last):
            return None, "date_untrusted"
    return last, None


def recent_appearances(appearances: Iterable[Appearance], n: int = 3) -> list[Appearance]:
    """最近 n 次登板（日期降冪；同日依 game key 降冪）。日期未知者排在已知之後、不丟棄。"""
    def key(a: Appearance):
        d = a.date or (max(a.possible_dates) if a.possible_dates else date.min)
        return (d, a.game_key[0], a.game_key[1], a.game_key[2])
    return sorted(appearances, key=key, reverse=True)[:n]


# —— 4A 負荷 ——————————————————————————————————————————————————————


def _day_window(target_date: date) -> list[date]:
    return [target_date - timedelta(days=k) for k in WINDOW_OFFSETS]


def _classify(metrics: Mapping[str, int]) -> tuple[str, list[dict]]:
    for level in ("high", "medium"):
        hits = [{"metric": m, "value": metrics[m], "threshold": THRESHOLDS[level][m]}
                for m in METRIC_ORDER if metrics[m] >= THRESHOLDS[level][m]]
        if hits:
            return level, hits
    return "low", []


def bullpen_load(target_date: date, appearances: Sequence[Appearance],
                 coverage: Mapping[date, DayCoverage], *, tactical_role: str | None = None,
                 tactical_roles: Sequence[str] | None = None) -> dict:
    """一位投手的 4A 近期使用負荷（JSON-able）。

    ``coverage`` 必須涵蓋 D−3～D 四個日期；缺任一日 ⇒ 該日 ``no_source`` ⇒ 灰（無來源不綠）。
    ``appearances`` 可含窗口外的登板（只用於最近登板與休息日）；窗口內只計已覆蓋日期。
    """
    apps, conflicts = dedupe_appearances(appearances)
    window = _day_window(target_date)
    in_window = set(window)

    # 每日：可信日期的球數、登板數；不可信（保留賽）只記入可能日期的未完整理由。
    days: dict[date, dict] = {}
    for d in window:
        cov = coverage.get(d)
        reasons = list(cov.reasons) if cov is not None and not cov.complete else []
        if cov is None:
            reasons = ["no_source"]
        elif not cov.complete and not reasons:
            reasons = ["no_source"]
        days[d] = {"date": d.isoformat(), "offset": (target_date - d).days, "pitches": 0,
                   "appearances": 0, "reasons": reasons, "live": bool(cov and cov.live)}

    unattributed: list[dict] = []
    for a in apps:
        if a.date_trusted and a.date is not None:
            if a.date not in in_window:
                continue
            day = days[a.date]
            day["appearances"] += 1
            day["live"] = day["live"] or a.live
            if a.pitch_cnt is None:
                day["reasons"].append("pitch_count_missing")
            else:
                day["pitches"] += a.pitch_cnt
            if a.game_key in conflicts:
                day["reasons"].append("duplicate_conflict")
            continue
        hit = [d for d in a.possible_dates if d in in_window] if a.possible_dates else list(window)
        if not hit:
            continue
        # 有登板紀錄卻沒有任何可歸屬日期（缺 games 列或 game_date）⇒ 整個窗口不可判定（無來源不綠）。
        for d in hit:
            days[d]["reasons"].append("date_untrusted" if a.possible_dates else "date_missing")
        unattributed.append({"game_key": _key_json(a.game_key), "pitches": a.pitch_cnt,
                             "possible_dates": [d.isoformat() for d in a.possible_dates]})

    for d in days.values():
        d["reasons"] = list(dict.fromkeys(d["reasons"]))
        d["complete"] = not d["reasons"]

    by_offset = {v["offset"]: v for v in days.values()}
    complete = all(v["complete"] for v in days.values())
    p = {k: by_offset[k]["pitches"] for k in WINDOW_OFFSETS}

    # C：截至 D−1 連續日曆日登板數。只看 D−3～D−1（C≥3 即紅，窗口外不影響等級）。
    consecutive, c_capped = 0, False
    for k in (1, 2, 3):
        if by_offset[k]["appearances"] == 0:
            break
        consecutive += 1
    else:
        c_capped = True
    q = by_offset[0]["appearances"]

    metrics = {"P0": p[0], "P1": p[1], "S2": p[1] + p[2], "S3": p[1] + p[2] + p[3], "C": consecutive, "Q": q}
    if complete:
        level, triggers = _classify(metrics)
    else:
        level, triggers = "unknown", []
    roles = set(tactical_roles) if tactical_roles is not None else ({tactical_role} if tactical_role else set())
    if level == "low" and roles in ({"先發"}, {ROTATION_ROLE}):
        level = "starter_exempt"

    incomplete = [{"date": v["date"], "offset": v["offset"], "reasons": v["reasons"],
                   "text": [REASON_TEXT[r] for r in v["reasons"]]}
                  for v in sorted(days.values(), key=lambda v: -v["offset"]) if not v["complete"]]
    last, last_reason = last_pitch_date(apps, before=target_date)
    # 窗口內 D 之前有不完整日期、且晚於最後已知投球日 ⇒ 該日可能有未入庫的登板，休息日不可判定。
    gap = next((v for v in sorted(days.values(), key=lambda v: v["offset"])
                if v["offset"] >= 1 and not v["complete"]
                and (last is None or date.fromisoformat(v["date"]) > last)), None)
    if gap is not None and last_reason is None:
        last, last_reason = None, gap["reasons"][0]
    return {
        "policy_version": POLICY_VERSION,
        "target_date": target_date.isoformat(),
        "level": level,
        "label": LEVEL_LABEL[level],
        "complete": complete,
        # 灰色時 metrics 只是「已知部分」：S2／S3／C 不可判定 ⇒ None，P 列已知球數。
        "metrics": metrics if complete else {
            "P0": p[0], "P1": p[1], "S2": None, "S3": None, "C": None, "Q": q},
        "c_at_least": c_capped and complete,
        "triggers": triggers,
        "days": [{k: v[k] for k in ("date", "offset", "pitches", "appearances", "complete", "live")}
                 for v in sorted(days.values(), key=lambda v: -v["offset"])],
        "incomplete": incomplete,
        "unattributed": unattributed,
        "live": any(v["live"] for v in days.values()),
        "last_pitch_date": last.isoformat() if last else None,
        "full_rest_days": full_rest_days(target_date, last) if last else None,
        "rest_unknown_reason": last_reason,
    }


# —— 連投 ERA ——————————————————————————————————————————————————————


ERA_SCOPE = "本季一軍例行賽（A）；前次登板日為前一個日曆日的當次出賽合計；ERA＝27×ER/outs"


def consecutive_day_era(season_a_appearances: Iterable[Appearance]) -> dict:
    """本季「距前次登板一天的當次出賽」ERA（PRD：連續兩日登板時附）。

    納入：該次出賽日期的前一個日曆日也有登板（以不同日期判斷；雙重賽同日兩場都納入）。
    日期不可信（保留賽）的登板既不納入、也不能當「前一日」證據，計入 ``excluded_untrusted``。
    先加總 ER 與 outs 再算；outs=0 ⇒ 不可定義（None）；⛔ 不平均單場 ERA、⛔ 不暗示因果。
    """
    apps, _ = dedupe_appearances(season_a_appearances)
    trusted = [a for a in apps if a.date_trusted and a.date is not None]
    excluded = len(apps) - len(trusted)
    dates = {a.date for a in trusted}
    picked = [a for a in trusted if a.date is not None and a.date - timedelta(days=1) in dates]
    missing = [a for a in picked if a.outs is None or a.er is None]
    if missing:
        return {"scope": ERA_SCOPE, "appearances": len(picked), "outs": None, "ip": None, "er": None,
                "era": None, "complete": False, "excluded_untrusted": excluded}
    outs = sum(a.outs for a in picked if a.outs is not None)
    er = sum(a.er for a in picked if a.er is not None)
    return {
        "scope": ERA_SCOPE,
        "appearances": len(picked),
        "outs": outs,
        "ip": f"{outs // 3}.{outs % 3}",
        "er": er,
        "era": round(27 * er / outs, 2) if outs > 0 else None,
        "complete": True,
        "excluded_untrusted": excluded,
    }


def _key_json(key: GameKey) -> dict:
    return {"year": key[0], "kind_code": key[1], "game_sno": key[2]}
