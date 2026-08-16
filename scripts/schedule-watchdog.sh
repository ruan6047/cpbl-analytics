#!/usr/bin/env bash
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
# 排程偵測器的 launchd 入口（OPS-SCHEDULE-FAILURE-BLIND1／#132）。
#
# 為什麼要這一層薄 wrapper：plist 直接叫 python 也行，但那樣就沒有地方放「用 /usr/bin/python3
# 而不是 uv」這個刻意的隔離決定，也沒有地方擋 argv。
#
# 隔離（刻意，不是省事）：
#   · **走系統 /usr/bin/python3，不經 uv／venv**——偵測器不可與被監控對象共用「uv 或
#     venv 壞掉」這個故障域。schedule_watch.py 因此只用 stdlib 且相容 Python 3.9。
#   · 不取 refresh lock、不碰 docker、不連本機 DB、不觸發任何爬蟲。只讀 JSON／plist、
#     跑唯讀的 launchctl print、對生產 /api/info 發一次 HTTPS GET。
#
# 四個面：
#   1. osascript 通知——主要讀者。2026-08-15 實測它被一個**非刻意開啟**的專注模式全數
#      擋下；2026-08-16 需求方裁定調整並關閉後復活，同日實測判定為 `presented`
#      （量測見 scripts/schedule_watch.py 的 notify() 區段）。⚠️ 它靠一個使用者設定，
#      **可被無聲撤銷**——已經發生過一次——所以每次執行都重新量一次，不假設它還活著。
#   2. logs/schedule-alert.json 持久產物（條件解除時自動刪除）＋ **tests/conftest.py 會把
#      它印在每次 `uv run pytest` 的 header 最前面**。這一層**不依賴任何使用者設定**，
#      是通知被擋時的備援：CLAUDE.md 明訂 push 前必跑 pytest，不需要有人記得翻檔案。
#   3. **非零退出碼**——讓 launchctl print 的 last exit status 那一面也留下痕跡，
#      而那正是 2026-08-10 那次失敗唯一被人看到的面。
#   4. stderr 警告（落 logs/launchd-schedule-watchdog.err.log）：三態各講各的話。
#
# ⚠️ 目標層級**不是寫死的**：不依賴使用者設定的保證（第 2、3、4 面）是目標 3；第 1 面
# 成功時該次達到目標 2，而那由**當次量測**決定並記在產物裡，不是由這段註解宣稱。
# ⚠️ 且「系統呈現了」≠「人讀了」——後者永遠是人證，碼判不到。
#
# 產物：logs/launchd-schedule-watchdog.{out,err}.log（plist 導向）
#       logs/schedule-watchdog/last-run.json、logs/schedule-alert.json
#       logs/schedule-history/com.cpbl.schedule-watchdog.jsonl
set -uo pipefail

# ============================================================== argv 守衛
# 守衛擺在任何副作用之前（本檔會寫產物、會彈通知、會發 HTTPS 請求）。
#
# ⚠️ 下方守衛的**控制流逐字等於** script_inventory.SHELL_GUARD_CANONICAL，不是巧合也不是
# 抄的：`#141` 量到四支排程 shell 的守衛在幾小時內漂成三個變體，於是把形狀收斂成一份
# canonical，並讓 `help_safety()` 以逐字比對判定。本檔原本寫成第四個變體（單一 `case`
# 兼管 help 與拒絕），清冊因此判它「無 argv 守衛」——**那是假的，它有守衛**，但一個
# 產生出來的清冊寫錯自己專案的事實，比沒有清冊更糟。改成 canonical 是為了讓判定成立。
#
# ⚠️ `usage()` 與 `if [ "$#" -gt 0 ]` 之間**不得插入任何一行**（含註解）：逐字比對的
# 抽取範圍是這兩者之間的整段，註解也會被算進控制流。說明只能放在這裡。
usage() {
  cat <<'EOF'
scripts/schedule-watchdog.sh — 排程缺席／失敗偵測器的 launchd 入口

在做什麼：依 scripts/schedule-registry.json 宣告的節奏，回頭判定每個 launchd job 的
          「上一個應該完成的週期」跑了沒、跑成怎樣；另讀生產 /api/info 的停擺訊號。
          唯讀：不取 refresh lock、不連資料庫、不觸發任何爬蟲。

會寫什麼：logs/schedule-watchdog/last-run.json（每次執行）
          logs/schedule-history/com.cpbl.schedule-watchdog.jsonl（append-only）
          logs/schedule-alert.json（有異常時；恢復正常時自動刪除）
          有異常時另試彈一則 macOS 通知，並記錄它到底有沒有送達
          （投遞判定分 presented／suppressed／unverified 三態，各講各的話；
            通知被擋時的備援是 pytest header 上的那一行）

怎麼呼叫：scripts/schedule-watchdog.sh                # 排程與手動皆走這支
          排程由 launchd 觸發（com.cpbl.schedule-watchdog，每日 21:10 ＋ RunAtLoad）
          想看判定細節但不要通知／不要產物：scripts/schedule_watch.py --api-url none

退出碼：0 正常｜2 缺席或應裝未裝｜3 失敗｜4 跑到一半死掉｜5 連續被跳過
        ｜6 登記表不可信或歷史毀損｜7 取不到生產訊號｜8 生產同步停擺
        ｜9 RunAtLoad 未兌現｜64 參數錯誤
EOF
}

if [ "$#" -gt 0 ]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
  esac
fi

# 位置參數契約（逐支不同，刻意不與守衛共用）：本檔一個位置參數都不收，且**沒有**
# 環境變數補救管道——判定行為的唯一旋鈕是 scripts/schedule-registry.json。
if [ "$#" -gt 0 ]; then
  printf '未知參數：%s\n' "$1" >&2
  printf '本腳本不接受任何參數；判定細節請直接跑 scripts/schedule_watch.py（見 --help）。\n' >&2
  exit 64
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# 執行身分只能在**這一層**算：launchd 直接 spawn 的是本 bash（PPID=1、父行程
# /sbin/launchd），而 macOS 會把子行程的 XPC_SERVICE_NAME 一律重設為 "0"，所以
# python 那邊自己讀環境變數必然判錯（"0" 在 Python 是 truthy，會恆判 launchd）。
# 實測見 scripts/weekly-box-revisions.sh 的同段註解與 #132 交付報告。
if [ "${PPID:-0}" = "1" ]; then
  export SCHEDULE_WATCH_TRIGGER=launchd
else
  export SCHEDULE_WATCH_TRIGGER=manual
fi

# 明確釘住系統 python：PATH 上若有 pyenv／venv 的 python3，隔離就白做了。
PYTHON="/usr/bin/python3"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

"$PYTHON" "$REPO_DIR/scripts/schedule_watch.py" --notify
exit $?
