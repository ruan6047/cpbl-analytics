"""INGEST-PLAYER-BIO-GAP1：補齊 players 缺 country／birthday 的一次性 bio 重爬。

為什麼要獨立腳本而不是直接跑 `cpbl-scrape-bio`：
1. 目標名單必須釘死在卡面明定的 14 人（只打必要頁數；見 EXPECTED_GAP_IDS），CLI 無此 scope。
2. 卡面驗收要求「官網 /team/person?acnt= 的實際回應已實地查證（非從解析器行為反推）」，
   故每頁原始 HTML 必須落地存證（`--html-dir`，寫 scratchpad，勿入 repo）。

**為什麼不走 canonical `cpbl_player_bio._upsert`（取捨已記錄於交付文件）**：
`_upsert` 的語意是「用 person 頁的全量內容更新一列」——它對
`height_cm`／`weight_kg`／`debut`／`education`／`birthplace`／`draft` 是無條件
`EXCLUDED` 覆蓋，並且會用頁面姓名改寫 `name`。本卡要做的事只有「補兩個 NULL 欄」；
硬套全量更新語意，任何退化頁／部分解析頁／抓錯人的頁都會造成資料損失。

改用**專用窄 UPDATE**（`FILL_SQL`）：只碰 `country`／`birthday`／`bio_updated_at`，
且兩個資料欄一律 `COALESCE(既有, 新值)`。其餘欄位與 `name` **結構上不可能被碰到**
——不是靠守衛列舉「哪些情況不能寫」（該做法已證實會漏：列舉了挑戰頁與查無此人頁，
仍漏掉部分解析頁與姓名不符頁），而是靠限制語句能觸及的範圍。

姓名檢查仍保留，但定位是**健全性閘門**而非資料保護：頁面姓名與 DB 不符代表這一頁的
country／birthday 本來就是別人的值，故拒寫並記錄，交人工判斷（可能是抓錯人，也可能
是官網改名而 DB 未同步——兩者都不該由本腳本自行決定）。

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

# 卡面明定的 14 人（2025 年登錄洋將、opendata 未涵蓋）。
# 為什麼釘死而不動態撈：正式執行延到 Gate3 觀測窗收窗（~2026-08-07）後，期間若有新球員
# 登錄且 bio 缺值，動態名單會多抓多寫、超出卡面核准的範圍與站台請求量——而請求量正是
# 這張卡被押後的原因。範圍有變動時必須由人重新確認並改本常數（改常數＝可查核的變更），
# 不得自動放行、也不得自動取交集。
EXPECTED_GAP_IDS: dict[str, str] = {
    "0000004796": "鎛銳",
    "0000006891": "力亞士",
    "0000007547": "石萬金",
    "0000007554": "龍聖",
    "0000007555": "霸鉧德",
    "0000007556": "波賽樂",
    "0000007558": "黃博多",
    "0000007559": "蒙德茲",
    "0000007573": "李博登",
    "0000007579": "韋禮加",
    "0000007583": "柯威士",
    "0000007588": "奧德銳",
    "0000007590": "那瑪夏",
    "0000007603": "凱樂",
}

# 唯一的寫入語句：只碰兩個目標欄 + 時間戳；COALESCE 保證只補缺不覆蓋。
# 這條 SQL 的欄位清單就是本卡的寫入邊界契約（tests/test_bio_gap_backfill.py 對它斷言）。
FILL_SQL = (
    "UPDATE cpbl.players "
    "SET country = COALESCE(country, %s), "
    "    birthday = COALESCE(birthday, %s), "
    "    bio_updated_at = now() "
    "WHERE id = %s"
)


def check_scope(found: set[str]) -> set[str]:
    """範圍閘門。回「已補滿」的 id 集合；發現未授權的缺值球員即中止。

    **兩個方向的差集意義相反，故閘門是非對稱的**：

    - `found - expected`（DB 有、卡面無）＝ 有新登錄球員缺 bio → **未授權的範圍擴張**，
      硬中止並維持現狀。多打的頁數正是本卡被押後的原因，不得順手在本卡處理。
    - `expected - found`（卡面有、DB 無）＝ 那個人**已經被補滿了** → 那是**進度**不是
      異常，視為 completed 並跳過。

    對稱地要求「集合必須完全相同」會直接打死兩個合法情境：斷路器中止後冷卻續跑
    （剩下的人數必然少於 14），以及補完後重跑（應為成功的 no-op，而非失敗）。
    後者正是卡面驗收條件「寫入冪等、可重跑」的要求。
    """
    extra = sorted(found - set(EXPECTED_GAP_IDS))
    if extra:
        raise SystemExit(
            "發現卡面未授權的缺值球員，中止（維持現狀，不動任何資料）。\n"
            f"  多出（DB 有、卡面無）：{extra}\n"
            "  這代表有新登錄球員缺 bio，屬另一張卡的範圍；本卡的站台請求量已核准為\n"
            "  固定 14 頁，不得擴張。確認範圍後由人工更新 EXPECTED_GAP_IDS。")
    return set(EXPECTED_GAP_IDS) - found


def target_ids(cur) -> list[tuple[str, str]]:
    """執行目標＝「仍缺值 ∩ 已授權」。已補滿者跳過；空集合為成功的 no-op。"""
    cur.execute("SELECT id, name FROM cpbl.players "
                "WHERE country IS NULL OR birthday IS NULL ORDER BY id")
    rows = [(r[0], r[1]) for r in cur.fetchall()]
    done = check_scope({pid for pid, _ in rows})
    if done:
        log.info("已補滿 %d/%d 人，跳過：%s", len(done), len(EXPECTED_GAP_IDS),
                 "、".join(f"{pid}({EXPECTED_GAP_IDS[pid]})" for pid in sorted(done)))
    targets = [(pid, name) for pid, name in rows if pid in EXPECTED_GAP_IDS]
    if not targets:
        log.info("14 人皆已補滿，無事可做（no-op）。")
    return targets


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
    """頁面形態分類（實地查證的證據欄位；不作為寫入判準，寫入看 write_decision）。"""
    if CPBL_MARK not in html:
        return "non_cpbl_page"           # 反爬挑戰頁／非官網內容
    if bio["name"] is None:
        return "cpbl_page_no_person"     # 完整 CPBL 頁但查無此人
    if bio["country"] is None and bio["birthday"] is None:
        return "person_page_no_bio_fields"
    return "person_page_parsed"


def write_decision(bio: dict, db_name: str) -> tuple[bool, str]:
    """可否寫入 + 理由。窄 UPDATE 已限制寫入範圍，此處只擋「值根本不是這個人的」。"""
    if bio["name"] is None:
        return False, "no_person_on_page"     # 挑戰頁／查無此人頁
    if bio["name"] != db_name:
        return False, "name_mismatch"         # 抓到別人的頁：值不對，交人工判斷
    if bio["country"] is None and bio["birthday"] is None:
        return False, "nothing_to_fill"       # 官網無此兩欄，無可補
    return True, "ok"


def fill_gap(acnt: str, country: str | None, birthday: str | None) -> int:
    """執行窄 UPDATE。回異動列數（冪等：重跑時 COALESCE 不會改變已有值）。"""
    from cpbl.db import conn

    with conn() as c:
        return c.execute(FILL_SQL, (country, birthday, acnt)).rowcount


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
        log.info("  未寫入：%s %s（徵狀 %s／判定 %s）",
                 r["id"], r["db_name"], r["symptom"], r.get("write_reason"))


def _loop(args, targets: list[tuple[str, str]], rows: list[dict]) -> None:
    from cpbl.ingest._browser import check_circuit
    from cpbl.ingest.cpbl_player_bio import parse_bio

    consec_fail = 0
    for i, (acnt, name) in enumerate(targets, 1):
        try:
            time.sleep(args.delay)
            html, route = fetch(acnt)
            (args.html_dir / f"{acnt}.html").write_text(html)
            bio = parse_bio(html)
            sym = symptom(html, bio)
            may_write, reason = write_decision(bio, name)
            wrote = False
            if may_write and not args.dry_run:
                fill_gap(acnt, bio["country"], bio["birthday"])
                wrote = True
            elif not may_write:
                log.warning("[%d/%d] %s %s 判定 %s → 跳過寫入（徵狀 %s）",
                            i, len(targets), acnt, name, reason, sym)
            # 挑戰頁不是「該員沒資料」而是節流訊號：連續出現要跟 fetch 例外一樣中止整輪，
            # 否則剩餘名單會繼續打站，把節流打成深度封鎖（在 try 外統一判，避免自己拋的
            # RuntimeError 被本層 except 接住後誤記成 fetch_failed）
            consec_fail = consec_fail + 1 if sym == "non_cpbl_page" else 0
            log.info("[%d/%d] %s %s → %s（route=%s, len=%d, wrote=%s）country=%s birthday=%s",
                     i, len(targets), acnt, name, sym, route, len(html), wrote,
                     bio["country"], bio["birthday"])
            rows.append({"id": acnt, "db_name": name, "symptom": sym, "route": route,
                         "html_len": len(html), "wrote": wrote, "write_reason": reason,
                         "page_name": bio["name"], "parsed": bio})
        except Exception as e:  # noqa: BLE001 — 單人失敗不中斷，連續失敗由斷路器擋
            consec_fail += 1
            log.error("[%d/%d] %s %s 失敗：%s", i, len(targets), acnt, name, e)
            rows.append({"id": acnt, "db_name": name, "symptom": "fetch_failed",
                         "wrote": False, "write_reason": "fetch_failed",
                         "error": str(e)[:300]})
        check_circuit(consec_fail)


if __name__ == "__main__":
    main()
