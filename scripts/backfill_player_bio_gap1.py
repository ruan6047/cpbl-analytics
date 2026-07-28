"""INGEST-PLAYER-BIO-GAP1：補齊 players 缺 country／birthday 的一次性 bio 重爬。

為什麼要獨立腳本而不是直接跑 `cpbl-scrape-bio`：
1. 目標名單必須由 DB 缺值條件推導（只打必要頁數；本卡 14 頁），CLI 無此 scope。
2. 卡面驗收要求「官網 /team/person?acnt= 的實際回應已實地查證（非從解析器行為反推）」，
   故每頁原始 HTML 必須落地存證（`--html-dir`，寫 scratchpad，勿入 repo）。

抓取與寫入路徑一律沿用 canonical 模組（`cpbl_player_bio.parse_bio` / `_upsert`），
本檔只負責「選名單、存證、分類徵狀、把關寫入」。

**fail-closed 寫入閘門（本檔存在的關鍵理由）**：canonical `_upsert` 對
`country`／`birthday`／`bats`／`throws` 是 COALESCE 只補缺，但
`height_cm`／`weight_kg`／`debut`／`education`／`birthplace`／`draft` 是無條件
`EXCLUDED` 覆蓋。若某頁回的是反爬挑戰頁或「查無此人」空頁，`parse_bio` 全 None，
直接呼叫 `_upsert` 會把該員**既有的** height/weight/debut/birthplace 洗成 NULL——
本卡是來補資料的，不能反而弄丟資料。故只有徵狀為 `person_page_parsed`
（確認是該員 person 頁且至少解析到 country 或 birthday）才寫入；其餘徵狀
只存證與記錄，不碰 DB。可重跑且不會把既有非空值洗成 NULL。

用法::

    uv run python scripts/backfill_player_bio_gap1.py --dry-run --limit 2 --html-dir /path/scratch
    uv run python scripts/backfill_player_bio_gap1.py --html-dir /path/scratch
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("cpbl.bio_gap1")

# 徵狀分類：官網「查無此人」空頁仍是完整 CPBL 頁（含此標記）；反爬挑戰頁沒有
CPBL_MARK = "全球資訊網"

# 唯一允許寫 DB 的徵狀（fail-closed；其餘一律只存證，見模組 docstring）
WRITABLE = "person_page_parsed"


def target_ids(cur) -> list[tuple[str, str]]:
    """缺 country 或 birthday 的球員（本卡母體；補滿後重跑即空集合）。"""
    cur.execute("SELECT id, name FROM cpbl.players "
                "WHERE country IS NULL OR birthday IS NULL ORDER BY id")
    return [(r[0], r[1]) for r in cur.fetchall()]


def fetch(acnt: str) -> tuple[str, str]:
    """取 person 頁 HTML。回 (html, 走過的路徑)。與 cpbl_player_bio.scrape 同語意。"""
    from cpbl.ingest._browser import session
    from cpbl.ingest.cpbl_player_bio import parse_bio

    path = f"/team/person?acnt={acnt}"
    html = session().page_html(path, wait="domcontentloaded")
    route = "domcontentloaded"
    if parse_bio(html)["name"] is None and CPBL_MARK not in html:
        html = session().page_html(path, wait="networkidle", force=True)
        route = "domcontentloaded→networkidle(reload)"
    return html, route


def symptom(html: str, bio: dict) -> str:
    """實地查證的徵狀分類（供交付文件逐人記錄）。"""
    if CPBL_MARK not in html:
        return "non_cpbl_page"           # 反爬挑戰頁／非官網內容
    if bio["name"] is None:
        return "cpbl_page_no_person"     # 完整 CPBL 頁但查無此人
    if bio["country"] is None and bio["birthday"] is None:
        return "person_page_no_bio_fields"
    return "person_page_parsed"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html-dir", type=Path, required=True,
                    help="原始 HTML 存證目錄（scratchpad；勿入 repo）")
    ap.add_argument("--dry-run", action="store_true", help="只抓不寫 DB")
    ap.add_argument("--limit", type=int, help="只處理前 N 人（正式跑前的徵狀分類驗證用）")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--report", type=Path, help="逐人徵狀 JSON 輸出路徑")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")

    from cpbl.db import conn

    with conn() as c:
        targets = target_ids(c.cursor())
    if args.limit:
        targets = targets[:args.limit]
    log.info("目標 %d 人（缺 country 或 birthday；limit=%s dry_run=%s）",
             len(targets), args.limit, args.dry_run)
    args.html_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    try:
        _loop(args, targets, rows)
    finally:
        # 斷路器中止也要留下已抓到的存證與徵狀（診斷靠它，不能因中止而遺失）
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    skipped = [r for r in rows if not r["wrote"]]
    log.info("完成：%d 人，寫入 %d，未寫入 %d（dry_run=%s）",
             len(rows), len(rows) - len(skipped), len(skipped), args.dry_run)
    for r in skipped:
        log.info("  未寫入：%s %s（徵狀 %s）", r["id"], r["db_name"], r["symptom"])


def _loop(args, targets: list[tuple[str, str]], rows: list[dict]) -> None:
    from cpbl.ingest._browser import check_circuit
    from cpbl.ingest.cpbl_player_bio import _upsert, parse_bio

    consec_fail = 0
    for i, (acnt, name) in enumerate(targets, 1):
        try:
            time.sleep(args.delay)
            html, route = fetch(acnt)
            (args.html_dir / f"{acnt}.html").write_text(html)
            bio = parse_bio(html)
            sym = symptom(html, bio)
            # fail-closed：只有確認是該員 person 頁且有解析到 bio 才寫；
            # 挑戰頁／查無此人頁全 None，寫進去會把既有 height/weight/debut 洗成 NULL
            wrote = sym == WRITABLE and not args.dry_run
            if wrote:
                _upsert(acnt, bio)
            elif sym != WRITABLE:
                log.warning("[%d/%d] %s %s 徵狀 %s 不合格 → 跳過寫入（保護既有欄位）",
                            i, len(targets), acnt, name, sym)
            # 挑戰頁不是「該員沒資料」而是節流訊號：連續出現要跟 fetch 例外一樣中止整輪，
            # 否則剩餘名單會繼續打站，把節流打成深度封鎖（在 try 外統一判，避免自己拋的
            # RuntimeError 被本層 except 接住後誤記成 fetch_failed）
            consec_fail = consec_fail + 1 if sym == "non_cpbl_page" else 0
            log.info("[%d/%d] %s %s → %s（route=%s, len=%d, wrote=%s）country=%s birthday=%s",
                     i, len(targets), acnt, name, sym, route, len(html), wrote,
                     bio["country"], bio["birthday"])
            rows.append({"id": acnt, "db_name": name, "symptom": sym, "route": route,
                         "html_len": len(html), "wrote": wrote,
                         "page_name": bio["name"],
                         "name_mismatch": bool(bio["name"]) and bio["name"] != name,
                         "parsed": bio})
        except Exception as e:  # noqa: BLE001 — 單人失敗不中斷，連續失敗由斷路器擋
            consec_fail += 1
            log.error("[%d/%d] %s %s 失敗：%s", i, len(targets), acnt, name, e)
            rows.append({"id": acnt, "db_name": name, "symptom": "fetch_failed",
                         "wrote": False, "error": str(e)[:300]})
        check_circuit(consec_fail)


if __name__ == "__main__":
    main()
