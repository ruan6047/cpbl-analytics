# 工作流檢討決議紀錄（2026-08-04）

> **形式**：grilling 對抗式質詢（需求方 ruan6047 × Claude Fable 5@Claude Code，共 11 題逐題定案）。
> **地位**：需求方已確認共識成立。本檔是「工作流遷移 Initiative」與「ai-workflow 產品化 Initiative」的 Discovery 證據；canonical 升版（WF-22）於 ai-workflow repo 執行。
> **注意**：本檔只記決議，**未實施**。實施前現行 canonical／CONTROL_PLANE_CONTRACT 仍有效。

## 1. 檢討緣起（需求方原始八項問題，重新編號）

1. 研究討論規劃階段太省略，卡片規劃不完整，花大量算力後才發現前提一開始就錯。
2. grilling 幾乎沒執行，沒有與人充分討論。
3. 流程缺失導致工作區找不到、規劃卡片沒同步，無法執行。
4. 每張卡未先確認核心痛點；修了很多問題但重點沒處理，反而開出與原目的衝突的新卡。
5. 文件因 git 關係造成錯誤評估；是否把任務管理變成獨立專案＋圖形化介面，讓撞卡偵測更可靠。
6. 任務套娃：每張卡開自己的前置任務（例：bio 資料缺失生出多張卡）。
7. 核心資源管理沒做好，多卡同時改相同資源導致數據跑掉。
8. 精簡流程：配卡、指派、追加卡片、資源調度由核心 PM 專責，他人不得代勞；session 間僅得就相關工作溝通。

## 2. 查證的證據基礎

- **工作區失靈實證**：本次檢討所在 worktree 的 `.ai-workflow` submodule 未初始化（canonical 規則讀不到）；Ledger 上 `DEV-CI-SCORELESS-DB-SKIP1` 與 `OPS-CONTROL-PLANE-PR-GUARD1` 兩卡共用同一 worktree（違反一卡一 worktree）；harness 自產分支名（`claude/…-33882b`）在 `ai/<執行者>/<卡>` 命名慣例之外。
- **前提錯誤實證**：`INGEST-SPLITS-IMPORT-RESTATE1` rev1 綁錯前置欄位（`country`，實為 `throws`）；`INGEST-PLAYER-BIO-GAP1` 診斷 §6 被證偽；2026-07-31 Review Gate 規劃建立在過期 main 基準（見記憶 plan-against-fresh-origin-main）。
- **套娃兩物種實證**：
  - 物種一（授權切碎）：bio 缺失一根問題生 4 卡（`ML-WP-BIO-PRIOR1`→`GAP1`→`GAP2`→`RESTATE1`）；根源是 GAP1 已抓到全部欄位卻只授權寫 2 欄。
  - 物種二（深度下鑽）：`DEV-EVENT-SCHEMA-GUARD1`→`DEV-EVENT-REPAIR-ANCHOR1`→`OPS-CONTROL-PLANE-PR-GUARD1`→`DEV-CI-SCORELESS-DB-SKIP1`→`DEV-TRAILER-GUARD-PR-CHECKOUT1` 五節鏈，全為流程機械卡，零產品價值，原始目標至今阻塞；其中 CI 紅燈屬全域環境債卻混入鏈中繼承急迫性。
- **流程自增生**：39 張活卡中 9 張（23%）為 DEV-*/OPS-*/DOC-* 流程機械卡。
- **規則存在但無比對點**：canonical §4.1 已強制資源宣告互斥、卡面已有 `db_scope`，但 claim 為 AI 自助式，無中央交集檢查。
- **法理集權、實務失守**：canonical「AI 不可自行派工」、contract「`ruan6047` 唯一 lifecycle writer」皆已明文，但 AI session 代行開卡／寫事件成常態。失守機制：決策與機械寫入綁在同一包，人迴避苦工時決策權隨之外流。

## 3. 三根因

1. **治理權實務分散**（問題 6、8，7 的一半）：法理集權但決策與寫入未拆離。
2. **思考前置不足、儀式後置過重**（問題 1、2、4）：對人的對齊（grilling）與對事實的驗證（前提實查）是兩種病、兩種藥。
3. **git 被當任務資料庫**（問題 3、5，7 的一半）：worktree 讀到過期狀態快照、事件寫入儀式繁重、看板缺席。

## 4. 決議（10 項）

1. **治理（PM 模型）**：決策（開卡、配卡、追加前置、資源調度、結案）100% 需求方本人；機械寫入（事件、狀態轉換、worktree 建立、結案清理）由唯一「PM 祕書」session 代行；其他 session 禁碰 control plane。需求方不在場時決策進佇列，AI 只能續做已派工作。
2. **卡範圍單位**：一根問題一張卡；卡內可列多個窄寫入授權（保留防呆、消除授權切碎型套娃）。執行者遇缺口→停→寫「阻塞發現」進決策佇列。開新卡僅限三情形：不同能力域執行者、紅線隔離（schema／data-migration）、可真平行。
3. **資源互斥執行層**：祕書派工時機械比對「本卡寫入集 × 現役卡寫入集」交集，撞則排隊；破壞性重建類 CLI（build／rebuild／migration）啟動時驗 lease，無 lease 拒跑。不做全面 namespace 隔離。
4. **規劃閘門三級制**：
   - Initiative／T4／不可逆：**同步 grilling 真對話**（brief 是對話殘渣，不是替代品）。
   - T3：**核心痛點三問**非同步輕質詢（痛點是什麼／成功怎麼觀察／最大未驗證前提是什麼），需求方批註放行才進 Backlog。
   - 所有 T2+：spec **前提清單逐條附實查證據**（SQL 結果、code 讀取、fresh origin/main SHA）；未驗證前提必須標示，且不得設為硬前置。
   - 祕書機械把關欄位齊備；需求方把關內容。
5. **鏈式停損**：每卡必填「服務的原始目標」。新前置先分流：**全域問題一律脫鏈獨立運行**（不入鏈、不繼承鏈的急迫性、不計鏈深，優先序全局裁定；鏈上只記等待條件）；鏈私有前置觸發停損裁決（固定問題：以原始目標的價值，這條鏈還值得加深嗎？有無降級繞道？）。**鏈深硬上限＝原始目標之下 2 層**；超過強制整鏈重審，預設答案是擱置或降級，不是繼續鑽。
6. **查核判準升級**：查核報告第一行必答「核心痛點是否已消失＋證據」，**具否決權**；驗收清單全過但痛點未消→REQUEST_CHANGES 並退回修 spec（清單與痛點脫節即 spec 缺陷）。
7. **狀態面遷 GitHub Issues + Projects**：卡狀態＝Issue、看板＝Projects（user-level Project 跨 repo 聚合＝多專案面板 v0）、事件＝timeline＋結構化 comment（祕書驗證）；規格文件與程式碼留 git；祕書每日快照 export 回 git 供離線稽核。GitHub 不可用時狀態操作暫停（沿現行退化模式）。
8. **worktree 註冊制**：放棄命名慣例、順應 harness——認領時祕書把「實際路徑＋分支」寫進卡；一卡一 worktree 靠註冊查重。`doctor` 對帳指令（派工前必跑）：孤兒 worktree、死路徑、submodule 未初始化、殘留 lease 一次列出；結案清理由祕書批次做。
9. **產品化時序**：ai-workflow 轉獨立產品（治理規則＋管理面板、多專案）的野心，立 **Initiative 占位卡**（💡需求階段）；**60 天 Issues dogfood 明定為其 Discovery 階段**（產出：驗證過的穩定規則集、快照資料 schema、祕書 CLI＝引擎原型、面板需求清單）；期滿帶證據過**商業評估 grilling**（目標客群、競品、定價）才動工。60 天後同時複評「自建內部系統」與否。
10. **在途流程卡處置**：即日凍結（不得新認領）；例外二張——`DEV-CI-SCORELESS-DB-SKIP1` 完成查核並合併（已完工且 CI 紅燈每日在痛）、`DEV-TRAILER-GUARD-PR-CHECKOUT1` 保留待排（程式碼走 PR 就會咬）。其餘逐張由需求方於遷移規劃時批示，建議見 §6。

## 5. 隨附三小項（已一併採納）

- **溝通限制**：session 間僅得就直接相關工作溝通（審核者↔執行者、前後端接口）；跨卡協調一律經需求方／祕書。
- **60 天回顧指標**（以過去 30 天回填基線）：前提翻案數（規劃後被推翻的前提）、每根問題卡數（套娃度）、結案債峰值、需求方每週裁決時間、狀態面錯誤評估事件數。
- **落地路徑**：canonical 升版（WF-22）在 ai-workflow repo；遷移 Initiative 主卡亦立於 ai-workflow repo（見決議 11），由需求方依新治理親自開卡（AI 不代開）。

### 決議 11：多專案適用（需求方 2026-08-04 補充裁定）

本套規則屬 **canonical 層、適用所有專案**（cpbl-analytics、PersonalWebsite 及未來專案），不是 cpbl 專屬：

- **規則與祕書 CLI 住 ai-workflow repo**（跨專案共用資產）；專案層只留 stub 與契約填空（哪些 CLI 是破壞性、哪些 DB 表要宣告等），不複製規則、不各自造工具。
- **單一祕書跨專案服務**：一個 PM 祕書 session 以 repo 為 namespace 操作各專案的 Issues；決策佇列全局唯一（你是一個人，佇列就是一條）。
- **看板單一入口**：user-level GitHub Project 跨 repo 聚合即多專案面板 v0，亦即產品化 Initiative 面板需求的活原型。
- **遷移 Initiative 主卡立在 ai-workflow repo**，各專案掛各自的採用卡；**cpbl-analytics 為首個試點**（卡最多、痛最深），驗證後 PersonalWebsite 跟進。

## 6. 在途流程機械卡逐張處置建議

| 卡 | 建議 | 理由 |
|---|---|---|
| `DEV-CI-SCORELESS-DB-SKIP1` | **完成查核→合併**（例外） | 已完工在審；CI 紅是全域債 |
| `DEV-TRAILER-GUARD-PR-CHECKOUT1` | **保留待排**（例外） | synthetic merge 假陽性咬所有程式碼 PR |
| `DEV-EVENT-REPAIR-ANCHOR1` | 🛑封存 | events.jsonl 退役後無物可偽；單寫入者威脅模型縮水 |
| `OPS-CONTROL-PLANE-PR-GUARD1` | 🛑封存原 scope | control-plane 不在 git；若要程式碼 main 的 branch protection＋required checks，重切窄卡入遷移 Initiative |
| `DEV-REVIEW-DEACCEPT-TRAIL1` | 🛑封存 | 概念（翻案留痕）併入審核契約的 Issues 移植 spec |
| `DEV-REVIEW-PREFLIGHT-GATE1` | 🛑封存 | preflight 改為祕書派審前 CLI 檢查 |
| `DEV-REVIEW-PREFLIGHT-SELFCHECK1` | 🛑封存 | 同上，併入祕書職責 |
| `DEV-CI-RED-OWNERSHIP1` | 🛑封存 | 紅燈歸屬即祕書 doctor 職責 |
| `DOC-CARD-SPEC-RULES1` | 內容併入 WF-22 卡面範本後封存 | 三規則仍有價值，載體隨 canonical 改版 |
| `DEV-VERIFY-TM-ASSERTS1` | 照舊 | 非流程卡（資料驗證），不受影響 |

## 7. 落地波次（建議）

- **Wave 0（即刻）**：凍結流程卡；DB-SKIP1 收尾；TRAILER 卡待排。
- **Wave 1**：祕書 CLI 最小集（開卡／派工／交接／doctor／快照）＋ Issues／Projects 建置＋ 39 張活卡遷移＋逐卡處置批示。
- **Wave 2**：canonical WF-22 改版（三級制、停損、註冊制、溝通限制、吸收卡面三規則）；各專案 stub 更新。
- **Wave 3（60 天）**：指標回顧 → 自建複評＋產品化商業評估 grilling。

## 8. 質詢軌跡

| # | 決策點 | 裁決 |
|---|---|---|
| 1 | 根因框架與討論順序 | 三根因成立；治理→規劃閘門→狀態面 |
| 2 | PM 身分模型 | 人決策＋AI 祕書寫入 |
| 3 | 套娃堵法（物種一） | 一根問題一張卡 |
| 4 | 資源互斥層級 | 派工互斥＋命令護欄 |
| 5 | 規劃閘門深度 | 三級制 |
| 6 | 鏈式停損（物種二） | 分流＋停損＋硬上限 2 層；全域問題脫鏈獨立運行（需求方補充裁定） |
| 7 | 查核第一判準 | 痛點證據具否決權 |
| 8 | 狀態面落點 | GitHub Issues／Projects |
| 9 | worktree 制度 | 註冊制 |
| 10 | 自建成本複覈 | Issues＋60 天後複評自建 |
| 11 | 產品化時序 | 立 Initiative，60 天試行＝Discovery |
| 12 | 在途卡處置 | 凍結＋逐張裁決，二張例外 |
| 13 | 多專案適用 | 規則與祕書 CLI 住 canonical 層；單一祕書、單一佇列跨專案；cpbl 為首個試點（需求方補充裁定） |
