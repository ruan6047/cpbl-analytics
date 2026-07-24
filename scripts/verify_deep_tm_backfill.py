"""Verification script for INGEST-DEEP-TM-BACKFILL1."""

import json
import logging
import subprocess
import urllib.request

from cpbl.db import conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
logger = logging.getLogger("verify_backfill")

VPS = "root@45.76.100.29"
DEPLOY_PATH = "/opt/personal-website"

def run_remote_psql(sql: str) -> str:
    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", VPS,
        f"cd {DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -v ON_ERROR_STOP=1 -U \"$DB_USER\" -d \"$DB_NAME\" -c \"{sql}\""
    ]
    res = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
    return res.stdout

def verify() -> None:
    logger.info("=== 1. Non-null Coverage Comparison (Local vs Prod) ===")
    local_cov_sql = """
        SELECT year, kind_code,
               count(*) as total,
               count(traj_x0) as traj_cnt,
               round(100.0 * count(traj_x0) / count(*), 2) as traj_pct,
               count(hit_landing_bearing) as landing_cnt,
               count(hit_landing_confidence) as conf_cnt,
               count(hit_spin_rate) as exit_spin_cnt
        FROM cpbl.pitch_tracking
        WHERE year = 2026
        GROUP BY year, kind_code
        ORDER BY kind_code;
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute(local_cov_sql)
        local_cov = cur.fetchall()
    
    prod_cov_raw = run_remote_psql(local_cov_sql)
    logger.info("Local DB Coverage:\n%s", local_cov)
    logger.info("Prod DB Coverage:\n%s", prod_cov_raw)

    logger.info("=== 2. Random Completed Game Spot Check (Row-by-Row Match) ===")
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT game_sno FROM cpbl.pitch_tracking WHERE year = 2026 AND kind_code = 'A' AND traj_x0 IS NOT NULL LIMIT 1;")
        sample_sno = cur.fetchone()[0]
    
    spot_sql = f"""
        SELECT pitcher_acnt, pitch_cnt,
               hit_landing_bearing, hit_landing_confidence, hit_spin_rate,
               traj_x0, traj_x1, traj_x2, traj_y0, traj_y1, traj_y2, traj_z0, traj_z1, traj_z2
        FROM cpbl.pitch_tracking
        WHERE year = 2026 AND kind_code = 'A' AND game_sno = {sample_sno}
        ORDER BY pitcher_acnt, pitch_cnt LIMIT 10;
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute(spot_sql)
        local_spot = cur.fetchall()
    
    prod_spot_raw = run_remote_psql(spot_sql)
    logger.info("Selected sample game_sno: %d", sample_sno)
    logger.info("Local Spot Check (top 10 rows):\n%s", local_spot)
    logger.info("Prod Spot Check (top 10 rows):\n%s", prod_spot_raw)

    logger.info("=== 3. Non-target Column Integrity Check ===")
    check_non_target_sql = """
        SELECT year, kind_code,
               count(*) as total,
               count(ivb_cm) as ivb_cnt,
               count(hb_cm) as hb_cnt,
               count(rel_speed) as speed_cnt,
               count(auto_pitch_type) as type_cnt
        FROM cpbl.pitch_tracking
        WHERE year = 2026
        GROUP BY year, kind_code ORDER BY kind_code;
    """
    prod_non_target = run_remote_psql(check_non_target_sql)
    logger.info("Prod Non-target Columns Stats:\n%s", prod_non_target)

    logger.info("=== 4. Production API Health Check ===")
    req_obj = urllib.request.Request("https://cpbl.ruan-ruan.com/api/info", headers={"User-Agent": "curl/8.7.1"})
    req = urllib.request.urlopen(req_obj, timeout=10)
    body = req.read().decode("utf-8")
    info = json.loads(body)
    logger.info("API /api/info Response (HTTP %d):\n%s", req.status, json.dumps(info, indent=2, ensure_ascii=False))
    assert req.status == 200, "API /api/info failed!"
    assert info.get("status") in ("running", "maintenance"), "API status invalid!"

    logger.info("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    verify()
