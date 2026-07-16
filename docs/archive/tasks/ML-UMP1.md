# ML-UMP1 好球帶判決差異研究〔🔴統計／反事實估計〕

- 需求：ruan6047（07-14）　規劃：GPT-5@Codex（[`approved spec`](../../../umpire-impact-research.md)）
- 執行：GPT-5@Codex　查核：Fable-5@Claude Code（獨立重建 artifacts＋實測，含退回修正一輪）
- 分支：`ai/gpt-5-codex/ML-UMP1`（已合併、已清理）　Merge SHA：`5f9077e`（reviewed branch tip：`7585604`）
- DB：`db_scope: read`；未新增表／migration
- 部署：否（離線研究，僅 git-ignored artifacts 與 [`results`](../../research/ML-UMP1_RESULTS.md)）

## 結論（複查通過後不變）

| 層級 | 結論 |
|---|---|
| count-aware run-value 引擎 | GO（研究元件；NLL 小勝且 CI 略跨 0，僅作後續基礎） |
| count-aware WP | NO-SHIP（Brier／LogLoss bootstrap CI 皆跨 0；`wp_*` 維持 null） |
| 固定代理帶方向性主審／球隊產品 | NO-GO（18/18 主審、6/6 球隊 zone-sensitive；coverage 82.5% 且場地缺口非隨機） |
| API／UI／production table | 不得進入（產品化須另卡授權） |

state value 是聯盟平均狀態價值差，不是實際得失分、因果效果或「裁判送分」。後續：[ML-UMP2](../../tasks/ML-UMP2.md)（身高比例逐打者代理帶重跑敏感度）。

## 範圍／驗收（定案版）

固定垂直帶因缺逐打者 `sz_top/sz_bot` 不是規則真值，canonical 名稱採「好球帶判決差異」，技術欄位保留 proxy 語意。建立 count-aware 壘況／出局／球數狀態價值（RE24 不能替 called ball/strike 定價）；2018–2024 建模調參、2025 untouched test、2018–2025 final refit 評分 2026 TrackMan called 球；按攻守隊與主審做帶 coverage、game-cluster 95% interval、zone／venue／home-away／月份 sensitivity 的描述性聚合。run value 必勝 count-agnostic baseline；WP 未勝現有 `wp_state()` 即不產出。

## Log

- 07-14 自 UX-10 拆出：反事實估計不宜與一般 UI 同卡；跨家族或人審查核。
- 07-15 GPT-5@Codex 唯讀稽核：2026 A called pitches 24,270、99.69% 唯一連結、99.82% 合法 pre-call 球數；spec 糾正兩前提（固定帶非真值、RE24 不含球數）。
- 07-15 ruan6047 核可 spec 四項決策；R0–R3 執行完成：24,192 顆可評分、2025 run-value gate 通過、WP gate 未過 no-ship、2,661 proxy disagreements、18/18 主審 zone-sensitive → 固定帶方向性產品 no-go。
- 07-16 Fable 獨立查核：detached worktree 重建全部 artifacts，統計核心與數字精確重現；退回 P2-1（球隊缺 bootstrap interval）、P2-2（預先註冊 baseline／敏感度缺項：WP sanity、edge-distance baseline、home-away／月份、50cm filter 對照）。
- 07-16 GPT-5@Codex 修正 P2-1／P2-2（球隊與主審共用同一 replicate；四項分析補齊）；pytest 170 passed。
- 07-16 Fable 複查 PASS：P2 清零、回歸零退化（audit 五數字、兩 gate、守恆恆等式逐位不變；sanity baseline p(home)=0.536943 精確吻合；50cm 契約與既有 SQL 等價僅排除 1 顆）。轉 ✅ 並 merge main（衝突僅 TASKS.md 格式重構，依 WF12 新格式整併）。
- 07-16 實際 merge commit 對帳為 `5f9077e`；本卡為離線研究、不需部署，補 release event 後轉 🏁完成並封存。
