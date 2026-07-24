"""Rehearsal script for INGEST-DEEP-TM-BACKFILL1."""

import logging

from cpbl.db import conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
logger = logging.getLogger("rehearsal")

DEEP_COLS = [
    "hit_landing_bearing",
    "hit_landing_confidence",
    "hit_spin_rate",
    "traj_x0", "traj_x1", "traj_x2",
    "traj_y0", "traj_y1", "traj_y2",
    "traj_z0", "traj_z1", "traj_z2",
]

PK_COLS = ["year", "kind_code", "game_sno", "pitcher_acnt", "pitch_cnt"]

def run_rehearsal() -> None:
    with conn() as c:
        cur = c.cursor()
        
        logger.info("1. Creating local rehearsal table cpbl.pitch_tracking_rehearsal...")
        cur.execute("DROP TABLE IF EXISTS cpbl.pitch_tracking_rehearsal;")
        cur.execute("CREATE TABLE cpbl.pitch_tracking_rehearsal AS SELECT * FROM cpbl.pitch_tracking;")
        cur.execute("ALTER TABLE cpbl.pitch_tracking_rehearsal ADD PRIMARY KEY (year, kind_code, game_sno, pitcher_acnt, pitch_cnt);")
        
        logger.info("2. Simulating prod state (nullifying 12 deep fields for 2026 in rehearsal table)...")
        null_set_clause = ", ".join([f"{col} = NULL" for col in DEEP_COLS])
        cur.execute(f"UPDATE cpbl.pitch_tracking_rehearsal SET {null_set_clause} WHERE year = 2026;")
        
        # Verify nullified counts
        cur.execute("SELECT count(*), count(traj_x0), count(hit_landing_bearing) FROM cpbl.pitch_tracking_rehearsal WHERE year = 2026;")
        tot, traj_cnt, hit_cnt = cur.fetchone()
        logger.info("Simulated prod null state: 2026 total=%d, traj_x0 non-null=%d, hit_landing_bearing non-null=%d", tot, traj_cnt, hit_cnt)
        assert traj_cnt == 0 and hit_cnt == 0, "Nullification failed!"

        logger.info("3. Creating staging table cpbl.pitch_tracking_deep_staging...")
        cur.execute("DROP TABLE IF EXISTS cpbl.pitch_tracking_deep_staging;")
        cur.execute("""
            CREATE UNLOGGED TABLE cpbl.pitch_tracking_deep_staging (
                year smallint,
                kind_code text,
                game_sno integer,
                pitcher_acnt text,
                pitch_cnt integer,
                hit_landing_bearing double precision,
                hit_landing_confidence text,
                hit_spin_rate double precision,
                traj_x0 double precision,
                traj_x1 double precision,
                traj_x2 double precision,
                traj_y0 double precision,
                traj_y1 double precision,
                traj_y2 double precision,
                traj_z0 double precision,
                traj_z1 double precision,
                traj_z2 double precision
            );
        """)
        
        logger.info("4. Populating staging table from source pitch_tracking...")
        stg_cols = ", ".join(PK_COLS + DEEP_COLS)
        cur.execute(f"""
            INSERT INTO cpbl.pitch_tracking_deep_staging ({stg_cols})
            SELECT {stg_cols} FROM cpbl.pitch_tracking
            WHERE year = 2026 AND (traj_x0 IS NOT NULL OR hit_landing_bearing IS NOT NULL OR hit_spin_rate IS NOT NULL);
        """)
        stg_cnt = cur.rowcount
        logger.info("Staging table populated with %d rows", stg_cnt)

        logger.info("5. Executing batch update on rehearsal table...")
        update_set_clause = ", ".join([f"{col} = s.{col}" for col in DEEP_COLS])
        join_clause = " AND ".join([f"p.{col} = s.{col}" for col in PK_COLS])
        cur.execute(f"""
            UPDATE cpbl.pitch_tracking_rehearsal p
            SET {update_set_clause}
            FROM cpbl.pitch_tracking_deep_staging s
            WHERE {join_clause};
        """)
        updated_cnt = cur.rowcount
        logger.info("Rehearsal update affected %d rows", updated_cnt)

        logger.info("6. Verifying rehearsal results against original pitch_tracking...")
        # Check non-null coverage
        cur.execute("""
            SELECT year, kind_code,
                   count(*) as tot,
                   count(hit_landing_bearing) as landing_cnt,
                   count(hit_landing_confidence) as conf_cnt,
                   count(hit_spin_rate) as spin_cnt,
                   count(traj_x0) as traj_cnt
            FROM cpbl.pitch_tracking_rehearsal
            WHERE year = 2026
            GROUP BY year, kind_code ORDER BY kind_code;
        """)
        rehearsal_cov = cur.fetchall()
        
        cur.execute("""
            SELECT year, kind_code,
                   count(*) as tot,
                   count(hit_landing_bearing) as landing_cnt,
                   count(hit_landing_confidence) as conf_cnt,
                   count(hit_spin_rate) as spin_cnt,
                   count(traj_x0) as traj_cnt
            FROM cpbl.pitch_tracking
            WHERE year = 2026
            GROUP BY year, kind_code ORDER BY kind_code;
        """)
        orig_cov = cur.fetchall()
        
        logger.info("Rehearsal coverage: %s", rehearsal_cov)
        logger.info("Original coverage:  %s", orig_cov)
        assert rehearsal_cov == orig_cov, f"Coverage mismatch: {rehearsal_cov} != {orig_cov}"

        # Verify non-target column check (e.g. ivb_cm, hb_cm, rel_speed, tagged_pitch_type)
        cur.execute("""
            SELECT count(*) FROM cpbl.pitch_tracking_rehearsal r
            JOIN cpbl.pitch_tracking o USING (year, kind_code, game_sno, pitcher_acnt, pitch_cnt)
            WHERE r.year = 2026 AND (
                r.ivb_cm IS DISTINCT FROM o.ivb_cm OR
                r.hb_cm IS DISTINCT FROM o.hb_cm OR
                r.rel_speed IS DISTINCT FROM o.rel_speed OR
                r.auto_pitch_type IS DISTINCT FROM o.auto_pitch_type
            );
        """)
        mismatch_non_target = cur.fetchone()[0]
        logger.info("Non-target column mismatches: %d", mismatch_non_target)
        assert mismatch_non_target == 0, "Non-target columns were modified!"

        logger.info("7. Testing idempotency (second update)...")
        cur.execute(f"""
            UPDATE cpbl.pitch_tracking_rehearsal p
            SET {update_set_clause}
            FROM cpbl.pitch_tracking_deep_staging s
            WHERE {join_clause};
        """)
        cur.execute("""
            SELECT year, kind_code, count(traj_x0), count(hit_landing_bearing)
            FROM cpbl.pitch_tracking_rehearsal WHERE year = 2026
            GROUP BY year, kind_code ORDER BY kind_code;
        """)
        idemp_cov = cur.fetchall()
        logger.info("Idempotent second update coverage: %s", idemp_cov)
        assert idemp_cov == [(r[0], r[1], r[6], r[3]) for r in rehearsal_cov], "Idempotency check failed!"

        logger.info("8. Cleaning up rehearsal & staging tables...")
        cur.execute("DROP TABLE cpbl.pitch_tracking_rehearsal;")
        cur.execute("DROP TABLE cpbl.pitch_tracking_deep_staging;")
        
        logger.info("SUCCESS: Rehearsal passed all checks perfectly!")

if __name__ == "__main__":
    run_rehearsal()
