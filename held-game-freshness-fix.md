# 保留比賽 freshness 修正

## Goal

讓「已完成」與 freshness 指標不再把帶有中止比分、排在未來續賽日的保留比賽算成完賽，同時避免未經驗證改寫 ML／歷史統計口徑。

## Tasks

- [ ] 固定 2026 二軍 5 場未來保留賽 snapshot，先讓 `/api/info` 與 sync freshness 測試在舊判定下失敗。→ Verify: fixture 可重現 `last_game_date=2026-09-15`、completed 多算 5 場。
- [ ] 以官網 `PresentStatus`／`GameResult`、`delay_kind`、日期與 gamelog 完整性證明 canonical completion predicate。→ Verify: 完賽、當日進行中、延賽、保留待續、保留續完各有決定性案例。
- [ ] 讓 `/api/info` 與 `refresh-cpbl-prod.sh` 共用同一可測 completion contract。→ Verify: local／production gate 對帳同一組正確指標，保留待續不會推高日期或場次。
- [ ] 盤點其他 `home_score + away_score > 0` consumer，僅修會造成 production freshness／排程錯判者；ML／歷史統計交由 `GAME-RECAP-STATUS1` 定義後再改。→ Verify: inventory 有 owner、風險與處置結論。
- [ ] 執行聚焦故障注入、全套測試與 production dry-run。→ Verify: 跨家族 T4 review、備份、API 指標與 sync gate 實測全通過。

## Done When

- [ ] 未完成保留賽不再被 freshness 視為完賽，真正續完後可自然轉為 completed。
- [ ] completion 判定只有一份可引用契約，且不以「兩端錯得一致」作為成功證據。
