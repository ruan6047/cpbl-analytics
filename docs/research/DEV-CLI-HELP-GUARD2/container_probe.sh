#!/usr/bin/env bash
# DEV-CLI-HELP-GUARD2：cpbl-train / cpbl-train-pitching 的容器內密封探針取證。
#
# 為什麼要進容器：這兩支 import LightGBM，macOS host 缺 `libomp` 直接 import 失敗
# （CLAUDE.md 既知限制），host 上的盤點只能得到 IMPORT_ERROR、拿不到護欄證據。
# 容器映像裝了 libgomp1，是唯一能真正 import 並觀察 main() 行為的地方。
#
# 為什麼是探針而不是真跑：`cpbl-train` 的主流程會讀全庫、訓練 LightGBM 並寫
# model_versions／projections。本卡 db_scope=none，**嚴禁真跑訓練**。探針把
# migrate/conn/scrape_*/build_* 與 socket/psycopg（含 async）全換成會拋例外的 stub，
# 觀察到的唯一事實是「主流程有沒有被觸發」。
#
# `--no-deps`：不啟動 db／redis。探針碰不到它們，起了只是徒增副作用面。
#
# 用法（repo 根目錄）：
#   bash docs/research/DEV-CLI-HELP-GUARD2/container_probe.sh > \
#        docs/research/DEV-CLI-HELP-GUARD2/container-probe.md
set -euo pipefail

cd "$(dirname "$0")/../../.."
REPO_ROOT="$PWD"
AUDIT_DIR="docs/research/DEV-CLI-HELP-GUARD1"   # 盤點工具的 canonical 位置（GUARD1 交付）

docker compose build api >/dev/null 2>&1

echo "# DEV-CLI-HELP-GUARD2 — cpbl-train / cpbl-train-pitching 容器內探針取證"
echo
echo "> **本檔由指令產生，勿手改。**重新產生："
echo "> \`bash docs/research/DEV-CLI-HELP-GUARD2/container_probe.sh > docs/research/DEV-CLI-HELP-GUARD2/container-probe.md\`"
echo
echo "掃描對象：\`$(git rev-parse HEAD)\`"
echo
echo "取證方式與判定碼定義見 \`$AUDIT_DIR/audit_cli_help.py\` docstring——同一支工具、"
echo "同一份封鎖清單，只是換到容器內執行。\`seal_gap: []\` 代表該次探針的封鎖面完整。"
echo
echo '```'
echo "\$ docker compose version: $(docker compose version --short 2>/dev/null || echo 'n/a')"
echo "\$ python: $(docker compose run --rm --no-deps -T api python -VV 2>/dev/null | tail -1)"
echo "\$ libgomp: $(docker compose run --rm --no-deps -T api python -c 'import lightgbm; print("lightgbm", lightgbm.__version__, "import OK")' 2>&1 | tail -1)"
echo '```'
echo
for target in cpbl.models.train:main cpbl.models.train_pitching:main; do
  echo "## \`$target\`"
  echo
  echo '```json'
  docker compose run --rm --no-deps -T \
    -v "$REPO_ROOT/$AUDIT_DIR:/app/$AUDIT_DIR:ro" \
    api python "/app/$AUDIT_DIR/audit_cli_help.py" --probe "$target" 2>/dev/null | tail -1
  echo '```'
  echo
done
