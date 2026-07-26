# GAME-RECAP-WP-CAL1 場中 WP 事後校準層〔T4；🔴統計〕

- 需求：ruan6047　規劃：基線＝[`GAME-RECAP-WP-VAL1_RESULTS.md`](../research/GAME-RECAP-WP-VAL1_RESULTS.md) §7 路徑 1（Gemini 跨家族 APPROVE @ c2ebb02）　分支：依認領時 worktree 慣例
- 執行：Claude Fable 5@Claude Code　查核：Gemini 3.6 Flash@Antigravity（跨模型家族 APPROVE @ 46bdd9e，零阻塞）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: read`；校準器 artifact 落檔案（`ARTIFACT_DIR`／`docs/research/`），`model_versions` 寫入與物化屬 WP-API1 或其子卡
- 部署：否　環境：—　PR：—　Merge SHA：`1b7188c`
- 範圍：**僅 A 一軍例行**。C（種子/主場混淆）、D（主場結構逐年不穩）、E（樣本不足）不在本卡，維持 unsupported
- Discovery：`GAME-RECAP-WP-VAL1` 已完成（全 scope unsupported；A 的 S 型偏差各季方向穩定 → 單調事後校準可行性有據）
- Design：Design Gate N/A；純統計模型層，不改 public API 或 UI
- current-state：🏁完成（No-Go）；A scope＋校準層 unsupported，`GAME-RECAP-WP-API1` A 範圍維持阻塞。結論報告：[`GAME-RECAP-WP-CAL1_RESULTS.md`](../../research/GAME-RECAP-WP-CAL1_RESULTS.md)。

## 目標

在既有局面 WP（`models/winprob.py` run_dist × WE DP）之上加一層**單調事後校準** [post-hoc calibration]（isotonic 為主、beta calibration 為對照），消除 WP-VAL1 證實的 S 型偏差（池化低分箱 +4.2~+6.0pt／高分箱 −4.3pt），使 A scope 通過 WP-VAL1 v2 門檻，解除 `GAME-RECAP-WP-API1` 的 A 範圍阻塞。

## 統計紅線（違反即退回）

1. **校準器只能用時間外預測擬合**：驗證季 Y 的校準器，訓練資料＝各季 s < Y 的 walk-forward 預測-結果對（該預測由 span ≤ s−1 的 base 模型產生，即 `winprob_val` 的 wf 輸出）。**嚴禁用 in-sample 預測擬合**——WP-VAL1 §1 已證明 in-sample 偏差剖面不同（低分箱偏差 in-sample 幾乎不存在，主要來自時間外才可見的主場優勢漂移），fit 在 in-sample 上會學到錯誤修正。
2. **嵌套時間分離**：base 模型窗、校準器訓練窗、驗證季三者嚴格分離且皆 ≤ Y−1；首個可校準驗證季自 2023 起（2021–22 wf 預測供第一個校準窗），驗證 2023–2026 逐季 + 池化。
3. **單調性與端點行為**：校準函數必須單調、值域 [0,1]，不得破壞 WP 曲線語意（終場收斂 0/1、再見門檻）；isotonic 須防小樣本尾端過擬合（段數/樣本下限），beta calibration（3 參數）作低複雜度對照。
4. **判定沿用 WP-VAL1 v2 門檻，不得另立寬鬆標準**：池化 walk-forward（n≥1000 分箱）|dev| ≤ 0.03 或 99% game-cluster CI 含 0；每季 Brier 勝主場常數基準且**不得劣於未校準 base**；coverage ≥ 0.98。門檻如需修訂，完整留痕理由（同 WP-VAL1 §5 慣例）。
5. **診斷不得惡化**：逐局帶（1-3/4-6/7-9/10+）校準摘要相對 base 不得系統性惡化；2024+ 突破僵局延長局樣本小，只列揭露不作支持證據。

## 驗收條件

- [ ] 校準層實作於 `models/`（消費 `winprob_val` 的 wf 預測管線），全程唯讀 DB；artifact 與報告寫 `docs/research/`。
- [ ] 嵌套 walk-forward 報告：逐季（2023–2026）+ 池化的 Brier、ECE、分箱偏差（cluster bootstrap CI）、與未校準 base 的並排對照、校準器參數/複雜度留痕。
- [ ] A scope 以 v2 門檻重新判定；**通過才解除 WP-API1 的 A 範圍阻塞，未通過本卡結論即 No-Go**，不得以「接近門檻」放行。
- [ ] isotonic vs beta 對照擇一定案並記錄理由；選型不得以驗證季表現挑選（用校準訓練窗內指標定案）。
- [ ] 離線測試：單調性、端點、[0,1] 值域、嵌套窗口無洩漏的合約測試（比照 `tests/test_winprob_val.py` 慣例）。

## 驗證

- [ ] `uv run ruff check`、`uv run pytest` 通過；驗證指令可重跑（seed 固定）。
- [ ] 獨立紅線 reviewer（跨家族）重跑至少一個校準留出季，核對嵌套窗口分離、分母與選型程序。

## 依賴與交付

- 依賴：`GAME-RECAP-WP-VAL1` ✅（harness 與 wf 預測管線直接復用）。
- 後續：通過 → 解除 `GAME-RECAP-WP-API1`（A scope）；WP-API1 消費「base WP + 校準層」而非裸 WP，並沿用本卡校準器版本留痕。
- 預估範圍：S–M；不得順手修改 public API／前端／既有 `winprob.py` 生產路徑。

## Log

- 2026-07-25 依 ruan6047 指示開卡（WP-VAL1 結案後續）→ 規劃基線取自已跨家族 APPROVE 的 WP-VAL1 報告 §7 路徑 1；Coordinator register 併同 commit。
- 2026-07-25 harness 注意事項（WP-VAL1 查核期實測）：`winprob_val` 預設輸出固定路徑，查核者以 `--kinds A` 重跑會覆寫完整 artifact（只剩 A scope）。本卡復用該 harness 時，部分 scope 重跑一律加 `--out` 導向 scratch 路徑；交付 artifact 以已提交版本為準。已同步寫入 [`CONTROL_PLANE_CONTRACT.md`](../CONTROL_PLANE_CONTRACT.md)「交付→查核→合併慣例」。
- 2026-07-26 Fable 5 claim（CLAIM-002）→ 依賴 WP-VAL1 已合併、spec 基線 v1.3 核對一致；WIP 1/4→2/4。
- 2026-07-26 Fable 5 執行完成 → handoff 🔍待查核（HANDOFF-003，分支 46bdd9e）。交付：`models/winprob_cal.py`（isotonic 等量分箱≥500PA/≤50 段＋加權 PAV＋端點釘；beta 3 參數 a,b>0 對照；復用 winprob_val wf 管線全程唯讀）＋ `tests/test_winprob_cal.py`（29 項離線合約）＋ 報告與 JSON artifact。嵌套分離：校準器只用 s<Y 的 wf 對、選型固定內部窗 fit2021→eval2022（beta 0.14466 勝 isotonic 0.14504）先於全部驗證季；v2 門檻未放寬＋新增門檻預註冊。結論：**A scope unsupported（No-Go）**——池化十分位 S 偏差可壓平（0 顯著分箱），但校準修正不具時間平穩性（1-3 局帶 0.1→2.6pt 惡化、2026 Brier 劣於 base +0.00075、2023 +0.00002、2026 coverage 0.9722 屬 PA build 時效缺口）；兩族同向排除實作因素。artifact `--out` scratch 重跑逐位一致。
- 2026-07-26 Gemini 3.6 Flash 跨家族查核 APPROVE（REVIEW-004，source_sha 46bdd9e）→ 零阻塞；查核者實測 ruff/pytest 522 passed、artifact diff -u 0 差異逐位重現、驗收六項全過、認同 No-Go 判定。findings 2 筆 INFO：2026 coverage 缺口屬資料工程時效（補齊亦不改結論）、變動零侵入生產路徑。
- 2026-07-26 merge + release（MERGE-005／RELEASE-006，依 ruan6047 於執行會話明確授權「授權 merge＋結案五步」）→ --no-ff 併入 main（merge_sha `1b7188c`，conflict-free 4 檔全新增，Reviewed-by Gemini 3.6 Flash）；main 上 ruff ✓、29 tests passed。免部署卡 release 即 🏁完成；WIP 2/4→1/4。後續：WP-API1 A 範圍維持阻塞；季末重跑不足以翻案（報告 §7）；校準窗變體（recency/衰減加權）須另卡預註冊；補跑 `cpbl-build-pa`（2026 sno 217–222）已建獨立 chip 非本卡阻塞。
