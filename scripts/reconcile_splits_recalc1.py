"""INGEST-SPLITS-RECALC1 重建對帳：diff 必須逐格等於已查核的預期 delta。

模式：
  --apply  執行者用：快照 → 重建 2018–2026 A/D → diff(前後) 逐格對
           `ingest_splits_pa_split1_player_delta.json`（預期格全命中、非預期變動 0、
           vs_team 零變動）→ build_career(2026) 生涯吸收驗證 → 冪等重跑 diff=0。
  --check  查核者用（DB 已為 corrected）：驗 DB == 預期 corrected 值 →
           重建一次 diff=0（冪等＋可重現）。

任何硬性斷言失敗 exit 1。結果寫 docs/research/INGEST-SPLITS-RECALC1_RECONCILE.json。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from cpbl.db import conn
from cpbl.ingest.splits_calc import build_career, build_splits

ROOT = Path(__file__).resolve().parents[1]
DELTA_PATH = ROOT / "docs/research/ingest_splits_pa_split1_player_delta.json"
OUT_PATH = ROOT / "docs/research/INGEST-SPLITS-RECALC1_RECONCILE.json"
SNAP_DIR = ROOT / "artifacts" / "recalc1_snapshot"

TABLES = ("batting_splits", "pitching_splits", "batting_vs_team", "pitching_vs_team")
YEARS = range(2018, 2027)
PK: dict[str, tuple[str, ...]] = {}
VALUE_COLS: dict[str, tuple[str, ...]] = {}


def _norm(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    return v


def _eq(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    return a == b


def _load_schema() -> None:
    with conn() as c:
        for t in TABLES:
            pk = [r[0] for r in c.execute(
                "SELECT a.attname FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid "
                " AND a.attnum = ANY(i.indkey) "
                "WHERE i.indrelid = ('cpbl.' || %s)::regclass AND i.indisprimary "
                "ORDER BY a.attnum", (t,)).fetchall()]
            cols = [r[0] for r in c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'cpbl' AND table_name = %s "
                "ORDER BY ordinal_position", (t,)).fetchall()]
            PK[t] = tuple(pk)
            VALUE_COLS[t] = tuple(x for x in cols if x not in pk and x != "updated_at")


def _load(table: str) -> dict[tuple, dict[str, Any]]:
    with conn() as c:
        cols = PK[table] + VALUE_COLS[table]
        out: dict[tuple, dict[str, Any]] = {}
        for row in c.execute(
                f"SELECT {', '.join(cols)} FROM cpbl.{table}"):  # noqa: S608
            key = tuple(row[:len(PK[table])])
            out[key] = {c2: _norm(v) for c2, v in
                        zip(VALUE_COLS[table], row[len(PK[table]):], strict=True)}
        return out


def _snapshot() -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        for t in TABLES:
            path = SNAP_DIR / f"{t}.csv"
            with path.open("w", newline="") as f, c.cursor() as cur:
                cur.execute(f"SELECT * FROM cpbl.{t}")  # noqa: S608
                w = csv.writer(f)
                w.writerow([d.name for d in cur.description])
                w.writerows(cur)
    print(f"快照完成 → {SNAP_DIR}（{len(TABLES)} 表）")


def _diff(before: dict, after: dict, table: str) -> dict[tuple, dict[str, tuple]]:
    """回傳 {pk: {col: (before, after)}}，含整列出現/消失（另一側視為 None）。"""
    out: dict[tuple, dict[str, tuple]] = {}
    for key in before.keys() | after.keys():
        b, a = before.get(key), after.get(key)
        cells = {}
        for col in VALUE_COLS[table]:
            bv = b.get(col) if b else None
            av = a.get(col) if a else None
            if not _eq(bv, av):
                cells[col] = (bv, av)
        if b is None or a is None:
            cells["__row__"] = ("present" if b else None, "present" if a else None)
        if cells:
            out[key] = cells
    return out


def _expected() -> dict[tuple, dict]:
    d = json.loads(DELTA_PATH.read_text())
    out: dict[tuple, dict] = {}
    for r in d["rows"]:
        key = (r["table"], r["year"], r["kind"], r["acnt"],
               r["group"], r["item_index"], r["item_name"])
        out[key] = r
    return out


def _pk_to_expected_key(table: str, pk: tuple) -> tuple:
    # PK 序：year, kind_code, acnt, item_group_code, item_index, item_name
    year, kind, acnt, grp, idx, name = pk
    return (table, year, kind, acnt, grp, idx, name)


def _rebuild() -> None:
    for year in YEARS:
        res = build_splits(year, ("A", "D"))
        print(f"build_splits({year}) → {res if isinstance(res, dict) else 'ok'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args()

    _load_schema()
    expected = _expected()
    exp_splits_keys = {k for k in expected if k[0] in ("batting_splits", "pitching_splits")}
    report: dict[str, Any] = {
        "generated_at": dt.datetime.now().astimezone().isoformat(),
        "mode": "apply" if args.apply else "check",
        "expected_rows": len(expected),
        "expected_cells": sum(len(r["cols"]) for r in expected.values()),
    }
    failures: list[str] = []

    if args.apply:
        before = {t: _load(t) for t in TABLES}
        _snapshot()
        _rebuild()
        after = {t: _load(t) for t in TABLES}

        # 1) vs_team 零變動
        for t in ("batting_vs_team", "pitching_vs_team"):
            d = _diff(before[t], after[t], t)
            report[f"diff_{t}"] = len(d)
            if d:
                failures.append(f"{t} 應零變動，實得 {len(d)} 列")

        # 2) splits diff 逐格對預期
        matched_cells = 0
        wrong_value: list[dict] = []
        unexpected: list[dict] = []
        seen_keys: set[tuple] = set()
        for t in ("batting_splits", "pitching_splits"):
            d = _diff(before[t], after[t], t)
            for pk, cells in d.items():
                ek = _pk_to_expected_key(t, pk)
                exp = expected.get(ek)
                if exp is None:
                    unexpected.append({"table": t, "pk": list(pk),
                                       "cells": {k: list(v) for k, v in cells.items()}})
                    continue
                seen_keys.add(ek)
                for col, (bv, av) in cells.items():
                    if col == "__row__":
                        # 列出現/消失方向必須與預期 in_legacy/in_corrected 一致
                        if ((bv == "present") == exp["in_legacy"]
                                and (av == "present") == exp["in_corrected"]):
                            matched_cells += 1
                        else:
                            wrong_value.append({"table": t, "pk": list(pk),
                                                "col": "__row__",
                                                "before": bv, "after": av,
                                                "expected": {
                                                    "in_legacy": exp["in_legacy"],
                                                    "in_corrected": exp["in_corrected"]}})
                        continue
                    ec = exp["cols"].get(col)
                    if ec is None:
                        if (col == "item_note"
                                and exp["in_legacy"] != exp["in_corrected"]
                                and (bv is None) == (not exp["in_legacy"])
                                and (av is None) == (not exp["in_corrected"])):
                            # 整列出現/消失連帶的 metadata 欄（預期 delta 只比數值欄）
                            matched_cells += 1
                            continue
                        unexpected.append({"table": t, "pk": list(pk), "col": col,
                                           "before": bv, "after": av,
                                           "why": "預期 delta 無此格"})
                    elif _eq(bv, ec["legacy"]) and _eq(av, ec["corrected"]):
                        matched_cells += 1
                    else:
                        wrong_value.append({"table": t, "pk": list(pk), "col": col,
                                            "before": bv, "after": av,
                                            "expected": ec})
        missing = sorted(str(k) for k in exp_splits_keys - seen_keys)
        report.update({
            "matched_cells": matched_cells,
            "wrong_value": wrong_value,
            "unexpected_changes": unexpected,
            "expected_rows_not_hit": missing,
        })
        if wrong_value:
            failures.append(f"{len(wrong_value)} 格值不符預期")
        if unexpected:
            failures.append(f"{len(unexpected)} 筆非預期變動")
        if missing:
            failures.append(f"{len(missing)} 個預期 row 未命中")

        # 3) 生涯吸收：build_career(2026) 後，受影響 2026 acnt 的整數欄位移＝季 delta
        career_before = {t: {k: v for k, v in after[t].items() if k[0] == 9999}
                         for t in ("batting_splits", "pitching_splits")}
        build_career(2026)
        career_after = {t: {k: v for k, v in _load(t).items() if k[0] == 9999}
                        for t in ("batting_splits", "pitching_splits")}
        aff_2026: dict[tuple, dict[str, float]] = {}
        for r in expected.values():
            if r["year"] != 2026:
                continue
            for col, ec in r["cols"].items():
                if isinstance(ec["legacy"], float) or isinstance(ec["corrected"], float):
                    continue  # rate 欄生涯層重算，不做整數位移斷言
                k = (r["table"], r["acnt"], r["group"], r["item_index"], r["item_name"])
                aff = aff_2026.setdefault(k, {})
                aff[col] = aff.get(col, 0) + (ec["corrected"] or 0) - (ec["legacy"] or 0)
        career_mismatch: list[dict] = []
        aff_acnts = {k[1] for k in aff_2026}
        for t in ("batting_splits", "pitching_splits"):
            d = _diff(career_before[t], career_after[t], t)
            for pk, cells in d.items():
                _y, _kc, acnt, grp, idx, name = pk
                if acnt not in aff_acnts:
                    career_mismatch.append({"table": t, "pk": list(pk),
                                            "why": "非受影響選手的生涯值變動",
                                            "cells": {k: list(v) for k, v in cells.items()}})
                    continue
                exp_cols = aff_2026.get((t, acnt, grp, idx, name), {})
                for col, (bv, av) in cells.items():
                    if col == "__row__" or isinstance(bv, float) or isinstance(av, float):
                        continue
                    shift = (av or 0) - (bv or 0)
                    if shift != exp_cols.get(col, 0):
                        career_mismatch.append({"table": t, "pk": list(pk), "col": col,
                                                "shift": shift,
                                                "expected": exp_cols.get(col, 0)})
        report["career_mismatch"] = career_mismatch
        report["career_affected_acnts"] = sorted(aff_acnts)
        if career_mismatch:
            failures.append(f"生涯吸收 {len(career_mismatch)} 筆不符")

        # 4) 冪等：重跑一次 diff=0
        _rebuild()
        build_career(2026)
        after2 = {t: _load(t) for t in TABLES}
        idem = 0
        for t in TABLES:
            if t in ("batting_splits", "pitching_splits"):
                # 生涯（9999）以 career_after 為基準（after 是 build_career 前的值）
                base = {k: v for k, v in after[t].items() if k[0] != 9999}
                base.update(career_after[t])
                now = after2[t]
            else:
                base, now = after[t], after2[t]
            idem += len(_diff(base, now, t))
        report["idempotent_diff_rows"] = idem
        if idem:
            failures.append(f"冪等重跑仍有 {idem} 列變動")

    else:  # --check
        # 先以本分支（修正後）程式碼重建一次，避免每日 refresh 以舊碼重建本季
        # 造成的混合狀態干擾；隨後驗 DB == corrected、再重建一次驗冪等。
        # as-of 注意：若 DB 已含預期 delta 產生日（2026-07-30）之後的新場次，
        # 2026 列的絕對值會位移，依 PA-SPLIT1 卡面 as-of 原則判讀。
        _rebuild()
        cur = {t: _load(t) for t in ("batting_splits", "pitching_splits")}
        wrong: list[dict] = []
        hit = 0
        for ek, exp in expected.items():
            t = ek[0]
            pk = (exp["year"], exp["kind"], exp["acnt"], exp["group"],
                  exp["item_index"], exp["item_name"])
            row = cur[t].get(pk)
            for col, ec in exp["cols"].items():
                actual = row.get(col) if row else None
                if _eq(actual, ec["corrected"]):
                    hit += 1
                else:
                    wrong.append({"table": t, "pk": list(pk), "col": col,
                                  "actual": actual, "expected": ec["corrected"]})
        report.update({"corrected_cells_hit": hit, "corrected_cells_wrong": wrong})
        if wrong:
            failures.append(f"{len(wrong)} 格與預期 corrected 不符")
        before = {t: _load(t) for t in TABLES}
        _rebuild()
        after = {t: _load(t) for t in TABLES}
        idem = sum(len(_diff(before[t], after[t], t)) for t in TABLES)
        report["idempotent_diff_rows"] = idem
        if idem:
            failures.append(f"重建後 {idem} 列變動（應為 0）")

    report["failures"] = failures
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                   default=str) + "\n")
    for f in failures:
        print("✗", f)
    if not failures:
        print("✓ 對帳全數通過：預期格全命中、非預期變動 0、vs_team 不變、"
              "生涯吸收一致、冪等 diff=0"
              if args.apply else "✓ check 通過：DB == corrected 且重建冪等")
    print(f"→ {OUT_PATH}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
