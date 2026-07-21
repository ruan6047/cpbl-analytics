# UX-PLAYER-SCOPE1 球員頁本季／生涯全域範圍重整 Design Brief

> 狀態：**需求方已核可方向（2026-07-22）**
> 規劃：GPT-5@Codex　基線：UX-PLAYER-IA2＋UX-MATCHUP2（main `bc15ba1`）

## 0. Discovery 與問題證據

需求方走查球員頁後指出「本季／生涯」版面管理混亂。2026-07-22 以王威晨球員頁在
1440px／390px 真實瀏覽器複驗，確認目前有三組同名、不同作用域的控制：

1. Hero 的「本季／生涯」只切能力雷達。
2. 主導覽的「生涯」只切下方分層內容。
3. 分項明細內另有「本季／生涯」局部切換。

即使 URL 為 `?sec=career`，頁面仍先渲染完整本季成績、官方 PR、選手特性與賽季走勢；
手機需跨越多個畫面才到達生涯內容。根因是資料範圍（scope）、球員身分（role）與內容類型
（view）混在同一層，且本季總覽被設為常駐。

## 1. 核可的設計原則

### 1.1 唯一全域範圍

- Hero 下方只保留一組 `本季｜生涯`，作為整頁唯一 scope 來源。
- scope 寫入 URL，控制 Hero headline、Hero 能力雷達、內容導覽、資料載入與所有下方模組。
- Hero 不再保有自己的局部 scope state；分項明細也不再重複 scope 切換。
- 現役球員預設本季；退役／教練預設生涯。

### 1.2 Hero 能力雷達保留

- 能力雷達是「快速認識選手」的核心，維持在 Hero。
- 點選 Hero 下方的全域 scope 後，雷達同步切為「2026 本季能力」或「生涯能力」。
- 切換應立即回饋且不重掛整個 Hero；雷達需有明確 scope 標籤，避免使用者只靠下方控制猜測。

### 1.3 既有圖表保留

既有圖表效果均為產品資產，重整只改安置與顯示順序，不改視覺語言、統計口徑或互動：

| scope／view | 保留內容 |
|---|---|
| 本季／總覽 | 官方 PR、選手特性、賽季走勢 |
| 本季／逐球追蹤 | 擊球落點、進壘點、揮棒紀律、好球帶熱區 |
| 本季／逐球追蹤 | 擊球品質摘要、彈道分布、拉打方向、強擊／Barrel |
| 本季投球／逐球追蹤 | 配球傾向、球種位移、出手點、球種品質 |
| 本季／分項對戰 | 對戰各隊圖表、分項明細、投打對決 |
| 生涯／總覽 | 生涯核心成績、史上排名、里程碑、最佳單季、生涯趨勢 |
| 生涯／逐年／進階價值 | 生涯逐年與既有 SABR 指標 |
| 本季／生涯守備 | 既有守備身分圖、價值卡與表格 |

唯一移除的是「擊球品質分布（仰角 × 初速）」`LaEvScatter`；同步清除 import、孤兒元件（確認無其他
consumer 後）與頁尾紅框說明。

## 2. 資訊架構

```text
Hero（身分、headline、能力雷達；內容隨 scope 同步）
└─ 全域範圍：本季｜生涯
   ├─ 身分：打擊｜投球（僅雙棲顯示；URL 可分享）
   ├─ 層級：一軍｜二軍（僅本季且有二軍語意時顯示）
   └─ 內容 view
      ├─ 本季：總覽｜逐球追蹤｜分項對戰｜守備
      └─ 生涯：總覽｜逐年成績｜分項對戰｜守備｜進階價值
```

- scope、role、view、level 是不同軸，不得再混為同一列標籤。
- 雙棲球員不再把兩種身分的長內容上下堆疊；改為可見、可鍵盤操作且寫入 URL 的 role 控制。
- 單一身分不顯示 role 控制；不存在的 view 顯示誠實空態，不以錯誤 scope 的資料補位。
- 本季完整傳統計數可收進 progressive disclosure，但資料不得刪除。

## 3. URL 與相容

目標狀態：

```text
?scope=season&view=overview&role=batting&level=A
?scope=career&view=yearly&role=pitching
```

舊 `?sec=batting|pitching|splits|fielding|career|approach` 與 `?role=` 必須有 deterministic migration map；
既有分享連結不可 404、不可空白。瀏覽器返回／前進、重整與 deep-link 必須維持相同畫面。

## 4. 狀態與可及性

- 全域 scope 與 view 使用 WAI-ARIA tabs；鍵盤方向鍵、焦點跟隨與 active label 正確。
- mobile touch target 至少 44px；375px 不產生 body 水平溢出。
- loading 不造成大幅頁高回夾；scope 切換後 Hero 與下方不得短暫顯示不同範圍。
- 退役、二軍、無 tracking、無 career、雙棲其中一種身分無資料均須有帶原因空態。

## 5. 非目標

- 不改 API、SQL、能力值或任何棒球統計公式。
- 不重畫、替換或減少既有圖表；僅移除需求方指定的 `LaEvScatter`。
- 不改 MatchupExplorer 的 fail-closed／credibility／baseline 契約。
- 不新增 OAA、Stuff+、PA 模擬或尚未通過 Gate 的入口。

## 6. 衝突與序列化

| 卡片 | 判定 | 約束 |
|---|---|---|
| UX-MATCHUP2 | **硬資源衝突**；已合併 main，但仍持有 `web/src/app/players/[id]/` lease 等待批次部署 | 本卡可註冊 Backlog；claim 前必須等 UX-MATCHUP2 release／釋放 lease，且從包含 `bc15ba1` 的 main 建分支 |
| BUG-ABILITY-DH-LABEL | 無檔案衝突；能力 API 修正已合併 | 保留新 DH／資料不足語意，不重做能力算法 |
| MATCHUP-DATA2 | 無檔案衝突；API 彙總修正 | 球員頁只消費共用 MatchupExplorer，不複製隊別修正 |
| UX-PA-SIM-MATCHUP1 | 可平行但有共用元件風險 | 本卡不修改 `web/src/components/matchups/` 的統計／fail-closed 行為；若執行範圍擴張須重新序列化 |
| INGEST-DEEP-TRACKMAN1／INGEST-GAME-TM-REFACTOR1 | 無衝突；資料管線與 DB | 本卡不依賴新欄位，不改 tracking API contract |
| ML-FIELD-OAA-VAL1 | 無當期衝突；明列不做前端 | 未來 OAA UI 另開卡，不預留空殼 |

## 7. 驗收

- [ ] 整頁只出現一組具 scope 語意的「本季／生涯」，並同步驅動 Hero 雷達與下方內容。
- [ ] `scope=career` 首屏後不再先渲染本季成績、官方 PR、選手特性或賽季走勢。
- [ ] 除「擊球品質分布（仰角 × 初速）」外，現有圖表 inventory 全數保留且可到達。
- [ ] 打者、投手、雙棲、退役、二軍、tracking 缺漏六情境正確；雙棲 role 不靠上下長頁堆疊。
- [ ] UX-MATCHUP2 的投打對決、四態 fail-closed、deep-link 與 compact 行為零退化。
- [ ] 舊 URL migration、返回／前進、鍵盤與 375px 通過。
- [ ] `npm test`、`npx tsc --noEmit`、`npm run build:check` 通過；真實瀏覽器走查桌機與手機。
