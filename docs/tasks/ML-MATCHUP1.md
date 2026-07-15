# ML-MATCHUP1 天敵候選／優勢對位統計洞察〔🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex（`matchups-redesign.md`）　分支：`ai/fable-5/ML-MATCHUP1`
- 執行：Fable-5@Claude Code（07-16 ruan6047 指派）　查核：待指派（跨家族或人工＋實測）
- worktree：`../cpbl-analytics-MATCHUP`（保留供查核者進駐）
- DB：`db_scope: read`；無新表／migration，洞察全由 API request 時計算（universe 記憶體快取 TTL 1h）
- 部署：否　環境：—　PR：—　Merge SHA：—

## 範圍／方法（實作定案）

- 主指標 `woba_generic_v1`：wOBA 型線性加權率（MLB 通用權重；僅作相對差異，主角／對手／聯盟同權重，尺度偏差對消）。跨年先加總原始計數再算 rate。
- 對稱期望：`expected = batter_loo + pitcher_loo − league_mean`（**leave-pair-out** baseline，避免期望被觀察值本身拉動）；delta 單一號向（正=有利打者），角色翻轉同組對戰不可能雙方同優（由建構保證＋測試）。
- 經驗貝氏收縮：delta ~ N(0, tau²) 先驗；sigma²（每機會事件變異）由聯盟事件分布算、tau² 由動差法估（估計子集：配對 n≥10 且兩側外部 baseline ≥100，含 baseline 抽樣噪音校正）。收縮用有效機會數 n_eff = 1/(1/n+1/h_n+1/p_n)。
- 顯示閘門：後驗同號機率 ≥0.75；未達者不進候選（1 打數 1 轟永遠不會成為天敵）。敏感度：閘門 0.70/0.75/0.80 × 先驗強度 ×0.5/×1/×2，名單成員變動即 `stable=false`。
- API：`GET /api/v1/players/{id}/matchups/insights`（role/scope/season/range/opponent_team/limit）；回 `baseline`、`league`、`advantages`、`disadvantages`、`sample_note`、`method`（sigma²/tau²/K/估計配對數）、`sensitivity`、descriptive disclaimer。前端不得自行重做統計判定。

## 關鍵實證（生涯 kind A，2026-07-16 快照）

- **首版估計器把 tau² 壓到 floor（全數 0 候選）**：診斷發現兩個偏差——配對含在自身 baseline 內的自我污染、1.7 萬個微樣本配對的負偏噪音。分層診斷：n≥60 配對以 leave-pair-out 期望的標準化殘差比 1.52（>1 → 訊號存在）。
- 修正後 tau²=0.000821、等效先驗 K≈295 機會、估計配對 5,096——「對戰配對訊號存在但弱，~300 PA 才各佔一半權重」，與 sabermetrics 文獻（The Book：matchup 資料大多是雜訊）一致。
- 實測抽查：林泓育天敵候選＝陳鴻文（82PA，obs .218 vs exp .389，cred .92）／羅曼／德保拉；伍鐸被蘇智傑、陳傑憲打爆、壓制林泓育——跨視角同組對戰 |Δ| 一致、標籤鏡像。邊界候選在敏感度掃描下會進出名單 → `stable=false` 誠實揭露。
- 資料形狀：對戰表僅 2026 年度＋生涯 9999（官網只提供本季＋生涯），`range` 多年查詢誠實回無資料。

## Log

- 07-15 WF-12 遷移：維持 Backlog，依賴 MATCHUP-DATA1。
- 07-16 ruan6047 指派執行（部署批次後）；control-plane claim＋worktree。確認 MATCHUP-DATA1 已於 07-14 結案（初判「缺卡」為誤，已修正認知：卡在 archive）。
- 07-16 實作：統計核心 `models/matchup_insights.py`（純函式）＋universe 載入快取（`api/matchups.py`）＋洞察端點（`routers/players.py`）＋route snapshot。
- 07-16 首版 tau² 撞 floor → 分層診斷 → 改 leave-pair-out＋噪音校正＋估計子集，實資料恢復合理訊號（過程留痕於上節，供查核者驗證）。
- 07-16 驗證：ruff 綠、pytest 229 passed（統計核心 15＋端點 3 新測試，含對稱性、1-for-1 閘門、動差法 pin 數字、敏感度結構）；真實資料抽查 career／season／opponent_team／無資料／投打雙視角。推分支、保留 worktree，轉 🔍待查核。
