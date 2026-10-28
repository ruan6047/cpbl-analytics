#!/usr/bin/env bash
# LIFECYCLE: oneshot · #353 E1 重驗（正式站分批全量）期間的每秒取樣（規劃 r4 §5）；E1 結案後可刪
#
# ⛔ 正式站執行時段由 #353 PM 與共同主 PM 排；執行者只在 E0 可拋棄容器（cpbl353-*）上跑過。
#
# 用法（在開發機上跑；所有遠端指令經同一個 REMOTE 前綴）：
#   e1_sampler.sh preflight OUTDIR              磁碟餘裕＋工具可用性；資料碟 < MIN_FREE_GB ⇒ rc=1（停止）
#   e1_sampler.sh start     OUTDIR              背景啟動四路取樣（主機 PSI／vmstat／行程、DB wait_event）
#   e1_sampler.sh stop      OUTDIR              只對帶本次標記的行程逐一送 TERM（見下方「停止」）
#   e1_sampler.sh wait-autovacuum OUTDIR EPOCH  每 30s 查 PA 五表 last_autovacuum，全部晚於 EPOCH 即
#                                               rc=0；滿 AV_MAX_SECONDS（預設 1800）⇒ rc=3（報告註明）
#   start／stop／wait-autovacuum 需要同一組環境變數。
#
# 量測窗（規劃 r4 §5）：全量開始前 10 分鐘 start → 最後一批完成（PA_BATCH n/n 的 finished）→
#   wait-autovacuum OUTDIR <該 finished epoch> → stop。
#
# 環境變數：
#   VPS            ssh 目標（除非給 REMOTE）
#   DEPLOY_PATH    VPS 上的部署目錄（.env 所在；除非給 PG_EXEC）
#   REMOTE         遠端執行前綴，最後一個參數是指令字串（預設 "ssh -o BatchMode=yes $VPS"）
#   PG_EXEC        遠端 psql 指令（預設：cd $DEPLOY_PATH && . ./.env && docker exec -i -e PGOPTIONS=…
#                  -e PGAPPNAME prod_pg psql …）
#   API_CONTAINER  API 容器名（預設 prod_cpbl_api）；其 IP 用來辨認 API 來源連線
#   API_IPS        直接指定 API 來源位址（逗號分隔；給了就不查 docker inspect）
#   MAX_SECONDS    每一路取樣的保險絲（遠端 timeout 與 \watch c=；預設 7200）
#   MIN_FREE_GB    preflight 門檻（預設 8；推論值：WAL 約 6GB＋餘裕）
#
# 產出（全部以 epoch 秒記時，與哨兵 TSV 的 epoch 欄對齊；busybox date 沒有 %N 時只到整秒）：
#   psi.tsv     epoch  resource(cpu|memory|io)  /proc/pressure 原文（some/full 兩行併一行）
#   vmstat.tsv  epoch  vmstat 1 原文一行
#   proc.tsv    epoch  pidstat -h -u -r -d 1 原文一行（沒有 pidstat ⇒ top -b -d 1 每幀前 22 行；檔頭註明）
#   pg.tsv      epoch  role  wait_event_type  wait_event  state  n  max_query_age_s
#               只取 API 來源連線（role=api），依 (wait_event_type, wait_event, state) 彙總；
#               ⛔ 不留 query 文字、⛔ 不留位址。READ ONLY、statement_timeout 900ms。
#   autovacuum.tsv、preflight.txt、pids、run_id、*.err、stop.log
#
# 停止（為什麼這樣寫）：E0 的 postmaster 重啟三次（16:36 用過期 pid 清單 kill；16:45 修正前本工具的行程
# 群組 kill；16:50 修正後本工具 kill 自己帶標記的孤兒）。成因（已更正，見 #353 issuecomment-6464716650）：
# E0 把主機層取樣跑在 postgres 容器內，該容器 PID 1＝postmaster；取樣子行程成為孤兒後被 postmaster 收養，
# 之後一被 TERM，postmaster 就當成 backend crash 而整個重啟。這一點是用誘餌（setsid sleep）重現的。
# ⛔ 先前「pid 被 postgres backend 重用、TERM 打到 backend」的說法沒有證據、已收回；16:45 那次打到的是孤兒
# 還是 backend 無法判定。正式站：取樣在 VPS host 跑、host PID 1 是 systemd，不會有上述收養效應——這是推論，
# 未實測。即使如此，pid 清單在某一路提早結束後可能指向已被重用的 pid，行程群組 kill 會連帶打到同群組的任何
# 行程（含自己 setsid 的 backend），所以：
#   * ⛔ 不用行程群組 kill（kill -- -PGID、killpg）、⛔ 不用 pkill／killall、⛔ 不靠 pid 清單決定要殺誰。
#   * 遠端每一路都帶環境變數 E1S_TAG=e1s-<run_id>（子孫行程繼承）；stop 掃 /proc/*/environ，只對
#     E1S_TAG 完全相等的行程逐一 kill <pid>。start 時記下的 pid 只用來報告：已不帶標記者記 skip_stale。
#   * 本機端只對命令列含本次標記的 remote 行程逐一 kill。
#   * DB 端只對 application_name＝本次標記的 session 做 pg_terminate_backend（docker exec -i 沒有 tty，
#     外層結束不保證容器內 psql 結束；\watch c=N 另給次數上限）。
#   tests/test_e1_sampler_353.py 逐行釘住上述三條（每個 kill 都在同一行先比對標記）。
#   * ⛔ REMOTE 不得指向 postgres 容器本身（docker exec 進 prod_pg 跑主機層取樣）：該容器的 PID 1 是
#     postmaster，取樣行程成為孤兒後由它收養，被 TERM 結束時 postmaster 會當成 backend crash 而整個重啟
#     （E0 實測，連誘餌 sleep 都會觸發）。主機層取樣只在 VPS host 上跑；prod_pg 內只經 docker exec 跑 psql。
set -euo pipefail

cmd="${1:-}"; out="${2:-}"
[ -n "$cmd" ] && [ -n "$out" ] || { sed -n '2,50p' "$0"; exit 64; }
REMOTE="${REMOTE:-ssh -o BatchMode=yes ${VPS:?需要 VPS 或 REMOTE}}"
API_CONTAINER="${API_CONTAINER:-prod_cpbl_api}"
MAX_SECONDS="${MAX_SECONDS:-7200}"
MIN_FREE_GB="${MIN_FREE_GB:-8}"
PG_OPTS='-c default_transaction_read_only=on -c statement_timeout=900ms'
if [ -z "${PG_EXEC:-}" ]; then
  PG_EXEC="cd ${DEPLOY_PATH:?需要 DEPLOY_PATH 或 PG_EXEC} && set -a && . ./.env && docker exec -i -e PGOPTIONS='${PG_OPTS}' -e PGAPPNAME prod_pg psql -X -q -At -F '	' -U \"\$DB_USER\" -d \"\$DB_NAME\""
fi
PA_TABLES="'game_recap_source_revisions','game_recap_builds','game_plate_appearances','game_pa_events','game_pa_pitch_mappings'"

remote() {  # $1＝遠端指令字串；REMOTE 依空白切開（不經 eval）
  local -a pre
  read -r -a pre <<<"$REMOTE"
  "${pre[@]}" "$1"
}

api_ips() {
  if [ -n "${API_IPS:-}" ]; then printf '%s' "$API_IPS"; return; fi
  remote "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}},{{end}}' ${API_CONTAINER}" \
    | tr -d '\n' | sed 's/,$//'
}

case "$cmd" in
preflight)
  mkdir -p "$out"
  {
    echo "at_epoch=$(date +%s)"
    remote 'root=$(docker info -f "{{.DockerRootDir}}" 2>/dev/null || echo /var/lib/docker); [ -d "$root" ] || root=/; echo "docker_root=$root"; df -Pk "$root" | tail -1'
    remote 'command -v pidstat >/dev/null && echo proc_tool=pidstat || echo proc_tool=top; test -r /proc/pressure/cpu && echo psi=yes || echo psi=no; command -v vmstat >/dev/null && echo vmstat=yes || echo vmstat=no; command -v timeout >/dev/null && echo timeout=yes || echo timeout=no'
  } | tee "$out/preflight.txt"
  avail_kb="$(awk 'NF>=6 && $1 !~ /=/ && $4 ~ /^[0-9]+$/ {print $4}' "$out/preflight.txt" | tail -1)"
  [ -n "$avail_kb" ] || { echo "PREFLIGHT_FAIL 量不到磁碟餘裕（fail-closed：量不到不能讀成夠）" >&2; exit 2; }
  echo "avail_kb=${avail_kb}" | tee -a "$out/preflight.txt"
  if [ "$avail_kb" -lt $((MIN_FREE_GB * 1024 * 1024)) ]; then
    echo "PREFLIGHT_FAIL 資料碟剩餘 ${avail_kb}KB < ${MIN_FREE_GB}GB：停止（規劃 r4 §5）" >&2; exit 1
  fi
  ips="$(api_ips)"
  [ -n "$ips" ] || { echo "PREFLIGHT_FAIL 查不到 ${API_CONTAINER} 的位址（pg.tsv 會是空的）" >&2; exit 2; }
  echo "api_ip_count=$(tr ',' '\n' <<<"$ips" | grep -c .)" | tee -a "$out/preflight.txt"
  echo "PREFLIGHT_OK"
  ;;
start)
  mkdir -p "$out"
  [ ! -s "$out/pids" ] || { echo "已有 $out/pids（先 stop）" >&2; exit 2; }
  ips="$(api_ips)"
  [ -n "$ips" ] || { echo "查不到 API 來源位址；⛔ 不在量不到的情況下開始" >&2; exit 2; }
  inlist="$(tr ',' '\n' <<<"$ips" | sed "s/.*/'&'/" | paste -sd, -)"
  run_id="$(date +%s)_$$"
  tag="e1s-${run_id}"
  echo "$run_id" >"$out/run_id"
  # 遠端腳本經 stdin 交給 sh -s（避免多層引號）。E1S_TAG 由遠端命令列前綴設定，sh 與其所有子孫行程都帶著它；
  # 命令列字串本身也含 tag，所以本機端的 remote 行程（ssh／docker exec）可由命令列辨認。
  # 每一路先把自己的 pid 記到遠端 /tmp/<tag>-<名稱>.pid——只供 stop 報告 skip_stale，⛔ 不用來決定 kill 誰。
  rstream() {  # $1＝名稱 $2＝遠端腳本本體（stdin 是腳本本身，本體裡的指令不得讀 stdin）
    printf 'echo $$ >/tmp/%s-%s.pid\n%s\n' "$tag" "$1" "$2" \
      | remote "E1S_TAG=${tag} E1S_STREAM=$1 sh -s" >"$out/$1.tsv" 2>"$out/$1.err" &
    echo "$! $1" >>"$out/pids"
  }
  stamp='while IFS= read -r l; do printf "%s\t%s\n" "$(date +%s.%N | sed "s/\.$//")" "$l"; done'
  rstream psi "timeout ${MAX_SECONDS} sh -c 'while :; do t=\$(date +%s.%N | sed \"s/\\.\$//\"); for r in cpu memory io; do printf \"%s\\t%s\\t%s\\n\" \"\$t\" \"\$r\" \"\$(tr \"\\n\" \" \" </proc/pressure/\$r)\"; done; sleep 1; done' </dev/null"
  rstream vmstat "timeout ${MAX_SECONDS} vmstat -n 1 </dev/null | ${stamp}"
  rstream proc "if command -v pidstat >/dev/null; then echo '# tool=pidstat -h -u -r -d 1'; timeout ${MAX_SECONDS} pidstat -h -u -r -d 1 </dev/null | ${stamp}; else echo '# tool=top -b -d 1 (pidstat 不在；規劃 r4 §5 的替代)'; timeout ${MAX_SECONDS} top -b -d 1 </dev/null | awk '/^top -/{n=0} {n++; if (n<=22) {print; fflush()}}' | ${stamp}; fi"
  # DB：application_name＝tag（stop 時只 terminate 這個名字）；\watch c=N 給次數上限（psql ≥16；prod_pg 是 17）；
  # \watch 遇錯（例如 900ms 逾時）會結束，遠端迴圈重開，直到保險絲或 stop。
  sql="SELECT to_char(extract(epoch FROM clock_timestamp()), 'FM9999999999.000'), 'api', coalesce(wait_event_type, '-'), coalesce(wait_event, '-'), coalesce(state, '-'), count(*), coalesce(round(max(extract(epoch FROM clock_timestamp() - query_start))::numeric, 3), 0) FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND host(client_addr) IN (${inlist}) GROUP BY 3, 4, 5 ORDER BY 3, 4, 5 \\watch i=1 c=${MAX_SECONDS}"
  rstream pg "export PGAPPNAME=${tag}; end=\$((\$(date +%s) + ${MAX_SECONDS})); while [ \$(date +%s) -lt \$end ]; do printf '%s\\n' \"${sql//\"/\\\"}\" | ${PG_EXEC}; sleep 1; done"
  sleep 2
  echo "STARTED $(wc -l <"$out/pids" | tr -d ' ') streams tag=${tag} at $(date +%s)"
  ;;
stop)
  [ -s "$out/pids" ] && [ -s "$out/run_id" ] || { echo "沒有 $out/pids／run_id" >&2; exit 2; }
  tag="e1s-$(cat "$out/run_id")"
  {
    echo "stop_at=$(date +%s) tag=${tag}"
    # 1) 遠端。先報告 start 記下的 pid 是否仍屬本工具（不屬於＝已結束或被重用：skip_stale，不送訊號）；
    #    再掃 /proc，只對 E1S_TAG 完全相等的行程逐一 kill。stop 自己不帶 E1S_TAG。
    printf '%s\n' "tag=${tag}" \
      'for f in /tmp/${tag}-*.pid; do [ -s "$f" ] || continue; p=$(cat "$f"); n=${f##*/}; { tr "\0" "\n" <"/proc/$p/environ"; } 2>/dev/null | grep -qx "E1S_TAG=$tag" || echo "skip_stale=${n%.pid} pid=$p"; rm -f "$f"; done' \
      'for d in /proc/[0-9]*; do p=${d#/proc/}; [ "$p" = "$$" ] && continue; { tr "\0" "\n" <"$d/environ"; } 2>/dev/null | grep -qx "E1S_TAG=$tag" && kill -TERM "$p" 2>/dev/null && echo "killed pid=$p"; done; true' \
      | remote "sh -s" || echo "remote_stop_failed"
    # 2) DB：只 terminate application_name＝本次 tag 的 session。
    printf '%s\n' "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity WHERE application_name = '${tag}' AND pid <> pg_backend_pid();" \
      | remote "$PG_EXEC" | sed 's/^/terminated_sessions=/' || echo "pg_terminate_failed"
    # 3) 本機：只對命令列仍含本次 tag 的 remote 行程逐一 kill（pid 可能已被重用）。
    while read -r pid _; do
      ps -o command= -p "$pid" 2>/dev/null | grep -qF -- "E1S_TAG=${tag}" && kill -TERM "$pid" 2>/dev/null && echo "killed_local pid=$pid"
    done <"$out/pids"
    sleep 2
    left="$(printf '%s\n' "SELECT count(*) FROM pg_stat_activity WHERE application_name = '${tag}';" | remote "$PG_EXEC" 2>/dev/null || echo '?')"
    rem="$(printf '%s\n' "tag=${tag}" 'n=0; for d in /proc/[0-9]*; do { tr "\0" "\n" <"$d/environ"; } 2>/dev/null | grep -qx "E1S_TAG=$tag" && n=$((n+1)); done; echo $n' | remote "sh -s" 2>/dev/null || echo '?')"
    echo "pg_sessions_left=${left} remote_tagged_left=${rem}"
  } | tee "$out/stop.log"
  mv "$out/pids" "$out/pids.stopped"
  echo "STOPPED at $(date +%s)"
  ;;
wait-autovacuum)
  since="${3:?需要最後一批完成的 epoch}"
  max="${AV_MAX_SECONDS:-1800}"; t0="$(date +%s)"
  q="SELECT relname, coalesce(to_char(extract(epoch FROM last_autovacuum), 'FM9999999999.000'), '-') FROM pg_stat_user_tables WHERE schemaname = 'cpbl' AND relname IN (${PA_TABLES}) ORDER BY 1;"
  while :; do
    now="$(date +%s)"
    rows="$(printf '%s\n' "$q" | remote "$PG_EXEC")"
    printf '%s\n' "$rows" | sed "s/^/${now}	/" >>"$out/autovacuum.tsv"
    if [ "$(printf '%s\n' "$rows" | awk -F'\t' -v s="$since" '$2 != "-" && $2+0 > s+0' | wc -l | tr -d ' ')" = 5 ]; then
      echo "AUTOVACUUM_DONE at ${now}"; exit 0
    fi
    if [ $((now - t0)) -ge "$max" ]; then echo "AUTOVACUUM_TIMEOUT after ${max}s（報告註明）"; exit 3; fi
    sleep 30
  done
  ;;
*) sed -n '2,50p' "$0"; exit 64 ;;
esac
