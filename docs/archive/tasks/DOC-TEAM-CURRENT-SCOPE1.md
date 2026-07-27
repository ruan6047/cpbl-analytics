# DOC-TEAM-CURRENT-SCOPE1 team_current 半季口徑補進事實來源〔T1；文件〕

- 需求：TEAM-STYLE1 iteration 1 查核 Minor finding（2026-07-27）　規劃：本卡即 spec　分支：依認領時慣例
- 執行：待指派　查核：待指派（≠ 執行；T1 輕量）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- current-state：📥Backlog。

## 背景（為什麼）

TEAM-STYLE1 的預註冊 QA 以「2026 全季聚合 vs `cpbl.team_current`」為口徑交叉驗證，
結果**全數 FAIL**（max|Δ| 0.083）；事後診斷證明 `team_current` 是官網**當前半季**口徑
（隊伍成績頁預設範圍）——以 `game_season_code='2'` 聚合後 5/6 隊三圍與官方逐位吻合
（樂天殘差 0.0024 研判快照時點差）。證據見
[`../research/TEAM-STYLE1_RESULTS.md`](../research/TEAM-STYLE1_RESULTS.md) §4。

這個口徑事實目前只存在於該研究報告與 archived task，`AI_RUNBOOK.md` 與
`docs/reference/GLOSSARY.md` 皆無記載——下一個研究者仍會把 `team_current` 當全年資料。

## 範圍

- `docs/reference/GLOSSARY.md`：`team_current` 條目補「當前半季口徑」語意與證據連結。
- `docs/AI_RUNBOOK.md`：current 系列表的陷阱清單補一行。
- 順帶核對 `pitching_current`／`batting_current` 是否同口徑（同頁面家族，很可能同樣是
  半季）——**只查證與記載，不改任何程式**；若無法確認就寫「未查證，勿假設」。

## 驗收條件

- [ ] 兩份文件更新，含證據連結；`current` 系列三表的口徑各自明寫（已證實／未查證）。
- [ ] `uv run pytest`（文件測試）通過。

## Log

- 2026-07-27 依 TEAM-STYLE1 iteration 1 查核 Minor finding 開卡。
