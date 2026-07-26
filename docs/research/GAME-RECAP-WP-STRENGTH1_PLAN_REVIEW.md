---
card: GAME-RECAP-WP-STRENGTH1
document_type: plan-review-result
status: approved
verdict: APPROVE
reviewer: Google Gemini 3.6 Flash
reviewer_family: Google Gemini
reviewed_base_sha: ecde1c5fd1c8a82615c9d158d452c3a0e2a53cf1
spec_baseline: v1.3
source: requester-transcribed
reviewed_at: 2026-07-26
---

# GAME-RECAP-WP-STRENGTH1 Plan Review

- Reviewer：Google Gemini（Gemini 3.6 Flash／Google Gemini Family）
- Reviewed commit / working-tree state：`ecde1c5fd1c8a82615c9d158d452c3a0e2a53cf1`；working tree 包含未提交的 `GAME-RECAP-WP-STRENGTH1.md`、`GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW_REQUEST.md` 與 `GAME-RECAP-WP-STRENGTH1_RESEARCH.md`
- Spec baseline check：`v1.3 == INIT-GAME-RECAP current` **PASS**
- Verdict：**APPROVE**

> 紀錄註記：本報告由需求方 ruan6047 轉錄跨家族 reviewer 回覆。此為規劃 gate 查核，不取代未來 implementation T4 review，也不自行寫 lifecycle event。

## Findings

### F-01 [P3] 軟標籤 `y=0.5` 的 L2 邏輯斯迴歸最佳化實作提醒

- 位置：[`GAME-RECAP-WP-STRENGTH1.md`](../tasks/GAME-RECAP-WP-STRENGTH1.md) §先驗模型預註冊
- 矛盾：無統計或設計矛盾。`y=0.5` 的 Binomial Cross-Entropy／Brier Score／Log-Loss 極小值皆為 `p=0.5`，統計語意自洽。
- 證據：若執行者在實作時直接呼叫 scikit-learn 的 `LogisticRegression.fit(X, y)`，傳入含 `0.5` 的浮點數 `y` 會引發 `ValueError: Unknown label type: 'continuous'`。
- 影響：不影響規劃正確性或 Go/No-Go 判定；僅為實作階段的 API 工具套用提醒。
- 必要修正（不阻擋 Backlog）：若使用只接受離散類別的 Python 分類器，可將 `y=0.5` 和局拆成兩筆權重 `0.5` 的樣本（`y=1, sample_weight=0.5` 與 `y=0, sample_weight=0.5`），或以 `scipy.optimize.minimize`／等價決定性凸優化計算自訂 L2 Binomial Cross-Entropy。

## C1–C20 Checklist

| ID | 結果 | 一句證據 |
|---|---|---|
| C1 | PASS | `w_gamma(0)=1` 且開場 `WP_situ=p_base0`，故 `WP_adj=p0`；扣除 `p_base0` 避免重複計算主場優勢。 |
| C2 | PASS | `t(s)` 以 54 個半出局平滑映射至 `[0,1]`，10+ 局固定 `w(t)=0` 退回 `WP_situ`，終場／再見端點由 canonical 狀態機直回 0/1。 |
| C3 | PASS | `y=0.5` 套用 binomial cross-entropy 的損失極小值落在 `p=0.5`，與 Brier `(p-0.5)^2` 及 log-loss 統計語意一致。 |
| C4 | PASS | 每個驗證季 Y 均只由 `≤Y-1` 資料擬合與選型，各 fold 均屬嚴格時間外預測；報告保留逐季與池化雙視角，不誤稱為單一同分布 holdout。 |
| C5 | PASS | 2026 特徵與 `(kappa, lambda, gamma)` 選型由 2018–2024 fit、2025 inner selection 預先鎖定，2026 advanced shadow 嚴禁參選，選型隔離完整。 |
| C6 | PASS | `current_num/den` 嚴格累積至賽前，`prior_rate` 採前一季或 fit-window 聯盟率，`kappa` 選型早於目標季，無未來資訊洩漏。 |
| C7 | PASS | 2017 `pitching_seasons` 具 SO／BB／HBP／HR／BF／IP，可供 K−BB 與 FIP 初始 prior；缺失之好球數可 fail closed 退回 fit-window 聯盟率而不讀 2018 未來。 |
| C8 | PASS | 八項特徵皆定義為正值有利主隊（FIP proxy 採 away−home），`kappa` 收縮確保分母大於 0，記錄好球占比明確標明非 TrackMan `zone%`。 |
| C9 | PASS | 牛棚 K−BB 僅累積目標場前 `role_type != '先發'` 的歷史 gamelog 投球，不依賴目標場賽後出賽名單或同季最終角色。 |
| C10 | PASS | `cpbl.games` 先發 ID 賽前已知，未賽或紀錄缺值時由預註冊 `kappa` prior 階層補值，2018–2026 A 覆蓋率 99.92% 滿足 `≥0.98` 門檻。 |
| C11 | PASS | 先以 Y−1 逐場 Brier 選定 `(kappa,lambda)`，再以 Y−1 逐 PA Brier 選定 `gamma`，程序早於 Y 且權重層級解釋合理。 |
| C12 | PASS | full 八特徵模型是唯一預註冊驗收對象，team-only 與 team+starter 僅作診斷，明確禁止依 Y 評估結果事後切換模型。 |
| C13 | PASS | 完整沿用 VAL1 v2 門檻，並將 1–3／4–6／7–9 局帶絕對偏差及相對 base 惡化（`>2pt` 或兩帶 `>1pt`）列為硬性失敗。 |
| C14 | PASS | 沿用 500 次 game-cluster bootstrap 與 99% CI 檢定，門檻與 VAL1 v2／CAL1 一致，無隱性放寬。 |
| C15 | PASS | 附錄 A 證明 3／5 箱格數可用觀測 `≥99.70%`，未選理由誠實歸因於高維、硬分箱不連續與維護成本，而非偽稱樣本不足。 |
| C16 | PASS | Tavily 重審將文獻主張限縮為架構參考與收縮原理，將舊 FiveThirtyEight 效果量與 MLB 係數降為不作證據，未過度宣稱。 |
| C17 | PASS | 2026 advanced shadow 僅作診斷與前瞻蒐集，紅線禁止回改本卡；未來 ADV1 必須有獨立留出期。 |
| C18 | PASS | 預計一個模型模組、一個測試模組與報告／artifact，將 2026 advanced 拆至 ADV1，範圍控制在 M–L。 |
| C19 | PASS | 模組獨立落於 `models/winprob_strength.py`，匯入 `winprob_val`／`winprob_cal` 公開 helper，支援 `--out` scratch，不改既有 harness 與 production path。 |
| C20 | PASS | spec 基線為 INIT-GAME-RECAP v1.3，角色標註 L4 層級，查核獨立於執行，無 lifecycle event 越權寫入。 |

## 結論

`GAME-RECAP-WP-STRENGTH1` 規劃案經獨立審核，無 P0–P2 阻擋性缺陷，C1–C20 必答項全數通過，裁決為 **APPROVE**。

本規劃在統計學與資料工程面具備以下完整性：

- **融合形式**：以 opening anchor（`p0` 減去同代 base 開場 WP）隔離 base DP 已包含的主場優勢，防止重複計算。
- **選型與時間分離**：四個 walk-forward fold（Y=2023..2026）的超參數與先驗模型皆僅在 Y−1 內部窗定案，評估季 Y 處於鎖箱狀態。
- **驗收與門檻加嚴**：吸取 CAL1 失效教訓，將逐局帶絕對與相對偏差列為硬性關卡，且 full 八特徵模型是唯一預註冊驗收標的。

本 `APPROVE` 僅解除規劃矛盾疑慮；卡面仍須由需求方 sign-off，並由 Coordinator 寫 lifecycle event 後才可轉 📥Backlog。

## Backlinks

- [[GAME-RECAP-WP-STRENGTH1]]
- [[GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW_REQUEST]]
- [[GAME-RECAP-WP-STRENGTH1_RESEARCH]]
- [[INIT-GAME-RECAP]]
