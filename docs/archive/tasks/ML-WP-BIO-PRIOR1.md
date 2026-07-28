# ML-WP-BIO-PRIOR1 WP 賽前先驗 bio 方向研究 spike〔T3；輕量研究層試跑〕

- 需求：ruan6047（2026-07-27 顆粒度調整會話裁定：繼續 WP 先驗方向、但降顆粒度）　規劃：本卡 spec　分支：依認領時 worktree 慣例
- 執行：待指派　查核：待指派（≠ 執行；輕量——核對協定遵守與判準即可，不跨家族）
- Initiative：INIT-GAME-RECAP（研究支線；不影響 WP-API1 阻塞狀態）　spec 基線：v1.3
- DB：`db_scope: read`（全程唯讀）
- 部署：否　環境：—　PR：—　Merge SHA：—
- current-state：📥Backlog；已註冊，可認領。**輕量研究層第一張試跑卡**（口頭慣例，未入流程文件）。

## 背景（為什麼）

STRENGTH1 No-Go 根因＝八項賽前特徵時間外無增量資訊（p0 vs 主場常數平均僅 −0.0009）。
執行期 scratch 評估發現 **bio 三項（年紀／洋將身份／年資）** 的池化 Δ ≈ −0.0053、99% 逐場
bootstrap CI 排除 0，效果約卡面八項的 3 倍；機制合理（洋將先發平均強於本土、100% 先發可得、
正好覆蓋 29.6% 零 CPBL 前史的缺口）。**但**該評估是看過 2023–2026 結果後做的＝選型洩漏，
且 2026 反向（+0.006）——需要乾淨重估，不可直接引用。

## 目標（只做一件事）

過前置關卡：「**bio 先驗 p0 在時間外多季穩定勝過主場常數**」。
deliverable ＝ `docs/research/` 短 memo（1–2 頁）＋可重跑腳本。
**不做融合、不動 winprob_strength.py 判定、不上線。** 過關 → 融合與上線另開卡升級到重層
（屆時才跨家族查核）；不過關 → 結論落 memo 收攤，WP 先驗路線正式封存。

## 統計最低限（僅此三件預註冊；不凍網格、不跨家族 plan review）

1. **協定固定**：fit 2018..Y−1 → 只評 Y（Y=2023–2026）；L2 logistic 固定 λ=100 一組
   （不掃網格——消除選型自由度，這是輕量層換來乾淨的代價）。特徵組固定一組：
   隊伍四項（沿 STRENGTH1）＋ bio 三項（年紀差／身份差／年資差），共七項，執行前不得增刪。
2. **賽前可得**：身份用 `ingest/imports.py` canonical 判定（含羅力／永田條款 override，勿用
   `country != '中華民國'` 粗規則）；年資用「首次出現於 `pitching_seasons` 的年份」推導
   （`players.debut` 覆蓋僅 65%，不用）；生日缺值（14 位）fail-closed 規則在 memo 明寫。
3. **判準預先寫死**：池化逐場 Brier 優於主場常數、99% 逐場 bootstrap CI 排除 0，
   **且 2026 不得顯著反向**（scratch 評估已見 +0.006 警訊，必列方向檢查）。
   三者同時成立才算過關；差一點就是不過，不得事後解釋。

## 驗收條件

- [ ] 依上節三件最低限執行：協定固定（fit 2018..Y−1 → 只評 Y，Y=2023–2026）、七特徵與 λ=100 執行前凍結、身份／年資／生日的賽前可得規則明寫。
- [ ] 判準三項逐條回答（**同時成立才算過關**）：池化逐場 Brier 優於主場常數基準、99% 逐場 bootstrap CI 排除 0、2026 不得顯著反向。差一項即「不過關」，不得事後解釋或改協定重跑。
- [ ] 交付 `docs/research/` 短 memo（1–2 頁）：逐季與池化數字、三項判準逐條結論、與 STRENGTH1 卡面八項的對照、明確 Go/No-Go 一句話。
- [ ] 附可重跑腳本與指令；DB 全程唯讀（腳本內無寫入語句）。
- [ ] `uv run ruff check`＋`uv run pytest` 全綠。

## 驗證

- [ ] memo 數字與腳本輸出逐位一致（查核者重跑至少一季複核）。
- [ ] 查核者確認：特徵未於執行期增刪、未掃網格、未使用 `players.debut`（覆蓋僅 65%）、身份走 `ingest/imports.py` canonical 判定。

## 邊界

- 唯讀 DB；不改任何生產路徑與既有 harness；scratch 先跑、定稿才落 `docs/research/`。
- 預估 S（半天內）；超出即停，回報需求方。

## Log

- 2026-07-27 依 ruan6047 指示開卡（顆粒度調整：輕量研究層試跑第一張；繼續 WP 先驗方向的最低成本驗證）。Coordinator register 併同 commit。
- 2026-07-28 查核 APPROVE 零阻塞（Google Gemini 3.6 Flash 獨立 session；ruff clean／pytest 728 passed／artifact 重跑 bitwise 相同／C1–C3 逐條 PASS／預註冊時序 git 可證）。需求方授權後 `--no-ff` merge `ac06535`，免部署卡 release 即 🏁完成。兩項 Low finding（F-01 對照臂改用 STRENGTH1 `ablation.team_only`；F-02 2025→2026 fit 窗的錯誤身分旗標傳播鏈）依查核者建議轉為融合／升級卡前置紀錄項，不在本卡再開一輪。

