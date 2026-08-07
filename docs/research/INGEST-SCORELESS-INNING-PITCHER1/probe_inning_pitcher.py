"""INGEST-SCORELESS-INNING-PITCHER1：stats.cpbl 單場 API 逐局責任投手粒度查證。

**本腳本不發出任何網路請求**（唯一一次請求由 `confirm_live_schema.py` 發出並已落檔）。
證據來源為兩份語料，端點皆為本卡待查的同一支
`GET https://stats.cpbl.com.tw/api/proxy/v1/games/{year}-{kind}-{sno}`：

- `g4_saved`：`INGEST-GAME-TM-REFACTOR1-G4` Phase A 保存的 10 份官方回應全文
  （`f.write(raw)` 逐位元保存，sha256 錨定於該卡 `manifest.json`／`dryrun_fetch_log.jsonl`，
  fetched_at 2026-08-05）。**該卡只為「有 TrackMan 差異」的場次保存 payload，屬偏差樣本。**
- `confirm`：本卡單次確認請求取得的中性完成場（`2026-A-246`），用於堵抽樣偏差質疑。

產出（`--outdir`，預設本檔所在目錄）：
- `field_inventory.json`   單場 API 全欄位遞迴清冊（含 payload sha256 對照）
- `granularity.json`       責任投手／自責分的最細可得粒度，及逐局推導的阻斷點
- `reconcile_pitchers.json` 跨來源對帳：stats.cpbl `Pitchers[]` vs `cpbl.pitching_gamelog`
                            （後者來自 **www.cpbl.com.tw** `/box/getlive`，是獨立的第二來源）

DB 只做 SELECT（`db_scope=read`）。跳過 DB：`--no-db`。

    uv run python docs/research/INGEST-SCORELESS-INNING-PITCHER1/probe_inning_pitcher.py
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pathlib
import re

# 證據來源：G4 Phase A 保存的原始回應。本卡唯讀引用，不重抓、不改動。
G4_DIR = pathlib.Path("docs/research/INGEST-GAME-TM-REFACTOR1-G4")
AS_OF = "2026-08-07"  # 顯式 as-of，非產生時間（避免每次重跑髒 worktree）
ENDPOINT = "https://stats.cpbl.com.tw/api/proxy/v1/games/{game_id}"

# 逐局責任投手若存在，最可能長成的欄位名樣態（用於窮舉否證，而非只憑肉眼掃）
RESPONSIBLE_PATTERNS = re.compile(
    r"responsib|charg|inherit|earned|selfrun|duty|owner", re.IGNORECASE
)
PITCHER_PATTERN = re.compile(r"pitcher", re.IGNORECASE)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _walk_keys(node, path: str, out: dict[str, set[str]]) -> None:
    """遞迴收集「路徑 -> 型別」；list 併為同一路徑（走訪全部元素，不只 [0]）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            out.setdefault(p, set()).add(type(v).__name__)
            _walk_keys(v, p, out)
    elif isinstance(node, list):
        p = f"{path}[]"
        for item in node:
            out.setdefault(p, set()).add(type(item).__name__)
            _walk_keys(item, p, out)


OWN_DIR = pathlib.Path("docs/research/INGEST-SCORELESS-INNING-PITCHER1")


def load_payloads() -> list[tuple[str, bytes, dict, str]]:
    """回傳 (game_id, raw bytes, 解析後 dict, 語料來源)。

    兩份語料：
    - ``g4_saved``：G4 Phase A 保存的 10 場（**有 TrackMan 差異才保存**，屬偏差樣本）
    - ``confirm``：本卡單次確認請求取得的中性完成場（見 ``confirm_live_schema.py``）
    """
    rows = []
    for src_dir, corpus in ((G4_DIR, "g4_saved"), (OWN_DIR, "confirm")):
        for f in sorted((src_dir / "payloads").glob("*.json.gz")):
            raw = gzip.open(f, "rb").read()
            rows.append((f.stem.replace(".json", ""), raw, json.loads(raw), corpus))
    if not rows:
        raise SystemExit(f"找不到任何 payload：{G4_DIR / 'payloads'}")
    return rows


def build_inventory(payloads) -> dict:
    keys: dict[str, set[str]] = {}
    fetch_log = {}
    fl = G4_DIR / "dryrun_fetch_log.jsonl"
    if fl.exists():
        for line in fl.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                fetch_log[rec["game"]] = rec
    own_log = {}
    rl = OWN_DIR / "request_log.json"
    if rl.exists():
        for r in json.loads(rl.read_text())["requests"]:
            own_log[r["url"].rsplit("/", 1)[-1]] = r
    sources = []
    for gid, raw, _, corpus in payloads:
        rec = fetch_log.get(gid, {}) if corpus == "g4_saved" else own_log.get(gid, {})
        anchor = rec.get("payload_sha256") or rec.get("raw_sha256")
        sources.append({
            "game_id": gid,
            "corpus": corpus,
            "endpoint_url": rec.get("endpoint_url") or rec.get("url")
            or ENDPOINT.format(game_id=gid),
            "fetched_at": rec.get("fetched_at") or rec.get("finished_at"),
            "raw_sha256_recomputed": _sha256(raw),
            "raw_sha256_anchor": anchor,
            "raw_sha256_matches_anchor": anchor == _sha256(raw),
        })
    # 逐 corpus 的欄位骨架，用於偏差樣本 vs 中性場的 schema 比對
    by_corpus: dict[str, dict[str, set[str]]] = {}
    for _, _, doc, corpus in payloads:
        _walk_keys(doc, "$", keys)
        _walk_keys(doc, "$", by_corpus.setdefault(corpus, {}))
    flat = {k: sorted(v) for k, v in sorted(keys.items())}
    pitcher_keys = [k for k in flat if PITCHER_PATTERN.search(k.rsplit(".", 1)[-1])]
    responsible_keys = [k for k in flat if RESPONSIBLE_PATTERNS.search(k.rsplit(".", 1)[-1])]
    return {
        "as_of": AS_OF,
        "endpoint": ENDPOINT,
        "evidence": "g4_saved=G4 Phase A 保存之官方回應全文（偏差樣本）；confirm=本卡單次確認請求之中性完成場",
        "payload_count": len(payloads),
        "sources": sources,
        "field_count": len(flat),
        "fields": flat,
        "keys_mentioning_pitcher": sorted(pitcher_keys),
        "keys_matching_responsibility_patterns": sorted(responsible_keys),
        "corpus_schema_comparison": {
            "note": "g4_saved 是『有 TrackMan 差異才保存』的偏差樣本；confirm 是中性完成場。"
                    "只在 g4_saved 出現的鍵若僅為情境性欄位（如無救援情境即無 Closer），"
                    "不構成 schema 差異。",
            "counts": {c: len(v) for c, v in sorted(by_corpus.items())},
            "only_in_confirm": sorted(
                set(by_corpus.get("confirm", {})) - set(by_corpus.get("g4_saved", {}))
            ),
            "only_in_g4_saved": sorted(
                set(by_corpus.get("g4_saved", {})) - set(by_corpus.get("confirm", {}))
            ),
        },
    }


def build_granularity(payloads) -> dict:
    """逐局責任投手是否存在？自責分最細粒度為何？逐局推導斷在哪裡？"""
    per_game = []
    zero_pitch_examples: list[dict] = []
    for gid, _, doc, corpus in payloads:
        g = doc["Data"]["Game"]
        sides = {}
        for side in ("Home", "Visiting"):
            s = g[side]
            pitchers = s["Pitchers"]
            sides[side] = {
                "pitcher_count": len(pitchers),
                "sum_RunCnt": sum(p.get("RunCnt") or 0 for p in pitchers),
                "sum_EarnedRunCnt": sum(p.get("EarnedRunCnt") or 0 for p in pitchers),
                "opponent_final_score": g["Visiting" if side == "Home" else "Home"]["Score"],
                "InningScore_fields": sorted(s["InningScore"][0].keys()) if s["InningScore"] else [],
                "InningScore_has_pitcher": any(
                    PITCHER_PATTERN.search(k)
                    for row in s["InningScore"] for k in row
                ),
                "per_pitcher": [
                    {"acnt": p.get("PitcherAcnt"), "role": p.get("RoleType"),
                     "IP": p.get("InningPitchedCnt"), "IPdiv3": p.get("InningPitchedDiv3Cnt"),
                     "R": p.get("RunCnt"), "ER": p.get("EarnedRunCnt"),
                     "pitches": p.get("PitchCnt")}
                    for p in pitchers
                ],
            }
        # LiveLog：逐球有 PitcherAcnt + InningSeq，但無自責分標記
        ll = g["LiveLog"]
        ll_keys = sorted({k for e in ll for k in e})
        scoring = [e for e in ll if e.get("IsScoreCnt") == "1"]
        # 零投球事件（同投手 PitchCnt 未推進）：規則反例的觀測佐證
        prev: dict[str, int] = {}
        zero_pitch = 0
        for e in ll:
            acnt, pc = e.get("PitcherAcnt"), e.get("PitchCnt")
            if acnt in prev and pc == prev[acnt]:
                zero_pitch += 1
                if len(zero_pitch_examples) < 8:
                    zero_pitch_examples.append({
                        "game_id": gid, "inning": e.get("InningSeq"),
                        "pitcher": e.get("PitcherName"),
                        "content": (e.get("Content") or "").strip()[:60],
                        "main_event_no": e.get("MainEventNo"),
                    })
            prev[acnt] = pc
        per_game.append({
            "game_id": gid,
            "corpus": corpus,
            "kind_code": g.get("KindCode"),
            "sides": sides,
            "livelog_rows": len(ll),
            "livelog_keys": ll_keys,
            "livelog_has_earned_run_marker": any(
                RESPONSIBLE_PATTERNS.search(k) for k in ll_keys
            ),
            "livelog_scoring_rows": len(scoring),
            "livelog_zero_pitch_rows": zero_pitch,
            "game_level_decision_fields": [
                k for k in ("WinningPitcher", "LoserPitcher", "Closer") if k in g
            ],
        })
    # 全樣本斷言
    any_inning_pitcher = any(
        s["InningScore_has_pitcher"] for row in per_game for s in row["sides"].values()
    )
    any_livelog_er = any(r["livelog_has_earned_run_marker"] for r in per_game)
    r_ne_er = [
        {"game_id": r["game_id"], "side": side,
         "R": s["sum_RunCnt"], "ER": s["sum_EarnedRunCnt"]}
        for r in per_game for side, s in r["sides"].items()
        if s["sum_RunCnt"] != s["sum_EarnedRunCnt"]
    ]
    return {
        "as_of": AS_OF,
        "verdict_inputs": {
            "InningScore_carries_pitcher_attribution": any_inning_pitcher,
            "LiveLog_carries_earned_run_marker": any_livelog_er,
            "finest_pitcher_identity_granularity": "per-pitch (LiveLog[].PitcherAcnt + InningSeq)",
            "finest_earned_run_granularity": "per-game per-pitcher (Pitchers[].EarnedRunCnt)",
            "inning_level_earned_run_available": False,
            "unearned_runs_observed_in_sample": len(r_ne_er),
            "unearned_run_cases": r_ne_er,
        },
        "zero_pitch_event_examples": zero_pitch_examples,
        "per_game": per_game,
    }


def _on_mound_runs(game: dict) -> dict[str, int]:
    """逐事件比分推進量歸給該事件的 ``PitcherAcnt``。"""
    on_mound: dict[str, int] = {}
    pv = ph = 0
    for e in game["LiveLog"]:
        v = e.get("VisitingScore") or 0
        h = e.get("HomeScore") or 0
        delta = (v - pv) + (h - ph)
        if delta > 0:
            on_mound[e.get("PitcherAcnt")] = on_mound.get(e.get("PitcherAcnt"), 0) + delta
        pv, ph = v, h
    return on_mound


def build_run_attribution(payloads) -> dict:
    """量測「逐球在場上的投手」能否重現官方失分歸屬——**先過來源完整性閘門**。

    即使退一步只求**失分**（不求自責分），LiveLog 的逐球 `PitcherAcnt` 也重現不了官方
    `RunCnt`。本函式量測的是**不符率本身**，不宣稱其成因。

    「不一致」至少有**兩類**成因，必須先分離，否則會把來源缺資料混進來充數
    （R1 查核命中處）：

    1. **來源異常**：LiveLog 本身沒記完（末筆比分 ≠ header 最終比分，或涵蓋局數不足）。
       此時整場的逐球歸屬都不可信（缺的分可能落在時間線任何位置，連「相符」的列也
       只是碰巧），故**整場剔除**，不只剔不一致的列。
    2. **歸屬轉移**：分只是從一位投手記到另一位，故同一 game+side 內官方與推導的
       **淨差必為 0**。守恆成立才留作證據。

    ⚠️ **守恆是轉移型解釋的必要條件，不是充分條件**（R2 查核命中處）：淨差 0 排除了
    「憑空增減」，但**不能指認**是哪個機制造成轉移——兩個方向相反的解析誤差互相抵消
    一樣會守恆。規則 9.16（繼承跑者記給讓他上壘的投手）是**最可能的候選解釋**，
    但本函式**未逐筆核對跑者的來源投手**，故輸出一律稱 mismatch rate，不稱 9.16 效應量。

    兩道閘門皆由本函式**程式化判定**，不是硬編場次黑名單——換一批 payload 一樣會自動分流。
    """
    completeness, retained, excluded = [], [], []
    for gid, _, doc, _corpus in payloads:
        g = doc["Data"]["Game"]
        ll = g["LiveLog"]
        last = ll[-1] if ll else {}
        term = (last.get("VisitingScore") or 0, last.get("HomeScore") or 0)
        final = (g["Visiting"]["Score"], g["Home"]["Score"])
        score_ok = term == final
        # 第二訊號：LiveLog 是否涵蓋到 InningScore 宣告的最後一局。只驗比分會漏掉
        # 「截斷點落在最後一次得分之後」的情形——那種截斷比分對得上，局數對不上。
        innings_declared = max(
            len(g["Home"]["InningScore"]), len(g["Visiting"]["InningScore"])
        )
        innings_in_livelog = max((e.get("InningSeq") or 0) for e in ll) if ll else 0
        innings_ok = innings_in_livelog >= innings_declared
        ok = score_ok and innings_ok
        completeness.append({
            "game_id": gid, "livelog_rows": len(ll),
            "livelog_terminal_score": list(term),
            "header_final_score": list(final),
            "runs_missing_from_livelog": (final[0] - term[0]) + (final[1] - term[1]),
            "innings_declared_by_InningScore": innings_declared,
            "innings_covered_by_livelog": innings_in_livelog,
            "score_signal_ok": score_ok,
            "inning_coverage_signal_ok": innings_ok,
            "passes_completeness_gate": ok,
        })
        (retained if ok else excluded).append((gid, g))

    rows, mismatches, conservation = 0, [], []
    for gid, g in retained:
        on_mound = _on_mound_runs(g)
        for side in ("Home", "Visiting"):
            official = {p["PitcherAcnt"]: (p.get("RunCnt") or 0) for p in g[side]["Pitchers"]}
            net, n = 0, 0
            for acnt in sorted(official):
                rows += 1
                off_r, der_r = official[acnt], on_mound.get(acnt, 0)
                net += off_r - der_r
                if off_r != der_r:
                    n += 1
                    mismatches.append({"game_id": gid, "side": side, "pitcher_acnt": acnt,
                                       "official_RunCnt": off_r, "derived_on_mound_runs": der_r})
            if n:
                conservation.append({"game_id": gid, "side": side, "mismatch_rows": n,
                                     "net_difference": net, "conserved": net == 0})

    # 被剔除場次的原始數字（保留供查核者複核，不進主證）
    excluded_detail = []
    for gid, g in excluded:
        on_mound = _on_mound_runs(g)
        rows_x, mism_x = 0, 0
        for side in ("Home", "Visiting"):
            for p in g[side]["Pitchers"]:
                rows_x += 1
                if (p.get("RunCnt") or 0) != on_mound.get(p["PitcherAcnt"], 0):
                    mism_x += 1
        excluded_detail.append({"game_id": gid, "pitcher_rows": rows_x,
                                "raw_mismatch_rows": mism_x,
                                "reason": "LiveLog 不完整（比分訊號與/或局數涵蓋訊號未過）"})

    all_conserved = all(c["conserved"] for c in conservation)
    return {
        "as_of": AS_OF,
        "question": "逐球 LiveLog 的『當下投手』能否重現官方逐投手失分歸屬？",
        "method": "逐事件比分推進量歸給該事件的 PitcherAcnt，與 Pitchers[].RunCnt 對照；"
                  "先過『來源完整性』閘門整場剔除，再以『同 side 淨差=0』守恆檢定排除"
                  "『憑空增減』型的來源異常。守恆是轉移型解釋的必要非充分條件，"
                  "不指認轉移機制。",
        "metric_name": "run_attribution_mismatch_rate_after_gates",
        "metric_is_not": "任何特定規則（含 9.16）的效應量——本卡未逐筆核對跑者來源投手",
        "gate_1_source_completeness": {
            "rule": "兩訊號皆須通過：(a) LiveLog 末筆比分 == header 最終比分；"
                    "(b) LiveLog 涵蓋局數 >= InningScore 宣告局數（抓截斷）",
            "per_game": completeness,
            "games_total": len(payloads),
            "games_retained": len(retained),
            "games_excluded": len(excluded),
            "excluded_detail": excluded_detail,
        },
        "gate_2_conservation": {
            "rule": "任何轉移型解釋皆蘊含同一 game+side 內 sum(official - derived) = 0",
            "logical_status": "必要非充分條件：排除『憑空增減』，但不指認轉移機制",
            "sides_with_mismatch": conservation,
            "all_conserved": all_conserved,
        },
        "pitcher_rows": rows,
        "mismatch_count": len(mismatches),
        "mismatch_rate": round(len(mismatches) / rows, 4) if rows else None,
        "interpretation": (
            "在通過完整性閘門的場次中，全部不一致皆守恆（淨差 0），型態與『歸屬轉移』相容，"
            "已排除『憑空增減』型的來源異常。成立的命題是：逐球 PitcherAcnt 重現不了官方"
            "逐投手失分歸屬——連『失分』都如此，『自責分』更無從逐局推導。"
            "轉移的具體機制未指認；最可能的候選是規則 9.16 繼承跑者歸屬，"
            "但本卡未逐筆核對跑者來源投手，故不得將本數字當作 9.16 的效應量。"
            if all_conserved else
            "⚠️ 仍有不守恆的 side，來源異常未排除乾淨，本數字不可直接引用——待人工判讀。"
        ),
        "claim_boundary": "可宣稱：逐球歸屬 != 官方 RunCnt（不符率如上）。"
                          "不可宣稱：該不符率是規則 9.16 或任何特定機制的效應量。",
        "mismatches": mismatches,
    }


def build_reconcile(payloads) -> dict:
    """跨來源對帳：stats.cpbl `Pitchers[]` vs www.cpbl 來源的 `cpbl.pitching_gamelog`。"""
    from cpbl.db import conn

    cmp_fields = [
        ("InningPitchedCnt", "inning_pitched_cnt"),
        ("InningPitchedDiv3Cnt", "inning_pitched_div3"),
        ("PlateAppearances", "plate_appearances"),
        ("PitchCnt", "pitch_cnt"),
        ("StrikeCnt", "strike_cnt"),
        ("HittingCnt", "hits"),
        ("HomeRunCnt", "home_runs"),
        ("BasesONBallsCnt", "bb"),
        ("IntentionalBasesONBallsCnt", "ibb"),
        ("HitBYPitchCnt", "hbp"),
        ("StrikeOutCnt", "so"),
        ("WildPitchCnt", "wild_pitch"),
        ("BalkCnt", "balk"),
        ("RunCnt", "runs"),
        ("EarnedRunCnt", "earned_runs"),
    ]
    games, rows_checked, mismatches, missing = [], 0, [], []
    with conn() as c, c.cursor() as cur:
        for gid, _, doc, _corpus in payloads:
            year, kind, sno = gid.split("-")
            g = doc["Data"]["Game"]
            api = {}
            for side in ("Home", "Visiting"):
                for p in g[side]["Pitchers"]:
                    api[p["PitcherAcnt"]] = p
            cur.execute(
                "SELECT pitcher_acnt, " + ",".join(db for _, db in cmp_fields) +
                " FROM cpbl.pitching_gamelog WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (int(year), kind, int(sno)),
            )
            db_rows = {r[0]: r[1:] for r in cur.fetchall()}
            only_api = sorted(set(api) - set(db_rows))
            only_db = sorted(set(db_rows) - set(api))
            if only_api or only_db:
                missing.append({"game_id": gid, "only_api": only_api, "only_db": only_db})
            for acnt in sorted(set(api) & set(db_rows)):
                rows_checked += 1
                for i, (ak, dbk) in enumerate(cmp_fields):
                    av, dv = api[acnt].get(ak), db_rows[acnt][i]
                    if (av or 0) != (dv or 0):
                        mismatches.append({"game_id": gid, "pitcher_acnt": acnt,
                                           "field": f"{ak}/{dbk}", "api": av, "db": dv})
            games.append(gid)

        # LiveLog 範圍跨來源比對：stats.cpbl payload vs cpbl.game_livelog（來源 www）。
        # 用於佐證 §3.1 完整性閘門剔除的場次確實是「單場 API 殘缺」而非「該場本來就短」。
        livelog_extent = []
        for gid, _, doc, _c in payloads:
            year, kind, sno = gid.split("-")
            g = doc["Data"]["Game"]
            ll = g["LiveLog"]
            cur.execute(
                "SELECT count(*), max(visiting_score), max(home_score), max(inning_seq) "
                "FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (int(year), kind, int(sno)),
            )
            n_db, v_db, h_db, inn_db = cur.fetchone()
            livelog_extent.append({
                "game_id": gid,
                "api_livelog_rows": len(ll),
                "db_livelog_rows": n_db,
                "api_max_inning": max((e.get("InningSeq") or 0) for e in ll) if ll else 0,
                "db_max_inning": inn_db,
                "api_terminal_score": [ll[-1].get("VisitingScore") if ll else None,
                                       ll[-1].get("HomeScore") if ll else None],
                "db_max_score": [v_db, h_db],
                "header_final_score": [g["Visiting"]["Score"], g["Home"]["Score"]],
                "api_shorter_than_db": (n_db or 0) > len(ll),
            })
    return {
        "livelog_extent_cross_check": {
            "purpose": "佐證完整性閘門剔除的場次是單場 API 殘缺，而非該場本來就短",
            "source_b_note": "cpbl.game_livelog 來源為 www.cpbl /box/getlive，與單場 API 不同站台",
            "games_where_api_shorter": [r["game_id"] for r in livelog_extent
                                        if r["api_shorter_than_db"]],
            "per_game": livelog_extent,
        },
        "as_of": AS_OF,
        "source_a": "stats.cpbl.com.tw /api/proxy/v1/games/{id} → Data.Game.{Home,Visiting}.Pitchers[]",
        "source_b": "cpbl.pitching_gamelog（來源 www.cpbl.com.tw /box/getlive，獨立第二站台）",
        "games": games,
        "pitcher_rows_compared": rows_checked,
        "fields_compared_per_row": len(cmp_fields),
        "cells_compared": rows_checked * len(cmp_fields),
        "pk_set_differences": missing,
        "cell_mismatch_count": len(mismatches),
        "cell_mismatches": mismatches,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="docs/research/INGEST-SCORELESS-INNING-PITCHER1")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    payloads = load_payloads()

    def dump(name: str, obj: dict) -> None:
        (outdir / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
        )
        print(f"wrote {outdir / name}")

    inv = build_inventory(payloads)
    dump("field_inventory.json", inv)
    gran = build_granularity(payloads)
    dump("granularity.json", gran)
    attr = build_run_attribution(payloads)
    dump("run_attribution.json", attr)
    if not args.no_db:
        dump("reconcile_pitchers.json", build_reconcile(payloads))

    print(f"\n欄位總數 {inv['field_count']}；提及 pitcher 的鍵：{inv['keys_mentioning_pitcher']}")
    print(f"符合『責任／自責』樣態的鍵：{inv['keys_matching_responsibility_patterns']}")
    print(f"InningScore 帶投手歸屬：{gran['verdict_inputs']['InningScore_carries_pitcher_attribution']}")
    print(f"LiveLog 帶自責分標記：{gran['verdict_inputs']['LiveLog_carries_earned_run_marker']}")
    print(f"run-attribution mismatch rate（過兩道閘門後）："
          f"{attr['mismatch_count']}/{attr['pitcher_rows']} 列＝{attr['mismatch_rate']}"
          f"　※不符率，非任何特定規則的效應量")


if __name__ == "__main__":
    main()
