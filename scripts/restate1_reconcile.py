"""INGEST-SPLITS-IMPORT-RESTATE1：分項重建的前後快照與變動歸因對帳。

為什麼要獨立腳本而不是臨時 SQL：卡面驗收要求「查核者獨立重現變動歸因對帳，不採信
執行者的宣稱數字」。把快照與 diff 寫成腳本，查核者可以拿受審 SHA 自己跑一次；臨時
SQL 只留在交付文件裡的話，重現成本高且無法確認跑的是同一套判準。

用法::

    uv run python scripts/restate1_reconcile.py snapshot --out <dir>/pre     # 重建前
    uv run cpbl-build-splits 2025                                            # 重建
    uv run python scripts/restate1_reconcile.py snapshot --out <dir>/post    # 重建後
    uv run python scripts/restate1_reconcile.py diff --pre <dir>/pre --post <dir>/post

`updated_at` 一律排除在比對之外——重建必然更新它，把它算進去會讓每一列都「變動」，
對帳就失去鑑別力（要看的是**數據格**有沒有變，不是有沒有被重寫）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

# 受影響的四張表與其主鍵。year 條件見 _YEARS：2025 是重建目標年，9999 是生涯
# （build_splits 之後 run_build_splits 會接 build_career，生涯＝base＋本季，故本季一變
# 生涯跟著變——這是正確行為，但必須納入快照，否則對帳看不到一半的寫入範圍）。
TABLES: dict[str, list[str]] = {
    "batting_splits": ["year", "kind_code", "acnt", "item_group_code", "item_index", "item_name"],
    "pitching_splits": ["year", "kind_code", "acnt", "item_group_code", "item_index", "item_name"],
    "batting_vs_team": ["year", "kind_code", "acnt", "fight_team_code"],
    "pitching_vs_team": ["year", "kind_code", "acnt", "fight_team_code"],
}
_YEARS = (2025, 9999)

# 卡面核准的 14 人（INGEST-PLAYER-BIO-GAP1）。身分旗標由 local 翻為 import 的就是這批。
GAP1_PITCHERS = [
    "0000004796", "0000006891", "0000007547", "0000007554", "0000007555",
    "0000007556", "0000007558", "0000007559", "0000007573", "0000007579",
    "0000007583", "0000007588", "0000007590", "0000007603",
]


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


def _changed(pre: pl.DataFrame, post: pl.DataFrame, pk: list[str]) -> dict[str, object]:
    """回傳該表的變動摘要：新增／消失／值變動的 PK，以及變動列的 acnt 集合。"""
    pre_k, post_k = pre.select(pk), post.select(pk)
    added = post_k.join(pre_k, on=pk, how="anti")
    removed = pre_k.join(post_k, on=pk, how="anti")
    # 值變動：PK 兩邊都有，但非 PK 欄位有差異
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
        "touched_acnts": sorted(touched["acnt"].unique().to_list()) if touched.height else [],
    }


def diff(pre_dir: Path, post_dir: Path, report: Path | None) -> None:
    from cpbl.db import conn

    # 預期變動母體：2025 曾與那 14 位洋投同場對戰過的打者。
    # 用 game_livelog 的實際對戰配對，而不是「同場出賽」——同場但沒對到的打者，其
    # 本土／外籍分項不會因這 14 人的身分翻轉而改變。
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT DISTINCT hitter_acnt FROM cpbl.game_livelog "
            "WHERE year = 2025 AND pitcher_acnt = ANY(%s) AND hitter_acnt IS NOT NULL",
            (GAP1_PITCHERS,))
        expected_batters = {r[0] for r in cur.fetchall()}
    print(f"預期變動母體（2025 對戰過那 14 位洋投的打者）：{len(expected_batters)} 人\n")

    tables_out: dict[str, dict[str, object]] = {}
    out: dict[str, object] = {"expected_batters": len(expected_batters), "tables": tables_out}
    for table, pk in TABLES.items():
        pre = pl.read_parquet(pre_dir / f"{table}.parquet")
        post = pl.read_parquet(post_dir / f"{table}.parquet")
        summary = _changed(pre, post, pk)
        touched: set[str] = set(summary.pop("touched_acnts"))  # type: ignore[arg-type]
        # 差集＝變動了、卻不在預期母體內的人。非空即異常（卡面紅線 3）。
        unexpected = sorted(touched - expected_batters)
        summary["touched_acnt_count"] = len(touched)
        summary["unexpected_acnts"] = unexpected
        summary["unexpected_count"] = len(unexpected)
        tables_out[table] = summary
        flag = "✅" if not unexpected else "⚠️ 差集非空"
        print(f"{table}: 前 {summary['rows_pre']} → 後 {summary['rows_post']}　"
              f"新增 {summary['added']}／消失 {summary['removed']}／值變動 {summary['value_changed']}")
        print(f"  變動涉及 {len(touched)} 位 acnt；預期外 {len(unexpected)} 位 {flag}")
        if unexpected[:5]:
            print(f"  預期外樣本：{unexpected[:5]}")
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        print(f"\n報告 → {report}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("--out", type=Path, required=True)
    d = sub.add_parser("diff")
    d.add_argument("--pre", type=Path, required=True)
    d.add_argument("--post", type=Path, required=True)
    d.add_argument("--report", type=Path)
    args = ap.parse_args()
    if args.cmd == "snapshot":
        snapshot(args.out)
    else:
        diff(args.pre, args.post, args.report)


if __name__ == "__main__":
    main()
