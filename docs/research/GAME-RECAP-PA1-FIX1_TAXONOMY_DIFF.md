# GAME-RECAP-PA1-FIX1 iteration 4：taxonomy 動態證據新舊聚合全母體 diff

> 執行者自驗（2026-07-29，iteration 4 交付攻擊點 1 的封閉）：舊 `_ISLAND_SQL` 聚合
> （commit `282af3f` 之前的實作，自 git history 取出原文）vs 新 `_aggregate_islands()`
> （走正式 `build_islands()`），對全母體 2018–2026 kind A/C/D/E 逐島比對。
> 重現方法：`git show 282af3f:scripts/pa_transition_taxonomy.py` 取出 `_ISLAND_SQL`
> 原文直接執行，與現行 `_RAW_ROWS_SQL` ＋ `_aggregate_islands()` 對照。

## 結果（本機 DB，執行當下）

```
舊聚合島數 = 331496
新聚合島數 = 331200
差 = 296（預期 296）
訊號島數對照（舊→新）：
  batter_out: 199402 → 199402  (Δ0)
  hit: 78398 → 78398  (Δ0)
  walk_hbp: 32805 → 32805  (Δ0)
  reach_error: 17635 → 17635  (Δ0)
  scored: 32309 → 32309  (Δ0)
term_action 分布變動的 action 數 = 23；總淨變 = -296（預期 −296）
   三振: -68
   一壘安打: -38
   四壞球: -37
   飛球接殺: -35
   刺殺: -32
   趁傳: -14
   犧牲飛球: -11
   雙殺打 刺殺: -10
   觸身死球: -8
   二壘安打: -7
   界外飛球接殺: -7
   一壘安打 內野安打: -5
```

## 結論

1. **島數差恰為 296**＝FIX1 認定的合併對數（每對合併淨減一島），無其他增減。
2. **五個觀測訊號（batter_out/hit/walk_hbp/reach_error/scored）的島級計數零漂移**
   ——合併只把兩段碎片的訊號 OR 起來，未改變任何訊號判定；regex 翻譯無偏差。
3. **term_action 分布（strip 後口徑）僅 23 個 action 變動、全為遞減、總和 −296**
   ——每個合併移除的正是與其終結結果同名的重複島；沒有任何島改變終結結果。
   注意第一次 diff 若不 strip 會看到大額假差異（如 一壘安打 ±5 萬）：舊 SQL 輸出
   未去尾空白、舊 profiles 在下游才 strip；新聚合先 strip。**profile 層語意兩者相同。**

## 邊界

- 本 diff 證明「聚合翻譯忠實 + 合併面精確」，**不**證明訊號 regex 對未來 content
  變體的穩健性（該面仍留給查核者）。
- 數字隨 DB 增長而變；重跑以當下 DB 為準，關鍵是三個結構性結論而非絕對值。
