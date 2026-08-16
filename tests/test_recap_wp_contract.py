"""GAME-RECAP-WP-API1 contract 紅燈＋API 測試（無 DB 依賴）。

紅燈核心：新 recap-wp API 必須**只消費 GAME-RECAP-PA1 canonical 打席**
（cpbl.game_plate_appearances），不得沿用 /winprob 的近似分組——
`(inning, half, batting_order, hitter)` 去重會把「同半局同打者二度上場」
（打線輪轉）合併成一個打席。本檔以合成事件流證明兩種分組產生不同打席數，
並以 contract 測試釘住新 API 回傳 canonical 打席數（近似分組實作必紅）。
"""

from __future__ import annotations

import ast
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cpbl.api.routers import recap
from cpbl.ingest.pa_build import load_taxonomy, plate_appearances

TAX = load_taxonomy()

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs/research/ML-WP-VERDICT-ROBUST1/verdict_metrics.json"
SUPERSEDED = ROOT / "docs/research/game_recap_wp_val1_metrics.json"
METHODOLOGY = ROOT / "web/src/lib/methodology-content.ts"
PA_FACTS = ROOT / "src/cpbl/models/pa_facts.py"


# ---------------------------------------------------------------------------
# 合成事件流：同半局同打者（同 batting_order）二度上場
# ---------------------------------------------------------------------------
def ev(
    no: int, hitter: str | None, *, inning: int = 1, half: str = "1", pitcher: str = "P1",
    pitch_cnt: int | None = None, action: str = "", change: bool = False,
    is_strike: bool = False, is_ball: bool = False, out: int = 0,
    order: int = 1, away: int = 0, home: int = 0,
) -> dict:
    return {
        "year": 2026, "kind_code": "A", "game_sno": 1,
        "main_event_no": f"{no:010d}",
        "inning_seq": inning, "visiting_home_type": half,
        "hitter_acnt": hitter, "pitcher_acnt": pitcher, "pitch_cnt": pitch_cnt,
        "action_name": action, "batting_action_name": "", "content": "",
        "is_strike": is_strike, "is_ball": is_ball, "is_score": False,
        "is_change_player": change, "is_special_event": False,
        "out_cnt": out, "ball_cnt": 0, "strike_cnt": 0,
        "first_base": None, "second_base": None, "third_base": None,
        "visiting_score": away, "home_score": home, "batting_order": order,
    }


# 一上：H1 安打 → H2 安打 → H1（同 batting_order=1，輪轉後二度上場）三振
REPEAT_BATTER_EVENTS = [
    ev(1, "H1", action="一壘安打", pitch_cnt=1, is_strike=True, order=1),
    ev(2, "H2", action="一壘安打", pitch_cnt=2, is_strike=True, order=2),
    ev(3, "H1", action="三振", pitch_cnt=3, is_strike=True, order=1),
    # 一下：主隊一個打席（讓比賽有下半局）
    ev(4, "B1", half="2", pitcher="P2", action="三振", pitch_cnt=1, is_strike=True, order=1),
]


def _legacy_pa_points(events: list[dict]) -> list[tuple]:
    """逐行複刻 routers/games.py `game_winprob` 的近似去重（紅燈對照基準）。"""
    items, seen = [], set()
    for e in sorted(events, key=lambda r: int(r["main_event_no"])):
        if e.get("is_change_player") or not e.get("hitter_acnt"):
            continue
        pa_key = (e["inning_seq"], str(e["visiting_home_type"]),
                  e.get("batting_order"), e["hitter_acnt"])
        if pa_key in seen:
            continue
        seen.add(pa_key)
        items.append(pa_key)
    return items


def _canonical_rows(events: list[dict]) -> list[dict]:
    """合成事件 → canonical PA rows（模擬 published build 的 DB 列）。"""
    return [{
        "pa_id": str(p.pa_id), "pa_index": p.pa_index, "state": p.state,
        "hitter_acnt": p.hitter_acnt, "start_pitcher_acnt": p.start_pitcher_acnt,
        "end_pitcher_acnt": p.end_pitcher_acnt, "result_action": p.result_action,
        "outcome_family": p.outcome_family, "pre_state": p.pre_state,
        "start_event_no": p.start_event_no,
    } for p in plate_appearances(2026, "A", 1, events, TAX)]


def _livelog_scores(events: list[dict]) -> list[dict]:
    """DB adapter ``_load_livelog_scores`` 的回傳形狀（只有比分解算需要的三欄）。"""
    return [{"main_event_no": e["main_event_no"], "visiting_score": e["visiting_score"],
             "home_score": e["home_score"]} for e in events]


# 最小 run_dist：只需上/下半局空壘 0 出局分布（其餘狀態 fallback）
DIST = {
    ("1", "___", 0): [0.7, 0.15, 0.08, 0.04, 0.02, 0.01, 0.0],
    ("2", "___", 0): [0.65, 0.17, 0.1, 0.05, 0.02, 0.01, 0.0],
}


def test_legacy_grouping_merges_repeat_batter() -> None:
    """近似分組缺陷實證：同半局同打者二度上場被合併（3 個真實打席只剩 2 點）。"""
    legacy = [k for k in _legacy_pa_points(REPEAT_BATTER_EVENTS) if k[1] == "1"]
    assert len(legacy) == 2  # H1 第二打席被去重吃掉
    canonical = [r for r in _canonical_rows(REPEAT_BATTER_EVENTS)
                 if r["state"] == "ready" and r["pre_state"]["half"] == "1"]
    assert len(canonical) == 3
    assert [r["hitter_acnt"] for r in canonical] == ["H1", "H2", "H1"]


# ---------------------------------------------------------------------------
# API contract（monkeypatch DB adapter；不碰真 DB）
# ---------------------------------------------------------------------------
@pytest.fixture()
def recap_module(monkeypatch):
    from cpbl.api.routers import recap
    from cpbl.models import winprob_scorer

    # 解算器住在 models/winprob_scorer（recap 以別名 re-export）→ 分布載入的
    # monkeypatch 必須打在該模組上，否則會靜默去讀真的 artifact。
    winprob_scorer._dist_cache.clear()
    winprob_scorer._solver_cache.clear()
    monkeypatch.setattr(winprob_scorer, "_load_dist", lambda span, kind: dict(DIST))
    yield recap
    winprob_scorer._dist_cache.clear()
    winprob_scorer._solver_cache.clear()


def _get(recap, monkeypatch, rows, game, events=REPEAT_BATTER_EVENTS, **params):
    from cpbl.api.main import app

    monkeypatch.setattr(recap, "_load_pa_rows", lambda season, kind, sno: rows)
    monkeypatch.setattr(recap, "_load_game_row", lambda season, kind, sno: game)
    monkeypatch.setattr(recap, "_load_livelog_scores",
                        lambda season, kind, sno: _livelog_scores(events))
    q = {"season": 2026, "kind_code": "A", **params}
    return TestClient(app).get("/api/v1/games/1/recap-wp", params=q)


def test_recap_api_returns_canonical_pa_not_legacy_grouping(recap_module, monkeypatch) -> None:
    """紅燈 contract：API 打席數 = canonical PA 數（近似分組實作在此必紅）。"""
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    resp = _get(recap_module, monkeypatch, rows, game)
    assert resp.status_code == 200
    body = resp.json()
    items = body["items"]
    # canonical：4 個打席（一上 3 + 一下 1），近似分組只會給 3
    assert len(items) == 4
    assert len(items) != len(_legacy_pa_points(REPEAT_BATTER_EVENTS))
    top = [i for i in items if i["half"] == "1" and i["inning"] == 1]
    assert [i["hitter"] for i in top] == ["H1", "H2", "H1"]
    # pa_id 全部相異且穩定（UUIDv5 canonical 身分）
    assert len({i["pa_id"] for i in items}) == 4
    assert body["completed"] is True
    # 逐列引用 PA1 契約欄位（不重建）：與 DB 列逐一對齊
    for it, r in zip(items, rows, strict=True):
        assert it["pa_id"] == r["pa_id"]
        assert it["state"] == r["state"]
        assert it["result"] == r["result_action"]


def test_recap_api_response_shape_and_model_metadata(recap_module, monkeypatch) -> None:
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    body = _get(recap_module, monkeypatch, rows, game).json()
    assert {"season", "kind_code", "game_sno", "completed", "final", "build_published",
            "model", "wp_reliability", "items"} <= set(body)
    m = body["model"]
    assert m["model_span"] == "2018-2025"
    assert m["model_kind"] == "A"
    assert m["distribution_source"] == "own"
    assert "model_built_at" in m  # run_dist artifact 無時戳欄位 → 誠實回 null
    assert m["model_built_at"] is None
    it = body["items"][0]
    assert {"pa_id", "pa_index", "state", "inning", "half", "outs_before", "bases_before",
            "away_score_before", "home_score_before", "hitter", "start_pitcher",
            "end_pitcher", "result", "outcome_family", "home_wp_before", "home_wp_after",
            "wpa", "beneficiary_team", "wp_status", "wp_unavailable_reason"} <= set(it)
    assert body["final"] == {"home_score": 0, "away_score": 1, "result": "away_win"}


def test_recap_api_ruleset_follows_kind_and_season(recap_module, monkeypatch) -> None:
    """延長規則參數化：2023 無突破僵局、2024+ tb10；C/E 無和局。"""
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    m23 = _get(recap_module, monkeypatch, rows, game, season=2023).json()["model"]
    m24 = _get(recap_module, monkeypatch, rows, game, season=2024).json()["model"]
    assert m23["ruleset"] == "cap12,tie"
    assert m24["ruleset"] == "cap12,tb10,tie"
    mc = _get(recap_module, monkeypatch, rows, game, kind_code="C").json()["model"]
    assert mc["ruleset"] == "cap20,no-tie"
    assert mc["model_kind"] == "A"
    assert mc["distribution_source"] == "borrowed"


def test_recap_api_model_not_built_fails_closed(recap_module, monkeypatch) -> None:
    """D scope（生產無自身分布 artifact）：保留事件列，WP 全欄不可用。"""
    from cpbl.models import winprob_scorer

    def raise_missing(span, kind):
        raise RuntimeError(f"run_dist 無 {span}/{kind}")
    monkeypatch.setattr(winprob_scorer, "_load_dist", raise_missing)
    rows = _canonical_rows(REPEAT_BATTER_EVENTS)
    game = {"home_score": 0, "away_score": 1, "completed": True}
    body = _get(recap_module, monkeypatch, rows, game, kind_code="D").json()
    assert body["model"] is None
    assert len(body["items"]) == 4  # 事件列保留
    assert all(i["wp_status"] == "unavailable" for i in body["items"])
    assert all(i["wp_unavailable_reason"] == "model_not_built" for i in body["items"])
    assert all(i["home_wp_before"] is None for i in body["items"])


def test_recap_api_unknown_game_404(recap_module, monkeypatch) -> None:
    resp = _get(recap_module, monkeypatch, [], None)
    assert resp.status_code == 404


def test_recap_api_no_published_build(recap_module, monkeypatch) -> None:
    """games 有列但無 published build：不猜、items 空、build_published=false。"""
    game = {"home_score": 3, "away_score": 1, "completed": True}
    body = _get(recap_module, monkeypatch, [], game).json()
    assert body["build_published"] is False
    assert body["items"] == []


# ---------------------------------------------------------------------------
# WP-DISCLOSURE-SYNC1：對外揭露 ↔ 來源 artifact 的逐位比對器
#
# 本卡治的病：方法頁的 version 欄逐字宣稱「數字逐位對應 game_recap_wp_val1_metrics.json」，
# 但那份 artifact 的 E scope 是 pre-FIX1、打席前比分走已知受污染的讀法、判定是 v2 規則
# ——**對外揭露的數字與它自己指名的證據來源對不上**。
#
# 三條紀律（R1／R2 兩輪查核退回後補強）：
#   1. **本檔不得持有任何分箱 ID 或偏差值的字面**。同一份內容清單先後住過產品碼
#      （ADJUDICATED_BIN_EXCLUSIONS）、測試常數（NAMED_BINS_IN_COPY）、以及核對式裡的
#      `(1, 2, 3)`／`8`——三代都是同一個病：等式有一側是人抄的，它證明的只是「我抄對了」。
#      現在**兩側都從各自的真實來源導出**：對外文字用 :func:`_parse_named_bins` 解析，
#      artifact 用 gates／deciles 現算。
#   2. **每個宣稱綁定到具體欄位**，不做整份 corpus 的 substring 搜尋——數字出現在別的
#      scope 或別的段落也能代打，那種命中不構成該欄位講對了。
#   3. **雙向**：不只斷言「該說的有說」，也斷言「不該說的沒說」（如對帳恢復 match 時，
#      過期的 MISMATCH 警語必須消失）。單向斷言會讓警語永遠留在頁面上。
#
# 唯一保留的字面是**定位錨**（哪一段、哪一句），不是被比對的內容；錨命中數不為 1 即紅。
# ---------------------------------------------------------------------------
_ART = json.loads(ARTIFACT.read_text(encoding="utf-8"))
_SCOPES = _ART["scopes"]
_CN_NUM = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}
_TS_FIELDS = ("kindBadge", "status", "question", "method", "period",
              "baseline", "validation", "limits", "version")
_PCT = r"(?:pt|\s*個百分點)"


def _balanced(src: str, start: int) -> tuple[int, int]:
    """由 `start` 的 `{` 起算平衡括號區塊 [start, end]。"""
    depth = 0
    for end in range(start, len(src)):
        if src[end] == "{":
            depth += 1
        elif src[end] == "}":
            depth -= 1
            if depth == 0:
                return start, end
    raise AssertionError("括號不平衡")


def _methodology_body() -> str:
    """METHODOLOGY_CONTENT 物件本體（排除型別宣告裡的同名 key）。"""
    src = METHODOLOGY.read_text(encoding="utf-8")
    i = src.index("export const METHODOLOGY_CONTENT")
    s, e = _balanced(src, src.index("{", i))
    return src[s:e + 1]


# 段落 key 在 TS 裡**可有引號可無**（無連字號的 key 不需引號）。先前只認有引號的，
# 於是 `pregame`／`winprob` 兩段從未被掃描過——`winprob.limits` 的場數因此一直沒被守到。
# ⚠️ 修法是把辨識規則放寬到兩種寫法（**規則**），不是把漏掉的段名補進一張表（清單）。
_SECTION_RE = re.compile(r'^  ("?)([a-z-]+)\1: \{', re.M)


def _ts_sections() -> list[str]:
    return [m.group(2) for m in _SECTION_RE.finditer(_methodology_body())]


def _ts_section(name: str) -> dict[str, list[str]]:
    """解析 methodology-content.ts 中某一段實際印出的文字（單值欄位亦回 list）。"""
    body = _methodology_body()
    hits = [m for m in _SECTION_RE.finditer(body) if m.group(2) == name]
    assert len(hits) == 1, f"methodology-content.ts 找不到唯一的 {name} 段"
    src = body
    start, end = _balanced(src, src.index("{", hits[0].start()))
    out: dict[str, list[str]] = {}
    field: str | None = None
    for line in src[start:end + 1].splitlines():
        m = re.match(r"\s{4}(\w+):", line)
        if m and m.group(1) in _TS_FIELDS:
            field = m.group(1)
            out.setdefault(field, [])
        if field is not None:
            out[field].extend(re.findall(r'"((?:[^"\\]|\\.)*)"', line))
    return out


def _ts(section: str, field: str, anchor: str | None = None) -> str:
    """取該段某欄位的字串；欄位是陣列時以 anchor 定位唯一那一句。"""
    vals = _ts_section(section)[field]
    if anchor is None:
        assert len(vals) == 1, f"{section}.{field} 有 {len(vals)} 個值，需 anchor 定位"
        return vals[0]
    hits = [v for v in vals if anchor in v]
    assert len(hits) == 1, f"anchor {anchor!r} 在 {section}.{field} 命中 {len(hits)} 次"
    return hits[0]


def _pooled(kind: str) -> dict:
    return _SCOPES[kind]["pooled_walk_forward"]


def _dev_pt(kind: str, bin_id: int) -> float:
    """池化十分位偏差（pred − actual，百分點）。正＝高估主隊勝率。"""
    b = _pooled(kind)["deciles"][bin_id]
    return round((b["pred"] - b["actual"]) * 100, 1)


def _gates(kind: str, gate: str, decision: str) -> list[dict]:
    return [g for g in _SCOPES[kind]["verdict"]["gates"]
            if g["gate"] == gate and g["decision"] == decision]


def _failed_bins(kind: str) -> dict[int, float]:
    """artifact 判「顯著且超界」的分箱 → 其偏差（百分點）。這是等式的 artifact 側。"""
    return {g["bin"]: _dev_pt(kind, g["bin"])
            for g in _gates(kind, "pooled_bin_dev", "fail")}


def _bound_pt() -> float:
    """預先註冊的分箱偏差上限（百分點），由 artifact 的 thresholds 現算。"""
    return round(_ART["thresholds"]["pooled_bin_dev_max"] * 100, 1)


def _detail_field(detail: str, key: str) -> str:
    m = re.search(rf"{key}=([0-9.]+)", detail)
    assert m, f"閘門 detail 找不到 {key}：{detail}"
    return m.group(1)


def _dev_str(dev: float) -> str:
    """對外文字的偏差寫法（全形負號、一位小數）。"""
    return f"{'+' if dev > 0 else '−'}{abs(dev)}"


def _parse_named_bins(text: str) -> dict[int, str]:
    """從**任一段對外文字**解析「十分位 N（可 N／N／N）… ±X（pt|個百分點）」的宣稱。

    同一支解析器同時用於 recap.py 與 methodology-content.ts——本檔因此不需要（也不允許）
    持有任何分箱清單。「低十分位」這類沒帶數字的泛稱不會被誤抓（regex 要求空白後接數字）。
    """
    out: dict[int, str] = {}
    for m in re.finditer(r"十分位 ([0-9／]+)", text):
        bins = [int(b) for b in m.group(1).split("／")]
        vm = re.search(rf"([+−][0-9.]+(?:／[+−][0-9.]+)*){_PCT}", text[m.end():m.end() + 60])
        if vm is None:
            continue
        devs = vm.group(1).split("／")
        assert len(bins) == len(devs), (
            f"文字裡分箱數 {len(bins)} 與偏差數 {len(devs)} 不等：{text[m.start():m.end() + 60]!r}"
        )
        for b, d in zip(bins, devs, strict=True):
            assert b not in out, f"十分位 {b} 在同一段文字出現兩次"
            out[b] = d
    return out


def _parse_bounds(text: str) -> list[float]:
    """解析「±N pt／個百分點」形式的上限宣稱（「±4–6pt」這種約數摘要不會被抓到）。"""
    return [float(x) for x in re.findall(rf"±([0-9.]+){_PCT}", text)]


def _claims() -> list[tuple[str, str, str, str]]:
    """(欄位定位, 宣稱, 由 artifact 現算的期望字串, 該欄位的實際文字)。

    ⚠️ 第 4 欄是**單一欄位**的字，不是整份檔案——數字出現在別處不算命中。
    """
    rows: list[tuple[str, str, str, str]] = []

    def api(kind: str, field: str, label: str, needle: str) -> None:
        rows.append((f"recap.py {kind}.{field}", label, needle,
                     recap.WP_RELIABILITY_SCOPES[kind][field]))

    def web(field: str, anchor: str | None, label: str, needle: str,
            section: str = "winprob-validation") -> None:
        rows.append((f"{section}.{field}", label, needle, _ts(section, field, anchor)))

    a = _pooled("A")
    a_fail = _failed_bins("A")
    over = sorted(d for d in a_fail.values() if d > 0)
    api("A", "validation", "A 母體場數", f"{a['n_games']:,} 場")
    api("A", "validation", "A 母體打席", f"{a['n_pa']:,} 打席")
    # 高估區間的上下界由 artifact 的 fail 分箱正偏差現算——不得寫死分箱編號
    api("A", "validation", "A 高估區間", f"+{over[0]}~+{over[-1]}pt")
    api("A", "validation", "資料 as-of", recap.WP_EVIDENCE_AS_OF)
    api("A", "known_bias", "A 池化 Brier", f"{a['brier']:.3f}")
    api("A", "known_bias", "A 主場常數基準", f"{a['baseline_home_const_brier']:.3f}")
    for kind in ("C", "E"):
        p = _pooled(kind)
        api(kind, "validation", f"{kind} 場數", f"{p['n_games']} 場")
        api(kind, "validation", f"{kind} 池化 Brier", f"{p['brier']:.3f}")
        api(kind, "validation", f"{kind} 主場常數基準", f"{p['baseline_home_const_brier']:.3f}")
        api(kind, "validation", f"{kind} 池化 ECE", f"{p['ece_weighted']:.3f}")
    e2025 = next(s for s in _SCOPES["E"]["seasons"] if s["year"] == 2025)
    api("E", "validation", "E2025 Brier", f"{e2025['walk_forward']['brier']:.3f}")
    api("E", "validation", "E2025 主場基準", f"{e2025['baseline_home_const']['brier']:.3f}")
    d_detail = _gates("D", "pooled_bin_dev", "fail")[0]["detail"]
    api("D", "validation", "D 重抽次數", f"{int(_detail_field(d_detail, 'reps')):,} 次")
    # p_one 原值落在捨入半點上：文案沿用 ROBUST1 §6-P2 的四捨五入寫法，而 Python format
    # 的銀行家捨入會少一個位——此處明示 ROUND_HALF_UP 對齊人寫的報告（呈現層契約）。
    p_one = Decimal(_detail_field(d_detail, "p_one")).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    api("D", "validation", "D p_one", f"p_one={p_one}")

    web("method", "逐季時間走查", "A 母體場數", f"{a['n_games']:,} 場")
    web("method", "逐季時間走查", "A 母體打席", f"{a['n_pa']:,} 個打席")
    web("method", "逐季時間走查", "資料 as-of", recap.WP_EVIDENCE_AS_OF)
    web("baseline", None, "A 主場常數基準", f"{a['baseline_home_const_brier']:.3f}")
    web("limits", "季後賽與二軍同樣完成時間外驗證", "C 池化 Brier", f"{_pooled('C')['brier']:.3f}")
    web("limits", "季後賽與二軍同樣完成時間外驗證", "C 主場常數基準",
        f"{_pooled('C')['baseline_home_const_brier']:.3f}")
    web("limits", "季後賽與二軍同樣完成時間外驗證", "E 池化 Brier", f"{_pooled('E')['brier']:.3f}")
    web("limits", "季後賽與二軍同樣完成時間外驗證", "E 主場常數基準",
        f"{_pooled('E')['baseline_home_const_brier']:.3f}")
    web("version", None, "事實來源檔名", ARTIFACT.name)
    web("version", None, "資料 as-of", recap.WP_EVIDENCE_AS_OF)
    web("validation", "為什麼序數用法站得住", "A 池化 Brier", f"{a['brier']:.3f}",
        section="key-plays")
    web("validation", "為什麼序數用法站得住", "A 主場常數基準",
        f"{a['baseline_home_const_brier']:.3f}", section="key-plays")
    return rows


def test_disclosure_numbers_match_artifact_digit_for_digit(capsys) -> None:
    """驗收條件 5：「數字逐位對應該 artifact」這句宣稱必須由指令重新驗證。"""
    rows = _claims()
    misses = []
    with capsys.disabled():
        print(f"\n=== 對外揭露 ↔ {ARTIFACT.name}（as-of {recap.WP_EVIDENCE_AS_OF}）逐欄位比對 ===")
        for locus, label, needle, text in rows:
            ok = needle in text
            if not ok:
                misses.append((locus, label, needle))
            print(f"  [{'OK ' if ok else 'MISS'}] {locus:34s} {label:16s} → {needle!r}")
        print(f"  --- {len(rows) - len(misses)}/{len(rows)} 命中（皆為欄位內命中）---")
    assert not misses, f"揭露面與 artifact 對不上：{misses}"


def test_registered_bound_matches_the_artifact_threshold() -> None:
    """對外講的「±N 上限」必須等於 artifact 的 thresholds，不得寫死。"""
    bound = _bound_pt()
    for locus, text in (
        ("recap.py D.validation", recap.WP_RELIABILITY_SCOPES["D"]["validation"]),
        ("winprob-validation.validation[S 型]",
         _ts("winprob-validation", "validation", "偏差呈 S 型結構")),
    ):
        found = _parse_bounds(text)
        assert found, f"{locus} 沒有解析出任何「±N」上限宣稱"
        for v in found:
            assert v == bound, f"{locus} 寫 ±{v}，artifact thresholds 為 ±{bound}"


def test_public_status_matches_the_machine_verdict_with_no_override_table() -> None:
    """對外 status 必須與 artifact 的機器判定**逐 scope 相同**（零人工覆寫表）。"""
    assert set(recap.WP_RELIABILITY_SCOPES) == set(_SCOPES), "揭露的 scope 集合與 artifact 不符"
    for kind, scope in recap.WP_RELIABILITY_SCOPES.items():
        assert scope["status"] == _SCOPES[kind]["verdict"]["status"], (
            f"{kind} scope 對外 {scope['status']!r} 與機器判定 "
            f"{_SCOPES[kind]['verdict']['status']!r} 不符"
        )


def test_insufficient_label_is_derived_from_gate_sources_and_fails_closed() -> None:
    """「測不了」的對外說法必須由**閘門來源**決定，且未映射的來源一律紅。"""
    for kind, scope in recap.WP_RELIABILITY_SCOPES.items():
        if scope["status"] != recap.STATUS_INSUFFICIENT:
            continue
        sources = {(g["gate"], g["decision"])
                   for g in _SCOPES[kind]["verdict"]["gates"]
                   if g["decision"] in ("undetermined", "unreachable")}
        assert sources, f"{kind} 判 insufficient 卻沒有任何 undetermined／unreachable 閘門"
        unmapped = sources - set(recap.INSUFFICIENT_SOURCE_LABELS)
        assert not unmapped, (
            f"{kind} scope 出現未映射的「測不了」來源 {sorted(unmapped)}——"
            "須先決定它的對外說法（fail-closed，不得靜默沿用「樣本不足」）"
        )
        labels = {recap.INSUFFICIENT_SOURCE_LABELS[s] for s in sources}
        assert scope["status_label"] in labels, (
            f"{kind} scope 標示 {scope['status_label']!r}，但其閘門來源對應的說法是 {labels}"
        )
        assert len(labels) == 1, (
            f"{kind} scope 同時有 {labels} 兩類來源，單一 status_label 會漏講一種"
        )


def test_counting_machine_disclosure_tracks_the_artifact_both_ways() -> None:
    """對帳狀態的揭露必須**雙向**跟著 artifact 走。

    MISMATCH＝此研究快照重建的分布與目前生產 run_dist 分岔（RESAMPLE1 §6-F5，射程外），
    **不是**這份 artifact 的量測或 v3 判定壞掉；少了這句，讀者會誤讀成後者。
    反過來，對帳恢復 match 時**過期的警語必須消失**——只斷言「這句在不在」是單向的，
    會讓警語永遠留在頁面上（R2-02）。
    """
    status = _ART["counting_machine_check"]["status"]
    version = _ts("winprob-validation", "version")
    known = {"match", "MISMATCH"}
    assert status in known, f"未知的對帳狀態 {status!r}，須先決定它的對外說法"
    assert status in version, f"artifact 對帳為 {status}，version 欄未揭露"
    for other in known - {status}:
        assert other not in version, (
            f"artifact 對帳為 {status}，version 欄卻仍出現 {other!r}——過期警語未清掉"
        )
    explain = ("生產" in version and "run_dist" in version
               and ("不表示" in version or "不是" in version))
    if status == "match":
        assert not explain, "對帳已恢復 match，分岔說明應同步移除"
    else:
        assert explain, "未說明分岔對象是生產 run_dist、且不等於這份 artifact 損壞"


def test_superseded_artifact_is_marked_and_no_longer_cited() -> None:
    """舊 artifact 保留不覆寫（凍結證據），但必須標 superseded 且不再被揭露面引用。"""
    old = json.loads(SUPERSEDED.read_text(encoding="utf-8"))
    assert old["superseded_by"] == recap.WP_EVIDENCE_ARTIFACT
    assert old["superseded_note"]["measurements_unchanged"] is True
    api = (json.dumps(recap.WP_RELIABILITY_SCOPES, ensure_ascii=False)
           + json.dumps(recap._EVIDENCE, ensure_ascii=False))
    assert "game_recap_wp_val1_metrics.json" not in api, "API 揭露面仍引用已 superseded 的 artifact"
    for i, line in enumerate(METHODOLOGY.read_text(encoding="utf-8").splitlines(), 1):
        if "game_recap_wp_val1_metrics.json" in line:
            assert "superseded" in line, (
                f"methodology-content.ts:{i} 提到舊 artifact 卻未同句標明 superseded"
            )
    assert recap.WP_EVIDENCE_ARTIFACT.endswith("ML-WP-VERDICT-ROBUST1/verdict_metrics.json")


# ---------------------------------------------------------------------------
# coverage universe 由**被查核表面本身導出**（R3 裁定：登記 → 掃描）
#
# 前四代硬編清單依序住在：產品碼常數 ADJUDICATED_BIN_EXCLUSIONS → 測試常數
# NAMED_BINS_IN_COPY → 核對式字面 (1,2,3)／8 → 位置登記表 BIN_CLAIM_LOCI。
# 資料形狀四次都不同，**失敗不變式四次都相同**：人漏一項就 fail-open。
# 掃描漏不掉，因為它不需要人記得任何事。
# ---------------------------------------------------------------------------
def _public_surfaces() -> list[tuple[str, str]]:
    """(定位, 文字)：API 每個 scope 的全部字串欄位 ＋ methodology 全段全欄位全句。"""
    out: list[tuple[str, str]] = []
    for kind, scope in recap.WP_RELIABILITY_SCOPES.items():
        for field, val in scope.items():
            if isinstance(val, str):
                out.append((f"recap.py {kind}.{field}", val))
    for section in _ts_sections():
        for field, vals in _ts_section(section).items():
            for i, v in enumerate(vals):
                out.append((f"{section}.{field}[{i}]", v))
    return out


def _attribute(claim: dict[int, str]) -> str:
    """把一組「分箱→偏差」宣稱歸屬到唯一 scope；歧義或無解一律 fail closed。"""
    hits = [k for k in _SCOPES
            if all(b in _failed_bins(k) and d == _dev_str(_failed_bins(k)[b])
                   for b, d in claim.items())]
    assert hits, f"公開宣稱 {claim} 對不上任何 scope 的超界分箱"
    assert len(hits) == 1, (
        f"公開宣稱 {claim} 同時符合 scope {hits}——歸屬歧義，須先讓句子標明 scope"
    )
    return hits[0]


def test_every_public_bin_claim_matches_the_artifact_and_none_is_missing(capsys) -> None:
    """健全性＋完整性，且 coverage universe 由掃描導出而非人登記。"""
    seen: dict[str, set[int]] = {}
    with capsys.disabled():
        print("\n=== 公開表面掃描（無登記表）===")
        for locus, text in _public_surfaces():
            claim = _parse_named_bins(text)
            if not claim:
                continue
            kind = _attribute(claim)
            print(f"  {locus:38s} → scope {kind}  {claim}")
            seen.setdefault(kind, set()).update(claim)
        for kind in _SCOPES:
            fail = set(_failed_bins(kind))
            if not fail:
                continue
            got = seen.get(kind, set())
            print(f"  [{kind}] 對外合集 {sorted(got)}  artifact fail {sorted(fail)}")
            assert got == fail, (
                f"{kind} scope：artifact 判 fail 的分箱 {sorted(fail)} 與對外合集 "
                f"{sorted(got)} 不符——沒被講到的那些會靜默消失"
            )
    sentence = _ts("winprob-validation", "validation", "偏差呈 S 型結構")
    n = len(_failed_bins("A"))
    assert f"{_CN_NUM[n]}個分箱" in sentence, f"計數詞不是「{_CN_NUM[n]}個分箱」"


def test_scope_attribution_fails_closed_on_ambiguity() -> None:
    """兩 scope 的 (bin, dev) 巧合時必須 fail closed，不得任意挑一個。"""
    real = _failed_bins("D")          # {2: +5.0}
    bin_id, dev = next(iter(real.items()))
    patched = dict(_SCOPES)
    with pytest.raises(AssertionError, match="歸屬歧義"):
        # 造一個與 D 完全同值的假 scope，證明歸屬器不會硬選
        fake = json.loads(json.dumps(_SCOPES["D"]))
        patched["Z"] = fake
        _SCOPES["Z"] = fake
        try:
            _attribute({bin_id: _dev_str(dev)})
        finally:
            del _SCOPES["Z"]
    with pytest.raises(AssertionError, match="對不上任何 scope"):
        _attribute({bin_id: "+99.9"})


# ---------------------------------------------------------------------------
# 前提斷言（R3 裁定第 3 題）：登記散文依賴的**性質**，不是它的值。
#
# 這關掉的是生成式關不掉的那一類——只把數字插值，若 artifact 的超界分箱哪天變成中段，
# 數字全對而「S 型」「這兩端」「翻盤／勝券在握」全部變假，且沒有任何測試會紅。
# 下列不變式一旦不成立，對外那幾句話就必須重寫（而不是改個數字了事）。
# ---------------------------------------------------------------------------
def test_prose_preconditions_still_hold(capsys) -> None:
    a_fail = _failed_bins("A")
    over = sorted(b for b, d in a_fail.items() if d > 0)
    under = sorted(b for b, d in a_fail.items() if d < 0)
    checks: list[tuple[str, bool, str]] = []

    # INV1／INV2「偏差呈 S 型結構」「這兩端」：超界分箱恰分正負兩群、正群索引全小於負群
    checks.append(("S 型且恰兩端（低分箱高估、高分箱低估）",
                   bool(over) and bool(under) and max(over) < min(under),
                   f"正群{over} 負群{under}"))
    # INV3「約 ±4–6pt」：每個超界分箱的幅度四捨五入後落在 4–6
    rounded = {b: int(Decimal(str(abs(d))).quantize(Decimal("1"), ROUND_HALF_UP))
               for b, d in a_fail.items()}
    checks.append(("約數帶 ±4–6pt 仍涵蓋全部超界分箱",
                   all(v in (4, 5, 6) for v in rounded.values()), str(rounded)))
    # INV4「各季方向一致」：每一季在這些分箱的偏差方向與池化同號
    consistent = True
    for s in _SCOPES["A"]["seasons"]:
        dec = s["walk_forward"]["deciles"]
        for b, d in a_fail.items():
            sd = dec[b]["pred"] - dec[b]["actual"]
            consistent &= (sd > 0) == (d > 0)
    checks.append(("各季方向一致", consistent, f"{len(_SCOPES['A']['seasons'])} 季全查"))
    # INV5「辨別力真實」：池化 Brier 勝過主場常數基準
    pa = _pooled("A")
    checks.append(("A 辨別力真實（Brier 勝過主場常數基準）",
                   pa["brier"] < pa["baseline_home_const_brier"],
                   f"{pa['brier']} < {pa['baseline_home_const_brier']}"))
    # INV6「模型其實勝過基準」：C／E 改標「樣本不足」的正當性前提
    for kind in ("C", "E"):
        p = _pooled(kind)
        checks.append((f"{kind} 池化勝過基準（支撐『不是測出不準』）",
                       p["brier"] < p["baseline_home_const_brier"],
                       f"{p['brier']} < {p['baseline_home_const_brier']}"))

    with capsys.disabled():
        print("\n=== 散文前提斷言（性質，非值）===")
        for name, ok, detail in checks:
            print(f"  [{'OK ' if ok else 'FAIL'}] {name:34s} {detail}")
    bad = [n for n, ok, _ in checks if not ok]
    assert not bad, f"對外散文的前提已不成立，該句必須重寫而非改數字：{bad}"


# ---------------------------------------------------------------------------
# 公開場數宣稱：規則導出，不是手挑欄位
#
# R4 實證的天花板：`_claims()` 是**手挑的欄位清單**，沒被挑到的公開數字無人看守。
# `winprob-validation.period` 的「210 完成場」就是活案例——換來源時被留在原地，
# 與同段 method 欄的池化 1,856 場自相矛盾（逐季 2021–25 合計 1,616，+210=1,826 是舊
# artifact 的池化值）。它不是詮釋句、不帶分箱，就是一個沒人守的數字。
#
# 這裡把「場數」這一類從手挑升成規則：掃描全部 WP 對外表面的「N 場」token，
# 單點值必須是 artifact 的合法場數，區間值必須真的框住某 scope 的逐季場數。
# ---------------------------------------------------------------------------
# 管轄權由 **version 欄自己宣告的來源**決定，不是測試裡的段落豁免清單。
# R5 查核指出：先前 `_GAME_COUNT_EXCLUDED_SECTIONS = {"key-plays"}` 是無條件整段豁免，
# 而它宣稱的來源只寫在交付報告裡、沒寫進 version 欄——機械上就是一段沒有依據的豁免。
# 現在改成：ts 段落的場數受本 artifact 檢查，**當且僅當**該段 version 欄指名本 artifact。
# ⚠️ fail closed：有場數宣稱卻沒宣告任何來源的段落一律紅，不得靜默略過。
_GAME_COUNT_RE = re.compile(r"([\d,]+)(?:\s*[–~-]\s*([\d,]+))?\s*(?:完成)?場")


def _artifact_game_counts(kind: str | None = None) -> set[int]:
    scopes = _SCOPES if kind is None else {kind: _SCOPES[kind]}
    out: set[int] = set()
    for sc in scopes.values():
        out.add(sc["pooled_walk_forward"]["n_games"])
        out.update(s["n_completed_games"] for s in sc["seasons"])
    return out


def _scope_before(text: str, at: int) -> str | None:
    """數字**緊鄰之前**指名的 scope；由 scope_label 現算比對，無或歧義回 None。

    區間宣稱不能靠「哪個 scope 的資料剛好落在區間內」反猜——R5 實測 150–360 同時符合
    A 與 D，改成錯誤的 160–240 仍會假綠。歸屬必須由**文字說了什麼**導出。
    """
    window = text[max(0, at - 30):at]
    hits = {k for k, sc in recap.WP_RELIABILITY_SCOPES.items()
            if any(tok and tok in window
                   for tok in (sc["scope_label"], sc["scope_label"].removeprefix("一軍")))}
    return next(iter(hits)) if len(hits) == 1 else None


def _game_count_surfaces() -> list[tuple[str, str, str | None]]:
    """(定位, 文字, 位置決定的 scope)。ts 段落是否受檢由其 version 欄宣告的來源決定。"""
    out: list[tuple[str, str, str | None]] = []
    for kind, scope in recap.WP_RELIABILITY_SCOPES.items():
        for field, val in scope.items():
            if isinstance(val, str):
                out.append((f"recap.py {kind}.{field}", val, kind))   # 位置即 scope
    for section in _ts_sections():
        fields = _ts_section(section)
        texts = [v for vals in fields.values() for v in vals]
        if not any(_GAME_COUNT_RE.search(v) for v in texts):
            continue
        version = " ".join(fields.get("version", []))
        assert version, f"{section} 段有場數宣稱卻沒有 version 欄宣告來源"
        if ARTIFACT.name not in version:
            continue                                   # 該段自認來源不是本 artifact
        for field, vals in fields.items():
            for i, v in enumerate(vals):
                out.append((f"{section}.{field}[{i}]", v, None))
    return out


def test_every_public_game_count_matches_the_artifact(capsys) -> None:
    """對外講的每個場數都要對得上 artifact；區間值的 scope 由文字導出，不由數值反猜。"""
    bad: list[str] = []
    with capsys.disabled():
        print("\n=== 公開場數宣稱（管轄權由 version 宣告的來源決定）===")
        for loc, text, pos_scope in _game_count_surfaces():
            for m in _GAME_COUNT_RE.finditer(text):
                lo = int(m.group(1).replace(",", ""))
                hi = int(m.group(2).replace(",", "")) if m.group(2) else None
                scope = pos_scope or _scope_before(text, m.start())
                if hi is None:
                    ok = lo in _artifact_game_counts(scope)
                    what = f"{lo:,} 場[{scope or '任一 scope'}]"
                elif scope is None:
                    ok, what = False, f"{lo}–{hi} 場（區間・**無法由文字判定 scope**）"
                else:
                    seasons = [s["n_completed_games"] for s in _SCOPES[scope]["seasons"]]
                    ok = all(lo <= n <= hi for n in seasons)
                    what = f"{lo}–{hi} 場（區間・{scope} 逐季 {seasons}）"
                if not ok:
                    bad.append(f"{loc}: {what}")
                print(f"  [{'OK ' if ok else 'MISS'}] {loc:34s} {what}")
    assert not bad, (
        f"對外場數宣稱對不上 artifact：{bad}——"
        "換來源時最容易留下舊值，這一類必須由規則掃描而非手挑欄位守住"
    )


# ---------------------------------------------------------------------------
# key-plays 的選法比較：由完整母體的重測 artifact 現算
#
# 這三個數字先前是選取準則改版當時的一次抽驗（81／15／0），樣本組成與產生程式皆未留存、
# 無法重跑，等於一組看起來像已查證、實際上沒人能查的公開數字。需求方 2026-08-17 裁定重測：
# 母體改為**明確定義**的「2026 一軍例行賽全部完成場」，兩個選法各跑一次並落成可 --check
# 重跑的 artifact。標註「不可查核」因此不再需要——數字現在真的可查，測試就真的查它。
# ---------------------------------------------------------------------------
KEYPLAY_ARTIFACT = ROOT / "docs/research/WP-DISCLOSURE-SYNC1/keyplay_garbage_time.json"
_KP = json.loads(KEYPLAY_ARTIFACT.read_text(encoding="utf-8"))


def test_key_play_selection_numbers_match_the_remeasurement(capsys) -> None:
    """key-plays 段的選法比較與門檻數字，逐位對應完整母體重測 artifact。"""
    pop, res, lim = _KP["population"], _KP["results"], _KP["key_play_limit"]
    n = pop["n_games_evaluated"]
    rows = [
        ("baseline", None, "母體場數", f"{n} 場完成場實測"),
        ("baseline", None, "資料 as-of", pop["as_of"]),
        ("baseline", None, "|ΔRE24| 命中場數", f"{res['delta_re24']['n_games_hit']} 場選中"),
        ("baseline", None, "|ΔWP| 命中場數", f"|ΔWP| 選法 {res['delta_wp']['n_games_hit']} 場"),
        ("validation", "行為實測", "母體場數", f"{n} 場完成場"),
        ("validation", "行為實測", "資料 as-of", pop["as_of"]),
        ("validation", "行為實測", "選滿門檻的場數",
         f"{n - lim['n_games_below_limit']} 場選得滿 {lim['limit']} 個"),
        ("validation", "行為實測", "未達門檻的場數", f"{lim['n_games_below_limit']} 場因"),
        ("version", None, "來源 artifact", KEYPLAY_ARTIFACT.name),
        ("version", None, "資料 as-of", pop["as_of"]),
    ]
    misses = []
    with capsys.disabled():
        print(f"\n=== key-plays ↔ {KEYPLAY_ARTIFACT.name}（as-of {pop['as_of']}）逐欄位比對 ===")
        for field, anchor, label, needle in rows:
            text = _ts("key-plays", field, anchor)
            ok = needle in text
            if not ok:
                misses.append((f"key-plays.{field}", label, needle))
            print(f"  [{'OK ' if ok else 'MISS'}] key-plays.{field:11s} {label:16s} → {needle!r}")
    assert not misses, f"key-plays 的數字與重測 artifact 對不上：{misses}"


def test_key_play_remeasurement_population_is_explicitly_defined() -> None:
    """母體必須是可複述的定義＋as-of，不得再是「某次抽驗的 N 場」。

    先前那組數字之所以不可查核，根因是**母體沒有定義**——沒有人知道是哪 81 場。
    """
    pop = _KP["population"]
    assert pop["definition"] and pop["as_of"], "母體定義或 as-of 缺漏"
    assert pop["n_games_evaluated"] == pop["n_games_completed"] - \
        pop["n_games_without_plate_appearances"], "母體分母對不上"
    assert pop["n_games_evaluated"] > 0
    # 降級場次必須分開記，不得混進分母充當「已用 |ΔWP| 評估」
    assert pop["n_games_wp_degraded"] == 0, (
        f"有 {pop['n_games_wp_degraded']} 場走降級路徑，"
        "其 |ΔWP| 結果不成立，須從母體分離後重述"
    )


def _pt(v: float) -> str:
    """比例 → 個百分點的對外寫法（門檻 0.03 ＝ 3 個百分點）。"""
    return f"{round(v * 100, 2):g}"


def test_key_play_zero_hit_is_disclosed_as_mechanism_not_discrimination(capsys) -> None:
    """「|ΔWP| 0 場」必須連同**成因**揭露，且分布數字逐位對應 artifact。

    需求方 2026-08-17 質疑：那個 0 是不是幾乎由定義推得，而文案讀起來像鑑別力實證。
    實測成立——WP 在分差 ≥7 已飽和，垃圾時間打席擺動中位數僅門檻的百分之一。因此文案
    必須講機制（飽和＋被前 5 名擠掉）、必須揭露它對門檻值的依賴，不得只報計數。
    ⚠️ 本測試不驗門檻值該是多少（那是產品參數），只驗「對外有沒有把依賴講出來」。
    """
    g = _KP["swing_distribution"]["garbage_time"]
    ng = _KP["swing_distribution"]["non_garbage_time"]
    thr = _KP["key_play_min_wp_abs"]
    text = _ts("key-plays", "baseline")
    rows = [
        ("垃圾時間打席數", f"{g['n_plate_appearances']:,} 個垃圾時間打席"),
        ("垃圾時間擺動中位數", f"中位數僅 {_pt(g['median'])} 個百分點"),
        ("入選門檻", f"{_pt(thr)} 個百分點的入選門檻"),
        ("達門檻的垃圾時間打席數", f"已有 {g['n_at_or_above_threshold']} 個達到門檻"),
        ("垃圾時間擺動最大值", f"最大 {_pt(g['max'])} 個百分點"),
        ("非垃圾時間擺動最大值", f"可達 {_pt(ng['max'])} 個百分點"),
    ]
    misses = [(lbl, needle) for lbl, needle in rows if needle not in text]
    # 機制與依賴的措辭本身也要在——只報計數就是本輪要修的病
    for phrase in ("不是鑑別力的實證", "已經飽和", "依賴", "門檻若調低",
                   "飽和加上被前 5 名擠掉"):
        if phrase not in text:
            misses.append(("機制／依賴措辭", phrase))
    with capsys.disabled():
        print("\n=== 「0 場」的成因揭露（機制，非只報計數）===")
        for lbl, needle in rows:
            print(f"  [{'OK ' if needle in text else 'MISS'}] {lbl:22s} → {needle!r}")
        for phrase in ("不是鑑別力的實證", "已經飽和", "依賴", "門檻若調低",
                       "飽和加上被前 5 名擠掉"):
            print(f"  [{'OK ' if phrase in text else 'MISS'}] 措辭 {phrase}")
    assert not misses, (
        f"「0 場」的成因或門檻依賴未揭露：{misses}——"
        "只報計數會讓讀者以為量到了鑑別力，實際上它幾乎是 WP 飽和的定義推論"
    )


def test_garbage_time_swings_are_not_claimed_to_be_all_below_threshold() -> None:
    """不得對垃圾時間的擺動下全稱斷言——artifact 裡就有現成反例。

    ⚠️ 這一族已連三輪：先是「擺動都接近 0」，改掉後替代文案寫「因此**必然**極小」，
    同一個病換了個字。禁用詞清單治得了已經見過的寫法，但它是**開放集合**——中文的全稱
    詞舉不完，這個檢查永遠可能被下一個沒列到的詞繞過。真正封閉的是下半段：不論用哪個
    詞，只要「不是全部」這個限定從講機制的那一句被刪掉就紅。兩半各補一個缺口，都不完備。
    完備版本要等揭露文字由 artifact 生成（#147）。
    """
    g = _KP["swing_distribution"]["garbage_time"]
    assert g["n_at_or_above_threshold"] > 0, (
        "artifact 顯示已無垃圾時間打席達門檻；若屬實，文案的門檻依賴說明需同步重寫"
    )
    assert g["max"] >= _KP["key_play_min_wp_abs"], "artifact 的最大值與達標計數自相矛盾"
    # 先剝掉「明文否定」的合法寫法，再禁絕對化說法——沿用本 repo 對「並非統計信賴區間」
    # 的既有慣例（methodology-content.test.ts）：否定句是允許的，肯定句才是病。
    text = _ts("key-plays", "baseline")
    stripped = text
    for negated in ("不是「垃圾時間的擺動全都低於門檻」",):
        stripped = stripped.replace(negated, "")
    for banned in ("擺動都接近 0", "擺動全都低於門檻", "必然", "必定"):
        assert banned not in stripped, f"文案出現與實測不符的絕對化說法：{banned}"

    # 封閉的那一半：artifact 說反例存在，講飽和機制的那一句就必須同句帶上限定。
    mechanism = [s for s in text.split("。") if "已經飽和" in s]
    assert len(mechanism) == 1, f"錨「已經飽和」在 key-plays.baseline 命中 {len(mechanism)} 句"
    hedged = [h for h in ("典型", "多數", "不是全部", "並非全部") if h in mechanism[0]]
    assert hedged, (
        f"artifact 有 {g['n_at_or_above_threshold']} 個垃圾時間打席達到門檻，"
        "講飽和機制的那一句卻沒有任何限定詞——無限定的概括會被資料裡現成的反例推翻"
    )


# ---------------------------------------------------------------------------
# `pa_facts.key_plays` 的註解：指向 artifact，而不是再抄一份數字
#
# R8 查核以 mutation 證實：docstring 裡的 0.0003／0.0332／0.7055／「2 個」改掉，全綠——
# 比對器守的是**對外文案**，docstring 從來不在射程內。兩條路擇一：
#   甲 把那些數字納入比對器射程 → 比對器多守一份**副本**。
#   乙 把數字從 docstring 拿掉、改指向 artifact → 沒有副本可漂。
# 本卡整輪的病因就是無人看守的副本（version 欄指名的 artifact 早已與內容分岔），
# 再造一份只是把同一個形狀再走一遍，故走**乙**。
#
# 於是這裡檢查的不是「副本抄對了」，而是「副本不存在」——而且禁用字面集合**由
# artifact 現算**：artifact 多一個統計量，射程自動多一項，不需要人記得補。
# ---------------------------------------------------------------------------
def _key_plays_docstring() -> str:
    tree = ast.parse(PA_FACTS.read_text(encoding="utf-8"))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "key_plays"]
    assert len(fns) == 1, f"pa_facts.py 找不到唯一的 key_plays（命中 {len(fns)}）"
    doc = ast.get_docstring(fns[0])
    assert doc, "key_plays 沒有 docstring"
    return doc


_NUM_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")


def _artifact_numeric_literals() -> set[str]:
    """artifact 全部**數值**葉節點的字面，過濾掉 1–2 字元者。

    ⚠️ 已知射程缺口：1–2 字元的值（0／2／5／22…）刻意排除——它們與散文裡的普通數字
    無法區分（``KEY_PLAY_LIMIT`` 的 5、``ΔRE24`` 的 24 都會撞），硬擋只會製造假紅。
    因此「有 2 個達到門檻」這種短數字若被抄回 docstring，本檢查抓不到；抓得到的是所有
    有辨識度的量測值。
    """
    lits: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, float):
            lits.add(f"{node:g}")
        elif isinstance(node, int):
            lits.add(str(node))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(_KP)
    return {s for s in lits if len(s) >= 3}


def _copied_artifact_values(text: str) -> list[str]:
    """``text`` 裡出現的 artifact 量測值（含 as-of）。

    數字以**token 相等**比對，不用 substring：``game_snos`` 的 202 會命中
    ``2026-08-06`` 的前三碼，那是比對方式的假陽性，不是真的抄了值（實測踩到）。
    as-of 是帶連字號的日期、token 化會被拆散，改以 substring 比對——日期字串夠特異，
    不會誤傷。
    """
    hits = sorted(set(_NUM_TOKEN_RE.findall(text)) & _artifact_numeric_literals())
    as_of = _KP["population"]["as_of"]
    if as_of in text:
        hits.append(as_of)
    return hits


def test_pa_facts_docstring_cites_the_artifact_instead_of_copying_its_numbers(capsys) -> None:
    """`key_plays` 的註解只講機制與依賴，數字留在 artifact。

    什麼結果會讓這個檢查不成立（依序對應三段斷言）：
      1. 把任何一個有辨識度的量測值（如最大擺動）貼回 docstring → 紅。
         R8 之前的 docstring 版本正是如此，本檔另有一測直接拿它當反例證明會紅。
      2. 把指向 artifact 的路徑刪掉 → 紅（乙的前提是「看得到去哪裡查」）。
      3. 把機制／門檻依賴的說明刪成只剩一個連結 → 紅（乙不得退化成純指標）。
    """
    doc = _key_plays_docstring()
    forbidden = _copied_artifact_values(doc)
    with capsys.disabled():
        print("\n=== pa_facts.key_plays 註解 ↔ keyplay artifact（檢查副本不存在）===")
        print(f"  禁用字面集合由 artifact 現算，共 {len(_artifact_numeric_literals())} 項（＋as-of）")
        print(f"  [{'FAIL' if forbidden else 'OK '}] docstring 內的 artifact 量測值 {forbidden}")
    assert not forbidden, (
        f"docstring 把 artifact 的量測值抄了回來：{forbidden}——"
        "那是一份沒有守衛的副本，會隨球季推進漂掉；改為指向 artifact"
    )
    assert KEYPLAY_ARTIFACT.name in doc, (
        f"docstring 未指向 {KEYPLAY_ARTIFACT.name}——拿掉數字又不給出處，讀碼的人無從查證"
    )
    for phrase in ("飽和", "擠掉", "KEY_PLAY_MIN_WP_ABS"):
        assert phrase in doc, (
            f"docstring 缺少「{phrase}」：機制與門檻依賴必須留在碼旁，"
            "只留一個連結會讓下一個讀碼的人重新相信「垃圾時間擺動都低於門檻」"
        )


def test_the_copy_detector_would_have_caught_the_previous_docstring() -> None:
    """變異檢驗（釘死在測試裡，不靠人手動跑一次）：R8 版 docstring 必須被判為副本。

    這一段是上一版 docstring 的原文節錄。若哪天它**不再**被判違規，代表禁用集合的
    產生方式壞了（例如 artifact 改了鍵名而 walk 掃不到），而不是問題消失了。

    ⚠️ 兩個通道**分開斷言**。原本只斷言 :func:`_copied_artifact_values` 回傳非空——實測
    把數值通道的長度門檻改成 30（等於全部關掉）仍然綠，因為 as-of 那個通道自己就撐住了
    非空。「至少抓到一個」在多通道偵測器上是零資訊的斷言。
    """
    previous = (
        "2026 一軍全季實測（as-of 2026-08-17）：978 個垃圾時間打席的 |ΔWP| 中位數 0.0003"
        "（門檻 0.03 的百分之一），但有 2 個達到門檻、最大 0.0332。它們仍未入選，是因為"
        "同場非垃圾時間打席的擺動可達 0.7055，取前 5 名時把它們排掉了。"
    )
    numeric = sorted(set(_NUM_TOKEN_RE.findall(previous)) & _artifact_numeric_literals())
    assert numeric, "數值通道對上一版 docstring 零命中——禁用集合的產生方式已壞"
    assert _KP["population"]["as_of"] in _copied_artifact_values(previous), (
        "as-of 通道對上一版 docstring 零命中——時戳比對已壞"
    )
