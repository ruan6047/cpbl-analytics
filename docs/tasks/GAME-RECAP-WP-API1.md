# GAME-RECAP-WP-API1 WP／WPA 參考資訊 public API（揭露語意）〔T3〕

- 需求：ruan6047　規劃：GPT-5@Codex（原 canonical 契約）＋2026-07-27 需求方定位改寫（見 Log）　分支：`ai/<執行者>/GAME-RECAP-WP-API1`
- 執行：待指派　查核：待指派（≠ 執行；邊界狀態機與 metadata 真實性為核對重點）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：依 DATA1 決策；預設 `read`，若物化另開 schema expand／backfill 卡
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §8、§10（§8.2 已允許「標示後提供」，細節同步屬本卡交付）
- Discovery：依賴 PA1 canonical contract ✅；統計驗證鏈已完結（VAL1 unsupported → CAL1 No-Go → STRENGTH1 交付 No-Go 待查核）
- Design：Design Gate N/A；本卡實作 public data contract
- current-state：📥Backlog；**已解除阻塞，可認領**（2026-07-27 需求方定位裁定：canonical → 參考資訊＋揭露；統計改善不再是前置）。

## 目標

只消費 `GAME-RECAP-PA1` 的 canonical 打席，為 **base 模型存在**的 scope 提供打席前後 WP、WPA、
受益隊與模型 metadata——**一律以「參考資訊」語意提供**：每筆回應附帶該 scope 的驗證結論
（時間外驗證 unsupported／分布借用等）、已知偏差量級（極端區間 ±4–6pt）與 `/methodology` 連結。
不宣稱 canonical、不暗示個人歸因具權威性；不再自行重建或去重打席。

**定位依據**：WP 辨別力真實（Brier 0.155 vs 主場常數 0.247），失準在極端分箱校準；兩條修復
路徑（事後校準 CAL1、戰力先驗 STRENGTH1）皆已驗證 No-Go，偏差屬長期存在 → 依「誠實第一」
（同賽果預測 ~60% 揭露上線的先例），**揭露後提供優於扣住不給**。

**升級路徑（保留原規劃）**：metadata 帶版本化的 `wp_reliability`（scope 驗證結論＋分布來源
自身/借用＋偏差揭露）。未來若更可靠的模型通過原 WP-VAL1 v2 門檻，將對應 scope 的 reliability
翻升為 validated 即可，consumer 無需 breaking change——原 canonical 規劃不作廢，只是後置。

## 驗收條件

- [ ] 每個可靠打席回傳 `pa_id`、`home_wp_before`、`home_wp_after`、`wpa`、受益隊與 model metadata，事件／比分／壘況直接引用 PA1 契約。
- [ ] 換局、終場、再見、和局、延長及不可靠狀態具有唯一 canonical 行為；不可靠列保留事件但 WP/WPA 不可用（fail closed 語意不因定位降級而放寬）。
- [ ] `wp_availability` 演進為 **reliability metadata**：逐 scope 聲明驗證結論、分布來源（自身／借自一軍例行）、已知偏差量級與方法頁錨點；**metadata 必須真實**，不得標示與 research 報告不符的狀態。本卡仍是此 metadata 的唯一 owner。
- [ ] WPA 隨 WP 一併提供（2026-07-27 需求方裁定），前端顯示處標「參考」並連 `/methodology`；與 `UX-WP-DISCLOSURE1` 文案對齊（數字同源自 VAL1/CAL1/STRENGTH1 報告）。
- [ ] `GAME_RECAP_PRODUCT_SPEC.md` §8.2 的欄位定義同步本卡定案（`wp_availability`→reliability 語意），需求方核可後併同交付。
- [ ] 現有 `/winprob` 採相容演進或 versioned route；前端遷移完成前不破壞既有 consumer。

## 驗證

- [ ] 先建立現有近似分組會失敗的 route／contract 紅燈測試。
- [ ] 邊界單元測試、API contract、route snapshot 與相容性測試通過。
- [ ] `uv run ruff check`、`uv run pytest` 通過；查核者複算至少一組 WP/WPA 邊界。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1` ✅（唯一硬依賴）。統計卡不再是前置。
- 後續：解除 `UX-GAME-RECAP1`、`UX-GAME-PA1` 的 WP 契約阻塞（兩卡改依本卡交付，全 T3 顆粒度）。
- 預估範圍：M；migration／大量 backfill 必須拆卡。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 為分離統計 Go/No-Go 與 API 實作而拆出；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
- 2026-07-25 WP-VAL1 結案：全 scope unsupported（merge c6ed954），本卡維持阻塞；解鎖路徑改經 `GAME-RECAP-WP-CAL1`。
- 2026-07-26 CAL1 結案 No-Go（修正不具時間平穩性）→ 解鎖改依 `GAME-RECAP-WP-STRENGTH1`。
- 2026-07-27 **需求方定位裁定（顆粒度調整會話）**：STRENGTH1 亦交付 No-Go（🔍待查核）後，確認偏差屬長期存在、統計改善鏈邊際效益失衡 → 本卡由「canonical 契約〔T4〕」改寫為「參考資訊＋揭露〔T3〕」，解除阻塞。WPA 照建議提供但標參考（需求方原文核可）；原 canonical 規劃保留為升級路徑（「等計算出更可靠數據後，原先規劃有機會可以做」），以 versioned reliability metadata 承接。Coordinator status 事件併同 commit。
