# BUG-HELD-GAME-FRESHNESS1 保留比賽誤算完賽並污染 freshness 〔T4；🔴資料正確性／production gate〕

- 重現：2026-07-18 本機 DB 查得 5 場 `kind_code='D'`、`delay_kind='保留'`、續賽日位於未來但保留中止比分；`home_score + away_score > 0` 使 `/api/info` 回報 `last_game_date=2026-09-15`。
- 預期 vs 實際：未完成保留賽不得算 completed／推高 freshness ／ 目前被計入 completed，且 local／production 會「錯得一致」而通過 sync gate。
- 根因：比分存在只是「已開賽」證據，不是「已完成」充分條件；`cpbl.games` 聚合同 sno 歷程時會保留中止比分與未來續賽日期，多個 consumer 仍複製舊判定。
- 修復：先證明 canonical completion predicate，再讓 `/api/info` 與 production sync gate 共用；其他 consumer 先盤點，不在缺乏資料語意證據時全面機械替換。
- 回歸測試：先以真實匿名化 snapshot 建紅測，至少涵蓋正常完賽、當日進行中、延賽、保留待續、保留續完與日期邊界。
- 需求：ruan6047　規劃：GPT-5@Codex　執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）　分支：`ai/<執行者>/BUG-HELD-GAME-FRESHNESS1`
- Initiative：INIT-PRODUCT-UX　spec／計畫：[`../../held-game-freshness-fix.md`](../../held-game-freshness-fix.md)
- DB：`db_scope: read`（調查／測試）；production dry-run 另取 `db:production:cpbl` lock 且先備份
- 部署：是　環境：local＋production　Design Gate：N/A；純技術資料正確性修復，不改使用者流程
- 依賴：與 `GAME-RECAP-STATUS1` 對齊 canonical status；本卡可先修 freshness 紅線，但不得自行擴張到全部 ML／歷史統計 consumer。
- owner、worktree、iteration、最後交接、阻塞與 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 驗收

- [ ] 舊版本上的紅測可重現 5 場未完成保留賽使日期跳到未來，修正後轉綠。
- [ ] `/api/info.metrics.last_game_date` 與 `season_games_completed` 排除未完成保留賽；續完後正確納入。
- [ ] `refresh-cpbl-prod.sh` 不再另寫一份語意不同的 completed SQL，local／production 對帳使用同一 contract。
- [ ] consumer inventory 列出 API、ingest、features／ML 的每個舊判定與「本卡修／STATUS1 後修／不受影響」結論。
- [ ] T4 reviewer 實測 fixture、真實 DB read-only 對帳、production dry-run、失敗傳遞與 freshness gate。

## Log

- 2026-07-18 註冊：OPS-REFRESH1 release 後真實驗收揭露 5 場二軍保留賽帶比分但續賽日在未來；同步成功不等於 completed 語意正確，另卡處理。
