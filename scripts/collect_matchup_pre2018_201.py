"""#201 一次性本機收集：首批缺口配對的 ≤2017 官方逐年投打對決列 → 唯讀 JSON 資源。

⛔ 一次性工具，不接排程、不寫 DB（DB 連線強制 default_transaction_read_only）。
⛔ 只能本機跑（官網反爬，VPS IP 被擋）；失敗不自動重試，冷卻 15–20 分後再單次續跑。

三段（皆讀寫 --workdir，預設 /tmp/cpbl201-t2）：
  plan     本機 DB 唯讀算首批缺口配對與 score 請求清單 → plan.json
  collect  Playwright 單次 POST（getfightingscore，fightingTeamNo=該年對手隊碼）→ raw.jsonl
           可續跑：已成功的請求跳過；POST 實數跨 run 累計於 ledger.json，達上限即停。
  build    raw.jsonl 過濾成目標配對列 → src/cpbl/resources/matchup_pre2018_rows.v1.json

首批母體（#201 T0 口徑）：生涯列 year=9999、kind A/C/E、官方 PA>0 且 > 2018 起逐打席證據；
對手投手 2024–2026 於 A 或 D 有任何出賽（投球或打擊 gamelog）。請求只打「打者與投手
該年季表都有、且非同隊單一隊」的年度×投手季表隊碼；C/E 只打該賽別當年有出賽的隊。

隊別只取回傳列上的當年 HitterTeamNo／PitcherTeamNo；⛔ 不用選單文字（可能是現名）。
同年季表多隊者（打者或投手）拆分語意未證實 → 列標 split_unverified，不可宣稱完整歸屬。
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

RESOURCE = Path(__file__).resolve().parents[1] / "src/cpbl/resources/matchup_pre2018_rows.v1.json"
SCORE_PATH = "/team/getfightingscore"
POST_CAP_DEFAULT = 696  # 全卡 700 − T1 已送 4
MAX_CONSEC_FAIL = 2
DELAY_S = 1.2
LAST_YEAR = 2017

GAP_SQL = """
WITH m AS (SELECT kind_code k, hitter_acnt h, pitcher_acnt p, coalesce(plate_appearances,0) off,
                  (updated_at AT TIME ZONE 'Asia/Taipei')::date upd
           FROM cpbl.batter_pitcher_matchups WHERE year=9999 AND kind_code IN ('A','C','E')),
ev AS (SELECT pa.kind_code k, pa.hitter_acnt h, pa.end_pitcher_acnt p, gm.game_date d,
              CASE WHEN pa.pre_state->>'half'='1' THEN gm.home_team_code ELSE gm.away_team_code END tc
       FROM cpbl.game_plate_appearances pa
       JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id AND b.state='published'
       JOIN cpbl.games gm ON gm.year=pa.year AND gm.kind_code=pa.kind_code AND gm.game_sno=pa.game_sno
       WHERE pa.state='ready' AND pa.kind_code IN ('A','C','E')),
t AS (SELECT m.k, m.h, m.p, m.off, count(ev.h) FILTER (WHERE ev.d<m.upd AND ev.tc IS NOT NULL) e
      FROM m LEFT JOIN ev USING (k,h,p) GROUP BY 1,2,3,4),
elu AS (SELECT pitcher_acnt a FROM cpbl.pitching_gamelog
        WHERE year BETWEEN 2024 AND 2026 AND kind_code IN ('A','D')
        UNION SELECT hitter_acnt FROM cpbl.batting_gamelog
        WHERE year BETWEEN 2024 AND 2026 AND kind_code IN ('A','D'))
SELECT k, h, p, off, e FROM t
WHERE p IN (SELECT a FROM elu) AND off>0 AND off>e ORDER BY 1,2,3
"""


def _db():
    import psycopg

    from cpbl.config import settings
    return psycopg.connect(settings.database_url,
                           options="-c default_transaction_read_only=on -c statement_timeout=600000")


def cmd_plan(wd: Path) -> None:
    with _db() as c:
        gaps = c.execute(GAP_SQL).fetchall()
        hs, ps, lg = (collections.defaultdict(set) for _ in range(3))
        for pid, y, t in c.execute(
                "SELECT player_id, year, team_id FROM cpbl.batting_seasons WHERE year<=%s", (LAST_YEAR,)):
            hs[(pid, y)].add(t[:3])
        for pid, y, t in c.execute(
                "SELECT player_id, year, team_id FROM cpbl.pitching_seasons WHERE year<=%s", (LAST_YEAR,)):
            ps[(pid, y)].add(t[:3])
        for y, k, t in c.execute(
                "SELECT year, kind_code, home_team_code FROM cpbl.games WHERE year<=%s "
                "UNION SELECT year, kind_code, away_team_code FROM cpbl.games WHERE year<=%s",
                (LAST_YEAR, LAST_YEAR)):
            lg[(y, k)].add(t)
        hitters = sorted({g[1] for g in gaps})
        # 目標打者的全部生涯列（非只缺口）：回傳列 PA 上限檢查用
        career = {f"{k}|{h}|{p}": off for k, h, p, off in c.execute(
            "SELECT kind_code, hitter_acnt, pitcher_acnt, coalesce(plate_appearances,0) "
            "FROM cpbl.batter_pitcher_matchups WHERE year=9999 AND kind_code IN ('A','C','E') "
            "AND hitter_acnt = ANY(%s)", (hitters,))}
    reqs: dict[tuple, set] = collections.defaultdict(set)
    targets = []
    for k, h, p, off, e in gaps:
        years = []
        for y in range(1990, LAST_YEAR + 1):
            ht, pt = hs.get((h, y)), ps.get((p, y))
            if not ht or not pt:
                continue
            series = {t[:3] for t in lg.get((y, k), ())}
            if k != "A" and not (ht & series):
                continue
            teams = [t for t in sorted(pt) if not (ht == {t}) and (k == "A" or t in series)]
            codes = [t + "011" for t in teams if t + "011" in lg.get((y, k), ())]
            if not codes:
                continue
            years.append(y)
            for code in codes:
                reqs[(k, h, y, code)].add(p)
        targets.append({"kind": k, "hitter": h, "pitcher": p, "official_pa": off,
                        "evidence_pa_2018plus": e, "years": years,
                        "split_unverified_years": [y for y in years
                                                   if len(hs[(h, y)]) > 1 or len(ps[(p, y)]) > 1]})
    plan = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "targets": targets,
        "requests": [{"kind": k, "hitter": h, "year": y, "team": t, "pitchers": sorted(v)}
                     for (k, h, y, t), v in sorted(reqs.items())],
        "league_teams": {f"{y}|{k}": sorted(v) for (y, k), v in lg.items()},
        "career_pa": career,
    }
    (wd / "plan.json").write_text(json.dumps(plan, ensure_ascii=False))
    cnt = collections.Counter(r["kind"] for r in plan["requests"])
    print(f"targets={len(targets)} {dict(collections.Counter(t['kind'] for t in targets))} "
          f"requests={len(plan['requests'])} {dict(cnt)} hitters={len(hitters)}")


# ---------------------------------------------------------------- collect

def _load_ledger(wd: Path) -> dict:
    f = wd / "ledger.json"
    if f.exists():
        return json.loads(f.read_text())
    return {"posts_sent": 0, "gets_sent": 0, "aborted_3rdparty": 0, "aborted_page_post": 0,
            "runs": []}


def _validate(rows: list, req: dict, plan: dict) -> str | None:
    """回傳列的語意檢查；不符回錯誤字串（→ 停止整輪）。"""
    league = set(plan["league_teams"].get(f"{req['year']}|{req['kind']}", []))
    for r in rows:
        if str(r.get("Year")) != str(req["year"]) or r.get("KindCode") != req["kind"]:
            return f"年份/賽別不符 Year={r.get('Year')} KindCode={r.get('KindCode')}"
        if r.get("HitterAcnt") != req["hitter"]:
            return f"HitterAcnt 不符 {r.get('HitterAcnt')}"
        if r.get("PitcherTeamNo") != req["team"]:
            return f"PitcherTeamNo={r.get('PitcherTeamNo')} ≠ 請求隊 {req['team']}"
        if r.get("HitterTeamNo") not in league:
            return f"HitterTeamNo={r.get('HitterTeamNo')} 不在 {req['year']}{req['kind']} 賽程隊碼"
        pa = int(r.get("PlateAppearances") or 0)
        cap = plan["career_pa"].get(f"{req['kind']}|{req['hitter']}|{r.get('PitcherAcnt')}")
        if cap is not None and pa > cap:
            return f"逐年 PA {pa} > 生涯 {cap}（{r.get('PitcherAcnt')}）"
    return None


def cmd_collect(wd: Path, cap: int, limit: int | None, only_kind: str | None,
                only_hitter: str | None = None, only_year: int | None = None) -> None:
    from cpbl.ingest import _browser as B
    from cpbl.ingest.cpbl_fighting import _token_in

    plan = json.loads((wd / "plan.json").read_text())
    ledger = _load_ledger(wd)
    raw_f = wd / "raw.jsonl"
    done = set()
    if raw_f.exists():
        for line in raw_f.read_text().splitlines():
            rec = json.loads(line)
            if rec["ok"]:
                done.add((rec["kind"], rec["hitter"], rec["year"], rec["team"]))
    todo = [r for r in plan["requests"] if (r["kind"], r["hitter"], r["year"], r["team"]) not in done]
    if only_kind:
        todo = [r for r in todo if r["kind"] == only_kind]
    if only_hitter:
        todo = [r for r in todo if r["hitter"] == only_hitter]
    if only_year:
        todo = [r for r in todo if r["year"] == only_year]
    # C 先打一筆當語意探針；其餘依打者分組（每打者只載一次頁面）
    todo.sort(key=lambda r: (r["kind"] != "C", r["hitter"], r["kind"], r["year"], r["team"]))
    if limit is not None:
        todo = todo[:limit]
    run = {"started": datetime.now().astimezone().isoformat(timespec="seconds"),
           "posts_before": ledger["posts_sent"], "planned": len(todo), "ok": 0, "fail": 0,
           "stop": None}
    ledger["runs"].append(run)
    state = {"allow_post": False}
    t0 = time.time()

    def save():
        (wd / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=1))

    def route_handler(route, req):
        host = urlparse(req.url).hostname or ""
        if not host.endswith("cpbl.com.tw"):
            ledger["aborted_3rdparty"] += 1
            return route.abort()
        if req.method == "POST":
            if not state["allow_post"] or ledger["posts_sent"] + 1 > cap:
                ledger["aborted_page_post"] += 1
                return route.abort()
            state["allow_post"] = False  # 一次授權只放行一個
            ledger["posts_sent"] += 1
            save()
        elif req.method == "GET":
            ledger["gets_sent"] += 1
        return route.continue_()

    def stop(msg: str) -> None:
        run["stop"] = msg
        run["ended"] = datetime.now().astimezone().isoformat(timespec="seconds")
        run["posts_after"] = ledger["posts_sent"]
        save()
        print("STOP:", msg, flush=True)
        try:
            s.close()
        finally:
            sys.exit(2 if msg != "completed" else 0)

    s = B._Session()
    s._ctx.route("**/*", route_handler)
    loaded, token = None, None
    consec = 0
    with raw_f.open("a") as out:
        for i, req in enumerate(todo):
            if ledger["posts_sent"] + 1 > cap:
                stop(f"POST 將超過上限 {cap}")
            if loaded != req["hitter"]:
                try:
                    s._page.goto(f"{B.BASE}/team/fighting?Acnt={req['hitter']}",
                                 wait_until="networkidle", timeout=45000)
                    s._page.wait_for_timeout(1500)
                    html = s._page.content()
                    token = _token_in(html, "getFightingScore: function")
                except Exception as e:  # noqa: BLE001 — 頁面失敗不重試、不冷啟動
                    stop(f"頁面載入/token 失敗 acnt={req['hitter']}：{str(e)[:200]}")
                loaded = req["hitter"]
            body = urlencode({"acnt": req["hitter"], "kindCode": req["kind"],
                              "year": str(req["year"]), "fightingTeamNo": req["team"],
                              "fightingAcnt": ""})
            h = {"X-Requested-With": "XMLHttpRequest",
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "RequestVerificationToken": token}
            before = ledger["posts_sent"]
            state["allow_post"] = True
            res = s._page.evaluate(B._JS_POST, {"path": SCORE_PATH, "headers": h, "body": body})
            state["allow_post"] = False
            rec = {**{k: req[k] for k in ("kind", "hitter", "year", "team")},
                   "t": round(time.time() - t0, 1), "status": res["status"],
                   "sent": ledger["posts_sent"] > before, "ok": False}
            err = None
            if res["status"] != 200:
                err = f"status={res['status']} {res['text'][:120]}"
            else:
                try:
                    j = json.loads(res["text"])
                    if j.get("Success") is False:
                        err = f"Success=false {str(j)[:120]}"
                    else:
                        rows = json.loads(j.get("FightingScore") or "[]")
                        rec["rows"] = rows
                        rec["ok"] = True
                except ValueError:
                    err = f"非 JSON {res['text'][:120]}"
            if err:
                rec["error"] = err
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if rec["ok"]:
                bad = _validate(rec["rows"], req, plan)
                if bad:
                    stop(f"語意不符 {req}：{bad}")
                run["ok"] += 1
                consec = 0
            else:
                run["fail"] += 1
                consec += 1
                print(f"FAIL {req['kind']} {req['hitter']} {req['year']} {req['team']}: {err}",
                      flush=True)
                if consec >= MAX_CONSEC_FAIL:
                    stop(f"連續 {consec} 次失敗（疑似節流）—冷卻 15–20 分後再單次續跑")
            if i % 20 == 0:
                print(f"[{i + 1}/{len(todo)}] POST={ledger['posts_sent']} GET={ledger['gets_sent']} "
                      f"ok={run['ok']} fail={run['fail']}", flush=True)
            time.sleep(DELAY_S)
    stop("completed")


# ---------------------------------------------------------------- build

COLUMNS = ("kind", "year", "hitter", "pitcher", "hitter_team", "pitcher_team", "pa",
           "split_unverified")


def cmd_build(wd: Path) -> None:
    """raw.jsonl → 資源檔。輸出只由 plan/ledger/raw 決定（不含建置時間），同輸入重跑位元組相同。"""
    plan = json.loads((wd / "plan.json").read_text())
    ledger = _load_ledger(wd)
    tkey = {(t["kind"], t["hitter"], t["pitcher"]): t for t in plan["targets"]}
    split = {(t["kind"], t["hitter"], t["pitcher"], y)
             for t in plan["targets"] for y in t["split_unverified_years"]}
    ok_req, fail_req = {}, {}
    for line in (wd / "raw.jsonl").read_text().splitlines():
        rec = json.loads(line)
        key = (rec["kind"], rec["hitter"], rec["year"], rec["team"])
        (ok_req if rec["ok"] else fail_req)[key] = rec
    fail_req = {k: v for k, v in fail_req.items() if k not in ok_req}
    rows = []
    for (k, h, y, _team), rec in sorted(ok_req.items()):
        for r in rec["rows"]:
            p = r.get("PitcherAcnt")
            pa = int(r.get("PlateAppearances") or 0)
            if (k, h, p) in tkey and pa > 0:
                rows.append((k, y, h, p, r["HitterTeamNo"], r["PitcherTeamNo"], pa,
                             (k, h, p, y) in split))
    rows.sort()
    if len({r[:6] for r in rows}) != len(rows):
        sys.exit("同一配對×年×兩隊出現重複列，拒絕輸出")
    planned = {(r["kind"], r["hitter"], r["year"], r["team"]): set(r["pitchers"])
               for r in plan["requests"]}
    # 目標配對中有規劃年度但該年度請求未成功者（缺列只會少算 → 判定端退為 partial/unknown）
    years_failed = sorted({(k, h, p, key[2]) for (k, h, p) in tkey
                           for key, ps in planned.items()
                           if key[:2] == (k, h) and p in ps and key not in ok_req})
    by_year = collections.defaultdict(lambda: [0, 0, 0])
    for key in planned:
        by_year[f"{key[2]}{key[0]}"][0 if key in ok_req else 1 if key in fail_req else 2] += 1
    manifest = {
        "issue": "#201",
        "source": "https://www.cpbl.com.tw POST /team/getfightingscore（fightingTeamNo=當年對手隊碼）",
        "population": "year=9999 A/C/E、官方PA>0 且 >2018起逐打席證據；對手投手 2024–2026 A/D 任何出賽",
        "semantics": "隊碼取自回傳列當年 HitterTeamNo/PitcherTeamNo；split_unverified=該年打者或投手"
                     "季表多隊，拆分語意未證實，不可宣稱完整歸屬",
        "plan_created_at": plan["created_at"],
        "collected_until": ledger["runs"][-1].get("ended") if ledger["runs"] else None,
        "targets": len(tkey),
        "targets_without_pre2018_years": sum(not t["years"] for t in tkey.values()),
        "target_years_failed": [list(x) for x in years_failed],
        "rows": len(rows),
        "rows_split_unverified": sum(r[7] for r in rows),
        "requests_planned": len(planned), "requests_ok": len(ok_req),
        "requests_failed": len(fail_req),
        "requests_not_attempted": len(planned) - len(ok_req) - len(fail_req),
        "http_posts_sent_t1": 4,
        "http_posts_sent_t2": ledger["posts_sent"], "http_gets_sent_t2": ledger["gets_sent"],
        "aborted_3rdparty": ledger["aborted_3rdparty"],
        "aborted_page_auto_post": ledger["aborted_page_post"],
        "runs": ledger["runs"],
        "by_year_kind_ok_fail_not_attempted": dict(sorted(by_year.items())),
    }

    # 一鍵一行／一列一行：可審、可 diff；載入端照常 json.load
    def dump(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    head = ",\n".join(f" {dump(k)}:{dump(v)}" for k, v in manifest.items())
    RESOURCE.write_text(
        "{\n" + f'"schema":{dump("cpbl.matchup_pre2018_rows.v1")},\n'
        + '"manifest":{\n' + head + "\n},\n"
        + f'"columns":{dump(COLUMNS)},\n'
        + '"rows":[\n' + ",\n".join(dump(r) for r in rows) + "\n]\n}\n")
    print(json.dumps({k: v for k, v in manifest.items()
                      if k not in ("runs", "by_year_kind_ok_fail_not_attempted")},
                     ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "collect", "build"])
    ap.add_argument("--workdir", default="/tmp/cpbl201-t2")
    ap.add_argument("--cap", type=int, default=POST_CAP_DEFAULT)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--kind")
    ap.add_argument("--hitter")
    ap.add_argument("--year", type=int)
    a = ap.parse_args()
    wd = Path(a.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    if a.cmd == "plan":
        cmd_plan(wd)
    elif a.cmd == "collect":
        cmd_collect(wd, a.cap, a.limit, a.kind, a.hitter, a.year)
    else:
        cmd_build(wd)


if __name__ == "__main__":
    main()
