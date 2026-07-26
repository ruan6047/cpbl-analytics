# ML-OUTCOME-LEAK1 賽果預測先發特徵前視洩漏修正〔T3〕

- 需求：ruan6047（2026-07-27 顆粒度調整會話裁定；源自 GAME-RECAP-WP-STRENGTH1 執行期實證）　規劃：本卡 spec　分支：依認領時 worktree 慣例
- 執行：待指派　查核：待指派（≠ 執行；重點核對「新特徵只含賽前事件」與回測數字一致性）
- Initiative：—（獨立修正卡）
- DB：`db_scope: write`（derived：`game_features` 重建、`model_versions(task='outcome')`；`migration_phase: none`。本機→prod 鏡像照既有 derived 慣例）
- 部署：是（面板數字修正上線才有意義）　環境：production　PR：—　Merge SHA：—
- current-state：📥Backlog；已註冊，可認領。

## 背景（為什麼）

`features/outcome.py` 的 `starter_era_diff`／`starter_whip_diff`／`starter_k9_diff` 以
`(starter_id, year)` 讀**同季彙總**（`pitching_seasons`／`pitching_current`）——對歷史回測，
模型在賽前就看見該投手該季之後的表現。**實證**（STRENGTH1 `--diagnostics`，
[`GAME-RECAP-WP-STRENGTH1_RESULTS.md`](../research/GAME-RECAP-WP-STRENGTH1_RESULTS.md) §6.2）：
加入該三欄後 2023–2026 四季一致產生 0.010–0.017 的假性 Brier 改善，而 leakage-safe 同類資訊
幾乎無效——前視洩漏的典型指紋。

**線上影響**：`/predict` 模型回測面板的 LightGBM ~62%（`model_versions`）與互動探索器中
含先發特徵組合的回測準確率都被高估。這是目前唯一「已知錯誤仍在線上展示」的宣稱。

## 目標

1. 三個 starter 特徵改為**賽前可得**：as-of 逐場 running state ＋ 前一季 prior 收縮
   （語意與機制可復用 `models/winprob_strength.py` 的 starter 累計；欄名是否沿用由執行者定，
   但語意變更須在前端 tooltip 同步反映）。
2. 重跑 `cpbl-train-outcome` 走查回測，更新 `model_versions(task='outcome')` 與 `/predict` 面板。
3. 互動探索器（`models/outcome.py`）的先發特徵同步換用新欄。
4. **準確率下降屬預期且是本卡目的**（誠實修正）；不得為了維持 62% 而保留洩漏欄或調整協定。

## 統計最低限（僅此三件；不掛完整紅線儀式——2026-07-27 顆粒度共識）

1. 時間切分協定不變（既有 walk-forward），不得為了數字好看而改切分。
2. 新特徵須可證明只含 `game_date` 前事件（測試比照 STRENGTH1 的 running-state 合約測試即可，勿加碼）。
3. 回測對照表永遠並排「全押主場」基準，並保留「修正前（含洩漏）vs 修正後」對照一次性留痕。

## 驗收條件

- [ ] `game_features` 重建後三欄為賽前值；離線測試證明不含該場與該季未來事件。
- [ ] 容器內 `cpbl-train-outcome` 重跑，`model_versions` 新列；`/predict` 面板與 API 回傳一致。
- [ ] 修正前後對照表寫入交付紀錄（預期 62% 下修；下修幅度即洩漏貢獻的量化）。
- [ ] `uv run ruff check`＋`uv run pytest`＋`cd web && npm test` 全綠；本機→prod 資料鏡像完成。

## 邊界

- 不動 WP 系列（winprob*）、不動賽果預測的模型族與協定——只修特徵的時間語意。
- 與 `LIVE-GAME-BACKEND1` lease 零重疊（`features/outcome.py`、`models/outcome*.py`、`web/` predict 區塊）；claim 時再對帳。

## Log

- 2026-07-27 依 ruan6047 指示開卡（顆粒度調整：把打磨投到「線上已知錯誤」而非研究原型）。Coordinator register 併同 commit。
