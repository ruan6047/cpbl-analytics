"""DATA-TIE-REMEDY1：5 場 0:0 隱形和局的取證、補爬與影響評估。

每個階段一個 subcommand，輸出 JSON artifact 供交付報告引用。**所有宣稱由本腳本產生**，
禁止人工計數（見 memory「完整性宣稱須自動化證明」）。

    uv run python scripts/data_tie_remedy1.py evidence     # 官方 box 取證（Playwright）
    uv run python scripts/data_tie_remedy1.py consumers    # 完成判準消費點盤點
    uv run python scripts/data_tie_remedy1.py impact       # 衍生表影響評估（不執行重建）

爬蟲紅線（docs/CPBL_SITE_MAP.md §2）：單次嘗試、逐場間隔數十秒、失敗即中止整輪，
冷卻 15–20 分鐘後只重試一次。本腳本**不重跑整輪**，失敗場次由呼叫端決定是否重試。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from typing import Any

# 5 場已確認 0:0 和局（DATA-RULES-AUDIT1 §2 候選 233，standings.tie 逐年對帳 7/7）
GAMES: tuple[tuple[int, str, int], ...] = (
    (2018, "A", 124),
    (2021, "A", 256),
    (2023, "A", 119),
    (2023, "A", 175),
    (2025, "A", 233),
)

EVIDENCE_DIR = "docs/research/DATA-TIE-REMEDY1"

# box 頁的 hidden token：挑戰頁沒有它，用來確認拿到的是真 box 頁而非挑戰頁
_HIDDEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _dump(obj: Any, out: str | None) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"written: {out} ({len(text)} bytes)")
    else:
        print(text)


# ---------------------------------------------------------------- evidence


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _parse_box(html: str) -> dict:
    """從 box 頁 HTML 抽「官方完賽證據」的最小集合。

    解析錨點（2026-08-05 實測，五場同構）：

    * ``<div class="game_detail final">``——官方賽事狀態標記（``final`` = 已完賽）。
    * ``<div class="linescore scrollable">``——``tr.inning`` 的 ``th`` 為局號、
      ``tr.away``/``tr.home`` 的 ``td`` 為逐局得分；**局號最大值即實際比賽局數**
      （雨裁和局如 2025/A/233 只到 6，打滿延長如 2018/A/124 到 12）。
    * ``<div class="linescore fixed">``——R/H/E 合計，用來對帳 0:0 與安打/失誤存在。
    * 賽事資訊 ``<div class="info">``——裁判/時間/觀眾，存在即證明官方認定此場已進行。
    """
    out: dict[str, Any] = {}

    m = re.search(r'<div class="game_detail\s+([a-z_]+)"', html)
    out["official_status_class"] = m.group(1) if m else None

    # 隊名（away/home 順序由 tr class 決定，不靠位置）
    nm = re.search(r'<div class="team_name fixed">(.*?)</div>', html, re.S)
    if nm:
        for side in ("away", "home"):
            t = re.search(rf'<tr class="{side}">(.*?)</tr>', nm.group(1), re.S)
            if t:
                full = re.search(r'<span class="full">(.*?)</span>', t.group(1), re.S)
                out[f"{side}_team"] = _strip(full.group(1)) if full else None

    # 逐局得分
    ls = re.search(r'<div class="linescore scrollable">(.*?)</div>', html, re.S)
    if ls:
        seg = ls.group(1)
        inn = re.search(r'<tr class="inning">(.*?)</tr>', seg, re.S)
        if inn:
            out["innings"] = [int(x) for x in re.findall(r"<span>(\d+)</span>", inn.group(1))]
        for side in ("away", "home"):
            t = re.search(rf'<tr class="{side}">(.*?)</tr>', seg, re.S)
            if t:
                out[f"{side}_by_inning"] = [
                    _strip(c) for c in re.findall(r"<td>(.*?)</td>", t.group(1), re.S)]

    # R / H / E
    rhe = re.search(r'<div class="linescore fixed">(.*?)</div>', html, re.S)
    if rhe:
        for side in ("away", "home"):
            t = re.search(rf'<tr class="{side}">(.*?)</tr>', rhe.group(1), re.S)
            if t:
                vals = [_strip(c) for c in re.findall(r"<td>(.*?)</td>", t.group(1), re.S)]
                if len(vals) >= 3:
                    out[f"{side}_rhe"] = vals[:3]

    # 賽事資訊 <div class="GameNote">：<li><span>標籤</span>值</li>
    for label, key in (("主審", "home_plate_umpire"), ("時間", "duration"),
                       ("觀眾", "attendance")):
        m = re.search(rf"<li><span>{label}</span>([^<]*)</li>", html)
        if m:
            out[key] = m.group(1).strip()

    # 導出欄：實際局數與 0:0 判定（供 evidence 表與交付報告直接引用）。
    #
    # ⚠️ 局數**不可**取表頭最大值：表頭恆為 1..9（延長賽才加欄），雨裁和局的 7-9 欄是空的。
    # 必須數「有值的格子」。兩隊格數可能不等——2023/A/175 客隊 8、主隊 7，即比賽止於
    # 8 局上（主隊未打 8 局下）。故同時保留兩側，並以較小者對照規章 §38 的 5 局門檻。
    for side in ("away", "home"):
        cells = out.get(f"{side}_by_inning") or []
        out[f"{side}_innings_batted"] = sum(1 for c in cells if c != "")
    a_inn, h_inn = out.get("away_innings_batted"), out.get("home_innings_batted")
    if a_inn is not None and h_inn is not None:
        out["innings_played"] = max(a_inn, h_inn)          # 比賽推進到的局數
        out["complete_innings"] = min(a_inn, h_inn)        # 雙方皆完成的局數
        # 規章 §38：例行賽滿 5 局始得裁定和局（docs/reference/聯盟規章.txt）
        out["meets_rule38_five_innings"] = out["complete_innings"] >= 5
    try:
        out["away_runs"] = int(out["away_rhe"][0])
        out["home_runs"] = int(out["home_rhe"][0])
        out["is_scoreless_tie"] = out["away_runs"] == 0 and out["home_runs"] == 0
    except (KeyError, ValueError, IndexError):
        out["is_scoreless_tie"] = None
    return out


def cmd_evidence(args: argparse.Namespace) -> dict:
    """Playwright 逐場抓官方 box 頁；HTML + sha256 + fetched_at 存證。

    紀律：單次嘗試（`page_html` 自身的 run 內退避重試屬既有自癒機制），逐場間隔
    ``--delay`` 秒；**任一場失敗即中止整輪**（連續失敗＝節流訊號，續打會升級封鎖）。
    """
    from cpbl.ingest._browser import session

    targets = [g for g in GAMES if not args.only or f"{g[0]}/{g[1]}/{g[2]}" in args.only]
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    results: list[dict] = []
    aborted_at: str | None = None

    s = session()
    for i, (year, kind, sno) in enumerate(targets):
        gid = f"{year}/{kind}/{sno}"
        if i:
            print(f"[{_now_iso()}] 間隔 {args.delay}s（爬蟲節流紀律）…", flush=True)
            time.sleep(args.delay)
        path = f"/box?year={year}&KindCode={kind}&gameSno={sno}"
        url = f"https://www.cpbl.com.tw{path}"
        print(f"[{_now_iso()}] fetch {gid} → {url}", flush=True)
        rec: dict[str, Any] = {"game": gid, "year": year, "kind_code": kind,
                               "game_sno": sno, "source_url": url}
        try:
            html = s.page_html(path, require=_HIDDEN_RE)
        except Exception as e:  # noqa: BLE001 — 失敗即中止整輪，交呼叫端冷卻後重試
            rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:400],
                       fetched_at=_now_iso())
            results.append(rec)
            aborted_at = gid
            print(f"[{_now_iso()}] FAIL {gid}：{rec['error']}", file=sys.stderr, flush=True)
            print(f"[{_now_iso()}] 中止整輪（紅線：連續打站會升級封鎖），"
                  f"冷卻 15–20 分鐘後只重試一次", file=sys.stderr, flush=True)
            break

        sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
        fname = f"{year}-{kind}-{sno}_box.html"
        with open(os.path.join(EVIDENCE_DIR, fname), "w", encoding="utf-8") as fh:
            fh.write(html)
        rec.update(ok=True, fetched_at=_now_iso(), payload_sha256=sha,
                   html_bytes=len(html.encode("utf-8")), html_file=fname,
                   parsed=_parse_box(html))
        results.append(rec)
        print(f"[{_now_iso()}] OK {gid} sha256={sha[:16]}… bytes={rec['html_bytes']}",
              flush=True)

    ok_n = sum(1 for r in results if r.get("ok"))
    payload = {
        "generated_at": _now_iso(),
        "targets": [f"{y}/{k}/{s}" for y, k, s in targets],
        "attempted": len(results),
        "succeeded": ok_n,
        "aborted_at": aborted_at,
        "gate_min_success": 2,
        "gate_passed": ok_n >= 2,
        "results": results,
    }
    return payload


# ---------------------------------------------------------------- parse


def cmd_parse(args: argparse.Namespace) -> dict:
    """**離線**重新解析已存證的 box HTML（不打站）。

    取證與解析分離：解析器改版可重跑本命令，不需再次爬取（爬蟲紅線：少打站）。
    sha256 就地重算並與取證當時的值比對，確保存證檔未被竄改。
    """
    fetch_meta: dict[str, dict] = {}
    meta_path = f"{EVIDENCE_DIR}/evidence_fetch.json"
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            for r in json.load(fh).get("results", []):
                fetch_meta[r["game"]] = r

    results = []
    for year, kind, sno in GAMES:
        gid = f"{year}/{kind}/{sno}"
        fname = f"{year}-{kind}-{sno}_box.html"
        path = os.path.join(EVIDENCE_DIR, fname)
        rec: dict[str, Any] = {"game": gid, "year": year, "kind_code": kind,
                               "game_sno": sno, "html_file": fname}
        if not os.path.exists(path):
            rec.update(ok=False, error="存證檔不存在（取證未成功）")
            results.append(rec)
            continue
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
        prior = fetch_meta.get(gid, {})
        rec.update(
            ok=True,
            payload_sha256=sha,
            sha256_matches_fetch=(prior.get("payload_sha256") == sha
                                  if prior.get("payload_sha256") else None),
            fetched_at=prior.get("fetched_at"),
            source_url=prior.get("source_url"),
            parsed=_parse_box(html),
        )
        results.append(rec)

    ok = [r for r in results if r.get("ok")]
    return {
        "generated_at": _now_iso(),
        "parsed_games": len(ok),
        "all_scoreless_tie": all(r["parsed"].get("is_scoreless_tie") for r in ok) if ok else None,
        "all_status_final": all(r["parsed"].get("official_status_class") == "final"
                                for r in ok) if ok else None,
        "all_meet_rule38": all(r["parsed"].get("meets_rule38_five_innings")
                               for r in ok) if ok else None,
        "min_complete_innings": min((r["parsed"].get("complete_innings") or 0)
                                    for r in ok) if ok else None,
        "results": results,
    }


# ---------------------------------------------------------------- consumers

# refresh 鏈模組：Phase 1 **不得**換判準（G4 觀測期進行中，換判準會改變爬取母體）。
CHAIN_MODULES = (
    "src/cpbl/ingest/run_refresh_recent.py",
    "src/cpbl/ingest/cpbl_pitch_tracking.py",
    "src/cpbl/ingest/cpbl_gamelog.py",
)

# 刻意凍結在舊判準的檔案（換掉會破壞既有結論的可重現性／污染觀測窗）：
#   * completion.py 本身＝舊判準的定義處。
#   * data_rules_audit1.py＝AUDIT1 的取證腳本，必須能重現當初的數字。
#   * g4_phase_a_metrics.py＝G4 觀測期指標，判準一換觀測就不可比。
FROZEN_FILES = (
    "src/cpbl/completion.py",
    "scripts/data_rules_audit1.py",
    "scripts/g4_phase_a_metrics.py",
)

# 本批切換範圍（卡面：非鏈的 API／features／models）。其餘 scripts/ 屬研究產物，不在本批。
SWITCH_PREFIXES = ("src/cpbl/api/", "src/cpbl/features/", "src/cpbl/models/")

# 在切換範圍內、但**經逐點檢視後刻意不換**者（file:line → 理由）。
# 這些不是遺漏：留在此表代表已判讀，理由隨程式碼一起版控。
REVIEWED_NOT_SWITCHED = {
    "src/cpbl/api/routers/info.py": (
        "predictions_today＝排在**今天**且尚無比分者；母體限定 game_date = CURRENT_DATE，"
        "5 場歷史和局（2018–2025）不可能落入。其時區界線問題屬 AUDIT1 的 D7，非本卡。"),
    "src/cpbl/api/routers/leaders.py": (
        "`home_score+away_score DESC` 是 ORDER BY 排序鍵（單場最多合計得分紀錄），"
        "**不是**完成判準——grep 的偽陽性，改了會破壞排序語意。"),
    "src/cpbl/models/matchup.py": (
        "`home_score + away_score = 0 AND game_date >= today`＝**未來待預測**場次（判準的反面）。"
        "5 場和局皆為歷史日期，被 game_date >= today 擋掉，語意不受影響。"),
    "src/cpbl/models/winprob_strength.py": (
        "此處的完成場母體會進 `sno_md5`/`games_md5` **可重現性雜湊**（iteration 2 查核 F2 的"
        "指定修法：依 as_of 重新界定母體，讓部分重跑逐位重現）。換判準會讓既有紀錄的雜湊"
        "全部對不上，屬研究產物的 provenance 破壞。5 場／約 13,000 場的量級不值得，"
        "交需求方裁定（見影響評估）。"),
    "src/cpbl/models/winprob_val.py": (
        "同 winprob_strength：全押主場基準線屬研究產物，且 WP-VAL1 全 scope 已判 unsupported。"
        "與該家族一起交需求方裁定，不在本卡單獨改動。"),
}

# 完成判準的兩種寫法：直接手寫比分和，或引用舊 helper。
_PATTERNS = (
    (re.compile(r"home_score\s*\+\s*away_score"), "score_sum"),
    (re.compile(r"completed_games_sql\s*\("), "legacy_helper"),
    (re.compile(r"completed_games_sql_with_evidence\s*\("), "evidence_helper"),
    (re.compile(r"\bis_completed\s*\("), "legacy_pyfn"),
    (re.compile(r"\bis_completed_game\s*\("), "evidence_pyfn"),
)


def cmd_consumers(args: argparse.Namespace) -> dict:
    """盤點全 repo 的完成判準消費點，並依 chain / non-chain 分類（機器產生，非人工計數）。"""
    import subprocess

    roots = ["src", "scripts", "tests"]
    files = subprocess.run(
        ["git", "ls-files", *roots], capture_output=True, text=True, check=True
    ).stdout.split()

    hits = []
    for path in files:
        if not path.endswith(".py"):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for rx, kind in _PATTERNS:
                if rx.search(line):
                    legacy = kind in ("score_sum", "legacy_helper", "legacy_pyfn")
                    in_scope = path.startswith(SWITCH_PREFIXES)
                    # 只有「仍是舊判準」的那一行才算已判讀不換；同檔的 import／常數行
                    # 已是新判準，不該被貼上這個標籤。
                    reviewed = REVIEWED_NOT_SWITCHED.get(path) if legacy else None
                    hits.append({
                        "file": path, "line": i, "match_kind": kind,
                        "is_chain": path in CHAIN_MODULES,
                        "is_frozen": path in FROZEN_FILES,
                        "is_test": path.startswith("tests/"),
                        "in_switch_scope": in_scope,
                        "reviewed_not_switched": reviewed,
                        # 本批應切換而尚未切換者（已判讀者不算未決）
                        "pending_switch": (legacy and in_scope
                                           and path not in CHAIN_MODULES
                                           and path not in FROZEN_FILES
                                           and reviewed is None),
                        "code": line.strip()[:160],
                    })
                    break

    by_kind: dict[str, int] = {}
    for h in hits:
        by_kind[h["match_kind"]] = by_kind.get(h["match_kind"], 0) + 1
    prod = [h for h in hits if not h["is_test"]]
    pending = [h for h in hits if h["pending_switch"]]
    switched = [h for h in hits if h["in_switch_scope"]
                and h["match_kind"] in ("evidence_helper", "evidence_pyfn")]
    return {
        "generated_at": _now_iso(),
        "total_hits": len(hits),
        "by_match_kind": by_kind,
        "production_hits": len(prod),
        "chain_hits": sum(1 for h in prod if h["is_chain"]),
        "frozen_hits": sum(1 for h in prod if h["is_frozen"]),
        "switch_scope_hits": sum(1 for h in prod if h["in_switch_scope"]),
        "switched_to_evidence": sorted(f"{h['file']}:{h['line']}" for h in switched),
        "pending_switch_count": len(pending),
        "pending_switch": sorted(f"{h['file']}:{h['line']}" for h in pending),
        "reviewed_not_switched": sorted(
            {f"{h['file']}:{h['line']}" for h in hits if h["reviewed_not_switched"]}),
        "reviewed_not_switched_reasons": REVIEWED_NOT_SWITCHED,
        "chain_deferred_to_phase2": sorted(
            f"{h['file']}:{h['line']}" for h in prod if h["is_chain"]),
        "hits": hits,
    }


# ---------------------------------------------------------------- write-evidence

# 需求方核准來源：GitHub Issue #90（DATA-TIE-REMEDY1 卡面即核准清單）
_APPROVER = "ruan6047"
_APPROVAL_SOURCE = "GitHub Issue #90 (DATA-TIE-REMEDY1)"

_EVIDENCE_UPSERT = """
INSERT INTO cpbl.game_completion_evidence
    (year, kind_code, game_sno, evidence_kind, source_url, payload_sha256,
     innings_played, approved_by, note)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (year, kind_code, game_sno, evidence_kind) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    payload_sha256 = EXCLUDED.payload_sha256,
    innings_played = EXCLUDED.innings_played,
    approved_by = EXCLUDED.approved_by,
    note = EXCLUDED.note
"""


def cmd_write_evidence(args: argparse.Namespace) -> dict:
    """把 5 場的完賽證據寫入 ``cpbl.game_completion_evidence``（冪等 UPSERT）。

    每場寫兩列，兩種證據互相獨立：

    * ``requester_approved_tie``——需求方領域知識核准（Issue #90 即核准清單）。
    * ``official_box_final``——官網 box 頁直接取證（``game_detail=final`` ＋ 記分板）。

    **只寫解析結果自證為 0:0 且滿規章 §38 五局門檻的場次**；任一條件不成立即跳過並記錄，
    不硬寫（fail-closed）。
    """
    from cpbl.db import conn

    with open(f"{EVIDENCE_DIR}/evidence_parsed.json", encoding="utf-8") as fh:
        parsed = json.load(fh)

    written, skipped = [], []
    with conn() as c, c.cursor() as cur:
        for r in parsed["results"]:
            p = r.get("parsed") or {}
            gid = r["game"]
            if not r.get("ok"):
                skipped.append({"game": gid, "reason": "取證未成功"})
                continue
            if not p.get("is_scoreless_tie") or p.get("official_status_class") != "final" \
                    or not p.get("meets_rule38_five_innings"):
                skipped.append({"game": gid, "reason": "解析未自證 0:0 / final / §38 五局",
                                "parsed": {k: p.get(k) for k in
                                           ("is_scoreless_tie", "official_status_class",
                                            "complete_innings")}})
                continue
            innings = p.get("innings_played")
            note_box = (f"官方 box：{p.get('away_team')} {p.get('away_rhe')} @ "
                        f"{p.get('home_team')} {p.get('home_rhe')}；"
                        f"客隊 {p.get('away_innings_batted')} 局／主隊 "
                        f"{p.get('home_innings_batted')} 局；時間 {p.get('duration')}；"
                        f"觀眾 {p.get('attendance')}；主審 {p.get('home_plate_umpire')}")
            for kind, approver, note in (
                ("requester_approved_tie", _APPROVER,
                 f"需求方核准來源：{_APPROVAL_SOURCE}"),
                ("official_box_final", None, note_box),
            ):
                cur.execute(_EVIDENCE_UPSERT, (
                    r["year"], r["kind_code"], r["game_sno"], kind,
                    r.get("source_url"), r.get("payload_sha256"), innings, approver, note))
                written.append({"game": gid, "evidence_kind": kind})

        cur.execute("SELECT count(*) FROM cpbl.game_completion_evidence")
        total = cur.fetchone()[0]

    return {"generated_at": _now_iso(), "written": len(written),
            "skipped": skipped, "rows_in_table": total, "detail": written}


# ---------------------------------------------------------------- backfill


def _game_data_counts(cur, year: str, kind: str, sno: int) -> dict:
    counts = {}
    for table, key in (("game_scoreboard", "scoreboard"), ("game_livelog", "livelog"),
                       ("batting_gamelog", "batting_box"), ("pitching_gamelog", "pitching_box"),
                       ("game_plate_appearances", "canonical_pa")):
        cur.execute(
            f"SELECT count(*) FROM cpbl.{table} "  # noqa: S608 — table 名為本函式內建常數
            "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind, sno))
        counts[key] = cur.fetchone()[0]
    return counts


def cmd_backfill(args: argparse.Namespace) -> dict:
    """5 場核心資料補爬：走既有單場路徑 `cpbl_gamelog.scrape_gamelogs`（冪等 UPSERT）。

    鏈安全：這 5 場是 2018–2025 的歷史年，**不會**進入當季 lagging 集合，
    也不觸碰 `run_refresh_recent`。逐場間隔數十秒；任一場失敗即中止整輪。

    官方若根本沒有該場逐場資料，如實記錄該場**降級**（只有 evidence 與比分，
    無逐打席），不硬湊。
    """
    from cpbl.db import conn
    from cpbl.ingest.cpbl_gamelog import scrape_game_details, scrape_gamelogs

    results, aborted_at = [], None
    for i, (year, kind, sno) in enumerate(GAMES):
        gid = f"{year}/{kind}/{sno}"
        if i:
            print(f"[{_now_iso()}] 間隔 {args.delay}s（爬蟲節流紀律）…", flush=True)
            time.sleep(args.delay)
        with conn() as c:
            before = _game_data_counts(c.cursor(), year, kind, sno)
        rec: dict[str, Any] = {"game": gid, "before": before}
        print(f"[{_now_iso()}] backfill {gid} …", flush=True)
        try:
            got = scrape_gamelogs(year, [sno], kind)
            det = scrape_game_details(year, [sno], kind)
        except Exception as e:  # noqa: BLE001 — 失敗即中止整輪，冷卻後單次重試
            rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:400])
            results.append(rec)
            aborted_at = gid
            print(f"[{_now_iso()}] FAIL {gid}：{rec['error']}", file=sys.stderr, flush=True)
            break
        with conn() as c:
            after = _game_data_counts(c.cursor(), year, kind, sno)
        # 官方無逐場資料 → 降級（不視為失敗，但必須如實標記）
        degraded = after["livelog"] == 0 and after["scoreboard"] == 0
        rec.update(ok=True, scraped=got, details=det, after=after, degraded=degraded)
        results.append(rec)
        print(f"[{_now_iso()}] OK {gid} {after}"
              f"{' ⚠️ 降級：官方無逐場資料' if degraded else ''}", flush=True)

    ok = [r for r in results if r.get("ok")]
    return {
        "generated_at": _now_iso(),
        "attempted": len(results),
        "succeeded": len(ok),
        "aborted_at": aborted_at,
        "degraded_games": [r["game"] for r in ok if r.get("degraded")],
        "results": results,
    }


# ---------------------------------------------------------------- impact

# 受影響的 (年, kind)：5 場所在的球季。衍生表若要吸收這 5 場，重建範圍以此為界。
AFFECTED_YEAR_KINDS = sorted({(y, k) for y, k, _ in GAMES})

# 衍生表 → (重建指令, 重建粒度, 風險註記)。**本命令只評估，不執行任何重建。**
DERIVED_TABLES: tuple[tuple[str, str, str, str], ...] = (
    ("game_plate_appearances", "cpbl-build-pa --game <year>-<kind>-<sno>", "逐場",
     "canonical PA；本卡已對 5 場逐場執行，故此表已吸收。下列各表都建立在它之上。"),
    ("game_pa_events", "（同 cpbl-build-pa）", "逐場", "隨 PA build 一併產生。"),
    ("game_pa_pitch_mappings", "（同 cpbl-build-pa）", "逐場", "隨 PA build 一併產生。"),
    ("batting_splits", "cpbl-build-splits <year>", "整年重算",
     "分項是**整年重算**不是增量：跑該年會重寫整年所有格。RECALC1 已定案其對帳程序，"
     "重建後須跑對帳（見 memory「分項重算語意」）。"),
    ("pitching_splits", "cpbl-build-splits <year>", "整年重算", "同上。"),
    ("batting_splits_career_base", "（生涯基底＝官方生涯−官方本季，migration 046）", "全庫",
     "生涯基底由官方數字相減而得，**不因本地補爬而變**；但本季分項變動會改變"
     "「基底＋本季」的合成結果，需一併覆核。"),
    ("pitching_splits_career_base", "（同上）", "全庫", "同上。"),
    ("batter_re24", "cpbl-build-sabr", "整年", "RE24 依 canonical PA；新增 5 場的打席會進入。"),
    ("pitcher_re24", "cpbl-build-sabr", "整年", "同上。"),
    ("batter_traits", "cpbl-build-sabr", "整年",
     "AUDIT1 D3 已記錄此表本就落後 canonical（2026/A 僅 78.6%），重建範圍應與 D3 一併規劃。"),
    ("pitcher_traits", "cpbl-build-sabr", "整年", "同上。"),
    ("batter_wsb", "cpbl-build-sabr", "整年", "wSB 依逐打席盜壘事件。"),
    ("catcher_runs", "cpbl-build-sabr", "整年", "捕手 RA9 依逐打席。"),
    ("team_der", "cpbl-build-sabr", "整年", "DER 依逐打席擊球結果。"),
    ("run_expectancy", "cpbl-build-sabr", "全庫矩陣",
     "RE 矩陣由全庫 PA 統計而得。5 場 ≈ 全庫萬分之四量級，數值影響極小，"
     "但矩陣一動就會連帶改變所有 RE24／WP 衍生值——**牽動面最大，最需要需求方裁定**。"),
    ("run_dist", "cpbl-build-sabr", "全庫矩陣", "同上（得分分布）。"),
    ("win_expectancy", "cpbl-build-sabr", "全庫矩陣", "同上（勝率矩陣）。"),
    ("sabr_run_values", "cpbl-build-sabr", "全庫", "線性權重，同屬全庫統計量。"),
    ("game_features", "cpbl-build-features", "全史重建",
     "本卡已改 `features/outcome.py` 的完成判準，但**未重建此表**。重建後 5 場會以"
     "completed=True、home_win=NULL 入表，並讓後續場次的 rfra 場數＋1。"),
    ("model_versions", "cpbl-train-outcome / cpbl-train", "重訓",
     "只有在重訓時才會變。賽果模型的回測母體會多 5 場（和局無勝負，"
     "對準確率分母的處理需確認）。"),
)


def cmd_impact(args: argparse.Namespace) -> dict:
    """衍生表影響評估（**唯讀，不執行任何重建**）——交需求方裁定範圍與時機。"""
    from cpbl.db import conn

    years = sorted({y for y, _ in AFFECTED_YEAR_KINDS})
    rows = []
    with conn() as c, c.cursor() as cur:
        cur.execute("""SELECT table_name FROM information_schema.tables
                       WHERE table_schema='cpbl' AND table_type='BASE TABLE'""")
        existing = {r[0] for r in cur.fetchall()}
        for table, cmd, granularity, note in DERIVED_TABLES:
            rec = {"table": table, "rebuild_command": cmd,
                   "granularity": granularity, "note": note,
                   "exists": table in existing}
            if table in existing:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='cpbl' AND table_name=%s AND column_name='year'",
                    (table,))
                if cur.fetchone():
                    cur.execute(
                        f"SELECT count(*) FROM cpbl.{table} "  # noqa: S608 — 表名來自本檔常數
                        "WHERE year = ANY(%s)", (years,))
                    rec["rows_in_affected_years"] = cur.fetchone()[0]
                    cur.execute(f"SELECT count(*) FROM cpbl.{table}")  # noqa: S608
                    rec["rows_total"] = cur.fetchone()[0]
                else:
                    rec["rows_in_affected_years"] = None  # 無 year 欄（全庫矩陣）
                    cur.execute(f"SELECT count(*) FROM cpbl.{table}")  # noqa: S608
                    rec["rows_total"] = cur.fetchone()[0]
            rows.append(rec)

        # 5 場本身目前的逐場資料落點
        per_game = []
        for y, k, s in GAMES:
            per_game.append({"game": f"{y}/{k}/{s}", **_game_data_counts(cur, y, k, s)})

    return {
        "generated_at": _now_iso(),
        "decision_required": "衍生表是否／何時重建，交需求方裁定；本卡不自動執行。",
        "affected_year_kinds": [f"{y}/{k}" for y, k in AFFECTED_YEAR_KINDS],
        "affected_years": years,
        "five_games_current_data": per_game,
        "derived_tables": rows,
    }


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("evidence", help="Playwright 抓官方 box 頁存證")
    p.add_argument("--out", default=f"{EVIDENCE_DIR}/evidence_fetch.json")
    p.add_argument("--delay", type=float, default=35.0, help="逐場間隔秒數")
    p.add_argument("--only", nargs="*", default=None, help="只抓指定場（如 2018/A/124）")
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("parse", help="離線重解析已存證 box HTML（不打站）")
    p.add_argument("--out", default=f"{EVIDENCE_DIR}/evidence_parsed.json")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("consumers", help="盤點完成判準消費點（chain / non-chain）")
    p.add_argument("--out", default=f"{EVIDENCE_DIR}/consumers.json")
    p.set_defaults(func=cmd_consumers)

    p = sub.add_parser("impact", help="衍生表影響評估（唯讀，不重建）")
    p.add_argument("--out", default=f"{EVIDENCE_DIR}/derived_impact.json")
    p.set_defaults(func=cmd_impact)

    p = sub.add_parser("backfill", help="5 場核心資料補爬（既有單場路徑）")
    p.add_argument("--out", default=f"{EVIDENCE_DIR}/backfill.json")
    p.add_argument("--delay", type=float, default=30.0, help="逐場間隔秒數")
    p.set_defaults(func=cmd_backfill)

    p = sub.add_parser("write-evidence", help="寫入 game_completion_evidence（冪等）")
    p.add_argument("--out", default=f"{EVIDENCE_DIR}/evidence_write.json")
    p.set_defaults(func=cmd_write_evidence)

    args = ap.parse_args()
    _dump(args.func(args), args.out)


if __name__ == "__main__":
    main()
