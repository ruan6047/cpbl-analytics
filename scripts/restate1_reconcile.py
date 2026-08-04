"""INGEST-SPLITS-IMPORT-RESTATE1：分項重建的前後快照與變動歸因對帳。

為什麼要獨立腳本而不是臨時 SQL：卡面驗收要求「查核者獨立重現變動歸因對帳，不採信
執行者的宣稱數字」。把快照與 diff 寫成腳本，查核者可以拿受審 SHA 自己跑一次；臨時
SQL 只留在交付文件裡的話，重現成本高且無法確認跑的是同一套判準。

用法::

    uv run python scripts/restate1_reconcile.py precheck --report <f.json>
    uv run python scripts/restate1_reconcile.py snapshot --out <dir>/pre
    uv run python scripts/restate1_reconcile.py rebuild                     # 只跑 build_splits(2025)
    uv run python scripts/restate1_reconcile.py snapshot --out <dir>/post
    uv run python scripts/restate1_reconcile.py diff --pre <dir>/pre --post <dir>/post
    uv run python scripts/restate1_reconcile.py direction --pre <dir>/pre --post <dir>/post

`updated_at` 一律排除在比對之外——重建必然更新它，把它算進去會讓每一列都「變動」，
對帳就失去鑑別力（要看的是**數據格**有沒有變，不是有沒有被重寫）。

## 為什麼 `rebuild` 不呼叫 `cpbl-build-splits`（卡面紅線 5）

`run_build_splits.main()` 是 `build_splits(year)` 後面接 `build_career(year)`，而
`build_career` ＝ base ＋ **該 year**、且是 `DELETE year=9999` 後全量重插。base 是
「當前球季以前的歷史」，對 2025 執行等於把 2026 整季換成 2025——2026-08-03 rev1 實跑
造成 17,306 列生涯值被改寫。本卡要的只有 2025 的 `build_splits`，故直接呼叫該函式，
生涯連碰都不碰（`build_splits` 的寫入是 `WHERE year=%s AND kind_code=%s`，結構上只碰
指定年份）。

## 各表的預期變動母體不同（v1 的對帳把四張表都比對「打者母體」，會誤報）

GAP2 補的 bio 只有那 14 位洋投的 `bats`／`throws`，在 `splits_calc` 內只有兩條路徑吃它：

1. `calc_t2` 打者側 `if p_throws:` 閘門（`splits_calc.py:389`）——補值前整個打席落入
   `missing_pitcher_bio` 被丟棄，故**與這 14 人對戰過的打者**的家族 3 會淨增加。
2. `calc_t2` 投手側 `_batter_side(h_bats, p_thr)`——`p_thr` 只在打者是「左右開弓」時
   才影響結果（其餘情況站位由 `h_bats` 單獨決定）。實查 2025 A/D 對上這 14 人的
   左右開弓打者打席數＝0，故**投手側預期零變動**。

`*_vs_team` 兩張表出自 `calc_*_t1`（gamelog 場次級），完全不讀 bio → 預期零變動。
生涯（9999）不在 `build_splits` 的寫入範圍 → 預期零變動。
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

# 受影響的四張表與其主鍵。
TABLES: dict[str, list[str]] = {
    "batting_splits": ["year", "kind_code", "acnt", "item_group_code", "item_index", "item_name"],
    "pitching_splits": ["year", "kind_code", "acnt", "item_group_code", "item_index", "item_name"],
    "batting_vs_team": ["year", "kind_code", "acnt", "fight_team_code"],
    "pitching_vs_team": ["year", "kind_code", "acnt", "fight_team_code"],
}
_YEARS = (2025, 9999)
TARGET_YEAR = 2025
KINDS = ("A", "D")

# 卡面核准的 14 人（INGEST-PLAYER-BIO-GAP1 補 country、GAP2 補 bats／throws）。
GAP1_PITCHERS = [
    "0000004796", "0000006891", "0000007547", "0000007554", "0000007555",
    "0000007556", "0000007558", "0000007559", "0000007573", "0000007579",
    "0000007583", "0000007588", "0000007590", "0000007603",
]

# 家族 3 中受 `if p_throws:` 閘門控制的四個 item（打者側）。
GRP3_ITEMS = ["VS. 左投", "VS. 右投", "VS. 本土投手", "VS. 外籍投手"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── precheck：硬前置（GAP2）是否真的落地 ──────────────────────────────────────

def precheck(report: Path | None) -> None:
    from cpbl.db import conn

    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT id, name, bats, throws, country FROM cpbl.players "
            "WHERE id = ANY(%s) ORDER BY id", (GAP1_PITCHERS,))
        people = [dict(zip(("id", "name", "bats", "throws", "country"), r, strict=True))
                  for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM cpbl.players WHERE throws IS NULL")
        throws_null = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM cpbl.players WHERE bats IS NULL")
        bats_null = cur.fetchone()[0]
        cur.execute(
            "SELECT item_name, count(*), min(updated_at)::text, max(updated_at)::text "
            "FROM cpbl.batting_splits WHERE year = %s AND item_name = ANY(%s) "
            "GROUP BY item_name ORDER BY item_name", (TARGET_YEAR, GRP3_ITEMS))
        grp3 = [dict(zip(("item_name", "rows", "updated_at_min", "updated_at_max"), r,
                         strict=True)) for r in cur.fetchall()]
        # 投手側閘門的實際觸及量：對上這 14 人的「左右開弓」打者打席數（預期 0）
        cur.execute(
            "SELECT count(*) FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.players p ON p.id = COALESCE(pa.end_hitter_acnt, pa.hitter_acnt) "
            "WHERE pa.year = %s AND pa.kind_code = ANY(%s) "
            "  AND pa.end_pitcher_acnt = ANY(%s) AND p.bats = '左右開弓'",
            (TARGET_YEAR, list(KINDS), GAP1_PITCHERS))
        switch_pa = cur.fetchone()[0]

    filled = sum(1 for p in people if p["throws"])
    out = {
        "generated_at": _now(),
        "pitchers": people,
        "pitcher_count": len(people),
        "throws_filled": filled,
        "players_throws_null_total": throws_null,
        "players_bats_null_total": bats_null,
        "gate_ok": len(people) == len(GAP1_PITCHERS) == filled and throws_null == 0,
        "grp3_rows_before": grp3,
        "switch_hitter_pa_vs_gap1": switch_pa,
    }
    for p in people:
        print(f"  {p['id']} {p['name']}\tbats={p['bats']}\tthrows={p['throws']}\t{p['country']}")
    print(f"\n14 人 throws 非 NULL：{filled}/{len(people)}；全表 throws IS NULL = {throws_null}；"
          f"bats IS NULL = {bats_null}")
    print(f"硬前置閘門 {'✅ 通過' if out['gate_ok'] else '❌ 未通過'}")
    print(f"對上這 14 人的左右開弓打者打席數 = {switch_pa}（>0 才會動到投手側）")
    for g in grp3:
        print(f"  重建前 {g['item_name']}：{g['rows']} 列，updated_at {g['updated_at_max']}")
    _write(report, out)


# ── snapshot / rebuild ───────────────────────────────────────────────────────

def snapshot(out: Path) -> None:
    from cpbl.db import conn

    out.mkdir(parents=True, exist_ok=True)
    # _YEARS 是本檔常數（非外部輸入），故直接內插；表名同樣來自本檔白名單 TABLES。
    years = ", ".join(str(int(y)) for y in _YEARS)
    with conn() as c:
        for table in TABLES:
            df = pl.read_database(
                f"SELECT * FROM cpbl.{table} WHERE year IN ({years})", connection=c,
            ).drop("updated_at")
            df.write_parquet(out / f"{table}.parquet")
            print(f"  {table}: {df.height} 列 → {out / f'{table}.parquet'}")


def rebuild(report: Path | None) -> None:
    """只跑 `build_splits(2025)`；**不**接 `build_career`（見模組 docstring 與卡面紅線 5）。"""
    from cpbl.ingest.splits_calc import build_splits

    summary = build_splits(TARGET_YEAR, KINDS)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    _write(report, {"generated_at": _now(), "year": TARGET_YEAR, "kinds": list(KINDS),
                    "entrypoint": "cpbl.ingest.splits_calc.build_splits",
                    "career_touched": False, "summary": summary})


# ── diff：變動歸因 ────────────────────────────────────────────────────────────

def _changed(pre: pl.DataFrame, post: pl.DataFrame, pk: list[str]) -> tuple[dict, pl.DataFrame]:
    """回傳該表的變動摘要與「被觸及的 PK 列」。"""
    pre_k, post_k = pre.select(pk), post.select(pk)
    added = post_k.join(pre_k, on=pk, how="anti")
    removed = pre_k.join(post_k, on=pk, how="anti")
    common = pre.join(post, on=pk, how="inner", suffix="__post")
    value_cols = [c for c in pre.columns if c not in pk]
    if value_cols:
        diff_expr = pl.any_horizontal([
            (pl.col(c) != pl.col(f"{c}__post"))
            | (pl.col(c).is_null() != pl.col(f"{c}__post").is_null())
            for c in value_cols
        ])
        changed = common.filter(diff_expr).select(pk)
    else:
        changed = common.clear().select(pk)
    touched = pl.concat([added, removed, changed]).unique()
    return {
        "rows_pre": pre.height, "rows_post": post.height,
        "added": added.height, "removed": removed.height, "value_changed": changed.height,
        "touched_total": touched.height,
    }, touched


def _expected_batters() -> set[tuple[str, str]]:
    """(kind_code, hitter_acnt)：2025 A/D 曾與那 14 位洋投實際對戰過的打者。

    用 `game_livelog` 的原始對戰配對（＝`calc_t2` 自己的輸入），不用 canonical PA 表——
    這裡要的是**保證涵蓋**的母體（⊆ 檢定的上界），PA 表另作方向抽驗的獨立量級對照。
    """
    from cpbl.db import conn

    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT DISTINCT kind_code, hitter_acnt FROM cpbl.game_livelog "
            "WHERE year = %s AND kind_code = ANY(%s) AND pitcher_acnt = ANY(%s) "
            "  AND hitter_acnt IS NOT NULL",
            (TARGET_YEAR, list(KINDS), GAP1_PITCHERS))
        return {(r[0], r[1]) for r in cur.fetchall()}


def diff(pre_dir: Path, post_dir: Path, report: Path | None) -> None:
    expected = _expected_batters()
    print(f"預期變動母體（2025 A/D 對戰過那 14 位洋投的打者）：{len(expected)} 組 (kind, acnt)\n")

    tables_out: dict[str, dict] = {}
    verdict = {"unexpected_total": 0, "career_changed_total": 0, "zero_change_violations": []}
    for table, pk in TABLES.items():
        pre_all = pl.read_parquet(pre_dir / f"{table}.parquet")
        post_all = pl.read_parquet(post_dir / f"{table}.parquet")
        per_year: dict[str, dict] = {}
        for year in _YEARS:
            pre = pre_all.filter(pl.col("year") == year)
            post = post_all.filter(pl.col("year") == year)
            summary, touched = _changed(pre, post, pk)
            pairs = {(r["kind_code"], r["acnt"]) for r in touched.iter_rows(named=True)}
            summary["touched_acnt_count"] = len({a for _, a in pairs})
            # 只有 batting_splits 的目標年有非空預期母體；其餘一律預期零變動。
            expect_zero = not (table == "batting_splits" and year == TARGET_YEAR)
            summary["expect_zero_change"] = expect_zero
            if expect_zero:
                summary["unexpected_count"] = summary["touched_total"]
                summary["unexpected_acnts"] = sorted({a for _, a in pairs})[:20]
                if summary["touched_total"]:
                    verdict["zero_change_violations"].append(f"{table}@{year}")
            else:
                unexpected = sorted(pairs - expected)
                summary["unexpected_count"] = len(unexpected)
                summary["unexpected_acnts"] = [list(x) for x in unexpected[:20]]
                # 家族碼不變式：閘門只加家族 3，變動列若出現其他家族即為預期外
                groups = sorted({r["item_group_code"] for r in touched.iter_rows(named=True)})
                items = sorted({r["item_name"] for r in touched.iter_rows(named=True)})
                summary["touched_item_groups"] = groups
                summary["touched_item_names"] = items
                summary["item_group_invariant_ok"] = groups in ([], ["3"])
                summary["item_name_invariant_ok"] = set(items) <= set(GRP3_ITEMS)
            if year == 9999:
                verdict["career_changed_total"] += summary["touched_total"]
            verdict["unexpected_total"] += summary["unexpected_count"]
            per_year[str(year)] = summary
            tag = "預期零變動" if expect_zero else "預期有變動"
            flag = "✅" if not summary["unexpected_count"] else "⚠️ 預期外"
            print(f"{table}@{year}（{tag}）：前 {summary['rows_pre']} → 後 {summary['rows_post']}　"
                  f"新增 {summary['added']}／消失 {summary['removed']}／值變動 {summary['value_changed']}")
            print(f"  觸及 {summary['touched_total']} 列、{summary['touched_acnt_count']} 位 acnt；"
                  f"預期外 {summary['unexpected_count']} {flag}")
            if not expect_zero and summary["touched_total"]:
                print(f"  觸及家族 {summary['touched_item_groups']}　item {summary['touched_item_names']}")
        tables_out[table] = per_year

    verdict["ok"] = (verdict["unexpected_total"] == 0
                     and verdict["career_changed_total"] == 0
                     and not verdict["zero_change_violations"])
    print(f"\n生涯（9999）變動列數合計 = {verdict['career_changed_total']}")
    print(f"預期外變動合計 = {verdict['unexpected_total']}")
    print(f"對帳 {'✅ 全數通過' if verdict['ok'] else '❌ 有預期外變動'}")
    _write(report, {"generated_at": _now(), "expected_population": len(expected),
                    "tables": tables_out, "verdict": verdict})


# ── direction：方向與量級抽驗 ────────────────────────────────────────────────

def _pa_vs_gap1() -> dict[tuple[str, str], int]:
    """(kind_code, charged_hitter) → 對上那 14 人的打席數。

    來源是 canonical PA 表 `game_plate_appearances`（pa-build-1.3.0），與 `splits_calc`
    是兩套獨立的物化路徑 → 可作為分項增量的獨立量級對照。歸屬鍵依 9.15(b)＝
    `COALESCE(end_hitter_acnt, hitter_acnt)`，投手取末球錨定的 `end_pitcher_acnt`。

    ⚠️ 必須先用 `game_recap_builds.state='published'` 篩掉 superseded 版本：同一場會有
    多個 `build_id`（2025 A/D 有 359 場重建過），直接對整張表 count 會把同一個打席重複
    計 2–3 次（實測 13,717 列 vs 4,572 個真實打席）。另 `state='truncated'` 的殘段不是
    完成打席，一併排除。
    """
    from cpbl.db import conn

    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "WITH pub AS (SELECT build_id FROM cpbl.game_recap_builds "
            "             WHERE year = %s AND kind_code = ANY(%s) AND state = 'published') "
            "SELECT pa.kind_code, COALESCE(pa.end_hitter_acnt, pa.hitter_acnt) AS h, count(*) "
            "FROM cpbl.game_plate_appearances pa JOIN pub USING (build_id) "
            "WHERE pa.year = %s AND pa.kind_code = ANY(%s) AND pa.end_pitcher_acnt = ANY(%s) "
            "  AND pa.state = 'ready' "
            "GROUP BY 1, 2",
            (TARGET_YEAR, list(KINDS), TARGET_YEAR, list(KINDS), GAP1_PITCHERS))
        return {(r[0], r[1]): r[2] for r in cur.fetchall()}


def _ghost_islands() -> list[dict]:
    """對上那 14 人、被 `splits_calc` 幽靈島規則丟棄、但帶合法結果詞彙的打席島。

    幽靈島規則（`splits_calc.py:337`）丟棄「整島無任何投球列」的島，立意是濾掉換人公告
    列傳播出來的假島。但**手勢故意四壞零投球**同樣無投球列，是真打席卻一併被丟——這是
    `splits_calc` 的既有語意，與本次重述無關（對全體投手一致生效，不只這 14 人）。

    本函式把每個被丟的島拿去 canonical PA 表對照，區分「兩邊都不算（規則命中本意）」與
    「PA 表算、分項不算（規則過寬）」，供 `direction` 把量級殘差歸因到具體席次，而不是
    用人工聲明把差異帶過。切分邏輯與 `calc_t2` 同源（此處是為了定位殘差而重跑同一套判準，
    不是對它的獨立驗證）。
    """
    from cpbl.db import conn
    from cpbl.ingest.splits_calc import PA_OUTCOME
    from cpbl.ingest.splits_pa_merge import merge_plan

    gap1 = set(GAP1_PITCHERS)
    found: list[dict] = []
    for kind in KINDS:
        merges, merge_info = merge_plan(TARGET_YEAR, kind, PA_OUTCOME)
        with conn() as c:
            rows = c.execute(
                "SELECT game_sno, inning_seq, visiting_home_type, main_event_no, hitter_acnt, "
                "       pitcher_acnt, batting_action_name, is_strike, is_ball "
                "FROM cpbl.game_livelog WHERE year = %s AND kind_code = %s "
                "ORDER BY game_sno, inning_seq, visiting_home_type, main_event_no",
                (TARGET_YEAR, kind)).fetchall()

        def flush(island: list, info: dict | None, kind: str = kind) -> None:
            outcome = next((r[6] for r in reversed(island) if r[6]), None)
            if not outcome or PA_OUTCOME.get(outcome) is None:
                return
            if any(r[7] or r[8] for r in island):   # 有投球列 → 不是幽靈島
                return
            if island[0][5] not in gap1:
                return
            hitter = (info or {}).get("charged_hitter") or island[0][4]
            found.append({"kind_code": kind, "game_sno": island[0][0],
                          "start_event_no": island[0][3],
                          "island_end_event_no": island[-1][3], "hitter_acnt": hitter,
                          "pitcher_acnt": island[0][5], "outcome": outcome})

        cur_game, island, ikey, cur_info = None, [], None, None
        for r in rows:
            sno = r[0]
            if sno != cur_game:
                if island:
                    flush(island, cur_info)
                cur_game, island, ikey, cur_info = sno, [], None, None
            if not r[4]:
                continue
            key = (r[1], r[2], r[4])
            if key != ikey:
                if island and (sno, r[3]) in merges:
                    cur_info, ikey = merge_info[(sno, r[3])], key
                else:
                    if island:
                        flush(island, cur_info)
                    island, ikey, cur_info = [], key, None
            island.append(r)
        if island:
            flush(island, cur_info)

    # 逐島查 canonical PA 表怎麼處理同一段事件。分項真正少算的條件是**該打席整段都落在
    # 無投球的島內**（＝手勢故四那類零投球真打席）；若 PA 表的 end_event 越過島尾（代打
    # 誤切：公告列自成一島、實際打席在後半段有投球），分項會由後半島算到同一席，不算少算。
    with conn() as c:
        cur = c.cursor()
        for g in found:
            cur.execute(
                "WITH pub AS (SELECT build_id FROM cpbl.game_recap_builds "
                "             WHERE year = %s AND kind_code = %s AND state = 'published') "
                "SELECT pa.state, pa.result_action, pa.end_event_no, "
                "       COALESCE(pa.end_hitter_acnt, pa.hitter_acnt) "
                "FROM cpbl.game_plate_appearances pa JOIN pub USING (build_id) "
                "WHERE pa.year = %s AND pa.kind_code = %s AND pa.game_sno = %s "
                "  AND pa.start_event_no = %s",
                (TARGET_YEAR, g["kind_code"], TARGET_YEAR, g["kind_code"],
                 g["game_sno"], g["start_event_no"]))
            r = cur.fetchone()
            g["pa_table_state"] = r[0] if r else None
            g["pa_table_action"] = r[1] if r else None
            g["pa_table_end_event_no"] = r[2] if r else None
            g["pa_table_hitter_acnt"] = r[3] if r else None
            g["splits_lost_pa"] = bool(
                r and r[0] == "ready" and r[2] <= g["island_end_event_no"])
    return found


def _grp3(df: pl.DataFrame) -> pl.DataFrame:
    return (df.filter((pl.col("year") == TARGET_YEAR) & (pl.col("item_group_code") == "3")
                      & pl.col("item_name").is_in(GRP3_ITEMS))
              .select("kind_code", "acnt", "item_name", "plate_appearances"))


def direction(pre_dir: Path, post_dir: Path, report: Path | None, top: int) -> None:
    pre = _grp3(pl.read_parquet(pre_dir / "batting_splits.parquet"))
    post = _grp3(pl.read_parquet(post_dir / "batting_splits.parquet"))
    key = ["kind_code", "acnt", "item_name"]
    j = (pre.join(post, on=key, how="full", suffix="_post", coalesce=True)
           .with_columns(pl.col("plate_appearances").fill_null(0).alias("pa_pre"),
                         pl.col("plate_appearances_post").fill_null(0).alias("pa_post"))
           .with_columns((pl.col("pa_post") - pl.col("pa_pre")).alias("delta")))
    wide = j.pivot(on="item_name", index=["kind_code", "acnt"], values="delta",
                   aggregate_function="sum").fill_null(0)
    for it in GRP3_ITEMS:
        if it not in wide.columns:
            wide = wide.with_columns(pl.lit(0).alias(it))
    pa_map = _pa_vs_gap1()
    ghosts = _ghost_islands()
    # 幽靈島規則丟掉、但 canonical PA 表收錄的席次：分項理應少算這些，逐打者扣除後才可比
    ghost_adj: dict[tuple[str, str], int] = {}
    for g in ghosts:
        if g["splits_lost_pa"]:
            k = (g["kind_code"], g["hitter_acnt"])
            ghost_adj[k] = ghost_adj.get(k, 0) + 1
    wide = (wide.with_columns(
                pl.struct("kind_code", "acnt").map_elements(
                    lambda s: pa_map.get((s["kind_code"], s["acnt"]), 0),
                    return_dtype=pl.Int64).alias("pa_vs_gap1"),
                pl.struct("kind_code", "acnt").map_elements(
                    lambda s: ghost_adj.get((s["kind_code"], s["acnt"]), 0),
                    return_dtype=pl.Int64).alias("ghost_drop"))
                .with_columns((pl.col("VS. 外籍投手") - pl.col("pa_vs_gap1")
                               + pl.col("ghost_drop")).alias("import_gap"),
                              (pl.col("VS. 左投") + pl.col("VS. 右投")
                               - pl.col("VS. 外籍投手")).alias("hand_gap")))
    changed = wide.filter(pl.any_horizontal([pl.col(c) != 0 for c in GRP3_ITEMS]))
    checks = {
        "batters_changed": changed.height,
        "local_side_delta_total": int(changed["VS. 本土投手"].sum()),
        "import_side_delta_total": int(changed["VS. 外籍投手"].sum()),
        "hand_side_delta_total": int(changed["VS. 左投"].sum() + changed["VS. 右投"].sum()),
        "pa_vs_gap1_total": int(changed["pa_vs_gap1"].sum()),
        "pa_vs_gap1_total_all": int(sum(pa_map.values())),
        "ghost_islands_vs_gap1": len(ghosts),
        "ghost_islands_causing_loss": sum(ghost_adj.values()),
        # 本土側不得有任何變動（原本就沒算進去，不是搬移）
        "local_side_any_change": int((changed["VS. 本土投手"] != 0).sum()),
        # 外籍側不得減少
        "import_side_negative_rows": int((changed["VS. 外籍投手"] < 0).sum()),
        # 外籍增量必須等於左投＋右投增量（同一個閘門放行的同一批打席）
        "hand_gap_nonzero_rows": int((changed["hand_gap"] != 0).sum()),
        # 外籍增量＋幽靈島扣除 必須等於獨立 PA 表對上這 14 人的打席數
        "import_gap_nonzero_rows": int((changed["import_gap"] != 0).sum()),
    }
    checks["ok"] = (checks["local_side_any_change"] == 0
                    and checks["import_side_negative_rows"] == 0
                    and checks["hand_gap_nonzero_rows"] == 0
                    and checks["import_gap_nonzero_rows"] == 0)
    sample = (changed.sort("VS. 外籍投手", descending=True).head(top)
                     .select("kind_code", "acnt", *GRP3_ITEMS, "pa_vs_gap1",
                             "ghost_drop", "import_gap", "hand_gap"))
    print(f"變動打者數：{checks['batters_changed']}")
    print(f"VS. 外籍投手 淨增打席合計 = {checks['import_side_delta_total']}　"
          f"（獨立 PA 表 {checks['pa_vs_gap1_total_all']} − 幽靈島丟棄 "
          f"{checks['ghost_islands_causing_loss']}）")
    print(f"VS. 本土投手 變動合計 = {checks['local_side_delta_total']}"
          f"（非零列數 {checks['local_side_any_change']}）")
    print(f"VS. 左投＋右投 淨增合計 = {checks['hand_side_delta_total']}")
    print(f"對上這 14 人的幽靈島 {checks['ghost_islands_vs_gap1']} 席，"
          f"其中 PA 表收錄 {checks['ghost_islands_causing_loss']} 席：")
    for g in ghosts:
        mark = ("PA 表收錄且整段無投球 → 分項少算" if g["splits_lost_pa"]
                else f"不構成少算（PA 表 state={g['pa_table_state']}、"
                     f"end_event={g['pa_table_end_event_no']}）")
        print(f"  {g['kind_code']} 第{g['game_sno']}場 event {g['start_event_no']} "
              f"打者{g['hitter_acnt']} 投手{g['pitcher_acnt']} 「{g['outcome']}」 → {mark}")
    print(f"逐打者不符列數：外籍 vs PA 表 {checks['import_gap_nonzero_rows']}、"
          f"左右投 vs 外籍 {checks['hand_gap_nonzero_rows']}")
    print(f"方向抽驗 {'✅ 全數通過' if checks['ok'] else '❌ 有不符'}\n")
    with pl.Config(tbl_rows=top + 5, tbl_cols=12, tbl_width_chars=220):
        print(sample)
    _write(report, {"generated_at": _now(), "checks": checks,
                    "ghost_islands": ghosts,
                    "sample_top": sample.to_dicts(),
                    "mismatch_rows": changed.filter(
                        (pl.col("import_gap") != 0) | (pl.col("hand_gap") != 0)
                        | (pl.col("VS. 本土投手") != 0)).to_dicts()})


def _write(report: Path | None, payload: dict) -> None:
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        print(f"\n報告 → {report}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("precheck"); p.add_argument("--report", type=Path)
    s = sub.add_parser("snapshot"); s.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("rebuild"); r.add_argument("--report", type=Path)
    for name in ("diff", "direction"):
        x = sub.add_parser(name)
        x.add_argument("--pre", type=Path, required=True)
        x.add_argument("--post", type=Path, required=True)
        x.add_argument("--report", type=Path)
        if name == "direction":
            x.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    if args.cmd == "precheck":
        precheck(args.report)
    elif args.cmd == "snapshot":
        snapshot(args.out)
    elif args.cmd == "rebuild":
        rebuild(args.report)
    elif args.cmd == "diff":
        diff(args.pre, args.post, args.report)
    else:
        direction(args.pre, args.post, args.report, args.top)


if __name__ == "__main__":
    main()
