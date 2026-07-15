# ML-UMP2 身高比例逐打者代理帶敏感度重跑〔🔴統計／反事實估計〕

- 需求：ruan6047（07-16）　規劃：待 spec 增補（沿用 [`umpire-impact-research.md`](../../umpire-impact-research.md)；建議 Fable）
- 執行：待指派　查核：待指派（跨家族模型或人審＋實測）
- 分支：`ai/<執行者>/ML-UMP2`　worktree：依 §3.1 另開
- DB：`db_scope: read`；不新增表／migration
- 部署：否（離線研究，僅 ignored artifacts＋報告增補）
- 依賴：[ML-UMP1](ML-UMP1.md)（已合併）——引擎、連結管線、敏感度框架全部複用，只換帶定義。

## 動機

ML-UMP1 固定代理帶 no-go 的根因之一是「帶為單一人為框」：對稱縮放 ±1–5cm 使 18/18 主審、6/6 球隊方向翻轉。逐打者身高比例帶讓垂直邊界隨打者變動，可驗證翻轉是否因此消失。Prior art：`yuetsu001.github.io/cpbl-umpire-scorecard`（實測反推其公式為 sz_top=0.535×身高、sz_bot=0.270×身高，資料源同為官方 TrackMan；其 RE 表非 CPBL fit 且無不確定性揭露，僅參考呈現形式，數字語意不採）。

## 範圍

1. 新 zone_definition `height_scaled_proxy_v2`：`sz_top=0.535×身高`、`sz_bot=0.270×身高`（讀 `players` 身高），水平沿用現契約。**仍是代理**（規則＝揮擊準備姿態，非站立身高比例），不得稱規則真值。
2. 資料前置 audit（fail-closed）：2026 called-pitch 全部打者的身高覆蓋率；缺身高列 exclusion waterfall，不得默默 fallback 到固定帶。
3. 以 v2 帶重跑 ML-UMP1 scoring 與全部敏感度（zone ±1/2/3/5cm、venue、home/away、月份、50cm 對照），與 `fixed_zone_proxy_v1` 全表對照。
4. 可選 scenario：球緣語意（球半徑 buffer，帶邊碰球緣即 strike）只作敏感度對照，不改主契約。

## 驗收

- 核心問題只有一個：**18 主審／6 隊的方向翻轉在 v2 帶下是否消失**。
- 若仍普遍翻轉 → 方向性產品維持 no-go，結論寫入報告即收卡。
- 若不再翻轉 → 「本場／本季判決差異偏向 X 隊」這類**方向性（不含分數）敘述**才取得可辯護基礎（07-16 ruan6047 詢問「只提方向不提分數」的前置條件即此）；但呈現仍須附區間與敏感度、仍稱「判決差異」非「誤判」、進 API/UI 仍須另卡授權。
- 沿用 ML-UMP1 全部紅線：不稱實際得失分／因果效果／裁判送分；bootstrap 以 game 為 cluster；描述性聚合不做精確排行。

## Log

- 07-16 自 ML-UMP1 查核結論＋外部 scorecard 專案逆向分析開卡；`players` 身高欄現成，成本主要在覆蓋 audit 與重跑。
