# 遠端無人值守 crawler 分階段計畫

## Goal

用可停止、可觀測且合規的方式，從安全探測逐步走到遠端 crawler canary；任何階段失敗都保留現有本機 launchd fallback。

## Tasks

- [ ] `OPS-REMOTE-CRAWL1`：核可探測邊界、候選路線與停止條件。→ Verify: Discovery Gate 明確允許／拒絕下一階段。
- [ ] `OPS-REMOTE-PROBE1`：交付 opt-in DEBUG CLI；allowlist、單次請求、零 retry、零 DB、sanitized JSON。→ Verify: fixture 證明 no-retry／redaction，local 與 VPS schema 相同。
- [ ] `OPS-REMOTE-ROUTE1`：在分離時窗比較 VPS 直連、合規台灣出口、住宅 worker。→ Verify: 證據矩陣含可靠性、合規、安全、成本及 GO／NO-GO。
- [ ] `OPS-REMOTE-WORKER1`：只對通過路線建立隔離 shadow worker，不寫 production。→ Verify: isolated DB/artifact、kill switch、一次性 job 與可觀測失敗均實測。
- [ ] `OPS-REMOTE-CUTOVER1`：production canary、排程與回滾；本機排程先維持 fallback。→ Verify: 備份、互斥、freshness 對帳、告警與人工 sign-off 後才切 primary。
- [ ] Phase 5 Verification：跨家族 T4 查核整條鏈路與連續數日 canary。→ Verify: 無重複 crawler、無 secrets、無沉默失敗，rollback rehearsal 成功。

## Done When

- [ ] 遠端刷新可無人值守運作，且任何 challenge／出口故障都 fail closed，不會連續冷啟動或污染 production。

## Notes

- DEBUG 介面只允許明確 opt-in 的 CLI／受保護 CI artifact，不建立公開 HTTP debug endpoint。
- 代理採購、challenge 繞過、共享住宅憑證與未隔離 production 寫入不在前兩階段授權範圍。
