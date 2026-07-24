"""INGEST-GAME-TM-REFACTOR1 Gate 2：單場 API vs 逐投手 logs 逐列等價對帳（唯讀，不寫 DB）。

對至少 N 場已完成賽，分別以兩條 fetch path 解析逐球 TrackMan，於隔離記憶體 artifact 比對：
- row count（每場、總計）
- PK 集合 (year,kind,game,pitcher,pitch_cnt) 差異（only_new / only_old）
- 共同 PK 上每一入庫欄位值是否逐格一致
並量化 API 請求次數降幅（單場路徑=場數；logs 路徑=需覆蓋這些場的投手數）。

兩路皆餵同一 pure parser（parse_pitches），故欄位若不一致＝兩官方端點 payload 本身有差，
是真發現而非解析歧異。全程只讀官方 API 與本機 games 表選場，不觸碰 pitch_tracking writer。

    uv run python scripts/reconcile_game_tm.py                 # 本季 A，最近 30 場有設備場
    uv run python scripts/reconcile_game_tm.py --year 2026 --kind A --games 35 --delay 0.4
    uv run python scripts/reconcile_game_tm.py --sno 99 100 101 ...   # 指定場次
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict

from cpbl.db import conn
from cpbl.ingest.cpbl_pitch_tracking import (
    _COLS,
    _client,
    _fetch_game_livelog,
    _fetch_logs,
    _record,
    parse_pitches,
)

_COL_NAMES = [c.strip() for c in _COLS.split(",")]
_PK_IDX = (0, 1, 2, 3, 4)  # year,kind_code,game_sno,pitcher_acnt,pitch_cnt


def _pk(rec: tuple) -> tuple:
    return tuple(rec[i] for i in _PK_IDX)


def _pick_games(year: int, kind: str, n: int) -> list[int]:
    """選最近 n 場「有 pitch_tracking 覆蓋（＝有設備）」的已完成場，讓兩路都有可比資料。"""
    with conn() as c:
        rows = c.execute(
            """
            SELECT g.game_sno
            FROM cpbl.games g
            WHERE g.year=%s AND g.kind_code=%s AND g.home_score+g.away_score>0
              AND g.game_date <= CURRENT_DATE
              AND EXISTS (SELECT 1 FROM cpbl.pitch_tracking pt
                          WHERE pt.year=g.year AND pt.kind_code=g.kind_code AND pt.game_sno=g.game_sno)
            ORDER BY g.game_date DESC, g.game_sno DESC
            LIMIT %s
            """,
            (year, kind, n),
        ).fetchall()
    return sorted(r[0] for r in rows)


def _gamelog_pitchers(year: int, kind: str, snos: list[int]) -> dict[int, set[str]]:
    """各場 pitching_gamelog 記錄的投手集合（用來對照 logs 路徑「靠名冊」的漏損風險）。"""
    out: dict[int, set[str]] = defaultdict(set)
    with conn() as c:
        for sno, acnt in c.execute(
            "SELECT game_sno, pitcher_acnt FROM cpbl.pitching_gamelog "
            "WHERE year=%s AND kind_code=%s AND game_sno=ANY(%s)",
            (year, kind, snos),
        ).fetchall():
            out[sno].add(acnt)
    return out


def _fmt_delta(col: str, a, b) -> str:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return f"{col}: new={a} old={b} Δ={abs(a - b):.6g}"
    return f"{col}: new={a!r} old={b!r}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--kind", default="A")
    ap.add_argument("--games", type=int, default=30)
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--sno", type=int, nargs="*")
    ap.add_argument("--out", default=None, help="寫 JSON 報告路徑")
    args = ap.parse_args()

    snos = sorted(args.sno) if args.sno else _pick_games(args.year, args.kind, args.games)
    if len(snos) < 30 and not args.sno:
        print(f"⚠️ 只選到 {len(snos)} 場有設備覆蓋場（<30）；仍繼續但樣本不足門檻。")
    print(f"對帳 {len(snos)} 場：{args.year}-{args.kind} snos={snos}")

    client = _client()
    req_new = 0
    req_old = 0

    # === NEW：單場 API，一場一請求 ===
    new_by_game: dict[int, dict[tuple, tuple]] = {}
    livelog_pitchers: dict[int, set[str]] = {}
    for sno in snos:
        time.sleep(args.delay)
        livelog = _fetch_game_livelog(client, args.year, args.kind, sno)
        req_new += 1
        recs = parse_pitches(livelog, args.kind)
        new_by_game[sno] = {_pk(r): r for r in recs}
        livelog_pitchers[sno] = {r[3] for r in recs}

    # === OLD：逐投手 logs（投手集合＝各場 livelog 出現投手 ∪ pitching_gamelog 名冊，全域去重
    # 一次抓）。取聯集而非只靠 livelog，才能偵測「game API 缺、logs 有」的 only_old PK。===
    gl_pitchers = _gamelog_pitchers(args.year, args.kind, snos)
    all_pitchers = sorted({a for s in snos for a in livelog_pitchers[s]}
                          | {a for s in snos for a in gl_pitchers.get(s, set())})
    logs_recs_by_pk: dict[tuple, tuple] = {}
    for acnt in all_pitchers:
        time.sleep(args.delay)
        logs = _fetch_logs(client, acnt, args.year, args.kind)
        req_old += 1
        for p in logs:
            rec = _record(p, args.kind)
            if rec is not None:
                logs_recs_by_pk[_pk(rec)] = rec
    client.close()

    target = set(snos)
    old_by_game: dict[int, dict[tuple, tuple]] = defaultdict(dict)
    for pk, rec in logs_recs_by_pk.items():
        if pk[2] in target:
            old_by_game[pk[2]][pk] = rec

    # === 比對 ===
    per_game = []
    tot_new = tot_old = tot_common = tot_cell_mismatch = 0
    all_only_new: list[tuple] = []
    all_only_old: list[tuple] = []
    field_mismatch_cols: dict[str, int] = defaultdict(int)
    mismatch_samples: list[str] = []
    roster_gap: dict[int, list[str]] = {}

    for sno in snos:
        nnew = new_by_game.get(sno, {})
        nold = old_by_game.get(sno, {})
        only_new = set(nnew) - set(nold)
        only_old = set(nold) - set(nnew)
        common = set(nnew) & set(nold)
        cell_mismatch = 0
        for pk in common:
            for i, (a, b) in enumerate(zip(nnew[pk], nold[pk], strict=True)):
                if a != b:
                    cell_mismatch += 1
                    field_mismatch_cols[_COL_NAMES[i]] += 1
                    if len(mismatch_samples) < 20:
                        mismatch_samples.append(f"{sno} {pk[3]}#{pk[4]} {_fmt_delta(_COL_NAMES[i], a, b)}")
        tot_new += len(nnew)
        tot_old += len(nold)
        tot_common += len(common)
        tot_cell_mismatch += cell_mismatch
        all_only_new += [(sno, *pk) for pk in only_new]
        all_only_old += [(sno, *pk) for pk in only_old]
        # 漏損風險：livelog 有 Trackman 的投手但 pitching_gamelog 名冊缺
        gap = sorted(livelog_pitchers[sno] - gl_pitchers.get(sno, set()))
        if gap:
            roster_gap[sno] = gap
        per_game.append({
            "sno": sno, "new_rows": len(nnew), "old_rows": len(nold),
            "only_new": len(only_new), "only_old": len(only_old),
            "common": len(common), "cell_mismatch": cell_mismatch,
        })

    # 請求量兩種框架：
    # (a) global-dedup：本 harness 實際抓法（整段窗口把同一投手只抓一次）＝節省下界。
    # (b) per-game/日 refresh 模型（生產真實）：每個比賽日對當日出賽投手各抓一次 logs，
    #     同一投手在不同出賽日會重抓，故 OLD = 各場出賽投手數合計（≈每日投手請求合計）。
    #     這才是「單場一請求」相對現行每日 refresh 的真實降幅。
    req_old_per_game = sum(len(gl_pitchers.get(s, set())) for s in snos)
    reduction_global = (1 - req_new / req_old) if req_old else 0.0
    reduction_per_game = (1 - req_new / req_old_per_game) if req_old_per_game else 0.0
    report = {
        "params": {"year": args.year, "kind": args.kind, "games": len(snos)},
        "requests": {
            "new_game_api": req_new,
            "old_logs_global_dedup": req_old,
            "old_logs_per_game_model": req_old_per_game,
            "reduction_pct_per_game_model": round(reduction_per_game * 100, 1),
            "reduction_pct_global_dedup": round(reduction_global * 100, 1),
        },
        "totals": {"new_rows": tot_new, "old_rows": tot_old, "common_pk": tot_common,
                   "only_new_pk": len(all_only_new), "only_old_pk": len(all_only_old),
                   "cell_mismatches": tot_cell_mismatch},
        "field_mismatch_cols": dict(field_mismatch_cols),
        "roster_gap_pitchers": roster_gap,
        "per_game": per_game,
    }

    print("\n================ 對帳結果 ================")
    print(f"請求次數：單場 API={req_new}  逐投手 logs（每日 refresh 模型）={req_old_per_game}"
          f"  → 降幅 {report['requests']['reduction_pct_per_game_model']}%"
          f"（global-dedup 下界 {report['requests']['reduction_pct_global_dedup']}%，實抓 {req_old} 次）")
    print(f"總列數：new={tot_new}  old={tot_old}  共同PK={tot_common}")
    print(f"PK 差異：only_new={len(all_only_new)}  only_old={len(all_only_old)}")
    print(f"欄位逐格不一致數：{tot_cell_mismatch}")
    if field_mismatch_cols:
        print("  不一致欄位分布：", dict(field_mismatch_cols))
    for s in mismatch_samples:
        print("   ·", s)
    if all_only_new[:10]:
        print("  only_new 樣本：", all_only_new[:10])
    if all_only_old[:10]:
        print("  only_old 樣本：", all_only_old[:10])
    if roster_gap:
        n_gap = sum(len(v) for v in roster_gap.values())
        print(f"名冊漏損風險：{len(roster_gap)} 場、共 {n_gap} 位投手在 livelog 有 Trackman 但 pitching_gamelog 名冊缺")
        for sno, gap in list(roster_gap.items())[:10]:
            print(f"   · {sno}: {gap}")
    verdict = "PASS" if (len(all_only_new) == 0 and len(all_only_old) == 0
                         and tot_cell_mismatch == 0 and len(snos) >= 30) else "REVIEW"
    print(f"\n判定：{verdict}（PK 集合與逐格欄位一致、樣本≥30 才 PASS）")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print(f"報告已寫入 {args.out}")


if __name__ == "__main__":
    main()
