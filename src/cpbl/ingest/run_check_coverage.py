"""CLI：資料涵蓋率排查（唯讀、不爬網）——抓「應有卻缺漏」的場次。

    uv run cpbl-check-coverage [year] [kind]     # 預設 今年 A

兩類缺漏：
1. **逐球缺漏**：完成場、球場有 TrackMan 設備、但 pitch_tracking 覆蓋率 < 門檻。
   設備判定為經驗式——某球場只要本季有任一場覆蓋率 ≥ 80% 即視為「有設備」，
   避免把大巨蛋等無設備場誤報。缺漏場印出建議：重跑 cpbl-scrape-pitches。
2. **缺 gamelog**：完成場（比分>0）卻無 livelog（逐打席）——延賽補賽/漏跑常見。

退出碼：有任何缺漏回 1（供腳本/CI 判斷），全乾淨回 0。
"""

from __future__ import annotations

import sys
from datetime import date

from cpbl.db import conn

COVER_OK = 0.80   # 判定「有設備」的球場：本季曾達此覆蓋率
COVER_BAD = 0.70  # 低於此且在有設備球場 → 標為缺漏
MIN_PITCHES = 50  # 太少球的場不判（避免雜訊）


def _rows(year: int, kind: str) -> list[dict]:
    with conn() as c:
        cur = c.execute(
            """
            SELECT g.game_sno, g.game_date, g.venue,
                   (g.home_score + g.away_score > 0) AS completed,
                   (SELECT count(*) FROM cpbl.game_livelog ll
                      WHERE ll.year=g.year AND ll.kind_code=g.kind_code AND ll.game_sno=g.game_sno
                        AND (ll.is_ball OR ll.is_strike)) AS pitches,
                   (SELECT count(*) FROM cpbl.game_livelog ll
                      WHERE ll.year=g.year AND ll.kind_code=g.kind_code AND ll.game_sno=g.game_sno) AS livelog,
                   (SELECT count(*) FROM cpbl.pitch_tracking pt
                      WHERE pt.year=g.year AND pt.kind_code=g.kind_code AND pt.game_sno=g.game_sno) AS tracked
            FROM cpbl.games g
            WHERE g.year=%s AND g.kind_code=%s
            ORDER BY g.game_date, g.game_sno
            """,
            (year, kind))
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def main() -> None:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    kind = sys.argv[2] if len(sys.argv) > 2 else "A"
    rows = _rows(year, kind)

    # 有設備球場：本季曾達 COVER_OK 覆蓋率
    equipped: set[str] = set()
    for r in rows:
        if r["completed"] and r["pitches"] >= MIN_PITCHES and r["tracked"] / r["pitches"] >= COVER_OK:
            equipped.add(r["venue"])

    # partial＝有部分逐球卻不足 → 幾乎必為爬蟲缺漏（別的投手漏抓），重爬可補。
    # zero＝完全零逐球 → 可能該場設備當日沒錄（源頭 Trackman=null，如大巨蛋），需查源頭。
    partial, zero, gamelog_missing = [], [], []
    for r in rows:
        if not r["completed"]:
            continue
        if r["livelog"] == 0:
            gamelog_missing.append(r)
            continue
        if r["venue"] in equipped and r["pitches"] >= MIN_PITCHES:
            ratio = r["tracked"] / r["pitches"]
            if r["tracked"] == 0:
                zero.append(r)
            elif ratio < COVER_BAD:
                partial.append(r)

    print(f"=== 涵蓋率排查 {year}/{kind} ===")
    print(f"有 TrackMan 設備球場（本季實證）：{sorted(equipped)}")

    if gamelog_missing:
        print(f"\n⚠️  缺 gamelog 的完成場 {len(gamelog_missing)} 場（重跑 cpbl-scrape-gamelog）：")
        for r in gamelog_missing:
            print(f"    sno={r['game_sno']} {r['game_date']} {r['venue']}")

    if partial:
        print(f"\n⚠️  逐球部分缺漏 {len(partial)} 場（先重跑 cpbl-scrape-pitches {year} {kind}；"
              f"若重跑後仍不足＝該場源頭只錄到部分，非缺漏）：")
        for r in partial:
            print(f"    sno={r['game_sno']} {r['game_date']} {r['venue']}："
                  f"{r['tracked']}/{r['pitches']} ({round(100 * r['tracked'] / r['pitches'])}%)")

    if zero:
        print(f"\nℹ️  逐球完全零 {len(zero)} 場（設備場但整場無逐球；重爬後仍零＝該場源頭無 TrackMan，非缺漏。"
              f"多為亞太主早季未裝機、大巨蛋設備不穩）：")
        for r in zero:
            print(f"    sno={r['game_sno']} {r['game_date']} {r['venue']}：0/{r['pitches']}")

    if not gamelog_missing and not partial:
        print("\n✅ 無「可補救」缺漏（gamelog 齊、逐球無部分缺；零覆蓋場多為源頭無資料）。")
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
