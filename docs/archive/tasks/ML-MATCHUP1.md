# ML-MATCHUP1 天敵候選／優勢對位統計洞察〔🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex（`matchups-redesign.md`）　分支：`ai/fable-5/ML-MATCHUP1`
- 執行：Fable-5@Claude Code（07-16 初版／07-16 二輪 P1 修正）／Opus-4.8@Claude Code（07-16 一輪退回修正）　查核：跨家族審核（07-16 兩輪退回，見下）＋**待獨立複查（非 Claude 家族）**
- worktree：`../cpbl-analytics-MATCHUP`（保留供查核者進駐）
- DB：`db_scope: read`；無新表／migration，洞察全由 API request 時計算（universe 記憶體快取 TTL 1h）
- 部署：否　環境：—　PR：—　Merge SHA：—

## 範圍／方法（實作定案）

- 主指標 `woba_generic_v1`：wOBA 型線性加權率（MLB 通用權重；僅作相對差異，主角／對手／聯盟同權重，尺度偏差對消）。跨年先加總原始計數再算 rate。
- **baseline 與 league_mean 取自官方完整季彙總**（`batting_seasons`/`pitching_seasons` + `*_current`，涵蓋全史 933 打者／1242 投手，可由官方數字驗證）——**不**取自對戰爬蟲子集（只含本季登錄打者、母體隨名單漂移，見審核）。投手官方季表無 1B/2B/3B 細分，以聯盟非全壘打長打比例拆分（HR 精確、分佈屬 BABIP 噪音）；投手 wOBA 分母 ≈ BF−IBB。對戰爬蟲樣本只提供「該配對觀察 rate」與「主角覆蓋率」。
- **leave-pair-out baseline（二輪審核必改 P1-3）**：官方兩側母體「包含」被評配對，直接當 baseline 會與配對樣本相依（covariance），噪音被過度扣除、tau² 系統性低估（合成宇宙實測 −78%）。故先自兩側官方彙總扣除該配對原始計數得剩餘 baseline，期望／殘差／noise／n_eff 全以此定義；扣除後計數或分母不為正 → 不可評估跳過。對稱期望：`expected = league_mean + batter_dev(LPO) + pitcher_dev(LPO)`；delta 單一號向（正=有利打者），角色翻轉同組對戰期望／|delta|／credibility 全同（建構保證＋測試）。
- 經驗貝氏收縮：delta ~ N(0, tau²) 先驗；sigma²（每機會事件變異）由官方打者事件分布算、tau² 由動差法估：`E[n·r²] = n·tau² + sigma²·(1+n/h_rem+n/p_rem)`（估計子集：配對 n≥50，避免微樣本負偏噪音壓低 tau²）。收縮用有效機會數 n_eff = 1/(1/n+1/h_rem+1/p_rem)。合成回收測試：已知 tau²=0.000401 的 self-inclusive 宇宙（400×25、n=50）修正版估 0.000431（+7.6%，±45% 帶內）；缺陷版估 0.0000863（−78%，帶外）。
- **先驗 fail-closed（二輪審核必改 P1-2）**：可用配對 < 20（`MIN_PAIRS_FOR_PRIOR`，動差估計相對誤差 >30%）即 `hyper=None`，端點不輸出方向性排行、`method.prior_available=false`／`pairs_used=0`／`tau2=null`，note 明示先驗無法估計；**嚴禁 tau²=sigma² 等任意常數 fallback**（等效先驗 1 機會，1 PA 對手 credibility 會到 0.99）。單季 scope 幾乎無 n≥50 配對 → 誠實全面 fail-closed。
- **覆蓋率閘門（二輪審核必改 P1-1）**：主角覆蓋率 = **全 scope**對戰樣本觀察機會數 / 官方生涯機會數，**在 opponent_team 篩選前評估**；隊伍篩選只限制候選對手（含歷史隊碼 franchise 映射），不影響資料完整性判定。回應以 `coverage`（全 scope，標 `scope: all_opponents`）與 `query_sample`（篩選後對手數／樣本量）分開回報。打者側 ~100% 過閘門；投手側中位數僅約 47%（官方生涯只被本季登錄打者對戰覆蓋、缺退休打者），< 60% 即 **fail-closed** 不輸出方向性結論。
- **kind C/E fail-closed**：官方季彙總僅涵蓋例行賽（A），C/E 無同賽事類型官方 baseline，不得借 A 組 baseline 假裝可比較 → 誠實回空並註明原因。
- 顯示閘門：後驗同號機率 ≥0.75；未達者不進候選（1 打數 1 轟永遠不會成為天敵）。敏感度：閘門 0.70/0.75/0.80 × 先驗強度 ×0.5/×1/×2 × 對手官方 baseline ≥100，名單成員變動即 `stable=false`。
- API：`GET /api/v1/players/{id}/matchups/insights`；回 `baseline`（官方）、`league`（官方，標 source）、`coverage`（全 scope：sampled/official/ratio/gate/passed）、`query_sample`（opponent_team/opponents/sampled_opportunities）、`advantages`、`disadvantages`、`sample_note`、`method`（baseline_source/observed_source/expected/sigma²/tau²/K/prior_available/pairs_used）、`sensitivity`、disclaimer。前端不得自行重做統計判定。

## 關鍵實證（生涯 kind A，2026-07-16 二輪修正後快照）

- 官方聯盟 wOBA=0.3197（打者側）／0.3148（投手被打側，denominator 慣例差 1.5%，各以自身均值中心化對消），可由官方季表加總復現。
- **tau²=0.000693（leave-pair-out 後）**、估計配對 344（n≥50）。一輪版 0.00039 是 self-inclusion 過度扣噪的低估；LPO 修正後先驗變寬鬆但仍極弱（~數百 PA 才各佔一半權重），與 The Book「matchup 資料大多雜訊」一致。
- 實測抽查（LPO baseline）：林泓育天敵候選＝陳鴻文（82PA，cred .895）／羅曼（.868）／德保拉（.801）；優勢＝官大元（.874）／林英傑（.857）；覆蓋率 100%。指定 ACN／AJL 後候選正常縮限至該 franchise（AJK011 舊碼被 AJL 命中），覆蓋率不變。limit=5 入榜對手最小機會數 27，無任何 ≤2 PA 對手；1AB 1HR 配對（范柏絜）不入榜。
- 覆蓋率閘門雙向實測：蔣銲 career pitching 覆蓋 99.7% 過閘門（候選被 credibility 濾空、誠實回空）；王勁力覆蓋 0.2% → fail-closed。郭天信 career 對六 franchise 逐一查詢：coverage 均為全 scope 1.0／passed（一輪版誤判 4%–23% 全清空的缺陷已修正）。
- 先驗 fail-closed 實測：郭天信 2026 season coverage 0.966 過閘門但 pairs_used=0 → `prior_available=false`、排行全空、note 明示先驗無法估計（一輪版 1 PA 對手 cred 0.996 入榜的缺陷已修正）。
- kind C/E 實測：誠實回空＋「無同賽事類型官方 baseline」註記。
- 資料形狀：對戰表僅 2026 年度＋生涯 9999（官網只提供本季＋生涯），`range` 多年查詢誠實回無資料；官方 baseline 則涵蓋全史。

## Log

- 07-15 WF-12 遷移：維持 Backlog，依賴 MATCHUP-DATA1。
- 07-16 ruan6047 指派執行（部署批次後）；control-plane claim＋worktree。確認 MATCHUP-DATA1 已於 07-14 結案（初判「缺卡」為誤，已修正認知：卡在 archive）。
- 07-16 實作：統計核心 `models/matchup_insights.py`（純函式）＋universe 載入快取（`api/matchups.py`）＋洞察端點（`routers/players.py`）＋route snapshot。
- 07-16 首版 tau² 撞 floor → 分層診斷 → 改 leave-pair-out＋噪音校正＋估計子集，實資料恢復合理訊號（過程留痕於上節，供查核者驗證）。
- 07-16 驗證：ruff 綠、pytest 229 passed；真實資料抽查 career／season／opponent_team／無資料／投打雙視角。推分支、保留 worktree，轉 🔍待查核。
- 07-16 **跨家族審核退回修正**（兩項必改）：(1) baseline／league 取自對戰爬蟲子集（只本季登錄打者、母體漂移），被當聯盟統計輸出；(2) 三 commit 缺工作流 trailers。審核設計面（leave-pair-out／對稱／低樣本閘門／敏感度）判定方向正確。
- 07-16 修正（Opus-4.8@Claude Code）：baseline＋league_mean＋sigma² 全改官方完整季彙總（可驗證、涵蓋全史）；投手 hits 以聯盟長打比例拆分；新增主角覆蓋率閘門（<60% fail-closed，投手多不過）＋對手 baseline 覆蓋敏感度；期望改 `league+batter_dev+pitcher_dev`（移除 leave-pair-out，官方 baseline 已完整）。tau² 估計子集改 n≥50（避免微樣本壓低）。ruff 綠、pytest 231 passed，真實資料復核官方聯盟 wOBA 0.3197、覆蓋率閘門雙向、season／career scope。commit trailers 補齊。
- 07-16 **二輪跨家族審核（GPT-5@Codex）REQUEST CHANGES**（三項 P1，對 a1fcbe7）：(1) opponent_team 先過濾再算 coverage，分子單隊／分母全生涯 → 904 組 player×franchise 中位 18.5%、僅 7 組過閘，郭天信對六隊全清空；(2) 無 n≥50 配對時 fallback tau²=sigma²（K=1）非 fail-closed，1 PA 對手 cred 0.996 入榜；(3) 官方 baseline 含被評配對卻用獨立樣本 noise 假設，忽略 covariance 系統性低估 tau²。
- 07-16 二輪修正（Fable-5@Claude Code）：**先寫 regression tests 於 a1fcbe7 跑紅再修**（P1-1 端點測試 fake cursor 重現 SQL 端過濾；P1-2 universe／端點雙層；P1-3 合成 self-inclusive 宇宙缺陷版 tau² −78% 深紅）。修正：coverage 移到篩選前（全 scope）＋`query_sample` 分開回報＋隊伍篩選只縮候選；`hyper=None` fail-closed＋`MIN_PAIRS_FOR_PRIOR=20`＋method 如實揭露；leave-pair-out baseline（期望／noise／n_eff 公式一致，扣除不足 → 不可評估）；kind C/E 無同類型官方 baseline → fail-closed。ruff 綠、pytest 241 passed（含 10 新測試）；真實資料 smoke 12 案（見關鍵實證）。轉 🔍**待獨立複查（非 Claude 家族）**。
