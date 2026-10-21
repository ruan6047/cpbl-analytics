"""#350 規劃示意（可拋棄）：從正式站 /api/v1/games/{sno}/live 唯讀快照算「本系列 DH 先發次數」。

判定（示意用代理，未驗證等同官方先發守位）：box `batting.role_type == "先發"` 的打者，
其本場第一個打席事件（livelog 依 main_event_no 排序）的 `defend_station_code == "DH"` ⇒ 該場 DH 先發。
用法：python3 -I derive_series_dh.py out.json live_1.json live_2.json ...
"""
import json
import sys
from collections import Counter

out, *paths = sys.argv[1:]
dh, starts = Counter(), Counter()
games = []
for p in paths:
    d = json.load(open(p))
    g = d["game"][0] if isinstance(d["game"], list) else d["game"]
    games.append(g.get("game_sno"))
    st = {b["hitter_acnt"] for b in d["batting"] if b["role_type"] == "先發"}
    first = {}
    for e in sorted(d["livelog"], key=lambda e: e["main_event_no"]):
        a = e["hitter_acnt"]
        if a in st and a not in first and e["defend_station_code"]:
            first[a] = e["defend_station_code"]
    for a, pos in first.items():
        starts[a] += 1
        if pos == "DH":
            dh[a] += 1
json.dump({"source": "GET /api/v1/games/{sno}/live?season=2026&kind_code=C", "games": games,
           "dh_starts": dict(dh), "starts": dict(starts)}, open(out, "w"), ensure_ascii=False, indent=1)
print("ok", games, dict(dh))
