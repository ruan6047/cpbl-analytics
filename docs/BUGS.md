# BUG 滾動 log — cpbl-analytics

> **T2 快線** bug：根因已知、局部且可逆 → 分支、先紅後綠、獨立輕量查核、merge，於此追加一行。T1 純文案／typo 只留 commit 說明。
> **T3+ 慢線**：根因不明、跨檔、契約／資料／安全影響或紅線 → 開卡於 [`tasks/`](tasks/)，見 [`TASKS.md`](TASKS.md)。
> git 是程式碼／文件事實來源；[`control-plane event log`](control-plane/events.jsonl) 是作業狀態事實來源。
>
> 格式：`- <ISO 8601> <症狀> → <commit/SHA> (by <模型@工具>；iteration <n>；回歸測試 <檔:test>；查核 <actor>)`

---

_（尚無 WF-15 後的 T2 快線 bug。）_
