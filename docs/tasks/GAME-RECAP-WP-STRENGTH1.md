# GAME-RECAP-WP-STRENGTH1 場中 WP 戰力感知先驗〔T4；🔴統計〕

- 需求：ruan6047（2026-07-26 會話確認走 VAL1 §7 路徑 2）　規劃：**待指派（MODEL_ROUTING L4；本卡面為 Fable 5 依已核可研究基線擬定之草稿，規劃者須定案模型形式與預註冊驗證設計後方可開放認領）**　分支：依認領時 worktree 慣例
- 執行：待指派（L4；統計正確性）　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: read`（研究階段唯讀；先驗參數 artifact 落檔案，物化與 `model_versions` 寫入屬 WP-API1 或其子卡——同 CAL1 慣例）
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：**僅 A 一軍例行**。C 需種子/讓一勝感知另卡（VAL1 §7.3）；D/E 維持 unsupported
- Discovery：`GAME-RECAP-WP-VAL1` ✅（偏差結構已量化）＋ `GAME-RECAP-WP-CAL1` 🏁（事後校準 No-Go，機制見其報告 §5）
- Design：Design Gate N/A；純統計模型層，不改 public API 或 UI
- current-state：💡需求；**規劃 gate 未過，不可 claim**——規劃者定案「候選設計擇一＋驗證預註冊」並更新本卡後，由 Coordinator 轉 📥Backlog。

## 背景（為什麼是這條路、為什麼只剩這條路）

WP-VAL1 證實 A scope 時間外 S 型偏差（低分箱 +4.2~+6.0pt／高分箱 −4.3pt，99% 叢集 CI 排除 0）。兩端成因不同：

- **高分箱（領先方低估）是結構性的**：中性隊伍假設的代價——現實中領先方不成比例地是較強隊（先發好投在投、戰力差），局面 DP 不知道。in-sample 亦顯著（−2.8pt），**任何事後校準都治不了**（CAL1 實證：校準修 bin 7 靠的是全域押低中心，代價是早局帶被推離真值）。
- **低分箱（落後方高估）主因主場優勢漂移**：base 窗自我吸收中（CAL1 §5：2023+ 早局帶 dev 僅 −0.1pt），殘餘部分戰力先驗可一併吸收。

CAL1 已關閉便宜路線並留下三條教訓，本卡設計必須內建：(1) 跨季彙整的預測-結果對**非同分布**（各季來自不同代 base 模型）；(2) 池化分箱指標對按局數異質的失效**無感**，逐局帶診斷必須進判定；(3) 內部窗指標會全數支持有害的修正，**嵌套時間外驗證是唯一防線**。

**排除路線（勿重走）**：校準窗變體（recency 窗/衰減加權）——CAL1 報告 §7 已標明勝率低（2026 base 已是全窗最佳校準，留給「校準」的空間逐年消失），不再投入。

## 目標

在局面 WP 之上疊加**賽前可知的隊伍戰力/先發投手先驗**，同時消除兩端偏差，使 A scope 通過 WP-VAL1 v2 門檻（含逐局帶診斷），解除 `GAME-RECAP-WP-API1` 的 A 範圍阻塞。

## 候選設計（規劃者擇一定案；可增列，定案理由留痕）

1. **logit 空間先驗融合（預設推薦，最小侵入）**：賽前先驗 p₀ 由 leakage-safe 戰力特徵（`features/outcome.py` 既有慣例：`prior_winpct_diff`、先發投手、`rest_days_diff`）之簡單模型給出；場中 `logit(WP_adj) = logit(WP_situ) + w(t)·(logit(p₀) − logit(p_home_base))`，權重 w(t) 隨比賽進行單調遞減至 0（保證終場收斂與再見門檻語意）。w(t) 形式與先驗模型參數皆須預註冊擬合準則。
2. **戰力條件化 run_dist**：依戰力差分箱分開估分布——樣本切薄（48 狀態 × 分箱），規劃者須先做樣本量可行性評估，不可行即淘汰留痕。
3. 其他（規劃者提出）：須通過同一嵌套驗證設計，不得另立寬鬆判準。

## 統計紅線（草稿；規劃者可加嚴、不得放寬）

1. **先驗只能用賽前可知資訊**：特徵 leakage-safe（比照 `features/outcome.py`：上季戰力、賽前累計、先發名單）；先驗模型與融合參數只能用 ≤Y−1 資料擬合。
2. **嵌套時間分離**：base 分布窗、先驗/融合參數訓練窗、驗證季三者嚴格分離且皆 ≤Y−1；驗證季與池化範圍由規劃者預註冊（建議沿用 2023–2026 便於與 base/CAL1 並排；2026 季末重跑）。
3. **單調與收斂語意**：WP_adj 對 WP_situ 單調、值域 [0,1]、終場收斂 0/1 與再見門檻語意不被先驗破壞（w(t)→0 或等價機制）；合約測試比照 `tests/test_winprob_cal.py` 慣例。
4. **判定沿用 WP-VAL1 v2 門檻不得放寬，且逐局帶（1-3/4-6/7-9）診斷納入硬性判定**（CAL1 教訓 (2) 的制度化；10+ 帶仍只揭露）；與未調整 base、CAL1 歷史結果三方並排。
5. **選型/超參數以訓練窗內預註冊準則定案**，嚴禁以驗證季表現挑選；wf 管線復用 `winprob_val`/`winprob_cal` harness（唯讀、seed 固定、`--out` scratch 紀律）。

## 驗收條件（草稿，規劃者定案後凍結）

- [ ] 先驗/融合層實作於 `models/`（消費既有 wf 管線），全程唯讀 DB；artifact 與報告入 `docs/research/`。
- [ ] 嵌套 walk-forward 報告：逐季＋池化 Brier、ECE、分箱偏差（cluster bootstrap CI）、逐局帶摘要，與 base（及 CAL1 歷史結果）並排；先驗模型參數/複雜度留痕。
- [ ] A scope 以 v2 門檻＋逐局帶硬性判定重判；**通過才解除 WP-API1 A 範圍阻塞，未通過即 No-Go**，不得以「接近門檻」放行。
- [ ] 離線合約測試：單調、端點、[0,1]、嵌套無洩漏、先驗 leakage-safe 特徵合約。
- [ ] `uv run ruff check`＋`uv run pytest` 全綠；驗證可重跑（seed 固定）；跨家族查核者重跑至少一個留出季。

## 依賴與交付

- 依賴：無阻塞（PA1 canonical、winprob_val/cal harness、game_features 皆已 merge）。
- 後續：通過 → 解除 `GAME-RECAP-WP-API1`（A scope），WP-API1 消費「base WP + 戰力先驗」並沿用本卡版本留痕；`UX-WP-DISCLOSURE1` 的註記文案屆時隨之修訂（另卡）。
- 預估範圍：M–L；不得順手修改 public API／前端／`winprob.py` 生產路徑。

## Log

- 2026-07-26 依 ruan6047 指示整理開卡（CAL1 No-Go 結案後續；需求方確認走 VAL1 §7 路徑 2）。卡面為執行過 VAL1/CAL1 之 Fable 5 依兩份已跨家族 APPROVE 報告擬定的草稿；**規劃 gate：MODEL_ROUTING L4 規劃者定案候選設計與驗證預註冊後才可開放認領**。Coordinator register 併同 commit。
