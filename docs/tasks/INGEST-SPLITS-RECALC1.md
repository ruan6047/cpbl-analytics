# INGEST-SPLITS-RECALC1 修正分項重算的代打誤切重複計數並重建〔T4；🔴資料正確性〕

- 需求：ruan6047（2026-07-30 於 `INGEST-SPLITS-PA-SPLIT1` 結案後指示「開卡然後執行」）　規劃：本卡 spec　分支：`ai/fable-5/INGEST-SPLITS-RECALC1`
- 執行：Claude Fable 5@Claude Code　查核：待指派（≠ 執行；**跨模型家族或人工**——統計紅線＋DB 寫入）
- review_independence: [cross_family_or_human]
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1
- DB：`db_scope: data-migration`（無 schema 變更，`migration_phase: none`；資料重建走既有
  `cpbl-build-splits` DELETE+INSERT，冪等可重跑。resources：`db:local:table:batting_splits`
  ＋ `pitching_splits`＋career 兩表（經每日 build 間接）；production 於部署階段另列）
- 部署：**是**（碼進生產＋生產資料重建；見〈階段〉）　環境：local → production　PR：—　Merge SHA：—
- 範圍：修正 `splits_calc.py` 的島切分缺陷（`INGEST-SPLITS-PA-SPLIT1` 已定案量化），
  本機重建並以該卡 delta artifact 逐格對帳，通過查核後部署生產重建。

## 問題陳述（結論已定案，本卡不重新查證）

`INGEST-SPLITS-PA-SPLIT1`（🏁，merge `cc339f5`）證實：`splits_calc.flush()` 以
`(inning, vht, hitter)` 切島，把**打席中途代打**切成兩個 PA 重複計數。曝險
**83 筆／82 場**（2018–2026，baseline 窗 `game_date ≤ 2026-07-28`）；H1 打序位移污染
家族 10（82 組／1,291 筆後續 PA）；選手層級完整發布欄位 delta **2,435 rows／17,997 格／
314 人**已 artifact 化（`docs/research/ingest_splits_pa_split1_player_delta.json`），
經跨家族查核 APPROVE，**即本卡的預期 diff**。

## 口徑定案（沿用已查核的 corrected 語意；需求方可覆寫）

1. **合併判準**＝canonical `pa_build.build_islands`／`continues_same_plate_appearance`
   （`pa-build-1.3.0`，六輪查核定案）。**本卡引用不重新定義。**
2. **打席歸屬**＝規則 9.15(b)（`charged_hitter`）：代打者完成的三振（含不死三振）記
   被判第 2 好球者、其餘記代打者——與 canonical PA 表 `end_hitter_acnt` 語意一致。
   **`2018/A/116` 官方 box 偏離 9.15(b)（記代打 1240，幅度 1 PA）：本卡依規則不依官方**，
   偏離已留痕（PA-SPLIT1 RESULTS）；選 9.15(b) 的理由＝與 canonical PA 表一致、且預期
   diff（已查核）即以此口徑產生，改口徑等於作廢已查核的對帳基準。
3. **投球數**＝逐列依實際 `pitcher_acnt` 保留（不整島搬給末任投手）；打席結果責任維持
   末球錨定，唯一例外 9.16(h)(1)（特定球數接手四壞記前任；PA-SPLIT1 兩例跨投手皆不適用）。

## 階段

- **Phase L（本卡執行，查核前）**：修 `splits_calc.py` → 本機重建 2018–2026 A/D →
  對帳 artifact → 交跨家族查核。
- **Phase P（查核通過＋merge 後）**：部署碼至生產 → **先自建並驗證生產備份**
  （`OPS-BACKUP-EMPTY1` 未修，每日備份全空；FIX1 手動備份勿刪）→ 生產重建 → 對帳
  → `✅已驗證`。**未備份不得動生產資料**。

## 紅線（違反即退回）

1. **對帳零人工聲明**：重建前後 diff 必須由腳本產生 artifact，並**逐格對帳** PA-SPLIT1
   預期 delta——變動格 ⊆ 預期格且值相等、預期格全數命中、**非預期變動＝0**
   （as-of 位移除外，判讀依 PA-SPLIT1 卡面 as-of 原則：差異須全部可歸因於新增場次）。
2. **冪等**：重建可重跑，重跑後 diff 為零。
3. **單一 writer**：本機重建避開每日 10:10 refresh 窗；執行期間不得有其他 splits writer。
4. **復原方案先行**：重建前 dump 受影響兩表（本機 CSV/SQL 快照，路徑記入交付）；
   語意上任何時點可由「還原程式碼＋重跑 build」重導出舊值。
5. **不動 canonical PA 表**（`game_pa` 系列）；不動 `*_vs_team`（T1 gamelog 路徑，
   PA-SPLIT1 已證零影響——對帳須驗證其確實未變）。
6. **生涯表**：不直接改寫；2026 本季貢獻由每日 `build_career`（base＋本季）自動吸收，
   對帳須含一位受影響選手的生涯值變化驗證。

## 驗收條件

- [ ] `splits_calc.py` 合併邏輯改用 canonical 判準；`uv run ruff check`＋`uv run pytest` 全綠。
- [ ] 本機重建後對帳 artifact：預期 delta **17,997 格全數命中、非預期變動 0**
      （as-of 歸因除外）；83 案例逐筆 PA −1；22 筆三振歸原打者；兩例跨投手投球數
      逐投手守恆；`*_vs_team` 兩表逐格未變。
- [ ] 重建後 box 逐場交叉驗證翻轉：82 場逐人 PA 由「legacy 88 筆不吻合」變為
      「corrected 側 7 筆已知殘差」（PA-SPLIT1 口徑）。
- [ ] 冪等驗證：重建緊接重跑第二次，diff＝0。
- [ ] PA-SPLIT1 的驗證腳本定位處理：其 simulator／assembly 保真錨定**修正前**行為，
      修正後將如實失效——標注為歷史 artifact（不刪除、不納入例行），本卡對帳腳本取代其守衛職能。

## 驗證（查核者）

- [ ] 獨立重跑對帳腳本，確認預期 diff 全命中與非預期變動 0。
- [ ] 抽驗曝險案例（至少含 `2018/A/116`、`2025/A/84`、兩例跨投手）對 livelog／box。
- [ ] 挑戰合併邏輯與 canonical `pa_build` 的一致性（同判準不同實作路徑的殊途同歸驗證）。

## 邊界

- **不做**：schema 變更；canonical PA 表改動；`vs_team` 語意變更；官方 `/team/apart`
  歷年值爬取（驗收對照另開卡，PA-SPLIT1 RESULTS 留有恢復路徑）；H2 對帳歷史的補救。
- **不做（本卡 Phase L）**：任何生產寫入。
- Design Gate：`N/A`——資料正確性修正，無介面變更；前端顯示數值隨資料修正微動
  （83 個 PA 的量級），屬修正本身。

## Log

- 2026-07-30 依 ruan6047 指示開卡（「開卡然後執行」）。前置 `INGEST-SPLITS-PA-SPLIT1`
  已結案（merge `cc339f5`），預期 diff artifact 經 Codex APPROVE。grilling 未觸發之
  判斷：本卡 T4 但資料重建可由 livelog 重導出（可逆），非「不可逆 T4」；口徑三項
  皆沿用已查核定案，無新 Discovery 面。
