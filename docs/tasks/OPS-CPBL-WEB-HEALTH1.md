# OPS-CPBL-WEB-HEALTH1 CPBL Web container healthcheck 與可寫快取修復〔T3；production reliability〕

- 需求：ruanruan　規劃：GPT-5@Codex　分支：`ai/<執行者>/OPS-CPBL-WEB-HEALTH1`
- 執行：待指派　查核：待指派（須 ≠ 執行者）
- Initiative：`INIT-PRODUCT-UX`　DB：`db_scope: none`；不得讀寫 production DB
- 部署：是　環境：production　Design Gate：N/A；內部維運修復
- 依賴：無；可獨立執行。owner、worktree、iteration、最後交接與狀態見 [`../TASKS.md`](../TASKS.md) Ledger。

## 背景與問題

2026-07-23 `INGEST-ADV-EXPAND1` rollout 的 production smoke 顯示：`prod_cpbl_web` 對外頁面皆可回 200，但 Docker healthcheck 長期為 `unhealthy`，日誌為 `wget: can't connect to remote host: Connection refused`；同時 Next.js 嘗試寫入 `/app/.next/cache`／prerender cache 時出現 `EACCES`。目前 healthcheck 以 `localhost:3000` 探測，而 runtime image 先以 root 複製 `.next` 後才切換至 `app` 使用者。

根因仍須由執行者在本機與 production container 實測確認；不得把上述觀察當作已證明的因果關係。

## 範圍

- 在 `web/Dockerfile` 修正 healthcheck 的 loopback [迴路位址] 探測與 runtime `.next` 可寫權限。
- 以正式 Docker image 實測：應用啟動後 healthcheck 連續為 healthy，且沒有新增 Next.js cache／prerender permission error。
- 依既有 push-to-deploy 流程更新 PersonalWebsite submodule，驗證 VPS `prod_cpbl_web` 與外部 CPBL 頁面。

## 非目標

- 不改 CPBL API、DB schema、migration、爬蟲、資料同步、`INGEST-ADV-RECONCILE1` 或 UI 行為。
- 不以關閉 healthcheck、永久改成 root user、忽略錯誤日誌作為修復。
- 不把既有 200 的外部頁面誤判為容器健康問題已解決。

## 驗收與回滾

- [ ] 先保存現況證據：production container health、healthcheck command／最近失敗 log、外部 `/` 與 `/api/info` HTTP status；確認 `localhost` 與 `127.0.0.1` 的實際差異，而非猜測 IPv4/IPv6 行為。
- [ ] Dockerfile 維持非 root runtime；`.next` runtime cache 目錄由 `app` 使用者可寫，最小化 ownership 變更範圍。
- [ ] `npm run build:check`、Docker image build 與本機容器 healthcheck 綠；至少驗證首頁與一個資料頁可載入，container logs 無本卡新增 EACCES。
- [ ] cpbl CI、PersonalWebsite CI、Deploy 全綠；VPS `prod_cpbl_web` `running + healthy`，外部 `/`、`/batters`、球員頁與 `/api/info` 均為 200。
- [ ] 回滾只需將 PersonalWebsite submodule 回指前一個 CPBL commit 並重新部署；本卡不得觸發 DB backup／restore 或 migration。
- [ ] handoff 需附上 healthcheck 前後輸出、非 root 權限證據、production container state、smoke URL 與 deploy SHA。

## 給執行 AI 的交接提示

> 僅處理 `OPS-CPBL-WEB-HEALTH1`。先在正式 image 重現 `prod_cpbl_web` healthcheck unhealthy 與 `.next` EACCES，再以最小 Dockerfile 改動修復；不要動 API／SQL／migration／爬蟲或 `INGEST-ADV-RECONCILE1`。驗證不可只看外部 HTTP 200，必須同時確認 Docker health 為 healthy、runtime 保持 non-root、logs 無 cache permission error。交付前提供本機 Docker probe、CI、submodule deploy 與 production smoke 證據；任何 production 異常即停止並以 submodule pointer 回退。

## Log

- 2026-07-23 register by GPT-5@Codex（依 ruanruan 指示，委託其他 AI 處理）；來源為 INGEST-ADV-EXPAND1 production verification 的既存 observability finding。
