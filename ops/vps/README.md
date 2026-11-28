# ops/vps：正式站 VPS 主機排程（版本化在本 repo，⛔ 不會自動安裝）

本目錄的 unit 檔只是 repo 內的版本化副本；安裝、啟用、停用都要需求方授權，程序見
`docs/AI_RUNBOOK.md` §3〈新球季冠軍自動補列（#469）〉。

| 檔案 | 作用 |
|---|---|
| `cpbl469-champion-autofill.service` | `docker exec prod_cpbl_api cpbl-champion-autofill`：收官判定 decided 且冠軍表缺該年才補列；⛔ 不 migrate |
| `cpbl469-champion-autofill.timer` | 每日 12:10（Asia/Taipei），避開 #393 每日 11:10 與週一 13:10；`Persistent=true` |

- 程式隨主站一般部署（bump submodule → Deploy 重建 `prod_cpbl_api`）送到；timer 裝一次後不用跟著換版。
- 不屬 #393 lane（`/var/lib/cpbl393-*`、`cpbl393-*` timer），也不登記在 `scripts/schedule-registry.json`
  （該表只描述 Mac launchd job，由 `scripts/schedule_watch.py` 以 plist 對帳）。
- 靜態契約測試：`tests/test_champion_autofill_units.py`。
