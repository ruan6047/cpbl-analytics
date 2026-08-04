"""INGEST-PLAYER-BIO-GAP2：補齊 14 人的 handedness 與 batch 2 其餘 bio 欄。

延續 `backfill_player_bio_gap1.py` 的作法（釘死名單＋原始 HTML 存證＋窄寫入），
但寫入的是**另外八欄**：`bats`／`throws`（14 人皆缺）與
`height_cm`／`weight_kg`／`debut`／`education`／`birthplace`／`draft`（batch 2 那 8 人缺）。

**為什麼不走 canonical `cpbl_player_bio._upsert`**：它對後六欄是**無條件 `EXCLUDED` 覆蓋**，
並會用頁面姓名改寫 `name`。GAP1 那批人六欄全 NULL、無值可失，但**本卡涵蓋的 batch 1 六人
是有值的**（height／weight／debut／birthplace 來自更早的解析器）——撞到退化頁或部分解析頁
就會被洗成 NULL，而生產端 `sync_table players` 是 `DO UPDATE SET` 無條件覆蓋，隔天照抄。

故八欄一律 `COALESCE(既有, 新值)`：**只補缺、不覆蓋**是語句本身的性質，不依賴守衛判斷是否
該寫。`name`／`country`／`birthday` 不在語句裡，結構上不可能被碰到（`country`／`birthday`
是 GAP1 的交付值，本卡必須逐位保持不變）。

用法::

    uv run python scripts/backfill_player_bio_gap2.py --dry-run --limit 2 --html-dir /path/scratch
    uv run python scripts/backfill_player_bio_gap2.py --html-dir /path/scratch
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("cpbl.bio_gap2")

CPBL_MARK = "全球資訊網"

# 卡面 v2 核准的 14 人。batch 1 只缺 bats／throws；batch 2 另缺六欄。
# 釘死而不動態撈的理由同 GAP1：核可的站台請求量是固定 14 頁，範圍有變必須由人改常數。
BATCH1_IDS: dict[str, str] = {
    "0000007573": "李博登", "0000007579": "韋禮加", "0000007583": "柯威士",
    "0000007588": "奧德銳", "0000007590": "那瑪夏", "0000007603": "凱樂",
}
BATCH2_IDS: dict[str, str] = {
    "0000004796": "鎛銳", "0000006891": "力亞士", "0000007547": "石萬金",
    "0000007554": "龍聖", "0000007555": "霸鉧德", "0000007556": "波賽樂",
    "0000007558": "黃博多", "0000007559": "蒙德茲",
}
EXPECTED_GAP_IDS: dict[str, str] = {**BATCH1_IDS, **BATCH2_IDS}

# 本卡的寫入邊界契約（tests/test_bio_gap2_backfill.py 對它斷言）。
# 八欄全部 COALESCE；name／country／birthday 不在語句中。
FILL_COLS = ("bats", "throws", "height_cm", "weight_kg",
             "debut", "education", "birthplace", "draft")
FILL_SQL = (
    "UPDATE cpbl.players SET "
    + ", ".join(f"{c} = COALESCE({c}, %s)" for c in FILL_COLS)
    + ", bio_updated_at = now() WHERE id = %s"
)


def check_scope(found: set[str]) -> set[str]:
    """範圍閘門（非對稱，理由同 GAP1）。

    - `found - expected`（DB 有、卡面無）＝ 未授權的範圍擴張 → 硬中止。
    - `expected - found`（卡面有、DB 無）＝ 已補滿 → 視為進度並跳過。

    `found` 以 `throws IS NULL` 為判準：實查全表 3767 人中恰為這 14 人，
    是本卡最窄且可驗證的不變式。
    """
    extra = sorted(found - set(EXPECTED_GAP_IDS))
    if extra:
        raise SystemExit(
            "發現卡面未授權的缺 handedness 球員，中止（維持現狀，不動任何資料）。\n"
            f"  多出（DB 有、卡面無）：{extra}\n"
            "  本卡核可的站台請求量固定 14 頁，不得擴張。確認後由人工更新 EXPECTED_GAP_IDS。")
    return set(EXPECTED_GAP_IDS) - found


def target_ids(cur) -> list[tuple[str, str]]:
    """執行目標＝仍缺 handedness 的授權球員，加上 batch 2 仍缺六欄者。

    兩個條件分開判：batch 1 只需 handedness，補完即完成；batch 2 另需六欄，
    若官網缺其中某欄會留 NULL，故以 `height_cm`（頁面必有、可驗證）當完成判準，
    避免因官網無 `draft`／`education` 而每次重跑都重抓。
    """
    cur.execute("SELECT id FROM cpbl.players WHERE throws IS NULL ORDER BY id")
    found = {r[0] for r in cur.fetchall()}
    done = check_scope(found)
    if done:
        log.info("handedness 已補滿 %d/%d 人", len(done), len(EXPECTED_GAP_IDS))
    cur.execute(
        "SELECT id, name FROM cpbl.players WHERE id = ANY(%s) "
        "AND (throws IS NULL OR bats IS NULL "
        "     OR (height_cm IS NULL AND id = ANY(%s))) ORDER BY id",
        (list(EXPECTED_GAP_IDS), list(BATCH2_IDS)))
    targets = [(r[0], r[1]) for r in cur.fetchall()]
    if not targets:
        log.info("14 人皆已補滿，無事可做（no-op）。")
    return targets


def fetch(acnt: str, cache_dir: Path | None = None) -> tuple[str, str]:
    """取 person 頁 HTML。`cache_dir` 存在該檔時**不發請求**，直接用既有存證。

    為什麼提供快取路徑：bio 是靜態資料，而本專案的爬蟲紅線是「盡量少打站台」
    （HiNet 挑戰對連續冷啟動會升級節流）。`INGEST-PLAYER-BIO-GAP1` 於 2026-08-03
    14:37 已對同一批 14 人抓過完整 person 頁且 14/14 皆 `person_page_parsed`，
    重抓換不到新資訊、只增加撞挑戰頁的風險。

    **這是顯式選項而非私下繞過**：用了就會記在報告的 `route` 欄（`cache:<路徑>`），
    交付文件與查核者都看得到本輪實際發出幾次請求。快取缺該檔時自動回退為真正抓取。
    """
    from cpbl.ingest.cpbl_player_bio import parse_bio

    if cache_dir is not None:
        cached = cache_dir / f"{acnt}.html"
        if cached.exists():
            return cached.read_text(), f"cache:{cached}"

    from cpbl.ingest._browser import session

    path = f"/team/person?acnt={acnt}"
    html = session().page_html(path, wait="domcontentloaded")
    route = "domcontentloaded"
    if parse_bio(html)["name"] is None and CPBL_MARK not in html:
        html = session().page_html(path, wait="networkidle", force=True)
        route = "domcontentloaded→networkidle(reload)"
    return html, route


def symptom(html: str, bio: dict) -> str:
    if CPBL_MARK not in html:
        return "non_cpbl_page"
    if bio["name"] is None:
        return "cpbl_page_no_person"
    if all(bio.get(c) is None for c in FILL_COLS):
        return "person_page_no_bio_fields"
    return "person_page_parsed"


def write_decision(bio: dict, db_name: str) -> tuple[bool, str]:
    """窄 UPDATE 已限制寫入範圍，此處只擋「值根本不是這個人的」。"""
    if bio["name"] is None:
        return False, "no_person_on_page"
    if bio["name"] != db_name:
        return False, "name_mismatch"   # 可能抓錯人，也可能官網改名——交人工判斷
    if all(bio.get(c) is None for c in FILL_COLS):
        return False, "nothing_to_fill"
    return True, "ok"


def fill_gap(acnt: str, bio: dict) -> int:
    from cpbl.db import conn

    with conn() as c:
        return c.execute(FILL_SQL, (*(bio.get(col) for col in FILL_COLS), acnt)).rowcount


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html-dir", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--html-cache", type=Path,
                    help="既有 HTML 存證目錄；命中即不發請求（route 記為 cache:）")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")

    from cpbl.db import conn

    with conn() as c:
        targets = target_ids(c.cursor())
    if args.limit:
        targets = targets[:args.limit]
    log.info("目標 %d 人（limit=%s dry_run=%s）", len(targets), args.limit, args.dry_run)
    args.html_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    try:
        _loop(args, targets, rows)
    finally:
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
            html, route = fetch(acnt, args.html_cache)
            (args.html_dir / f"{acnt}.html").write_text(html)
            bio = parse_bio(html)
            sym = symptom(html, bio)
            may_write, reason = write_decision(bio, name)
            wrote = False
            if may_write and not args.dry_run:
                fill_gap(acnt, bio)
                wrote = True
            elif not may_write:
                log.warning("[%d/%d] %s %s 判定 %s → 跳過寫入（徵狀 %s）",
                            i, len(targets), acnt, name, reason, sym)
            # 挑戰頁是節流訊號而非「該員沒資料」：連續出現要中止整輪（判定放在 try 外，
            # 免得自己拋的 RuntimeError 被本層 except 接住後誤記成 fetch_failed）
            consec_fail = consec_fail + 1 if sym == "non_cpbl_page" else 0
            log.info("[%d/%d] %s %s → %s（route=%s, wrote=%s）bats=%s throws=%s ht=%s",
                     i, len(targets), acnt, name, sym, route, wrote,
                     bio.get("bats"), bio.get("throws"), bio.get("height_cm"))
            rows.append({"id": acnt, "db_name": name, "symptom": sym, "route": route,
                         "html_len": len(html), "wrote": wrote, "write_reason": reason,
                         "page_name": bio["name"], "parsed": bio})
        except Exception as e:  # noqa: BLE001 — 單人失敗不中斷，連續失敗由斷路器擋
            consec_fail += 1
            log.error("[%d/%d] %s %s 失敗：%s", i, len(targets), acnt, name, e)
            rows.append({"id": acnt, "db_name": name, "symptom": "fetch_failed",
                         "wrote": False, "write_reason": "fetch_failed", "error": str(e)[:300]})
        check_circuit(consec_fail)


if __name__ == "__main__":
    main()
