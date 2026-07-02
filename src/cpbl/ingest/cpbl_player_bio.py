"""官網選手 person 頁 bio 細項爬蟲（身高體重/初出場/學歷/出生地/選秀順位）。

person 頁（/team/person?acnt=<id>）inline HTML 以 `<dd class="X">` 排列，每項為
`<div class="label">標籤</div><div class="desc">值</div>`。bio 幾近靜態，故只需一次
回填 + 偶爾刷新（新人加入）。冪等 UPDATE 進既有 cpbl.players 列（migration 040 欄位）。

只在本機爬蟲用（官網封海外 IP）。共用 _browser.session()（過 HiNet CDN 反爬挑戰）。
"""

from __future__ import annotations

import logging
import re
import time

from cpbl.db import conn

log = logging.getLogger("cpbl.bio")

# <div class="label">標籤</div> ... <div class="desc">值</div>（desc 內可含 <span> 單位）
_PAIR = re.compile(
    r'<div class="label">([^<]+)</div>\s*<div class="desc">(.*?)</div>', re.S)
_TAG = re.compile(r"<[^>]+>")
_HT = re.compile(r"(\d+)\s*\(CM\).*?(\d+)\s*\(KG\)", re.S)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub("", html)).strip()


def parse_bio(html: str) -> dict:
    """從 person 頁 HTML 抽 bio 欄位。缺項回 None（各年頁面欄位會缺）。"""
    fields = {_text(lbl): desc for lbl, desc in _PAIR.findall(html)}
    out: dict = {"height_cm": None, "weight_kg": None, "debut": None,
                 "education": None, "birthplace": None, "draft": None}
    htwt = fields.get("身高/體重")
    if htwt:
        m = _HT.search(_text(htwt))
        if m:
            out["height_cm"] = int(m.group(1))
            out["weight_kg"] = int(m.group(2))
    for label, key in (("初出場", "debut"), ("學歷", "education"),
                       ("國籍/出生地", "birthplace"), ("選秀順位", "draft")):
        v = _text(fields.get(label, "")) if fields.get(label) else ""
        out[key] = v or None
    return out


def _target_ids(scope: str) -> list[str]:
    """scope=current → 本季登錄打者∪投手；all → players 表全員（未抓過優先）。"""
    with conn() as c:
        if scope == "current":
            rows = c.execute(
                "SELECT player_id FROM cpbl.batting_current "
                "UNION SELECT player_id FROM cpbl.pitching_current "
                "ORDER BY 1").fetchall()
        else:
            rows = c.execute(
                "SELECT id FROM cpbl.players ORDER BY bio_updated_at NULLS FIRST, id"
            ).fetchall()
        return [r[0] for r in rows]


def _upsert(acnt: str, bio: dict) -> None:
    with conn() as c:
        c.execute(
            "UPDATE cpbl.players SET height_cm=%s, weight_kg=%s, debut=%s, "
            "education=%s, birthplace=%s, draft=%s, bio_updated_at=now() WHERE id=%s",
            (bio["height_cm"], bio["weight_kg"], bio["debut"], bio["education"],
             bio["birthplace"], bio["draft"], acnt),
        )


def scrape(scope: str = "current", delay: float = 1.0,
           ids: list[str] | None = None, skip_done: bool = False) -> int:
    """爬 bio 寫回 players。回傳成功列數。

    scope: current（本季登錄）/ all（全員）。ids 指定時忽略 scope。
    skip_done: 跳過 bio_updated_at 已有值者（續跑/背景全回填用）。
    """
    from cpbl.ingest._browser import session
    targets = ids if ids is not None else _target_ids(scope)
    if skip_done:
        with conn() as c:
            done = {r[0] for r in c.execute(
                "SELECT id FROM cpbl.players WHERE bio_updated_at IS NOT NULL").fetchall()}
        targets = [t for t in targets if t not in done]
    log.info("bio 目標 %d 人（scope=%s skip_done=%s delay=%.1fs）",
             len(targets), scope, skip_done, delay)
    ok = 0
    for i, acnt in enumerate(targets, 1):
        for attempt in range(3):
            try:
                time.sleep(delay)
                html = session().page_html(f"/team/person?acnt={acnt}")
                bio = parse_bio(html)
                _upsert(acnt, bio)
                ok += 1
                if i % 25 == 0 or i == len(targets):
                    log.info("[%d/%d] acnt=%s ht=%s wt=%s draft=%s",
                             i, len(targets), acnt, bio["height_cm"],
                             bio["weight_kg"], bool(bio["draft"]))
                break
            except Exception as e:  # noqa: BLE001 — 單人失敗不中斷整批
                log.warning("[%d/%d] acnt=%s attempt=%d 失敗：%s",
                            i, len(targets), acnt, attempt + 1, e)
                time.sleep(2.0 * (attempt + 1))
        else:
            log.error("[%d/%d] acnt=%s 連續失敗，略過", i, len(targets), acnt)
    log.info("bio 完成：%d/%d 寫入", ok, len(targets))
    return ok
