<!-- 本檔由 build_verdict_list.py 產生，勿手改；改處置請改 dispositions.json 後重跑。 -->

掃描檔數 122／重審母體 64／處置覆蓋 64（missing 0、ghost 0）

裁決分布（S＋F 類，即實際落裁決者）：維持 28、需改寫理由 3、需重跑 1

## S 統計判定（12 份）

| 檔案 | 裁決 | tier1 | 理由 |
|---|---|---:|---|
| `GAME-RECAP-WP-CAL1_RESULTS.md` | 需重跑 | 13 | 四條硬性失敗逐條都有問題（雜訊尺度／管線落後／母體已修復／閘門無不確定性量化），且 2026 的 PA build 缺口事後已補跑，重跑才知道現況。 |
| `GAME-RECAP-WP-STRENGTH1_RESULTS.md` | 需改寫理由 | 20 | 唯一失敗閘門 4c 是點估計比較，報告自己載明四季 Δ 的 99% CI 全含 0。No-Go 決定正確（未證立增益不得上線），但理由不得寫成『融合有害』。 |
| `GAME-RECAP-WP-VAL1-FIX1_ERRATA.md` | 需改寫理由 | 3 | E scope 判定的現行事實來源。兩條硬性理由（E2025 Brier 輸基準、池化 ECE > 0.05）在 4 場／13 場的樣本下皆不具解析度，與 VAL1 E 同一處置。 |
| `GAME-RECAP-WP-VAL1_RESULTS.md` | 需改寫理由（A:維持／C:需改寫理由／D:需改寫理由／E:需改寫理由） | 17 | A scope 判定在雜訊底線之上且對 seed 穩健，維持；C/D/E 的決定性理由各自踩到準則 3 或準則 1（詳 VERDICTS.md §3.1）。整份因此標需改寫理由。 |
| `ML-OUTCOME-LEAK1_RESULTS.md` | 維持 | 4 | 洩漏的存在由變異測試、DB 層反證、同路徑前後對照三條互相獨立的證據確立，不倚賴任何門檻；『outcome_gbm 62% 不可當賽前預測力證據』是其正確推論。 |
| `ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md` | 維持 | 11 | (b) 溫度縮放的否決建立在時間外評估＋零假設模擬（固定區間偽失敗率 41.8%），是本專案內三準則的正面示範，本卡的雜訊底線方法即沿用其 §3.2。 |
| `ML-UMP1_RESULTS.md` | 維持 | 1 | 方向翻轉是 18/18 主審、6/6 隊全面發生的定義不穩定，不是離群個案；leave-one-venue-out 0 翻轉已排除覆蓋缺口為成因。三準則皆不適用。 |
| `ML-UMP2_RESULTS.md` | 維持 | 6 | 同 ML-UMP1。身高比例帶換掉固定帶後 18/18 主審整體換號，證明方向由帶定義決定；覆蓋缺口是永久性來源缺失而非管線落後，不因新增比賽而改善。 |
| `ML_FIELD_TZ1_FEASIBILITY.md` | 維持 | 40 | 分類洩漏是資料生成機制的性質（成功記本位、失敗推別區），對全母體成立；三輪校準已自行修正過度悲觀與過度樂觀，且明確區分『可識別』與『估得準』。正面對照組。 |
| `TEAM-STYLE1_RESULTS.md` | 維持 | 17 | 守備效率軸判『不成立』時同句已寫明成因是『DER 在 4–6 隊、半季樣本下噪音壓過隊間差異』，且處置為保留軸、僅不單獨當標籤——已是準則 3 的正確處理。 |
| `TEAM-STYLE2_RESULTS.md` | 維持 | 7 | 決定性判準（ii）本身就是 CI 排除 0 的檢定，且 §5.1 已明寫『未能證立差異，不是證立無差異』——準則 3 要求的詞彙已具備。 |
| `UX-PLAYER-FIELDVIZ1_RESEARCH.md` | 維持 | 6 | 否決建立在事前檢定力計算（每區 12–21 球、整體 SE 3.7pp vs 聯盟離散度數 pp），且明言『會產出看起來有差、實際不可信的排名』——正是準則 3 要求的『測不了』表述。 |

## S* 機器 artifact（5 份）

| 檔案 | 裁決 | tier1 | 理由 |
|---|---|---:|---|
| `game_recap_wp_cal1_metrics.json` | 不適用（繼承 GAME-RECAP-WP-CAL1_RESULTS.md） | 1 | CAL1 的機器 artifact，判定繼承 parent。 |
| `game_recap_wp_strength1_metrics.json` | 不適用（繼承 GAME-RECAP-WP-STRENGTH1_RESULTS.md） | 2 | STRENGTH1 的機器 artifact，判定繼承 parent。 |
| `game_recap_wp_val1_fix1_metrics.json` | 不適用（繼承 GAME-RECAP-WP-VAL1-FIX1_ERRATA.md） | 1 | FIX1 的機器 artifact，判定繼承 parent。 |
| `game_recap_wp_val1_metrics.json` | 不適用（繼承 GAME-RECAP-WP-VAL1_RESULTS.md） | 4 | VAL1 的機器 artifact，判定繼承 parent。註：E scope 為 pre-FIX1 版，已由 ML-WP-VAL-RESAMPLE1 §6-F1 列為範圍外發現。 |
| `team_style2_metrics.json` | 不適用（繼承 TEAM-STYLE2_RESULTS.md） | 1 | TEAM-STYLE2 的機器 artifact，判定繼承 parent。 |

## F 可行性／規則判定（20 份）

| 檔案 | 裁決 | tier1 | 理由 |
|---|---|---:|---|
| `DATA-RULES-AUDIT1_REPORT.md` | 維持 | 20 | 刷新收斂性的 ❌『永不收斂』是管線設計的確定性性質（只補整場缺、不補內容改判），與樣本無關。 |
| `DATA-TIE-REMEDY1/streak_impact.json` | 維持 | 3 | SKIP 語意被需求方二次裁定否決，屬官方語意裁決，非統計判定；該檔已自標為反證存證。 |
| `DEV-CLI-HELP-GUARD1/cli-help-audit-before.md` | 維持 | 1 | 同上，執行前快照。 |
| `DEV-CLI-HELP-GUARD1/cli-help-audit.md` | 維持 | 1 | 查核指出的安全宣稱不成立（可繞過 ctypes／syscall），屬能力邊界事實。 |
| `DEV-CLI-HELP-GUARD2/cli-help-audit-before.md` | 維持 | 1 | 同 GUARD1，執行前快照。 |
| `DEV-CLI-HELP-GUARD2/cli-help-audit.md` | 維持 | 1 | 同 GUARD1。 |
| `DISCOVERY-CPBL-RECORDS1_RESULTS.md` | 維持 | 12 | 頁面級 NO-GO 的理由是與既有資料源重複／深度不足，屬確定性事實；報告本身已把預設 NO-GO 依實測翻掉一項（/stats/mvp），顯示判定非機械照抄。 |
| `FIELDING_METRIC_DIRECTION.md` | 維持 | 3 | 方向評估，非統計判定。UZR/DRS 的否決寫明『每人每區 12–21 球，樣本不足』；Phase 2 不執行是投資取捨。準則 1 不適用（結論不隨賽季新增翻面）。 |
| `GAME-RECAP-DATA1_RESULTS.md` | 維持 | 9 | canonical PA 的 NO-GO 立論是『三套現行近似分組邊界互不相同』，已由查核逐一回源程式碼行號重現；確定性判定，且後續 PA1 build 已據此建成。 |
| `GAME-RECAP-WP-STRENGTH1_RESEARCH.md` | 維持 | 8 | 外部文獻的證據強度限縮（『已驗證但不可外推』），是引用紀律而非本專案的統計判定；其保守方向與紅線一致。 |
| `INGEST-PLAYER-BIO-GAP1_DIAGNOSIS.md` | 維持 | 8 | 『不成立』指卡面對 canonical target 集合的假設被實查推翻，屬事實查證；並明文禁止重判 ML-WP-BIO-PRIOR1 的 Go/No-Go。 |
| `INGEST-SPLITS-IBB-GHOST1_RESULTS.md` | 維持 | 6 | 方案 A 不建議單獨採用的理由是規則語意涵蓋不全，非門檻未過。 |
| `LIVE_GAME_BACKEND1_OBSERVATION.md` | 維持 | 1 | 『stats 不支援已驗證的賽前預告先發來源』是端點內容的存在性判定，且處置為 fail closed（不由 RoleType 倒推），保守方向正確。 |
| `ML-PITCHER-SCORELESS1_RESULTS.md` | 維持 | 10 | 七輪失敗模式皆為規則推導與窮舉的結果，不涉抽樣；『以列的缺席為證據』不可證是邏輯前提問題。 |
| `ML-PITCHER-SCORELESS2_RESULTS.md` | 維持 | 9 | 撤回第二條下界是窮舉證明（53,988 組嚴格增益全落在反例適用區，零例外），不是統計判定；其他救法的 No-Go 同屬規則層。 |
| `OFFICIAL_DATA_GAP1_RESULTS.md` | 維持 | 3 | 端點 NO-GO 的理由是與 games.mvp_acnt 等既有欄位重複，確定性。 |
| `OPS-BACKUP-EMPTY1_RESULTS.md` | 維持 | 13 | 維運事故的根因分析（空 dump、convalidated=t 卻不成立的 FK），全部可逐項復現，非抽樣推論。 |
| `OPS-CODE-BRANCH-PROTECT1_PLAN.md` | 維持 | 18 | ruleset 選項的 ❌ 排除全部有 GitHub 行為實測佐證（如 required_signatures 對近 5 個 commit 實測 verified:false），確定性。 |
| `OPS-STATE-PLANE-MIG1_field_mapping.md` | 維持 | 3 | 欄位型別取捨與 gh CLI 能力限制，屬工具事實。 |
| `UX-ABILITY-FIELD1_PHASE1.md` | 維持 | 1 | 方案 C 放棄的理由是確定性副作用（9 名真實守備者被錯標指打）＋無收斂效果，不是統計檢定失敗。 |

## N 非否定判定（27 份）

| 檔案 | 裁決 | tier1 | 理由 |
|---|---|---:|---|
| `DATA-RULES-AUDIT1/C10_bunt_and_dp.json` | 不適用 | 52 | tier1 命中全為官方動作名欄位值『三振/第三好球觸擊失敗』，非判定。 |
| `DATA-RULES-AUDIT1/C11_convergence_matrix.json` | 不適用 | 1 | tier1 命中為爬取錯誤訊息（ERR_INTERNET_DISCONNECTED），非判定。 |
| `DATA-RULES-AUDIT1/C9_special_rulings.json` | 不適用 | 1 | 同上，欄位值。 |
| `DATA-TIE-REMEDY1/consumers.json` | 不適用 | 2 | 引用 VAL1 的 unsupported 結論，非自身判定。 |
| `DOC-GAME-RECAP1_REVIEW.md` | 不適用 | 4 | 查核報告，tier1 命中為對 spec fail-closed 條款的 PASS 敘述。 |
| `GAME-RECAP-DATA1_REVIEW.md` | 不適用 | 6 | 查核報告，逐項確認 GAME-RECAP-DATA1 的 NO-GO 立論回源無誤。 |
| `GAME-RECAP-PA1-BUILD1_HANDOFF.md` | 不適用 | 2 | 命中為『0 失敗』等執行統計，非判定。 |
| `GAME-RECAP-PA1-BUILD1_QA.md` | 不適用 | 1 | 同上。 |
| `GAME-RECAP-PA1-FIX1_PROD_RUNBOOK.md` | 不適用 | 2 | 生產操作手冊，命中為操作建議與封存流程用語。 |
| `GAME-RECAP-PA1-TAXONOMY1_RESULTS.md` | 不適用 | 1 | 命中為 taxonomy 表的動作名欄位值。 |
| `GAME-RECAP-PA1_REVIEW.md` | 不適用 | 5 | 查核報告，命中為 NO-GO 前提回源敘述。 |
| `GAME-RECAP-STATUS-EXPAND1_REVIEW.md` | 不適用 | 4 | 查核報告，命中全為 PASS 列與既有 baseline failure 註記。 |
| `GAME-RECAP-STATUS1_RESULTS.md` | 不適用 | 1 | 命中為『失敗取得留下 source error』的驗收敘述。 |
| `GAME-RECAP-STATUS1_REVIEW.md` | 不適用 | 2 | 查核報告，命中為失敗處理路徑的 PASS 敘述。 |
| `GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW.md` | 不適用 | 2 | 規劃階段查核，無研究判定。 |
| `GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW_REQUEST.md` | 不適用 | 7 | 查核請求書，命中為對查核者的提問清單。 |
| `INGEST-SPLITS-IBB-GHOST1_IMPACT.json` | 不適用 | 0 | 結構化掃描命中 has_result_row=False 布林欄，非判定欄。 |
| `INIT-GAME-RECAP/spike-report.md` | 不適用 | 2 | spike 紀錄，命中為 fail-closed 設計敘述與缺口盤點。 |
| `INIT-GAME-RECAP_DISCOVERY-BRIEF.md` | 不適用 | 2 | discovery brief，命中為待驗證假設的『不成立時退路』描述。 |
| `ML-WP-BIO-PRIOR1_MEMO.md` | 不適用 | 1 | 本卡判定為 Go（三判準同時成立），非否定判定；命中為引用 STRENGTH1 的 No-Go 根因。 |
| `ML-WP-BIO-PRIOR1_SPEC.md` | 不適用 | 1 | 預註冊協定，命中為判準定義文字，尚無結果。 |
| `ML_FIELD_TZ1_REVIEW.md` | 不適用 | 12 | 跨家族查核報告（iteration 1），推動執行者收斂結論。 |
| `ML_FIELD_TZ1_REVIEW_IT2.md` | 不適用 | 8 | 同上（iteration 2）。 |
| `ML_FIELD_TZ1_REVIEW_IT3.md` | 不適用 | 10 | 同上（iteration 3）。 |
| `OPS-REMOTE-CRAWL1_PLAN.md` | 不適用 | 3 | 規劃書，GO/NO-GO 尚未做出（『待證據矩陣完成後決定』），無判定可重審。 |
| `WORKFLOW-REVIEW-2026-08-04.md` | 不適用 | 10 | 工作流總檢討，命中為卡片封存決定，非研究判定。 |
| `game_recap_pa1_fix1_metrics.json` | 不適用 | 3 | 命中為動作名欄位值『三振/第三好球觸擊失敗』。 |

