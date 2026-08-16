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

⚠️ **而且完整性證不到**：實測回收是**逐 process 獨立**的——2026-08-15 00:32 的一般日誌
還在（4406 列），同一分鐘的 `usernoted` 通知紀錄卻已消失。所以「別的 process 還有資料」
無法推論「通知紀錄還在」。本檔因此不宣稱完整性，只做兩件事：
  · 零樣本一律**拒答**（分不出「沒有通知」與「紀錄被回收」）
  · 非零樣本照常輸出，但強制標上**取樣時刻**

**判準：本檔的輸出只能被引用為「於 X–Y 視窗、在 T 時刻量得」，不得寫成無時間限定的宣稱。**

## 關聯方式與它的限制

逐則通知的判定沿用 `scripts/schedule_watch.py` 的作法，但**少一個錨點**：即時探針
知道自己的 `osascript` PID，回頭分析歷史資料沒有這個資訊。故本檔的關聯是

1. `usernoted` 的 `Delivering` 行帶 `uuid:"XXXXXXXX"` ⇒ 一則通知一個 uuid（唯一）
2. 該 uuid 出現過的時間跨距，就是這則通知在日誌上的生命期
3. 打擾裁決行（`Resolved interruption suppression … as …`／`muted by …`）**只帶恆定的
   `ident`**（osascript 一律 `DA39-A3EE`，空字串的 SHA-1 前綴）——它在此平台上**無法**
   被歸屬到特定通知（完整查證見 `scripts/schedule_watch.py` 的「已知限制」表）。
   故改用兩道閘，任一不過就判 `ambiguous`，**絕不以順序或距離挑一條**：
     閘一 · 跨距內只能有這一則通知的 uuid
     閘二 · 跨距內所有裁決必須指向同一個結論

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

FMT = "%Y-%m-%d %H:%M:%S"

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


def _run_log(start: str, end: str, predicate: str | None) -> tuple[list[str], list[str]]:
    argv = [LOG_BIN, "show", "--start", start, "--end", end, "--style", "compact"]
    if predicate:
        argv += ["--predicate", predicate]
    proc = subprocess.run(argv, capture_output=True, check=False)
    if proc.returncode != 0:
        sys.exit(f"log show 失敗（{proc.returncode}）："
                 f"{proc.stderr.decode('utf-8', 'replace')[:300]}")
    return proc.stdout.decode("utf-8", "replace").splitlines(), argv


def _overlaps(lines: list[str], start: datetime, end: datetime) -> bool:
    """回傳的資料是否**真的落在**請求視窗裡（有交集就算）。

    ⚠️ 這一條是必要的，因為 `log show` 在請求視窗超出保留範圍時**不報錯、也不回空**，
    而是**默默忽略兩個邊界並倒出最近的資料**。實測：
        log show --start '2020-01-01 00:00:00' --end '2020-01-01 00:01:00'
    回了 219,408 行，第一列是 `2026-08-16 22:35:56`——問 2020 卻拿到今天。
    沒有這道檢查，那些資料會被當成 2020 年的樣本算進統計裡。

    ⚠️ 判準刻意是**有沒有交集**，不是「每一列都在界內」：實測 `--end` 會溢出約一秒
    （請求 12:00:00 會拿到 12:00:01.268 的列），那是 log show 的邊界解析度，不是
    邊界被忽略。用「全部在界內」當判準會把正常查詢也擋掉；用交集則兩者分得開——
    邊界被忽略時，回傳範圍與請求視窗**完全不相交**。溢出的列另由呼叫端濾掉。
    """
    stamps = [t for ln in lines if (t := _ts(ln))]
    if not stamps:
        return True          # 零樣本另有一條專門的判準，不在這裡處理
    return min(stamps) <= end and max(stamps) >= start


def collect(start: str, end: str, start_dt: datetime, end_dt: datetime,
            ) -> tuple[list[str], list[str], bool]:
    """回傳 (日誌行, 實際執行的指令)。指令一併回傳是為了讓報告可以原樣附上。

    ⚠️ 兩道 fail-closed：邊界被忽略、以及「零樣本但無法證明視窗還在」，都拒答而不輸出零。
    """
    lines, argv = _run_log(start, end, PREDICATE)

    if not _overlaps(lines, start_dt, end_dt):
        stamps = [t for ln in lines if (t := _ts(ln))]
        sys.exit(
            f"⚠️ 拒絕輸出：log show 沒有遵守請求的邊界。\n"
            f"   請求視窗 {start} → {end}，但回傳資料落在 "
            f"{min(stamps)} … {max(stamps)}——與請求視窗**完全不相交**。\n"
            "   這是 `--start` 超出保留範圍時的已知行為：它會默默忽略邊界並倒出最近的\n"
            "   資料。此時任何統計都是**別的時間段**的樣本，故不輸出任何數字。")

    # `--end` 會溢出約一秒（實測請求 12:00:00 會拿到 12:00:01.268 的列）。那些列若留著
    # 會被算進統計，故在此濾掉——濾掉之後同一視窗的樣本才真的固定。
    dropped = sum(1 for ln in lines if (t := _ts(ln)) and not (start_dt <= t <= end_dt))
    lines = [ln for ln in lines if not (t := _ts(ln)) or start_dt <= t <= end_dt]
    if dropped:
        print(f"（邊界溢出已濾除 {dropped} 列——log show 的 --end 解析度所致）")

    # ================= 完整性**無法**被證明：回收是逐 process 的，不是逐時間的
    #
    # 我原本想用「不加 predicate 問視窗開頭有沒有資料」來判斷覆蓋是否完整。**那個判準
    # 是錯的**，實測（2026-08-16 22:5x）當場推翻：
    #
    #   一般日誌 2026-08-15 00:00:00–00:01:00 ......... 4480 列（還在）
    #   一般日誌 2026-08-15 00:32:00–00:33:00 ......... 4406 列（還在）
    #   `usernoted` 的 Delivering 於 00:32:00–00:33:30 .... **0 列（不見了）**
    #
    # 同一個時間點，一般日誌在、通知紀錄不在 ⇒ **環形緩衝是各 process／subsystem 獨立
    # 回收的**，不是整個 store 依時間一起往前推。因此用「別的 process 還有沒有資料」
    # 去推論「通知紀錄在不在」，是拿 A population 的存在去證明 B population——不成立。
    #
    # 結論：本工具**沒有辦法證明某個過去視窗的通知紀錄是完整的**。既然證不到，就不宣稱。
    # 處置分兩段：
    #   · 零樣本 ⇒ 一律拒答（見下）。「這段沒有通知」與「這段的通知紀錄被回收了」在
    #     此平台上無法分辨，輸出零就是把不知道講成知道。
    #   · 非零樣本 ⇒ 照常輸出，但**強制標上取樣時刻**，並在頁首寫明數字只在該時刻成立。
    #     這是需求方授權的處置：「若本質上不可固定，就不要寫成宣稱，改為『於某明確時刻
    #     量得』並附取樣指令」。
    if not any(_ts(ln) for ln in lines):
        sys.exit(
            f"⚠️ 拒絕輸出：視窗 {start} → {end} 內沒有任何通知紀錄。\n"
            "   「這段時間真的沒有通知」與「這段時間的通知紀錄已被回收」在此平台上\n"
            "   **無法分辨**——回收是逐 process 獨立的，拿別的 process 還有沒有資料\n"
            "   去推論通知紀錄在不在並不成立（實測見本檔原始碼註解）。\n"
            "   故不輸出零樣本統計。請改用一個較近、確定還有通知的視窗。")

    return lines, argv, True


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
        # 與 scripts/schedule_watch.py 同一條規則：**不看順序**，收集所有裁決後要求一致。
        # 挑「第一條」沒有事實依據——裁決行無法歸屬到特定通知，挑了就是把猜測寫成程式碼。
        states = set()
        detail = ""
        for ln in window:
            m = MUTED_RE.search(ln)
            if m:
                states.add("suppressed")
                detail = detail or f"muted by {(m.group(1) or '').strip()}"
                continue
            r = RESOLUTION_RE.search(ln)
            if r:
                states.add("presented" if r.group(1) == NOT_SUPPRESSED else "suppressed")
                detail = detail or f"resolved as {r.group(1)}"
        if len(states) > 1:
            results.append({"at": t, "app": app, "uuid": uuid, "verdict": "ambiguous",
                            "detail": f"裁決彼此矛盾（{sorted(states)}）"})
            continue
        if states:
            results.append({"at": t, "app": app, "uuid": uuid,
                            "verdict": states.pop(), "detail": detail})
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
        start_dt = datetime.strptime(args.start, FMT)
        end_dt = datetime.strptime(args.end, FMT)
    except ValueError as error:
        sys.exit(f"--start/--end 需為 'YYYY-MM-DD HH:MM:SS'：{error}")
    # ⚠️ `log show` 對 start > end **不報錯**：實測它照樣 exit 0 並從 start 倒資料出來。
    if start_dt >= end_dt:
        sys.exit(f"--start（{args.start}）不早於 --end（{args.end}）。"
                 "log show 對這種輸入不會報錯，會直接倒出資料，故在此擋掉。")
    if end_dt > datetime.now():
        sys.exit(f"--end（{args.end}）還在未來：此時的輸出會隨重跑時刻改變，"
                 "不具重現性。請等視窗結束後再量，或改用已經過去的終點。")

    lines, argv, _ = collect(args.start, args.end, start_dt, end_dt)
    results, coverage = classify(lines)

    print("=" * 78)
    print("重跑指令（原樣複製即可逐位比對）：")
    print("  " + " ".join(f"'{a}'" if " " in a else a for a in argv))
    print("=" * 78)
    print(f"取樣時刻    : {datetime.now().strftime(FMT)}  ← **數字只在這個時刻成立**")
    print("            本工具無法證明過去視窗的通知紀錄完整（回收是逐 process 獨立的，")
    print("            見原始碼註解的實測）。引用時必須連同視窗與取樣時刻一起寫，")
    print("            不得寫成無時間限定的宣稱。")
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
