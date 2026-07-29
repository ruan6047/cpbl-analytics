# OPS-WEB-DEPS1 前端相依套件漏洞（1 critical ＋ 3 high，皆為建置面）〔T2；🟡維運〕

- 需求：ruan6047（2026-07-29 依 `UX-ENTITY-LINKS3` 跨家族查核的 informational finding 1 指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/OPS-WEB-DEPS1`
- 執行：待指派（建議 L2；patch 級升版＋回歸驗證，判準已界定）　查核：待指派（建議 L2；≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：**是**（前端映像重建）　環境：production　PR：—　Merge SHA：—
- 範圍：`web/package.json`、`web/package-lock.json`
- Discovery：—（T2，暴露面已於開卡時查明）
- Design：Design Gate N/A——無使用者可見變更（升版不改行為）。

## 事實（開卡時實查，非轉述查核者的「4 個漏洞」）

`npm audit` 在 `web/` 回報 **1 critical ＋ 3 high**。逐一查相依路徑與實際暴露面後，**四項全部落在建置面或未使用的功能路徑上**：

- **`tar` 7.5.16（critical，node-tar PAX numeric path type confusion）**：來源是 `@tailwindcss/postcss → @tailwindcss/oxide → tar`，屬 **devDependency 鏈**，只在 build 階段出現。
- **`next` 15.5.20（high，App Router Server Actions DoS）**：全站 **未使用 Server Actions**（`rg '"use server"' web/src` 零命中），該 advisory 的攻擊面在本專案不成立。
- **`sharp` 0.34.5（high，libvips CVE-2026-33327／33328…）**：由 `next` 帶入，用於 `next/image` 最佳化；全站 **未使用 `next/image`**（零命中）。
- **`postcss`（high，XSS via unescaped `</style>`）**：build 階段執行（Tailwind 管線與 `next` 內部），不在 request 路徑。

生產 runtime 映像為多階段建置，**只複製 `.next/standalone` 與 `.next/static`**（見 `web/Dockerfile`），builder 階段的 `node_modules` 不進 runtime。

**因此本卡是低風險維護，不是資安事件。** 開卡的理由是：`fixAvailable` 全為 true 且 `next` 的修正版 **15.5.22 非 semver-major**（15.5.20 → 15.5.22 為 patch），修它同時解掉 `postcss` 與 `sharp` 三項；成本極低而帳面長期掛著 critical 會稀釋未來真正的告警。

## 目標

清掉 `npm audit` 的 high／critical，且**不改任何行為**。

- `next` 15.5.20 → **15.5.22**（patch；連帶解 `postcss`、`sharp`）。
- `tar` 經 `@tailwindcss/*` 鏈解決（升 tailwind 相關套件或 `npm audit fix`，**不得用 `--force`**）。

## 紅線

1. **不得 `npm audit fix --force`**。它會做 semver-major 升級，把一張 patch 卡變成框架升級卡。若某項只能靠 major 才能解，**停下來寫進卡片交需求方裁定**，不要自行升。
2. **不得只看 `npm audit` 轉綠就結案**。audit 綠燈只證明版本號變了，不證明站台沒壞——必須有 build 與測試證據。
3. **`package-lock.json` 必須一起提交**，且 `npm ci` 能從乾淨環境重現。

## 驗收條件

- [ ] `npm audit` 的 high／critical 歸零；若有項目無法在不做 major 升級的前提下解決，**明列該項與理由**（不得靜默留著也不得硬升）。
- [ ] `next` 停在 15.x patch 版；`package.json` 與 `package-lock.json` 同步提交。
- [ ] `npm ci` 於乾淨 worktree 成功；`npm run build:check` 21 routes 全過；`npm test` 全過。
- [ ] **行為未變的證據**：至少三頁（建議 `/`、`/games/[sno]`、`/standings`）與升版前的渲染結果比對，DOM 結構或截圖擇一，說明比對方法。
- [ ] `docker compose build`（或等效的 web 映像建置）成功——升版可能踩到 Alpine／node:22 的原生模組差異，**本機 build 過不代表映像 build 過**。

## 驗證

- [ ] 查核者於獨立 detached worktree 重跑 `npm ci` ＋ `audit` ＋ `build:check` ＋ `test`。
- [ ] 查核者確認沒有 semver-major 升級混入（比對 `package.json` diff 與 lock 中主要套件的 major 版號）。
- [ ] 查核者確認 `next` 的升版未改變既有路由集合（21 routes 不多不少）。

## 邊界

- 只動 `web/` 的相依；不碰 Python 側、不碰 `Dockerfile` 的階段結構。
- 不處理 Lighthouse 的 `text-faint` 色彩對比（同批 informational，屬設計系統議題，另議）。
- 預估 S。

## Log

- 2026-07-29 register by Claude Opus 5@Claude Code（Coordinator，依 ruan6047 指示）；iteration 0。來源為 `UX-ENTITY-LINKS3` 跨家族查核的 informational finding 1（查核者僅報「3 high ＋ 1 critical」）。**Coordinator 開卡前實查相依路徑與使用情形**，確認四項全在建置面或未使用功能路徑上、生產 runtime 映像不含 builder 的 `node_modules`，據以把本卡定位為低風險維護而非資安事件——避免用嚴重度標籤驅動優先序。
