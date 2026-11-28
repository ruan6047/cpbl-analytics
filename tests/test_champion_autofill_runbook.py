"""#469 審核第 1 輪 finding 2／3：Runbook〈首次安裝與回復程序〉的停止點與回復條件。

finding 2：舊版把「裝 unit → 入口檢查 → 首次執行 → 啟用 timer」寫成一段可整段貼上的區塊，前面失敗 shell 照跑，
timer 仍被啟用。現版每步一個 ``set -euo pipefail`` 子 shell、靠上一步的通過標記串起來。這裡用**替身命令**
（docker／systemctl／journalctl／install／psql 全換成只記錄的 shell 函式）把各步**整段一次貼上**實跑：
任何一步失敗都不得走到 ``systemctl enable``。負控制：同一套替身跑舊版區塊，必須看得到它照樣啟用 timer
（證明這個演練抓得到原缺陷）。

finding 3：回復要先確認寫入已停（容器內入口程序已不在）才還原；刪除條件是本次寫入的 ``verified_at``（＋總教練
``note``），⛔ 不以年份當條件。

⛔ 不連 VPS、不連 DB、不執行任何 ``cpbl-*`` 入口；替身只在暫存目錄寫檔。R2 的 psql ``\\if`` 交易邏輯
需要真 PostgreSQL，本檔只做靜態檢查（未實跑）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cpbl.ingest import championships as ch

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "AI_RUNBOOK.md"
SECTION_HEAD = "### 新球季冠軍自動補列（#469）"
INSTALL = [f"WP3-{n}" for n in range(7)]
ROLLBACK = [f"ROLLBACK-{n}" for n in range(1, 5)]
# 每步的通過標記（上一步的標記＝下一步的第一個檢查）。
MARKERS = {"WP3-1": "1-backup.ok", "WP3-2": "2-entry.ok", "WP3-3": "3-units.ok", "WP3-4": "4-run.ok",
           "WP3-5": "5-readback.ok", "WP3-6": "6-timer.ok", "ROLLBACK-1": "r1-stopped.ok",
           "ROLLBACK-2": "r2-deleted.ok", "ROLLBACK-3": "r3-members.ok", "ROLLBACK-4": "r4-verified.ok"}
GATES = {"WP3-2": "1-backup.ok", "WP3-3": "2-entry.ok", "WP3-4": "3-units.ok", "WP3-5": "4-run.ok",
         "WP3-6": "5-readback.ok", "ROLLBACK-1": "1-backup.ok", "ROLLBACK-2": "r1-stopped.ok",
         "ROLLBACK-3": "r2-deleted.ok", "ROLLBACK-4": "r3-members.ok"}

# 審核第 1 輪受審版本（9f9fff9b）的安裝區塊原文：負控制用。
OLD_INSTALL_BLOCK = """\
install -m 0644 ops/vps/cpbl469-champion-autofill.service ops/vps/cpbl469-champion-autofill.timer /etc/systemd/system/
systemctl daemon-reload
docker exec prod_cpbl_api sh -c 'command -v cpbl-champion-autofill'   # 入口存在（新映像已部署）才往下
systemctl start cpbl469-champion-autofill.service && journalctl -u cpbl469-champion-autofill.service -n 20 --no-pager
systemctl enable --now cpbl469-champion-autofill.timer && systemctl list-timers cpbl469-champion-autofill.timer
"""


def _section() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index(SECTION_HEAD)
    end = text.find("\n### ", start + len(SECTION_HEAD))
    return text[start:end if end != -1 else len(text)]


def _blocks() -> dict[str, str]:
    """``# WP3-n``／``# ROLLBACK-n`` 開頭的 bash 區塊，去掉 fence 縮排（＝操作者實際貼上的內容）。"""
    out: dict[str, str] = {}
    for m in re.finditer(r"^( *)```bash\n(.*?)\n\1```", _section(), re.S | re.M):
        indent = len(m.group(1))
        lines = [ln[indent:] if ln.startswith(" " * indent) else ln for ln in m.group(2).split("\n")]
        body = "\n".join(lines)
        tag = re.match(r"# (WP3-\d|ROLLBACK-\d)\n", body)
        if tag:
            assert tag.group(1) not in out, f"區塊標籤重複：{tag.group(1)}"
            out[tag.group(1)] = body
    return out


# =========================================================================== 靜態


def test_install_and_rollback_steps_are_separate_blocks_in_plan_order():
    blocks = _blocks()
    assert list(blocks) == INSTALL + ROLLBACK


@pytest.mark.parametrize("tag", [t for t in INSTALL + ROLLBACK if t != "WP3-0"])
def test_each_step_is_an_errexit_subshell_gated_on_the_previous_marker(tag):
    body = _blocks()[tag].split("\n", 1)[1].lstrip()
    assert body.startswith("( set -euo pipefail"), f"{tag} 必須是 set -euo pipefail 子 shell"
    if tag in GATES:
        first = body.split("\n", 1)[0]
        assert f'test -f "$BK/{GATES[tag]}"' in first, f"{tag} 第一行必須檢查上一步標記 {GATES[tag]}"
    tail = body.rstrip().rsplit("\n", 1)[-1]
    assert f'touch "$BK/{MARKERS[tag]}"' in tail and tail.endswith(")"), f"{tag} 最後一行才寫自己的標記"


def test_only_the_last_step_enables_the_timer_and_only_after_readback():
    blocks = _blocks()
    enabling = [t for t, b in blocks.items() if re.search(r"systemctl enable\b", b)]
    starting = [t for t, b in blocks.items() if re.search(r"systemctl start\b", b)]
    assert enabling == ["WP3-6"] and starting == ["WP3-4"]
    assert GATES["WP3-6"] == MARKERS["WP3-5"]


def test_no_negated_command_relies_on_errexit():
    """bash：``! cmd`` 失敗時 ``set -e`` 不會中止（反轉回傳值的指令豁免）；停止條件必須寫成 if … exit。"""
    for tag, body in _blocks().items():
        assert not re.search(r"^\s*! ", body, re.M), f"{tag} 有 '! cmd'：set -e 不會因它停下"


def test_runbook_literals_match_the_code_constants():
    """讀回種子與 R2 刪除條件用的 ``note`` 必須和程式寫入的值逐字相同（否則讀回永遠不符／刪除永遠 0 列）。"""
    blocks = _blocks()
    assert blocks["WP3-5"].count(ch.MANAGER_NOTE) == 1
    assert blocks["ROLLBACK-2"].count(ch.MANAGER_NOTE) == 1
    assert ch.BOX_URL.format(year=2026, kind="C", sno=6) in blocks["WP3-5"]
    assert ch.TEAM_PAGE_URL.format(code="AAA011") in blocks["WP3-5"]


def test_rollback_deletes_only_rows_written_by_this_run():
    deletes = re.findall(r"DELETE FROM cpbl\.(\w+) WHERE ([^)]*?) RETURNING", _section())
    assert sorted(t for t, _ in deletes) == ["championship_managers", "championships"]
    for table, where in deletes:
        assert "year = 2026" in where and "verified_at = :'va'" in where, f"{table} 刪除條件缺 verified_at：{where}"
    assert "note = :'note'" in dict(deletes)["championship_managers"]
    r2 = _blocks()["ROLLBACK-2"]
    assert "SELECT (:m = :exp_m AND :c = :exp_c)::int AS ok \\gset" in r2, "刪除列數必須等於步驟 4 記下的預期值"
    assert r2.index("\\if :ok") < r2.index("COMMIT;") < r2.index("\\else") < r2.index("ROLLBACK;") \
        < r2.index("RAISE EXCEPTION") < r2.index("\\endif")


def test_rollback_confirms_the_container_entry_is_gone_before_restoring():
    r1 = _blocks()["ROLLBACK-1"]
    assert r1.index("systemctl disable --now") < r1.index("systemctl stop") < r1.index("if alive; then")
    assert r1.index("if alive; then") < r1.index('touch "$BK/r1-stopped.ok"')


# =========================================================================== 替身演練（實跑 bash）

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash")

SEED_CHAMP = ("AAA011|ACN011|AAA011|" + ch.BOX_URL.format(year=2026, kind="C", sno=6) + "|verified|1")
SEED_MGR = ("葉君璋|AAA011|" + ch.TEAM_PAGE_URL.format(code="AAA011") + "|verified|" + ch.MANAGER_NOTE + "|1")
VA = "2026-12-01T04:10:00.000001+00:00"


def _snapshot(*, after: bool, champ: str = SEED_CHAMP, other_write: bool = False) -> str:
    hist_c, hist_m, hist_p = "2025\tAJL011", "2025\t某教練", "P1\t2025\tAJL011\tplayer"
    rows_c = [hist_c] + (["2026\tAAA011"] if after else [])
    rows_m = [hist_m] + (["2026\t葉君璋"] if after else [])
    rows_p = [hist_p] + (["P2\t2026\tAAA011\tplayer"] if after else [])
    tup = ["championships|" + ("2" if after else "1"), "games|" + ("9" if other_write else "5")]
    parts = ["@@championships.copy", *rows_c, "@@championship_managers.copy", *rows_m,
             "@@championship_members.copy", *rows_p, "@@counts.txt",
             f"championships|{len(rows_c)}", f"championship_managers|{len(rows_m)}",
             f"championship_members|{len(rows_p)}", "@@tup.txt", *tup,
             "@@champion-2026.txt", *([champ] if after else []),
             "@@manager-2026.txt", *([SEED_MGR] if after else []),
             "@@members-2026.txt", "1" if after else "0"]
    return "\n".join(parts) + "\n"


STUBS = r"""
set +e
log() { printf '%s\n' "$*" >> "$LOG"; }
install() { log "install $*"; }
sleep() { :; }
rm() { case "$*" in *"/etc/systemd/"*) log "rm $*" ;; *) command rm "$@" ;; esac; }
if ! command -v sha256sum >/dev/null 2>&1; then sha256sum() { shasum -a 256 "$@"; }; fi
docker() {
  log "docker $*"
  if [ "$1 $2" = "exec -i" ] && [ "$4 $5" = "python -c" ]; then "$PY" -c "$6"; return; fi
  case "$*" in
    "exec prod_cpbl_api sh -c command -v cpbl-champion-autofill")
      if [ -n "${FAIL_ENTRY:-}" ]; then return 1; fi; echo /usr/local/bin/cpbl-champion-autofill ;;
    "exec prod_cpbl_api python -c "*) if [ -n "${ALIVE:-}" ]; then echo "running: [42]"; return 0; fi; return 1 ;;
    *) return 0 ;;
  esac
}
systemctl() {
  log "systemctl $*"
  case "$1" in
    start) touch "$STATE/started"; if [ -n "${FAIL_START:-}" ]; then return 1; fi; touch "$STATE/ran" ;;
    show) echo inv-1 ;;
    is-enabled) if [ -e "$STATE/enabled" ]; then echo enabled; else echo disabled; return 1; fi ;;
    enable) touch "$STATE/enabled" ;;
    is-active) echo inactive; return 3 ;;
    list-timers) if [ -e "$STATE/enabled" ]; then echo "next cpbl469-champion-autofill.timer"; fi ;;
    *) return 0 ;;
  esac
}
journalctl() {
  log "journalctl $*"
  echo "2026-12-01 INFO cpbl.champ | start"
  if [ -n "${MIGRATE:-}" ]; then echo "2026-12-01 INFO cpbl.db | migrate(): applying 001_init.sql"; fi
  if [ -n "${FAIL_START:-}" ]; then
    echo '{"action": "error", "error": "RuntimeError", "manager": null, "stage": "members"}'
  else
    echo "{\"action\": \"inserted\", \"manager\": \"inserted\", \"members\": \"rebuilt\", \"verified_at\": \"$VA\", \"year\": 2026}"
  fi
}
"""

PG_STUB = r"""
pg() {
  log "pg $*"
  input=$(cat)
  printf '%s\n----\n' "$input" >> "$LOG.pgin"
  case "$input" in
    *"@@championships.copy"*) if [ -e "$STATE/ran" ]; then cat "$STATE/after.txt"; else cat "$STATE/before.txt"; fi ;;
  esac
}
"""


def _drill(tmp_path: Path, script_blocks: list[str], *, env_extra: dict[str, str] | None = None,
           after: str | None = None, written: str | None = None, with_setup: bool = True) -> tuple[str, Path]:
    state = tmp_path / "state"
    bk = tmp_path / "bk"
    state.mkdir()
    (state / "before.txt").write_text(_snapshot(after=False), encoding="utf-8")
    (state / "after.txt").write_text(after if after is not None else _snapshot(after=True), encoding="utf-8")
    if written is not None:
        bk.mkdir()
        (bk / "written").write_text(written, encoding="utf-8")
    log = tmp_path / "log"
    blocks = _blocks()
    setup = [STUBS, blocks["WP3-0"], PG_STUB] if with_setup else [STUBS]
    script = "\n".join(setup + script_blocks) + "\n"
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path), "LOG": str(log), "STATE": str(state),
           "BK": str(bk), "PY": sys.executable, "VA": VA, **(env_extra or {})}
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-c", script], env=env, capture_output=True,
                          text=True, timeout=60, check=False)
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    return calls + "\n#STDOUT\n" + proc.stdout + "\n#STDERR\n" + proc.stderr, bk


def _install_steps() -> list[str]:
    blocks = _blocks()
    return [blocks[t] for t in INSTALL[1:]]


@needs_bash
def test_drill_happy_path_reaches_the_timer_once(tmp_path):
    out, bk = _drill(tmp_path, _install_steps())

    assert out.count("systemctl enable") == 1, out
    assert all((bk / MARKERS[t]).exists() for t in INSTALL[1:]), out
    assert (bk / "written").read_text(encoding="utf-8").split() == [VA, "1", "1"]


@needs_bash
@pytest.mark.parametrize(("env_extra", "after", "reached"), [
    ({"FAIL_ENTRY": "1"}, None, "2-entry.ok"),
    ({"FAIL_START": "1"}, None, "4-run.ok"),
    ({"MIGRATE": "1"}, None, "4-run.ok"),
    ({}, _snapshot(after=True, champ="AAA011||AAA011|x|verified|1"), "5-readback.ok"),
    ({}, _snapshot(after=True, other_write=True), "5-readback.ok"),
], ids=["entry-missing", "service-fails", "migrate-in-output", "readback-mismatch", "other-table-written"])
def test_drill_pasting_every_step_at_once_never_enables_the_timer_after_a_failure(tmp_path, env_extra, after, reached):
    """審核者的重現形狀：整段一次貼上、中間某步失敗。"""
    out, bk = _drill(tmp_path, _install_steps(), env_extra=env_extra, after=after)

    assert "systemctl enable" not in out, out
    assert not (bk / "6-timer.ok").exists()
    assert not (bk / reached).exists(), f"失敗的那一步不得寫出 {reached}"
    if "FAIL_ENTRY" in env_extra:
        assert "systemctl start" not in out and "install " not in out, out


@needs_bash
def test_drill_negative_control_old_block_enables_the_timer_despite_failures(tmp_path):
    """負控制：受審版本的單一區塊在入口檢查與首次執行都失敗時，仍會啟用 timer。"""
    out, _ = _drill(tmp_path, [OLD_INSTALL_BLOCK], env_extra={"FAIL_ENTRY": "1", "FAIL_START": "1"},
                    with_setup=False)

    assert "systemctl start" in out and "systemctl enable --now" in out, out


@needs_bash
def test_drill_service_retry_is_capped_at_one(tmp_path):
    step4 = _blocks()["WP3-4"]
    pre = [_blocks()[t] for t in ("WP3-1", "WP3-2", "WP3-3")]

    out, bk = _drill(tmp_path, pre + [step4, step4, step4], env_extra={"FAIL_START": "1"})

    assert out.count("systemctl start") == 2, out
    assert (bk / "run.attempts").read_text(encoding="utf-8").strip() == "2"


@needs_bash
def test_drill_rollback_stops_while_the_entry_still_runs_in_the_container(tmp_path):
    blocks = _blocks()
    out, bk = _drill(tmp_path, [blocks["WP3-1"]] + [blocks[t] for t in ROLLBACK], env_extra={"ALIVE": "1"},
                     written=f"{VA} 1 1\n")

    assert (bk / "1-backup.ok").exists() and not (bk / "r1-stopped.ok").exists(), out
    assert out.count("pg ") == 1, "容器內入口還在跑就不得對 DB 做任何還原（唯一一次 pg 是步驟 1 備份）"
    assert "DELETE" not in (tmp_path / "log.pgin").read_text(encoding="utf-8"), "容器內入口還在跑就不得對 DB 做任何還原"
    assert "rm /etc/systemd/" not in out


@needs_bash
def test_drill_rollback_passes_this_runs_verified_at_and_expected_counts(tmp_path):
    blocks = _blocks()
    out, bk = _drill(tmp_path, [blocks["WP3-1"]] + [blocks[t] for t in ROLLBACK], written=f"{VA} 1 1\n")

    assert (bk / "r4-verified.ok").exists(), out
    assert f"pg -v va={VA} -v exp_c=1 -v exp_m=1 -v note={ch.MANAGER_NOTE}" in out, out
    pgin = (tmp_path / "log.pgin").read_text(encoding="utf-8")
    assert "TRUNCATE cpbl.championship_members;\nCOPY cpbl.championship_members FROM STDIN;\n" \
           "P1\t2025\tAJL011\tplayer\n\\.\nCOMMIT;" in pgin


@needs_bash
def test_drill_rollback_skips_the_delete_when_nothing_was_written(tmp_path):
    blocks = _blocks()
    out, bk = _drill(tmp_path, [blocks["WP3-1"]] + [blocks[t] for t in ROLLBACK], written="- 0 0\n")

    assert (bk / "r2-deleted.ok").exists(), out
    assert "-v exp_c=" not in out
    assert "DELETE" not in (tmp_path / "log.pgin").read_text(encoding="utf-8")
    assert "nothing written by this run" in out


@needs_bash
def test_drill_failed_first_run_then_rollback_deletes_nothing(tmp_path):
    """步驟 4 失敗（交易已回滾、JSON 沒有 verified_at）後照 R1–R4 回復：``written`` 由步驟 4 實際產出，
    R2 不得送出任何 DELETE（佔位值被 ``read`` 誤讀成時間戳就會送出）。"""
    blocks = _blocks()
    steps = [blocks[t] for t in ("WP3-1", "WP3-2", "WP3-3", "WP3-4")] + [blocks[t] for t in ROLLBACK]

    out, bk = _drill(tmp_path, steps, env_extra={"FAIL_START": "1"})

    assert not (bk / "4-run.ok").exists() and (bk / "r4-verified.ok").exists(), out
    assert "DELETE" not in (tmp_path / "log.pgin").read_text(encoding="utf-8"), out
    assert "nothing written by this run" in out
