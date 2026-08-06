"""UX-GAME-RECAP1：單場打席事實流 API（賽後 recap／live Recent Plays／#79 探索器共用）。

只做查詢（API 唯讀契約）；打席邏輯全在 :mod:`cpbl.models.pa_facts`，本檔僅負責取
snapshot、呼叫服務、貼快取標頭。

與既有路由的分工（**不重疊、不取代**）：

* ``/api/v1/games/{sno}/live``：全量賽況 payload（box／逐球／snapshot），賽況頁主資料源。
* ``/api/v1/games/{sno}/winprob``、``/recap-wp``：WP／WPA **參考資訊**（全 scope 驗證
  unsupported）。本路由**不回任何 WP 欄位**，也禁止 WPA 參與關鍵打席排序。
* 本路由：canonical 打席 × ΔRE24 的事實流 ＋ 結論行事實句 ＋ 得分半局鏈。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.api.live_cache import get_public_live_snapshot
from cpbl.models.pa_facts import build_game_facts, cache_directive

router = APIRouter()


@router.get("/api/v1/games/{game_sno}/facts")
def game_facts(
    response: Response,
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E|D|F)$"),
) -> dict:
    """單場打席事實流：每打席＝局面狀態＋官方結果＋ΔRE24（打者觀點，正＝對打擊方有利）。

    資料源與呈現層級由 ``render_state`` 揭露（設計稿 §7 降級階梯）：
    ``authoritative``（DB canonical PA）／``provisional``（當晚 snapshot，mini 對帳全過）／
    ``provisional_simple``（對帳未過 → 簡版）／``stale_live``／``pending``／``postponed``／
    ``reconciling``。**呼叫端必須據此揭露，不得把暫定當權威照顯。**
    """
    snapshot = get_public_live_snapshot(season, kind_code, game_sno)
    payload = build_game_facts(season, kind_code, game_sno, snapshot=snapshot)
    if payload.get("reason") == "game_not_found":
        raise HTTPException(status_code=404, detail="查無此場次")
    response.headers["Cache-Control"] = cache_directive(payload)
    return payload
