# ML-SIM1 執行計畫

## 目標

依核可的 `ml-sim1-spec.md`，交付固定賽前勝率模型與單一打席情境模擬的後端模型、離線驗證及唯讀 API。

## Tasks

- [ ] PA 資料稽核與 snapshot builder → Verify：分類／狀態重建覆蓋率報告逐年輸出且低於 99% fail-closed。
- [ ] 打席 empirical-Bayes 機率 → Verify：互斥機率總和為 1、cutoff 無洩漏、走查優於聯盟常數率。
- [ ] 經驗狀態轉移與 WP 聚合 → Verify：人工邊界案例及留出季 next-state／WP 指標通過。
- [ ] 固定賽前模型 → Verify：nested walk-forward 同池比較 baseline、既有模型與校準指標。
- [ ] CLI／artifact／唯讀 API → Verify：route snapshot、API contract、缺 artifact fail-closed。
- [ ] 全面驗證與留痕 → Verify：容器回測、`uv run ruff check`、`uv run pytest` 全綠。

## Done When

- [ ] 通過核可 spec 的統計／資料閘門，或產出可重現的不上線結論。
- [ ] 分支乾淨、commit 完整，交由非 GPT 家族模型或人審獨立實測。
