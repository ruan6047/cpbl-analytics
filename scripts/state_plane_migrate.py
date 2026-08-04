"""OPS-STATE-PLANE-MIG1 Task 2：一次性遷移 Ledger 活卡至 GitHub Issues + Projects v2。

**一次性腳本**（`WF-22-CLI1` 之後的常駐版是獨立卡，本檔不會被那張卡沿用邏輯以外的部分取代）。

用法：
    uv run python scripts/state_plane_migrate.py --dry-run                    # 零網路呼叫，只印出解析結果
    uv run python scripts/state_plane_migrate.py --only OPS-STATE-PLANE-MIG1  # 單卡試跑（驗證端到端管線）
    uv run python scripts/state_plane_migrate.py                              # 全量遷移
    uv run python scripts/state_plane_migrate.py --out docs/research/OPS-STATE-PLANE-MIG1_reconciliation.md

資料來源與基準：
- 卡母體與現況欄位（Initiative／級別／功能／owner／分支worktree／iteration／交付狀態／
  部署狀態／最後交接）一律讀 `--baseline-ref`（預設 `origin/main`）當下的 `docs/TASKS.md`，
  用 `git show <ref>:docs/TASKS.md` 讀取，**不 checkout、不 merge**，執行分支的
  `docs/TASKS.md`／`docs/control-plane/**` 全程不受影響（紅線）。
- 新制欄位（服務的原始目標／鏈深／資源宣告）從同一 ref 的 `docs/tasks/<CARD_ID>.md`
  逐卡解析；2026-08-04 實測（見 Task 1 對照表）：39 卡中僅 1 卡（本卡自己）填了
  「服務的原始目標」，**0 卡**填了「鏈深」（決議 5 剛定案，字面上的「鏈深」提及只出現
  在規則說明文字，不是欄位值）。**未填寫一律顯示未填寫／未分類，不得預設猜測值**
  （鏈深尤其不可預設 0——0 與「尚未分類」語意不同，會污染決議 5 的鏈式停損判斷）。

欄位結構（結構凍結，events.jsonl `a04a862`；Task 1 對照表 12 項 Project 欄位，
「資源宣告」依需求方裁決改走 Issue body fenced JSON，**不建 Project 欄位、不用
MULTI_SELECT**——未文件化型別不採用，見 Task 1 報告的取捨記錄）：
    卡ID／Initiative／級別／功能／owner／分支worktree／iteration／交付狀態／
    部署狀態／最後交接（TEXT，完整 ISO-8601，字典序即時序）／服務的原始目標／鏈深。

冪等與重跑安全：
- Issue 內文尾端固定嵌入 `<!-- state-plane-mig1:card_id=<ID> -->` marker；重跑時先讀
  `--out` 指向的既有對帳表（若存在）跳過已成功的卡，只補跑缺漏／失敗的部分，不重建
  已存在的 Issue。
- 39/39（或當下實際活卡數）全數成功才在對帳表標記「完整」；任何一筆失敗，腳本結尾
  `sys.exit(1)`，對帳表如實列出失敗卡與原因，**不得回傳部分成功當作完整**（紅線 2）。

已知陷阱（Task 1 實測記錄，本腳本已規避）：
- `gh project item-list --format json` 對中文欄位名稱的 JSON **鍵名**會產生 U+FFFD
  亂碼（欄位「值」不受影響）。本腳本讀回一律走 `gh api graphql` 搭配
  `fieldValueByName(name: "...")` 或直接用欄位 `id` 精準指定，不依賴該指令的 JSON key。
- Project 自訂 `NUMBER` 欄位底層是 `Float`；iteration／鏈深皆為小整數，寫入時仍以
  Python `int` 產生字面值，讀回比對時容許 `x == int(x)`。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = "ruan6047/cpbl-analytics"
DEFAULT_OWNER = "@me"
DEFAULT_PROJECT_TITLE = "cpbl-analytics 任務看板"
DEFAULT_BASELINE_REF = "origin/main"
MARKER_PREFIX = "state-plane-mig1:card_id="

# --- 凍結欄位結構（Task 1 對照表 + 需求方 2026-08-04 裁決，events.jsonl a04a862） ---
# 級別／交付狀態／部署狀態選項＝canonical 文件定義值 ∪ 2026-08-04 fresh baseline 實測值，
# 兩者皆須涵蓋（例：canonical 定義 T0/T1 但目前無活卡使用；「🚧執行中」是 fresh baseline
# 實測才發現、Task 1 抽樣未涵蓋的既有資料變體，若照抄 Task 1 舊樣本會漏收）。
TIER_OPTIONS = ["T0", "T1", "T2", "T3", "T4"]
DELIVERY_STATUS_OPTIONS = [
    "📥Backlog", "💡需求", "🚧進行中", "🚧執行中", "⏸阻塞",
    "🔍待查核", "↩退回", "📦已合併", "🏁完成", "🚨已升級",
]
DEPLOY_STATUS_OPTIONS = ["—不適用", "⏸未部署", "✅已驗證", "🏁完成"]

# (欄位名, 型別, single-select 選項或 None)；資源宣告不在此列（body-only，見模組說明）。
FIELD_SPECS: list[tuple[str, str, list[str] | None]] = [
    ("卡ID", "TEXT", None),
    ("Initiative", "TEXT", None),
    ("級別", "SINGLE_SELECT", TIER_OPTIONS),
    ("功能", "TEXT", None),
    ("owner", "TEXT", None),
    ("分支／worktree", "TEXT", None),
    ("iteration", "NUMBER", None),
    ("交付狀態", "SINGLE_SELECT", DELIVERY_STATUS_OPTIONS),
    ("部署狀態", "SINGLE_SELECT", DEPLOY_STATUS_OPTIONS),
    ("最後交接", "TEXT", None),
    ("服務的原始目標", "TEXT", None),
    ("鏈深", "NUMBER", None),
]


class MigrationError(RuntimeError):
    """單卡遷移失敗（不中斷整體迴圈，由呼叫端收集後決定整體是否 fail）。"""


# --------------------------------------------------------------------------------------
# 外部指令包裝
# --------------------------------------------------------------------------------------


def run(*args: str) -> str:
    result = subprocess.run(list(args), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"命令失敗：{' '.join(args)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result.stdout


def gh_json(*args: str) -> Any:
    return json.loads(run("gh", *args, "--format", "json"))


def graphql(query: str) -> dict:
    return json.loads(run("gh", "api", "graphql", "-f", f"query={query}"))


def git_show(ref: str, path: str) -> str:
    return run("git", "show", f"{ref}:{path}")


def resolve_sha(ref: str) -> str:
    return run("git", "rev-parse", ref).strip()


# --------------------------------------------------------------------------------------
# Ledger／卡片檔解析
# --------------------------------------------------------------------------------------


@dataclass
class LedgerRow:
    card_id: str
    initiative: str
    tier: str
    feature: str
    owner: str
    branch_worktree: str
    iteration: str
    delivery_status: str
    deploy_status: str
    last_handoff: str


_ROW_RE = re.compile(
    r"^\|\s*\[(?P<card_id>[A-Za-z0-9_-]+)\]\([^)]+\)\s*\|"
    r"(?P<initiative>[^|]*)\|"
    r"(?P<tier>[^|]*)\|"
    r"(?P<feature>[^|]*)\|"
    r"(?P<owner>[^|]*)\|"
    r"(?P<branch_worktree>[^|]*)\|"
    r"(?P<iteration>[^|]*)\|"
    r"(?P<delivery_status>[^|]*)\|"
    r"(?P<deploy_status>[^|]*)\|"
    r"(?P<last_handoff>[^|]*)\|\s*$",
    re.MULTILINE,
)


def parse_ledger(markdown: str) -> list[LedgerRow]:
    rows = []
    for m in _ROW_RE.finditer(markdown):
        values = {k: v.strip() for k, v in m.groupdict().items()}
        rows.append(LedgerRow(**values))
    return rows


def validate_row_options(row: LedgerRow) -> list[str]:
    """純函式、零網路呼叫的預檢查：確認本卡的 級別／交付狀態／部署狀態 都落在凍結的
    single-select 選項域內。設計成獨立於 `field_defs`（不需真的建好 Project 欄位才能
    驗證），讓 `--dry-run` 與正式跑之前都能先抓到「資料裡出現選項清單沒涵蓋的值」
    這類問題——2026-08-04 實測就抓到 `INGEST-SPLITS-IMPORT-RESTATE1` 用「🚧執行中」
    而非 Task 1 樣本裡的「🚧進行中」，兩者是不同字串，若照抄舊樣本會在正式跑到一半
    才報錯。回傳空list代表本卡通過。"""
    problems = []
    if row.tier not in TIER_OPTIONS:
        problems.append(f"級別「{row.tier}」不在 {TIER_OPTIONS}")
    if row.delivery_status not in DELIVERY_STATUS_OPTIONS:
        problems.append(f"交付狀態「{row.delivery_status}」不在 {DELIVERY_STATUS_OPTIONS}")
    if row.deploy_status not in DEPLOY_STATUS_OPTIONS:
        problems.append(f"部署狀態「{row.deploy_status}」不在 {DEPLOY_STATUS_OPTIONS}")
    return problems


_DB_SCOPE_RE = re.compile(r"DB：`([^`]+)`")
_RESOURCE_LINE_RE = re.compile(r"資源：(.*)$", re.MULTILINE)
_RESOURCE_TOKEN_RE = re.compile(r"`([^`]+)`")
_ORIGINAL_GOAL_RE = re.compile(r"^-\s*服務的原始目標[:：]\s*(.+)$", re.MULTILINE)
_CHAIN_DEPTH_RE = re.compile(r"^-\s*鏈深[:：]\s*(\d+)", re.MULTILINE)


def extract_db_scope(card_text: str) -> str | None:
    """回傳 None 代表本卡 header 無 `DB：` 行（實測：3/39 為 INIT-* Initiative 卡，
    無獨立分支／db_scope 屬結構性正常，非資料缺漏；一般執行卡若缺此行才是真缺漏，
    對帳表會照實顯示 None，由人判讀是哪一種）。"""
    m = _DB_SCOPE_RE.search(card_text)
    if not m:
        return None
    value = m.group(1).strip()
    if value.lower().startswith("db_scope:"):
        value = value.split(":", 1)[1].strip()
    return value


def extract_resources(card_text: str) -> list[str]:
    """空陣列＝本卡未在 `資源：` 行正式宣告額外資源，不代表無風險，只代表未宣告。
    刻意只認 `資源：` 標籤後的 backtick token，不掃全文 `file:`/`db:` 字樣——後者會把
    純敘述文字裡提到的檔案路徑誤認成資源宣告（過度收集），兩種錯誤中這裡選擇少報而非
    亂報。"""
    m = _RESOURCE_LINE_RE.search(card_text)
    if not m:
        return []
    return _RESOURCE_TOKEN_RE.findall(m.group(1))


def extract_original_goal(card_text: str) -> str | None:
    m = _ORIGINAL_GOAL_RE.search(card_text)
    return m.group(1).strip() if m else None


def extract_chain_depth(card_text: str) -> int | None:
    """2026-08-04 實測：0/39 卡有此欄位真實填寫值（決議剛定案）。維持獨立函式供未來
    卡片開始填寫後直接生效；目前恆回傳 None，呼叫端顯示「未分類」而非猜測 0。"""
    m = _CHAIN_DEPTH_RE.search(card_text)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------------------
# Issue body 組裝
# --------------------------------------------------------------------------------------


def build_issue_title(row: LedgerRow) -> str:
    return f"{row.card_id}：{row.feature}"


def build_issue_body(row: LedgerRow, card_text: str, baseline_sha: str) -> str:
    db_scope = extract_db_scope(card_text)
    resources = extract_resources(card_text)
    original_goal = extract_original_goal(card_text)
    chain_depth = extract_chain_depth(card_text)

    resource_json = {"db_scope": db_scope, "resources": resources}
    spec_url = f"https://github.com/{REPO}/blob/{baseline_sha}/docs/tasks/{row.card_id}.md"

    lines = [
        f"> 遷移自 `docs/tasks/{row.card_id}.md`（baseline `{baseline_sha}`，"
        "OPS-STATE-PLANE-MIG1 Task 2 一次性遷移；結構凍結 `a04a862`）。",
        ">",
        "> **本 Issue 為 cutover 前的影子追蹤**：`docs/control-plane/events.jsonl` 仍是唯一",
        "> 作業狀態事實來源；Issue 內容僅反映遷移當下快照，不隨後續 event 自動更新。",
        "",
        "## Spec",
        f"- [`docs/tasks/{row.card_id}.md`]({spec_url})（baseline SHA `{baseline_sha}`）",
        "",
        f"## 現況摘要（遷移當下，來自 Ledger @ `{baseline_sha}`）",
        f"- Initiative：{row.initiative}",
        f"- 級別：{row.tier}",
        f"- 功能：{row.feature}",
        f"- owner：{row.owner}",
        f"- 分支／worktree：{row.branch_worktree}",
        f"- iteration：{row.iteration}",
        f"- 交付狀態：{row.delivery_status}",
        f"- 部署狀態：{row.deploy_status}",
        f"- 最後交接：{row.last_handoff}",
        "",
        "## 新制欄位",
        f"- 服務的原始目標：{original_goal or '未填寫（本卡於新制欄位定案前建立，2026-08-04）'}",
        "- 鏈深："
        + (str(chain_depth) if chain_depth is not None else "未分類（決議 5 剛定案，尚未逐卡分類；非 0）"),
        "",
        "## 資源宣告（機器可讀；`null`／`[]` 代表未正式宣告，不代表無資源）",
        "```json",
        json.dumps(resource_json, ensure_ascii=False, indent=2),
        "```",
        "",
        f"<!-- {MARKER_PREFIX}{row.card_id} -->",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Project / Issue 操作
# --------------------------------------------------------------------------------------


def find_or_create_project(owner: str, title: str, dry_run: bool) -> tuple[str, int]:
    data = gh_json("project", "list", "--owner", owner, "--limit", "100")
    for p in data["projects"]:
        if p["title"] == title:
            return p["id"], p["number"]
    if dry_run:
        return "DRY-RUN-PROJECT-ID", -1
    created = gh_json("project", "create", "--owner", owner, "--title", title)
    return created["id"], created["number"]


def existing_fields(project_number: int, owner: str) -> dict[str, dict]:
    data = gh_json("project", "field-list", str(project_number), "--owner", owner)
    return {f["name"]: f for f in data["fields"]}


def get_select_options_full(field_id: str) -> list[dict]:
    """查完整選項（含 color／description），供安全合併新增選項用——`gh project
    field-list` 的簡化 JSON 不帶 color，直接覆蓋會把它們重設成預設值。"""
    data = graphql(
        f'query {{ node(id: "{field_id}") {{ '
        f"... on ProjectV2SingleSelectField {{ options {{ id name color description }} }} }} }}"
    )
    return data["data"]["node"]["options"]


def ensure_select_options(field_id: str, desired_names: list[str]) -> None:
    """既有選項全部保留原 id／color／description（避免打亂已引用這些 option id 的
    item 資料），只把缺少的名稱以新選項附加上去——這是 main 持續推進、新狀態值
    （如「↩退回」）在欄位建立後才出現時的必要補強，不能因為欄位已存在就跳過。"""
    current = get_select_options_full(field_id)
    current_names = {o["name"] for o in current}
    missing = [n for n in desired_names if n not in current_names]
    if not missing:
        return
    parts = [
        "{" + f'id: "{o["id"]}", name: {json.dumps(o["name"], ensure_ascii=False)}, '
        f'color: {o["color"]}, description: {json.dumps(o["description"], ensure_ascii=False)}' + "}"
        for o in current
    ] + [
        "{" + f"name: {json.dumps(n, ensure_ascii=False)}, color: GRAY, description: \"\"" + "}"
        for n in missing
    ]
    graphql(
        f'mutation {{ updateProjectV2Field(input: {{ fieldId: "{field_id}", '
        f"singleSelectOptions: [{', '.join(parts)}] }}) {{ "
        f"projectV2Field {{ ... on ProjectV2SingleSelectField {{ id }} }} }} }}"
    )


def ensure_fields(project_number: int, owner: str, dry_run: bool) -> dict[str, dict]:
    current = {} if dry_run else existing_fields(project_number, owner)
    for name, dtype, options in FIELD_SPECS:
        if dry_run:
            continue
        if name not in current:
            args = [
                "project", "field-create", str(project_number), "--owner", owner,
                "--name", name, "--data-type", dtype,
            ]
            if options:
                args += ["--single-select-options", ",".join(options)]
            gh_json(*args)
        elif options:
            # 欄位已存在（例如試跑遺留）：仍須確認選項全集涵蓋凍結列表，
            # main 前進導致的新狀態值不能因為欄位已建立就永遠補不進去。
            ensure_select_options(current[name]["id"], options)
    return current if dry_run else existing_fields(project_number, owner)


def find_existing_issue_number(card_id: str) -> int | None:
    """本地對帳表優先（見 load_progress）；本函式是額外保險，用 GitHub search 撈
    marker，僅在對帳表遺失時當備援（search 索引有延遲，不可當主要冪等機制）。"""
    query = f'repo:{REPO} "{MARKER_PREFIX}{card_id}" in:body'
    try:
        results = json.loads(run("gh", "search", "issues", query, "--json", "number,title"))
    except RuntimeError:
        return None
    return results[0]["number"] if results else None


def create_issue(card_id: str, title: str, body: str) -> tuple[int, str]:
    """建立 Issue；重跑且本地進度檔遺失時，先用 marker 搜尋既有 Issue 再決定是否
    真的需要新建，避免對同一張卡重複建立（`find_existing_issue_number` 的存在意義：
    本地 `--out` JSON 是主要冪等機制，這裡是它遺失時的備援，不是主要路徑）。"""
    existing_number = find_existing_issue_number(card_id)
    if existing_number is not None:
        return existing_number, f"https://github.com/{REPO}/issues/{existing_number}"

    body_path = ROOT / f".migrate_body_{card_id}.tmp.md"
    body_path.write_text(body, encoding="utf-8")
    try:
        url = run(
            "gh", "issue", "create", "--repo", REPO,
            "--title", title, "--body-file", str(body_path),
        ).strip()
    finally:
        body_path.unlink(missing_ok=True)
    number = int(url.rsplit("/", 1)[-1])
    return number, url


def add_item_to_project(project_number: int, owner: str, issue_url: str) -> str:
    data = gh_json(
        "project", "item-add", str(project_number), "--owner", owner, "--url", issue_url,
    )
    return data["id"]


def _alias(field_name: str) -> str:
    # GraphQL alias 不可含中文／全形符號，改用穩定的英數對照表。
    table = {
        "卡ID": "cardId", "Initiative": "initiative", "級別": "tier", "功能": "feature",
        "owner": "owner", "分支／worktree": "branchWorktree", "iteration": "iteration",
        "交付狀態": "deliveryStatus", "部署狀態": "deployStatus", "最後交接": "lastHandoff",
        "服務的原始目標": "originalGoal", "鏈深": "chainDepth",
    }
    return table[field_name]


def _to_number_literal(value: str) -> str:
    try:
        return str(int(value))
    except ValueError:
        return str(float(value))


# --------------------------------------------------------------------------------------
# 對帳表輸出
# --------------------------------------------------------------------------------------


@dataclass
class CardResult:
    card_id: str
    status: str  # "ok" | "failed" | "skipped(dry-run)"
    issue_number: int | None = None
    issue_url: str | None = None
    item_id: str | None = None
    error: str | None = None


def load_progress(out_path: Path) -> dict[str, CardResult]:
    if not out_path.exists():
        return {}
    json_path = out_path.with_suffix(".json")
    if not json_path.exists():
        return {}
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    return {r["card_id"]: CardResult(**r) for r in raw.get("results", [])}


def write_reconciliation(
    out_path: Path,
    results: list[CardResult],
    baseline_ref: str,
    baseline_sha: str,
    project_title: str,
    project_number: int,
) -> None:
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status == "failed"]
    total = len(results)

    lines = [
        "# OPS-STATE-PLANE-MIG1 Task 2 — 卡ID ↔ Issue# 對帳表",
        "",
        f"- 遷移基準：`{baseline_ref}` @ `{baseline_sha}`",
        f"- 目標 Project：`{project_title}`（number {project_number}）",
        f"- 結果：**{len(ok)}/{total} 成功**"
        + ("　**全數通過，可宣告完整**" if len(ok) == total and total > 0 else "　**未全數通過，不得宣告完整（紅線 2）**"),
        "",
        "| 卡ID | Issue# | 狀態 | 備註 |",
        "|---|---|---|---|",
    ]
    for r in results:
        issue_ref = f"[#{r.issue_number}](https://github.com/{REPO}/issues/{r.issue_number})" if r.issue_number else "—"
        note = r.error or ""
        lines.append(f"| {r.card_id} | {issue_ref} | {r.status} | {note} |")

    if failed:
        lines += ["", "## 失敗詳情", ""]
        for r in failed:
            lines.append(f"- **{r.card_id}**：{r.error}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_path.with_suffix(".json").write_text(
        json.dumps(
            {
                "baseline_ref": baseline_ref,
                "baseline_sha": baseline_sha,
                "project_title": project_title,
                "project_number": project_number,
                "total": total,
                "ok": len(ok),
                "results": [vars(r) for r in results],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------------------


def _text_mutation(project_id: str, item_id: str, field_defs: dict, name: str, value: str) -> str:
    fid = field_defs[name]["id"]
    return (
        f'{_alias(name)}: updateProjectV2ItemFieldValue(input: {{projectId: "{project_id}", '
        f'itemId: "{item_id}", fieldId: "{fid}", '
        f'value: {{ text: {json.dumps(value, ensure_ascii=False)} }}}}) '
        f"{{ projectV2Item {{ id }} }}"
    )


def _number_mutation(project_id: str, item_id: str, field_defs: dict, name: str, value: str) -> str:
    fid = field_defs[name]["id"]
    return (
        f'{_alias(name)}: updateProjectV2ItemFieldValue(input: {{projectId: "{project_id}", '
        f'itemId: "{item_id}", fieldId: "{fid}", value: {{ number: {_to_number_literal(value)} }}}}) '
        f"{{ projectV2Item {{ id }} }}"
    )


def _select_mutation(project_id: str, item_id: str, field_defs: dict, name: str, value: str) -> str:
    fid = field_defs[name]["id"]
    option = next((o for o in field_defs[name]["options"] if o["name"] == value), None)
    if option is None:
        raise MigrationError(
            f"「{name}」的值「{value}」不在既有 single-select 選項中"
            f"（現有：{[o['name'] for o in field_defs[name]['options']]}）"
        )
    return (
        f'{_alias(name)}: updateProjectV2ItemFieldValue(input: {{projectId: "{project_id}", '
        f'itemId: "{item_id}", fieldId: "{fid}", '
        f'value: {{ singleSelectOptionId: "{option["id"]}" }}}}) '
        f"{{ projectV2Item {{ id }} }}"
    )


def build_field_mutations(
    project_id: str,
    item_id: str,
    field_defs: dict[str, dict],
    row: LedgerRow,
    original_goal: str | None,
    chain_depth: int | None,
) -> list[str]:
    """組出本卡全部欄位的 aliased mutation 字串（純函式，無網路呼叫，可單元測試）。

    鏈深為 `None`（未分類）時**刻意省略該欄位的 mutation**，讓 Project 上該欄位保持
    空白——比寫入 `-1`／`0` 這類哨兵數字誠實，因為 NUMBER 欄位無法像 TEXT 一樣顯示
    「未分類」字樣，留空最不容易被誤讀成「已分類為 0 層」。
    """
    resolved_goal = original_goal or "未填寫（本卡於新制欄位定案前建立，2026-08-04）"
    mutations = [
        _text_mutation(project_id, item_id, field_defs, "卡ID", row.card_id),
        _text_mutation(project_id, item_id, field_defs, "Initiative", row.initiative),
        _select_mutation(project_id, item_id, field_defs, "級別", row.tier),
        _text_mutation(project_id, item_id, field_defs, "功能", row.feature),
        _text_mutation(project_id, item_id, field_defs, "owner", row.owner),
        _text_mutation(project_id, item_id, field_defs, "分支／worktree", row.branch_worktree),
        _number_mutation(project_id, item_id, field_defs, "iteration", row.iteration),
        _select_mutation(project_id, item_id, field_defs, "交付狀態", row.delivery_status),
        _select_mutation(project_id, item_id, field_defs, "部署狀態", row.deploy_status),
        _text_mutation(project_id, item_id, field_defs, "最後交接", row.last_handoff),
        _text_mutation(project_id, item_id, field_defs, "服務的原始目標", resolved_goal),
    ]
    if chain_depth is not None:
        mutations.append(_number_mutation(project_id, item_id, field_defs, "鏈深", str(chain_depth)))
    return mutations


def migrate_one_card(
    row: LedgerRow,
    card_text: str,
    baseline_sha: str,
    project_id: str,
    project_number: int,
    owner: str,
    field_defs: dict[str, dict],
    dry_run: bool,
) -> CardResult:
    title = build_issue_title(row)
    body = build_issue_body(row, card_text, baseline_sha)

    if dry_run:
        return CardResult(card_id=row.card_id, status="skipped(dry-run)")

    try:
        number, url = create_issue(row.card_id, title, body)
        item_id = add_item_to_project(project_number, owner, url)

        original_goal = extract_original_goal(card_text)
        chain_depth = extract_chain_depth(card_text)
        mutations = build_field_mutations(
            project_id, item_id, field_defs, row, original_goal, chain_depth,
        )
        graphql("mutation {\n  " + "\n  ".join(mutations) + "\n}")

        return CardResult(
            card_id=row.card_id, status="ok", issue_number=number, issue_url=url, item_id=item_id,
        )
    except Exception as exc:  # noqa: BLE001 — 逐卡失敗須被捕捉，不得讓整迴圈中斷
        return CardResult(card_id=row.card_id, status="failed", error=str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--project-title", default=DEFAULT_PROJECT_TITLE)
    parser.add_argument("--out", default="docs/research/OPS-STATE-PLANE-MIG1_reconciliation.md")
    parser.add_argument("--only", action="append", default=None, help="只跑指定卡ID（可重複），用於試跑")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    baseline_sha = resolve_sha(args.baseline_ref)
    ledger_md = git_show(args.baseline_ref, "docs/TASKS.md")
    rows = parse_ledger(ledger_md)
    if args.only:
        rows = [r for r in rows if r.card_id in args.only]

    print(f"基準：{args.baseline_ref} @ {baseline_sha}；卡數：{len(rows)}")

    all_problems = {row.card_id: validate_row_options(row) for row in rows}
    all_problems = {k: v for k, v in all_problems.items() if v}
    if all_problems:
        print("預檢查失敗：以下卡的值不在凍結 single-select 選項域內，須先擴充選項常數再跑：", file=sys.stderr)
        for card_id, problems in all_problems.items():
            for p in problems:
                print(f"  {card_id}：{p}", file=sys.stderr)
        sys.exit(1)
    print(f"預檢查通過：{len(rows)} 卡的 級別／交付狀態／部署狀態 皆在凍結選項域內")

    out_path = ROOT / args.out
    previous = load_progress(out_path) if not args.dry_run else {}

    project_id, project_number = find_or_create_project(args.owner, args.project_title, args.dry_run)
    field_defs = ensure_fields(project_number, args.owner, args.dry_run)
    print(f"Project：{args.project_title} #{project_number}（{project_id}）")

    results: list[CardResult] = []
    for row in rows:
        if row.card_id in previous and previous[row.card_id].status == "ok":
            print(f"  [skip 已完成] {row.card_id}")
            results.append(previous[row.card_id])
            continue

        card_text = git_show(args.baseline_ref, f"docs/tasks/{row.card_id}.md")
        result = migrate_one_card(
            row, card_text, baseline_sha, project_id, project_number,
            args.owner, field_defs, args.dry_run,
        )
        status_label = {"ok": "OK", "failed": "FAILED", "skipped(dry-run)": "dry-run"}[result.status]
        print(f"  [{status_label}] {row.card_id}" + (f" -> #{result.issue_number}" if result.issue_number else ""))
        if result.status == "failed":
            print(f"      錯誤：{result.error}")
        results.append(result)

        if not args.dry_run:
            # 每張卡處理完立刻落盤（而非等整批跑完）：39 卡 × 多次 gh／GraphQL
            # round-trip 實測會跑到逼近或超過單次逾時視窗，中途被中斷時已成功
            # 建立的 Issue／Project item 不能因為對帳表沒寫入就從進度追蹤裡消失
            # ——那會讓重跑時對已成功的卡重複建立 Issue（search 索引有延遲、
            # 不能單靠它去重，見 create_issue docstring）。
            write_reconciliation(
                out_path, results, args.baseline_ref, baseline_sha, args.project_title, project_number,
            )

    if not args.dry_run:
        print(f"對帳表已寫入：{out_path}")

    ok_count = sum(1 for r in results if r.status == "ok")
    total = len(results)
    if args.dry_run:
        print(f"[dry-run] 解析完成，共 {total} 卡（未實際寫入）")
        return

    print(f"完成：{ok_count}/{total}")
    if ok_count != total:
        print("未全數成功，依紅線 2 不得宣告完整。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
