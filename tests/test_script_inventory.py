"""DEV-SCRIPT-INVENTORY1：可執行入口清冊的**同步偵測器**。

`scripts/script_inventory.py` 是工具（人跑它重生清冊），本檔是偵測器（CI 跑它）。
形狀沿用 repo 內既有的 `tests/test_strength1_report_sync.py`：
測試載入產生器 → 重新產生 → 與已 commit 的產物逐字比對。

## 本檔守的四條不變式

1. **檔頭標記**：`scripts/**` 每一支的 `LIFECYCLE:` 標記必須等於機械推導出來的分類。
2. **位置棘輪**：分類與位置不符的集合**只能縮不能長**。
3. **引用完整性**：活檔案裡的 `scripts/<name>.<ext>` 字面路徑必須指向存在的檔案。
4. **寫入型必須 `--help` 安全**：不合格者必須具名列入 allowlist。

## 以及所有「宣告表」的過期偵測

`WRITE_ADJUDICATION`／`SINGLE_CRITERION_OVERRIDE`／`CLASS_OVERRIDES`／
`HELP_SAFETY_ALLOWLIST`／`POSITION_EXCEPTIONS` 全部是人工維護的表。
**每一張都有對應的過期偵測**——條目所描述的情況已經不存在時，CI 紅。
這是刻意的：`roadmap_lines.py` 的 `GATE_OVERRIDES` 被 `#137` 判為缺陷的理由
就是「硬編的逐卡說明文字，沒有到期或真實性來源」，本卡不重演。

## 五類已知錯誤的回歸案例

產生器在開發過程中犯過五類錯，全部有回歸案例，且每個案例都附**負控制**
（naive 實作），證明「修法之前這個測試會紅」而不是「這個測試剛好會過」。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from scripts import script_inventory as si
from tests import test_cli_help_guard as cli_guard

REPO_ROOT = Path(__file__).resolve().parents[1]


# ===================================================== 集合窮舉與 fail closed


def test_three_surfaces_are_enumerated_from_git_not_hand_listed() -> None:
    """窮舉的證據力來自「清單由 `git ls-files` 產生」而非人工列舉。"""
    entries = si.build_entries()
    by_surface: dict[str, set[str]] = {"scripts": set(), "research": set(), "cli": set()}
    for e in entries:
        by_surface[e.surface].add(e.ident)

    assert by_surface["scripts"] == {
        p for p in si._git_ls(si.SCRIPTS_GLOB) if Path(p).name not in si.NON_ENTRY_BASENAMES
    }
    assert by_surface["research"] == set(si._git_ls(si.RESEARCH_GLOB))
    assert len(by_surface["cli"]) == 47, "pyproject [project.scripts] 應為 47 支"
    assert len(entries) == sum(len(v) for v in by_surface.values())


def test_every_entry_has_a_class_fail_closed() -> None:
    """未判定的項目要列出來，不得靜默跳過（卡面「驗證」節明訂）。"""
    unclassified = sorted(e.ident for e in si.build_entries() if not e.cls)
    assert not unclassified, f"以下入口分不出類別，須具名改判：{unclassified}"


def test_class_labels_cover_every_class_in_use() -> None:
    used = {e.cls for e in si.build_entries()}
    assert used <= set(si.CLASS_LABELS), f"分類標籤缺漏：{used - set(si.CLASS_LABELS)}"


# ============================================== 不變式 1：檔頭標記 ⇔ 分類


def test_invariant_1_every_script_carries_a_lifecycle_marker() -> None:
    """`scripts/**` 的每一支都要有檔頭標記——這是「檔案系統上可分辨」的載體。"""
    missing = [
        rel for rel in si._git_ls(si.SCRIPTS_GLOB)
        if Path(rel).name not in si.NON_ENTRY_BASENAMES and not si.lifecycle_marker(rel)
    ]
    assert not missing, (
        f"以下腳本缺 LIFECYCLE 檔頭標記：{missing}\n"
        "補上：`uv run python scripts/script_inventory.py --stamp`")


def test_invariant_1_marker_matches_derived_class() -> None:
    """標記寫錯比沒標更危險——分類是錯的而不是缺的。"""
    mismatched = []
    for rel in si._git_ls(si.SCRIPTS_GLOB):
        if Path(rel).name in si.NON_ENTRY_BASENAMES:
            continue
        cls, _ = si.classify(rel)
        marker = si.lifecycle_marker(rel)
        if marker != cls:
            mismatched.append(f"{rel}: 標記={marker!r} 推導={cls!r}")
    assert not mismatched, "標記與推導分類不符：\n" + "\n".join(mismatched)


def test_invariant_1_marker_is_within_the_scan_window() -> None:
    """產生器寫得出來、讀取器讀不回來＝靜默不一致。標記必須落在掃描窗內。

    初版把標記放在 module docstring 之後，5 支長 docstring 的檔案標記掉出掃描窗。
    """
    for rel in si._git_ls("scripts/*.py"):
        if Path(rel).name in si.NON_ENTRY_BASENAMES:
            continue
        lines = (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
        idx = next(i for i, ln in enumerate(lines) if si.LIFECYCLE_RE.match(ln))
        assert idx < si.LIFECYCLE_SCAN_LINES, f"{rel} 的標記在第 {idx + 1} 行，超出掃描窗"


def test_invariant_1_stamping_is_idempotent(tmp_path: Path) -> None:
    """`--stamp` 重跑不得產生第二個標記，也不得吃掉原有內容。"""
    sample = tmp_path / "sample.py"
    original = '"""Docstring。"""\n\nVALUE = 1\n'
    sample.write_text(original, encoding="utf-8")

    lines = original.splitlines()
    once = si._strip_existing_marker(lines)
    marker = "# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（X-1）"
    stamped = [marker, *once]
    twice = [marker, *si._strip_existing_marker(stamped)]
    assert stamped == twice
    assert sum(1 for ln in twice if si.LIFECYCLE_RE.match(ln)) == 1
    assert ast.get_docstring(ast.parse("\n".join(twice))) == "Docstring。"


# ================================================= 不變式 2：位置棘輪

# ⚠️ 凍結的位置債。**只能縮不能長**——新增的位置不符即紅。
# 由 `scripts/script_inventory.py::position_debt()` 於 2026-08-15 產生，理由逐支見
# `scripts/README.md`「位置棘輪」節。後續卡以正確射程搬動時，從本表刪除對應條目。
FROZEN_POSITION_DEBT = frozenset({
    "scripts/audit_game_recap_data.py",
    "scripts/backfill_player_bio_gap1.py",
    "scripts/backfill_player_bio_gap2.py",
    "scripts/check_scoreless_null_folding.py",
    "scripts/check_splits_pa_split1_results.py",
    "scripts/compare_runless_vs_er_streak.py",
    "scripts/data_tie_remedy1.py",
    "scripts/data_tz_boundary1.py",
    "scripts/dryrun_game_tm_fullseason.py",
    "scripts/g4_gate_report.py",
    "scripts/g4_redline1_probe.py",
    "scripts/ibb_ghost1_probe.py",
    "scripts/outcome_leak_compare.py",
    "scripts/outcome_simple_calibration_audit.py",
    "scripts/reconcile_game_tm.py",
    "scripts/reconcile_splits_recalc1.py",
    "scripts/rehearsal_backfill.py",
    "scripts/rehearsal_pa_build.py",
    "scripts/replay_schedule_branches.py",
    "scripts/report_pa_rebuild_fix1.py",
    "scripts/restate1_reconcile.py",
    "scripts/state_plane_migrate.py",
    "scripts/strength1_report_tables.py",
    "scripts/team_style2_manager_pairs.py",
    "scripts/team_style_vectors.py",
    "scripts/verify_pa_build_fix1.py",
    "scripts/verify_splits_pa_split1.py",
    "scripts/wp_bio_prior1.py",
})


def test_invariant_2_position_debt_only_shrinks() -> None:
    """新增一支分類與位置不符的腳本 → CI 紅。這是「作者忘記了會怎樣」的答案。"""
    current = set(si.position_debt())
    added = sorted(current - FROZEN_POSITION_DEBT)
    assert not added, (
        f"新增的位置不符：{added}\n"
        "分類決定位置：常設 → scripts/；CI 繫結 → scripts/ci/；"
        "一次性產物 → docs/research/<CARD-ID>/。\n"
        "刻意的例外請具名列入 script_inventory.POSITION_EXCEPTIONS 並寫理由。")


def test_invariant_2_frozen_debt_has_no_phantom_entries() -> None:
    """已經搬好（或已刪）的條目要從凍結表移除，否則這張表會變成第二個 GATE_OVERRIDES。"""
    stale = sorted(FROZEN_POSITION_DEBT - set(si.position_debt()))
    assert not stale, f"位置債已解除但仍留在凍結表：{stale}——請從 FROZEN_POSITION_DEBT 刪除"


def test_invariant_2_every_oneshot_has_a_home_card() -> None:
    """一次性產物必須有歸屬卡，否則 `docs/research/<CARD-ID>/` 算不出來。"""
    homeless = sorted(
        e.ident for e in si.build_entries()
        if e.cls == "oneshot" and not e.expected)
    assert not homeless, f"一次性產物缺歸屬卡：{homeless}——請補 ONESHOT_HOME"


# ============================================== 不變式 3：引用完整性


def test_invariant_3_literal_paths_in_live_files_resolve() -> None:
    """全庫**活檔案**裡的 `scripts/<name>.<ext>` 字面路徑必須指向存在的檔案。

    這條是被 `scripts/data_tie_remedy1.py:273-277` 的 `FROZEN_FILES` 逼出來的：
    它以字面路徑硬編兩支一次性產物，而 CI 只 import `_streaks_for` 碰不到 `is_frozen`。
    搬走那兩支會讓守衛靜默回 `False`，零訊號。**現在會紅。**
    """
    broken = set(si.broken_enforced_refs())
    unexpected = sorted(broken - set(FROZEN_BROKEN_REFS))
    assert not unexpected, "強制面裡的字面路徑指向不存在的檔案：\n" + "\n".join(unexpected)


# ⚠️ 本卡射程外、但確實壞掉的字面路徑。**具名 ＋ 理由**，不放寬判準。
# 這些是本卡順手掃出來的既有缺陷，不是本卡造成的；修它們要碰 `docs/`，
# 而需求方裁定 4 已把 `docs/` 移出射程。
#
# 目前為空：唯一一筆（`REVIEW_GATE_CONTRACT.md:284 → scripts/review_gate_preflight.py`）
# 已由 DOC-REVIEW-GATE-ARCHIVE1 消解——該行是被否決的設計替代方案（§9 稽核表「另立
# `scripts/review_gate_preflight.py`」→ 處置「併入 `review_prompt.py --preflight`」），
# 那支腳本**刻意不存在**，措辭沒有錯。契約本身也是死的（等一張 🛑已停止 的卡才生效），
# 故整份 `git mv` 進 `docs/archive/`，落到 `historical` 面＝只回報不強制。
# ⚠️ 空集合不代表判準失效：`test_reference_integrity_surface_is_not_empty` 是它的正控制。
FROZEN_BROKEN_REFS: dict[str, str] = {}


def test_frozen_broken_refs_have_not_been_silently_fixed() -> None:
    """凍結表只放**現在真的還壞著**的——修好了要撤掉，否則它會變成第二個 GATE_OVERRIDES。"""
    stale = sorted(set(FROZEN_BROKEN_REFS) - set(si.broken_enforced_refs()))
    assert not stale, f"以下壞路徑已修復，請從 FROZEN_BROKEN_REFS 刪除：{stale}"


def test_reference_integrity_surface_is_not_empty() -> None:
    """正控制：強制面若因為分類寫錯而變成空集合，上面那條會退化成恆真。"""
    surfaces = [si._ref_surface(loc)
                for locs in si.literal_path_refs().values() for loc in locs]
    assert surfaces.count("enforced") > 100, (
        f"強制面只有 {surfaces.count('enforced')} 處，判準可能寫錯了")


def test_invariant_3_frozen_files_guard_is_actually_covered() -> None:
    """正控制：確認 `FROZEN_FILES` 的兩條字面路徑真的落在本不變式的觀測面內。

    不驗這件事的話，上面那條會退化成「證明什麼都沒發生」。
    """
    refs = si.literal_path_refs()
    for target in ("scripts/data_rules_audit1.py", "scripts/g4_phase_a_metrics.py"):
        sites = [loc for loc in refs.get(target, ()) if loc.startswith("scripts/data_tie_remedy1.py")]
        assert sites, f"{target} 未被 FROZEN_FILES 引用偵測到——不變式的前提破了"


def test_invariant_3_unresolvable_split_paths_are_reported_not_hidden() -> None:
    """靜態解析不了的分段路徑要被**看見**並列出，不能因為抓不到就當作沒有。"""
    sites = si.split_path_sites()
    rendered = (REPO_ROOT / "scripts" / "README.md").read_text(encoding="utf-8")
    if sites:
        assert "分段路徑" in rendered, "有分段路徑組裝點，但清冊沒有揭露"


# ======================================== 不變式 4：高後果必須 --help 安全
#
# ⚠️ 判準原本寫成「**寫入型**必須 `--help` 安全」，而 `backup-prod-db.sh` 從那個形狀
# 的縫隙掉出去：它對 DB 唯讀（`pg_dump`），所以 `writes=False`，不變式根本不看它——
# 但它的 `--help` 會 ssh 進生產跑整庫 dump，然後 exit 0、產出備份、`rm -f` 掉輪替
# 視窗裡最舊的那份。**清冊逐支印著「⚠️ --help 不安全」，卻沒有任何強制路徑。**
#
# 判準已改問「探索動作會不會造成損害」＝寫 DB **或**接觸遠端生產 **或**不可逆刪檔。
# 下方 `test_invariant_4_predicate_is_not_dbwrite_only` 就是釘住這個縫隙不再打開。


def test_invariant_4_high_consequence_entries_are_help_safe_or_allowlisted() -> None:
    """高後果入口，argv 必須在主流程前被解析；例外必須具名。"""
    violators = [
        e.ident for e in si.high_consequence_unsafe(si.build_entries())
        if e.ident not in si.HELP_SAFETY_ALLOWLIST
    ]
    assert not violators, (
        f"以下入口高後果但 `--help` 不安全，且未具名例外：{violators}\n"
        "判準沿用 tests/test_cli_help_guard.py：argv 必須在主流程前被解析。\n"
        "既有不合格者請列入 script_inventory.HELP_SAFETY_ALLOWLIST 並寫明理由與去向。")


def test_invariant_4_allowlist_has_no_stale_entries() -> None:
    """腳本修好了、或不再判定為高後果 → allowlist 條目要撤掉。"""
    violators = {e.ident for e in si.high_consequence_unsafe(si.build_entries())}
    stale = sorted(set(si.HELP_SAFETY_ALLOWLIST) - violators)
    assert not stale, f"allowlist 條目已過期：{stale}——請刪除"


def test_invariant_4_predicate_is_not_dbwrite_only() -> None:
    """回歸：**對 DB 唯讀但探索即造成損害**的入口必須進得了不變式 4 的射程。

    負控制就是舊判準本身——`writes and help_state == unsafe`。以 `backup-prod-db.sh`
    的真實形狀（唯讀 DB ＋ ssh 生產 ＋ rm -f 輪替 ＋ 無守衛）構造合成入口：舊判準
    看不到它，新判準要抓到。抓不到就表示縫隙又打開了。
    """
    src = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'ssh -o BatchMode=yes "$VPS" "docker exec prod_pg pg_dump -U u -d d" | gzip -c > "$P"\n'
        'rm -f "$OLDEST"\n'
    )
    assert not si.MUTATING_SQL_RE.search(src) and not si.MUTATING_SHELL_RE.search(src), (
        "構造失敗：這份合成腳本被判成寫入型，就證明不了舊判準的縫隙")
    assert si.REMOTE_REACH_RE.search(src), "遠端接觸沒被偵測到"
    assert si.IRREVERSIBLE_FS_RE.search(src), "不可逆刪檔沒被偵測到"


def test_invariant_4_predicate_sees_http_not_just_ssh() -> None:
    """回歸 `DEV-SCRIPT-INVENTORY1-R2-001`：**HTTP 出口**必須進得了不變式 4 的射程。

    成因：判準**名為**「接觸遠端」，**實作**只認 SSH（`REMOTE_REACH_RE`）。
    `confirm_live_schema.py` 完全不看 argv，`--help` 直接被當成 game ID 拼進 URL 對
    `stats.cpbl.com.tw` 發真實 GET——判準看不到它。

    負控制＝**修法前的判準本身**：`REMOTE_REACH_RE` ∪ `IRREVERSIBLE_FS_RE` 對這份
    合成入口一條都不命中。舊判準看不到、新判準要抓到；抓不到就是縫隙又打開了。
    """
    src = (
        "import httpx\n"
        "import sys\n"
        "def main() -> None:\n"
        "    gid = sys.argv[1] if len(sys.argv) > 1 else 'X'\n"
        "    with httpx.Client() as c:\n"
        "        c.get('https://example.invalid/' + gid)\n"
        "main()\n"
    )
    # 負控制：舊判準的兩條正則對整份原始碼都不命中
    assert not si.REMOTE_REACH_RE.search(src), "負控制失效——舊判準本來就不該命中 HTTP"
    assert not si.IRREVERSIBLE_FS_RE.search(src), "負控制失效"
    assert not si.MUTATING_SQL_RE.search(src), "構造失敗：被判成寫入型就證明不了縫隙"

    graph = si._build_graph(src)
    effects = si._propagate(graph, {})
    assert "http" in effects.get("main", set()), "新判準沒抓到 httpx 出口"

    # 正控制：把 httpx 換成純計算，同一條路徑必須判成無出口
    benign = src.replace("import httpx\n", "").replace(
        "    with httpx.Client() as c:\n        c.get('https://example.invalid/' + gid)\n",
        "    print(gid)\n")
    assert not si._propagate(si._build_graph(benign), {}).get("main"), (
        "正控制失效——無出口的入口不該有效果，否則上面那條退化成恆真")


def test_invariant_4_predicate_is_path_sensitive_not_import_closure() -> None:
    """精確度回歸：**import 一個常數**不等於碰得到那個模組的出口。

    這條擋的是「為了看見 HTTP 而改掃 import 閉包」那個修法：`httpx` 在 `cpbl.*`
    相依圖裡到處都是，閉包法會把 `check_splits_pa_split1_results.py`（只 import
    `APART_COMBOS` 這個 list 常數）判成打網路的，然後需要 allowlist 消化誤判——
    而每多一條 allowlist 就離 `GATE_OVERRIDES` 近一步。
    """
    entry = next(e for e in si.build_entries()
                 if e.ident == "scripts/check_splits_pa_split1_results.py")
    assert not entry.high_consequence, (
        "只 import 常數的唯讀腳本被判成高後果——判準退回 import 閉包了")

    # 正控制：同一個模組的**函式**若真的可達出口，必須抓得到。
    reached = si.reachable_effects("scripts/replay_schedule_branches.py")
    assert "http" in reached, (
        "`with _client() as client:` 打賽程 API 沒被偵測到——"
        "精確度不能是靠什麼都判不到換來的")


def test_closure_method_is_measurably_less_precise(capsys: pytest.CaptureFixture) -> None:
    """「呼叫圖比閉包精確」必須是**現算的**，不是清冊裡一個會過期的數字。

    ⚠️ 這條同時是誠實度的守衛：如果哪天呼叫圖法變成閉包法的超集（＝退回去了），
    下面的方向性斷言會紅。
    """
    # ⚠️ 兩邊都限 `.py`：閉包法結構性只適用於 Python（`.sh` 沒有 import 圖），
    # 拿 `.sh` 進來比會製造一個假的「呼叫圖多判」——實測 `refresh-cpbl-prod.sh`
    # 真的有 `curl`（:555、:569），那是 shell 那一格的判準，不是本對照的母體。
    entries = [e for e in si.build_entries() if si._entry_module(e).endswith(".py")]
    closure = set(si.closure_http_hits(entries))
    graph = {e.ident for e in entries
             if "http" in si.entry_effects(si._entry_module(e), e.writes)}

    with capsys.disabled():
        print(f"\n閉包法 {len(closure)} 支 / 呼叫圖法 {len(graph)} 支 / "
              f"閉包法多判 {len(closure - graph)} 支")

    assert closure - graph, "閉包法沒有多判任何一支——精確度差額的前提破了"
    assert "scripts/check_splits_pa_split1_results.py" in closure - graph, (
        "只 import `APART_COMBOS` 常數的腳本不再是閉包法的誤判——"
        "回歸案例的前提變了，請重新檢視這條的意義")
    assert not graph - closure, (
        f"呼叫圖判到而閉包法沒判到：{sorted(graph - closure)}——"
        "閉包法應是超集，出現反例表示其中一法寫錯了")


def test_invariant_4_predicate_follows_reexported_sinks() -> None:
    """再匯出鏈：`b` 只是 `from a import f`，`b.f` 仍然帶著 `a.f` 的出口。

    實測抓到的假陰性：`game_tm_shadow` 自己一行 `httpx` 呼叫都沒有，
    但它 `from cpbl.ingest.cpbl_pitch_tracking import _client`，
    而 `replay_schedule_branches.py` 呼叫的正是這個再匯出的 `_client`。
    """
    symbols = si._module_effects("cpbl.ingest.game_tm_shadow")
    assert "http" in symbols.get("_client", frozenset()), (
        "再匯出的符號丟失了效果——呼叫圖會在轉手處斷掉")


def test_invariant_4_predicate_counts_class_methods_as_the_class() -> None:
    """類別的出口記在 `Class.method` 底下，而 import 綁的是**裸類別名**。

    實測抓到的假陰性：`cpbl-live-worker` 從 `cpbl.ingest.live_game_worker` import
    `StatsLiveSource`，而 `httpx.Client(...)` 在 `StatsLiveSource.__init__:175` 裡。
    只比對裸名 → 判成不打網路，而它其實會。
    """
    symbols = si._module_effects("cpbl.ingest.live_game_worker")
    assert "http" in symbols.get("StatsLiveSource.__init__", frozenset()), "前提變了"
    assert "http" in si._effects_of_symbol(symbols, "StatsLiveSource"), (
        "裸類別名拿不到方法的效果——建構式裡的出口會整個消失")

    entry = next(e for e in si.build_entries() if e.ident == "cpbl-live-worker")
    assert entry.high_consequence and "網路" in entry.high_consequence_note

    # 負控制：只比對裸名（修法前的形狀）看不到它
    assert "StatsLiveSource" not in symbols, (
        "負控制失效——裸名本來就不該是 key，否則證明不了這個縫隙存在過")


def test_writes_ast_is_a_projection_of_the_same_engine() -> None:
    """W1 與不變式 4 不得再各自演化——這正是 `R2-001` 的成因。

    `writes_ast` 必須逐支等於 `reachable_effects(...) ∋ db_write`，
    否則就是又有了第二份實作。
    """
    cfg = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    targets = sorted(
        {e.ident for e in si.build_entries()
         if e.surface != "cli" and e.ident.endswith(".py")}
        | {rel for rel in (si._cli_entry_module(t)
                           for t in cfg["project"]["scripts"].values()) if rel}
    )
    assert len(targets) > 90, f"觀測面只有 {len(targets)} 支，這條會退化成恆真"
    mismatched = [
        rel for rel in targets
        if si.writes_ast(rel) != ("db_write" in si.reachable_effects(rel))
    ]
    assert not mismatched, f"W1 與可達性引擎不一致：{mismatched}"


# ============================ 一次性產物的 `--help` 守衛：執行期零請求證明
#
# 需求方裁定（2026-08-15）：**加守衛，不要留紀錄。** 執行者原本主張具名放行，理由是
# 「一次性產物本來就沒人該跑」；被推翻的關鍵是 `--help` 不是「跑它」而是「想知道它
# 是什麼」，而本 repo 已有兩次 `--help` 觸發真實爬蟲的事故。
#
# 判準沿用 `.py` 那條（argparse 在主流程前 `parse_args`），但靜態判準只證明 argv 有被
# 解析、證明不了「解析之前沒有副作用」。這裡補上執行期證明，形狀沿用
# `tests/test_shell_help_guard.py`：**副本 ＋ 假樁**，本卡紅線「不得執行版控樹上的
# 腳本」照舊——跑的一律是 `tmp_path` 裡 `shutil.copy2` 出來的副本。

# 路徑 → (守衛那一行, 改回修法前的形狀)
ONESHOT_HELP_GUARDS = {
    "docs/research/INGEST-SCORELESS-INNING-PITCHER1/confirm_live_schema.py": (
        "    gid = _parser().parse_args().gid",
        '    import sys as _s\n    gid = _s.argv[1] if len(_s.argv) > 1 else "2026-A-246"',
    ),
    "scripts/replay_schedule_branches.py": (
        "    _parser().parse_args()\n",
        "",
    ),
}

# 假 httpx：import 鏈實際只用到 `Client` 與 `HTTPError`（實測 grep 全鏈）。
# 建構即留痕、`get` 留痕後立刻 SystemExit——「有沒有走到網路出口」是唯一要證明的事。
_HTTPX_STUB = '''\
import json, os, pathlib

_LOG = pathlib.Path(os.environ["HTTPX_CALL_LOG"])


class HTTPError(Exception):
    pass


class HTTPStatusError(HTTPError):
    pass


class RequestError(HTTPError):
    pass


def _record(what):
    entries = json.loads(_LOG.read_text()) if _LOG.exists() else []
    entries.append(what)
    _LOG.write_text(json.dumps(entries))


class Client:
    def __init__(self, *a, **k):
        _record("httpx.Client()")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, *a, **k):
        _record("httpx.Client.get")
        raise SystemExit(97)


def get(*a, **k):
    _record("httpx.get")
    raise SystemExit(97)
'''


def _oneshot_harness(tmp_path: Path, rel: str, *, drop_guard: bool) -> dict:
    """把腳本**複製**進 tmp，httpx 換成留痕假樁。絕不執行版控樹上的檔案。"""
    work = tmp_path / "work"
    stub_dir = tmp_path / "stub"
    work.mkdir()
    stub_dir.mkdir()
    (stub_dir / "httpx.py").write_text(_HTTPX_STUB, encoding="utf-8")

    source = (REPO_ROOT / rel).read_text(encoding="utf-8")
    guard, replacement = ONESHOT_HELP_GUARDS[rel]
    if drop_guard:
        assert guard in source, f"{rel} 的守衛那一行找不到——負控制會變成空斷言"
        source = source.replace(guard, replacement, 1)
    script = work / Path(rel).name
    script.write_text(source, encoding="utf-8")

    return {"work": work, "script": script, "stub": stub_dir,
            "log": tmp_path / "httpx-calls.json"}


def _run_oneshot(harness: dict, argv: list[str]) -> tuple[subprocess.CompletedProcess, list[str]]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(harness["work"].parent / "home"),
        "PYTHONPATH": str(harness["stub"]),
        "HTTPX_CALL_LOG": str(harness["log"]),
    }
    result = subprocess.run(
        [sys.executable, str(harness["script"]), *argv],
        cwd=harness["work"], env=env, text=True, capture_output=True,
        stdin=subprocess.DEVNULL, check=False,
    )
    calls = json.loads(harness["log"].read_text()) if harness["log"].exists() else []
    return result, calls


def _created(work: Path, script: Path) -> list[str]:
    return sorted(str(p.relative_to(work)) for p in work.rglob("*") if p != script)


@pytest.mark.parametrize("rel", sorted(ONESHOT_HELP_GUARDS), ids=lambda s: Path(s).name)
def test_oneshot_help_answers_and_issues_no_request(rel: str, tmp_path: Path) -> None:
    """`--help` 要 exit 0、回答三段用法，且**一個請求都不發、一個檔案都不產出**。"""
    harness = _oneshot_harness(tmp_path, rel, drop_guard=False)
    result, calls = _run_oneshot(harness, ["--help"])

    assert result.returncode == 0, f"stderr={result.stderr}"
    assert not calls, f"--help 發出了請求：{calls}"
    assert not _created(harness["work"], harness["script"]), _created(
        harness["work"], harness["script"])
    for section in ("在做什麼", "會寫什麼", "怎麼呼叫"):
        assert section in result.stdout, f"用法缺少「{section}」段：拒絕不是答案"


@pytest.mark.parametrize("rel", sorted(ONESHOT_HELP_GUARDS), ids=lambda s: Path(s).name)
def test_oneshot_unknown_flag_is_refused_not_ignored(rel: str, tmp_path: Path) -> None:
    """未知旗標要被拒絕（argparse 的 EX_USAGE=2），而不是被當成資料吞下去。"""
    harness = _oneshot_harness(tmp_path, rel, drop_guard=False)
    result, calls = _run_oneshot(harness, ["--dry-run"])

    assert result.returncode == 2, f"stdout={result.stdout} stderr={result.stderr}"
    assert not calls, f"未知旗標仍然走到網路出口：{calls}"
    assert "--dry-run" in result.stderr


@pytest.mark.parametrize("rel", sorted(ONESHOT_HELP_GUARDS), ids=lambda s: Path(s).name)
def test_negative_control_unguarded_help_really_reaches_the_network(
    rel: str, tmp_path: Path,
) -> None:
    """負控制：把守衛改回修法前的形狀，`--help` 必須真的走到 HTTP 出口。

    這條證明修的是**實害**而不是體感——假樁留痕就是那一次請求的證據。
    """
    harness = _oneshot_harness(tmp_path, rel, drop_guard=True)
    _, calls = _run_oneshot(harness, ["--help"])

    assert calls, (
        "拿掉守衛後 `--help` 沒有碰到網路——那代表假樁面沒有涵蓋這支的出口，證據力是假的")
    assert any("httpx" in c for c in calls), calls


def test_invariant_4_backup_prod_db_is_in_scope_and_now_guarded() -> None:
    """`backup-prod-db.sh`：本次加寬的成因，兩件事都要成立才算修好。

    (1) 進得了射程——否則加寬是空的；(2) `--help` 已安全——否則守衛沒加上。
    只驗其中一件都會讓另一半悄悄退化。
    """
    entry = next(e for e in si.build_entries() if e.ident == "scripts/backup-prod-db.sh")
    assert not entry.writes, "前提變了：它現在被判成寫入型，本測試的意義要重新檢視"
    assert entry.high_consequence, "唯讀 DB 但 ssh 生產＋rm -f 輪替，必須算高後果"
    assert entry.help_state == "safe", "argv 守衛不見了"
    assert entry.ident not in si.HELP_SAFETY_ALLOWLIST, "已加守衛就不該再具名放行"


def test_invariant_4_reuses_cli_help_guard_criteria_not_a_second_copy() -> None:
    """兩套判準各自演化正是本專案在修的病。本檔的 CLI 側判準直接對齊既有守衛。"""
    assert si.CLI_GUARD_FROZEN == cli_guard.FROZEN_MODULES
    assert si.CLI_GUARD_PACKAGES == cli_guard.GUARDED_PACKAGES


def test_refresh_recent_is_marked_unsafe_in_the_inventory() -> None:
    """需求方裁定 2：本卡不處理它，但清冊必須標記。"""
    entry = next(e for e in si.build_entries() if e.ident == "cpbl-refresh-recent")
    assert entry.help_state == "unsafe"
    assert "#53" in si.HELP_SAFETY_ALLOWLIST["cpbl-refresh-recent"]
    rendered = (REPO_ROOT / "scripts" / "README.md").read_text(encoding="utf-8")
    assert "cpbl-refresh-recent" in rendered
    assert "--help 不安全" in rendered


# ===================================== 寫入面交叉複算：不得未裁定、不得過期


def test_write_surface_has_no_undecided_disagreements() -> None:
    """兩判準不一致而沒有人工裁定 → fail closed。"""
    undecided = si.undecided_disagreements()
    assert not undecided, (
        f"以下入口的 W1（AST call-graph）與 W2（正則 SQL 掃描）不一致且未裁定：{undecided}\n"
        "**不取聯集也不取交集**——逐支判定後寫進 script_inventory.WRITE_ADJUDICATION。")


def test_write_surface_adjudications_are_not_stale() -> None:
    assert not si.stale_adjudications(), (
        f"以下裁定條目已過期（兩判準現在一致）：{si.stale_adjudications()}——請刪除")


def test_single_criterion_entries_are_shell_only() -> None:
    """W1 不適用只該發生在 `.sh`／`.plist`。若 `.py` 掉進這格，是產生器壞了。"""
    for e in si.build_entries():
        if e.writes_ast is None:
            assert e.ident.endswith((".sh", ".plist")), f"{e.ident} 不該是單一判準"


def test_class_overrides_are_not_stale() -> None:
    """推導結果已等於改判值 ＝ 這條改判可以刪。"""
    stale = []
    for rel, (cls, _reason) in si.CLASS_OVERRIDES.items():
        derived, _ = si.derive_class(rel)
        if derived == cls:
            stale.append(rel)
    assert not stale, f"分類改判已過期（推導結果已相符）：{stale}——請刪除"


def test_position_exceptions_are_not_stale() -> None:
    """位置例外必須真的是「分類與現況位置不符」才需要存在。"""
    stale = []
    for rel in si.POSITION_EXCEPTIONS:
        if not (REPO_ROOT / rel).exists():
            stale.append(f"{rel}（檔案已不存在）")
            continue
        cls, _ = si.derive_class(rel)
        default = {"standing": "scripts/", "ci_guard": "scripts/ci/"}.get(cls)
        if cls == "oneshot":
            default = f"docs/research/{si.ONESHOT_HOME.get(rel, si._card_of(rel))}/"
        current = str(Path(rel).parent) + "/"
        if default and (current == default or current.startswith(default)):
            stale.append(f"{rel}（位置已相符）")
    assert not stale, f"位置例外已過期：{stale}"


# ================================================== 清冊與產生器同步


def test_committed_inventory_matches_generator_output() -> None:
    """清冊是產生物。手改會被這條擋下——形狀沿用 test_strength1_report_sync.py。"""
    committed = (REPO_ROOT / "scripts" / "README.md").read_text(encoding="utf-8")
    assert committed == si.render(), (
        "scripts/README.md 與產生器輸出不一致；"
        "請執行 `uv run python scripts/script_inventory.py --write`")


def test_purpose_verified_is_labelled_as_a_human_column() -> None:
    """需求方裁定 6：這一欄可以留，但必須明載「人工維護、無機械讀者、會過期」。"""
    rendered = (REPO_ROOT / "scripts" / "README.md").read_text(encoding="utf-8")
    assert "人工維護" in rendered or "人工欄" in rendered
    assert "沒有機械讀者" in rendered
    assert "會過期" in rendered


def test_unverified_purposes_are_shown_not_silently_blank() -> None:
    """未查證的要列出來不得靜默跳過。"""
    rendered = (REPO_ROOT / "scripts" / "README.md").read_text(encoding="utf-8")
    unverified = [e for e in si.build_entries() if e.ident not in si.PURPOSE_VERIFIED]
    if unverified:
        assert "未查證" in rendered


def test_generator_itself_touches_no_io() -> None:
    """產生器不得 import DB driver 或開網路——它是唯讀盤點工具。

    本卡紅線是「不得執行任何 `scripts/` 下的腳本」。產生器是本卡自己寫的、
    且必須被本檔執行，所以它「不碰 I/O」這件事要機械證明，不能靠聲明。
    """
    tree = ast.parse((REPO_ROOT / "scripts" / "script_inventory.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = imported & {"psycopg", "psycopg_pool", "socket", "httpx", "requests",
                            "urllib", "urllib3", "cpbl", "playwright"}
    assert not forbidden, f"產生器 import 了 I/O 模組：{sorted(forbidden)}"

    # subprocess 唯一允許的用途是 `git ls-files`
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run" and node.args):
            first = node.args[0]
            assert isinstance(first, ast.List) and isinstance(first.elts[0], ast.Constant)
            assert first.elts[0].value == "git", "產生器只准跑 git"


def test_generator_help_is_safe_by_its_own_criterion() -> None:
    """產生器自己也要通過不變式 4 的判準——盤點工具不能是例外。"""
    state, _ = si.help_safety("scripts/script_inventory.py")
    assert state == "safe"


# ==================================================================
# 五類已知錯誤的回歸案例
#
# 每一個都附**負控制**（naive 實作），證明「修法之前這個測試會紅」。
# ==================================================================


def test_regression_1_prose_mention_is_not_a_ci_binding() -> None:
    """已知錯誤 1「模組級誤標」：註解／散文裡提到腳本，不算 pytest 機械載入。

    誤標的後果不是漏掉，是**分類錯**——一次性產物被標成 CI 繫結守衛，
    位置跟著錯，而且看起來像「有人在用」。
    """
    known = {"scripts/foo.py"}
    prose_only = '''"""這個測試的邏輯參考 scripts/foo.py 的作法。"""
# 另見 scripts/foo.py 的 _helper()
# TODO: 之後把 scripts/foo.py 的判準搬過來

def test_something():
    assert True
'''
    assert si.ci_binding_targets(prose_only, known) == set()

    real_import = "from scripts.foo import helper\n"
    assert si.ci_binding_targets(real_import, known) == {"scripts/foo.py"}

    spec_load = 'SPEC = spec_from_file_location("foo", ROOT / "scripts" / "foo.py")\n'
    assert si.ci_binding_targets(spec_load, known) == {"scripts/foo.py"}

    # 負控制：naive 的「全文正則掃描」會把散文也算進去
    naive = re.compile(r"scripts/foo\.py")
    assert naive.search(prose_only), "負控制失效——naive 實作本來就該在這裡誤命中"


def test_regression_2_literal_path_matching_respects_word_boundaries() -> None:
    """已知錯誤 2「正則邊界」：`scripts/foo.py` 不得命中 `.pyc`，也不得命中 `myscripts/`。"""
    path = "scripts/foo.py"
    assert si.literal_path_in_line(path, "uv run python scripts/foo.py --check")
    assert si.literal_path_in_line(path, "見 `scripts/foo.py`。")

    assert not si.literal_path_in_line(path, "rm scripts/foo.pyc")
    assert not si.literal_path_in_line(path, "cat myscripts/foo.py")
    assert not si.literal_path_in_line(path, "scripts/foo.py.bak")
    assert not si.literal_path_in_line(path, "docs/scripts/foo.py")

    # 負控制：無詞界的 naive 正則會全部誤命中
    naive = re.compile(re.escape(path))
    for line in ("rm scripts/foo.pyc", "cat myscripts/foo.py", "docs/scripts/foo.py"):
        assert naive.search(line), "負控制失效——naive 實作本來就該在這裡誤命中"


@pytest.mark.parametrize("text", [
    "SELECT updated_at FROM games",
    "ORDER BY created_at DESC",
    "WHERE deleted_flag IS NULL",
    "TRUNCATE_KEYS = ('points', 'spray')",
    "PRODUCTION_HOST = 'x'",
    "DROPDB_BACKUP_DIR = '/tmp'",
    "SELECT count(*) FROM cpbl.games",
])
def test_regression_3_sql_verbs_do_not_match_as_substrings(text: str) -> None:
    """已知錯誤 3「子字串假陽性」：`updated_at`／`PRODUCTION` 這類 token 不是動詞。

    誤判的後果是把唯讀腳本標成寫入型，然後不變式 4 對它提出一個不存在的要求——
    偵測器開始要求作者為不存在的危險加守衛，久了就沒有人相信它。
    """
    assert not si.MUTATING_SQL_RE.search(text), f"不該命中：{text}"
    assert not si.MUTATING_SHELL_RE.search(text), f"不該命中：{text}"


@pytest.mark.parametrize("text", [
    "INSERT INTO cpbl.games (id) VALUES (%s)",
    "UPDATE cpbl.pitch_tracking p SET x = 1",
    "DELETE FROM cpbl.splits WHERE year = %s",
    "TRUNCATE cpbl.staging",
    "DROP TABLE IF EXISTS cpbl.tmp",
    "CREATE TABLE cpbl.foo (id int)",
])
def test_regression_3_positive_control_real_verbs_still_match(text: str) -> None:
    """正控制：上面那條若因為正則寫太緊而全部不命中，就退化成「證明什麼都沒發生」。"""
    assert si.MUTATING_SQL_RE.search(text), f"應該命中：{text}"


def test_regression_4_split_paths_are_detected_not_silently_missed() -> None:
    """已知錯誤 4「分段路徑假陰性」：`ROOT / "scripts" / name` 字面正則抓不到。

    抓不到本身無解（要靜態求值），但**不能假裝沒有**——必須列出來。
    """
    split_forms = [
        'SCRIPT = ROOT / "scripts" / name',
        'path = "scripts/" + basename',
        'p = Path("scripts", name)',
    ]
    for line in split_forms[:2]:
        assert si._SPLIT_PATH_RE.search(line), f"分段路徑未被偵測：{line}"
        # 負控制：字面路徑正則對這些形式**本來就**抓不到，這正是要回報的原因
        assert not si._LITERAL_PATH_RE.search(line)

    assert not si._SPLIT_PATH_RE.search('SCRIPT = "scripts/foo.py"'), "完整字面路徑不該算分段"


def test_regression_5_card_ids_are_not_truncated_at_a_prefix() -> None:
    """已知錯誤 5「卡 ID 前綴截斷」：`GAME-RECAP-PA1-FIX1` 不得被截成 `GAME-RECAP-PA1`。

    截斷的後果是一次性產物被歸到**錯的卡目錄**，而那個目錄看起來完全合理。
    """
    assert si.card_ids("見 GAME-RECAP-PA1-FIX1 的交付") == ["GAME-RECAP-PA1-FIX1"]
    assert si.card_ids("INGEST-GAME-TM-REFACTOR1-G4 Gate 4") == ["INGEST-GAME-TM-REFACTOR1-G4"]
    assert si.card_ids("DEV-SCRIPT-INVENTORY1") == ["DEV-SCRIPT-INVENTORY1"]

    # 負控制：非貪婪／固定段數的 naive 正則會截斷
    naive = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){0,3}?\b")
    assert naive.search("GAME-RECAP-PA1-FIX1").group(0) != "GAME-RECAP-PA1-FIX1", (
        "負控制失效——naive 實作本來就該在這裡截斷")


def test_regression_5_real_repo_card_ids_are_intact() -> None:
    """回歸案例的形狀要與真實資料一致，不能只在合成字串上成立。

    ⚠️ 這裡**不能**用「某個卡 ID 是另一個的前綴」當截斷訊號：
    `INGEST-GAME-TM-REFACTOR1` 與 `INGEST-GAME-TM-REFACTOR1-G4` 是兩張真實的不同卡。
    改為直接對真實 docstring 斷言長 ID 被完整抽出。
    """
    cases = {
        "scripts/report_pa_rebuild_fix1.py": "GAME-RECAP-PA1-FIX1",
        "scripts/g4_gate_report.py": "INGEST-GAME-TM-REFACTOR1-G4",
    }
    for rel, expected in cases.items():
        found = si.card_ids(si._docstring(rel))
        assert expected in found, f"{rel} 的 docstring 未抽出完整卡 ID {expected}：{found}"
        prefix = expected.rsplit("-", 1)[0]
        assert prefix not in found, f"{rel} 抽出了截斷前綴 {prefix}"


# ================================================ 計數對帳（交付證據）


def test_counts_reconcile_across_three_surfaces() -> None:
    """三面計數對帳。本輪零搬動，增量全部具名。

    ⚠️ 這幾個數字是**閘門不是紀錄**：任何人新增 `scripts/` 入口都會撞紅這條，
    然後被迫在這裡寫下「多的那支是誰、為什麼」。所以改數字時必須同時改註解，
    不得只把數字調大——那等於把閘門拆了。
    """
    entries = si.build_entries()
    scripts = [e for e in entries if e.surface == "scripts"]
    research = [e for e in entries if e.surface == "research"]
    cli = [e for e in entries if e.surface == "cli"]

    assert len(scripts) == 53, (
        "49（基準 33c7c3f）＋ 1（DEV-SCRIPT-INVENTORY1 的 script_inventory.py）"
        "＋ 3（OPS-SCHEDULE-FAILURE-BLIND1／#132：schedule_watch.py、"
        "schedule-watchdog.sh、com.cpbl.schedule-watchdog.plist）。"
        "同卡的 schedule-registry.json 是純資料不是入口，見 NON_ENTRY_BASENAMES")
    assert len(research) == 21, (
        "19（基準）＋ 1（OPS-SCHEDULE-FAILURE-BLIND1／#132："
        "docs/research/OPS-SCHEDULE-FAILURE-BLIND1/measure_notification_delivery.py，"
        "通知投遞的可重建量測工具。住在自己卡的目錄裡，符合 oneshot 的位置規則）"
        "＋ 1（WP-DISCLOSURE-SYNC1／#100："
        "docs/research/WP-DISCLOSURE-SYNC1/keyplay_garbage_time.py，"
        "關鍵打席選法 × 垃圾時間的完整母體重測，取代原本樣本未留存、不可重跑的抽驗。"
        "住在自己卡的目錄裡，符合 oneshot 的位置規則）")
    assert len(cli) == 47, "CLI 不變"
    assert len(scripts) + len(research) + len(cli) == 121, (
        "119＋1（#132 的量測工具）＋1（#100 的重測工具）")


def test_invariant_proof_enumerates_every_entry(capsys: pytest.CaptureFixture) -> None:
    """驗收條件 2 的證明：逐支印出 (path, class, expected, ok)，**由 git ls-files 窮舉**。

    以 `uv run pytest tests/test_script_inventory.py -s -k proof` 取全文輸出。
    「窮舉」的證據力來自清單是機械產生的，不是人工列舉——報告裡不會出現
    任何「全部／全數」而背後只有人工聲明的句子。
    """
    entries = si.build_entries()
    lines = ["", "=" * 100,
             "DEV-SCRIPT-INVENTORY1 不變式證明（逐支窮舉，來源：git ls-files ＋ pyproject）",
             "=" * 100]

    for surface, title in (("scripts", "scripts/**"),
                           ("research", "docs/research/**/*.py"),
                           ("cli", "pyproject [project.scripts]")):
        rows = [e for e in entries if e.surface == surface]
        lines.append(f"\n--- {title}（{len(rows)}）---")
        lines.append(f"{'ok':>3} {'class':<16}{'marker':<16}{'writes':<7}{'help':<8}"
                     f"{'位置 → 應在':<44}入口")
        for e in sorted(rows, key=lambda x: x.ident):
            placed = e.surface == "cli" or si.position_ok(e.ident, e.cls)
            debt = e.ident in si.position_debt()
            marked = e.surface != "scripts" or e.marker == e.cls
            ok = bool(e.cls) and (placed or debt) and marked
            loc = "—" if surface == "cli" else (
                e.location if placed else f"{e.location} → {e.expected} ⚠️債")
            lines.append(
                f"{'✅' if ok else '❌':>3} {e.cls:<16}{(e.marker or '—'):<16}"
                f"{('寫' if e.writes else '唯讀'):<7}{e.help_state:<8}{loc:<44}{e.ident}")

    debt = si.position_debt()
    lines += [
        "", "-" * 100,
        f"計數對帳：scripts/** {sum(1 for e in entries if e.surface == 'scripts')}"
        f" ＋ docs/research/**/*.py {sum(1 for e in entries if e.surface == 'research')}"
        f" ＋ CLI {sum(1 for e in entries if e.surface == 'cli')} ＝ {len(entries)}",
        "（基準 33c7c3f 為 49＋19＋47＝115；本輪零搬動、零刪除，"
        "唯一增量是本卡新增的 scripts/script_inventory.py）",
        f"未分類：{sum(1 for e in entries if not e.cls)}　"
        f"標記缺漏：{sum(1 for e in entries if e.surface == 'scripts' and not e.marker)}　"
        f"標記不符：{sum(1 for e in entries if e.surface == 'scripts' and e.marker != e.cls)}",
        f"位置債：{len(debt)}（凍結表 {len(FROZEN_POSITION_DEBT)}，新增 "
        f"{len(set(debt) - FROZEN_POSITION_DEBT)}）",
        f"寫入面：兩判準皆適用 {sum(1 for e in entries if e.writes_ast is not None)}"
        f"（不一致 {sum(1 for e in entries if e.writes_ast is not None and e.writes_ast != e.writes_sql)}"
        f"，未裁定 {len(si.undecided_disagreements())}，過期 {len(si.stale_adjudications())}）；"
        f"單一判準 {sum(1 for e in entries if e.writes_ast is None)}",
        f"判定為寫入型：{sum(1 for e in entries if e.writes)}　"
        f"高後果（含非寫入型 {sum(1 for e in entries if e.high_consequence and not e.writes)}）："
        f"{sum(1 for e in entries if e.high_consequence)}　"
        f"其中 --help 不安全：{len(si.high_consequence_unsafe(entries))}"
        f"（全部具名於 allowlist：{all(e.ident in si.HELP_SAFETY_ALLOWLIST for e in si.high_consequence_unsafe(entries))}）",
        f"引用完整性：強制面壞路徑 {len(si.broken_enforced_refs())}"
        f"（凍結例外 {len(FROZEN_BROKEN_REFS)}，未預期 "
        f"{len(set(si.broken_enforced_refs()) - set(FROZEN_BROKEN_REFS))}）",
        "=" * 100,
    ]
    with capsys.disabled():
        print("\n".join(lines))

    assert all(e.cls for e in entries)
    assert not set(debt) - FROZEN_POSITION_DEBT
    assert not si.undecided_disagreements()
    assert not set(si.broken_enforced_refs()) - set(FROZEN_BROKEN_REFS)


def test_no_script_was_deleted_this_round() -> None:
    """卡面驗收條件 4：已死的只標記不刪除。"""
    baseline = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "--name-only", "origin/main", "scripts/"],
        capture_output=True, text=True, check=False)
    if baseline.returncode != 0:
        pytest.skip("取不到 origin/main")
    before = {p for p in baseline.stdout.split() if p}
    after = set(si._git_ls(si.SCRIPTS_GLOB))
    assert not (before - after), f"本輪不得刪除任何腳本，但少了：{sorted(before - after)}"
