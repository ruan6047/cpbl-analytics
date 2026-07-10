# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UX-1 | 全站頁面 UI/UX 重新設計 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 🚦spec待核可 |

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。

---

## 進行中／待辦卡

### UX-1 全站頁面 UI/UX 重新設計  〔⚪（大卡：規劃後預期拆多張子卡，涉全站視覺）〕
- 需求：ruan6047（07-11）——**重新設計每個頁面的 UI/UX**。動機／範圍邊界／成功標準待需求方補充或派工進規劃時釐清（本卡僅 problem statement，不含做法）。
- 規劃：Fable-5@Claude Code → spec 見 [`UX_REDESIGN_SPEC.md`](UX_REDESIGN_SPEC.md)（八原則＋UX-2〜9 拆卡＋深色模式決策點）
- 執行：待指派　查核：待指派（涉全站視覺，建議跨家族或人審驗收）
- 狀態：🚦spec 待 ruan6047 核可（核可後 UX-2〜9 開卡進 Ledger）　Commit：—
- 前置事實（規劃時必讀）：現行設計系統＝日間 Navy+白（memory `frontend-redesign`）；UI-2/3/4 剛完成運動風質感/微互動/響應式（`docs/archive/`）；UI-1 深色模式與 UI-5 對比頁在封存區可視需要復活併入
- Log：
  - 07-11 需求開卡 by ruan6047（Fable-5@Claude Code 代記）
  - 07-11 ruan6047 派規劃（原則先行、通用→個別、大→小）；規劃 by Fable-5@Claude Code 出 spec，🚦待核可

### 開卡格式（範本）

```markdown
### <卡ID> <功能名>  〔⚪一般 或 🔴紅線：原因〕
- 需求：<誰>　規劃：<誰>　分支：`ai/<模型或工具>/<卡ID>`
- 執行：<model@tool>　查核：<model@tool 或 人審>
- 狀態：🔨執行中　Commit：—
- Log：
  - MM-DD <事件>
```

---

## 歷史

已完成／封存卡片（UI-1〜UI-5、LIVE-1、工作流建立前補記）→ [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)
