"""排程 shell 的 `--help` 守衛（DEV-SCRIPT-INVENTORY1，需求方裁定：提前處置）。

盤點原本把這幾支具名列進 `script_inventory.HELP_SAFETY_ALLOWLIST`（＝已知危害、
具名放行）。需求方推翻該處置：它們與 `sync_deep_tm_prod.py` **同級**——探索動作即
造成損害——而破壞半徑更大：後者 DROP 一張表，`refresh-cpbl-prod.sh` 是**整條生產
同步鏈**（爬官網 → 備份並 upsert production → VPS 重跑訓練）。

判準與 `tests/test_cli_help_guard.py` 同一條，不另立第二套：
**argv 必須在主流程觸及任何副作用之前被解析；`--help` 要給答案（exit 0），未知參數
要被拒絕（非零退出）而不是被忽略。** CLI 側用執行期密封探針證明，shell 沒有
Python 那層可以 monkeypatch 的出口，改以**副本 ＋ 假樁**證明，形狀沿用
`tests/test_scrape_daily.py`（假 `docker`／`uv`）與 `tests/test_prod_sync_revision_seq.py`
（假 `ssh`，`VPS` 指向 `.invalid` 保留網域當 fail-safe）。

## 三個不得妥協的設計

1. **一律跑副本，不跑版控樹上的檔案。** 本卡紅線是「不得執行任何 `scripts/` 下的
   腳本，含加了守衛之後的 `--help`」。所有執行都在 `tmp_path` 的假 repo 裡對
   `shutil.copy2` 出來的副本進行（不是 symlink——symlink 執行到的仍是版控樹上那個
   inode）。變異檢驗同理。
2. **證據是「零副作用」而不是「有守衛字樣」。** `script_inventory.help_safety()` 的
   shell 判準是整檔正則，只看得到守衛在不在、看不到它在哪；位置由本檔的靜態斷言
   （守衛之前不得有任何副作用）＋執行期斷言（`--help` 時零假樁呼叫、零檔案產出）
   共同證明。
3. **每條都附負控制。** 把守衛從副本上拿掉後同一條測試必須變紅，否則它只是剛好會過。

## 為什麼 `weekly-box-revisions.sh` 不在這裡

它與這三支同性質、同樣沒有守衛，但它是 `#132` 的資源（該卡同時持有
`scripts/refresh_status.py` 與 `src/cpbl/api/routers/info.py`）。本卡改它等於動另一
張活卡的檔案，故留在 `HELP_SAFETY_ALLOWLIST` 具名放行，去向寫在該條目上。
`test_every_safe_shell_is_covered_here` 保證這個缺口不會靜默擴大。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import script_inventory as si

ROOT = Path(__file__).resolve().parents[1]

# 本卡處置的四支。`weekly-box-revisions.sh` 見檔頭說明（#132 資源，射程外）。
#
# `backup-prod-db.sh` 是後補的第四支，而它**不是**從 allowlist 撤下來的——它從來
# 沒進過那張表：舊判準問「寫不寫 DB」，而它 `pg_dump` 對 DB 唯讀。實測 `--help`
# 會 ssh 進生產跑整庫 dump，然後 exit 0、產出備份、`rm -f` 掉輪替視窗最舊的那份
# （7 份視窗實測：08-08 消失、08-15 補進來）。判準已一併加寬為「高後果」。
GUARDED_SHELLS = (
    "scripts/backup-prod-db.sh",
    "scripts/refresh-cpbl-prod.sh",
    "scripts/scrape-daily.sh",
    "scripts/weekly-game-pitches.sh",
)

# 假樁攔截的外部指令。`cat`／`mkdir`／`date` 刻意**不攔**：留真的才能讓「守衛沒擋住時
# 真的會在假 repo 裡建出 logs/」成為可觀測證據，而 `--help` 的 heredoc 也要真的 `cat`。
STUBBED_COMMANDS = ("uv", "docker", "ssh", "curl", "psql", "pg_dump", "pg_restore")

# 副作用的靜態近似：守衛之前出現任何一個都算破功。刻意寬（`uv` 連 `command -v uv`
# 都會命中），因為誤判成「更早就有副作用」只會讓斷言更嚴格，不會放水。
EFFECT_RE = re.compile(r"\b(uv|docker|ssh|curl|psql|pg_dump|mkdir|tee|rm|python3)\b")

# `--help` 輸出的形狀契約——「拒絕」不算答案，一個想知道它在做什麼的人要拿到：
# 這支在做什麼、會寫什麼、正常怎麼呼叫。
USAGE_SECTIONS = ("在做什麼", "會寫什麼", "怎麼呼叫")


# ------------------------------------------------------------------ 假 repo


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _fake_repo(tmp_path: Path, script_rel: str, *, drop_guard: bool = False) -> dict:
    """把待測腳本**複製**進 tmp 假 repo，外部指令全部換成會留痕的假樁。

    假樁一律非零退出：`--help` 應該一個都碰不到；真的碰到就當場中止，
    不會有第二個假樁被呼叫，也不會有任何真實主機／容器被接觸。
    """
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    fake_bin = tmp_path / "bin"
    calls = tmp_path / "calls"
    scripts.mkdir(parents=True)
    fake_bin.mkdir()
    calls.mkdir()

    shutil.copy2(ROOT / script_rel, scripts / Path(script_rel).name)
    if drop_guard:
        target = scripts / Path(script_rel).name
        target.write_text(_without_guard(target.read_text(encoding="utf-8")), encoding="utf-8")

    stub = (
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "out = Path(os.environ['STUB_CALL_DIR'])\n"
        "name = Path(sys.argv[0]).name\n"
        "(out / ('%s-%03d.json' % (name, len(list(out.glob('*.json'))))))"
        ".write_text(json.dumps({'cmd': name, 'argv': sys.argv[1:]}), encoding='utf-8')\n"
        "sys.exit(97)\n"
    )
    for name in STUBBED_COMMANDS:
        _write_exec(fake_bin / name, stub)

    return {"repo": repo, "script": scripts / Path(script_rel).name, "bin": fake_bin,
            "calls": calls}


_USAGE_BODY_RE = re.compile(r"^usage\(\) \{\n.*?^\}\n", re.S | re.M)
_GUARD_BLOCK_RE = re.compile(r"^if \[ \"\$#\" -gt 0 \]; then\n.*?^fi\n", re.S | re.M)


def _without_usage_body(source: str) -> str:
    """把 `usage()` 函式本體從掃描面剔除——heredoc 裡的說明文字不是可執行碼。"""
    stripped = _USAGE_BODY_RE.sub("", source)
    assert stripped != source, "找不到 usage() 定義"
    return stripped


def _without_guard(source: str) -> str:
    """變異檢驗：整段 argv 守衛（`usage()` 定義 ＋ `if [ "$#" -gt 0 ]` 區塊）拿掉。"""
    mutated = _GUARD_BLOCK_RE.sub("", _without_usage_body(source))
    assert _GUARD_BLOCK_RE.search(source), "變異檢驗沒有真的拿掉守衛——負控制會變成空斷言"
    return mutated


def _run(harness: dict, argv: list[str], **extra_env: str) -> tuple[subprocess.CompletedProcess,
                                                                   list[dict]]:
    env = {
        "PATH": f"{harness['bin']}:/usr/bin:/bin",
        "HOME": str(harness["repo"].parent / "home"),
        "STUB_CALL_DIR": str(harness["calls"]),
        # fail-safe：假樁沒攔到也連不上任何真實主機／容器／端點。
        "VPS": "stub@harness.invalid",
        "LOCAL_DB": "stub-nonexistent-container",
        "DEPLOY_PATH": "/nonexistent/stub-deploy",
        "API_INFO_URL": "http://127.0.0.1:1/api/info",
        "REFRESH_LOCK_DIR": str(harness["repo"].parent / "lock"),
        # ⚠️ fail-safe，不是裝飾：`backup-prod-db.sh` 的 BACKUP_DIR 預設是
        # `$HOME/Library/Application Support/cpbl-analytics/backups`——**真實的輪替
        # 視窗**。負控制會在拿掉守衛的情況下跑主流程，指到假 repo 裡才不會有任何
        # 一條路徑通往真的備份目錄。指進 repo 內另有好處：產物落在 `_files_created`
        # 看得到的範圍。
        "BACKUP_DIR": str(harness["repo"] / "backups"),
        **extra_env,
    }
    result = subprocess.run(
        ["/bin/bash", str(harness["script"]), *argv],
        cwd=harness["repo"], env=env, text=True, capture_output=True,
        stdin=subprocess.DEVNULL, check=False,
    )
    recorded = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(harness["calls"].glob("*.json"))]
    return result, recorded


def _files_created(repo: Path) -> list[str]:
    """假 repo 裡除了腳本副本以外多出來的東西——`--help` 不該產出任何一項。"""
    return sorted(
        str(p.relative_to(repo)) for p in repo.rglob("*")
        if p.is_file() and p.parent != repo / "scripts"
    )


# =========================================================== 執行期：零副作用


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_help_answers_and_touches_nothing(script_rel: str, tmp_path: Path) -> None:
    """`--help` 要 exit 0、印出用法，且**一個外部指令都不呼叫、一個檔案都不產出**。"""
    harness = _fake_repo(tmp_path, script_rel)
    result, calls = _run(harness, ["--help"])

    assert result.returncode == 0, f"stderr={result.stderr}"
    assert not calls, f"--help 呼叫了外部指令：{calls}"
    assert not _files_created(harness["repo"]), _files_created(harness["repo"])
    assert Path(script_rel).name in result.stdout
    for section in USAGE_SECTIONS:
        assert section in result.stdout, f"用法缺少「{section}」段：拒絕不是答案"


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_short_help_flag_behaves_the_same(script_rel: str, tmp_path: Path) -> None:
    harness = _fake_repo(tmp_path, script_rel)
    result, calls = _run(harness, ["-h"])

    assert result.returncode == 0
    assert not calls
    assert "在做什麼" in result.stdout


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_unknown_argument_is_refused_not_ignored(script_rel: str, tmp_path: Path) -> None:
    """未知參數＝呼叫端誤會了介面。靜默忽略只會讓誤會延續，故 64（EX_USAGE）退出。"""
    harness = _fake_repo(tmp_path, script_rel)
    result, calls = _run(harness, ["--dry-run"])

    assert result.returncode == 64, f"stdout={result.stdout} stderr={result.stderr}"
    assert not calls, f"未知參數仍然跑了主流程：{calls}"
    assert not _files_created(harness["repo"])
    assert "--dry-run" in result.stderr


# ================================================ 執行期：負控制（拿掉守衛就要紅）


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_negative_control_removing_the_guard_kills_the_answer(
    script_rel: str, tmp_path: Path,
) -> None:
    """守衛拿掉後 `--help` 不再是 exit 0 ＋ 用法——證明上面那條不是剛好會過。"""
    harness = _fake_repo(tmp_path, script_rel, drop_guard=True)
    result, _ = _run(harness, ["--help"])

    assert not (result.returncode == 0 and "在做什麼" in result.stdout), (
        "拿掉守衛後 `--help` 仍然回答得出來——本檔的正控制是空的")


@pytest.mark.parametrize(
    "script_rel",
    ["scripts/backup-prod-db.sh",
     "scripts/refresh-cpbl-prod.sh",
     "scripts/weekly-game-pitches.sh"],
    ids=lambda s: Path(s).name,
)
def test_negative_control_unguarded_help_really_reaches_the_main_flow(
    script_rel: str, tmp_path: Path,
) -> None:
    """守衛拿掉後 `--help` 真的會落進主流程——即這三支修的是實害，不是體感。

    `scrape-daily.sh` 不在這條的參數化裡：它自 `a0b6cfd`（2026-07-17）起就有
    `參數只接受 fast` 的檢查，`--help` 一直是 exit 64 而非「跑完整每日爬取」。
    清冊原本記載的理由（「把 `--help` 當成模式字串吞掉」）**與事實不符**，本輪
    已隨條目撤除一併修正；那一支修的是「拒絕 → 答案」，不是「開跑 → 不開跑」。
    """
    harness = _fake_repo(tmp_path, script_rel, drop_guard=True)
    result, calls = _run(harness, ["--help"])

    touched = calls or _files_created(harness["repo"])
    assert touched, (
        f"拿掉守衛後 `--help` 沒有碰到任何東西（rc={result.returncode}）——"
        "那代表本檔的假樁面沒有涵蓋這支的副作用出口，證據力是假的")


# ==================================================== 靜態：守衛之前不得有副作用


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_nothing_effectful_happens_before_the_guard(script_rel: str) -> None:
    """守衛必須留在檔案最前面。往下移就等於沒有——而整檔正則看不出來這件事。

    掃描面先剔除 `usage()` 本體（heredoc 裡的說明文字提到 `ssh`／`docker` 不是副作用），
    再剔除註解，剩下的就是守衛生效前**真的會執行**的程式碼。
    """
    source = _without_usage_body((ROOT / script_rel).read_text(encoding="utf-8"))
    lines = source.splitlines()
    guard_open = next(i for i, line in enumerate(lines)
                      if line.startswith('if [ "$#" -gt 0 ]; then'))

    before = [line for line in lines[:guard_open]
              if line.strip() and not line.lstrip().startswith("#")]
    offenders = [line for line in before if EFFECT_RE.search(line)]

    assert not offenders, f"{script_rel} 的守衛之前就有副作用：{offenders}"


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_guard_sits_at_top_level_not_inside_a_function(script_rel: str) -> None:
    """守衛區塊縮排為 0＝頂層；掉進函式裡就只有被呼叫時才生效。"""
    lines = (ROOT / script_rel).read_text(encoding="utf-8").splitlines()
    guard_open = next(i for i, line in enumerate(lines)
                      if line.startswith('if [ "$#" -gt 0 ]; then'))
    guard_close = next(i for i, line in enumerate(lines) if i > guard_open and line == "fi")

    assert lines[guard_open] == lines[guard_open].lstrip()
    assert lines[guard_close] == "fi"


# ======================================= scrape-daily.sh → refresh-cpbl-prod.sh


def _daily_harness(tmp_path: Path) -> dict:
    """`tests/test_scrape_daily.py` 的假 repo 手法，外加一個會**記錄 argv 與 env**
    的假 `refresh-cpbl-prod.sh`——每日鏈實際送出的呼叫形狀就從這裡取得。

    ⚠️ 假樁必須是 POSIX sh：呼叫點寫的是 `bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh"`，
    **明確指定直譯器**，shebang 不會被採用。
    """
    harness = _fake_repo(tmp_path, "scripts/scrape-daily.sh")
    scripts = harness["repo"] / "scripts"
    shutil.copy2(ROOT / "scripts" / "refresh_status.py", scripts / "refresh_status.py")

    _write_exec(harness["bin"] / "docker", "#!/bin/sh\nprintf 'cpbl-analytics-db-1\\n'\n")
    _write_exec(harness["bin"] / "uv", "#!/bin/sh\nexit 0\n")
    _write_exec(
        scripts / "refresh-cpbl-prod.sh",
        "#!/bin/sh\n"
        ': > "$SYNC_CALL_FILE"\n'
        "printf 'SKIP_SCRAPE=%s\\n' \"${SKIP_SCRAPE:-}\" >> \"$SYNC_CALL_FILE\"\n"
        "printf 'WITH_DETAIL=%s\\n' \"${WITH_DETAIL:-}\" >> \"$SYNC_CALL_FILE\"\n"
        'for a in "$@"; do printf \'ARG=%s\\n\' "$a" >> "$SYNC_CALL_FILE"; done\n',
    )
    harness["sync_call"] = tmp_path / "sync-call.json"
    return harness


def _recorded_call(path: Path) -> dict:
    """把假 `refresh-cpbl-prod.sh` 錄下的呼叫形狀讀回來。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    return {
        "argv": [line[len("ARG="):] for line in lines if line.startswith("ARG=")],
        "skip_scrape": next(line[len("SKIP_SCRAPE="):] for line in lines
                            if line.startswith("SKIP_SCRAPE=")),
        "with_detail": next(line[len("WITH_DETAIL="):] for line in lines
                            if line.startswith("WITH_DETAIL=")),
    }


@pytest.mark.parametrize("argv", [[], ["fast"]], ids=["no-args", "fast"])
def test_daily_chain_still_reaches_the_sync_script(argv: list[str], tmp_path: Path) -> None:
    """紅線：守衛不得弄壞既有呼叫路徑。

    launchd 以**無參數**呼叫；`fast` 是文件化的既有位置參數。兩者都必須照舊跑到
    `scripts/refresh-cpbl-prod.sh:107` 那一步，而且**送出零個位置參數**——
    後者正是下一條測試要餵回真腳本守衛的輸入。
    """
    harness = _daily_harness(tmp_path)
    result, _ = _run(harness, argv, SYNC_CALL_FILE=str(harness["sync_call"]), SYNC_PROD="1",
                     REFRESH_TRIGGER="launchd")

    assert result.returncode == 0, f"stdout={result.stdout} stderr={result.stderr}"
    assert harness["sync_call"].exists(), "每日鏈沒有呼叫到 refresh-cpbl-prod.sh"

    call = _recorded_call(harness["sync_call"])
    assert call["argv"] == [], f"每日鏈送出了位置參數 {call['argv']}——會被新守衛擋下"
    assert call["skip_scrape"] == "1"
    assert call["with_detail"] == "1"


def test_recorded_daily_call_shape_passes_the_real_guard(tmp_path: Path) -> None:
    """把上一條錄到的呼叫形狀原樣餵回**真的** `refresh-cpbl-prod.sh` 副本。

    守衛不得攔下它，且必須真的放行到主流程（假樁被呼叫＝過了守衛）。只驗 rc≠64
    是不夠的——腳本因別的理由早退也會是非 64。
    """
    daily = _daily_harness(tmp_path / "daily")
    _run(daily, [], SYNC_CALL_FILE=str(daily["sync_call"]), SYNC_PROD="1",
         REFRESH_TRIGGER="launchd")
    call = _recorded_call(daily["sync_call"])

    harness = _fake_repo(tmp_path / "sync", "scripts/refresh-cpbl-prod.sh")
    result, calls = _run(harness, call["argv"], SKIP_SCRAPE=call["skip_scrape"],
                         WITH_DETAIL=call["with_detail"])

    assert result.returncode != 64, f"每日鏈的呼叫形狀被守衛擋下了：{result.stderr}"
    assert "未知參數" not in result.stderr
    assert calls, "沒有任何假樁被呼叫——無法證明守衛真的放行到主流程"
    assert calls[0]["cmd"] == "uv", calls


def test_daily_chain_call_site_passes_no_positional_arguments() -> None:
    """碼面釘住：呼叫點一旦被加上位置參數，新守衛會讓整條每日鏈當場 exit 64。"""
    source = (ROOT / "scripts" / "scrape-daily.sh").read_text(encoding="utf-8")
    # `usage()` 的 heredoc 也會提到這個檔名（說明文字），那不是呼叫點。
    body = _without_usage_body(source)
    call_lines = [line.strip() for line in body.splitlines()
                  if "refresh-cpbl-prod.sh" in line and not line.lstrip().startswith("#")]

    assert call_lines == [
        'SKIP_SCRAPE=1 WITH_DETAIL=1 bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh" >>"$LOG" 2>&1'
    ], call_lines


def test_fast_mode_is_still_the_only_accepted_positional(tmp_path: Path) -> None:
    """向後相容的另一半：`fast` 照舊被接受，其餘照舊 exit 64（守衛沒有放寬它）。"""
    harness = _daily_harness(tmp_path)
    result, _ = _run(harness, ["slow"], SYNC_CALL_FILE=str(harness["sync_call"]),
                     REFRESH_TRIGGER="launchd")

    assert result.returncode == 64
    assert "參數只接受 fast" in result.stderr
    assert not harness["sync_call"].exists()


# ============================================ 守衛控制流：四份必須逐字相同
#
# ⚠️ 這一節是量出來的。四支的守衛由同一個執行者在同一天寫出（`4956546`、`3833638`），
# **幾小時內就漂成三個變體**：兩支一種、`weekly-game-pitches.sh` 拒絕訊息不同、
# `scrape-daily.sh` 沒有 `*)` 分支。不是「未來會漂」，是已經漂了。
#
# 修法是把兩件事拆開（見 `script_inventory.SHELL_GUARD_CANONICAL` 的說明）：
# **`--help` 守衛**逐字相同、**位置參數契約**逐支不同。後者本來就該不同——
# 「不接受位置參數」vs「只接受 fast」、補救是環境變數 vs `YEAR=`，都是各腳本的事實。


def test_guard_control_flow_is_byte_identical_across_scripts() -> None:
    """四支的守衛控制流必須與 canonical 逐字相同——不是「看起來一樣」。"""
    flows = {rel: si.shell_guard_control_flow(rel) for rel in GUARDED_SHELLS}
    drifted = {rel: flow for rel, flow in flows.items() if flow != si.SHELL_GUARD_CANONICAL}
    assert not drifted, (
        "守衛控制流已漂離 canonical：\n"
        + "\n".join(f"--- {rel} ---\n{flow}" for rel, flow in drifted.items())
        + f"\n--- canonical ---\n{si.SHELL_GUARD_CANONICAL}")
    assert len(set(flows.values())) == 1, "四份之間互不相同"


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_negative_control_drifting_one_guard_is_caught(script_rel: str) -> None:
    """負控制：把控制流改壞，判準必須立刻不認它——**逐支**都要，不是抽驗一支。

    只證明「現況一致」不算數：一致有可能是巧合，也有可能是判準根本沒在看。
    這裡在**字串副本**上做四種真實會發生的漂移，每一種都必須被抓到。
    """
    source = (ROOT / script_rel).read_text(encoding="utf-8")
    assert si.guard_control_flow(source) == si.SHELL_GUARD_CANONICAL, "前提就不成立"

    drifts = {
        "把 exit 0 改成 exit 64（--help 變成拒絕而不是答案）":
            source.replace("      usage\n      exit 0\n", "      usage\n      exit 64\n", 1),
        "多認一個旗標（分支集合被偷偷擴張）":
            source.replace("    -h|--help)\n", "    -h|--help|-\\?)\n", 1),
        "把 if 條件改寬": source.replace('if [ "$#" -gt 0 ]; then',
                                    'if [ "$#" -ge 0 ]; then', 1),
        "縮排從 4 變 2（純空白的漂移也算漂移）":
            source.replace("    -h|--help)\n", "  -h|--help)\n", 1),
    }
    for label, mutated in drifts.items():
        assert mutated != source, f"變異沒有真的改到東西：{label}"
        assert si.guard_control_flow(mutated) != si.SHELL_GUARD_CANONICAL, (
            f"控制流被改壞卻沒被抓到：{label}")


@pytest.mark.parametrize("script_rel", GUARDED_SHELLS, ids=lambda s: Path(s).name)
def test_usage_content_is_not_shared_and_is_script_specific(script_rel: str) -> None:
    """反向要求：`usage` 內容**應該**逐支不同，共用才是錯的。

    三段（在做什麼／會寫什麼／怎麼呼叫）必須都在、且提到自己的路徑。
    """
    source = (ROOT / script_rel).read_text(encoding="utf-8")
    body = _USAGE_BODY_RE.search(source)
    assert body, "抽不到 usage() 本體"
    text = body.group(0)

    for section in USAGE_SECTIONS:
        assert section in text, f"{script_rel} 的用法缺少「{section}」段"
    assert script_rel in text, f"{script_rel} 的用法沒有提到自己"


def test_usage_bodies_are_pairwise_distinct() -> None:
    """四份用法不得有任何兩份相同——「會寫什麼」是各腳本特有的事實。"""
    bodies = {}
    for rel in GUARDED_SHELLS:
        match = _USAGE_BODY_RE.search((ROOT / rel).read_text(encoding="utf-8"))
        assert match
        bodies[rel] = match.group(0)
    assert len(set(bodies.values())) == len(bodies), "有兩支的用法內容一模一樣"


def test_positional_contract_stays_out_of_the_shared_guard() -> None:
    """位置參數契約必須在守衛**之後**，否則共用的東西就不再是純控制流。

    `scrape-daily.sh` 收 `fast`，另外三支一個都不收——把這個差異塞回守衛裡，
    守衛就會再度分岔。這條釘住那個誘惑。
    """
    for rel in GUARDED_SHELLS:
        flow = si.shell_guard_control_flow(rel)
        assert "exit 64" not in flow, f"{rel} 把拒絕邏輯放回守衛裡了"
        assert "fast" not in flow, f"{rel} 把位置參數的值寫進守衛了"


def test_guard_is_inline_not_sourced() -> None:
    """守衛不得靠 `source` 取得：那一行跑在守衛之前，檔案不見時會死在印出用法之前。"""
    for rel in GUARDED_SHELLS:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        guard_open = next(i for i, ln in enumerate(lines)
                          if ln == 'if [ "$#" -gt 0 ]; then')
        before = [ln for ln in lines[:guard_open]
                  if ln.strip() and not ln.lstrip().startswith("#")]
        sourced = [ln for ln in before if re.match(r"\s*(\.|source)\s+", ln)]
        assert not sourced, f"{rel} 在守衛之前 source 了東西：{sourced}"


# ================================================== 與盤點清冊同一條判準，不另立


def test_criteria_match_the_inventory_not_a_second_copy() -> None:
    """清冊判 safe 的依據就是本檔測的東西；兩邊不得各自演化。"""
    for rel in GUARDED_SHELLS:
        state, note = si.help_safety(rel)
        assert state == "safe", f"{rel} 在清冊仍是 {state}"
        assert "test_shell_help_guard.py" in note


def test_every_safe_shell_is_covered_here() -> None:
    """fail closed：清冊只要把任何一支 shell 判成 safe，本檔就必須涵蓋它。

    清冊的 shell 判準是整檔正則（看得到守衛在不在、看不到它在哪），
    它給出的 `safe` 之所以可信，靠的是本檔逐支證明零副作用。新腳本若只是
    碰巧含有 `usage()` 字樣就拿到 safe，這條會紅。
    """
    safe = {rel for rel in si._git_ls(si.SCRIPTS_GLOB)
            if rel.endswith(".sh") and si.help_safety(rel)[0] == "safe"}

    assert safe == set(GUARDED_SHELLS), (
        f"清冊判 safe 但本檔未涵蓋：{sorted(safe - set(GUARDED_SHELLS))}；"
        f"本檔涵蓋但清冊不判 safe：{sorted(set(GUARDED_SHELLS) - safe)}")


def test_allowlist_no_longer_names_the_scripts_this_card_fixed() -> None:
    """需求方推翻「具名放行」：修好的就不該再留在放行清單上。"""
    for rel in GUARDED_SHELLS:
        assert rel not in si.HELP_SAFETY_ALLOWLIST, f"{rel} 已修好，不該還在 allowlist"


def test_the_remaining_shell_gap_is_named_with_its_owner() -> None:
    """缺口只剩一支，且理由必須指名持有它的卡——不得只寫「同上」。"""
    reason = si.HELP_SAFETY_ALLOWLIST["scripts/weekly-box-revisions.sh"]

    assert "#132" in reason
    assert os.linesep not in reason
