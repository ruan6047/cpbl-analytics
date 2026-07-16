# ML-UMP2 執行計畫

## Goal

以逐打者身高比例代理帶重跑 ML-UMP1 全敏感度，嚴格驗證主審與球隊方向翻轉是否全數消失。

## Tasks

- [ ] 建立 player-height coverage waterfall 與 fail-closed 契約 → Verify: pitch 與 distinct hitter 的缺失數可對帳。
- [ ] 用現有 bio ingest 補齊 2026 called-pitch 打者身高 → Verify: 重跑 audit 不對缺值 fallback。
- [ ] 新增 `height_scaled_proxy_v2` 與 per-pitch zone 計分 → Verify: 比例、margin、邊界與缺值單測先紅後綠。
- [ ] 重跑 fixed v1、v2 ±1/2/3/5 cm、venue、home/away、月份、50cm 與球緣對照 → Verify: 18 主審／6 隊逐列對照。
- [ ] 以 2,000 次 game-cluster bootstrap 產出 ignored artifacts 與結果報告 → Verify: 守恆、coverage 與零翻轉 gate 可重現。
- [ ] 執行 ruff、聚焦測試與全套 pytest → Verify: 全綠且 worktree 無非預期變更。

## Done When

- [ ] 結果明確回答 18 主審／6 隊是否零翻轉，並且不超出代理帶、描述性與非因果語意。
