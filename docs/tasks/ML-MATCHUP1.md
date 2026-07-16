# ML-MATCHUP1 天敵候選／優勢對位統計洞察〔🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex（`matchups-redesign.md`）　分支：`ai/fable-5/ML-MATCHUP1`
- 執行：Fable-5@Claude Code（07-16 初版）／Opus-4.8@Claude Code（07-16 退回修正）　查核：跨家族審核（07-16 退回修正，見下）＋待複查
- worktree：`../cpbl-analytics-MATCHUP`（保留供查核者進駐）
- DB：`db_scope: read`；無新表／migration，洞察全由 API request 時計算（universe 記憶體快取 TTL 1h）
- 部署：否　環境：—　PR：—　Merge SHA：—

## 範圍／方法（實作定案）

- 主指標 `woba_generic_v1`：wOBA 型線性加權率（MLB 通用權重；僅作相對差異，主角／對手／聯盟同權重，尺度偏差對消）。跨年先加總原始計數再算 rate。
- **baseline 與 league_mean 取自官方完整季彙總**（`batting_seasons`/`pitching_seasons` + `*_current`，涵蓋全史 933 打者／1242 投手，可由官方數字驗證）——**不**取自對戰爬蟲子集（只含本季登錄打者、母體隨名單漂移，見審核）。投手官方季表無 1B/2B/3B 細分，以聯盟非全壘打長打比例拆分（HR 精確、分佈屬 BABIP 噪音）；投手 wOBA 分母 ≈ BF−IBB。對戰爬蟲樣本只提供「該配對觀察 rate」與「主角覆蓋率」。
- 對稱期望：`expected = league_mean + batter_dev + pitcher_dev`（各偏差以自身官方母體均值中心化）；delta 單一號向（正=有利打者），角色翻轉同組對戰不可能雙方同優（由建構保證＋測試）。
- 經驗貝氏收縮：delta ~ N(0, tau²) 先驗；sigma²（每機會事件變異）由官方打者事件分布算、tau² 由動差法估（估計子集：配對 n≥50，避免微樣本負偏噪音壓低 tau²）。收縮用有效機會數 n_eff = 1/(1/n+1/h_off+1/p_off)（官方 baseline 大 → ≈n）。
- **覆蓋率閘門（審核必改）**：主角覆蓋率 = 對戰樣本觀察機會數 / 官方生涯機會數。打者側 ~100% 過閘門；投手側中位數僅約 47%（官方生涯只被本季登錄打者對戰覆蓋、缺退休打者），< 60% 即 **fail-closed** 不輸出方向性結論。
- 顯示閘門：後驗同號機率 ≥0.75；未達者不進候選（1 打數 1 轟永遠不會成為天敵）。敏感度：閘門 0.70/0.75/0.80 × 先驗強度 ×0.5/×1/×2 × 對手官方 baseline ≥100，名單成員變動即 `stable=false`。
- API：`GET /api/v1/players/{id}/matchups/insights`；回 `baseline`（官方）、`league`（官方，標 source）、`coverage`（sampled/official/ratio/gate/passed）、`advantages`、`disadvantages`、`sample_note`、`method`（baseline_source/observed_source/sigma²/tau²/K）、`sensitivity`、disclaimer。前端不得自行重做統計判定。

## 關鍵實證（生涯 kind A，2026-07-16 快照）

- 官方聯盟 wOBA=0.3197（打者側）／0.3148（投手被打側，denominator 慣例差 1.5%，各以自身均值中心化對消），可由官方季表加總復現。
- tau²=0.00039、等效先驗 K≈611、估計配對 344（n≥50）。全池動差估會被 5000+ 微樣本配對壓到 0.00018，但 n≥50／n≥100 分層一致指向 ~0.0005，故估計子集設 n≥50。結論：對戰配對訊號存在但極弱（~600 PA 才各佔一半權重），與 The Book「matchup 資料大多雜訊」一致。
- 實測抽查（官方 baseline）：林泓育天敵候選＝陳鴻文（82PA，obs .218 vs 官方期望 .373，cred .83）／羅曼；優勢＝官大元／林英傑；候選 credibility 多在 .77–.86 且 `stable=false`，誠實揭露為弱訊號。覆蓋率 100% 過閘門。
- 投手 fail-closed 實測：伍鐸覆蓋率 64.6% 過閘門但候選被 credibility 濾空；某投手覆蓋率 17% → fail-closed，note 明示「僅覆蓋官方生涯 17%（門檻 60%），非隨機子集」。
- 資料形狀：對戰表僅 2026 年度＋生涯 9999（官網只提供本季＋生涯），`range` 多年查詢誠實回無資料；官方 baseline 則涵蓋全史。

## Log

- 07-15 WF-12 遷移：維持 Backlog，依賴 MATCHUP-DATA1。
- 07-16 ruan6047 指派執行（部署批次後）；control-plane claim＋worktree。確認 MATCHUP-DATA1 已於 07-14 結案（初判「缺卡」為誤，已修正認知：卡在 archive）。
- 07-16 實作：統計核心 `models/matchup_insights.py`（純函式）＋universe 載入快取（`api/matchups.py`）＋洞察端點（`routers/players.py`）＋route snapshot。
- 07-16 首版 tau² 撞 floor → 分層診斷 → 改 leave-pair-out＋噪音校正＋估計子集，實資料恢復合理訊號（過程留痕於上節，供查核者驗證）。
- 07-16 驗證：ruff 綠、pytest 229 passed；真實資料抽查 career／season／opponent_team／無資料／投打雙視角。推分支、保留 worktree，轉 🔍待查核。
- 07-16 **跨家族審核退回修正**（兩項必改）：(1) baseline／league 取自對戰爬蟲子集（只本季登錄打者、母體漂移），被當聯盟統計輸出；(2) 三 commit 缺工作流 trailers。審核設計面（leave-pair-out／對稱／低樣本閘門／敏感度）判定方向正確。
- 07-16 修正（Opus-4.8@Claude Code）：baseline＋league_mean＋sigma² 全改官方完整季彙總（可驗證、涵蓋全史）；投手 hits 以聯盟長打比例拆分；新增主角覆蓋率閘門（<60% fail-closed，投手多不過）＋對手 baseline 覆蓋敏感度；期望改 `league+batter_dev+pitcher_dev`（移除 leave-pair-out，官方 baseline 已完整）。tau² 估計子集改 n≥50（避免微樣本壓低）。ruff 綠、pytest 231 passed，真實資料復核官方聯盟 wOBA 0.3197、覆蓋率閘門雙向、season／career scope。commit trailers 補齊。
