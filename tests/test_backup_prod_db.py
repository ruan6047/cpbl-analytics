"""`scripts/backup-prod-db.sh` 的行為守衛（OPS-BACKUP-EMPTY1）。

**為什麼內容門檻要有測試**：生產 VPS 的 `infra/scripts/backup-db.sh` cron 連續 86 天
產出 20-byte 空檔而無人察覺。那些檔案**每一份都能通過 `gzip -t`**——空輸入的 gzip
是合法串流。只驗「檔案非空 ＋ gzip 完整」永遠抓不到這個失敗模式，必須驗解壓後的
內容規模。`test_dump_with_no_content_is_rejected_and_leaves_no_artifact` 就是該缺陷
的回歸測試。
"""

import gzip
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = str(ROOT / "scripts" / "backup-prod-db.sh")

# 測試用的假 dump 很小，故把內容門檻降到 1；正式預設為 90 張表／100 MB。
LOW_THRESHOLDS = {"BACKUP_MIN_TABLES": "1", "BACKUP_MIN_BYTES": "1"}


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run(env_updates: dict, fake_ssh: str, tmp_path: Path) -> subprocess.CompletedProcess:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    _executable(fake_bin / "ssh", fake_ssh)
    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}:/usr/bin:/bin"})
    env.update(env_updates)
    return subprocess.run(
        ["/bin/bash", SCRIPT], env=env, text=True, capture_output=True, check=False
    )


def test_backup_writes_verified_archive(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    result = _run(
        {"BACKUP_DIR": str(backup_dir), **LOW_THRESHOLDS},
        "#!/bin/sh\nprintf '%s\\n' 'CREATE SCHEMA cpbl;' 'CREATE TABLE cpbl.games(id int);'\n",
        tmp_path,
    )

    assert result.returncode == 0
    backup_path = Path(result.stdout.strip())
    assert backup_path.parent == backup_dir
    assert backup_path.name.startswith("alphadb-prod-")
    with gzip.open(backup_path, "rt", encoding="utf-8") as handle:
        assert "CREATE TABLE cpbl.games" in handle.read()


def test_dump_covers_whole_database_not_only_cpbl_schema(tmp_path: Path) -> None:
    """alpha_db 為兩專案共用；`--schema=cpbl` 會讓主站 public 的 18 張表零覆蓋。"""
    args_log = tmp_path / "ssh-args.txt"
    result = _run(
        {"BACKUP_DIR": str(tmp_path / "backups"), **LOW_THRESHOLDS},
        f'#!/bin/sh\nprintf \'%s\\n\' "$*" > {args_log}\n'
        "printf '%s\\n' 'CREATE TABLE cpbl.games(id int);' 'CREATE TABLE public.users(id int);'\n",
        tmp_path,
    )

    assert result.returncode == 0
    remote_cmd = args_log.read_text(encoding="utf-8")
    assert "pg_dump" in remote_cmd
    assert "--schema=" not in remote_cmd, "備份不得限定單一 schema"


def test_ssh_failure_leaves_no_artifact(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    result = _run(
        {"BACKUP_DIR": str(backup_dir), **LOW_THRESHOLDS},
        "#!/bin/sh\nexit 23\n",
        tmp_path,
    )

    assert result.returncode != 0
    assert not list(backup_dir.glob("*.sql.gz"))
    assert not list(backup_dir.glob("*.partial*"))


def test_dump_with_no_content_is_rejected_and_leaves_no_artifact(tmp_path: Path) -> None:
    """回歸測試：pg_dump 回空但 exit 0 時，產物必須被拒絕。

    這正是 VPS cron 86 天的失敗模式——空輸入的 gzip 是 20 bytes 的合法串流，
    `test -s` 與 `gzip -t` 雙雙通過，只有內容門檻攔得住。
    """
    backup_dir = tmp_path / "backups"
    result = _run(
        {"BACKUP_DIR": str(backup_dir)},  # 用正式門檻
        "#!/bin/sh\nexit 0\n",  # 成功但無輸出
        tmp_path,
    )

    assert result.returncode != 0
    assert "備份內容驗證失敗" in result.stderr
    assert not list(backup_dir.glob("*.sql.gz"))
    assert not list(backup_dir.glob("*.partial*"))


def test_undersized_dump_is_rejected(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    result = _run(
        {"BACKUP_DIR": str(backup_dir), "BACKUP_MIN_TABLES": "1", "BACKUP_MIN_BYTES": "100000"},
        "#!/bin/sh\necho 'CREATE TABLE cpbl.games(id int);'\n",
        tmp_path,
    )

    assert result.returncode != 0
    assert "解壓後" in result.stderr
    assert not list(backup_dir.glob("*.sql.gz"))


def test_non_positive_threshold_is_rejected(tmp_path: Path) -> None:
    result = _run(
        {"BACKUP_DIR": str(tmp_path / "backups"), "BACKUP_MIN_TABLES": "0"},
        "#!/bin/sh\necho 'CREATE TABLE cpbl.games(id int);'\n",
        tmp_path,
    )

    assert result.returncode == 64


def test_default_backup_directory_is_persistent_user_storage(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    _executable(fake_bin / "ssh", "#!/bin/sh\necho 'CREATE TABLE cpbl.games(id int);'\n")
    full_env = os.environ.copy()
    full_env.pop("BACKUP_DIR", None)
    full_env.update(
        {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), **LOW_THRESHOLDS}
    )

    result = subprocess.run(
        ["/bin/bash", SCRIPT], env=full_env, text=True, capture_output=True, check=False
    )

    assert result.returncode == 0
    assert Path(result.stdout.strip()).parent == (
        tmp_path / "home" / "Library" / "Application Support" / "cpbl-analytics" / "backups"
    )


def test_successful_backup_retains_only_configured_newest_archives(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(5):
        with gzip.open(backup_dir / f"alphadb-prod-2026010{index + 1}-010101.sql.gz", "wt") as fh:
            fh.write("old backup")

    result = _run(
        {"BACKUP_DIR": str(backup_dir), "BACKUP_KEEP": "3", **LOW_THRESHOLDS},
        "#!/bin/sh\necho 'CREATE TABLE cpbl.games(id int);'\n",
        tmp_path,
    )

    assert result.returncode == 0
    assert len(list(backup_dir.glob("*.sql.gz"))) == 3


def test_cleanup_ages_out_legacy_cpbl_prefix(tmp_path: Path) -> None:
    """改名前的 `cpbl-prod-*` 備份也要納入輪替，否則會永久佔用磁碟。"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(4):
        with gzip.open(backup_dir / f"cpbl-prod-2026010{index + 1}-010101.sql.gz", "wt") as fh:
            fh.write("legacy cpbl-only backup")

    result = _run(
        {"BACKUP_DIR": str(backup_dir), "BACKUP_KEEP": "2", **LOW_THRESHOLDS},
        "#!/bin/sh\necho 'CREATE TABLE cpbl.games(id int);'\n",
        tmp_path,
    )

    assert result.returncode == 0
    remaining = sorted(p.name for p in backup_dir.glob("*.sql.gz"))
    assert len(remaining) == 2, remaining
    # 最舊的三份 legacy 檔應已淘汰，保留最新 legacy 與這次的新備份。
    assert remaining[0].startswith("alphadb-prod-")
    assert remaining[1] == "cpbl-prod-20260104-010101.sql.gz"


def test_refresh_progress_uses_consistent_four_step_labels() -> None:
    script = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")

    assert script.count('echo "==> 1/4') == 2
    assert script.count('echo "==> 2/4') == 1
    assert script.count('echo "==> 3/4') == 1
    assert script.count('echo "==> 4/4') == 1
    assert "/3" not in "\n".join(line for line in script.splitlines() if 'echo "==>' in line)


def test_refresh_uses_shared_completed_game_contract() -> None:
    """同步閘門必須與 `/api/info` 用**同一支** helper（DATA-TZ-BOUNDARY-SUCCESSION1 (3c)）。

    ⚠️ 這條釘的是「兩邊同源」不只是「有引用 contract」：閘門取到的值會被
    `verify_refresh_info.py` 拿去跟 `/api/info` 做**精確相等**比對，不等就擋同步——
    而擋住的位置在**備份已完成、正要 upsert** 之後。用不同判準＝資料對了也會被擋。
    """
    script = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")

    assert 'COMPLETED_GAMES_SQL="$(uv run python -m cpbl.completion --with-evidence)"' in script
    assert "FILTER (WHERE ${COMPLETED_GAMES_SQL})" in script
    # --with-evidence 產出的條件帶 `g.` 限定詞（相關子查詢的正確性要求），
    # 故查詢來源必須別名化，否則整段 SQL 語法錯誤。
    #
    # ⚠️ **必須在 freshness 查詢本體內找，不能全檔 `in`**：本檔上方的說明註解也寫著
    # 「FROM cpbl.games g」，全檔比對會被註解餵飽——實測把 SQL 的別名拿掉後，
    # `"FROM cpbl.games g" in script` 仍然通過。那是零資訊的檢查。
    assert "FROM cpbl.games g" in _freshness_query(script)


def _freshness_query(script: str) -> str:
    """抓出 `LOCAL_FRESHNESS=...` 那一段賦值（不含註解），供斷言在其內部比對。"""
    start = script.index('LOCAL_FRESHNESS="$(docker exec')
    end = script.index("\nIFS=", start)
    return script[start:end]


def test_refresh_gate_and_info_metric_share_one_criterion() -> None:
    """閘門與 `/api/info` 的判準逐字同源：只准差在別名，as_of 與判準本體必須完全一致。

    ⚠️ 不要用「本機兩側今天都是 454」當通過依據——那是巧合。本機實測兩套判準的
    分類差為 **5 場**經取證的 0:0 真和局（2018/A/124、2021/A/256、2023/A/119、
    2023/A/175、2025/A/233），只是它們都不在本季、今天剛好不影響計數。
    """
    import subprocess
    import sys

    from cpbl.completion import TAIPEI_TODAY_SQL, completed_games_sql_with_evidence

    gate_sql = subprocess.run(  # noqa: S603 — 固定引數、無使用者輸入
        [sys.executable, "-m", "cpbl.completion", "--with-evidence"],
        capture_output=True, text=True, check=True, cwd=ROOT,
    ).stdout.strip()
    info_sql = completed_games_sql_with_evidence("games")

    # 別名以外逐字相同 → 判準本體與 as_of 都同源
    assert gate_sql == info_sql.replace("games.", "g."), (
        f"閘門與 /api/info 判準已分歧：\n  gate={gate_sql}\n  info={info_sql}"
    )
    # as_of 自帶時區：閘門在 `docker exec psql`（連線池之外）求值，
    # `cpbl.db` 的 configure 管不到那個 session，靠 session timezone 會失效。
    assert TAIPEI_TODAY_SQL in gate_sql
    assert "CURRENT_DATE" not in gate_sql


def test_refresh_calls_the_whole_database_backup_script() -> None:
    script = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")

    assert "scripts/backup-prod-db.sh" in script
    assert "backup-cpbl-prod.sh" not in script


# ---- #268（需求方裁定 issuecomment-6138860627）：新備份建立時即 0600 -------------------
#
# 合成回歸，零真實主機：假 ssh、低內容門檻、tmp 目錄。父行程刻意設 umask 022——修補前同一情境
# 產出 0644（重導向建立、mv 保留 mode、全檔無 chmod），這兩條在修補前必紅。

# 假 ssh：等 .partial 出現（管線兩端並行啟動）後記下它當下的權限，再吐出合成 dump。
_SSH_RECORDING_PARTIAL_MODE = """#!/bin/sh
i=0
while [ "$i" -lt 50 ]; do
  f="$(ls "$BACKUP_DIR"/*.partial.* 2>/dev/null | head -1)"
  [ -n "$f" ] && break
  sleep 0.1; i=$((i + 1))
done
m="$(stat -c %a "$f" 2>/dev/null || stat -f %Lp "$f")"
printf '%s\\n' "$m" > "$PARTIAL_MODE_LOG"
printf '%s\\n' 'CREATE TABLE cpbl.games(id int);'
"""


def _run_under_caller_umask(env_updates: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    _executable(fake_bin / "ssh", _SSH_RECORDING_PARTIAL_MODE)
    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}:/usr/bin:/bin", **LOW_THRESHOLDS, **env_updates})
    # 呼叫端 umask 022；腳本結束後再印一次呼叫端 umask，證明修補不外洩到呼叫端。
    return subprocess.run(
        ["/bin/bash", "-c", 'umask 022; /bin/bash "$0"; rc=$?; echo "CALLER_UMASK=$(umask)" >&2; exit $rc',
         SCRIPT],
        env=env, text=True, capture_output=True, check=False,
    )


def test_new_backup_and_partial_are_owner_only_even_when_caller_umask_is_022(tmp_path: Path) -> None:
    import stat

    backup_dir = tmp_path / "new-backups"
    mode_log = tmp_path / "partial-mode.txt"
    result = _run_under_caller_umask(
        {"BACKUP_DIR": str(backup_dir), "PARTIAL_MODE_LOG": str(mode_log)}, tmp_path)

    assert result.returncode == 0, result.stderr
    backup_path = Path(result.stdout.strip())
    assert result.stdout.strip().splitlines() == [str(backup_path)], "stdout 仍只有備份路徑"
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    assert mode_log.read_text().strip() == "600", ".partial 建立當下就是 0600"
    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700, "新建的備份目錄只給擁有者"
    assert "CALLER_UMASK=0022" in result.stderr, "umask 只作用於備份行程，不外洩到呼叫端"


def test_existing_directory_and_old_backups_keep_their_modes(tmp_path: Path) -> None:
    """修補不回頭改既有產物：既有 0755 目錄與 0644 舊備份的權限與內容原樣保留（保留份數內）。"""
    import stat

    backup_dir = tmp_path / "existing"
    backup_dir.mkdir()
    backup_dir.chmod(0o755)
    old = backup_dir / "alphadb-prod-20260101-000000-1.sql.gz"
    old.write_bytes(gzip.compress(b"CREATE TABLE cpbl.old(id int);\n"))
    old.chmod(0o644)
    before = old.read_bytes()

    result = _run_under_caller_umask(
        {"BACKUP_DIR": str(backup_dir), "BACKUP_KEEP": "7",
         "PARTIAL_MODE_LOG": str(tmp_path / "partial-mode.txt")}, tmp_path)

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o755
    assert stat.S_IMODE(old.stat().st_mode) == 0o644
    assert old.read_bytes() == before
    new = Path(result.stdout.strip())
    assert new != old and stat.S_IMODE(new.stat().st_mode) == 0o600
