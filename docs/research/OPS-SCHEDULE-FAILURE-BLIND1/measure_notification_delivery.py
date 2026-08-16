#!/usr/bin/env python3
"""macOS 通知投遞的可重建量測（OPS-SCHEDULE-FAILURE-BLIND1／#132）。

## 為什麼有這一支

本卡的診斷數字錯了三代，每一代都是「量測面與待答問題不對齊」：

| 輪次 | 宣稱 | 錯在哪 |
|---|---|---|
| R2 | suppressed 103／allowed 11 | 數的是 `donotdisturbd` 的**預載解析**，不是通知投遞 |
| R3 | 44/12、1960/56 | 對象修對了，但視窗寫成「最近 48 小時」⇒ **換個時刻重跑就是別的數字** |
| 查核 | 37/12、1982/49 | 同一句宣稱、不同時刻、不同值——於是誰都無法對帳 |

R3 的問題不是算錯，是**邊界沒釘住**。「最近 48 小時」是相對量，它讓一句宣稱在不同
時刻有不同的真值，而那種宣稱沒有辦法被查核——這正是本卡自己在防的形狀。

所以本檔只接受**絕對時間戳**，並把用到的 `log show` 指令原樣印出來，讓任何人可以
逐位重跑、逐位比對。

## ⚠️ 日誌會滾動：本質上不可保證永久重現

`log show` 讀的是系統的環形緩衝，舊資料會被回收。因此本檔的輸出**不是**「永遠為真的
事實」，而是「某個明確視窗、在還讀得到的時候量到的值」。本檔一律印出實際觀測到的
第一筆／最後一筆時戳，讓重跑者一眼看出自己的 log store 還涵不涵蓋那段——涵蓋不到就
會看到不同的樣本數，那是保留期限造成的，不是誰算錯。

**判準：本檔的輸出只能被引用為「於 X–Y 視窗量得」，不得寫成無時間限定的宣稱。**

## 關聯方式與它的限制

逐則通知的判定沿用 `scripts/schedule_watch.py` 的作法，但**少一個錨點**：即時探針
知道自己的 `osascript` PID，回頭分析歷史資料沒有這個資訊。故本檔的關聯是

1. `usernoted` 的 `Delivering` 行帶 `uuid:"XXXXXXXX"` ⇒ 一則通知一個 uuid（唯一）
2. 該 uuid 出現過的時間跨距，就是這則通知在日誌上的生命期
3. 打擾裁決行（`Resolved interruption suppression … as …`／`muted by …`）**只帶恆定的
   `ident`**（osascript 一律 `DA39-A3EE`，空字串的 SHA-1 前綴），故只能用上述跨距圈；
   跨距內若出現一個以上的通知 uuid ⇒ 判 `ambiguous`，**不猜**

`donotdisturbd` **完全不採用**：它的行沒有任何欄位對得回某一則通知（uuid 欄位沒有、
`identifier` 是空字串、`UUID:` 是解析自己的 id、`clientIdentifier` 是預載客戶端），
只剩 bundle 可比，而同一 bundle 在同一秒可有大量與投遞無關的預載解析。R2 的 103/11
就是這樣來的。

用法：
    docs/research/OPS-SCHEDULE-FAILURE-BLIND1/measure_notification_delivery.py \\
        --start "2026-08-15 00:00:00" --end "2026-08-16 12:00:00"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta

# ⚠️ 絕對路徑：`log` 在 zsh 是內建指令，裸寫 `log show` 會被 shell 吃掉並回
# 「too many arguments」，看起來像「沒有紀錄」。本卡 R1 的假陰性就是這樣來的。
LOG_BIN = "/usr/bin/log"
PREDICATE = 'process == "NotificationCenter" OR process == "usernoted"'

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")
UUID_RE = re.compile(r'uuid:"([0-9A-F]+)"')
APP_RE = re.compile(r'app:"([^"]+)"')
RESOLUTION_RE = re.compile(r"Resolved interruption suppression for \S+ as (\w+)")
MUTED_RE = re.compile(r"muted by ([A-Za-z ]+?)(?::\s*(\S+)|\s*\(([^)]*)\))")
NOT_SUPPRESSED = "none"


def _ts(line: str):
    m = TS_RE.match(line)
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f") if m else None


def collect(start: str, end: str) -> tuple[list[str], list[str]]:
    """回傳 (日誌行, 實際執行的指令)。指令一併回傳是為了讓報告可以原樣附上。"""
    argv = [LOG_BIN, "show", "--start", start, "--end", end,
            "--style", "compact", "--predicate", PREDICATE]
    proc = subprocess.run(argv, capture_output=True, check=False)
    if proc.returncode != 0:
        sys.exit(f"log show 失敗（{proc.returncode}）："
                 f"{proc.stderr.decode('utf-8', 'replace')[:300]}")
    return proc.stdout.decode("utf-8", "replace").splitlines(), argv


def classify(lines: list[str]) -> tuple[list[dict], dict]:
    """逐則通知判定。回傳 (每則的結果, 視窗實際涵蓋範圍)。"""
    deliveries = []           # (時間, app, uuid)
    spans: dict[str, list] = {}
    for line in lines:
        t = _ts(line)
        if not t:
            continue
        for u in UUID_RE.findall(line):
            spans.setdefault(u, []).append(t)
        if "Delivering " in line:
            app, uu = APP_RE.search(line), UUID_RE.search(line)
            if app and uu:
                deliveries.append((t, app.group(1), uu.group(1)))

    results = []
    for t, app, uuid in sorted(deliveries):
        stamps = spans.get(uuid, [t])
        lo, hi = min(stamps) - timedelta(seconds=1), max(stamps) + timedelta(seconds=1)
        window = [ln for ln in lines
                  if (_t := _ts(ln)) and lo <= _t <= hi]
        others = {u for ln in window for u in UUID_RE.findall(ln)} - {uuid}
        if others:
            results.append({"at": t, "app": app, "uuid": uuid, "verdict": "ambiguous",
                            "detail": f"跨距內另有 {len(others)} 則通知"})
            continue
        muted = next((ln for ln in window if MUTED_RE.search(ln)), None)
        if muted:
            m = MUTED_RE.search(muted)
            results.append({"at": t, "app": app, "uuid": uuid, "verdict": "suppressed",
                            "detail": f"muted by {(m.group(1) or '').strip()}"})
            continue
        res = next((ln for ln in window if RESOLUTION_RE.search(ln)), None)
        if res:
            behavior = RESOLUTION_RE.search(res).group(1)
            results.append({
                "at": t, "app": app, "uuid": uuid,
                "verdict": "presented" if behavior == NOT_SUPPRESSED else "suppressed",
                "detail": f"resolved as {behavior}"})
            continue
        results.append({"at": t, "app": app, "uuid": uuid, "verdict": "unverified",
                        "detail": "無裁決行"})

    observed = [t for ts in spans.values() for t in ts]
    coverage = {"first": min(observed).isoformat() if observed else None,
                "last": max(observed).isoformat() if observed else None}
    return results, coverage


def main() -> None:
    ap = argparse.ArgumentParser(
        description="macOS 通知投遞的可重建量測（只吃絕對時間戳）")
    ap.add_argument("--start", required=True, help='例："2026-08-15 00:00:00"')
    ap.add_argument("--end", required=True, help='例："2026-08-16 12:00:00"')
    ap.add_argument("--per-notification", action="store_true", help="逐則列出")
    args = ap.parse_args()

    # ⚠️ 視窗終點若還在未來，這次的輸出**不可重現**——晚一點重跑會多撈到資料。
    # 實測：11:59 跑 `--end "2026-08-16 12:00:00"` 得 72548 行，12:01 再跑得 72557 行。
    # 兩次都「正確」，但它們不是同一個樣本，於是又變成一句沒有辦法對帳的宣稱。
    try:
        end_dt = datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        sys.exit(f"--end 需為 'YYYY-MM-DD HH:MM:SS'，收到：{args.end!r}")
    if end_dt > datetime.now():
        sys.exit(f"--end（{args.end}）還在未來：此時的輸出會隨重跑時刻改變，"
                 "不具重現性。請等視窗結束後再量，或改用已經過去的終點。")

    lines, argv = collect(args.start, args.end)
    results, coverage = classify(lines)

    print("=" * 78)
    print("重跑指令（原樣複製即可逐位比對）：")
    print("  " + " ".join(f"'{a}'" if " " in a else a for a in argv))
    print("=" * 78)
    print(f"要求視窗    : {args.start} → {args.end}")
    print(f"實際觀測範圍: {coverage['first']} → {coverage['last']}")
    print("            ⚠️ 若上一行明顯窄於要求視窗，代表 log store 已回收部分資料，")
    print("              樣本數會因此變少——那是保留期限，不是計算錯誤。")
    print(f"日誌行數    : {len(lines)}")
    print(f"通知則數    : {len(results)}")
    print()
    print("逐則判定彙總：")
    for verdict, n in sorted(Counter(r["verdict"] for r in results).items()):
        print(f"  {verdict:12s} {n:4d}")
    print()
    print("按 app：")
    by_app: dict[str, Counter] = {}
    for r in results:
        by_app.setdefault(r["app"], Counter())[r["verdict"]] += 1
    for app, counter in sorted(by_app.items(), key=lambda kv: -sum(kv[1].values())):
        detail = " ".join(f"{k}={v}" for k, v in sorted(counter.items()))
        print(f"  {app:52s} {detail}")

    if args.per_notification:
        print()
        print("逐則：")
        for r in results:
            print(f"  {r['at']:%Y-%m-%d %H:%M:%S}  {r['verdict']:11s} "
                  f"{r['uuid']}  {r['app']:46s} {r['detail']}")


if __name__ == "__main__":
    main()
