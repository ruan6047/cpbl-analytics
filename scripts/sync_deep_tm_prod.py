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
        "DROP TABLE IF EXISTS cpbl.pitch_tracking_deep_staging;\n"
        "CREATE UNLOGGED TABLE cpbl.pitch_tracking_deep_staging (\n"
        "    year smallint,\n"
        "    kind_code text,\n"
        "    game_sno integer,\n"
        "    pitcher_acnt text,\n"
        "    pitch_cnt integer,\n"
        "    hit_landing_bearing double precision,\n"
        "    hit_landing_confidence text,\n"
        "    hit_spin_rate double precision,\n"
        "    traj_x0 double precision,\n"
        "    traj_x1 double precision,\n"
        "    traj_x2 double precision,\n"
        "    traj_y0 double precision,\n"
        "    traj_y1 double precision,\n"
        "    traj_y2 double precision,\n"
        "    traj_z0 double precision,\n"
        "    traj_z1 double precision,\n"
        "    traj_z2 double precision\n"
        ");\n"
        "COPY cpbl.pitch_tracking_deep_staging (\n"
        "    year, kind_code, game_sno, pitcher_acnt, pitch_cnt,\n"
        "    hit_landing_bearing, hit_landing_confidence, hit_spin_rate,\n"
        "    traj_x0, traj_x1, traj_x2,\n"
        "    traj_y0, traj_y1, traj_y2,\n"
        "    traj_z0, traj_z1, traj_z2\n"
        ") FROM STDIN WITH CSV HEADER;\n"
    ).encode("utf-8")

    footer = (
        "\\.\n"
        "UPDATE cpbl.pitch_tracking p\n"
        "SET hit_landing_bearing = s.hit_landing_bearing,\n"
        "    hit_landing_confidence = s.hit_landing_confidence,\n"
        "    hit_spin_rate = s.hit_spin_rate,\n"
        "    traj_x0 = s.traj_x0,\n"
        "    traj_x1 = s.traj_x1,\n"
        "    traj_x2 = s.traj_x2,\n"
        "    traj_y0 = s.traj_y0,\n"
        "    traj_y1 = s.traj_y1,\n"
        "    traj_y2 = s.traj_y2,\n"
        "    traj_z0 = s.traj_z0,\n"
        "    traj_z1 = s.traj_z1,\n"
        "    traj_z2 = s.traj_z2\n"
        "FROM cpbl.pitch_tracking_deep_staging s\n"
        "WHERE p.year = s.year\n"
        "  AND p.kind_code = s.kind_code\n"
        "  AND p.game_sno = s.game_sno\n"
        "  AND p.pitcher_acnt = s.pitcher_acnt\n"
        "  AND p.pitch_cnt = s.pitch_cnt;\n"
        "DROP TABLE cpbl.pitch_tracking_deep_staging;\n"
    ).encode("utf-8")

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
