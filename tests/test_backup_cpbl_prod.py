import gzip
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_backup_writes_verified_cpbl_schema_archive(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    backup_dir = tmp_path / "backups"
    fake_bin.mkdir()
    _executable(
        fake_bin / "ssh",
        "#!/bin/sh\nprintf '%s\\n' 'CREATE SCHEMA cpbl;' 'CREATE TABLE cpbl.games(id int);'\n",
    )
    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}:/usr/bin:/bin", "BACKUP_DIR": str(backup_dir)})

    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts" / "backup-cpbl-prod.sh")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    backup_path = Path(result.stdout.strip())
    assert backup_path.parent == backup_dir
    with gzip.open(backup_path, "rt", encoding="utf-8") as handle:
        assert "CREATE TABLE cpbl.games" in handle.read()


def test_backup_failure_does_not_report_a_valid_archive(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    backup_dir = tmp_path / "backups"
    fake_bin.mkdir()
    _executable(fake_bin / "ssh", "#!/bin/sh\nexit 23\n")
    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}:/usr/bin:/bin", "BACKUP_DIR": str(backup_dir)})

    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts" / "backup-cpbl-prod.sh")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert not list(backup_dir.glob("*.sql.gz"))


def test_refresh_progress_uses_consistent_four_step_labels() -> None:
    script = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")

    assert script.count('echo "==> 1/4') == 2
    assert script.count('echo "==> 2/4') == 1
    assert script.count('echo "==> 3/4') == 1
    assert script.count('echo "==> 4/4') == 1
    assert "/3" not in "\n".join(line for line in script.splitlines() if 'echo "==>' in line)
