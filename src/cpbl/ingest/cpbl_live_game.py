"""【實驗】賽況即時 TrackMan 探測：stats.cpbl 單場端點 /api/proxy/v1/games/{year}-{kind}-{sno}。

定位：**可行性實驗**，不掛常態爬蟲（refresh-recent 不會呼叫）、不寫 DB。
假說：比賽進行中此端點的 Data.Game 會帶即時逐球（TrackMan），可做賽況頁即時源。
已知（2026-07-04，SITE_MAP §4b）：端點免參數可用（200）、含隊伍/狀態/SkipTrackman；
比賽中的 payload 形狀**未驗證**——需在比賽進行中實測（uv run cpbl-live-game）。

stats 站 httpx 直連無挑戰、無鎖 IP 前科；單次探測請求量 = 1。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any

import httpx

log = logging.getLogger("cpbl.livegame")

BASE = "https://stats.cpbl.com.tw"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fetch_game(year: int, kind: str, sno: int, timeout: float = 30.0) -> dict:
    """單次抓單場物件。回傳 Data 整包（含 Game；比賽中可能含逐球）。"""
    url = f"{BASE}/api/proxy/v1/games/{year}-{kind}-{sno}"
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.json().get("Data") or {}


def _find_trackman(obj: Any, path: str = "") -> list[tuple[str, Any]]:
    """遞迴找所有 Trackman/Pitch 相關節點（實驗觀測用）。"""
    hits: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if any(t in k.lower() for t in ("trackman", "pitch", "log")):
                hits.append((p, v))
            hits += _find_trackman(v, p)
    elif isinstance(obj, list):
        if obj:
            hits += _find_trackman(obj[0], path + "[0]")
    return hits


def probe(year: int, kind: str, sno: int, dump_path: str | None = None) -> dict:
    """抓一次並整理觀測報告；dump_path 給定時存完整 JSON 供離線分析。"""
    data = fetch_game(year, kind, sno)
    game = data.get("Game") or {}
    report = {
        "fetched_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "game_id": f"{year}-{kind}-{sno}",
        "top_keys": sorted(data.keys()),
        "game_keys": sorted(game.keys()) if isinstance(game, dict) else str(type(game)),
        "status": {k: game.get(k) for k in ("GameStatus", "GameStatusChi", "SkipTrackman",
                                            "VisitingTotalScore", "HomeTotalScore")
                   if isinstance(game, dict)},
        "trackman_nodes": [],
    }
    for p, v in _find_trackman(data):
        desc = f"list len={len(v)}" if isinstance(v, list) else (
            f"dict keys={sorted(v.keys())[:10]}" if isinstance(v, dict) else repr(v)[:60])
        report["trackman_nodes"].append(f"{p}: {desc}")
    if dump_path:
        with open(dump_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        report["dump"] = dump_path
    return report
