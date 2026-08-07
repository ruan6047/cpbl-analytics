"""GAME-RECAP-WP-API1：逐打席 WP／WPA 參考資訊 API（揭露語意）。

只消費 GAME-RECAP-PA1 canonical 打席（cpbl.game_plate_appearances，published
build），不重建、不去重打席——近似分組是既有 /winprob 的舊契約，本路由取代其
語意但不動舊路由（相容演進）。WP 解算器 import 自 models/winprob（生產
run_dist artifact）與 models/winprob_val（規則參數化 DP：9 局門檻、12 局和局、
2024+ 一軍突破僵局、季後無和局；VAL1 已證與生產解算器 legacy 規則下逐值相等）。

誠實紅線（本卡 2026-07-27 定位：canonical → 參考資訊＋揭露）：
* 所有 scope 的時間外驗證結論皆 unsupported（WP-VAL1），事後校準修復 No-Go
  （WP-CAL1，修正不具時間平穩性）→ WP/WPA 一律以「參考資訊」語意提供，
  response 附版本化 `wp_reliability` metadata 揭露驗證結論、分布來源與已知偏差，
  不宣稱 canonical、不暗示個人歸因具權威性。
* fail closed：state != 'ready' 或 pre_state 關鍵欄缺值的打席保留事件列，
  但 WP/WPA 欄不可用並附機器可讀原因；無對應分布 artifact（D scope）回
  model_not_built，不靜默借用未驗證分布。
* 邊界唯一 canonical 行為：`home_wp_after` 一律取「下一個真實打席的打席前
  狀態」（換局自然銜接；非 non_pa 佈局列——其快照在突破僵局跑者佈局前，
  不可作錨點）；最後一個真實打席收斂到終場結果（勝 1／負 0／和 0.5，
  含再見）；延長規則依 (kind, season) 參數化。
* ⚠️ **打席前比分只能取事件流**（DATA-RECAP-WP-PRESTATE1）：canonical
  `pre_state.away_score`／`home_score` 是把**起始事件列的比分欄**原樣存下來，
  而 livelog 的比分欄是**事件後**快照——單一事件就結束的得分打席（例如首球
  全壘打）起始列＝終結列，`pre_state` 存到的已是得分**後**的比分。拿它算 WP
  會讓該打席自己的 WPA 被歸零、並把那筆得分誤記到前一個打席（後者的 after
  錨點正是這個被污染的 pre_state）。修法比照 `models/pa_facts.delta_re24`：
  以 `start_event_no` 對回 `annotate_scores()` 標好的事件流，取該事件**之前**
  的 running 比分。**病灶在讀取端**——canonical PA 忠實存下來源欄位，語意由
  消費端負責，故本卡不動 DB（`db_scope=read`）。該純函式
  （`pre_scores_from_events`）已於 ML-WP-VAL-RESAMPLE1 上抽至
  `models/winprob_val`，本模組以別名 re-export；消費者不只本路由，還有
  WP 評估 harness，而 models 不得 import api。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.db import conn

# 解算器已上抽 models/winprob_scorer（models 不得 import api，而 pa_facts 的關鍵打席
# ΔWP 需要同一台機器）。此處以別名 re-export，本路由的既有語意與快取行為不變。
from cpbl.models.winprob_scorer import (  # noqa: F401  （對外別名，勿刪）
    DIST_SOURCE,
    MODEL_SPAN,
    Scorer,
    _dist_cache,
    _solver_cache,
)
from cpbl.models.winprob_scorer import get_scorer as _get_scorer

# 打席前比分的純函式同樣已上抽 models（ML-WP-VAL-RESAMPLE1）：消費者除本路由外還有
# models/winprob_val 的驗證 harness，而 models 不得 import api；留在此處還會構成
# winprob_val → recap → winprob_scorer → winprob_val 迴圈。同一條紅線只能有一份實作
# ——本卡的病灶就是同一語意有兩份讀法。此處以別名 re-export，既有 import 路徑不變。
from cpbl.models.winprob_val import pre_scores_from_events  # noqa: F401  （對外別名，勿刪）

router = APIRouter()

# ---------------------------------------------------------------------------
# wp_reliability metadata（本卡唯一 owner；版本化）
# 事實來源（僅引已 merge 報告，不得美化）：
#   docs/research/GAME-RECAP-WP-VAL1_RESULTS.md（含 FIX1 errata 修正 E scope）
#   docs/research/GAME-RECAP-WP-CAL1_RESULTS.md
# ---------------------------------------------------------------------------
WP_RELIABILITY_SCHEMA_VERSION = "1.0.0"
METHODOLOGY_ANCHOR = "/methodology#winprob"
_EVIDENCE = [
    "docs/research/GAME-RECAP-WP-VAL1_RESULTS.md",
    "docs/research/GAME-RECAP-WP-VAL1-FIX1_ERRATA.md",
    "docs/research/GAME-RECAP-WP-CAL1_RESULTS.md",
]

WP_RELIABILITY_SCOPES: dict[str, dict[str, Any]] = {
    "A": {
        "scope_label": "一軍例行賽",
        "status": "unsupported",
        "distribution_source": "own",
        "borrowed_from": None,
        "validation": (
            "時間外 walk-forward 驗證（2021–2026 池化 1,826 場／138,949 打席）unsupported："
            "低十分位（落後中的主隊）系統性高估 +4.2~+6.0pt、十分位 8（領先中的主隊）"
            "低估 −4.3pt，99% game-cluster CI 全數排除 0（VAL1 §0/§3.1）"
        ),
        "known_bias": (
            "極端分箱已知偏差 ±4–6pt；辨別力真實（池化 Brier 0.153 vs 主場常數基準 0.245），"
            "失準在校準而非資訊量（VAL1 §0 註）"
        ),
        "remediation": (
            "事後校準層已驗證 No-Go：校準修正不具時間平穩性，會系統性破壞原本"
            "近乎無偏的早局帶（CAL1 §0/§5）；偏差屬長期存在"
        ),
    },
    "C": {
        "scope_label": "一軍總冠軍賽",
        "status": "unsupported",
        "distribution_source": "borrowed",
        "borrowed_from": "A",
        "validation": (
            "分布借自一軍例行（A），未獨立驗證：代理池化 ECE 0.110 > 0.05、全期僅 25 場；"
            "季後主隊指定與種子強度掛鉤，中性隊伍＋主場優勢假設方向性失效（VAL1 §3.3）"
        ),
        "known_bias": (
            "已知系統性混淆：2025 年 5 場主隊實際勝率權重僅 0.18，模型預測 ~0.44–0.49"
            "（VAL1 §3.3）"
        ),
    },
    "D": {
        "scope_label": "二軍例行賽",
        "status": "unsupported",
        "distribution_source": "own",
        "borrowed_from": None,
        "validation": (
            "自身分布 walk-forward 驗證 unsupported：池化十分位 2 偏差 +4.7pt 顯著超界；"
            "二軍主場結構逐年不穩（主隊勝率滑向 ~0.50）使跨年分布聚合失真（VAL1 §3.2）"
        ),
        "known_bias": "主場優勢逐年漂移；生產目前無 D 分布 artifact，本 API 回 model_not_built",
    },
    "E": {
        "scope_label": "一軍季後挑戰賽",
        "status": "unsupported",
        "distribution_source": "borrowed",
        "borrowed_from": "A",
        "validation": (
            "分布借自一軍例行（A），未獨立驗證：池化 ECE 0.085 > 0.05、"
            "E2025 Brier 0.289 輸給主場常數基準 0.253、全期僅 13 場（VAL1-FIX1 §2）"
        ),
        "known_bias": "樣本極小（單季 3–5 場），統計檢定力永遠不足以逐季驗證（VAL1 §3.3 同理）",
    },
}


def wp_reliability(kind_code: str) -> dict[str, Any]:
    """該 scope 的版本化 reliability 揭露；未來任一 scope 通過重新驗證，
    僅翻升該 scope 的 status（consumer 無 breaking change）。"""
    return {
        "schema_version": WP_RELIABILITY_SCHEMA_VERSION,
        "semantics": "reference",  # 參考資訊，非 canonical 歸因
        "scope": kind_code,
        **WP_RELIABILITY_SCOPES[kind_code],
        "methodology": METHODOLOGY_ANCHOR,
        "evidence": _EVIDENCE,
    }


# ---------------------------------------------------------------------------
# 純核心：canonical PA rows → WP/WPA items
# ---------------------------------------------------------------------------
_PRE_REQUIRED = ("inning", "half", "outs", "home_score", "away_score")


def _pre_complete(pre: dict) -> bool:
    return all(pre.get(f) is not None for f in _PRE_REQUIRED)


def _score_pre(scorer: Scorer, pre: dict) -> float:
    bs = pre.get("bases") or []
    bases = (("1" if "1" in bs else "_") + ("2" if "2" in bs else "_")
             + ("3" if "3" in bs else "_"))
    return scorer(int(pre["inning"]), str(pre["half"]),
                  int(pre["home_score"]) - int(pre["away_score"]), bases, int(pre["outs"]))


def _pre_view(row: dict, pre_scores: dict[int, tuple[int, int]]) -> dict | None:
    """canonical ``pre_state`` × 事件流打席前比分 → WP 用的打席前局面。

    回 ``None``＝比分無法由事件流解出（fail closed）。局面欄（inning／half／outs／
    bases）仍取 canonical，只有比分改由事件流供給。
    """
    resolved = pre_scores.get(row["pa_index"])
    if resolved is None:
        return None
    pre = dict(row.get("pre_state") or {})
    pre["away_score"], pre["home_score"] = resolved
    return pre


def _base_item(row: dict, pre: dict | None) -> dict:
    """逐列引用 PA1 契約欄位（spec §8.1），不重建、不改寫。

    ``away_score_before``／``home_score_before`` 例外：改由 ``pre`` （事件流解出的打席前
    比分）供給，未解出時誠實回 ``None``，不退回 ``pre_state`` 的事件後值。
    """
    raw = row.get("pre_state") or {}
    return {
        "pa_id": row["pa_id"],
        "pa_index": row["pa_index"],
        "state": row["state"],
        "inning": raw.get("inning"),
        "half": raw.get("half"),
        "outs_before": raw.get("outs"),
        "bases_before": raw.get("bases") or [],
        "away_score_before": None if pre is None else pre.get("away_score"),
        "home_score_before": None if pre is None else pre.get("home_score"),
        "hitter": row.get("hitter_acnt"),
        "start_pitcher": row.get("start_pitcher_acnt"),
        "end_pitcher": row.get("end_pitcher_acnt"),
        "result": row.get("result_action"),
        "outcome_family": row.get("outcome_family"),
    }


def _unavailable(reason: str) -> dict:
    return {"home_wp_before": None, "home_wp_after": None, "wpa": None,
            "beneficiary_team": None, "wp_status": "unavailable",
            "wp_unavailable_reason": reason}


def _partial(before: float, reason: str) -> dict:
    return {"home_wp_before": before, "home_wp_after": None, "wpa": None,
            "beneficiary_team": None, "wp_status": "partial",
            "wp_unavailable_reason": reason}


def _wp_fields(row: dict, pre: dict | None, nxt: tuple[dict, dict | None] | None,
               completed: bool, final_outcome: float | None,
               scorer: Scorer | None) -> dict:
    """``pre``＝本打席解出的打席前局面（None＝比分未解出）；``nxt``＝下一個真實打席的
    ``(row, pre_view)``（None＝本打席是最後一個真實打席）。"""
    if scorer is None:
        return _unavailable("model_not_built")
    if row["state"] == "non_pa":
        return _unavailable("non_pa_context")  # 突破僵局佈局列：context，不進 PA 分母
    if row["state"] != "ready":
        return _unavailable(f"pa_state_{row['state']}")  # fail closed（truncated/unreliable/…）
    if pre is None:
        # 事件流對不回 start_event_no → 不以 pre_state 的事件後比分冒充
        return _unavailable("pre_score_unresolved")
    if not _pre_complete(pre):
        return _unavailable("pre_state_incomplete")
    before = round(_score_pre(scorer, pre), 4)
    if nxt is None:  # 最後一個真實打席 → 收斂到終場結果（含再見、和局）
        if not completed or final_outcome is None:
            return _partial(before, "final_unknown")
        after = final_outcome
    else:
        _nrow, npre = nxt
        if npre is None:
            return _partial(before, "next_pa_score_unresolved")
        if not _pre_complete(npre):
            return _partial(before, "next_pa_state_incomplete")
        after = round(_score_pre(scorer, npre), 4)
    wpa = round(after - before, 4)  # 主隊視角；以回傳的捨入值相減，consumer 可逐位核驗
    beneficiary = "home" if wpa > 0 else ("away" if wpa < 0 else None)
    return {"home_wp_before": before, "home_wp_after": after, "wpa": wpa,
            "beneficiary_team": beneficiary, "wp_status": "available",
            "wp_unavailable_reason": None}


def enrich_items(pa_rows: list[dict], *, pre_scores: dict[int, tuple[int, int]],
                 completed: bool, final_outcome: float | None,
                 scorer: Scorer | None) -> list[dict]:
    """canonical PA rows（published build）→ 依 pa_index 全序的 WP/WPA items。

    after 錨點 = 下一個真實 PA（state != non_pa）的打席前局面：non_pa 佈局列的
    快照在突破僵局跑者佈局前（bases 恆空），作錨點會低估延長局開局狀態，故跳過；
    換局由下一半局首打席自然銜接，無需特例。

    ``pre_scores``（``pa_index`` → 打席前 ``(away, home)``，由
    :func:`pre_scores_from_events` 產生）是**必填**：比分是 WP 的主要輸入，讓它有
    預設值等同替「悄悄退回 pre_state」留後門，而那正是本卡要修掉的病灶。
    """
    rows = sorted(pa_rows, key=lambda r: r["pa_index"])
    pre_by_index: dict[int, dict | None] = {r["pa_index"]: _pre_view(r, pre_scores) for r in rows}
    real = [r for r in rows if r["state"] != "non_pa"]
    next_real: dict[int, tuple[dict, dict | None] | None] = {}
    for idx, r in enumerate(real):
        nxt = real[idx + 1] if idx + 1 < len(real) else None
        next_real[r["pa_index"]] = None if nxt is None else (nxt, pre_by_index[nxt["pa_index"]])
    items = []
    for r in rows:
        pre = pre_by_index[r["pa_index"]]
        it = _base_item(r, pre)
        it.update(_wp_fields(r, pre, next_real.get(r["pa_index"]), completed,
                             final_outcome, scorer))
        items.append(it)
    return items


# ---------------------------------------------------------------------------
# DB adapter（唯讀；測試以 monkeypatch 置換）
# ---------------------------------------------------------------------------
def _load_game_row(season: int, kind_code: str, game_sno: int) -> dict | None:
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT home_score, away_score, "
            "(coalesce(home_score,0) + coalesce(away_score,0) > 0 "
            " AND game_date <= CURRENT_DATE) AS completed "
            "FROM cpbl.games WHERE year=%s AND kind_code=%s AND game_sno=%s",
            (season, kind_code, game_sno))
        row = cur.fetchone()
    if not row:
        return None
    return {"home_score": row[0], "away_score": row[1], "completed": bool(row[2])}


def _load_pa_rows(season: int, kind_code: str, game_sno: int) -> list[dict]:
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT pa.pa_id::text AS pa_id, pa.pa_index, pa.state, pa.hitter_acnt, "
            "pa.start_pitcher_acnt, pa.end_pitcher_acnt, pa.result_action, "
            "pa.outcome_family, pa.pre_state, pa.start_event_no "
            "FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id "
            "  AND b.state = 'published' "
            "WHERE pa.year=%s AND pa.kind_code=%s AND pa.game_sno=%s "
            "ORDER BY pa.pa_index",
            (season, kind_code, game_sno))
        return _dicts(cur)


def _load_livelog_scores(season: int, kind_code: str, game_sno: int) -> list[dict]:
    """打席前比分的來源事件流（**全場逐事件**，不可只取 PA 起始列）。

    ``annotate_scores`` 是 running 比分，必須看過每一列才能算出任一事件的「之前」值；
    只取起始列會漏掉打席之間造成得分的事件（盜壘／暴投等）。
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT main_event_no, visiting_score, home_score FROM cpbl.game_livelog "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s",
            (season, kind_code, game_sno))
        return _dicts(cur)


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------
@router.get("/api/v1/games/{game_sno}/recap-wp")
def game_recap_wp(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E|D)$"),
) -> dict:
    """逐打席 WP／WPA（參考資訊）：只消費 GAME-RECAP-PA1 canonical 打席。

    每個可靠打席回傳 pa_id、home_wp_before/after、wpa（主隊視角）與受益隊；
    不可靠打席 fail closed（保留事件列、WP 欄不可用並附原因）。全 scope 驗證
    結論 unsupported → response 附版本化 wp_reliability 揭露，前端顯示須標
    「參考」並連 /methodology（UX 卡職責）。

    ``away_score_before``／``home_score_before`` 取自 livelog 事件流的打席前快照，
    與 ``/api/v1/games/{sno}/facts`` 的 ``plate_appearances`` 逐打席一致
    （DATA-RECAP-WP-PRESTATE1；解不出時該打席回 ``pre_score_unresolved``）。
    """
    game = _load_game_row(season, kind_code, game_sno)
    rows = _load_pa_rows(season, kind_code, game_sno)
    if game is None and not rows:
        raise HTTPException(status_code=404, detail="查無此場次")
    completed = bool(game and game["completed"])
    final = None
    final_outcome: float | None = None
    if game is not None:
        final = {"home_score": game["home_score"], "away_score": game["away_score"]}
        if completed:
            hs, aw = game["home_score"] or 0, game["away_score"] or 0
            final_outcome = 1.0 if hs > aw else (0.0 if hs < aw else 0.5)
            final["result"] = ("home_win" if hs > aw
                               else "away_win" if hs < aw else "tie")
    scorer, model = _get_scorer(kind_code, season)
    # 打席前比分走事件流（不讀 pre_state 的事件後值）；無 canonical 打席時免打 livelog。
    pre_scores = (pre_scores_from_events(rows, _load_livelog_scores(season, kind_code, game_sno))
                  if rows else {})
    items = enrich_items(rows, pre_scores=pre_scores, completed=completed,
                         final_outcome=final_outcome, scorer=scorer)
    return {
        "season": season,
        "kind_code": kind_code,
        "game_sno": game_sno,
        "completed": completed,
        "final": final,
        "build_published": bool(rows),
        "model": model,
        "wp_reliability": wp_reliability(kind_code),
        "items": items,
    }
