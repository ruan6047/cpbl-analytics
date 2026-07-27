# TEAM-STYLE1 球隊球風研究〔🔴統計／資料正確性〕

- 需求：ruan6047　規劃：待研究 spec　分支：—
- 執行：待指派　查核：待指派（跨家族或人工）
- worktree：—（認領後建立）
- DB：`db_scope: read`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：先以年度／時期風格向量驗證速度戰、投手戰等描述性假說；候選特徵必須增量回測勝出才可進賽果模型。
- **消費表面（2026-07-27 需求方確認）**：球隊頁「球風」區塊（標籤或雷達）。**排程：等 GAME_RECAP_DESIGN_BRIEF v1.3 過 Gate 後派**（需求方 Q7 裁定，集中查核頻寬）。

## 紅線（違反即退回）

> 具體數值全部引用預註冊 spec（commit `50c23be`，先於一切計算；完整定義見
> [`../research/TEAM-STYLE1_RESULTS.md`](../research/TEAM-STYLE1_RESULTS.md) §0）。
> 本節為 canonical §5 要求的卡面紅線；iteration 1 開卡時缺此節，經查核退回補齊——
> **不改寫任何預註冊內容，只把已凍結的門檻抄上卡面**。

1. **描述性宣稱為限**：任何「球風可預測賽果」的宣稱不在本卡；候選特徵進 outcome
   模型須另卡增量回測勝出。報告不得出現預測性語言（含暗示）。
2. **預註冊凍結**：七軸定義與計算式、季內聯盟 z-score（ddof=0）、穩定性判準
   （**兩套判讀帶，各自獨立**——分半：r ≥ 0.5 高穩定／0.3 ≤ r < 0.5 中度／r < 0.3
   不穩定；跨季：r ≥ 0.3 中度延續／0.1 ≤ r < 0.3 弱／r < 0.1 無延續訊號）、
   face validity 三個隊季（2023 味全短打／2019 Lamigo 長打／2021 中信先發·三振）
   ——全部先於計算 commit 凍結；執行中不得增刪軸、改判準、換抽查隊季。
   未達門檻時**依對應判讀帶如實標記**（「不穩定」／「無延續訊號」）並保留於報告，
   不得刪除；單一檢定未達不等於整軸「不成立」（例：短打與長打分半不穩定但跨季
   中度延續，仍判可用）——「不成立」僅於相應檢定皆未達時作為綜合結論（如守備效率）。
3. **樣本窗口**：kind A、2018–2026、完成場依 `completed_games_sql()`（含
   `game_date <= CURRENT_DATE` 界線）；**2026 軸值照算但排除於全部穩定性檢定**
   （進行中球季）。母體＝45 隊季（4×3＋5×3＋6×3）、跨季配對＝33
   （franchise 對映凍結：Lamigo→樂天；味全 2021／台鋼 2024 無 t−1）。
4. **QA 門檻（凍結）**：逐年 games 完成場數 vs gamelog distinct 場數必須全等；
   2026 隊三圍 vs `team_current` |Δ| ≤ 0.002（口徑不符時照實記 FAIL、事後診斷
   須明標「非預註冊」）。
5. **DB 全程唯讀**（`db_scope: read`）：只准 SELECT；不碰爬蟲與 refresh 鏈
   （TM Gate3 觀測窗基線）。
6. **完整性宣稱須窮舉**：「全部隊季／配對已計算」須附母體對帳（45／33 逐項），
   artifact 內含 reconciliation。

## 驗收條件

- [ ] 預註冊 spec 以獨立 commit 先於計算 commit（git 歷史可證先後）。
- [ ] 七軸逐隊季 raw＋z 值、分半與跨季穩定性、face validity 三隊季結果全數落
      artifact（`docs/research/team_style1_metrics.json`）；報告數字與 artifact 一致。
- [ ] 母體對帳：45 隊季全數計算、33 組跨季配對窮舉、逐年 games vs gamelog 覆蓋全等。
- [ ] 檢定不過的軸（含 face validity FAIL）照實保留並標記，判準未回溯修改。
- [ ] 可重跑腳本（唯讀）重算與 artifact 逐位一致（除 `generated_at`）。
- [ ] `uv run ruff check`＋`uv run pytest` 全綠；新增計算邏輯有單元測試。

## 驗證

- [ ] 查核者以唯讀交易重跑腳本，diff artifact（除時間戳）為空。
- [ ] 查核者核對預註冊 commit 先於計算 commit，且 spec 內容未被後續 commit 改寫。
- [ ] 查核者確認報告無預測性宣稱、無回溯修改判準的痕跡。

## Log

- 07-15 WF-12 遷移：維持 Backlog。
- 07-22 新資料影響：官方 `leaderboards/summary` 可作年度聯盟 normalization／QA baseline，降低跨季 raw 值不可比；它不是球隊 split，仍須由球員或逐場資料按隊聚合，且候選特徵仍須增量回測勝出才可進 outcome。
- 2026-07-27 iteration 1 查核退回（卡面缺紅線章節，canonical §5）；Coordinator 補齊卡面，數值全部引用既有預註冊 spec `50c23be`，未改寫任何預註冊 commit。
- 2026-07-27 iteration 2 查核退回（卡面抄錄錯誤：兩套判讀帶被合併、「不成立」過度概括）；修正為逐字對應預註冊 spec §0.4。
