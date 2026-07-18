"""擷取球員頁 IA prototype 用的真實 fixture（UX-PLAYER-IA1）。

從本機 API 抓 5 位代表性球員（打者/投手/雙棲/二軍 tracking 缺漏/退役）的
detail 端點回應，存為 web/src/app/dev/player-ia/fixtures/*.json。
大型逐球陣列截斷至 400 筆以控制 repo 體積（仍為真實資料）。

用法：先起 API（uv run uvicorn cpbl.api.main:app --port 4012），再
  uv run python scripts/capture_player_ia_fixtures.py [--base http://localhost:4012]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

PLAYERS = {
    "batter": {"id": "0000005549", "name": "郭天信", "roles": ["batting"], "kind": "A"},
    "pitcher": {"id": "0000005151", "name": "羅戈", "roles": ["pitching"], "kind": "A"},
    "twoway": {"id": "0000003563", "name": "余德龍", "roles": ["batting", "pitching"], "kind": "A"},
    "farm": {"id": "0000004627", "name": "張偉聖", "roles": ["batting"], "kind": "D"},
    "retired": {"id": "0000000667", "name": "彭政閔", "roles": ["batting"], "kind": "A"},
}

TRUNCATE_KEYS = ("points", "spray", "batted")
TRUNCATE_N = 400

OUT_DIR = Path(__file__).resolve().parent.parent / "web/src/app/dev/player-ia/fixtures"


def truncate(payload: object) -> object:
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            if k in TRUNCATE_KEYS and isinstance(v, list) and len(v) > TRUNCATE_N:
                out[k] = v[:TRUNCATE_N]
                out[f"{k}_total"] = len(v)
            else:
                out[k] = truncate(v)
        return out
    if isinstance(payload, list):
        return [truncate(x) for x in payload]
    return payload


def capture(client: httpx.Client, pid: str, roles: list[str], kind: str) -> dict:
    def get(path: str):
        r = client.get(path)
        r.raise_for_status()
        return truncate(r.json())

    fx: dict = {
        "profile": get(f"/api/v1/players/{pid}/profile"),
        "season": get(f"/api/v1/players/{pid}/season?kind={kind}"),
        "advanced": get(f"/api/v1/players/{pid}/advanced?kind_code={kind}"),
        "careerStats": get(f"/api/v1/players/{pid}/career"),
        "abilityCard": get(f"/api/v1/players/{pid}/ability-card"),
        "fieldingSeason": get(f"/api/v1/players/{pid}/fielding?scope=season&kind_code={kind}"),
        "fieldingCareer": get(f"/api/v1/players/{pid}/fielding?scope=career&kind_code=A"),
    }
    for role in roles:
        fx[role] = {
            "discipline": get(f"/api/v1/players/{pid}/discipline?role={role}&kind_code={kind}"),
            "pitchMix": get(f"/api/v1/players/{pid}/pitch-mix?role={role}&kind_code={kind}"),
            "arsenal": get(f"/api/v1/players/{pid}/arsenal?role={role}") if kind == "A" else {"items": []},
            "trend": get(f"/api/v1/players/{pid}/trend?role={role}"),
            "trendCareer": get(f"/api/v1/players/{pid}/trend-career?role={role}&bucket=week"),
            "vsTeam": get(f"/api/v1/players/{pid}/vs-team?role={role}"),
            "career": get(f"/api/v1/players/{pid}/{role}"),
            "sabr": get(f"/api/v1/players/{pid}/sabr?role={role}"),
            "traits": get(f"/api/v1/players/{pid}/traits?role={role}"),
            "splitsSeason": get(f"/api/v1/players/{pid}/splits?role={role}&year=2026&kind_code={kind}"),
            "splitsCareer": get(f"/api/v1/players/{pid}/splits?role={role}&year=9999&kind_code=A"),
        }
        if role == "pitching":
            fx[role]["movement"] = get(f"/api/v1/players/{pid}/movement?kind_code={kind}")
    return fx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:4012")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.base, timeout=30) as client:
        for key, meta in PLAYERS.items():
            fx = capture(client, meta["id"], meta["roles"], meta["kind"])
            fx["_meta"] = {"scenario": key, **meta, "captured_from": args.base}
            path = OUT_DIR / f"{key}.json"
            path.write_text(json.dumps(fx, ensure_ascii=False, separators=(",", ":")) + "\n")
            print(f"{key}: {meta['name']} -> {path.name} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
