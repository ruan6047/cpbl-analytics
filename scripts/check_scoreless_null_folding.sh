#!/usr/bin/env bash
# 窮舉「把缺值折成有效值」的寫法（ML-PITCHER-SCORELESS1 紅線 2 的守衛）。
#
# 為什麼要有這支腳本：iteration 9 我口頭宣稱「全檔掃過 or 0，其餘只剩兩處 or {}」，
# 但那次 grep 是在**我自己後續的編輯之前**跑的，而那些編輯又引入了一個新的 `or 0`
# （team_outs 加總）。結論與事實不符。窮舉宣稱必須可被覆核，所以改成腳本。
#
# 用法：scripts/check_scoreless_null_folding.sh
# 每一處命中都必須「已修正」或「就地註明為何無害」；輸出供人工覆核，不自動判定。
set -euo pipefail
cd "$(dirname "$0")/.."

FILES=(
  src/cpbl/api/scoreless.py
  src/cpbl/models/scoreless_streak.py
  scripts/reconcile_scoreless_streak.py
)

# 涵蓋 `x or 0`、`x or ''`、`x or {}`、`.get(k, 預設)`、SQL COALESCE。
# `.get(` 用**貪婪**比對到最後一個逗號——鍵本身可能含括號（如 `.get((*game, side), 0)`），
# 用 `[^)]*` 會在巢狀括號處斷掉而漏掉命中（本腳本第一版就是這樣漏的）。
# 寧可誤報：這是人工覆核清單，多列出來不會有害。
PATTERN="or 0\b|or ''|or \"\"|or \{\}|or \[\]|\.get\(.*, *[0-9'\"\[{]|COALESCE"

echo "掃描檔案：${FILES[*]}"
echo "樣式：$PATTERN"
echo "---"
grep -rnE "$PATTERN" "${FILES[@]}" || echo "(無命中)"
echo "---"
echo "命中數：$(grep -rcEh "$PATTERN" "${FILES[@]}" | paste -sd+ - | bc)"
echo
echo "每一處都必須是下列之一，否則即為缺陷："
echo "  (a) 已改為保留 None／未知並 fail-closed"
echo "  (b) 就地註解說明為何該處折疊無害（且說明要能被獨立驗證）"
