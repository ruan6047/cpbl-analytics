"""Sync 12 deep TrackMan fields from local DB to production DB for INGEST-DEEP-TM-BACKFILL1."""

import io
import logging
import subprocess

from cpbl.db import conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
logger = logging.getLogger("sync_prod")

VPS = "root@45.76.100.29"
DEPLOY_PATH = "/opt/personal-website"

def sync_to_prod() -> None:
    logger.info("1. Querying local 12 deep TrackMan fields for 2026...")
    with conn() as c:
        cur = c.cursor()
        copy_sql = """
            COPY (
                SELECT year, kind_code, game_sno, pitcher_acnt, pitch_cnt,
                       hit_landing_bearing, hit_landing_confidence, hit_spin_rate,
                       traj_x0, traj_x1, traj_x2,
                       traj_y0, traj_y1, traj_y2,
                       traj_z0, traj_z1, traj_z2
                FROM cpbl.pitch_tracking
                WHERE year = 2026 AND (traj_x0 IS NOT NULL OR hit_landing_bearing IS NOT NULL OR hit_spin_rate IS NOT NULL)
            ) TO STDOUT WITH CSV HEADER;
        """
        buf = io.BytesIO()
        with cur.copy(copy_sql) as copy:
            for chunk in copy:
                buf.write(chunk)
        csv_bytes = buf.getvalue()
        logger.info("Exported %d bytes of CSV data from local DB", len(csv_bytes))

    logger.info("2. Constructing remote psql script...")
    header = (
        b"DROP TABLE IF EXISTS cpbl.pitch_tracking_deep_staging;\n"
        b"CREATE UNLOGGED TABLE cpbl.pitch_tracking_deep_staging (\n"
        b"    year smallint,\n"
        b"    kind_code text,\n"
        b"    game_sno integer,\n"
        b"    pitcher_acnt text,\n"
        b"    pitch_cnt integer,\n"
        b"    hit_landing_bearing double precision,\n"
        b"    hit_landing_confidence text,\n"
        b"    hit_spin_rate double precision,\n"
        b"    traj_x0 double precision,\n"
        b"    traj_x1 double precision,\n"
        b"    traj_x2 double precision,\n"
        b"    traj_y0 double precision,\n"
        b"    traj_y1 double precision,\n"
        b"    traj_y2 double precision,\n"
        b"    traj_z0 double precision,\n"
        b"    traj_z1 double precision,\n"
        b"    traj_z2 double precision\n"
        b");\n"
        b"COPY cpbl.pitch_tracking_deep_staging (\n"
        b"    year, kind_code, game_sno, pitcher_acnt, pitch_cnt,\n"
        b"    hit_landing_bearing, hit_landing_confidence, hit_spin_rate,\n"
        b"    traj_x0, traj_x1, traj_x2,\n"
        b"    traj_y0, traj_y1, traj_y2,\n"
        b"    traj_z0, traj_z1, traj_z2\n"
        b") FROM STDIN WITH CSV HEADER;\n"
    )

    footer = (
        b"\\.\n"
        b"UPDATE cpbl.pitch_tracking p\n"
        b"SET hit_landing_bearing = s.hit_landing_bearing,\n"
        b"    hit_landing_confidence = s.hit_landing_confidence,\n"
        b"    hit_spin_rate = s.hit_spin_rate,\n"
        b"    traj_x0 = s.traj_x0,\n"
        b"    traj_x1 = s.traj_x1,\n"
        b"    traj_x2 = s.traj_x2,\n"
        b"    traj_y0 = s.traj_y0,\n"
        b"    traj_y1 = s.traj_y1,\n"
        b"    traj_y2 = s.traj_y2,\n"
        b"    traj_z0 = s.traj_z0,\n"
        b"    traj_z1 = s.traj_z1,\n"
        b"    traj_z2 = s.traj_z2\n"
        b"FROM cpbl.pitch_tracking_deep_staging s\n"
        b"WHERE p.year = s.year\n"
        b"  AND p.kind_code = s.kind_code\n"
        b"  AND p.game_sno = s.game_sno\n"
        b"  AND p.pitcher_acnt = s.pitcher_acnt\n"
        b"  AND p.pitch_cnt = s.pitch_cnt;\n"
        b"DROP TABLE cpbl.pitch_tracking_deep_staging;\n"
    )

    if not csv_bytes.endswith(b"\n"):
        csv_bytes += b"\n"

    script = header + csv_bytes + footer

    logger.info("3. Streaming script to production psql over SSH...")
    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", VPS,
        f"cd {DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -v ON_ERROR_STOP=1 --single-transaction -U \"$DB_USER\" -d \"$DB_NAME\""
    ]
    proc = subprocess.run(ssh_cmd, input=script, capture_output=True)
    if proc.returncode != 0:
        logger.error("Production sync failed! stderr:\n%s", proc.stderr.decode("utf-8", errors="replace"))
        raise RuntimeError("Production sync execution failed")

    logger.info("Production sync stdout:\n%s", proc.stdout.decode("utf-8", errors="replace"))
    logger.info("SUCCESS: Production backfill complete!")

if __name__ == "__main__":
    sync_to_prod()
