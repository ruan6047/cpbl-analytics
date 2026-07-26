# OPS-CPBL-WEB-HEALTH1-FIX1 Next.js prerender 寫入權限 remediation 〔T3；⚪production reliability〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：`ai/fable-5/OPS-CPBL-WEB-HEALTH1-FIX1`（卡族共用 worktree `ops-cpbl-web-health1-execution`）
- 執行：Claude Fable 5@Claude Code（建議 L2；根因已定位的 Dockerfile 權限修正＋正式 image 重現）　查核：待指派（獨立查核；須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：—
- DB：`none`；不得讀寫 production DB
- 部署：是　環境：production（push-to-deploy，查核 APPROVE＋需求方授權後）　PR：—　Merge SHA：—
- 範圍：原卡 9a6c84f 已修 healthcheck bind／loopback（有效，prod healthy），但**僅授權 `.next/cache` 不足**：production 實證（NOTE-007，2026-07-26T06:55:11Z）首次 `/methodology` 請求觸發 `EACCES open /app/.next/server/app/methodology.html`——Next.js 對 build 時靜態化、runtime lazy 寫回的路由會重寫 `.next/server/app/**`（該頁 fetch API 失敗退快照設計使其被靜態化）。本卡：
  1. 以正式 image **先重現** EACCES（缺陷版），確認實際 writable paths（`.next/server/app`、`.next/cache`，如有其他以實測為準）。
  2. `web/Dockerfile` 最小 ownership 擴充：runtime 需寫入的目錄交給 `app`，其餘維持 root:root 唯讀；**不得整包 `.next` chown、不得改回 root user、不得關 healthcheck**（原卡非目標沿用）。
  3. 修復版同 image 驗證：`/methodology` 首請求後 logs 零 EACCES、container healthy、runtime 仍 non-root。
- Discovery：—（根因已由 NOTE-007 production 證據定位）
- Design：Design Gate N/A；內部維運修復

## 驗收條件

- [ ] 缺陷版正式 image 重現 EACCES（先紅證據：logs 原文）。
- [ ] 修復版：`/methodology` 與首頁載入後 container logs 無任何 permission error；`docker inspect` health=healthy；容器內 `id` 證明 non-root。
- [ ] ownership 變更最小化：`ls -l` 證明 `.next` 除實測必要目錄外仍 root:root。
- [ ] `npm run build:check` 綠（不影響 dev 快取）；不動 API／UI 行為。
- [ ] 部署後（需求方授權）：VPS `prod_cpbl_web` healthy、外部 `/`、`/methodology`、`/batters` 200、logs 無 EACCES——此項屬部署驗證，merge 前以本機證據交付。

## 驗證

- [ ] 本機：docker build → 缺陷/修復對照 run → curl ＋ logs ＋ inspect 證據齊附 handoff。
- [ ] 回滾：僅需 PersonalWebsite submodule 回指前一 CPBL commit 重新部署（沿原卡）。

## Log

- 2026-07-26T17:56:00+08:00 register by Claude Fable 5@Claude Code（依 ruan6047 指示開卡並派工；原卡 NOTE-007 ⚠驗證失敗的 remediation，原卡由本修復卡帶動結案）。
