# OPS-REMOTE-CUTOVER1 遠端 crawler production canary 與切換 〔T4；🔴production／資料正確性／資安部署〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/OPS-REMOTE-CUTOVER1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　DB：`db_scope: write`；production `cpbl` 需專屬 lane lock、備份與 rollback
- 部署：是　環境：production＋本機 fallback　Design Gate：N/A；內部維運切換
- 計畫：[`../../ops-remote-crawler-rollout.md`](../../ops-remote-crawler-rollout.md) Phase 4–5
- 依賴：`OPS-REMOTE-WORKER1` T4 APPROVE、shadow 對帳達標、需求方 production sign-off。
- owner、worktree、iteration、最後交接與交付／部署 current-state 見 GitHub Issue＋[Project #4](https://github.com/users/ruan6047/projects/4)；歷史交接留在 Issue timeline 的結構化 comment。
- **前提查證（2026-07-27）**：www 對 VPS 仍 404（當日實測）、stats 域全開；本機 launchd 每日爬連日全綠。**本鏈降為可用性保險**（防本機長期離線），且解除本機依賴的候選正解已變：stats 域自有賽程與單場 API（含 LiveLog），若 TM Gate3（~8/7）與 live observer 證據支持來源遷移，應評估開「stats 域 VPS 爬蟲」新卡取代本鏈——8/7 後由需求方裁定，屆時重評本鏈存廢。

## 驗收

- [ ] 先 canary 單一排程時窗；remote 與 local crawler 有跨主機互斥，任何時刻只允許一個 primary writer。
- [ ] production 寫入前備份，逐表／批次失敗可觀測且 rollback rehearsal 通過；freshness 驗證使用真實資料 contract。
- [ ] 告警區分未觸發、challenge、crawler failure、sync failure、stale running 與資料對帳失敗；禁止沉默 fallback 後宣告成功。
- [ ] 本機 launchd 先保留停用／手動 fallback，不在同一變更刪除；回退 remote 後可單次安全接手且不冷啟動重跑。
- [ ] 連續多日 canary SLO、成本與值班負擔達標後，才由需求方決定 remote primary；未達標即 NO-GO／回復本機。
- [ ] 跨家族 T4 review、production sign-off、CI／deploy／smoke／資料 QA 全部留痕後才可 release。
