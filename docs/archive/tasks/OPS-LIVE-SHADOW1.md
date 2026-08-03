# OPS-LIVE-SHADOW1 VPS 隔離 live source observer 〔T4；🔴production 資安部署／資料證據〕

- 需求：ruan6047　規劃：GPT-5.6@Codex　分支：`ai/<執行者>/OPS-LIVE-SHADOW1`
- 執行：待指派（建議 L3；跨 repo production isolation、來源限流與可重驗證據）　查核：待指派（建議 L3；須跨模型家族或人工，且 ≠ 執行）
- Initiative：—　spec 基線：`LIVE_GAME_PRODUCT_SPEC v1.0`
- DB：`db_scope: none`；不得取得或掛載 local／production DB credentials
- 部署：是　環境：production VPS（隔離 shadow namespace）　PR：—　Merge SHA：—
- 範圍：見 [`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §2、§4.1–§4.2；只蒐集 `LIVE-GAME-BACKEND1` T4 觀測矩陣需要的來源證據，不提供 public contract
- Discovery：ruan6047 於 2026-07-26 核可「先建立、跨家族審核並部署隔離 VPS observer，使開發機可關閉」；成功條件為不接 production data plane 仍能跨 T-30h／T-90m／T-60m／T-30m／START 留存可獨立重驗的證據
- Design：Design Gate N/A；本卡為無公開入口、無使用者可見狀態的暫時性維運觀測器
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log

## Plan Gate

- [ ] 本修訂版須先由非 GPT 家族（Claude／Gemini）或人工完成 Plan Gate APPROVE；這不取代實作完成後的跨家族 T4 implementation review。
- [ ] cpbl source 只能由本 repo protected `main` 建置；VPS service 必須另在 `PersonalWebsite` 登記 companion 卡 `OPS-CPBL-LIVE-SHADOW1`，修改其 protected `main` 的 `docker-compose.prod.yml`／部署驗證。兩邊均須獨立查核、合併後才部署，deploy event 同時記錄 cpbl main SHA、PersonalWebsite main SHA 與 image ID。
- [ ] 禁止 SSH 手動 `docker run`、部署 feature branch，或建立會被主站 `docker compose up -d --remove-orphans` 移除的旁路服務。
- [ ] `docs/AI_RUNBOOK.md` 與 `docs/CPBL_SITE_MAP.md` 納入本卡 scope：將「VPS 禁止官網 crawler」限縮為 `www.cpbl.com.tw` 禁止；`stats.cpbl.com.tw` 僅允許經 T4 核可的 observer／worker，並補 `GameStatus=START` 的 2026-07-26 實測 provenance。

## 驗收條件

- [ ] observer 唯一 allowlist 為 `https://stats.cpbl.com.tw/api/proxy/v1/games/schedule` 與 `https://stats.cpbl.com.tw/api/proxy/v1/games/{game_id}`；schedule 固定 `kindCode=A&year=2026&month=7`，single-game 僅允許 `2026-A-226`、`2026-A-227`、`2026-A-228`。URL 必須在發送前以 scheme／host／exact path 驗證；禁止 redirect、`www.cpbl.com.tw`、production DB／Redis／API 與 Docker socket，且不得開放 inbound port。
- [ ] request policy 為 connect timeout 5 秒、read timeout 15 秒；每 cycle 最多 4 個初始 request、含 retry 最多 8 個 attempts、每場每分鐘最多 5 個、全域每分鐘最多 18 個、全期間最多 6000 attempts。429 不做同 cycle retry，遵守 `Retry-After`（至少 60 秒且不超過截止時間）；5xx／timeout 每 request 最多重試 1 次，jitter 30–120 秒，連續失敗採全域 exponential backoff、上限 15 分鐘。所有 attempts（含失敗）先扣 budget，耗盡即 exit 0 並留下終止原因。
- [ ] 每次 HTTP response 以 immutable gzip 保存完整 raw body；先寫同 volume temp file、`fsync` 後 atomic rename。append-only manifest JSONL 使用 process lock、run ID、嚴格遞增 sequence、UTC／Asia-Taipei wall clock、monotonic elapsed、game ID、URL template ID、HTTP status／latency、official raw status、exact key path presence／count、raw SHA-256、gzip path／size；manifest 每筆 append 後 `fsync`。不得把時間窗、空陣列或未知值推論成已公布／完賽。
- [ ] evidence volume 由 app 施行 4 GiB 累積寫入上限；host／volume 可用空間低於 1 GiB 或 10% 任一門檻即 fail closed、寫入終止 marker 後 exit 0。匯出時產生排序 manifest、每檔 SHA-256 與總 checksum；T4 查核者可只依匯出包重建 exact key path、partial 與 first-observed 判讀。
- [ ] PersonalWebsite companion service 使用獨立 container name、獨立 egress bridge network、專用 named volume、`read_only: true`、`tmpfs: /tmp`、`user` non-root、`cap_drop: [ALL]`、`security_opt: [no-new-privileges:true]`、無 `env_file`／secrets／backend network／`depends_on`，並固定 CPU、memory 與 Docker log rotation（10 MiB × 3）。
- [ ] restart policy 固定 `on-failure:3`。持久 kill switch 為 evidence volume 的 `/evidence/STOP`；process 每 cycle 與每 request 前檢查。截止時間固定 `2026-07-30T00:00:00+08:00`：到期或 STOP／budget／disk gate 觸發皆寫終止 marker並 clean exit 0；VPS reboot 不因 `on-failure` 復活，CI redeploy 即使重新 start 也必須在任何 network request 前讀截止時間／STOP 並 exit 0。
- [ ] observer 輸出只作 `LIVE-GAME-BACKEND1` 查核證據；不得被 production API、前端或正式 refresh 消費。完整 T4 後端卡仍須獨立查核，不因本卡通過而降級。

## 紅線（違反即退回）

- [ ] 不得部署任何未合併至兩個 protected `main` 的 source，不得以「shadow」名義繞過 production workflow。
- [ ] 不得掛載 production credentials、backend network、Docker socket、host path 或 inbound port；redirect／非 allowlist URL 一律在送出前拒絕。
- [ ] 不得保存只有 hash 而無可重驗 raw evidence，不得在磁碟不足時覆寫／rotate 掉 observation，不得猜測來源語意。
- [ ] 不得讓 deadline／STOP 的 clean exit 被 restart policy 視為 crash；7/30 截止後任何 reboot／redeploy 均不得發出 request。
- [ ] production 部署前須取得跨模型家族或人工 T4 APPROVE，以及 ruan6047 對跨 repo compose 變更、request hard limits 與撤除方案的 sign-off。

## 驗證

- [ ] unit／integration tests 覆蓋 allowlist 拒絕、成功、redirect、429、5xx、timeout、schema drift、budget、backoff、重啟續寫、process lock、atomic raw／manifest、checksum、disk gate、STOP、deadline 與截止後零 request；`uv run ruff check`、`uv run pytest` 通過。
- [ ] 用 production-equivalent image／compose rehearsal 檢查 non-root、read-only rootfs、capabilities、no-new-privileges、tmpfs、無 port／DB／cache／env_file／backend network、資源與 log 限制、volume 持久化；模擬 crash 最多重啟 3 次，deadline／STOP exit 0 不重啟。
- [ ] 在隔離 rehearsal 模擬 host reboot 與 CI `compose up -d`：截止後 process 必須先 exit 0 且 mock server 收到 0 request；記錄 image digest 與 compose config 證據。
- [ ] 兩 repo 跨家族 T4 review APPROVE 且合併 `main` 後才可部署；部署時驗證 NTP 同步／clock skew、兩個 main SHA、image ID、container inspect、stats 200／latency、第一份 gzip raw＋manifest、volume free space、request counter 與 STOP smoke。
- [ ] 7/30 或證據收集完成後先移除 service／container／network；volume 在 `LIVE-GAME-BACKEND1` 匯出、checksum 與 reviewer 對帳完成前保留。刪除 volume 為不可回復資料操作，必須另取得 ruan6047 明示。

## 依賴與範圍

- 本卡從 `main` 獨立實作，不 cherry-pick 或部署尚未通過 T4 的 `ai/codex/LIVE-GAME-BACKEND1`。
- PersonalWebsite companion 卡只負責受保護的 compose／deployment wiring；不得把 observer source 複製進主站，也不得擴張既有 cpbl API／DB 權限。
- 本卡的經查核輸出是 `LIVE-GAME-BACKEND1` 來源觀測矩陣的證據輸入；`UX-LIVE-GAME1` 仍只依賴完整 backend additive API contract。

## Log

- 2026-07-26T20:24:13+08:00 register by GPT-5.6@Codex（依 ruan6047 核可建立 VPS 隔離 observer 卡；尚未 claim、實作或部署）。
- 2026-07-26 Plan Gate by GPT-5.6 sibling context → REQUEST_CHANGES；7 blocking findings：T4 分級、跨 repo deploy path、deadline 防復活、request hard limits、raw evidence 可重驗、baseline、Runbook／Site Map 契約衝突；未 claim／實作／部署。
- 2026-08-03T12:45:00+08:00 release by Claude Opus 5@Claude Code（依 ruan6047 指示代 Coordinator 結案）。7/30 兩項待辦皆閉合：**對帳**＝`LIVE-GAME-BACKEND1-NOTE-005` 唯讀 VPS 對帳（deadline clean exit、manifest 4,614 entries、A-226／227／228 每場 HTTP error=0 且皆到 FINISHED、export manifest／checksum 已生成），且證據消費卡 `LIVE-GAME-BACKEND1` 已於 7/30 21:16 結案；**撤除**＝PersonalWebsite protected main `3bee24c` 移除 `cpbl-live-observer` service 與 deploy verify 步驟，該次及其後 deploy run 皆綠，container 由 `--remove-orphans` 移除。evidence volume `cpbl_live_shadow_evidence` 與 network `cpbl_live_shadow_egress` **刻意保留**（刪除 volume 屬不可回復操作，須 ruan6047 另行明示），其處置為獨立操作。**驗證邊界**：本機 session 無 VPS SSH／production 憑證，撤除結論依據為 protected main compose 內容與 deploy run 結果，未做主機端實測。dormant 的 `src/cpbl/ingest/live_shadow_observer.py` 保留（截止釘在碼內，啟動即於發 request 前 exit 0），是否刪除另議。worktree 與卡族分支（含 FIX1）本地與 origin 均已回收；companion 卡 `OPS-CPBL-LIVE-SHADOW1` 於 PersonalWebsite 同步結案。
