# GAME-RECAP-WP-VAL1 場中 WP 時間外驗證與支援邊界〔T4；🔴統計〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`claude/fable-5-suitable-tasks-8aa8d9`（harness 既建，claim 事件誠實記錄）
- 執行：Fable 5　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: read`；唯讀 canonical PA、games 與既有 run distribution／win expectancy
- 部署：否　環境：—　PR：—　Merge SHA：c6ed954e60d6f67e4a2e02a09d4b940d52bc8c63
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §8
- Discovery：`GAME-RECAP-DATA1` 已核可；仍依賴 `GAME-RECAP-PA1` canonical contract。
- Design：Design Gate N/A；本卡只做統計 Go/No-Go，不改 public API 或 UI
- current-state：📦已合併（merge_sha c6ed954，Gemini 跨家族 APPROVE @ c2ebb02）。結論：**A/C/D/E 全 scope unsupported，WP-API1 維持阻塞**；解鎖條件與報告見 [`GAME-RECAP-WP-VAL1_RESULTS.md`](../research/GAME-RECAP-WP-VAL1_RESULTS.md)。

## 目標

沿用現有 `models/winprob.py` 方法，但改用 PA1 的 canonical 打席，以 walk-forward／holdout season 驗證 WP 校準與規則邊界，先決定哪些賽季與賽制可對外提供，再投入 public API。

## 驗收條件

- [ ] 建模期間與驗證期間完全分離，逐季報告 Brier score、校準分箱、樣本數、主場基準與模型 span。
- [ ] 一軍例行賽、季後賽、二軍分別得到 `supported`、`proxy_with_warning` 或 `unsupported` 結論，不以一軍結果靜默外推。
- [ ] 再見、九局後規則、十二局和局、提前結束與狀態不可重建案例有明確統計處置。
- [ ] 產出 Go/No-Go 報告與門檻；未通過的 scope 不得進入 `GAME-RECAP-WP-API1`。

## 驗證

- [ ] 先證明現有同母體 calibration 不能作為時間外證據，再新增可重跑的 holdout／walk-forward 測試。
- [ ] `uv run ruff check`、`uv run pytest` 通過，驗證指令與 artifact 寫入 `docs/research/`。
- [ ] 獨立紅線 reviewer 重跑至少一個留出季並核對分母、資料洩漏與規則邊界。

## 依賴與交付

- 依賴：`GAME-RECAP-DATA1` ✅ → `GAME-RECAP-PA1`。
- 後續：只有通過的 scope 可解除 `GAME-RECAP-WP-API1` 阻塞。
- 預估範圍：M；不得順手修改 public API／前端。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 為分離統計 Go/No-Go 與 API 實作而拆出；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
- 2026-07-19 `GAME-RECAP-DATA1` Checkpoint 1 已核可 → 僅保留 PA1 為阻塞依賴。
- 2026-07-25 Fable 5 claim（CLAIM-002）→ 依賴 PA1 已解除（BUILD1 prod 330K PA 已驗證）；WIP 3/4→4/4。
- 2026-07-25 Fable 5 執行完成 → handoff 🔍待查核（HANDOFF-003，分支 c2ebb02）。交付：`models/winprob_val.py` 唯讀驗證 harness（訓練分布記憶體重建；與生產 run_dist 2018-2025/A 逐列對帳 match、解算器 legacy 規則逐值相等）＋ `tests/test_winprob_val.py`（13 項離線）＋ Go/No-Go 報告與 JSON artifact。結論：池化 walk-forward（A 1,826 場）十分位 1–3 偏差 +4.2~+6.0pt、十分位 8 −4.3pt（99% game-cluster CI 排除 0）→ **A/C/D/E 全 unsupported、WP-API1 維持阻塞**；同框架 in-sample 僅 ECE 0.0147 且低分箱不顯著，證明同母體 calibration 非時間外證據（驗收①）。規則邊界 (kind,year) 參數化（2024+ 突破僵局／C·E 無和局／D 分年 9·10 局）；再見/宵禁/保留賽/狀態不可重建 fail closed＋敏感度。門檻 v1→v2 修訂（叢集相關）完整留痕於報告 §5。驗證：ruff ✓、pytest 468 passed、`uv run python -m cpbl.models.winprob_val` 可重跑（seed 固定）。
- 2026-07-25 Gemini 跨家族查核 APPROVE（REVIEW-005，source_sha c2ebb02）→ 零阻塞缺陷；查核者實測重現留出季 A2025 分母逐位一致、洩漏稽核（C/E train_to=Y 經 SQL 實證無時間洩漏）、規則邊界映射精確、門檻 v1→v2 判定為統計糾錯非 p-hacking。findings 2 筆 INFO：2026 進行中賽季季末重跑、counting_machine_check 離線 skipped 屬設計內。待 merge＋release。
- 2026-07-25 merge + release（MERGE-006／RELEASE-007，依 ruan6047 授權）→ --no-ff 併入 main（merge_sha c6ed954，conflict-free 4 檔全新增）；main 上 pytest 13 passed／ruff ✓；lease 釋放、WIP 4/4→3/4；worktree 留待 harness 回收。後續：WP-API1 解鎖走報告 §7、2026 季末重跑（Gemini INFO-1）、賽況頁 WP 曲線偏差註記留需求方裁定。
