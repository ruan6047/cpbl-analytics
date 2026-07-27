# ML-OUTCOME-SIMPLE-LEAK2 上線 serving 模型 outcome_simple 去洩漏與閘門重校〔T4；🔴統計／ML〕

- 需求：ruan6047（2026-07-27 裁定「另開卡，ML-OUTCOME-LEAK1 先 merge 不部署」）　規劃：本卡 spec（源自 ML-OUTCOME-LEAK1 執行期發現）　分支：依認領時 worktree 慣例
- 執行：Claude（iteration 2 修正中）　查核：**須跨模型家族或人工**（canonical §5 紅線卡要求；iteration 1 已由 GPT 家族查核 REJECT）
- Initiative：—（獨立修正卡；與 `ML-OUTCOME-LEAK1` 同族）
- DB：`db_scope: write`（本機 derived：`model_versions(task='outcome_simple')`；`migration_phase: none`）＋ artifact 檔案寫入
- 部署：是（**與 `ML-OUTCOME-LEAK1` 必須同批上線**，見下方阻塞關係）　環境：production　PR：—　Merge SHA：—
- current-state：📥Backlog；已註冊，可認領。**在本卡完成前，`ML-OUTCOME-LEAK1` 不得部署、不得跑 `refresh-cpbl-prod.sh`。**

## 背景（為什麼）

`ML-OUTCOME-LEAK1` 修正了 `game_features` 的三個 starter 欄（同季彙總 → 賽前 as-of），
量化出前視洩漏貢獻約 6–7 個百分點。但該卡開卡時的前提「`/predict` 面板是唯一線上錯誤宣稱」
**不成立**：真正在 serving 的是 `outcome_simple`（`api/routers/daily.py` 首頁 pregame 點機率、
`api/routers/outcome.py`、`/methodology#pregame` 主展示），其四個固定語意訊號之一即 `starter_era_diff`。

**硬相依（部署阻塞的真正原因）**：`scripts/refresh-cpbl-prod.sh:236` 只重跑 `cpbl-train-outcome`，
**不重跑** `cpbl-train-outcome-simple`。一旦 LEAK1 上線並跑過一次 refresh，`game_features` 會以
修正後特徵重建並鏡像到 prod，而 prod 的 `outcome_simple.joblib`（fit 於洩漏特徵）將開始消費
修正後的分布 → **serving 端分布錯配**，不只是展示數字不一致。

**閘門問題**：LEAK1 執行期實測（test 2021–2025，n=1,585）修正後 `outcome_simple`
準確率 0.6126 → 0.5584、Brier 0.23203 → 0.24496、`calibration_slope` 1.054 → **1.373**
（超出 [0.8, 1.2]），部署閘門由 7/7 PASS 變 6/7、`deployable: false`。
`run_train_outcome_simple.main()` 在閘門失敗時不更新 serving artifact，因此**直接重跑會卡住**，
留下「指標已修正、serving 仍是洩漏訓練」的半套狀態——這正是 LEAK1 選擇不動它的原因。

## 目標

1. 以修正後的 `game_features` 重訓 `outcome_simple` 並使 serving artifact 與 `model_versions`
   一致落地（不得停在半套狀態）。
2. **重新檢視部署閘門門檻的正當性**：現行 `calibration_slope ∈ [0.8, 1.2]` 是對著含洩漏的模型
   校準的。拿掉強（假）訊號後辨別力下降、機率往基準率壓縮、斜率上升屬**預期行為**而非新缺陷。
   執行者須判定：(a) 門檻本身需依誠實模型重校；(b) 或模型需加後處理（如溫度縮放）；
   (c) 或兩者皆非、該模型不應繼續 serving。**三種結論皆可接受，但必須有證據且不得為過閘門而放寬到無意義。**
3. 若最終 `deployable: false` 成立，須明確定義 serving 的降級行為（維持舊 artifact 並揭露？
   或改回無模型的基準顯示？），不得靜默沿用洩漏訓練的 artifact。

## 紅線（違反即退回）

> 2026-07-27 iteration 1 查核 REJECT F5 指出：本卡修改 **serving ML 部署閘門**，屬 canonical
> [`AI_WORKFLOW.md`](../AI_WORKFLOW.md) §5 的統計／ML 紅線卡，須列本區塊並具體化窗口與門檻。
> 原卡面誤標 T3＋「統計最低限」係 Coordinator 開卡分級錯誤（依 2026-07-27 顆粒度共識，
> 動 serving／canonical 宣稱本就屬「重層」），已於本次更正。

1. 時間切分協定不變（沿用 `outcome_simple` 既有 walk-forward），不得為過閘門而改切分或測試期。
2. 特徵一律取自 `ML-OUTCOME-LEAK1` 修正後的 `game_features`，不得回退洩漏欄。
3. 閘門若調整，須並排「調整前後門檻值＋調整理由＋全押主場基準」，並說明為何新門檻不是「為了讓它過」。
4. **serving 狀態一致性不得靠人工紀律**：DB `model_versions` 與 serving artifact 的更新必須是
   一致性操作（先產生並驗證暫存 artifact 再切換 serving 指標），不得先 commit DB 再寫 artifact；
   任一步失敗時 DB 不得宣稱 `deployable=true` 而 serving 仍為舊版。
5. **失敗路徑不得靜默**：production refresh 中的 trainer 失敗碼必須傳遞（pipeline 不得吞
   exit code），且「最新回測未過閘門、serving 沿用版本 X」的狀態必須由後端明確回傳並在
   **首頁與方法頁同時**呈現，不得只寫進 log。
6. **統計敘述須精確**：型一誤差宣稱須標明其條件零假設；不得以數值接近推論歷史制定原因；
   區間寬窄的方向性描述須正確。

## 驗收條件

- [ ] `outcome_simple` 以修正後特徵重訓，`model_versions(task='outcome_simple')` 與 serving artifact 狀態一致（要嘛都更新、要嘛都不更新並明確揭露降級行為）。
- [ ] 閘門七項逐條列出前後值與判定；`calibration_slope` 的處置有明確結論與理由。
- [ ] `/methodology#pregame` 與首頁 pregame 點機率顯示的數字與新 `model_versions` 一致；若降級則揭露文案同步。
- [ ] **`scripts/refresh-cpbl-prod.sh` 補上 `cpbl-train-outcome-simple`**（或明確說明為何不該補），消除「refresh 後 serving 與特徵分布錯配」的結構性風險。
- [ ] `uv run ruff check`＋`uv run pytest`＋`cd web && npm test` 全綠；LightGBM／訓練步驟在容器內跑。

## 依賴與部署順序

- **依賴 `ML-OUTCOME-LEAK1`**（已 merge 待部署）。兩張**必須同批上線**：
  先合併本卡 → 一次部署 → 部署後才可恢復 `refresh-cpbl-prod.sh` 常規執行。
- **在本卡完成前**：不得部署 LEAK1、不得跑 `refresh-cpbl-prod.sh`（會觸發 game_features 鏡像）。

## 邊界

- 不改 `features/outcome.py` 的特徵語意（屬 LEAK1 交付，已 merge）。
- 不改 `models/matchup.py`（另列 follow-up：對戰卡仍用 `pitching_current` 當季彙總顯示先發數據，
  未開打場次無洩漏但與訓練分布尺度不同，`z` 會被高估；一致化時應改用同一支 `_starter_rates`）。
- 與 `LIVE-GAME-BACKEND1` lease 對帳後再 claim。

## Log

- 2026-07-27 依 ruan6047 裁定開卡（ML-OUTCOME-LEAK1 執行期發現卡面前提不完整：serving 模型另有其人、refresh 腳本不重跑 simple）。Coordinator register 併同 commit。
- 2026-07-27 iteration 1 交付（source 3174d70）→ **跨家族查核 REJECT**，4 個 Blocking：(1) `refresh-cpbl-prod.sh` 遠端 pipeline 吞掉 trainer exit code（實測 `sh -c 'false | grep | tail'` 回 0）→ trainer crash 仍寫成功標記，正是本卡要消除的錯配；(2) `run_train_outcome_simple.py` 先 commit `model_versions` 才寫 artifact，中途失敗會使 DB 宣稱 `deployable=true` 而 serving 為舊版；(3) 「沿用上一版」只進 log，API 未比對兩版本、首頁與方法頁皆未呈現降級狀態；(4)〔流程〕卡面誤標 T3 且缺「紅線（違反即退回）」區塊、實作 commit 缺 `Requested-by`／`Planned-by`／`Implemented-by` trailer。另 1 個 Minor：統計敘述三處不精確（區間寬窄方向誤述、「型一誤差恆定 5%」未標條件零假設、以數值接近推論舊門檻歷史成因）。
- 2026-07-27 Coordinator 認錯並更正卡面：分級 T3 → **T4；🔴統計／ML**，「統計最低限」改為 canonical §5 要求的「紅線（違反即退回）」區塊，並依查核 findings 新增紅線 4（serving 狀態一致性操作）、5（失敗路徑不得靜默）、6（統計敘述精確性）。分級錯誤係 Coordinator 開卡判斷失誤——依 2026-07-27 顆粒度共識，動 serving／canonical 宣稱本就屬「重層」，本不該落在輕層。查核者指出的跨家族要求實際上已滿足（Claude 執行、GPT 查核），僅分級與留痕需補。
