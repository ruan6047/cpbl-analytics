#!/usr/bin/env bash
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
# 三層備援（第一層可能被權限靜默吃掉，所以不能只有它）：
#   1. osascript 通知——讀者＝需求方，在自己螢幕上。⚠️ osascript 回 0 不是通知彈出的
#      證據：通知權限未授予時它一樣回 0 而訊息被丟棄。
#   2. logs/schedule-alert.json 持久產物（條件解除時自動刪除）。
#   3. **非零退出碼**——讓 launchctl print 的 last exit status 那一面也留下痕跡，
#      而那正是 2026-08-10 那次失敗唯一被人看到的面。
#
# 產物：logs/launchd-schedule-watchdog.{out,err}.log（plist 導向）
#       logs/schedule-watchdog/last-run.json、logs/schedule-alert.json
#       logs/schedule-history/com.cpbl.schedule-watchdog.jsonl
set -uo pipefail

usage() {
  cat <<'EOU'
scripts/schedule-watchdog.sh — 排程缺席／失敗偵測器的 launchd 入口

在做什麼：依 scripts/schedule-registry.json 宣告的節奏，回頭判定每個 launchd job 的
          「上一個應該完成的週期」跑了沒、跑成怎樣；另讀生產 /api/info 的停擺訊號。
          唯讀：不取 refresh lock、不連資料庫、不觸發任何爬蟲。

會寫什麼：logs/schedule-watchdog/last-run.json（每次執行）
          logs/schedule-history/com.cpbl.schedule-watchdog.jsonl（append-only）
          logs/schedule-alert.json（有異常時；恢復正常時自動刪除）
          有異常時另彈一則 macOS 通知

怎麼呼叫：scripts/schedule-watchdog.sh                # 排程與手動皆走這支
          排程由 launchd 觸發（com.cpbl.schedule-watchdog，每日 21:10 ＋ RunAtLoad）
          想看判定細節但不要通知／不要產物：scripts/schedule_watch.py --api-url none

退出碼：0 正常｜2 缺席或應裝未裝｜3 失敗｜4 跑到一半死掉｜5 連續被跳過
        ｜6 登記表不可信或歷史毀損｜7 取不到生產訊號｜8 生產同步停擺
        ｜9 RunAtLoad 未兌現｜64 參數錯誤
EOU
}

# argv 守衛擺在任何副作用之前（本檔會寫產物、會彈通知、會發 HTTPS 請求）。
case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  "") ;;
  *) echo "未知參數：$1（本檔不吃參數；--help 看用法）" >&2; exit 64 ;;
esac

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
