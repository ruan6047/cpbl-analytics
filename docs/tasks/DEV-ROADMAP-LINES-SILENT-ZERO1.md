# DEV-ROADMAP-LINES-SILENT-ZERO1 roadmap_lines 對錯誤 schema 的輸入靜默回報零活卡，且 exit 0　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：看板上的數字要等於真實的待辦
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-ROADMAP-LINES-SILENT-ZERO1），不重複於此檔。

## 核心痛點

- **痛點**：scripts/roadmap_lines.py --json 讀 payload['items']（gh project item-list 的 schema），而官方認可的狀態面匯出 wfcli snapshot 吐的是 {'cards': [...]}。鍵名不符時 .get('items', []) 回空陣列，工具印出 active_total=0、per_line 全 0、exit 0——一份看起來完全正常的報告。實測 2026-08-15 同一份狀態面：正確輸入得 active_total=44（L1 12／L2 10／L3 5／L4 12／L5 5），錯誤輸入得 0。失效方向是回報最無害的答案。該工具 active_cards() 的 docstring 逐字寫著缺欄位一律 fail closed——它對缺欄位 fail closed，對整個容器鍵不存在卻 fail open。--check 路徑安全（大聲 FAIL、列出 43 張只在 ROADMAP），危害限於 --json 與其消費者。PM 本人就踩了這個坑，因為 wfcli snapshot 才是官方匯出。

## 驗收條件

- [ ] 餵入不含 items 鍵的 payload 時必須非零退出並指名收到的是什麼 schema，不得回報 active_total=0;判準以「容器鍵存在與否」為準而非「取到的清單是不是空的」——真的零活卡與讀不到活卡必須可區分;若決定改為同時接受 wfcli snapshot 的 schema，兩種 schema 的辨識須明示且各有回歸案例，不得靠猜;既有 --check 路徑的行為不得改變（它現在是 fail closed 的）

## 驗證

- [ ] 以 wfcli snapshot --out-dir 的實際產物與 gh project item-list --format json 的實際產物各跑一次，貼出兩者 exit code 與輸出;變異檢驗：拿掉修法後回歸測試必須轉紅;uv run ruff check + uv run pytest
