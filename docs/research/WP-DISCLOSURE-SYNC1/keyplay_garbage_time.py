"""WP-DISCLOSURE-SYNC1：關鍵打席選法 × 垃圾時間打席 的完整母體重測（唯讀）。

取代 key-plays 段落原本那組**未留存樣本、不可重跑**的 81／15／0 抽驗：母體改為明確定義
的「2026 一軍例行賽全部完成場」，兩個選法各跑一次，數「選中分差 ≥7 打席」的場次數。

    uv run python docs/research/WP-DISCLOSURE-SYNC1/keyplay_garbage_time.py
    uv run python docs/research/WP-DISCLOSURE-SYNC1/keyplay_garbage_time.py --check

`--check` 重跑並比對既有 artifact，不寫檔（交付物必須可重現）。
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from cpbl.db import conn
from cpbl.models.pa_facts import (
    KEY_PLAY_MIN_WP_ABS,
    _load_wp_swings,
    build_game_facts,
    delta_re24,
    key_plays,
    load_livelog,
    load_pa_members,
    load_published_pas,
    load_re_matrix,
)

OUT = Path(__file__).with_name("keyplay_garbage_time.json")
SEASON, KIND = 2026, "A"


def _completed_snos() -> tuple[list[int], date]:
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT game_sno FROM cpbl.games WHERE year=%s AND kind_code=%s "
            "AND coalesce(home_score,0)+coalesce(away_score,0) > 0 "
            "AND game_date <= CURRENT_DATE ORDER BY game_sno", (SEASON, KIND))
        snos = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT CURRENT_DATE")
        return snos, cur.fetchone()[0]


def _swing_distribution() -> dict:
    """全部打席的 |ΔWP| 分布，依垃圾時間切兩組（**不是只看入選的那五個**）。

    「|ΔWP| 選法 0 場選中垃圾時間打席」若只報計數，讀起來像是量到了鑑別力；實際上 WP 在
    分差 ≥7 時已飽和，垃圾時間打席的擺動**必然**極小。把分布寫進 artifact，讀者才看得到
    那個 0 的成因是機制而非巧合，也才看得到它離門檻有多遠（即結論對門檻值的敏感度）。
    """
    buckets: dict[str, list[float]] = {"garbage_time": [], "non_garbage_time": []}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT game_sno, home_score, away_score FROM cpbl.games WHERE year=%s "
            "AND kind_code=%s AND coalesce(home_score,0)+coalesce(away_score,0) > 0 "
            "AND game_date <= CURRENT_DATE ORDER BY game_sno", (SEASON, KIND))
        games = cur.fetchall()
        re_map = load_re_matrix(cur, KIND)
        for sno, hs, aws in games:
            pa_rows = load_published_pas(cur, SEASON, KIND, sno)
            if not pa_rows:
                continue
            events = load_livelog(cur, SEASON, KIND, sno)
            members = load_pa_members(cur, SEASON, KIND, sno)
            for row in pa_rows:
                row["member_event_nos"] = members.get(row["pa_index"], [])
            facts = delta_re24(pa_rows, events, re_map)
            swings, _ = _load_wp_swings(facts, season=SEASON, kind_code=KIND,
                                        home_score=hs, away_score=aws)
            if not swings:
                continue
            for f in facts:
                s = swings.get(f["pa_index"])
                if s is None or s.get("delta") is None:
                    continue
                key = "garbage_time" if f.get("garbage_time") else "non_garbage_time"
                buckets[key].append(abs(s["delta"]))
    out: dict[str, dict] = {}
    for key, xs in buckets.items():
        xs.sort()
        out[key] = {
            "n_plate_appearances": len(xs),
            "max": round(xs[-1], 4),
            "p99": round(xs[min(len(xs) - 1, int(len(xs) * 0.99))], 4),
            "median": round(xs[len(xs) // 2], 4),
            "n_at_or_above_threshold": sum(1 for v in xs if v >= KEY_PLAY_MIN_WP_ABS),
        }
    return out


def measure() -> dict:
    snos, as_of = _completed_snos()
    hit_wp: list[int] = []          # |ΔWP| 選法選中垃圾時間打席的場次
    hit_re24: list[int] = []        # |ΔRE24| 選法選中垃圾時間打席的場次
    degraded: list[int] = []        # 無 WP 序列（降級）——分開記，不混入分母
    no_facts: list[int] = []
    short: list[int] = []           # 選不滿 5 個關鍵打席的場次（文案宣稱「每場都選得出」）
    for sno in snos:
        payload = build_game_facts(SEASON, KIND, sno)
        facts = payload.get("plate_appearances") or []
        if not facts:
            no_facts.append(sno)
            continue
        sel = payload.get("key_play_selection") or {}
        if sel.get("signal") != "delta_wp":
            degraded.append(sno)
        if any(p.get("garbage_time") for p in (payload.get("key_plays") or [])):
            hit_wp.append(sno)
        if any(p.get("garbage_time") for p in key_plays(facts)):
            hit_re24.append(sno)
        if len(payload.get("key_plays") or []) < 5:
            short.append(sno)
    evaluated = [s for s in snos if s not in set(no_facts)]
    return {
        "card": "WP-DISCLOSURE-SYNC1",
        "measurement": "key-play selection vs garbage-time plate appearances",
        "population": {
            "definition": "2026 一軍例行賽（kind A）全部完成場："
                          "home_score+away_score > 0 且 game_date <= CURRENT_DATE",
            "as_of": str(as_of),
            "n_games_completed": len(snos),
            "n_games_evaluated": len(evaluated),
            "n_games_without_plate_appearances": len(no_facts),
            "n_games_wp_degraded": len(degraded),
        },
        "key_play_limit": {
            "limit": 5,
            "n_games_below_limit": len(short),
            "game_snos": short,
        },
        "garbage_time_definition": "打席前分差 ≥7（pa_facts._is_garbage_time）",
        "key_play_min_wp_abs": KEY_PLAY_MIN_WP_ABS,
        "swing_distribution": _swing_distribution(),
        "results": {
            "delta_wp": {"n_games_hit": len(hit_wp), "game_snos": hit_wp},
            "delta_re24": {"n_games_hit": len(hit_re24), "game_snos": hit_re24},
        },
        "reproduce": "uv run python docs/research/WP-DISCLOSURE-SYNC1/"
                     "keyplay_garbage_time.py --check",
    }


# `--check` 比對什麼、不比對什麼
#
# 判準：**在跑檢查之前先問「什麼樣的結果會讓它不成立」**。答不出任何能讓它通過的情形，
# 那就不是檢查而是噪音。母體每天長大，把 `as_of`／各項場數放進比對集合等於明天必紅——
# 本專案已經有「覆蓋告警響了兩個半月無人讀」的前例，不重演。
#
# 比對（變了就該紅）＝**散文所依賴的定性宣稱與量測定義**：
#   結論 |ΔWP| 選中 0 場、|ΔRE24| 確實會選中（>0）、門檻確實會咬到（>0）、
#   垃圾時間擺動中位數仍遠低於門檻（機制）、母體定義／垃圾時間定義／門檻值／上限值。
# 只報告（變了是預期）＝**隨賽季長大的計數**：as_of、各項場數、game_snos、分布的 n。
#
# 逐項的「什麼結果會讓它不成立」：
#   delta_wp == 0        → 某場垃圾時間打席擠進前 5（飽和假設破或門檻被調低）
#   delta_re24 > 0       → ΔRE24 不再於大分差選中垃圾時間（該指標性質變了）
#   below_limit > 0      → 再也沒有場次咬到門檻（文案那句要改寫）
#   median << threshold  → WP 不再於 ≥7 分差飽和（整段機制說明失效）
#   四個定義字串          → 量測換了母體或換了判準，數字不可再與舊值相提並論
_COMPARED_DEFINITIONS = ("population.definition", "garbage_time_definition",
                         "key_play_min_wp_abs", "key_play_limit.limit")


def _invariants(o: dict) -> dict:
    g = o["swing_distribution"]["garbage_time"]
    return {
        "delta_wp_selects_no_garbage_time": o["results"]["delta_wp"]["n_games_hit"] == 0,
        "delta_re24_does_select_garbage_time": o["results"]["delta_re24"]["n_games_hit"] > 0,
        "key_play_limit_does_bite": o["key_play_limit"]["n_games_below_limit"] > 0,
        "garbage_swings_far_below_threshold": g["median"] * 10 < o["key_play_min_wp_abs"],
        "population.definition": o["population"]["definition"],
        "garbage_time_definition": o["garbage_time_definition"],
        "key_play_min_wp_abs": o["key_play_min_wp_abs"],
        "key_play_limit.limit": o["key_play_limit"]["limit"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="重跑並比對定性結論與量測定義（計數只報告不比對）")
    args = ap.parse_args()
    out = measure()
    if args.check:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        old_inv, new_inv = _invariants(prev), _invariants(out)
        broken = {k: (old_inv[k], new_inv[k]) for k in old_inv if old_inv[k] != new_inv[k]}
        op, np_ = prev["population"], out["population"]
        moved = (f"母體 {op['n_games_evaluated']} → {np_['n_games_evaluated']} 場、"
                 f"as-of {op['as_of']} → {np_['as_of']}")
        if broken:
            print(f"CHECK FAILED：定性結論或量測定義已變 {broken}（{moved}）")
            return 1
        print(f"CHECK OK（{moved}；結論與定義未變）")
        print("  ⚠️ 計數本來就會隨賽季長大，故只報告不比對；"
              "對外文案引用的確切數字由 tests/test_recap_wp_contract.py 對本檔逐位比對。")
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    r, g = out["results"], out["swing_distribution"]["garbage_time"]
    print(f"母體 {out['population']['n_games_evaluated']} 場"
          f"（as-of {out['population']['as_of']}）")
    print(f"  |ΔWP|   選中垃圾時間打席：{r['delta_wp']['n_games_hit']} 場")
    print(f"  |ΔRE24| 選中垃圾時間打席：{r['delta_re24']['n_games_hit']} 場")
    print(f"  垃圾時間擺動中位數 {g['median']} vs 門檻 {out['key_play_min_wp_abs']}"
          f"（{out['key_play_min_wp_abs'] / g['median']:.0f} 倍）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
