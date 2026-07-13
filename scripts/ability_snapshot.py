"""能力值卡回歸快照：跨年代抽驗球員的各軸 PR/總評/組成 dump 成 JSON。

用法（改前後各跑一次再 diff，或 main 與分支 worktree 各跑一次）：
    uv run python scripts/ability_snapshot.py > snapshot.json

ABILITY-2 驗收準則：對照表人工判讀——90 年代（低 K 灌水應消除）、2016 打高投低
（接觸/壓制應反向修正）、現役（含 wSB/FIP/揮空/捕手 RA9 組成）方向皆須符合棒球常識。
"""
import json

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.api.routers.ability import _ability_card
from cpbl.db import conn

# 跨年代抽驗名單：90 年代／2016 打高投低／現役；含盜壘型、重砲、捕手、
# 先發/後援、三振/滾地型投手。
PLAYERS = {
    "0000000551": "林易增", "0000000573": "王光輝", "0000000486": "張泰山",
    "0000000045": "林智勝", "0000000935": "王柏融", "0000001804": "陳傑憲",
    "0000000476": "葉君璋", "0000000462": "黃平洋", "0000000564": "陳義信",
    "0000002589": "潘威倫", "0000004638": "古林睿煬", "0000000135": "陳禹勳",
    "0000003467": "林泓育", "0000004645": "戴培峰", "0000001119": "許基宏",
    "0000005151": "羅戈", "0000006497": "鋼龍", "0000002274": "黃子鵬",
}


def main() -> None:
    out = {}
    with conn() as c:
        cur = c.cursor()
        for pid, name in PLAYERS.items():
            for role in ("batting", "pitching"):
                for scope in ("career", "season"):
                    card = _ability_card(cur, pid, role, scope, DEFAULT_SEASON)
                    if not card.get("available"):
                        continue
                    out[f"{name}|{role}|{scope}"] = {
                        "overall": card["overall"],
                        "signature": card.get("signature"),
                        "axes": {a["key"]: {
                            "label": a["label"], "pr": a["pr"], "grade": a["grade"],
                            "comps": [(cp["label"], cp["weight"], cp["pr"])
                                      for cp in a["components"]],
                        } for a in card["axes"]},
                    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
