"""官方系列獎項（#288 S07 WP-AWARDS）：輸入驗證、本機寫入、讀取與 overview 呈現。

資料流：需求方／維護者把官方公布頁的 URL＋得主清單寫成 JSON → 本機 ``cpbl-import-series-awards``
（:mod:`cpbl.ingest.run_import_series_awards`）驗證後寫本機 → ``refresh-cpbl-prod.sh`` 的 sync_table 同步到生產
→ overview 在同一唯讀交易內讀每系列**最新** revision（:func:`read_latest`）→ 第 1 區獎項格。

紅線（母卡 P6、PRD v2 第 1 區、需求方 Q1／Q2）：

1. 只收官方站 https 來源；⛔ 爬蟲、⛔ 公開寫入 API、⛔ 從單場 MVP 次數或 RE24 推任何獎項。
2. **未公布 ≠ 未取得**：``not_published``＝本站查核時官方尚未公布（帶查核時間）；``pending_source``＝本站
   沒有任何 revision（含表尚未建立）。兩者格內都是「待更新」，原因分寫頁尾。
3. 共同得主依官方順序全部列出（同一獎項多個 ordinal），⛔ 壓成單一 ID；顯示用官方公布姓名。
4. revision 只追加：同內容重送＝冪等（不新增）；指定已存在的 revision 號＝拒收。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

KINDS = ("E", "C")
STATUSES = ("published", "not_published")
AWARD_TYPES = ("series_mvp", "other")
# 與 migration 078 的 CHECK 同一條規則（DB 是最後一道；這裡先給可讀的錯誤）。
OFFICIAL_URL = re.compile(r"^https://(www\.|stats\.)?cpbl\.com\.tw(/[^\s\\]*)?$")
PLAYER_ID = re.compile(r"^[0-9]{10}$")


class AwardInputError(ValueError):
    """輸入不合格（拒收）；``errors`` 逐條列出原因。"""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Winner:
    winner_name: str
    player_id: str | None
    team_code: str | None


@dataclass(frozen=True)
class Award:
    award_name: str
    award_type: str
    winners: tuple[Winner, ...]


@dataclass(frozen=True)
class AwardRevisionInput:
    year: int
    kind_code: str
    status: str
    source_url: str
    checked_at: datetime
    awards: tuple[Award, ...]
    revision: int | None            # None ⇒ 取下一號

    def content(self) -> dict:
        """決定「是否同內容」的正規形（不含 checked_at／revision）。"""
        return {
            "year": self.year, "kind_code": self.kind_code, "status": self.status,
            "source_url": self.source_url,
            "awards": [{"award_name": a.award_name, "award_type": a.award_type,
                        "winners": [[w.winner_name, w.player_id, w.team_code] for w in a.winners]}
                       for a in self.awards],
        }

    def content_sha256(self) -> str:
        blob = json.dumps(self.content(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _text(v: Any) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def parse_input(raw: dict, *, team_codes: set[str] | None = None) -> AwardRevisionInput:
    """JSON 物件 → 已驗證輸入（純函式）。任何問題一次列齊後拒收。"""
    errors: list[str] = []
    if not isinstance(raw, dict):
        raise AwardInputError(["輸入必須是 JSON 物件"])
    allowed = {"year", "kind_code", "status", "source_url", "checked_at", "awards", "revision"}
    if extra := sorted(set(raw) - allowed):
        errors.append(f"未知欄位：{', '.join(extra)}")

    year = raw.get("year")
    if not isinstance(year, int) or isinstance(year, bool) or not 1990 <= year <= 2100:
        errors.append("year 必須是 1990–2100 的整數")
    kind = raw.get("kind_code")
    if kind not in KINDS:
        errors.append("kind_code 必須是 E 或 C")
    status = raw.get("status")
    if status not in STATUSES:
        errors.append("status 必須是 published 或 not_published")
    url = _text(raw.get("source_url"))
    if url is None:
        errors.append("缺 source_url（官方公布頁 https 網址）")
    elif not OFFICIAL_URL.match(url):
        errors.append(f"source_url 不是官方站 https：{url}")
    checked_at = None
    try:
        checked_at = datetime.fromisoformat(str(raw.get("checked_at")))
        if checked_at.tzinfo is None:
            errors.append("checked_at 必須帶時區（例 2026-10-26T21:00:00+08:00）")
    except ValueError:
        errors.append("checked_at 必須是 ISO 8601 時間（例 2026-10-26T21:00:00+08:00）")
    revision = raw.get("revision")
    if revision is not None and (not isinstance(revision, int) or isinstance(revision, bool) or revision < 1):
        errors.append("revision 若提供必須是 ≥1 的整數")

    awards: list[Award] = []
    raw_awards = raw.get("awards", [])
    if not isinstance(raw_awards, list):
        errors.append("awards 必須是陣列")
        raw_awards = []
    if status == "not_published" and raw_awards:
        errors.append("status=not_published 不能有 awards（官方尚未公布）")
    if status == "published" and not raw_awards:
        errors.append("status=published 至少要有一個獎項")
    seen_names: set[str] = set()
    for i, a in enumerate(raw_awards, 1):
        where = f"awards[{i}]"
        if not isinstance(a, dict):
            errors.append(f"{where} 必須是物件")
            continue
        name = _text(a.get("award_name"))
        if name is None:
            errors.append(f"{where} 缺 award_name（官方完整名稱）")
        elif name in seen_names:
            errors.append(f"{where} 獎項名稱重複：{name}")
        else:
            seen_names.add(name)
        atype = a.get("award_type")
        if atype not in AWARD_TYPES:
            errors.append(f"{where} award_type 必須是 series_mvp 或 other")
        raw_winners = a.get("winners")
        if not isinstance(raw_winners, list) or not raw_winners:
            errors.append(f"{where} 至少要有一位得主")
            raw_winners = []
        winners: list[Winner] = []
        seen_w: set[tuple] = set()
        for j, w in enumerate(raw_winners, 1):
            wwhere = f"{where}.winners[{j}]"
            if not isinstance(w, dict):
                errors.append(f"{wwhere} 必須是物件")
                continue
            wname = _text(w.get("winner_name"))
            pid = _text(w.get("player_id"))
            team = _text(w.get("team_code"))
            if wname is None:
                errors.append(f"{wwhere} 缺 winner_name（官方公布姓名）")
            if pid is not None and not PLAYER_ID.match(pid):
                errors.append(f"{wwhere} player_id 必須是 10 碼數字")
            if team is not None and team_codes is not None and team not in team_codes:
                errors.append(f"{wwhere} team_code 不在 team_dim：{team}")
            ident = (pid,) if pid else (wname,)
            if ident in seen_w:
                errors.append(f"{wwhere} 同一獎項得主重複：{pid or wname}")
            seen_w.add(ident)
            winners.append(Winner(wname or "", pid, team))
        awards.append(Award(name or "", atype or "", tuple(winners)))

    if errors:
        raise AwardInputError(errors)
    return AwardRevisionInput(year=year, kind_code=kind, status=status, source_url=url, checked_at=checked_at,
                              awards=tuple(awards), revision=revision)


# ---------------------------------------------------------------------------------------------
# 寫入（本機 CLI 唯一 writer；呼叫端給 cursor 與交易）
# ---------------------------------------------------------------------------------------------
LATEST_SQL = """
    SELECT revision, source_sha256 FROM cpbl.series_award_revision
    WHERE year = %s AND kind_code = %s ORDER BY revision DESC LIMIT 1
"""
EXISTS_SQL = "SELECT 1 FROM cpbl.series_award_revision WHERE year = %s AND kind_code = %s AND revision = %s"
INSERT_REVISION_SQL = """
    INSERT INTO cpbl.series_award_revision (year, kind_code, revision, status, source_url, source_sha256, checked_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""
INSERT_WINNER_SQL = """
    INSERT INTO cpbl.series_award_winner
        (year, kind_code, revision, award_seq, ordinal, award_name, award_type, player_id, winner_name, team_code)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class DuplicateRevisionError(Exception):
    """指定的 revision 號已存在（拒收；revision 只追加、不可改）。"""


@dataclass(frozen=True)
class WriteResult:
    action: str          # "created" | "unchanged"
    revision: int
    source_sha256: str


def write_revision(cur, item: AwardRevisionInput) -> WriteResult:
    """在呼叫端交易內寫入一個 revision 與其得主。同內容＝冪等；指定號已存在＝拒收。"""
    sha = item.content_sha256()
    cur.execute("LOCK TABLE cpbl.series_award_revision IN SHARE ROW EXCLUSIVE MODE")  # 序列化取號
    cur.execute(LATEST_SQL, (item.year, item.kind_code))
    latest = cur.fetchone()
    if item.revision is not None:
        cur.execute(EXISTS_SQL, (item.year, item.kind_code, item.revision))
        if cur.fetchone():
            raise DuplicateRevisionError(
                f"{item.year}/{item.kind_code} revision {item.revision} 已存在（revision 只追加、不可改）")
    if latest and latest[1] == sha and item.revision is None:
        return WriteResult("unchanged", int(latest[0]), sha)
    revision = item.revision if item.revision is not None else (int(latest[0]) + 1 if latest else 1)
    if latest and revision <= int(latest[0]):
        raise DuplicateRevisionError(
            f"{item.year}/{item.kind_code} revision {revision} 不大於目前最新 {latest[0]}（只追加）")
    cur.execute(INSERT_REVISION_SQL, (item.year, item.kind_code, revision, item.status, item.source_url, sha,
                                      item.checked_at))
    for seq, award in enumerate(item.awards, 1):
        for ordinal, w in enumerate(award.winners, 1):
            cur.execute(INSERT_WINNER_SQL, (item.year, item.kind_code, revision, seq, ordinal, award.award_name,
                                            award.award_type, w.player_id, w.winner_name, w.team_code))
    return WriteResult("created", revision, sha)


# ---------------------------------------------------------------------------------------------
# 讀取（overview 同一唯讀交易）＋呈現（純函式）
# ---------------------------------------------------------------------------------------------
READ_LATEST_SQL = """
    WITH latest AS (
        SELECT DISTINCT ON (kind_code) year, kind_code, revision, status, source_url, checked_at
        FROM cpbl.series_award_revision
        WHERE year = %(year)s AND kind_code = ANY(%(kinds)s)
        ORDER BY kind_code, revision DESC
    )
    SELECT l.kind_code, l.revision, l.status, l.source_url, l.checked_at,
           w.award_seq, w.ordinal, w.award_name, w.award_type, w.player_id, w.winner_name, w.team_code
    FROM latest l
    LEFT JOIN cpbl.series_award_winner w
      ON w.year = l.year AND w.kind_code = l.kind_code AND w.revision = l.revision
    ORDER BY l.kind_code, w.award_seq, w.ordinal
"""


def read_latest(cur, year: int) -> dict[str, dict]:
    """每系列最新 revision（含得主）。沒有任何 revision 的系列不在回傳裡。表不存在時拋錯，由呼叫端降級。"""
    cur.execute(READ_LATEST_SQL, {"year": year, "kinds": list(KINDS)})
    out: dict[str, dict] = {}
    for (kind, revision, status, url, checked_at, seq, ordinal, name, atype, pid, wname, team) in cur.fetchall():
        rec = out.setdefault(kind, {"revision": int(revision), "status": status, "source_url": url,
                                    "checked_at": checked_at.isoformat() if hasattr(checked_at, "isoformat")
                                    else checked_at, "winners": []})
        if seq is not None:
            rec["winners"].append({"award_seq": int(seq), "ordinal": int(ordinal), "award_name": name,
                                   "award_type": atype, "player_id": pid, "winner_name": wname,
                                   "team_code": team})
    return out


def awards_json(latest: dict[str, dict] | None, kind: str) -> dict:
    """單一系列的獎項格 payload（純函式）。

    - ``None``（讀取失敗／表未建）或該系列沒有 revision ⇒ ``pending_source``（本站尚未取得）
    - 最新 revision 為 not_published ⇒ ``not_published``（帶查核時間與來源）
    - published 且有得主 ⇒ ``published``（獎項依官方順序、共同得主全列）
    - published 卻沒有得主（同步半途或資料損壞）⇒ fail closed 回 ``pending_source``
    """
    # 三種「本站尚未取得」對讀者是同一件事（格內「待更新」＋同一條頁尾），payload 形狀與 G2 相同、不帶原因。
    rec = (latest or {}).get(kind)
    if rec is None:
        return {"status": "pending_source"}
    base = {"revision": rec["revision"], "source_url": rec["source_url"], "checked_at": rec["checked_at"]}
    if rec["status"] == "not_published":
        return {"status": "not_published", **base}
    if not rec["winners"]:
        return {"status": "pending_source"}
    awards: list[dict] = []
    for w in rec["winners"]:
        if not awards or awards[-1]["award_seq"] != w["award_seq"]:
            awards.append({"award_seq": w["award_seq"], "award_name": w["award_name"],
                           "award_type": w["award_type"], "winners": []})
        awards[-1]["winners"].append({"player_id": w["player_id"], "name": w["winner_name"],
                                      "team_code": w["team_code"]})
    return {"status": "published", **base,
            "awards": [{k: a[k] for k in ("award_name", "award_type", "winners")} for a in awards]}
