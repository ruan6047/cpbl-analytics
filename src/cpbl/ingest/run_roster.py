"""cpbl-roster：季後賽官方 32 人資格名單的本機 CLI（#284 S03；唯一會員 writer）。

流程：需求方整理的 PRD 格式全文 → preview（解析＋身分＋規則檢查，唯讀）
      → 人工核對 32 人身份與官方來源 → submit --confirm-hash <preview 的 membership_hash>。

用法：
  cpbl-roster preview roster.txt [--json] [--out draft.json]      # 唯讀；也可用 - 讀 stdin
  cpbl-roster submit roster.txt --confirm-hash <64 hex> [--observed-at ISO8601]
  cpbl-roster annotate roster.txt                                 # 只改戰術角色，另存新版
  cpbl-roster show --year 2026 --series C --team ACN011 [--annotation-version N] [--json]
  cpbl-roster import-official-population --year 2026 --series E --team ACN011 [--confirm-hash H]

DB：寫入 DATABASE_URL 指向的庫（預設本機共享 cpbl）。寫共享庫前須取得資源租用；
    ⛔ 正式站不建提交端點，生產只經 `ROSTER_ONLY=1` 同步（scripts/refresh-cpbl-prod.sh）。

不變量：每隊每系列一份、提交後不可變；同內容重送冪等回原 roster_id；不同內容拒絕並列差異；
        未滿／超過 32、重複、身份未解決、守位衝突、已核洋將 > 3 一律不能提交；
        身分未知（players.country 缺）不猜，只標「外籍資格檢查不完整」。
        資格名單 ⛔ 不代表先發、當場 28 人登錄或可用。
        參賽隊只驗 team_dim 存在，系列參賽資格需人工確認（S02 契約未核定）。

退出碼：
  0 成功（preview＝可提交；submit＝created／idempotent；annotate＝revised／unchanged）
  2 參數錯 · 10 語法錯（附行號與原文片段） · 11 身分未解析（草稿，列候選）
  12 規則違反 · 13 同隊同系列已有不同內容（拒絕＋差異） · 14 --confirm-hash 不符
  15 annotate 前提不符（無名單／會員或來源不同）或角色版本不存在 · 16 角色修訂競爭，請重跑
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from cpbl import db
from cpbl.ingest._cli import cli_parser
from cpbl.reports.official_population import load as load_official_population
from cpbl.rosters.identity import PARTICIPANT_NOTE, STATUS_LABEL
from cpbl.rosters.parser import ParseError, parse, render
from cpbl.rosters.role_store import annotate_package, preview_package
from cpbl.rosters.store import (
    ELIGIBILITY_NOTE,
    EXIT_CONFLICT,
    EXIT_DRAFT,
    EXIT_SYNTAX,
    EXIT_VIOLATION,
    Origin,
    RosterError,
    annotate,
    pasted_origin,
    prepare,
    read_roster,
    submit,
)

PROG = "cpbl-roster"


def _parser():
    p = cli_parser(PROG, __doc__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{preview,submit,annotate,show,import-official-population}")

    def text_cmd(name: str, helptext: str):
        sp = sub.add_parser(name, help=helptext, allow_abbrev=False)
        sp.add_argument("file", help="PRD 格式名單全文檔案；- 讀 stdin")
        sp.add_argument("--json", action="store_true", help="輸出 JSON")
        return sp

    pv = text_cmd("preview", "解析＋身分＋規則檢查（唯讀）")
    pv.add_argument("--format", choices=("text-v1", "roles-v2"), default="text-v1")
    pv.add_argument("--out", help="把預覽（含草稿候選）另存成 JSON 檔")
    sm = text_cmd("submit", "原子提交（需 preview 的 membership_hash）")
    sm.add_argument("--confirm-hash", required=True, help="preview 印出的 membership_hash")
    sm.add_argument("--observed-at", type=datetime.fromisoformat,
                    help="取得官方文字的時間（ISO8601，含時區；預設＝執行時間）")
    an = text_cmd("annotate", "戰術角色修訂（另存新版，不改會員）")
    an.add_argument("--format", choices=("text-v1", "roles-v2"), default="text-v1")
    an.add_argument("--confirm-approval-hash", help="roles-v2核准表SHA-256；寫入時必要")
    an.add_argument("--restore-version", action="append", default=[], metavar="ROSTER_ID:N",
                    help="roles-v2兩隊完整基準還原；每隊各給一次，不刪既有歷史")

    sh = sub.add_parser("show", help="唯讀摘要", allow_abbrev=False)
    for sp in (sh,):
        sp.add_argument("--year", type=int, required=True)
        sp.add_argument("--series", choices=("E", "C"), required=True)
        sp.add_argument("--team", required=True)
    sh.add_argument("--annotation-version", type=int)
    sh.add_argument("--json", action="store_true")

    ip = sub.add_parser("import-official-population",
                        help="把 official_population 已核 E 名單渲染成 PRD 格式走同一管線",
                        allow_abbrev=False)
    ip.add_argument("--year", type=int, required=True)
    ip.add_argument("--series", choices=("E", "C"), required=True)
    ip.add_argument("--team", required=True)
    ip.add_argument("--confirm-hash", help="不給＝只預覽；給＝提交")
    ip.add_argument("--json", action="store_true")
    return p


def _read(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def _emit(doc: dict, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(doc, ensure_ascii=False, indent=2, default=str))
    else:
        print(text)


def _preview_doc(prep, h, verdict) -> dict:
    p = prep.parsed
    return {
        "status": prep.status,
        "year": p.year, "series": p.kind_code, "team": p.team_code,
        "source_url": p.source_url, "published_date": p.published_date.isoformat(),
        "team_check": {"team_dim": prep.team_known, "participant": PARTICIPANT_NOTE},
        "count": len(prep.rows),
        "rows": [
            {"line": r.entry.line, "position": r.entry.position, "announced_name": r.entry.name,
             "player_id": r.player_id, "master_name": r.master_name,
             "evidence": list(r.evidence), "import_status": r.import_status,
             "role": r.role, "problem": r.problem, "candidates": list(r.candidates)}
            for r in prep.rows
        ],
        "violations": prep.violations,
        "import_check": prep.import_check,
        "hashes": h,
        "existing": verdict,
        "note": ELIGIBILITY_NOTE,
    }


def _preview_text(doc: dict) -> str:
    out = [f"== {doc['year']} {doc['series']} {doc['team']}｜{doc['source_url']}｜公告 {doc['published_date']}",
           f"參賽隊：team_dim {'存在' if doc['team_check']['team_dim'] else '不存在'}；{doc['team_check']['participant']}",
           f"人數：{doc['count']}"]
    for r in doc["rows"]:
        status = STATUS_LABEL.get(r["import_status"], "—")
        ev = ",".join(r["evidence"]) or "—"
        out.append(f"  L{r['line']:<3} {r['position']:<3} {r['announced_name']:<6} "
                   f"{r['player_id'] or '??????????'} 主檔={r['master_name'] or '—'} "
                   f"佐證={ev} 外籍={status} 角色={r['role']}")
        if r["problem"]:
            out.append(f"       ⚠ {r['problem']}")
            for cand in r["candidates"]:
                out.append(f"         候選 {cand['player_id']} 主檔={cand['master_name']} "
                           f"佐證={','.join(cand['team_year_evidence'])}")
    ic = doc["import_check"]
    out.append(f"已核洋將 {len(ic['verified_imports'])}／上限 {ic['limit']}："
               + ("、".join(f"{v['name']}({v['player_id']},{v['country']})" for v in ic["verified_imports"]) or "無"))
    if not ic["complete"]:
        out.append(f"⚠ 外籍資格檢查不完整（{len(ic['unknown'])} 人身分未知）：⛔ 不宣稱完整資格審查")
    for v in doc["violations"]:
        out.append(f"✗ {v}")
    if doc["hashes"]:
        out.append(f"membership_hash {doc['hashes']['membership_hash']}")
        out.append(f"source_hash     {doc['hashes']['source_hash']}")
    ex = doc["existing"]
    if ex:
        if ex["status"] == "idempotent":
            out.append(f"已提交（{ex['roster_id']}，{ex['submitted_at']}）：同內容重送將冪等返回原 roster_id")
        else:
            out.append(f"已提交不同內容（{ex['roster_id']}）：提交將被拒絕；差異 "
                       + json.dumps(ex["diff"], ensure_ascii=False))
    out.append({"ready": "→ 可提交：人工核對後 submit --confirm-hash <membership_hash>",
                "draft": "→ 草稿：身分未解析，補 @id= 或先補主檔身份後重跑（不寫 DB）",
                "violation": "→ 規則違反：不能提交（不寫 DB）"}[doc["status"]])
    out.append(doc["note"])
    return "\n".join(out)


def _preview_exit(doc: dict) -> int:
    if doc["status"] == "draft":
        return EXIT_DRAFT
    if doc["status"] == "violation":
        return EXIT_VIOLATION
    if doc["existing"] and doc["existing"]["status"] == "conflict":
        return EXIT_CONFLICT
    return 0


def _do_preview(text: str, as_json: bool, out_path: str | None = None) -> int:
    parsed = parse(text)
    with db.conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        prep, h, verdict = prepare(c, parsed)
    doc = _preview_doc(prep, h, verdict)
    if out_path:
        Path(out_path).write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str),
                                  encoding="utf-8")
    _emit(doc, as_json, _preview_text(doc))
    return _preview_exit(doc)


def _do_submit(text: str, confirm: str, origin: Origin, as_json: bool) -> int:
    parsed = parse(text)
    with db.conn() as c:
        result = submit(c, parsed, confirm, origin)
    lines = [f"{result['status']}: roster_id={result['roster_id']} submitted_at={result['submitted_at']}",
             f"membership_hash {result['membership_hash']}", f"source_hash     {result['source_hash']}"]
    if "notice" in result:
        lines.append(f"⚠ {result['notice']}")
    _emit(result, as_json, "\n".join(lines))
    return 0


def _show_text(r: dict) -> str:
    h = r["head"]
    out = [f"== {h['year']} {h['kind_code']} {h['team_code']} roster_id={h['roster_id']}",
           f"來源 {h['source_url']}｜公告 {h['published_date']}（{h['published_precision']}）"
           f"｜observed_at {h['observed_at']}（{h['observation_basis']}）｜input_origin {h['input_origin']}",
           f"submitted_at {h['submitted_at']}｜membership_hash {h['membership_hash']}",
           f"source_hash {h['source_hash']}｜角色版本 {r['annotation_version']}（現有 {r['annotation_versions']}）"]
    for m in r["members"]:
        a = "無" if m["a_games"] is None else str(m["a_games"])
        out.append(f"  {m['official_position']:<3} {m['announced_name']:<6} {m['player_id']} "
                   f"角色={'、'.join(m['tactical_roles']) or 'unclassified'} 本季A出賽={a}")
    ic = h["import_check"]
    out.append(f"已核洋將 {len(ic['verified_imports'])}／上限 {ic['limit']}"
               + ("" if ic["complete"] else f"；⚠ 外籍資格檢查不完整（{len(ic['unknown'])} 人身分未知）"))
    out.append(r["note"])
    return "\n".join(out)


def _official_text(year: int, series: str, team: str) -> tuple[str, Origin]:
    recs = [r for r in load_official_population(year, series) if r["team_code"] == team]
    if len(recs) != 1:
        raise RosterError(EXIT_SYNTAX, f"official_population 無 {year}/{series}/{team} 已核記錄")
    rec = recs[0]
    text = render(year, series, team, rec["source_url"], rec["published_date"],
                  [(m["official_role"], m["name"], m["player_id"]) for m in rec["members"]])
    origin = Origin(
        "official_population_v1",
        datetime.fromisoformat(rec["observed_at"].replace("Z", "+00:00")),
        rec["observation_basis"],
        datetime.fromisoformat(rec["identity_verified_at"]),
    )
    return text, origin


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd in ("preview", "annotate") and args.format == "roles-v2":
            doc = json.loads(_read(args.file))
            with db.conn() as c:
                if args.cmd == "preview":
                    c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    result = preview_package(c, doc)
                else:
                    restore = None
                    if args.restore_version:
                        restore = {}
                        for item in args.restore_version:
                            rid, version = item.rsplit(":", 1)
                            if rid in restore:
                                raise ValueError("restore不得重複同一roster_id")
                            restore[rid] = int(version)
                    result = annotate_package(c, doc, args.confirm_approval_hash, restore)
            if args.cmd == "preview" and args.out:
                Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            _emit(result, args.json, json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "annotate" and (args.confirm_approval_hash or args.restore_version):
            raise ValueError("核准hash／restore旗標只接受roles-v2格式")
        if args.cmd == "preview":
            return _do_preview(_read(args.file), args.json, args.out)
        if args.cmd == "submit":
            return _do_submit(_read(args.file), args.confirm_hash, pasted_origin(args.observed_at),
                              args.json)
        if args.cmd == "annotate":
            with db.conn() as c:
                result = annotate(c, parse(_read(args.file)))
            _emit(result, args.json, json.dumps(result, ensure_ascii=False))
            return 0
        if args.cmd == "show":
            with db.conn() as c:
                c.execute("SET TRANSACTION READ ONLY")
                with c.cursor() as cur:
                    r = read_roster(cur, args.year, args.series, args.team, args.annotation_version)
            if r is None:
                print(f"{args.year} {args.series} {args.team}：尚無已提交名單（missing）")
                return 0
            _emit(r, args.json, _show_text(r))
            return 0
        if args.cmd == "import-official-population":
            text, origin = _official_text(args.year, args.series, args.team)
            if args.confirm_hash is None:
                return _do_preview(text, args.json)
            return _do_submit(text, args.confirm_hash, origin, args.json)
    except ParseError as exc:
        print("✗ 解析錯誤（不寫 DB）：", file=sys.stderr)
        for issue in exc.issues:
            print(f"  {issue}", file=sys.stderr)
        return EXIT_SYNTAX
    except RosterError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        if exc.detail:
            print(json.dumps(exc.detail, ensure_ascii=False, indent=2, default=str), file=sys.stderr)
        return exc.code
    except ValueError as exc:
        print(f"✗ 角色輸入格式錯誤（不寫 DB）：{exc}", file=sys.stderr)
        return EXIT_SYNTAX
    raise AssertionError(args.cmd)


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
