# UX-HOME-LIVE-STRIP1 首頁 live 比賽精簡狀態列〔T3；⚪使用者可見功能〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/UX-HOME-LIVE-STRIP1`
- 執行：待指派（建議 L2；既有 React polling／live contract 整合）　查核：待指派（跨模型家族；須 ≠ 執行）
- review_independence: [human, cross_family]
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2、LIVE_GAME_PRODUCT_SPEC v1.1
- DB：`db_scope: none`；只讀既有 Redis canonical snapshot 與 PostgreSQL fallback
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：首頁 `/` 的 live strip、既有 live API 的首頁聚合讀取、型別與測試；不新增 worker、DB schema、推播或文字轉播。
- Discovery：先以 production／本機的 canonical phase 驗證首頁可取得的場次集合、payload 大小與 12 秒 polling 行為；不得假設 `/games/[sno]/live` 可直接批次使用。
- Design：需需求方 Design Gate；候選設計見本卡〈決策〉。

## 問題陳述

`UX-LIVE-GAME1` 已在單場頁呈現 live 狀態，但首頁仍只回答「最近比賽日／下一批賽事」。有一軍比賽正在進行時，首頁沒有直接可見的入口，使用者必須先進賽程頁才知道現在有比賽。

首頁不能因此變成即時文字轉播或多一套 ESPN 狀態板；產品定位仍是非即時分析。正解是僅在 canonical phase=`live` 時渲染一張小型、可點入單場的 strip，無 live 場次時零空白、零 polling。

## 決策（Design Gate 必答）

1. strip 顯示層級：建議「雙隊名／比分／局況／最後更新時間／進入單場」；不顯示壘包、球數、逐球與 Recent Plays。
2. 多場同時 live：建議最多 2 場，超出時顯示總數連結 `/games`，不讓首頁無限延長。
3. 位置：建議 hero 下、DailyHub 前；有 live 時它是當下情境入口，無 live 時不佔資訊預算。
4. polling：前景 12 秒，背景暫停或降頻；只在 strip 存在時啟動，final／stale／離開頁面必清除 timer。

## 驗收條件

- [ ] 只有 canonical `live` 場次出現 strip；`scheduled`、`lineup_announced`、`final`、`postponed`、`reserved`、`unknown` 一律不渲染，且無 live 時沒有空容器或 polling。
- [ ] 每張 strip 只顯示雙隊、比分、局況、最後更新與單場連結；不可複製逐球／壘包／球數 UI，資料缺失顯示 `—`，不得補 0 或宣稱即時。
- [ ] stale／source error 保留 last-known-good 並標示更新中斷；不得把它渲染為未開賽或正常 live。
- [ ] 同時多場時排序／上限 deterministic，超出場次可進 `/games`；首頁第一 viewport 仍維持 1 個主要結論、最多 3 個支持證據、1 個主要下一步。
- [ ] 所有 live 資料取自既有 canonical snapshot；不新增 DB 寫入、worker、外部請求或 API 寫入。

## 驗證

- [ ] contract／component tests 覆蓋無 live、單場 live、多場 live、stale、source error、final transition 與缺比分／局況。
- [ ] 瀏覽器實測前景 polling 約 10–15 秒、背景降頻／停止、final 後停止，沒有重複 timer、全頁 reload 或外部 request。
- [ ] 375px 與桌機無橫向溢出；strip 連結／焦點目標 ≥44px，比分與狀態以 `aria-live=polite` 適量播報。
- [ ] `uv run ruff check`、`uv run pytest`、`cd web && npm test`、`npx tsc --noEmit`、`npm run build:check` 通過。

## 邊界

- 依賴：`UX-LIVE-GAME1` 的 canonical phase 與 public snapshot；在該契約 production 實測完成前不得 merge。
- 不包含直播通知、推播、賽前先發、完整 box、逐球文字轉播、預期勝率或任何新的即時資料基礎設施。

## Log

- 2026-08-01 草稿 by GPT-5@Codex（依 ruan6047 指示）：從 UX-BRAND-HOME1 分離，避免首頁品牌卡擴張為 live 產品改版。
- 2026-08-02 需求方 ruan6047 裁定正式註冊；查核順序定為需求方人工審後，再交由跨模型家族 AI 查核。待 Discovery 與 Design Gate 後才可 claim。
