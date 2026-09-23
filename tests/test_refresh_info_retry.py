"""同步腳本最後兩道 /api/info freshness 檢查必須帶重試（2026-09-23）。

為什麼：兩道檢查緊接在 VPS 訓練之後，而 VPS（1 vCPU／950MB RAM）在同步與部署期間大量
換頁，重工作後的第一個請求可能卡超過 10 秒——09-23 22:07:57（CST）#190 部署後那次同步
就因此整條判失敗，資料其實早已寫完。見 `scripts/refresh-cpbl-prod.sh` 的 `fetch_api_info`。

本測試只驗**接線**：真腳本實際發出的 curl 是否帶重試旗標、兩道檢查是否都走它。
curl 自己的重試行為（逾時與 5xx 會重試、4xx 不會）不在此重測——假 curl 模擬不出來；
2026-09-23 已用真 curl 8.7.1 對本機模擬 server 實測：卡 25 秒 → 20 秒逾時、15 秒後重試
成功（rc=0）；502 → 重試成功；404 → 不重試、rc=22。
"""

from __future__ import annotations

from pathlib import Path

from tests.test_prod_sync_revision_seq import _run_refresh

API_INFO_URL = "http://127.0.0.1:1/api/info"   # 與 `_run_refresh` 的 fail-safe 值一致


def _curl_calls(tmp_path: Path) -> list[list[str]]:
    """讀回假 curl 記下的 argv（`_build_harness` 的 curl 樁寫在 `<tmp>/calls/curl/`）。"""
    log_dir = tmp_path / "calls" / "curl"
    assert log_dir.is_dir(), "假 curl 一次都沒被呼叫——harness 沒跑到 freshness 檢查"
    return [p.read_text(encoding="utf-8").splitlines() for p in sorted(log_dir.glob("*.args"))]


def _has_pair(argv: list[str], flag: str, value: str) -> bool:
    return any(a == flag and b == value for a, b in zip(argv, argv[1:], strict=False))


def test_both_freshness_checks_retry_transient_failures(tmp_path: Path) -> None:
    result, _ = _run_refresh(tmp_path)
    assert result.returncode == 0, f"harness 未跑完：rc={result.returncode}\n{result.stderr}"

    info_calls = [argv for argv in _curl_calls(tmp_path) if API_INFO_URL in argv]
    assert len(info_calls) == 2, f"預期 2 道 /api/info 檢查，實際 {len(info_calls)}：{info_calls}"
    for argv in info_calls:
        assert "-fsS" in argv, argv
        assert _has_pair(argv, "--retry", "3"), argv
        assert _has_pair(argv, "--retry-delay", "15"), argv
        assert _has_pair(argv, "--max-time", "20"), argv
