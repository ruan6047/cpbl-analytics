"""#353 WP3：同步腳本的 freshness 檢查先等 /api/info 快取換代（`wait_api_info_cache_since`）。

只抽出該函式、配假 curl／sleep 執行（零網路）。驗三件事：
* 沒有標頭（舊版 API／取不到）＝不等；
* 標頭 ≥ 基準＝不等；標頭 < 基準＝每 10 秒再探，換代即停；
* 等不到也只警告、回 0——⛔ 內容比對交給其後的 verify，等待本身不得決定成敗。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "refresh-cpbl-prod.sh"


def _function_source() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("wait_api_info_cache_since() {")
    end = source.index("\n}\n", start) + 3
    return source[start:end]


def _run(tmp_path: Path, headers: list[str], since: int) -> tuple[subprocess.CompletedProcess, int, int]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seq = tmp_path / "seq"
    seq.write_text("0", encoding="utf-8")
    responses = tmp_path / "responses"
    responses.write_text("\n".join(headers) + "\n", encoding="utf-8")
    (bin_dir / "curl").write_text(
        "#!/bin/sh\n"
        f'n=$(cat "{seq}"); echo $((n + 1)) > "{seq}"\n'
        f'line=$(sed -n "$((n + 1))p" "{responses}")\n'
        'printf "HTTP/1.1 200 OK\\r\\ncontent-type: application/json\\r\\n"\n'
        '[ -n "$line" ] && printf "%s\\r\\n" "$line"\n'
        'printf "\\r\\n"\n',
        encoding="utf-8",
    )
    (bin_dir / "sleep").write_text(f'#!/bin/sh\necho x >> "{tmp_path}/slept"\n', encoding="utf-8")
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    script = (
        "set -euo pipefail\nAPI_INFO_URL=http://127.0.0.1:1/api/info\n"
        + _function_source()
        + f"\nwait_api_info_cache_since {since}\necho done\n"
    )
    result = subprocess.run(
        ["/bin/bash", "-c", script], env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        text=True, capture_output=True, check=False,
    )
    slept = (tmp_path / "slept").read_text().count("x") if (tmp_path / "slept").exists() else 0
    return result, int(seq.read_text()), slept


def test_no_header_means_no_cache_and_no_wait(tmp_path: Path) -> None:
    result, calls, slept = _run(tmp_path, [""], since=1_000)
    assert result.returncode == 0 and "done" in result.stdout
    assert (calls, slept) == (1, 0)


def test_fresh_cache_returns_immediately(tmp_path: Path) -> None:
    result, calls, slept = _run(tmp_path, ["X-Cpbl-Info-Computed-At: 1000"], since=1_000)
    assert result.returncode == 0
    assert (calls, slept) == (1, 0)


def test_stale_cache_waits_until_rollover(tmp_path: Path) -> None:
    headers = ["x-cpbl-info-computed-at: 990", "x-cpbl-info-computed-at: 995",
               "x-cpbl-info-computed-at: 1005"]
    result, calls, slept = _run(tmp_path, headers, since=1_000)
    assert result.returncode == 0
    assert (calls, slept) == (3, 2)


def test_never_rolling_over_only_warns(tmp_path: Path) -> None:
    result, calls, slept = _run(tmp_path, ["X-Cpbl-Info-Computed-At: 1"] * 20, since=1_000)
    assert result.returncode == 0 and "done" in result.stdout
    assert (calls, slept) == (12, 12)
    assert "未換代" in result.stderr


def test_both_freshness_checks_wait_for_their_own_baseline() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    data_only = source.index('wait_api_info_cache_since "$SYNC_DONE_AT"')
    marker = source.index('wait_api_info_cache_since "$MARKER_AT"')
    verify_data_only = 'verify_refresh_info.py" --data-only'
    assert source.index('SYNC_DONE_AT="$(date +%s)"') < data_only < source.rindex(verify_data_only)
    # 季後晚間 POSTSEASON_RESULTS_ONLY：同步後、data-only 比對前也要等。
    evening = source.index('wait_api_info_cache_since "$(date +%s)"')
    assert source.index("  sync_postseason_results\n") < evening < source.index(verify_data_only)
    assert source.index("'local-to-production sync completed'") < source.index('MARKER_AT="$(date +%s)"') < marker
