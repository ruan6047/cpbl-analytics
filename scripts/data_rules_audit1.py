"""DATA-RULES-AUDIT1：規章→資料判讀的偽陽偽陰審計（**唯讀**）。

每個候選一個 subcommand，輸出 JSON artifact 供報告引用。**所有宣稱由本腳本產生**，
禁止人工計數。用法：

    uv run python scripts/data_rules_audit1.py c6 --out docs/research/DATA-RULES-AUDIT1_C6.json

設計紀律：
* 只跑 SELECT；不寫入任何表（db_scope=read）。
* 島（island）重建與 :mod:`cpbl.ingest.splits_calc` 的 ``calc_t2`` 對齊：
  ``(game_sno, inning_seq, visiting_home_type, hitter_acnt)`` 連續段，
  換人列不切界；canonical PA 則直接讀 ``cpbl.game_plate_appearances``。
* 樣本一律附 ID（year/kind/game_sno/main_event_no）讓查核者可逐例覆驗。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from typing import Any

from cpbl.db import conn

KINDS = ("A", "C", "D", "E")
SAMPLE_N = 25


def _rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _dump(obj: Any, out: str | None) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"written: {out} ({len(text)} bytes)")
    else:
        print(text)


# ---------------------------------------------------------------------------
# 共用：canonical PA + 其成員 livelog 列
# ---------------------------------------------------------------------------
_PA_MEMBER_SQL = """
SELECT pa.pa_row_id, pa.year, pa.kind_code, pa.game_sno, pa.pa_index,
       pa.hitter_acnt, pa.result_action, pa.outcome_family, pa.state,
       pa.start_event_no, pa.end_event_no,
       ll.main_event_no, ll.inning_seq, ll.visiting_home_type, ll.batting_order,
       ll.ball_cnt, ll.strike_cnt, ll.pitch_cnt, ll.out_cnt,
       ll.is_ball, ll.is_strike, ll.is_change_player, ll.is_score,
       ll.content, ll.action_name, ll.batting_action_name,
       ll.hitter_acnt AS row_hitter, ll.pitcher_acnt,
       ll.first_base, ll.second_base, ll.third_base,
       ll.visiting_score, ll.home_score
FROM cpbl.game_plate_appearances pa
JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
JOIN cpbl.game_pa_events ev ON ev.pa_row_id = pa.pa_row_id
JOIN cpbl.game_livelog ll
  ON ll.year = ev.year AND ll.kind_code = ev.kind_code
 AND ll.game_sno = ev.game_sno AND ll.main_event_no = ev.event_no
WHERE {where}
ORDER BY pa.year, pa.kind_code, pa.game_sno, pa.pa_index, ll.main_event_no::bigint
"""


def _pa_groups(cur, where: str, params: tuple) -> dict[int, list[dict]]:
    cur.execute(_PA_MEMBER_SQL.format(where=where), params)
    groups: dict[int, list[dict]] = defaultdict(list)
    for r in _rows(cur):
        groups[r["pa_row_id"]].append(r)
    return groups


# ===========================================================================
# 候選 6｜投球中途改判故意四壞（規則 9.14(b)(d)）
# ===========================================================================
def cand6(cur) -> dict:
    """四壞家族 PA 的實際壞球數分布，找出 <4 壞球的保送（改判/手勢故四）。"""
    out: dict[str, Any] = {"rule_anchor": {
        "file": "docs/reference/棒球規則.txt",
        "lines": "6001-6018",
        "quote_9_14_a": "投出 4 個壞球於好球帶外，裁判員宣判擊球員上一壘時，記錄為四壞球",
        "quote_9_14_b": "所謂故意四壞球，應指投手無企圖對擊球員投最後 1 球進入好球帶，且故意投偏給在捕手區外之捕手",
        "quote_9_14_d": "對於守方總教練通知裁判員意圖讓擊球員上一壘時，記錄員應記錄為故意四壞球",
    }}

    groups = _pa_groups(cur, "pa.outcome_family = 'walk'", ())
    dist: Counter = Counter()
    by_action: dict[str, Counter] = defaultdict(Counter)
    anomalies: list[dict] = []
    per_year: dict[str, Counter] = defaultdict(Counter)
    for pid, members in groups.items():
        head = members[0]
        real = [m for m in members if m["is_ball"] or m["is_strike"]]
        balls = sum(1 for m in real if m["is_ball"])
        strikes = sum(1 for m in real if m["is_strike"])
        action = head["result_action"] or ""
        key = (balls, len(real))
        dist[key] += 1
        by_action[action][balls] += 1
        yk = f"{head['year']}/{head['kind_code']}"
        per_year[yk]["walk_pa"] += 1
        if action == "故意四壞球":
            per_year[yk]["ibb"] += 1
            if balls == 0:
                per_year[yk]["ibb_zero_ball"] += 1
        if balls < 4:
            per_year[yk]["balls_lt_4"] += 1
            anomalies.append({
                "pa_row_id": pid, "year": head["year"], "kind": head["kind_code"],
                "game_sno": head["game_sno"], "pa_index": head["pa_index"],
                "hitter_acnt": head["hitter_acnt"], "result_action": action,
                "balls": balls, "strikes": strikes, "pitch_rows": len(real),
                "start_event_no": head["start_event_no"],
                "end_event_no": head["end_event_no"],
                "last_content": (members[-1]["content"] or "")[:120],
            })
    out["walk_pa_total"] = sum(dist.values())
    out["ball_count_distribution"] = [
        {"balls": b, "pitch_rows": p, "n": n}
        for (b, p), n in sorted(dist.items())
    ]
    out["by_result_action"] = {
        a: {str(b): n for b, n in sorted(c.items())} for a, c in sorted(by_action.items())
    }
    out["per_year"] = {k: dict(v) for k, v in sorted(per_year.items())}
    out["anomaly_total"] = sum(v.get("balls_lt_4", 0) for v in per_year.values())
    out["anomaly_samples"] = anomalies[:SAMPLE_N]
    out["anomaly_all"] = anomalies

    # 壞球數 = 4 但總投球列 = 0 的（純 award）已由 IBB-GHOST1 覆蓋；此處交叉列出
    zero_pitch = [a for a in anomalies if a["pitch_rows"] == 0]
    out["zero_pitch_walk_total"] = len(zero_pitch)
    out["zero_pitch_by_action"] = dict(Counter(a["result_action"] for a in zero_pitch))

    # 對照組：一般四壞 vs 故四的「終局列是否帶投球旗標」——判定 award-without-pitch
    cur.execute("""
        SELECT action_name,
               count(*) FILTER (WHERE is_ball) AS terminal_is_ball,
               count(*) FILTER (WHERE is_strike) AS terminal_is_strike,
               count(*) FILTER (WHERE NOT is_ball AND NOT is_strike) AS terminal_no_pitch,
               count(*) AS n
        FROM cpbl.game_livelog
        WHERE action_name IN ('四壞球','故意四壞球','裁定四壞球')
          AND content LIKE '%%四壞球上壘%%'
        GROUP BY 1 ORDER BY 1
    """)
    out["terminal_row_pitch_flag"] = _rows(cur)

    # 逐球衍生消費點 1：sabr traits 的 two_strike_*（legacy 島規則＝打者變化即切界，
    # 早於 PA1-FIX1 的代打合併），與 canonical PA 對帳
    cur.execute("""
        SELECT year, kind_code, sum(pa) AS traits_pa, count(*) AS batters
        FROM cpbl.batter_traits GROUP BY 1,2 ORDER BY 1,2
    """)
    traits = {(r["year"], r["kind_code"]): r for r in _rows(cur)}
    cur.execute("""
        SELECT pa.year, pa.kind_code,
               count(*) FILTER (WHERE pa.state='ready') AS canonical_ready,
               count(*) AS canonical_all
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        GROUP BY 1,2 ORDER BY 1,2
    """)
    cmp_rows = []
    for r in _rows(cur):
        t = traits.get((r["year"], r["kind_code"]))
        if not t:
            continue
        cmp_rows.append({
            "year": r["year"], "kind": r["kind_code"],
            "batter_traits_pa": t["traits_pa"],
            "canonical_ready_pa": r["canonical_ready"],
            "canonical_all_islands": r["canonical_all"],
            "traits_minus_ready": t["traits_pa"] - r["canonical_ready"],
        })
    out["sabr_traits_vs_canonical_pa"] = cmp_rows

    # 逐球衍生消費點 2：TrackMan 逐球映射對四壞家族 PA 的成功率
    cur.execute("""
        SELECT pa.outcome_family, m.mapping_state, count(*) AS n
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        JOIN cpbl.game_pa_pitch_mappings m ON m.pa_row_id = pa.pa_row_id
        WHERE pa.outcome_family = 'walk'
        GROUP BY 1,2 ORDER BY 3 DESC
    """)
    out["walk_pa_pitch_mapping_state"] = _rows(cur)
    return out


# ===========================================================================
# 候選 7｜暴投／投手犯規結束比賽（walk-off WP/balk）
# ===========================================================================
def cand7(cur) -> dict:
    out: dict[str, Any] = {"rule_anchor": {
        "file": "docs/reference/棒球規則.txt",
        "pa_enumeration": {
            "rule": "9.22(a)", "lines": "6480-6481",
            "quote": "打席數之總計應包括打數、四壞球、觸身球、犧牲觸擊、犧牲飛球及妨礙打擊或妨礙跑壘員的上壘等各項合計",
        },
        "incomplete_pa": {
            "rule": "9.23(b)【註】", "lines": "6542-6544",
            "quote": "球員雖出場比賽，但尚未輪到打席，比賽就已結束；或因壘上之跑壘員出局攻守交換，如此雖進入打席但未能完成擊球時，不視為連續安打及連續比賽安打之記錄中斷",
        },
        "walkoff": {"rule": "7.01(b)(1)②", "quote": "主隊於延長局之進攻中獲得決勝分時"},
    }}

    # 各場最後一個 PA（依 pa_index）
    cur.execute("""
        WITH last_pa AS (
          SELECT DISTINCT ON (pa.year, pa.kind_code, pa.game_sno)
                 pa.pa_row_id, pa.year, pa.kind_code, pa.game_sno, pa.pa_index,
                 pa.hitter_acnt, pa.result_action, pa.outcome_family, pa.state,
                 pa.start_event_no, pa.end_event_no
          FROM cpbl.game_plate_appearances pa
          JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
          ORDER BY pa.year, pa.kind_code, pa.game_sno, pa.pa_index DESC
        )
        SELECT lp.*, g.game_date, g.home_score, g.away_score
        FROM last_pa lp
        JOIN cpbl.games g ON g.year=lp.year AND g.kind_code=lp.kind_code AND g.game_sno=lp.game_sno
        ORDER BY lp.year, lp.kind_code, lp.game_sno
    """)
    last = _rows(cur)
    out["games_with_pa"] = len(last)
    out["last_pa_state_dist"] = dict(Counter(r["state"] for r in last))
    out["last_pa_family_dist"] = dict(Counter(str(r["outcome_family"]) for r in last))

    trunc = [r for r in last if r["state"] == "truncated"]
    out["last_pa_truncated_total"] = len(trunc)

    # 逐例補上該 PA 的成員列（找 得分/暴投/投手犯規 字樣）
    detail = []
    for r in trunc:
        cur.execute("""
            SELECT ll.main_event_no, ll.inning_seq, ll.visiting_home_type, ll.out_cnt,
                   ll.ball_cnt, ll.strike_cnt, ll.pitch_cnt, ll.is_score, ll.is_ball,
                   ll.is_strike, ll.action_name, ll.batting_action_name, ll.content,
                   ll.visiting_score, ll.home_score
            FROM cpbl.game_pa_events ev
            JOIN cpbl.game_livelog ll ON ll.year=ev.year AND ll.kind_code=ev.kind_code
              AND ll.game_sno=ev.game_sno AND ll.main_event_no=ev.event_no
            WHERE ev.pa_row_id = %s
            ORDER BY ll.main_event_no::bigint
        """, (r["pa_row_id"],))
        mem = _rows(cur)
        text = " ".join((m["content"] or "") for m in mem)
        detail.append({
            "pa_row_id": r["pa_row_id"], "year": r["year"], "kind": r["kind_code"],
            "game_sno": r["game_sno"], "pa_index": r["pa_index"],
            "hitter_acnt": r["hitter_acnt"], "game_date": r["game_date"],
            "final_score": f"{r['away_score']}-{r['home_score']}",
            "inning": mem[-1]["inning_seq"] if mem else None,
            "half": mem[-1]["visiting_home_type"] if mem else None,
            "scored": any(m["is_score"] for m in mem),
            "has_wp": "暴投" in text, "has_balk": "投手犯規" in text,
            "has_pb": "捕逸" in text,
            "pitch_rows": sum(1 for m in mem if m["is_ball"] or m["is_strike"]),
            "content": text[:300],
        })
    out["last_pa_truncated_detail"] = detail
    out["last_pa_truncated_scoring"] = [d for d in detail if d["scored"]]
    out["last_pa_truncated_scoring_n"] = sum(1 for d in detail if d["scored"])
    out["walkoff_cause"] = dict(Counter(
        ("wild_pitch" if d["has_wp"] else "balk" if d["has_balk"] else
         "passed_ball" if d["has_pb"] else "other")
        for d in detail if d["scored"]))

    # 全庫 truncated PA（不限終局）：確認皆不計 PA
    cur.execute("SELECT count(*) FROM cpbl.game_plate_appearances pa JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id AND b.state='published' WHERE pa.state='truncated'")
    out["truncated_pa_total"] = cur.fetchone()[0]
    cur.execute("""SELECT count(*) FROM cpbl.game_plate_appearances pa
                   JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id AND b.state='published'
                   WHERE pa.state='truncated' AND pa.outcome_family IS NOT NULL""")
    out["truncated_with_family"] = cur.fetchone()[0]

    # splits 側：這些島的 batting_action_name 是否為空（空→skipped_no_outcome，不計 PA）
    cur.execute("""
        SELECT count(*) FROM cpbl.game_plate_appearances pa
JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        JOIN cpbl.game_pa_events ev ON ev.pa_row_id=pa.pa_row_id
        JOIN cpbl.game_livelog ll ON ll.year=ev.year AND ll.kind_code=ev.kind_code
          AND ll.game_sno=ev.game_sno AND ll.main_event_no=ev.event_no
        WHERE pa.state='truncated'
          AND coalesce(ll.batting_action_name,'') <> ''
    """)
    out["truncated_rows_with_batting_action"] = cur.fetchone()[0]
    return out


# ===========================================================================
# 候選 8｜第三出局（盜壘阻殺／牽制）中斷打席，同打者次局重打
# ===========================================================================
def cand8(cur) -> dict:
    out: dict[str, Any] = {"rule_anchor": {
        "file": "docs/reference/棒球規則.txt",
        "foul_interference_third_out": {
            "rule": "6.01(a)(10)", "lines": "3484-3487",
            "quote": "若跑壘員因擊球員擊出之界外球被判妨礙守備出局，且成為第 3 出局時，則認定該擊球員已完成打擊，次擊球員為下一局首位擊球員；若為無出局或 1 出局時，則該擊球員繼續打擊",
        },
        "incomplete_pa_not_a_break": {
            "rule": "9.23(b)【註】", "lines": "6542-6544",
            "quote": "因壘上之跑壘員出局攻守交換，如此雖進入打席但未能完成擊球時，不視為連續安打及連續比賽安打之記錄中斷",
        },
        "pa_enumeration": {"rule": "9.22(a)", "lines": "6480-6481"},
    }}

    # 所有 truncated PA + 其成員摘要
    cur.execute("""
        SELECT pa.pa_row_id, pa.year, pa.kind_code, pa.game_sno, pa.pa_index,
               pa.hitter_acnt, pa.state, pa.result_action,
               min(ll.inning_seq) AS inning, min(ll.visiting_home_type) AS half,
               max(ll.out_cnt) AS max_out,
               count(*) FILTER (WHERE ll.is_ball OR ll.is_strike) AS pitch_rows,
               max(ll.ball_cnt) AS max_ball, max(ll.strike_cnt) AS max_strike,
               string_agg(coalesce(ll.content,''), ' ' ORDER BY ll.main_event_no::bigint) AS text
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        JOIN cpbl.game_pa_events ev ON ev.pa_row_id=pa.pa_row_id
        JOIN cpbl.game_livelog ll ON ll.year=ev.year AND ll.kind_code=ev.kind_code
          AND ll.game_sno=ev.game_sno AND ll.main_event_no=ev.event_no
        WHERE pa.state='truncated'
        GROUP BY 1,2,3,4,5,6,7,8
        ORDER BY 2,3,4,5
    """)
    trunc = _rows(cur)
    out["truncated_total"] = len(trunc)
    out["truncated_by_year"] = dict(Counter(f"{r['year']}/{r['kind_code']}" for r in trunc))

    def cause(text: str) -> str:
        t = text or ""
        if "盜壘刺" in t or "盜壘失敗" in t:
            return "caught_stealing"
        if "牽制" in t:
            return "pickoff"
        if "妨礙" in t:
            return "interference"
        if "夾殺" in t or "觸殺" in t:
            return "rundown_or_tag"
        if "比賽結束" in t or "再見" in t:
            return "game_end"
        return "other"

    out["truncated_cause_dist"] = dict(Counter(cause(r["text"]) for r in trunc))

    # 逐例：同打者是否在「下一個半局（同隊）」以新 PA 重新打擊
    cur.execute("""
        SELECT pa.pa_row_id, pa.year, pa.kind_code, pa.game_sno, pa.pa_index,
               pa.hitter_acnt, pa.state, pa.outcome_family,
               min(ll.inning_seq) AS inning, min(ll.visiting_home_type) AS half,
               min(ll.ball_cnt) AS first_ball, min(ll.strike_cnt) AS first_strike,
               count(*) FILTER (WHERE ll.is_ball OR ll.is_strike) AS pitch_rows
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        JOIN cpbl.game_pa_events ev ON ev.pa_row_id=pa.pa_row_id
        JOIN cpbl.game_livelog ll ON ll.year=ev.year AND ll.kind_code=ev.kind_code
          AND ll.game_sno=ev.game_sno AND ll.main_event_no=ev.event_no
        GROUP BY 1,2,3,4,5,6,7,8
        ORDER BY 2,3,4,5
    """)
    allpa = _rows(cur)
    idx: dict[tuple, list[dict]] = defaultdict(list)
    for r in allpa:
        idx[(r["year"], r["kind_code"], r["game_sno"])].append(r)

    resume: list[dict] = []
    no_resume: list[dict] = []
    for r in trunc:
        key = (r["year"], r["kind_code"], r["game_sno"])
        seq = idx[key]
        later = [x for x in seq if x["pa_index"] > r["pa_index"]
                 and x["hitter_acnt"] == r["hitter_acnt"]]
        nxt = later[0] if later else None
        rec = {
            "pa_row_id": r["pa_row_id"], "year": r["year"], "kind": r["kind_code"],
            "game_sno": r["game_sno"], "pa_index": r["pa_index"],
            "hitter_acnt": r["hitter_acnt"], "inning": r["inning"], "half": r["half"],
            "pitch_rows": r["pitch_rows"], "cause": cause(r["text"]),
            "text": (r["text"] or "")[:200],
        }
        if nxt:
            rec["next_pa_index"] = nxt["pa_index"]
            rec["next_inning"] = nxt["inning"]
            rec["next_half"] = nxt["half"]
            rec["next_state"] = nxt["state"]
            rec["next_family"] = nxt["outcome_family"]
            rec["next_first_count"] = f"{nxt['first_ball']}-{nxt['first_strike']}"
            rec["next_is_adjacent_inning"] = (
                nxt["inning"] == (r["inning"] or 0) + 1 and nxt["half"] == r["half"])
            # livelog 球數是「該球投完後」的值 → 新打席首列必 ball+strike <= 1
            rec["count_reset"] = (nxt["first_ball"] + nxt["first_strike"]) <= 1
            resume.append(rec)
        else:
            no_resume.append(rec)
    out["truncated_with_later_same_hitter_pa"] = len(resume)
    out["truncated_without_resume"] = len(no_resume)
    adj = [r for r in resume if r.get("next_is_adjacent_inning")]
    out["resume_next_inning_same_half"] = len(adj)
    out["resume_next_inning_count_reset"] = sum(1 for r in adj if r["count_reset"])
    out["resume_next_inning_count_not_reset"] = [r for r in adj if not r["count_reset"]]
    out["resume_samples"] = adj[:SAMPLE_N]
    out["no_resume_samples"] = no_resume[:SAMPLE_N]

    # 誤併檢查：同一 PA 是否跨越 >1 個 inning_seq。
    # 需區分兩種：(a) **實質列**（有打者、非換人）跨局＝島切界失效（紅線）；
    # (b) 只有換人／空打者列跨局＝build_islands 刻意把非 usable 列附掛於當前島。
    cur.execute("""
        SELECT pa.pa_row_id, pa.year, pa.kind_code, pa.game_sno, pa.pa_index, pa.state,
               count(DISTINCT ll.inning_seq) AS n_inning_all,
               count(DISTINCT ll.visiting_home_type) AS n_half_all,
               count(DISTINCT ll.inning_seq) FILTER (
                   WHERE ll.hitter_acnt IS NOT NULL AND ll.hitter_acnt <> ''
                     AND ll.is_change_player IS NOT TRUE) AS n_inning_usable,
               count(DISTINCT ll.visiting_home_type) FILTER (
                   WHERE ll.hitter_acnt IS NOT NULL AND ll.hitter_acnt <> ''
                     AND ll.is_change_player IS NOT TRUE) AS n_half_usable
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        JOIN cpbl.game_pa_events ev ON ev.pa_row_id=pa.pa_row_id
        JOIN cpbl.game_livelog ll ON ll.year=ev.year AND ll.kind_code=ev.kind_code
          AND ll.game_sno=ev.game_sno AND ll.main_event_no=ev.event_no
        GROUP BY 1,2,3,4,5,6
        HAVING count(DISTINCT ll.inning_seq) > 1 OR count(DISTINCT ll.visiting_home_type) > 1
    """)
    cross = _rows(cur)
    out["pa_spanning_any_row_multi_inning"] = len(cross)
    usable_span = [r for r in cross if r["n_inning_usable"] > 1 or r["n_half_usable"] > 1]
    out["pa_spanning_usable_row_multi_inning"] = len(usable_span)
    out["pa_spanning_usable_samples"] = usable_span[:SAMPLE_N]
    out["pa_spanning_change_row_only"] = len(cross) - len(usable_span)
    out["pa_spanning_note"] = (
        "livelog 的 ball_cnt/strike_cnt 是**該球投完後**的球數（IBB 逐列 1,2,3 遞增為證），"
        "故新打席首列必為 0-1／1-0／0-0；判定球數歸零須用 ball+strike <= 1。")

    # splits 側對照：truncated 島在 splits 是否被計為 PA
    # splits 用 batting_action_name（非 action_name）取結果；空→skipped_no_outcome
    cur.execute("""
        SELECT count(DISTINCT pa.pa_row_id)
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        JOIN cpbl.game_pa_events ev ON ev.pa_row_id=pa.pa_row_id
        JOIN cpbl.game_livelog ll ON ll.year=ev.year AND ll.kind_code=ev.kind_code
          AND ll.game_sno=ev.game_sno AND ll.main_event_no=ev.event_no
        WHERE pa.state='truncated' AND coalesce(ll.batting_action_name,'') <> ''
    """)
    out["truncated_pa_with_nonempty_batting_action"] = cur.fetchone()[0]
    return out


# ===========================================================================
# recon｜splits 島計數 vs canonical PA 全年對帳（唯讀呼叫 calc_t2）
# ===========================================================================
def recon(cur) -> dict:
    from cpbl.ingest.splits_calc import calc_t2

    cur.execute("""
        SELECT pa.year, pa.kind_code,
               count(*) FILTER (WHERE pa.state='ready') AS canonical_ready,
               count(*) FILTER (WHERE pa.state='truncated') AS canonical_truncated,
               count(*) FILTER (WHERE pa.state='non_pa') AS canonical_non_pa,
               count(*) FILTER (WHERE pa.state NOT IN ('ready','truncated','non_pa'))
                   AS canonical_other,
               count(*) AS canonical_islands
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        GROUP BY 1,2 ORDER BY 1,2
    """)
    canon = {(r["year"], r["kind_code"]): r for r in _rows(cur)}

    rows = []
    for (year, kind), cv in canon.items():
        _bat, _pit, _gofo, diag = calc_t2(year, kind, {}, {})
        snp = dict(diag["skipped_no_pitch"])
        ibb_zero = snp.get("故四", 0)
        rows.append({
            "year": year, "kind": kind,
            "splits_islands": diag["islands"],
            "splits_pa": diag["pa"],
            "splits_skipped_no_outcome": diag["skipped_no_outcome"],
            "splits_skipped_no_pitch": sum(snp.values()),
            "splits_skipped_no_pitch_ibb": ibb_zero,
            "splits_unknown_action": sum(diag["unknown_action"].values()),
            "splits_unknown_detail": dict(diag["unknown_action"]),
            "canonical_ready": cv["canonical_ready"],
            "canonical_truncated": cv["canonical_truncated"],
            "canonical_non_pa": cv["canonical_non_pa"],
            "canonical_other": cv["canonical_other"],
            "canonical_islands": cv["canonical_islands"],
            "splits_pa_minus_canonical_ready": diag["pa"] - cv["canonical_ready"],
            "identity_holds": (diag["pa"] - cv["canonical_ready"]) == -ibb_zero,
        })
    return {
        "identity": "splits_pa == canonical_ready_pa - zero_pitch_IBB_islands",
        "rows": rows,
        "identity_holds_all": all(r["identity_holds"] for r in rows),
        "identity_violations": [r for r in rows if not r["identity_holds"]],
        "total_zero_pitch_ibb_dropped": sum(r["splits_skipped_no_pitch_ibb"] for r in rows),
        "total_unknown_action": sum(r["splits_unknown_action"] for r in rows),
    }


# ===========================================================================
# 候選 9｜特殊判例結果家族（不死三振／妨礙打擊／妨害守備／妨害跑壘）
# ===========================================================================
def cand9(cur) -> dict:
    out: dict[str, Any] = {"rule_anchor": {
        "file": "docs/reference/棒球規則.txt",
        "uncaught_third_strike": {
            "rule": "9.15(a)(3)", "lines": "6027",
            "quote": "捕手未能確實接捕第 3 好球，擊球員成為跑壘員時",
        },
        "catcher_interference_ab": {
            "rule": "9.02(a)(1)(D)", "lines": "5044-5045",
            "quote": "因妨礙（Interference）、妨礙跑壘（Obstruction）、違反野手位置規定，獲進一壘時",
        },
        "obp_excludes_interference": {
            "rule": "9.21(f)【原註】", "lines": "6464-6466",
            "quote": "計算上壘率時，因妨礙（Interference）或妨礙跑壘（Obstruction）而獲得上壘者不計算在內",
        },
        "interference_not_gidp": {
            "rule": "9.02(a)(17)【原註】", "lines": "5076-5078",
            "quote": "擊球跑壘員因前位跑壘員的妨礙行為而被判出局時，不得記錄為雙殺打",
        },
        "obstruction": {"rule": "6.01(h)", "lines": "3717-3733",
                        "quote": "若發生妨礙跑壘時，裁判員應宣告「Obstruction」"},
    }}

    # (1) action_name ↔ batting_action_name 對照（splits 與 taxonomy 各讀一欄，須確認一致）
    cur.execute("""
        SELECT action_name, batting_action_name, count(*) AS n
        FROM cpbl.game_livelog
        WHERE coalesce(action_name,'') <> ''
        GROUP BY 1,2 ORDER BY 1,2
    """)
    out["action_name_to_batting_action_name"] = _rows(cur)

    # (2) 四個家族的存在性與頻次（canonical PA 側）
    cur.execute("""
        SELECT pa.result_action, pa.outcome_family, pa.state, count(*) AS n
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        WHERE pa.result_action LIKE '%%不死三振%%' OR pa.result_action LIKE '%%妨礙%%'
           OR pa.result_action LIKE '%%妨害%%' OR pa.outcome_family IN
              ('uncaught_third_strike','interference')
        GROUP BY 1,2,3 ORDER BY 4 DESC
    """)
    out["special_case_pa_counts"] = _rows(cur)

    # (3) content 字樣全史存在性（妨害跑壘／阻擋等 taxonomy 未登錄的家族）
    patterns = {
        "不死三振": "不死三振", "妨礙打擊": "妨礙打擊", "妨害打擊": "妨害打擊",
        "捕手妨礙": "捕手妨礙", "妨礙守備": "妨礙守備", "妨害守備": "妨害守備",
        "妨礙跑壘": "妨礙跑壘", "妨害跑壘": "妨害跑壘", "阻擋": "阻擋",
        "Obstruction": "Obstruction", "Interference": "Interference",
        "違規": "違規", "促請裁決": "促請裁決", "打序錯誤": "打序錯誤",
    }
    hits = {}
    for label, pat in patterns.items():
        cur.execute(
            "SELECT count(*) AS n, count(DISTINCT (year,kind_code,game_sno)) AS games, "
            "min(year) AS y0, max(year) AS y1 "
            "FROM cpbl.game_livelog WHERE content LIKE %s", (f"%{pat}%",))
        hits[label] = _rows(cur)[0]
    out["content_pattern_frequency"] = hits

    # (4) 不死三振：出局歸屬驗證——同半局 batter-out PA 是否≤3、該 PA 是否被當出局
    cur.execute("""
        SELECT pa.year, pa.kind_code, pa.game_sno, pa.pa_index, pa.result_action,
               pa.outcome_family, pa.pre_state, pa.post_state
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        WHERE pa.outcome_family = 'uncaught_third_strike'
        ORDER BY pa.year, pa.kind_code, pa.game_sno, pa.pa_index
    """)
    utk = _rows(cur)
    out["uncaught_third_strike_total"] = len(utk)
    out["uncaught_third_strike_by_action"] = dict(Counter(r["result_action"] for r in utk))
    out["uncaught_third_strike_samples"] = utk[:SAMPLE_N]

    # (5) 妨礙打擊：canonical interference + splits 的「礙打」抽樣
    cur.execute("""
        SELECT year, kind_code, game_sno, main_event_no, hitter_acnt, action_name,
               batting_action_name, left(coalesce(content,''),150) AS content
        FROM cpbl.game_livelog
        WHERE batting_action_name IN ('礙打','礙守','雙礙守')
        ORDER BY year, kind_code, game_sno, main_event_no::bigint
    """)
    interf = _rows(cur)
    out["interference_rows_total"] = len(interf)
    out["interference_rows_by_abbrev"] = dict(Counter(r["batting_action_name"] for r in interf))
    out["interference_samples"] = interf[:SAMPLE_N]

    # (6) OBP 分母語意：splits 對「礙打」只加 pa（不加 ab/bb/hbp/sf）→ 自動排除於 OBP
    from cpbl.ingest.splits_calc import PA_OUTCOME
    out["splits_mapping_special"] = {
        k: PA_OUTCOME[k] for k in ("不死三振", "礙打", "礙守", "雙礙守", "違規", "裁決",
                                   "三振", "犧短", "犧短誤", "犧選", "犧飛", "界犧飛")
        if k in PA_OUTCOME
    }
    out["splits_mapping_all_keys"] = sorted(PA_OUTCOME)
    cur.execute("""
        SELECT DISTINCT batting_action_name FROM cpbl.game_livelog
        WHERE coalesce(batting_action_name,'') <> '' ORDER BY 1
    """)
    observed = [r["batting_action_name"] for r in _rows(cur)]
    out["observed_batting_action_names"] = observed
    out["unmapped_batting_action_names"] = [a for a in observed if a not in PA_OUTCOME]
    return out


# ===========================================================================
# 候選 10｜觸擊特則＋判例雙殺
# ===========================================================================
def cand10(cur) -> dict:
    out: dict[str, Any] = {"rule_anchor": {
        "file": "docs/reference/棒球規則.txt",
        "bunt_foul_two_strike_k": {
            "rule": "9.15(a)(4)", "lines": "6028-6030",
            "quote": "第 2 好球後，擊球員觸擊成為界外球者；但觸擊球成為界外飛球被任何野手接獲者，不記錄為三振，給予接獲者刺殺之記錄",
        },
        "bunt_foul_batter_out": {
            "rule": "5.09(a)(4)", "lines": "2388",
            "quote": "第 3 好球觸擊成為界外球",
        },
        "sac_bunt_not_ab": {
            "rule": "9.02(a)(1)(A)", "lines": "5037", "quote": "犧牲觸擊或犧牲飛球",
        },
        "interference_not_gidp": {
            "rule": "9.02(a)(17)【原註】", "lines": "5076-5078",
            "quote": "擊球跑壘員因前位跑壘員的妨礙行為而被判出局時，不得記錄為雙殺打",
        },
    }}

    # (1) 異型 K：三振/第三好球觸擊失敗 的存在性與末球型態
    cur.execute("""
        SELECT pa.result_action, pa.outcome_family, count(*) AS n,
               min(pa.year) AS y0, max(pa.year) AS y1
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        WHERE pa.result_action LIKE '%%三振%%'
        GROUP BY 1,2 ORDER BY 3 DESC
    """)
    out["strikeout_action_variants"] = _rows(cur)

    # 異型 K 的末球（終結事件）是否為界外球，以及 is_strike 旗標
    cur.execute("""
        SELECT pa.year, pa.kind_code, pa.game_sno, pa.pa_index, pa.result_action,
               ll.main_event_no, ll.ball_cnt, ll.strike_cnt, ll.is_strike, ll.is_ball,
               left(coalesce(ll.content,''),120) AS content
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        JOIN cpbl.game_livelog ll ON ll.year=pa.year AND ll.kind_code=pa.kind_code
          AND ll.game_sno=pa.game_sno AND ll.main_event_no=pa.end_event_no
        WHERE pa.result_action = '三振/第三好球觸擊失敗'
        ORDER BY pa.year, pa.kind_code, pa.game_sno, pa.pa_index
    """)
    bunt_k = _rows(cur)
    out["bunt_foul_k_total"] = len(bunt_k)
    out["bunt_foul_k_terminal_is_strike"] = sum(1 for r in bunt_k if r["is_strike"])
    out["bunt_foul_k_terminal_strike_cnt_dist"] = dict(
        Counter(r["strike_cnt"] for r in bunt_k))
    out["bunt_foul_k_samples"] = bunt_k[:SAMPLE_N]

    # (2) 觸擊全樣本：content 帶「觸擊/短打」的島 → 結果分布（反查漏型）
    cur.execute("""
        SELECT ll.batting_action_name, ll.action_name, count(*) AS n
        FROM cpbl.game_livelog ll
        WHERE ll.content LIKE '%%觸擊%%' OR ll.content LIKE '%%短打%%'
        GROUP BY 1,2 ORDER BY 3 DESC
    """)
    out["bunt_content_result_distribution"] = _rows(cur)

    # (3) 犧短家族 PA/AB 語意
    from cpbl.ingest.splits_calc import PA_OUTCOME
    out["sac_bunt_mapping"] = {k: PA_OUTCOME[k] for k in ("犧短", "犧短誤", "犧選")}
    cur.execute("""
        SELECT batting_action_name, count(*) AS n, min(year) AS y0, max(year) AS y1
        FROM cpbl.game_livelog
        WHERE batting_action_name IN ('犧短','犧短誤','犧選')
        GROUP BY 1 ORDER BY 2 DESC
    """)
    out["sac_bunt_counts"] = _rows(cur)

    # (4) 妨礙守備形成雙殺：雙殺打 妨礙守備 / 雙礙守
    cur.execute("""
        SELECT pa.year, pa.kind_code, pa.game_sno, pa.pa_index, pa.result_action,
               pa.outcome_family, pa.pre_state, pa.post_state
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        WHERE pa.result_action IN ('雙殺打 妨礙守備','妨礙守備','三振/妨礙')
        ORDER BY pa.year, pa.kind_code, pa.game_sno, pa.pa_index
    """)
    dpi = _rows(cur)
    out["interference_dp_total"] = len(dpi)
    out["interference_dp_by_action"] = dict(Counter(r["result_action"] for r in dpi))
    out["interference_dp_samples"] = dpi[:SAMPLE_N]

    # GIDP 來源確認：splits 的 gidp 只來自官方 T1（PA_OUTCOME 無 gidp 鍵）
    out["pa_outcome_has_gidp_key"] = any(
        "gidp" in v for v in PA_OUTCOME.values())
    return out


# ===========================================================================
# 候選 12｜系統時區與窗口邊界
# ===========================================================================
def cand12(cur) -> dict:
    out: dict[str, Any] = {}
    cur.execute("SHOW timezone")
    out["db_timezone"] = cur.fetchone()[0]
    cur.execute("SELECT CURRENT_DATE, now(), now() AT TIME ZONE 'Asia/Taipei', "
                "current_setting('TimeZone'), version()")
    r = cur.fetchone()
    out["db_current_date"] = str(r[0])
    out["db_now"] = str(r[1])
    out["db_now_taipei"] = str(r[2])
    out["db_timezone_setting"] = r[3]
    out["db_version"] = r[4]
    cur.execute("SELECT (now() AT TIME ZONE 'Asia/Taipei')::date AS taipei_date, "
                "CURRENT_DATE AS current_date_val, "
                "((now() AT TIME ZONE 'Asia/Taipei')::date - CURRENT_DATE) AS day_delta")
    out["date_delta"] = _rows(cur)[0]

    # 完成場判定在「未來日期保留賽」上的行為
    cur.execute("""
        SELECT year, kind_code, game_sno, game_date, home_score, away_score, delay_kind
        FROM cpbl.games
        WHERE home_score + away_score > 0 AND game_date > CURRENT_DATE
        ORDER BY game_date
    """)
    out["future_dated_with_score"] = _rows(cur)
    cur.execute("""
        SELECT count(*) AS n FROM cpbl.games
        WHERE home_score + away_score > 0
          AND game_date = CURRENT_DATE
    """)
    out["today_dated_with_score"] = _rows(cur)[0]

    # 確定性示範：UTC 與台北在台北 00:00–08:00 之間日界差 1 天（不依賴執行當下時刻）
    cur.execute("""
        SELECT ('2026-08-05 03:00:00+08'::timestamptz AT TIME ZONE 'UTC')::date AS utc_date,
               ('2026-08-05 03:00:00+08'::timestamptz AT TIME ZONE 'Asia/Taipei')::date
                   AS taipei_date,
               ('2026-08-05 09:00:00+08'::timestamptz AT TIME ZONE 'UTC')::date AS utc_date_0900,
               ('2026-08-05 09:00:00+08'::timestamptz AT TIME ZONE 'Asia/Taipei')::date
                   AS taipei_date_0900
    """)
    out["timezone_boundary_demo"] = _rows(cur)[0]

    # 全使用點盤點（由原始碼掃描產生；依運算子分類）
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    usages: list[dict] = []
    for sub in ("src", "scripts", "migrations", "tests"):
        for path in sorted((root / sub).rglob("*")):
            if path.suffix not in (".py", ".sql") or path.name == Path(__file__).name:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if "CURRENT_DATE" not in line:
                    continue
                stripped = line.strip()
                if re.search(r"[<>]=?\s*(?:\()?\s*CURRENT_DATE", stripped) or re.search(
                        r"CURRENT_DATE\s*[<>]=?", stripped):
                    op = "range"
                elif re.search(r"CURRENT_DATE\s*-", stripped):
                    op = "window_offset"
                elif re.search(r"=\s*CURRENT_DATE", stripped):
                    op = "exact_equality"
                else:
                    op = "other_or_comment"
                usages.append({
                    "file": str(path.relative_to(root)), "line": i,
                    "operator_class": op, "text": stripped[:160],
                })
    out["current_date_usage_total"] = len(usages)
    out["current_date_usage_by_class"] = dict(Counter(u["operator_class"] for u in usages))
    out["current_date_usages"] = usages
    out["current_date_risk_note"] = (
        "range／window_offset 類在 UTC 落後 8 小時下只會「保守地晚一天納入」，不會誤納未來場；"
        "exact_equality 類（game_date = CURRENT_DATE）在台北 00:00–08:00 會指向前一日，"
        "屬真實行為差異。")
    return out


# ===========================================================================
# 候選 1-5 + 233｜終局判定族（裁定殘局／保留賽／突破僵局／和局斷連／kind 差異）
# ===========================================================================
def terminal(cur) -> dict:
    out: dict[str, Any] = {"rule_anchor": {
        "called_game": {
            "file": "docs/reference/聯盟規章.txt", "rule": "第9章 第38條【正式比賽的確定】",
            "lines": "1330-1344",
            "quote": ("未賽完第 1 局：比賽不算，另擇期重賽。已賽 2 至未滿 5 局：比賽保留，"
                      "另擇期進行（記錄認定於比賽完成日之成績）。已賽完 5 局上半或 5 局下半中途："
                      "後攻隊為領先或追平時，視同已賽滿 5 局，成為正式比賽。已賽滿 5 局以上："
                      "以棒球規則判定為基準…殘局不算，以賽至前一完整局數之結果判定勝負"),
        },
        "postseason": {
            "file": "docs/reference/聯盟規章.txt", "rule": "第12章 第66條【正式比賽的確定】",
            "lines": "1779-1786",
            "quote": ("比賽採 9 局制，每場比賽皆須完成正規 9 局。在完成第 9 局前，因雨或其他"
                      "不可抗力等因素而終止比賽時，皆成為保留比賽。在完成第 9 局後、及延長賽"
                      "任一局數中成為平手，因雨或其他不可抗力等因素而終止比賽時，成為和局比賽"),
        },
        "extra_inning_tiebreak": {
            "file": "docs/reference/棒球規則.txt", "rule": "7.01(b)(2)(C)",
            "quote": ("為符合規則 9.16 自責分的計算，每半局開始位於二壘的跑壘員，視為守備失誤上壘，"
                      "但不記錄球隊或任何球員失誤"),
        },
        "extra_inning_rule": {
            "file": "docs/reference/棒球規則.txt", "rule": "7.01(b)(2)",
            "quote": "第 9 局之後的每半局，將以跑壘員位於二壘開始",
        },
        "postseason_stats_excluded": {
            "file": "docs/reference/聯盟規章.txt", "rule": "第48條【加賽記錄】",
            "quote": "季後決賽之各項成績均不列入球季例行賽記錄；加賽之成績得列入例行賽記錄",
        },
    }}

    # ── 233｜0:0 和局判定缺口：以官方 standings 和局數為 ground truth 反證 ──
    cur.execute("""
        SELECT s.year, sum(s.tie) AS official_tie_slots,
               (SELECT count(*) FROM cpbl.games g
                 WHERE g.year=s.year AND g.kind_code='A'
                   AND g.home_score=g.away_score AND g.home_score>0) AS derived_nonzero_tie_games,
               (SELECT count(*) FROM cpbl.games g
                 WHERE g.year=s.year AND g.kind_code='A'
                   AND g.home_score=0 AND g.away_score=0
                   AND g.game_date <= CURRENT_DATE AND g.present_status=1
                   AND g.delay_kind IS NULL) AS zero_zero_candidates
        FROM cpbl.standings s WHERE s.year >= 2018 GROUP BY s.year ORDER BY s.year
    """)
    tie_rows = _rows(cur)
    for r in tie_rows:
        r["official_tie_games"] = (r["official_tie_slots"] or 0) / 2
        r["unaccounted_tie_games"] = r["official_tie_games"] - r["derived_nonzero_tie_games"]
        r["explained_by_zero_zero"] = (
            r["unaccounted_tie_games"] == r["zero_zero_candidates"])
    out["tie_reconciliation_vs_official_standings"] = tie_rows
    out["tie_reconciliation_all_explained"] = all(
        r["explained_by_zero_zero"] for r in tie_rows)

    cur.execute("""
        SELECT year, kind_code, game_sno, game_date, game_season_code, present_status,
               delay_kind, orig_date, home_team_name, away_team_name, venue,
               (SELECT count(*) FROM cpbl.game_livelog l WHERE l.year=g.year
                  AND l.kind_code=g.kind_code AND l.game_sno=g.game_sno) AS livelog_rows,
               (SELECT count(*) FROM cpbl.batting_gamelog b WHERE b.year=g.year
                  AND b.kind_code=g.kind_code AND b.game_sno=g.game_sno) AS gamelog_rows,
               (SELECT count(*) FROM cpbl.game_scoreboard s WHERE s.year=g.year
                  AND s.kind_code=g.kind_code AND s.game_sno=g.game_sno) AS scoreboard_rows
        FROM cpbl.games g
        WHERE kind_code='A' AND home_score=0 AND away_score=0
          AND game_date <= CURRENT_DATE AND present_status=1 AND delay_kind IS NULL
          AND year IN (2018,2021,2023,2025)
        ORDER BY year, game_date
    """)
    out["confirmed_scoreless_tie_games"] = _rows(cur)

    # 全庫「score=0 且已過日期」母體（含未打/延賽），供分母
    cur.execute("""
        SELECT count(*) FILTER (WHERE delay_kind IS NULL) AS no_delay_kind,
               count(*) FILTER (WHERE delay_kind IS NOT NULL) AS with_delay_kind,
               count(*) AS total
        FROM cpbl.games
        WHERE home_score=0 AND away_score=0 AND game_date <= CURRENT_DATE
    """)
    out["zero_score_past_dated_population"] = _rows(cur)[0]

    # ── 候選 1｜裁定殘局：完成場的最終局數分布（<9 局＝縮短比賽）──
    cur.execute("""
        WITH maxinn AS (
          SELECT l.year, l.kind_code, l.game_sno, max(l.inning_seq) AS max_inning
          FROM cpbl.game_livelog l GROUP BY 1,2,3
        )
        SELECT m.kind_code, m.max_inning, count(*) AS n
        FROM maxinn m
        JOIN cpbl.games g ON g.year=m.year AND g.kind_code=m.kind_code AND g.game_sno=m.game_sno
        WHERE g.home_score + g.away_score > 0 AND g.game_date <= CURRENT_DATE
        GROUP BY 1,2 ORDER BY 1,2
    """)
    out["completed_game_max_inning_distribution"] = _rows(cur)

    cur.execute("""
        WITH maxinn AS (
          SELECT l.year, l.kind_code, l.game_sno, max(l.inning_seq) AS max_inning
          FROM cpbl.game_livelog l GROUP BY 1,2,3
        )
        SELECT g.year, g.kind_code, g.game_sno, g.game_date, m.max_inning,
               g.home_score, g.away_score, g.delay_kind, g.orig_date
        FROM maxinn m
        JOIN cpbl.games g ON g.year=m.year AND g.kind_code=m.kind_code AND g.game_sno=m.game_sno
        WHERE g.home_score + g.away_score > 0 AND g.game_date <= CURRENT_DATE
          AND m.max_inning < 9
        ORDER BY g.year, g.kind_code, g.game_sno
    """)
    out["short_games_under_9_innings"] = _rows(cur)

    # ── 候選 2｜保留賽：delay_kind 分布與逐場證據 ──
    cur.execute("""
        SELECT kind_code, delay_kind, count(*) AS n,
               count(*) FILTER (WHERE game_date > CURRENT_DATE) AS future_dated,
               count(*) FILTER (WHERE home_score + away_score > 0) AS with_score
        FROM cpbl.games GROUP BY 1,2 ORDER BY 1,2
    """)
    out["delay_kind_distribution"] = _rows(cur)
    cur.execute("""
        SELECT year, kind_code, game_sno, game_date, orig_date, delay_kind,
               home_score, away_score,
               (SELECT count(*) FROM cpbl.game_livelog l WHERE l.year=g.year
                  AND l.kind_code=g.kind_code AND l.game_sno=g.game_sno) AS livelog_rows
        FROM cpbl.games g WHERE delay_kind = '保留' ORDER BY year, kind_code, game_sno
    """)
    out["held_games"] = _rows(cur)

    # ── 候選 3｜突破僵局：延長局分布與 non_pa_tiebreak 出現年 ──
    cur.execute("""
        WITH maxinn AS (
          SELECT l.year, l.kind_code, l.game_sno, max(l.inning_seq) AS max_inning
          FROM cpbl.game_livelog l GROUP BY 1,2,3
        )
        SELECT year, kind_code, count(*) FILTER (WHERE max_inning > 9) AS extra_inning_games,
               max(max_inning) AS deepest_inning
        FROM maxinn GROUP BY 1,2 ORDER BY 1,2
    """)
    out["extra_inning_games_by_year"] = _rows(cur)
    cur.execute("""
        SELECT pa.year, pa.kind_code, count(*) AS tiebreak_runner_pa
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
        WHERE pa.outcome_family = 'tiebreak_runner'
        GROUP BY 1,2 ORDER BY 1,2
    """)
    out["tiebreak_runner_pa_by_year"] = _rows(cur)
    # 突破僵局跑者得分是否被官方記為自責分（7.01(b)(2)(C)：視為失誤上壘＝非自責）
    cur.execute("""
        SELECT year, kind_code, sum(runs) AS runs, sum(earned_runs) AS er,
               sum(runs) - sum(earned_runs) AS unearned
        FROM cpbl.pitching_gamelog
        WHERE year >= 2022 AND kind_code IN ('A','D') GROUP BY 1,2 ORDER BY 1,2
    """)
    out["runs_vs_earned_by_year"] = _rows(cur)

    # ── 候選 4｜和局斷連：special_records / scoreless streak 對和局的處置 ──
    cur.execute("""
        SELECT year, kind_code, count(*) AS tie_games
        FROM cpbl.games
        WHERE home_score = away_score AND home_score > 0
        GROUP BY 1,2 ORDER BY 1,2
    """)
    out["nonzero_tie_games_by_year"] = _rows(cur)

    # ── 候選 5｜kind 差異：各 kind 的資料覆蓋（games / livelog / PA / splits）──
    cur.execute("""
        SELECT g.kind_code,
               count(*) AS games,
               count(*) FILTER (WHERE g.home_score+g.away_score>0
                                AND g.game_date<=CURRENT_DATE) AS completed,
               min(g.year) AS y0, max(g.year) AS y1
        FROM cpbl.games g GROUP BY 1 ORDER BY 1
    """)
    kinds = _rows(cur)
    cur.execute("SELECT kind_code, count(DISTINCT (year, game_sno)) AS n, "
                "min(year) y0, max(year) y1 FROM cpbl.game_livelog GROUP BY 1")
    ll = {r["kind_code"]: r for r in _rows(cur)}
    cur.execute("""
        SELECT pa.kind_code, count(DISTINCT (pa.year, pa.game_sno)) AS n
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state='published'
        GROUP BY 1
    """)
    pab = {r["kind_code"]: r["n"] for r in _rows(cur)}
    cur.execute("SELECT DISTINCT kind_code FROM cpbl.batting_splits ORDER BY 1")
    spl = [r["kind_code"] for r in _rows(cur)]
    for k in kinds:
        k["livelog_games"] = ll.get(k["kind_code"], {}).get("n", 0)
        k["published_pa_games"] = pab.get(k["kind_code"], 0)
        k["in_batting_splits"] = k["kind_code"] in spl
    out["kind_coverage"] = kinds

    # ── 候選 4｜和局斷連：以官方 team_standings.streak 為 ground truth 實測 ──
    # 我方 special_records._add_streaks 註明「和局中斷連勝/連敗」；官方口徑須實證。
    cur.execute("""
        SELECT ts.year, ts.kind_code, ts.season_code, ts.team_code, ts.streak, ts.updated_at
        FROM cpbl.team_standings ts WHERE ts.streak IS NOT NULL AND ts.streak <> ''
        ORDER BY ts.year, ts.kind_code, ts.season_code, ts.team_code
    """)
    official_streaks = _rows(cur)
    out["official_streak_snapshot"] = official_streaks

    # 重建每隊近期勝敗序列（含和局標記），供人工比對官方 streak 字串
    seqs = {}
    for row in official_streaks:
        y, k, code = row["year"], row["kind_code"], row["team_code"]
        if (y, k, code) in seqs:
            continue
        cur.execute("""
            SELECT game_date, game_sno, home_team_code, away_team_code,
                   home_score, away_score,
                   CASE WHEN home_score = away_score THEN 'T'
                        WHEN (home_team_code = %s) = (home_score > away_score) THEN 'W'
                        ELSE 'L' END AS result
            FROM cpbl.games
            WHERE year=%s AND kind_code=%s AND (home_team_code=%s OR away_team_code=%s)
              AND home_score + away_score > 0 AND game_date <= CURRENT_DATE
            ORDER BY game_date DESC, game_sno DESC LIMIT 12
        """, (code, y, k, code, code))
        seqs[(y, k, code)] = [
            {"date": str(r["game_date"]), "sno": r["game_sno"], "result": r["result"]}
            for r in _rows(cur)]
    out["recent_result_sequences"] = {f"{y}/{k}/{c}": v for (y, k, c), v in seqs.items()}
    return out


# ===========================================================================
# 候選 11｜事後判決／紀錄更正的收斂保證矩陣（實證新鮮度）
# ===========================================================================
def cand11(cur) -> dict:
    out: dict[str, Any] = {
        "policy": "需求方 2026-08-05 裁定：改判一律賽季後批次或人工更新，不建自動收斂機制",
    }
    cur.execute("SELECT max(game_date) AS d FROM cpbl.games "
                "WHERE home_score+away_score>0 AND game_date<=CURRENT_DATE AND kind_code='A'")
    latest = _rows(cur)[0]["d"]
    out["latest_completed_game_date_A"] = latest

    # 每日 refresh 的實際軌跡（refresh_log）
    cur.execute("""
        SELECT scope, from_date, to_date, games_total, games_completed, ok, note, refreshed_at
        FROM cpbl.refresh_log ORDER BY refreshed_at DESC LIMIT 10
    """)
    out["recent_refresh_log"] = _rows(cur)

    # 逐表新鮮度：以「本季 A 已完成場」為分母，看各表覆蓋到哪一場
    year = 2026
    checks = {
        "games": ("SELECT max(game_date) FROM cpbl.games WHERE year=%s AND kind_code='A' "
                  "AND home_score+away_score>0 AND game_date<=CURRENT_DATE"),
        "batting_gamelog": ("SELECT max(g.game_date) FROM cpbl.batting_gamelog b "
                            "JOIN cpbl.games g ON g.year=b.year AND g.kind_code=b.kind_code "
                            "AND g.game_sno=b.game_sno WHERE b.year=%s AND b.kind_code='A'"),
        "game_livelog": ("SELECT max(g.game_date) FROM cpbl.game_livelog l "
                         "JOIN cpbl.games g ON g.year=l.year AND g.kind_code=l.kind_code "
                         "AND g.game_sno=l.game_sno WHERE l.year=%s AND l.kind_code='A'"),
        "pitch_tracking": ("SELECT max(g.game_date) FROM cpbl.pitch_tracking p "
                           "JOIN cpbl.games g ON g.year=p.year AND g.kind_code=p.kind_code "
                           "AND g.game_sno=p.game_sno WHERE p.year=%s AND p.kind_code='A'"),
        "game_plate_appearances": (
            "SELECT max(g.game_date) FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id AND b.state='published' "
            "JOIN cpbl.games g ON g.year=pa.year AND g.kind_code=pa.kind_code "
            "AND g.game_sno=pa.game_sno WHERE pa.year=%s AND pa.kind_code='A'"),
    }
    fresh = {}
    for name, sql in checks.items():
        cur.execute(sql, (year,))
        fresh[name] = str(cur.fetchone()[0])
    out["table_freshness_2026_A"] = fresh

    # 衍生表（非每日鏈）：以列數／PA 數對 canonical 比對，證明是否停在舊值
    cur.execute("""
        SELECT bt.year, bt.kind_code, sum(bt.pa) AS traits_pa
        FROM cpbl.batter_traits bt GROUP BY 1,2 ORDER BY 1,2
    """)
    traits = {(r["year"], r["kind_code"]): r["traits_pa"] for r in _rows(cur)}
    cur.execute("""
        SELECT pa.year, pa.kind_code, count(*) FILTER (WHERE pa.state='ready') AS canonical_ready
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id AND b.state='published'
        GROUP BY 1,2 ORDER BY 1,2
    """)
    stale = []
    for r in _rows(cur):
        t = traits.get((r["year"], r["kind_code"]))
        if t is None:
            continue
        stale.append({"year": r["year"], "kind": r["kind_code"], "batter_traits_pa": t,
                      "canonical_ready_pa": r["canonical_ready"],
                      "ratio": round(t / r["canonical_ready"], 4) if r["canonical_ready"] else None})
    out["derived_table_staleness_batter_traits"] = stale

    for tbl in ("run_expectancy", "batter_re24", "pitcher_re24", "batter_wsb",
                "team_der", "catcher_runs", "sabr_run_values", "fielding_innings",
                "batter_traits", "pitcher_traits", "advanced_stats", "game_scoreboard"):
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='cpbl' AND table_name=%s AND column_name='year'", (tbl,))
        has_year = cur.fetchone() is not None
        sql = ("SELECT count(*) AS n, max(year) AS max_year FROM cpbl.%s" % tbl  # noqa: S608
               if has_year else "SELECT count(*) AS n, NULL AS max_year FROM cpbl.%s" % tbl)  # noqa: S608
        cur.execute(sql)
        out.setdefault("derived_table_year_coverage", {})[tbl] = _rows(cur)[0]
    return out


COMMANDS = {"c6": cand6, "c7": cand7, "c8": cand8, "c9": cand9, "c10": cand10,
            "c11": cand11, "c12": cand12, "recon": recon, "terminal": terminal}


def main() -> int:
    ap = argparse.ArgumentParser(description="DATA-RULES-AUDIT1 唯讀審計")
    ap.add_argument("cmd", choices=sorted(COMMANDS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    with conn() as c:
        cur = c.cursor()
        result = COMMANDS[args.cmd](cur)
    _dump(result, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
