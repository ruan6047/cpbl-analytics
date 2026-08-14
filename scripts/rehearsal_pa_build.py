# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（GAME-RECAP-PA1-BUILD1）
"""GAME-RECAP-PA1-BUILD1 production rehearsal：DB 層 reconciliation / atomic swap / 冪等。

在本機 dev DB 用一個**合成場**（year=2099，絕不與真實資料衝突）演練 builder 的
DB 路徑：首次發布 → 同來源重跑 no-op → 晚到/修正來源 reconciliation。全程只插入/刪除
**合成 livelog**（不碰 pitch_tracking 逐球源，Gate 3 紅線）；結束一律清理。

    uv run python scripts/rehearsal_pa_build.py

失敗即 assert 中止，並輸出前後對帳。可重複執行（開頭先清理殘留）。
"""

from __future__ import annotations

import logging

from psycopg.rows import dict_row

from cpbl.db import conn
from cpbl.ingest.pa_build import build_game

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
log = logging.getLogger("rehearsal.pa")

Y, K = 2099, "A"
G = 90001


def _ll_row(no: int, hitter: str | None, *, pitcher: str = "P1", action: str = "",
            pitch_cnt: int | None = None, is_strike: bool = False, is_ball: bool = False,
            change: bool = False, content: str = "") -> tuple:
    return (
        Y, K, G, f"{no:010d}", 1, "1", 1, 0, 0, 0, pitch_cnt, content, action, "",
        hitter, pitcher, is_strike, is_ball, False, change, False, 0, 0,
    )


_LL_COLS = (
    "year, kind_code, game_sno, main_event_no, inning_seq, visiting_home_type, batting_order, "
    "out_cnt, ball_cnt, strike_cnt, pitch_cnt, content, action_name, batting_action_name, "
    "hitter_acnt, pitcher_acnt, is_strike, is_ball, is_score, is_change_player, is_special_event, "
    "visiting_score, home_score"
)


def _insert_livelog(cur, rows: list[tuple]) -> None:
    placeholders = ",".join(["%s"] * 23)
    cur.executemany(
        f"INSERT INTO cpbl.game_livelog ({_LL_COLS}) VALUES ({placeholders})",  # noqa: S608
        rows,
    )


def _cleanup(cur) -> None:
    # 先刪 builds（cascade 清 PA/event/mapping），再刪 revision 與合成 livelog。
    cur.execute("DELETE FROM cpbl.game_recap_builds WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (Y, K, G))
    cur.execute("DELETE FROM cpbl.game_recap_source_revisions "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s", (Y, K, G))
    cur.execute("DELETE FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (Y, K, G))


def _published(cur) -> dict:
    cur.execute(
        "SELECT build_id, state FROM cpbl.game_recap_builds "
        "WHERE year=%s AND kind_code=%s AND game_sno=%s AND state='published'", (Y, K, G))
    return dict(cur.fetchone())


def _pa_ids(cur, build_id) -> list[str]:
    cur.execute("SELECT pa_id::text FROM cpbl.game_plate_appearances "
                "WHERE build_id=%s ORDER BY pa_index", (build_id,))
    return [r["pa_id"] for r in cur.fetchall()]


def _count_published(cur) -> int:
    cur.execute("SELECT count(*) AS n FROM cpbl.game_recap_builds "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s AND state='published'", (Y, K, G))
    return int(cur.fetchone()["n"])


def run() -> None:
    with conn() as c:
        cur = c.cursor(row_factory=dict_row)
        _cleanup(cur)
        c.commit()

        # v1：H1 完成打席、H2 打席中換投、H1 同局二度、一個 unknown action、一個 truncated
        v1 = [
            _ll_row(1, "H1", action="一壘安打", is_ball=True, pitch_cnt=1),
            _ll_row(2, "H1", action="一壘安打", is_strike=True, pitch_cnt=2, content="一壘安打"),
            _ll_row(3, "H2", pitcher="P1", action="四壞球", is_ball=True, pitch_cnt=3),
            _ll_row(4, None, change=True, content="更換投手"),
            _ll_row(5, "H2", pitcher="P2", action="四壞球", is_ball=True, pitch_cnt=1),
            _ll_row(6, "H1", action="三振", is_strike=True, pitch_cnt=3),  # 同局二度上場
            _ll_row(7, "H3", action="外星人降臨", is_strike=True, pitch_cnt=4),  # unknown → unreliable
            _ll_row(8, "H4", action="", is_ball=True, pitch_cnt=5),  # 空 action 有投球 → truncated
        ]
        _insert_livelog(cur, v1)
        c.commit()

        r1 = build_game(cur, Y, K, G)
        c.commit()
        assert r1.action == "publish" and r1.build_state == "published", r1
        pub1 = _published(cur)
        ids1 = _pa_ids(cur, pub1["build_id"])
        log.info("v1 publish: build=%s pa_ids=%d states=%s", str(pub1["build_id"])[:8], len(ids1),
                 r1.summary.get("ready"))
        # 同局二度上場 → H1 兩個相異 pa_id
        cur.execute("SELECT hitter_acnt, count(*) FROM cpbl.game_plate_appearances "
                    "WHERE build_id=%s AND hitter_acnt='H1' GROUP BY 1", (pub1["build_id"],))
        assert cur.fetchone()["count"] == 2, "H1 應有兩個相異 PA"

        # 2) 同來源重跑 → 冪等 no-op（不新增 build）
        r2 = build_game(cur, Y, K, G)
        c.commit()
        assert r2.action == "noop", r2
        assert _count_published(cur) == 1, "重跑不得產生第二個 published"
        assert _pa_ids(cur, pub1["build_id"]) == ids1, "pa_id 不得漂移"
        log.info("v2 rerun: noop ✓（published 仍為 %s）", str(pub1["build_id"])[:8])

        # 3) 晚到/修正來源：把 H1 第一打席的終結由「一壘安打」改為「二壘安打」（成員指紋變）
        cur.execute(
            "UPDATE cpbl.game_livelog SET action_name='二壘安打', content='二壘安打' "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s AND main_event_no IN ('0000000001','0000000002')",
            (Y, K, G))
        c.commit()
        r3 = build_game(cur, Y, K, G)
        c.commit()
        assert r3.action == "reconcile" and r3.build_state == "reconciliation_required", r3
        # 舊 published 未被覆寫/刪除；仍恰好一個 published，且 build_id 不變
        assert _count_published(cur) == 1, "reconciliation 不得動搖既有 published 唯一性"
        pub_after = _published(cur)
        assert pub_after["build_id"] == pub1["build_id"], "已發布 build 不得被替換"
        assert _pa_ids(cur, pub1["build_id"]) == ids1, "已發布 pa_id 不得變更/刪除"
        # 新 reconciliation build 存在且其變更 PA 標 reconciliation_required
        cur.execute(
            "SELECT pa.state AS pa_state, count(*) FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id "
            "WHERE b.state='reconciliation_required' AND pa.year=%s AND pa.kind_code=%s AND pa.game_sno=%s "
            "GROUP BY 1 ORDER BY 1", (Y, K, G))
        rec_states = {r["pa_state"]: r["count"] for r in cur.fetchall()}
        assert rec_states.get("reconciliation_required", 0) >= 1, rec_states
        log.info("v3 reconcile: 新 build 標 reconciliation_required=%s；舊 published 完整保留 ✓",
                 rec_states)

        # 4) FIX1 builder 升級：來源 manifest 不變、只有 builder_version 進版 →
        #    fingerprint 變更歸因於解讀改變，允許發布；差異仍留痕。
        # 先把來源**逐欄**還原成 v1：source manifest 由 sha256 決定，還原不精確就會產生
        # 新 revision，本步驟就測不到「來源不變」那條路。
        cur.execute(
            "UPDATE cpbl.game_livelog SET action_name='一壘安打', "
            "content = CASE main_event_no WHEN '0000000002' THEN '一壘安打' ELSE '' END "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s "
            "AND main_event_no IN ('0000000001','0000000002')", (Y, K, G))
        c.commit()
        cur.execute(  # 假裝既有 published 是舊 builder 產出的（模擬升級前的存量）
            "UPDATE cpbl.game_recap_builds SET builder_version='pa-build-0.9.0' "
            "WHERE build_id=%s", (pub1["build_id"],))
        # 同時讓其 PA 指紋與新 build 不同，確保走的是「有差異但仍發布」那條路
        cur.execute("UPDATE cpbl.game_pa_events SET event_fingerprint='stale-from-old-builder' "
                    "WHERE pa_id=(SELECT pa_id FROM cpbl.game_plate_appearances "
                    "WHERE build_id=%s ORDER BY pa_index LIMIT 1)", (pub1["build_id"],))
        c.commit()
        r4 = build_game(cur, Y, K, G)
        c.commit()
        assert r4.action == "publish" and r4.build_state == "published", r4
        assert r4.summary["reconcile"]["builder_upgrade"] is True, r4.summary["reconcile"]
        assert r4.summary["reconcile"]["changed"], "差異必須逐筆留痕，不得靜默"
        assert _count_published(cur) == 1, "atomic swap 後仍須恰好一個 published"
        pub4 = _published(cur)
        assert pub4["build_id"] != pub1["build_id"], "builder 升級應發布新 build"
        log.info("v4 builder upgrade: 來源不變+版本進版 → publish，changed=%d 筆留痕 ✓",
                 len(r4.summary["reconcile"]["changed"]))

        # 5) FIX1 fail closed：同半局塞出第 4 個打者出局 PA → 整場不 publish、舊 published 保留
        _insert_livelog(cur, [
            _ll_row(20, "X1", action="三振", is_strike=True, pitch_cnt=20, content="1人出局。"),
            _ll_row(21, "X2", action="三振", is_strike=True, pitch_cnt=21, content="2人出局。"),
            _ll_row(22, "X3", action="三振", is_strike=True, pitch_cnt=22, content="3人出局。"),
            _ll_row(23, "X4", action="三振", is_strike=True, pitch_cnt=23, content="3人出局。"),
        ])
        c.commit()
        r5 = build_game(cur, Y, K, G)
        c.commit()
        assert r5.action == "reconcile" and r5.build_state == "reconciliation_required", r5
        assert r5.summary["invariant_violations"], "違反不變式必須留痕"
        assert _count_published(cur) == 1 and _published(cur)["build_id"] == pub4["build_id"], \
            "fail closed 不得動搖既有 published"
        cur.execute(
            "SELECT count(*) AS n FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id "
            "WHERE b.state='reconciliation_required' AND b.build_id=%s "
            "AND pa.state='unreliable' AND pa.reconciliation_reason='half_inning_out_overflow'",
            (r5.build_id,))
        assert int(cur.fetchone()["n"]) >= 4, "違反半局的 PA 須標 unreliable"
        log.info("v5 invariant fail closed: %s → 不 publish、舊 published 保留 ✓",
                 r5.summary["invariant_violations"])

        # 6) FIX1 iteration 6：同版本 reconciliation build 的 noop 路徑必須自癒降級
        #    （iteration 5 查核 Critical 情境：等價 noop 跳過同源降級 side effect，
        #     已知損壞的 published 持續可消費；且不得以刪 build 解決）
        cur.execute("SELECT count(*) AS n FROM cpbl.game_recap_builds "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s", (Y, K, G))
        builds_before = int(cur.fetchone()["n"])
        # v5 的 reconciliation build 與 pub4 的 livelog revision 不同（v5 加了列）。
        # 偽造成同源：把 pub4 的 revision 改成當前來源的 revision（模擬紀律違反殘留態）。
        cur.execute(
            "SELECT livelog_revision_id FROM cpbl.game_recap_builds "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s "
            "  AND state='reconciliation_required' ORDER BY built_at DESC LIMIT 1", (Y, K, G))
        rec_rev = int(cur.fetchone()["livelog_revision_id"])
        cur.execute("UPDATE cpbl.game_recap_builds SET livelog_revision_id=%s "
                    "WHERE build_id=%s", (rec_rev, pub4["build_id"]))
        c.commit()
        r6 = build_game(cur, Y, K, G)
        c.commit()
        assert r6.action == "noop", r6
        assert r6.summary.get("repaired_demotion") is True, r6.summary
        assert _count_published(cur) == 0, "同源損壞的 published 必須被自癒降級"
        cur.execute("SELECT count(*) AS n FROM cpbl.game_recap_builds "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s", (Y, K, G))
        assert int(cur.fetchone()["n"]) == builds_before, "自癒不得刪除任何 build"
        cur.execute("SELECT state FROM cpbl.game_recap_builds WHERE build_id=%s",
                    (pub4["build_id"],))
        assert cur.fetchone()["state"] == "superseded", "舊 published 應轉 superseded（列保留）"
        # 冪等：再跑一次仍 noop、無事可修
        r6b = build_game(cur, Y, K, G)
        c.commit()
        assert r6b.action == "noop" and not r6b.summary.get("repaired_demotion"), r6b
        log.info("v6 noop self-heal: 同源殘留態補降級、零刪除、冪等 ✓")

        # 清理
        _cleanup(cur)
        c.commit()
        log.info("REHEARSAL PASSED：publish → idempotent noop → reconciliation → "
                 "builder upgrade republish → 半局出局不變式 fail closed → noop 自癒降級")


if __name__ == "__main__":
    run()
