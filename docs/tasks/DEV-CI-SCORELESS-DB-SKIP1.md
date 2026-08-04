# DEV-CI-SCORELESS-DB-SKIP1 CI `api` job 因單一測試未循同檔案模式 skip DB 不可用而長紅〔T1；⚪一般〕

- 需求：ruan6047（經 `OPS-CONTROL-PLANE-PR-GUARD1` Task 1 Discovery 發現並登記）　規劃：Claude Sonnet 5@Claude Code　分支：`ai/<執行者>/DEV-CI-SCORELESS-DB-SKIP1`
- 執行：待指派（建議 L1；純測試容錯修正，不涉統計／資料正確性邏輯）　查核：待指派（新 context 即可，≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`tests/test_scoreless_streak_api.py`（僅此檔案，不動 `src/cpbl/api/scoreless.py` 或任何統計／資料正確性邏輯）
- Discovery：Claude Sonnet 5@Claude Code（2026-08-04；於 `OPS-CONTROL-PLANE-PR-GUARD1` Task 1 執行 CI 綠色基線查核時發現）
- Design：Design Gate N/A——純測試基礎設施修正，無使用者可見介面。

## 問題陳述

`main` 最近三次 CI run（`30895706890`、`30895359002`、`30894819233`）的 `api` job 全部失敗，`web` 全綠。三次失敗完全一致：`tests/test_scoreless_streak_api.py::test_every_counted_appearance_is_officially_er_zero` 拋出
`psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec`（996 passed / 28 skipped / 1 failed）。

`.github/workflows/ci.yml` 的 `api` job 確認未起 PostgreSQL service，這點與卡面既有假設相符。但同檔案其餘測試（`test_metric_wording_says_earned_run`、`test_extended_is_never_below_strict`）都經由 `_get()` helper 存取 API：

```python
def _get(path: str):
    try:
        ...
        r = TestClient(app).get(path)
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    ...
```

唯獨 `test_every_counted_appearance_is_officially_er_zero` 直接呼叫 `cpbl.api.scoreless.load_appearances()`／`compute_all()`，繞過了這層防護，導致連線逾時以未捕捉例外傳播為測試失敗，而非依同檔案既有慣例 skip。**這不是「CI 缺 PostgreSQL」本身的問題（那是已知且刻意的設計），而是這一個測試沒有套用同檔案已存在的容錯模式。**

此卡是 `OPS-CONTROL-PLANE-PR-GUARD1` Task 1（取得 `api`／`web` required-check 綠色基線）的硬阻塞：該卡紅線明文禁止在 `api` 為紅時將其設為 required check，也禁止該卡自行代修此處 DB 依賴。

## 驗收條件

- [ ] `test_every_counted_appearance_is_officially_er_zero` 在無法取得 DB 連線時以 `pytest.skip` 收尾（比照同檔案 `_get()` 的既有模式與 skip 訊息風格），不再讓 `PoolTimeout` 以未捕捉例外傳播。
- [ ] 有 DB 可用時，原有斷言（紅線 3／4／5：官方 ER 必為 0、`kind_code == "A"`）完全不變、照常執行，不得放寬或刪減。
- [ ] 不改動 `src/cpbl/api/scoreless.py` 或任何統計／資料正確性計算邏輯，僅測試檔案的容錯範圍。
- [ ] 同一 source SHA 下，GitHub Actions `api` 與 `web` job 皆為 `success`。

## 驗證

- `uv run pytest tests/test_scoreless_streak_api.py -q`：本機無 DB 環境下三個測試皆 skip（非 fail）；`docker compose up -d db` 後有 DB 環境下三個測試皆正常執行並通過。
- `uv run pytest -q` 全庫回歸綠色（現況 996 passed / 28 skipped，修正後應為 997 passed / 28 skipped 或等價）。
- `gh run view <run-id> --json jobs,conclusion --jq '.jobs[] | {name,conclusion}'` 確認同 SHA 下 `api`／`web` 皆 `success`，附 run URL。

## Log

- 2026-08-04 register by Claude Sonnet 5@Claude Code（於 `OPS-CONTROL-PLANE-PR-GUARD1` Task 1 Discovery 期間發現並登記；三次連續 main run 一致重現，root cause 已定位至測試檔案層級的 skip 防護缺漏，非 CI 環境或統計邏輯問題）。
