"""#350 方案 D 示意（可拋棄）：從正式站 /api/v1/games/{sno}/live 唯讀快照彙總本系列逐人打擊原始計數
（ab/h/bb/hbp/sf/tb/pa）與 DH 先發次數，供 mockup 算區塊綜合成績。產品實作改由名單 API 提供，⛔ 不由前端逐場抓。

DH 先發判定（與 API 擴充設計同一口徑）：batting.role_type == "先發" 且該打者本場第一個
有 defend_station_code 的 livelog 事件（依 main_event_no）為 "DH"。
用法：python3 -I derive_series_batting.py out.json live_1.json live_2.json ...
"""
import json
import sys
from collections import Counter, defaultdict

out, *paths = sys.argv[1:]
dh = Counter()
bat = defaultdict(Counter)
games = []
for p in paths:
    d = json.load(open(p))
    g = d["game"][0] if isinstance(d["game"], list) else d["game"]
    games.append(g["game_sno"])
    for b in d["batting"]:
        c = bat[b["hitter_acnt"]]
        c["g"] += 1
        for k_out, k_in in (("pa", "plate_appearances"), ("ab", "at_bats"), ("h", "hits"), ("bb", "bb"),
                            ("hbp", "hbp"), ("sf", "sac_fly"), ("tb", "total_bases")):
            c[k_out] += b.get(k_in) or 0
    st = {b["hitter_acnt"] for b in d["batting"] if b["role_type"] == "先發"}
    first = {}
    for e in sorted(d["livelog"], key=lambda e: e["main_event_no"]):
        a = e["hitter_acnt"]
        if a in st and a not in first and e["defend_station_code"]:
            first[a] = e["defend_station_code"]
    for a, pos in first.items():
        if pos == "DH":
            dh[a] += 1
json.dump({"source": "GET /api/v1/games/{sno}/live?season=2026&kind_code=C", "games": games,
           "dh_starts": dict(dh), "batting": {k: dict(v) for k, v in bat.items()}},
          open(out, "w"), ensure_ascii=False, indent=1)
print("ok", games, dict(dh))
