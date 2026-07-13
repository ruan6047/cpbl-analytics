from __future__ import annotations

from cpbl.api.routers.players import player_career
from cpbl.db import conn


def test_coach_ambiguity_guard():
    try:
        with conn() as c:
            cur = c.cursor()

            # Clean up any potential stale test data
            cur.execute("DELETE FROM cpbl.coaches WHERE name = '測試同名'")
            cur.execute("DELETE FROM cpbl.managers WHERE name = '測試同名'")
            cur.execute("DELETE FROM cpbl.players WHERE id IN ('TEST_COACH_1', 'TEST_COACH_2')")

            # 1. Insert two players with the same name to simulate ambiguity
            cur.execute(
                "INSERT INTO cpbl.players (id, name) VALUES (%s, %s), (%s, %s)",
                ("TEST_COACH_1", "測試同名", "TEST_COACH_2", "測試同名")
            )

            # 2. Insert coach and manager records
            cur.execute(
                "INSERT INTO cpbl.coaches (year, team_code, name, pos, uniform_no) "
                "VALUES (2026, 'E01', '測試同名', '總教練', '99')"
            )
            cur.execute(
                "INSERT INTO cpbl.managers (team_code, era_name, name, from_year, to_year, g, w, l, t, win_pct) "
                "VALUES ('E01', '測試時期', '測試同名', 2026, 2026, 120, 60, 55, 5, 0.522)"
            )
            c.commit()

        # 3. Verify that the query flags the name as ambiguous and does not return the records
        res = player_career("TEST_COACH_1")
        assert res["coach_ambiguous"] is True
        assert len(res["official_coach_tenures"]) == 0
        assert len(res["manager_stats"]) == 0

        # 4. Delete one of the duplicate players to resolve ambiguity
        with conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM cpbl.players WHERE id = 'TEST_COACH_2'")
            c.commit()

        # 5. Verify that the query now returns the correct records without ambiguity
        res2 = player_career("TEST_COACH_1")
        assert res2["coach_ambiguous"] is False
        assert len(res2["official_coach_tenures"]) == 1
        assert res2["official_coach_tenures"][0]["pos"] == "總教練"
        assert len(res2["manager_stats"]) == 1
        assert res2["manager_stats"][0]["era_name"] == "測試時期"

    finally:
        # 6. Clean up test data and commit
        with conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM cpbl.coaches WHERE name = '測試同名'")
            cur.execute("DELETE FROM cpbl.managers WHERE name = '測試同名'")
            cur.execute("DELETE FROM cpbl.players WHERE id IN ('TEST_COACH_1', 'TEST_COACH_2')")
            c.commit()
