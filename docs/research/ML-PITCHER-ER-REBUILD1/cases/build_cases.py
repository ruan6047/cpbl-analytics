"""`earned_rule_boundary` 分層討論案例集產生器（唯讀，不改任何計算碼）。

需求方裁定不做 759 場全量人工判讀，改用討論方式挑代表場次看有沒有遺漏的因素。
本檔把該群依**可觀測特徵**切層、輸出每層的場數／佔比，並以**明確且不可挑選**的
規則選代表場次，逐字附上 livelog。

用法：
    uv run python docs/research/ML-PITCHER-ER-REBUILD1/cases/build_cases.py

輸出：同目錄 `STRATA.md` ＋ `stratum_*.md`。
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

from rebuild_er import (  # noqa: E402
    DSN,
    ERROR_MARKERS,
    EVENT_COLS,
    _classify,
    _s,
    rebuild_game,
)

from cpbl.ingest.pa_build import load_taxonomy  # noqa: E402

# 打者上壘型失誤 vs 跑者進壘型失誤：兩者在 9.16 的條款不同（(b)(3)/(c) vs (d)），
# 分層時必須分開，否則會把兩種成因混成一群。
RUNNER_ADV_RE = re.compile(r"[一二三]壘跑者[^。]{0,40}?(失誤|捕逸|妨礙|漏接)")
BATTER_REACH_RE = re.compile(r"(打者|擊出)[^。]{0,40}?(失誤|漏接)[^。]{0,10}?上[一二三]壘")

# 每群的成因假設。分類：(a) 規則有明文、我們沒實作／(b) 記錄員判斷、無法程式化／
# (c) 現場紀錄與最終官方紀錄不同調／(d) 我們的解析有 bug／(e) 不知道。
# key＝(方向, 失誤位置)，適用於該組合的所有差值大小。
HYPOTHESES: dict[tuple[str, str], tuple[str, str]] = {
    ("多算", "打者上壘型"): ("a", "9.16(a) 後段『3 個出局機會』的重建不完整。三場代表"
        "案例同一機制：失誤抵銷掉的出局要計入出局機會，且**該 play 的出局機會應在"
        "該 play 的得分之前結算**。本實作先記分後累加，故該分被判自責。"
        "候選修法存在但**尚未套用**——naive 版（`out_before_run`）實測更差，因為它"
        "沒有區分 5.08(a) 的『打者未達一壘即成立第 3 出局』與高飛犧牲打之類的時間差 play。"),
    ("多算", "跑者進壘型"): ("a", "同上，但失誤發生在跑者進壘側；另含本實作對"
        "『失誤發生在打者側、跑者於同一 play 得分』未標記污染的情形（跑者的進壘敘述"
        "不帶失誤字樣，逐跑者 taint 因此漏掉）。"),
    ("少算", "跑者進壘型"): ("b", "9.16(d)【註 1】第二句的記錄員判斷：『即使無該失誤"
        "行為幫助，基於其後成為自責分之因素亦得以進壘而得分時，應記自責分』。"
        "內含一個 (a) 子缺口：9.16(a) **明列盜壘為自責分之因素**，而本實作的 taint "
        "上限只由打者推進數決定，未為盜壘留出口（實例 `2018/A/57` 六局下雙盜壘回本壘）。"),
    ("少算", "打者上壘型"): ("b", "同 9.16(d)【註 1】第二句的判斷方向，樣本小。"),
    ("多算", "兩者皆有"): ("e", "同一半局內失誤同時出現在打者與跑者側，兩種機制疊加，"
        "無法由分層特徵單獨判定，需逐案。"),
    ("少算", "兩者皆有"): ("e", "同上。"),
    ("同場雙向", "兩者皆有"): ("d", "同場出現雙向差異且失分守恆 ⇒ 責任歸屬邊界殘留"
        "（9.16(g)/(h)），非自責分判定本身。"),
    ("同場雙向", "跑者進壘型"): ("d", "同上。"),
    ("同場雙向", "打者上壘型"): ("d", "同上。"),
    ("多算", "無失誤敘述"): ("c", "該半局逐球敘述完全無失誤性字樣，且官方逐局 E 亦為 0"
        "（否則會先被 `official_error_unlocated` 攔下）。官方判非自責的依據**不在逐球"
        "紀錄裡**——最可能是未被描述的捕逸／妨礙，或現場紀錄與事後更正的最終紀錄不同調。"
        "**此假設在現有資料上不可證偽**，理由見 RESULTS.md §7.6。"),
    ("少算", "無失誤敘述"): ("c", "同上，方向相反。"),
    ("多算", "有標記未分類"): ("e", "有失誤標記但不落在既有兩種位置樣態，需逐案。"),
    ("少算", "有標記未分類"): ("e", "同上。"),
}

NOISE = re.compile(r"^(壞球。|好球沒揮棒。|揮棒落空。|擊出界外球。|教練暫停|界外球。)\s*$")
KEEP = re.compile(
    r"出局|上壘|安打|得分|失誤|捕逸|妨礙|暴投|更換|盜壘|牽制|全壘打|犧牲|趁傳|殘壘|"
    r"比賽結束|突破僵局|投手犯規|不死三振|觸身"
)


def code_fingerprint() -> tuple[str, str]:
    """(rebuild_er.py 的 blob SHA, 產生時的 repo HEAD)。

    內容由**計算碼**決定，故以 blob SHA 為主識別；HEAD 僅供追溯（重跑會變）。
    """
    blob = subprocess.run(
        ["git", "hash-object", str(HERE.parent / "rebuild_er.py")],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout.strip()
    return blob, head


def features(events: list[dict[str, Any]], diverging: set[str]) -> dict[str, Any]:
    """由差異投手的**掉分半局**取可觀測特徵。"""
    halves: dict[tuple, list[dict]] = defaultdict(list)
    for e in events:
        if e["pitcher_acnt"] in diverging:
            halves[(e["inning_seq"], _s(e["visiting_home_type"]))].append(e)
    marks: Counter = Counter()
    runner_adv = batter_reach = n_err_events = 0
    pitching_change = False
    scoring_halves: list[tuple] = []
    for hk, rows in halves.items():
        rows.sort(key=lambda r: r["main_event_no"])
        col = "visiting_score" if hk[1] == "1" else "home_score"
        sc = [r[col] for r in rows if r[col] is not None]
        if not sc or max(sc) == min(sc):
            continue
        scoring_halves.append(hk)
        txt = "\n".join(_s(r["content"]) for r in rows)
        for m in ERROR_MARKERS:
            if m in txt:
                marks[m] += 1
        runner_adv += len(RUNNER_ADV_RE.findall(txt))
        batter_reach += len(BATTER_REACH_RE.findall(txt))
        n_err_events += sum(
            1 for r in rows if any(m in _s(r["content"]) for m in ERROR_MARKERS)
        )
        if "更換投手" in txt:
            pitching_change = True
    if runner_adv and batter_reach:
        loc = "both"
    elif runner_adv:
        loc = "runner_adv"
    elif batter_reach:
        loc = "batter_reach"
    elif marks:
        loc = "other_marker"
    else:
        loc = "none"
    return {
        "markers": dict(marks),
        "location": loc,
        "n_err_events": n_err_events,
        "pitching_change": pitching_change,
        "scoring_halves": scoring_halves,
        "rows_in_scoring_halves": sum(len(halves[h]) for h in scoring_halves),
    }


def main() -> None:
    blob, head = code_fingerprint()
    tax = load_taxonomy()
    recs: list[dict[str, Any]] = []

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT year, kind_code, game_sno FROM cpbl.game_livelog "
            "WHERE year BETWEEN 2018 AND 2026 AND kind_code = ANY(%s) ORDER BY 1,2,3",
            (["A", "D"],),
        )
        games = [(r["year"], r["kind_code"], r["game_sno"]) for r in cur.fetchall()]
        for y, k, s in games:
            cur.execute(
                f"SELECT {EVENT_COLS}, hitter_name, pitcher_name FROM cpbl.game_livelog "  # noqa: S608
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (y, k, s),
            )
            events = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT pitcher_acnt, pitcher_name, visiting_home_type, "
                "inning_pitched_cnt, inning_pitched_div3, runs, earned_runs "
                "FROM cpbl.pitching_gamelog WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (y, k, s),
            )
            official = {r["pitcher_acnt"]: r for r in cur.fetchall()}
            if not official:
                continue
            cur.execute(
                "SELECT inning_seq, visiting_home_type, error_cnt FROM cpbl.game_scoreboard "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (y, k, s),
            )
            oe: dict[tuple[int, str], int] = {}
            for r in cur.fetchall():
                if r["inning_seq"] is None or r["error_cnt"] is None:
                    continue
                hf = "2" if _s(r["visiting_home_type"]) == "1" else "1"
                ek = (int(r["inning_seq"]), hf)
                oe[ek] = oe.get(ek, 0) + int(r["error_cnt"])
            try:
                res = rebuild_game(y, k, s, events, tax, official_errors=oe)
            except Exception:  # noqa: BLE001
                continue
            if not res.ok:
                continue
            diffs = []
            for a, r in official.items():
                d_er = res.er.get(a, 0) - int(r["earned_runs"] or 0)
                if d_er:
                    diffs.append({"acnt": a, "name": r["pitcher_name"], "d": d_er,
                                  "off": int(r["earned_runs"] or 0), "mine": res.er.get(a, 0),
                                  "side": r["visiting_home_type"],
                                  "off_r": int(r["runs"] or 0), "mine_r": res.runs.get(a, 0),
                                  "off_o": (r["inning_pitched_cnt"] or 0) * 3
                                           + (r["inning_pitched_div3"] or 0),
                                  "mine_o": res.outs.get(a, 0)})
            if not diffs or _classify(res, official) != "earned_rule_boundary":
                continue
            signs = {1 if d["d"] > 0 else -1 for d in diffs}
            direction = "mixed" if len(signs) > 1 else ("er+" if 1 in signs else "er-")
            mag = max(abs(d["d"]) for d in diffs)
            f = features(events, {d["acnt"] for d in diffs})
            recs.append({"gid": f"{y}/{k}/{s}", "y": y, "k": k, "s": s,
                         "diffs": diffs, "direction": direction, "mag": mag, **f})

    # ---- 分層 --------------------------------------------------------------
    def stratum(r: dict) -> str:
        d = {"er+": "多算", "er-": "少算", "mixed": "同場雙向"}[r["direction"]]
        m = "差1分" if r["mag"] == 1 else "差2分以上"
        loc = {"runner_adv": "跑者進壘型", "batter_reach": "打者上壘型",
               "both": "兩者皆有", "other_marker": "有標記未分類", "none": "無失誤敘述"}[r["location"]]
        return f"{d}｜{m}｜{loc}"

    by: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by[stratum(r)].append(r)
    total = len(recs)

    hdr = (f"> 產生自 `rebuild_er.py` blob `{blob}`；產生時 repo HEAD `{head}`"
           f"（HEAD 僅供追溯，重跑會變，內容由 blob 決定）。\n"
           f"> 由 `cases/build_cases.py` 產生，勿手改。\n")

    lines = [f"# `earned_rule_boundary` 分層（母體 {total} 場）\n", hdr,
             "\n| 群 | 場數 | 佔比 | 多重事件 | 含換投 |",
             "|---|---|---|---|---|"]
    for name, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        multi = sum(1 for r in rs if r["n_err_events"] > 1)
        pc = sum(1 for r in rs if r["pitching_change"])
        lines.append(f"| {name} | {len(rs)} | {len(rs)/total:.1%} | {multi} | {pc} |")

    lines.append("\n## 方向 × 差值（主線索）\n")
    lines.append("| | 差1分 | 差2分以上 | 小計 |")
    lines.append("|---|---|---|---|")
    for d in ("er+", "er-", "mixed"):
        a = sum(1 for r in recs if r["direction"] == d and r["mag"] == 1)
        b = sum(1 for r in recs if r["direction"] == d and r["mag"] > 1)
        lines.append(f"| {d} | {a} | {b} | {a+b} |")

    lines.append("\n## 每群的成因假設\n")
    lines.append("| 群 | 場數 | 類別 | 假設 |")
    lines.append("|---|---|---|---|")
    for name, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        d, _m, loc = name.split("｜")
        cls, why = HYPOTHESES.get((d, loc), ("e", "未分類"))
        lines.append(f"| {name} | {len(rs)} | **({cls})** | {why} |")

    lines.append("\n## 失誤標記出現頻率（可複選，分母＝該方向場數）\n")
    lines.append("| 標記 | 多算群 | 少算群 |")
    lines.append("|---|---|---|")
    for m in ERROR_MARKERS:
        p = sum(1 for r in recs if r["direction"] == "er+" and m in r["markers"])
        n = sum(1 for r in recs if r["direction"] == "er-" and m in r["markers"])
        np_, nn = (sum(1 for r in recs if r["direction"] == d) for d in ("er+", "er-"))
        lines.append(f"| {m} | {p}/{np_} ({p/max(np_,1):.0%}) | {n}/{nn} ({n/max(nn,1):.0%}) |")

    (HERE / "STRATA.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- 每群代表場次 ------------------------------------------------------
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        for name, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
            if len(rs) < 3:
                continue
            # 選取規則：掉分半局逐球列數**最少**者優先（僅為可讀性，與內容無關），
            # 同列數則依 gid。刻意不用「最好講」之類的主觀準則。
            chosen = sorted(rs, key=lambda r: (r["rows_in_scoring_halves"], r["gid"]))[:3]
            out = [f"# {name}（{len(rs)} 場，佔 {len(rs)/total:.1%}）\n", hdr,
                   "\n選取規則：該群中**掉分半局逐球列數最少**的 3 場（僅為可讀性），"
                   "同列數依場次 ID 排序。\n"]
            for rec in chosen:
                y, k, s = rec["y"], rec["k"], rec["s"]
                cur.execute("SELECT game_date, home_team_name, away_team_name, home_score, "
                            "away_score FROM cpbl.games WHERE year=%s AND kind_code=%s "
                            "AND game_sno=%s", (y, k, s))
                g = cur.fetchone() or {}
                out.append(f"\n### `{rec['gid']}`　{g.get('game_date')}　"
                           f"{g.get('away_team_name')} {g.get('away_score')} : "
                           f"{g.get('home_score')} {g.get('home_team_name')}\n")
                out.append("| 投手 | 主客 | 官方 outs | 重建 | 官方 R | 重建 | 官方 ER | 重建 |")
                out.append("|---|---|---|---|---|---|---|---|")
                for d in rec["diffs"]:
                    out.append(f"| {d['name']} | {'客' if _s(d['side'])=='1' else '主'} | "
                               f"{d['off_o']} | {d['mine_o']} | {d['off_r']} | {d['mine_r']} | "
                               f"**{d['off']}** | **{d['mine']}** |")
                cur.execute(
                    f"SELECT {EVENT_COLS}, hitter_name, pitcher_name FROM cpbl.game_livelog "  # noqa: S608
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s ORDER BY main_event_no",
                    (y, k, s))
                evs = [dict(r) for r in cur.fetchall()]
                for hk in rec["scoring_halves"]:
                    out.append(f"\n**{hk[0]} 局{'上' if hk[1]=='1' else '下'}**（逐字）\n")
                    out.append("```")
                    for e in evs:
                        if (e["inning_seq"], _s(e["visiting_home_type"])) != hk:
                            continue
                        c = re.sub(r"[\r\n]+", " ", _s(e["content"])).strip()
                        if not c or not KEEP.search(c):
                            continue
                        b = "".join(x or "-" for x in (e["first_base"], e["second_base"],
                                                       e["third_base"]))
                        out.append(f"{e['main_event_no']} out{e['out_cnt']} 壘[{b}] "
                                   f"{e['visiting_score']}:{e['home_score']} "
                                   f"P={e['pitcher_name']} B={e['hitter_name']} "
                                   f"[{e['action_name']}] {c}")
                    out.append("```")
            fn = "stratum_" + re.sub(r"[^\w]", "_", name) + ".md"
            (HERE / fn).write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"母體 {total} 場，{len(by)} 群")
    for name, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"  {name:36} {len(rs):4}  {len(rs)/total:6.1%}")


if __name__ == "__main__":
    main()
