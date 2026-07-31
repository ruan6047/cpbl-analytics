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
    script = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")

    assert 'COMPLETED_GAMES_SQL="$(uv run python -m cpbl.completion)"' in script
    assert "FILTER (WHERE ${COMPLETED_GAMES_SQL})" in script


def test_refresh_calls_the_whole_database_backup_script() -> None:
    script = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")

    assert "scripts/backup-prod-db.sh" in script
    assert "backup-cpbl-prod.sh" not in script
