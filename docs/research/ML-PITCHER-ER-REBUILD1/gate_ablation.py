"""逐 fail-closed 閘門的消融對照（卡面紅線「fail-closed 不得雙向濫用」的證據產生器）。

卡面要求：**每一道 fail-closed 閘門都要有對應消融並列出 Δ**（拿掉該閘門後逐場
通過數的變化量），或說明為何該閘門不需要消融。本檔把那份表**由指令產生**，
不靠人工聲明（memory「完整性宣稱須自動化證明」）。

它做四件事：

1. **分母不變量**：證明 fail-closed **不縮小分母**。`rebuild_er.reconcile` 對每一場
   都先 `games += 1`，被閘門擋下的場次留在分母裡當失敗。故
   `games == all_pass + Σ fail_reasons`。這條算式一旦成立，「排太多讓剩下的看起來
   更準」這個方向就**不成立**：閘門只會壓低通過率，不會抬高。
2. **逐閘門 Δ**：對每一道有對應 mutation 的閘門跑消融，算「原本被它擋下的場次
   有幾場變成通過」，並列出**沒變成通過的那些場次落到哪裡**（去向分布）。
   去向分布是關鍵——Δ=0 可能是「閘門擋對了」，也可能是「拿掉後立刻掉進下一道
   閘門」，兩者意義不同，必須看得見。
3. **無消融者的交代**：`mismatch:*` 不是閘門（它是對帳失敗的成因分類，場次早已
   在分母裡當失敗）；`multiple_new_runners`／`ledger_desync` 拿掉不是「移除檢查」
   而是「補一個猜測」，故給**確定上界**（Δ ≤ 被擋場數）而非假消融。
4. **`official_error_unlocated` 的逐案 ER 相關性**：官方記分板說某半局有失誤、
   逐球敘述卻沒寫。9.16 的失誤效果（(b) 失誤致得分非自責、(d) 無失誤重建、
   漏接第三出局後的續打）**全部侷限在同一個半局內**。故該半局若**一分未得**，
   那個看不到的失誤對三個對帳維度都不可能有影響：
     * ER：該半局沒有分可以被判自責／非自責；
     * runs：失誤不改變得分數；
     * outs：我方出局數逐球數實際發生的，不是重建出來的。
   本檔用官方記分板 `score_cnt`（**獨立於逐球敘述**的第二來源）判定該半局是否
   得分，再與消融後的通過與否交叉列表。

用法：

    uv run python docs/research/ML-PITCHER-ER-REBUILD1/gate_ablation.py

輸出 `gate_ablation.json`（同目錄）。不含 wall-clock 時戳；as-of 取自 full 執行的
`data_asof`。DB 唯讀。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import psycopg
import rebuild_er as R
from psycopg.rows import dict_row

YEARS = list(range(2018, 2027))
KINDS = ["A", "D"]

# 無對應 mutation 的閘門／分類，逐道交代理由。**「沒做」不是理由**，故每一條都要
# 說清楚「拿掉它會發生什麼」，而不是「不方便做」。
NO_ABLATION: dict[str, dict[str, str]] = {
    "mismatch:source_gap": {
        "kind": "mismatch_classification",
        "why": (
            "不是 fail-closed 閘門。`mismatch:*` 是**對帳失敗後**的成因分類："
            "重建已完整跑完、三維與官方比對不符，場次留在分母裡當失敗（見分母不變量）。"
            "沒有可以「拿掉」的檢查——拿掉標籤不會讓任何一場變成通過，Δ 恆為 0。"
            "成因為某一側 runs 或 outs 淨差不為 0，屬來源資料缺漏。"
        ),
        "delta_upper_bound": "0",
    },
    "mismatch:attribution_boundary": {
        "kind": "mismatch_classification",
        "why": (
            "同上，不是閘門而是對帳失敗的成因分類（淨差為 0 但逐投手歸屬不同）。"
            "Δ 恆為 0。"
        ),
        "delta_upper_bound": "0",
    },
    "mismatch:earned_rule_boundary": {
        "kind": "mismatch_classification",
        "why": (
            "同上，不是閘門。這是本卡真正的殘差：失分與出局全對、只有自責分不同，"
            "即 9.16 的記錄員判斷邊界。Δ 恆為 0。"
        ),
        "delta_upper_bound": "0",
    },
    "multiple_new_runners": {
        "kind": "gate",
        "why": (
            "拿掉它不是「移除檢查」而是「補一個猜測」。該閘門觸發於：下一個 island "
            "的壘況比本 island 多出**一個以上**新棒次槽，即無法判斷哪一位是打者、"
            "哪一位是本來就在壘上而帳本漏掉的人。任何消融實作都必須先指定「哪一個"
            "新槽是打者」，那正是 fail-closed 要禁止的歸屬猜測；若改成不指定"
            "（batter_slot=None），多出來的跑者會在下一個 island 觸發 ledger_desync，"
            "Δ 由建構方式決定而非由資料決定，是**沒有鑑別力的假消融**。"
            "故給確定上界：Δ ≤ 被擋場數。"
        ),
        "delta_upper_bound": "blocked",
    },
    "ledger_desync": {
        "kind": "gate",
        "why": (
            "同型：帳本重建的壘上棒次槽與 livelog 觀測的壘況不一致。消融要能繼續，"
            "必須以觀測壘況重建帳本並替憑空出現的跑者指定**責任投手與上壘手段**"
            "（earned_ok），兩者都是 9.16 的核心判定、都只能猜。這是補猜測不是移除"
            "檢查。故給確定上界：Δ ≤ 被擋場數。"
        ),
        "delta_upper_bound": "blocked",
    },
}


def _run(mutation: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    per_game: dict[str, dict[str, Any]] = {}
    res = R.reconcile(YEARS, KINDS, None, mutation, as_of=None, per_game=per_game)
    return res, per_game


def _verify_half_mapping(conn: Any) -> dict[str, Any]:
    """半局別對照的獨立驗證：逐局 score_cnt 加總須等於 `games` 的終場比分。

    對照弄反會讓整個「該半局是否得分」的判定失效，而那是本檔最關鍵的判準——
    故不靠註解宣稱，跑一次全母體對帳。保留賽／來源缺漏造成的不符照實計數。
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) AS n, "
        "  count(*) FILTER (WHERE s.away_sum = g.away_score "
        "                     AND s.home_sum = g.home_score) AS ok "
        "FROM cpbl.games g JOIN ("
        "  SELECT year, kind_code, game_sno, "
        "         sum(score_cnt) FILTER (WHERE visiting_home_type = '1') AS away_sum, "
        "         sum(score_cnt) FILTER (WHERE visiting_home_type <> '1') AS home_sum "
        "  FROM cpbl.game_scoreboard "
        "  WHERE year = ANY(%s) AND kind_code = ANY(%s) "
        "  GROUP BY 1, 2, 3) s "
        "  ON s.year = g.year AND s.kind_code = g.kind_code "
        " AND s.game_sno = g.game_sno "
        "WHERE g.year = ANY(%s) AND g.kind_code = ANY(%s) "
        "  AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL",
        (YEARS, KINDS, YEARS, KINDS),
    )
    row = cur.fetchone() or {}
    n, ok = int(row.get("n") or 0), int(row.get("ok") or 0)
    return {
        "games_compared": n,
        "matched": ok,
        "mismatched": n - ok,
        "claim": "visiting_home_type='1' 的逐局 score_cnt 加總 == games.away_score",
    }


def main() -> int:
    full, pg_full = _run("full")
    baseline = {
        "games": full["totals"]["games"],
        "all_pass": full["totals"]["all_pass"],
        "all_pass_rate": full["totals"]["all_pass_rate"],
    }

    # --- 1. 分母不變量 -----------------------------------------------------
    fail_sum = sum(full["fail_reasons"].values())
    invariant = {
        "games": baseline["games"],
        "all_pass": baseline["all_pass"],
        "fail_reasons_sum": fail_sum,
        "holds": baseline["games"] == baseline["all_pass"] + fail_sum,
        "meaning": (
            "被 fail-closed 擋下的場次**留在分母裡當失敗**，不從母體移除。"
            "故任何閘門只能壓低通過率、不可能抬高；"
            "「排太多」的後果是低報而非高報，「排太少」才會高報。"
        ),
    }

    # --- 2. 逐閘門消融 -----------------------------------------------------
    gates: dict[str, Any] = {}
    blocked_by: dict[str, list[str]] = defaultdict(list)
    for gid, info in pg_full.items():
        st = info["status"]
        if st != "pass":
            blocked_by[st].append(gid)

    ablation_pg: dict[str, dict[str, dict[str, Any]]] = {}
    for gate, mut in sorted(R.GATE_ABLATIONS.items()):
        blocked = blocked_by.get(gate, [])
        if not blocked:
            continue
        _, pg_mut = _run(mut)
        ablation_pg[gate] = pg_mut
        fate = Counter(pg_mut.get(g, {}).get("status", "absent") for g in blocked)
        delta = fate.get("pass", 0)
        gates[gate] = {
            "kind": "gate",
            "blocked": len(blocked),
            "blocked_share_of_population": round(len(blocked) / baseline["games"], 4),
            "ablation": mut,
            "artifact": f"mutation_{mut}.json",
            "delta_pass": delta,
            "fate_of_blocked_games": dict(sorted(fate.items(), key=lambda kv: -kv[1])),
            "verdict": "Δ=0" if delta == 0 else f"Δ=+{delta}（須逐案說明）",
        }

    for gate, spec in NO_ABLATION.items():
        n = len(blocked_by.get(gate, []))
        if not n and gate not in full["fail_reasons"]:
            continue
        n = n or full["fail_reasons"].get(gate, 0)
        ub = spec["delta_upper_bound"]
        gates[gate] = {
            "kind": spec["kind"],
            "blocked": n,
            "blocked_share_of_population": round(n / baseline["games"], 4),
            "ablation": None,
            "why_no_ablation": spec["why"],
            "delta_upper_bound": n if ub == "blocked" else int(ub),
            "delta_upper_bound_share": (
                round(n / baseline["games"], 4) if ub == "blocked" else 0.0
            ),
        }

    # --- 3. official_error_unlocated：窄化的證據與殘餘 Δ 的逐案交代 ----------
    # 窄化前的閘門（`wide_official_error_gate`）擋 62 場、Δ=+34。那 34 場**不是
    # 一種東西**：其中一部分的未定位失誤落在**一分未得的半局**，依 9.16 的半局
    # 侷限性它不可能影響任何一個對帳維度 —— 那是閘門排太多。剩下的落在有得分的
    # 半局，通過只證明總數不敏感，不證明判對。本節把兩者拆開並各給數字。
    wide, pg_wide = _run("wide_official_error_gate")
    _, pg_nsb = _run("no_scoreboard_signal")
    with psycopg.connect(R.DSN, row_factory=dict_row) as conn:
        mapping_check = _verify_half_mapping(conn)

    severity = {"er_irrelevant": 0, "runs_unknown": 1, "er_possible": 2}

    def _classify_case(gid: str, src: dict[str, dict[str, Any]]) -> dict[str, Any]:
        halves = src[gid].get("gate_info", {}).get("unlocated", [])
        details, worst = [], "er_irrelevant"
        for u in halves:
            runs = u.get("half_runs")
            cls = ("runs_unknown" if runs is None
                   else "er_irrelevant" if runs == 0 else "er_possible")
            if severity[cls] > severity[worst]:
                worst = cls
            details.append({
                "half": f"{u['inning']}/{u['half']}", "official_E": u["n_err"],
                "half_runs": runs, "missing_livelog": u["missing_livelog"],
                "class": cls,
            })
        return {"game": gid, "class": worst, "halves": details}

    wide_blocked = sorted(
        g for g, v in pg_wide.items() if v["status"] == "official_error_unlocated"
    )
    rows = []
    for gid in wide_blocked:
        row = _classify_case(gid, pg_wide)
        row["ablated_status"] = pg_nsb.get(gid, {}).get("status", "absent")
        row["narrowed_status"] = pg_full.get(gid, {}).get("status", "absent")
        rows.append(row)
    xtab: Counter[str] = Counter()
    for r in rows:
        xtab[f"{r['class']}×{'pass' if r['ablated_status'] == 'pass' else 'fail'}"] += 1
    narrowed_away = [r for r in rows if r["narrowed_status"] != "official_error_unlocated"]
    cases = {
        "half_inning_mapping_check": mapping_check,
        "classification_rule": (
            "官方記分板說有失誤、逐球敘述沒寫的那個半局，若該半局攻方得分為 0，"
            "則 9.16 的失誤效果（(b) 失誤致得分非自責、(d) 無失誤重建、漏接第三"
            "出局後該半局續打）沒有任何分可以作用；本檔的帳本也逐半局重置，"
            "故該場三維判定不受這個看不見的失誤影響 ⇒ er_irrelevant。"
            "該半局有得分 ⇒ er_possible（判不了）；記分板無該局列 ⇒ runs_unknown"
            "（fail-closed 併入判不了）。一場有多個未定位失誤時取最嚴格者。"
        ),
        "narrowing": {
            "wide_gate_mutation": "wide_official_error_gate",
            "wide_blocked": len(wide_blocked),
            "wide_all_pass": wide["totals"]["all_pass"],
            "wide_all_pass_rate": wide["totals"]["all_pass_rate"],
            "narrowed_blocked": len(blocked_by.get("official_error_unlocated", [])),
            "narrowed_all_pass": baseline["all_pass"],
            "narrowed_all_pass_rate": baseline["all_pass_rate"],
            "delta_from_narrowing": baseline["all_pass"] - wide["totals"]["all_pass"],
            "narrowed_away_games": len(narrowed_away),
            "narrowed_away_all_er_irrelevant": all(
                r["class"] == "er_irrelevant" for r in narrowed_away
            ),
            "fate_of_narrowed_away": dict(sorted(
                Counter(r["narrowed_status"] for r in narrowed_away).items(),
                key=lambda kv: -kv[1],
            )),
        },
        "crosstab_class_x_ablated_outcome_over_wide_blocked": dict(sorted(xtab.items())),
        "residual_delta_after_narrowing": {
            "gate": "official_error_unlocated（窄化後）",
            "blocked": len(blocked_by.get("official_error_unlocated", [])),
            "delta_pass": gates.get("official_error_unlocated", {}).get("delta_pass"),
            "why_still_unjudgeable": (
                "窄化後剩下的都是「未定位失誤所在半局有得分」。那些分的自責／非自責"
                "取決於失誤發生在哪一球，而**那正是缺的資訊**：逐球敘述沒寫，記分板"
                "只給半局計數。我方重建把該半局所有進壘一律當無失誤 ⇒ 預設判為自責。"
                "官方若剛好也全記自責，三維就會吻合 —— 但那證明的是「總數對這個未知"
                "不敏感」，不是「我們判對了」。能分辨兩者的證據就是缺的那一項，"
                "故通過不可作為判定能力的證據，維持 fail-closed。"
            ),
        },
        "cases": rows,
    }

    # --- 4. scorer_unresolved 的 Δ 為何不是「閘門排太多」---------------------
    # 該閘門觸發於：得分敘述明寫「N壘跑者<某人>回本壘得分」，而重建帳本在那個壘上
    # 沒有這個人。消融不是「放行一個判得出來的場次」，而是**用一個敘述明文否定的
    # 歸屬去頂替**：那一分會走到打者路徑，記給**當下投手**、用**打者的上壘手段**
    # 判自責。敘述說得分的是壘上跑者，打者依定義不是壘上跑者 —— 代換值已知為假。
    # 三維吻合只證明總數對這個代換不敏感（例如該半局只有一位投手時，逐投手 runs
    # 對「誰得分」完全無鑑別力），不證明歸屬判對。
    su_rows = []
    for gid in sorted(blocked_by.get("scorer_unresolved", [])):
        gi = pg_full[gid].get("gate_info", {}).get("unresolved_scorer", {})
        su_rows.append({
            "game": gid,
            "ablated_status": ablation_pg.get("scorer_unresolved", {})
            .get(gid, {}).get("status", "absent"),
            **gi,
        })
    su_pass = [r for r in su_rows if r["ablated_status"] == "pass"]
    scorer_detail = {
        "blocked": len(su_rows),
        "delta_pass": len(su_pass),
        "substituted_attribution": (
            "當下投手 ＋ 打者的上壘手段（敘述明文否定：得分者是壘上跑者，不是打者）"
        ),
        "pass_cases_pitchers_in_half": dict(sorted(
            Counter(r.get("pitchers_in_half") for r in su_pass).items(),
            key=lambda kv: (kv[0] is None, kv[0]),
        )),
        "pass_cases_single_pitcher_half": sum(
            1 for r in su_pass if r.get("pitchers_in_half") == 1
        ),
        "why_pass_is_not_evidence": (
            "該半局只有一位投手時，逐投手 runs 對「得分的是哪一位跑者」毫無鑑別力"
            "——代換再怎麼錯，runs 維都會吻合。剩下的鑑別力只在 ER，而 ER 要看的"
            "正是那位無法定位的跑者當初怎麼上壘，那份資訊就是缺的那一項。"
            "故通過只能說明總數對代換不敏感，不能作為「判得出來」的證據。"
        ),
        "cases": su_rows,
    }

    out = {
        "data_asof": full["data_asof"],
        "scope": full["scope"],
        "baseline": baseline,
        "denominator_invariant": invariant,
        "gates": dict(sorted(gates.items())),
        "official_error_unlocated_cases": cases,
        "scorer_unresolved_detail": scorer_detail,
    }
    path = Path(__file__).with_name("gate_ablation.json")
    path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {"baseline": baseline, "denominator_invariant": invariant,
         "gates": {k: {kk: vv for kk, vv in v.items()
                       if kk in ("blocked", "ablation", "delta_pass",
                                 "delta_upper_bound", "fate_of_blocked_games")}
                   for k, v in out["gates"].items()},
         "oeu_narrowing": cases["narrowing"],
         "oeu_crosstab_over_wide_blocked":
             cases["crosstab_class_x_ablated_outcome_over_wide_blocked"],
         "scorer_unresolved": {
             k: v for k, v in scorer_detail.items()
             if k in ("blocked", "delta_pass", "pass_cases_pitchers_in_half")}},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
