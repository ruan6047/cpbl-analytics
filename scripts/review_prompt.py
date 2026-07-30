"""審核提示詞產生器：從 control-plane 最新 handoff event + 卡片檔自動生成查核提示詞。

用法（需求方在 repo 根目錄執行）：
    uv run python scripts/review_prompt.py <CARD_ID>            # 印到 stdout
    uv run python scripts/review_prompt.py <CARD_ID> | pbcopy   # 直接進剪貼簿貼給查核者

資料來源（零 AI 成本、永遠反映最新交接狀態）：
- docs/control-plane/events.jsonl：該卡最新 handoff event（分支、worktree、source_sha、
  tier、db_scope、執行者交付摘要）
- docs/tasks/<CARD_ID>.md：標題含「驗收」「驗證」「Gate」的章節原文、卡面〈查核〉欄
- git diff main...<source_sha>：該卡實際改動路徑（決定重現指令）

慣例（CONTROL_PLANE_CONTRACT.md「Review→merge 慣例」）：查核 APPROVE（零阻塞
findings）後 Coordinator 直接 merge，結果回傳執行者，部署另由需求方確認。

**產出物是查核者實際照著做的那一份**（DEV-REVIEW-PROMPT-GUARD1）：契約寫了什麼、
卡面要求什麼，若沒出現在這裡就等於沒有。因此三件事一律由輸出本身承載，不靠
「查核者自己會知道」——查核環境（HANDOFF_CONTRACT §3 的 detached worktree）、
重現指令（依實際改動路徑而非寫死）、獨立性（只給 tier 下限，卡面原文照登由人判讀）。
三者任一判不出來時**明講判不出來**，不得靜默退回預設值。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _main_checkout() -> Path:
    """主 checkout 的絕對路徑（worktree 慣例的錨點）。

    `ROOT` 只是「腳本這次從哪裡被跑起來」——從某個執行 worktree 跑時它就是那個
    worktree，拿它去組 `git worktree add .claude/worktrees/<卡>-review` 會把查核
    worktree 建在**執行 worktree 裡面**。查核環境的路徑必須錨在主 checkout，
    與腳本從哪跑無關，故走 `--git-common-dir`（worktree 與主 checkout 共用同一個
    值，即主 checkout 的 `.git`）。解不出來時退回 `ROOT`，不靜默給錯路徑。
    """
    r = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True)
    common = r.stdout.strip()
    if r.returncode != 0 or not common:
        print("警告：無法解析 --git-common-dir，worktree 指令改以腳本所在 repo 根目錄組成；"
              "貼給查核者前請確認路徑。", file=sys.stderr)
        return ROOT
    return Path(common).parent


MAIN_ROOT = _main_checkout()

# 卡面欄位錨點（tasks-card 範本）：「- Initiative：<父卡 ID／—>　spec 基線：<版本／—>」
_INITIATIVE_RE = re.compile(r"Initiative：\s*([A-Z][A-Z0-9\-]+)")
_BASELINE_RE = re.compile(r"spec 基線：\s*([^\s　]+)")


def _card_path(card_id: str) -> Path | None:
    """卡片檔路徑：活卡在 tasks/，父卡可能已封存在 archive/tasks/。"""
    for rel in (f"docs/tasks/{card_id}.md", f"docs/archive/tasks/{card_id}.md"):
        p = ROOT / rel
        if p.exists():
            return p
    return None


def baseline_check(card_id: str) -> str:
    """有 Initiative 父卡時產出 spec 基線一致性查核段（baseline-cascade §5）。

    無父卡（Initiative 欄為「—」或缺）回空字串——輸出不多任何段落。
    版本欄缺席時不靜默省略：明確標示「人工核對」。
    """
    path = _card_path(card_id)
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8")
    m_init = _INITIATIVE_RE.search(text)
    if not m_init:
        return ""
    parent_id = m_init.group(1)
    m_child = _BASELINE_RE.search(text)
    child_ver = m_child.group(1) if m_child else None

    parent_path = _card_path(parent_id)
    parent_ver = None
    if parent_path is not None:
        m_parent = _BASELINE_RE.search(parent_path.read_text(encoding="utf-8"))
        parent_ver = m_parent.group(1) if m_parent else None

    lines = [
        "### spec 基線一致性（canonical baseline-cascade §5）",
        "",
        f"- Initiative 父卡：{parent_id}"
        + (f"（`{parent_path.relative_to(ROOT)}`）" if parent_path else "（**卡片檔不存在**）"),
    ]
    if parent_ver and child_ver:
        verdict = "一致" if parent_ver == child_ver else "**不一致——舊基線交付，直接退回**"
        lines.append(f"- 父卡當前 spec 基線：`{parent_ver}`；本卡卡面 spec 基線：`{child_ver}` → {verdict}")
    else:
        missing = "父卡" if not parent_ver else "本卡"
        lines.append(
            f"- {missing}的 spec 基線欄缺席，無法自動核對——**人工核對**：對照父卡「基線變更紀錄」"
            "與本卡範圍是否仍在當前基線內。"
        )
    lines.append(
        "- 本段為產生提示詞當下的快照；查核時以父卡**當前**檔案再核對一次，"
        "不一致即退回（不進 finding 協商）。"
    )
    return "\n".join(lines)


def latest_handoff(card_id: str) -> tuple[dict, list[dict]]:
    """回傳 (最新 handoff event, 該 handoff 之後已發生的 review 事件)。

    第二個回傳值只在「這些 review（經更正後）都沒有終結本輪」時才非空——那是多關卡的卡
    （Design Gate、本地人工審先於跨家族查核）；它們的裁定是下一位查核者的前提，
    必須帶進提示詞，不能只留在 event log 裡。
    """
    ev = None
    events: list[dict] = []
    with open(ROOT / "docs/control-plane/events.jsonl", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("card_id") != card_id:
                continue
            events.append(e)
            if e.get("type") == "handoff":
                ev = e  # append-only → 最後一筆即最新
    if ev is None:
        sys.exit(f"錯誤：{card_id} 沒有 handoff event（尚未交付查核）。")
    gates = _assert_no_review_supersedes_handoff(card_id, events)
    _assert_handoff_matches_branch_head(ev)
    return ev, gates


# review 事件的選填欄位（語意與寫入時機見 docs/CONTROL_PLANE_CONTRACT.md）：
# - `closes_review_round`：`false` ＝ 這一筆是中繼關卡，不終結本輪查核。
#   欄位缺席一律視為終結本輪——既有事件（升級前 146 筆）因此判定完全不變。
# - `corrects_event_id`：這一筆更正**同輪內較早那筆** review 的 closes_review_round 宣告
#   （event log append-only，寫錯只能追加更正）。未指名更正對象的事件只代表自己。
CLOSES_ROUND_FIELD = "closes_review_round"
CORRECTS_FIELD = "corrects_event_id"


def _closes_review_round(e: dict) -> bool:
    """這筆 review 是否終結本輪。欄位缺席＝是；型別不對就吵，不當成缺席帶過。"""
    value = e.get(CLOSES_ROUND_FIELD)
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    sys.exit(
        f"錯誤：{e.get('event_id', '?')} 的 `{CLOSES_ROUND_FIELD}` 是 {value!r}"
        f"（{type(value).__name__}），只接受布林值。\n"
        "  這個欄位決定「本輪查核結束了沒」，猜錯的兩個方向都有代價——"
        "拒絕臆測，請先修正事件再重跑本指令。")


def _assert_no_review_supersedes_handoff(card_id: str, events: list[dict]) -> list[dict]:
    """最新 handoff 之後只要**存在終結本輪**的 review（經更正後），即拒絕再發提示詞。

    ML-PITCHER-SCORELESS1 的教訓：卡片已 `↩退回`、執行者尚未推修正，但本腳本
    只檢查「handoff SHA 是否等於分支 HEAD」——兩者當然還相等，於是照發提示詞。
    重跑指令就再派一位查核者去查同一份未修改的程式，得到逐字相同的 REJECT；
    實際發生三次，燒掉兩輪查核頻寬。該成立的性質是**現在到底還有沒有待查核的交付**。

    DEV-REVIEW-PROMPT-GATE1（2026-07-29）：舊版拿「有沒有 review 事件」當那個性質的
    標記，在**多關卡**的卡上不成立。`UX-ENTITY-LINKS2` 卡面要求「先本地人工審再交
    跨家族查核」，人工審 APPROVE（`REVIEW-007`）是第一關通過、不是本輪結束，守衛卻
    據此拒絕，該卡因而無法派跨家族查核；更糟的是拒絕訊息斷言「APPROVE → 接續
    merge／結案，不需要再查核一次」——照做就是把必要查核從未發生的交付直接 merge。

    為什麼是新增欄位而不是從既有欄位推斷（實測 146 筆 review 事件）：
    `delivery_status` 分不出來——17 筆停在 `🔍待查核`，其中 9 筆是最終 APPROVE 且
    下一個事件就是 merge；`owner` 更危險——最終 APPROVE 寫的是「Opus 4.8（執行，
    交付待查核）」，**本身就含「查核」二字**，子字串比對會把終局判成中繼。
    這個性質沒有既有欄位承載得住，所以讓它變成顯式欄位（`CLOSES_ROUND_FIELD`）。

    **存在終結本輪者即拒絕，且更正必須指名對象**（本卡 iteration 1 退回，2026-07-30）：
    iteration 1 曾採「以最新一筆為準」讓 append-only 的更正成為可能，代價是終局 REJECT
    之後追加**任意**一筆 `closes_review_round: false` 就重開同一 handoff，重開後先前的
    終局 REJECT 還會被當成「已通過的中繼關卡」帶進提示詞——中繼欄位成了繞過退回的
    後門。更正因此改為顯式：追加事件以 `corrects_event_id` 指向**同輪內較早**被更正的
    那筆，被指名者的判定以更正事件的宣告為準（多次更正以最新一筆為準）；未指名對象
    的事件只代表自己。型別驗證涵蓋該卡**每一筆** review 而非只有最後一筆——較早的
    malformed 事件不得被後續事件掩蓋（同輪退回 finding 3）。

    回傳值：本輪已發生且（經更正後）不終結本輪的 review（供提示詞帶出關卡裁定）。
    """
    after: list[dict] = []
    seen_handoff = False
    for e in events:
        if e.get("type") == "handoff":
            after = []            # 新一輪開始，之前的 review 不再相關
            seen_handoff = True
        elif e.get("type") == "review":
            _closes_review_round(e)   # 型別驗證不分輪、不分先後：malformed 不得被掩蓋
            if seen_handoff:
                after.append(e)
    if not after:
        return []
    effective: dict[str, bool] = {}
    for e in after:
        eid = str(e.get("event_id", "?"))
        declared = _closes_review_round(e)
        target = e.get(CORRECTS_FIELD)
        if target is not None:
            if not isinstance(target, str) or not target:
                sys.exit(
                    f"錯誤：{eid} 的 `{CORRECTS_FIELD}` 是 {target!r}"
                    f"（{type(target).__name__}），只接受被更正 review 的 event_id 字串。")
            if target == eid:
                sys.exit(f"錯誤：{eid} 的 `{CORRECTS_FIELD}` 指向自己，"
                         "更正對象必須是同輪內較早的另一筆 review。")
            if target not in effective:
                sys.exit(
                    f"錯誤：{eid} 宣告更正 {target}，但本輪（最新 handoff 之後）"
                    "在它之前沒有這筆 review。\n"
                    "  更正只能指向同一輪內較早的 review 事件——上一輪的判定已被新 handoff"
                    " 重置；對象若確實存在，請檢查 event_id 是否打錯，修正後再重跑本指令。")
            effective[target] = declared
        effective[eid] = declared
    closing = [e for e in after if effective[str(e.get("event_id", "?"))]]
    if not closing:
        return after
    listed = "\n".join(
        f"  - {e.get('event_id', '?')}（state_version {e.get('state_version')}，"
        f"{e.get('occurred_at', '?')}）actor：{e.get('actor', '?')}；"
        f"review_result：{e.get('review_result', '（未填）')}"
        for e in closing)
    sys.exit(
        f"錯誤：{card_id} 最新 handoff 之後已有 {len(after)} 筆 review，其中 {len(closing)} 筆"
        f"終結本輪（`{CLOSES_ROUND_FIELD}` 缺席或為 true），拒絕產生提示詞：\n"
        f"{listed}\n"
        "  ——終結本輪的每一筆都有兩種可能，本守衛分不出來，由你判斷：\n"
        "  (a) 確實是終局查核：REJECT → 等執行者推修正並補新的 handoff event"
        "（iteration+1）再重跑本指令；APPROVE → 接續 merge／結案流程。\n"
        "  (b) 其實是**中繼關卡**（Design Gate、需求方本地人工審…），本輪尚未結束：\n"
        "      event log 是 append-only 不得改寫，請追加一筆更正用的 review 事件，帶\n"
        f"      `{CLOSES_ROUND_FIELD}: false` 並以 `{CORRECTS_FIELD}` 指名被更正的那一筆，"
        "然後重跑。\n"
        f"      未指名更正對象的 `{CLOSES_ROUND_FIELD}: false` 只代表它自己，"
        "**不會**重開已終局的一輪。\n"
        "      欄位語意見 docs/CONTROL_PLANE_CONTRACT.md。")


def _rev(rev: str) -> str | None:
    """把任意 commit-ish 解析成完整 object id；解不出來回 None。"""
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet",
                        f"{rev}^{{commit}}"], capture_output=True, text=True)
    return r.stdout.strip() or None


def _assert_handoff_matches_branch_head(ev: dict) -> None:
    """handoff 的 source_sha 必須指向該分支當前 HEAD 這個 commit，否則拒絕產生提示詞。

    ML-OUTCOME-SIMPLE-LEAK2 iteration 4 的教訓：Coordinator 派了新 iteration 產生新 commit
    卻沒補 handoff，本腳本照讀最新 handoff 帶出過期 SHA，查核者被迫程序性 REJECT——
    整輪跨家族查核燒在一件機器兩秒可查的事上。此後「送審前 SHA 一致」由這裡強制，
    不靠 Coordinator 記得。分支不存在（已 merge 清理）或無法解析時同樣拒絕，
    請改以 merge 後流程處理而非對舊 handoff 產生提示詞。

    **兩邊都先經 `git rev-parse` 解析成完整 object id 再比對**，不做字串相等比較。
    2026-07-28 UX-TEAM-HOTZONE1 實例：handoff 記短碼 `c9868b7`、`rev-parse` 回完整
    40 碼，字串比對判定不一致而誤擋——但兩者本來就是同一個 commit。事件裡的
    `source_sha` 短碼與完整碼**都是合法寫法**（本 repo 的歷史事件兩種都有），
    該成立的性質是「指向同一個 commit」，不是「字串長得一樣」。
    """
    branch, sha = ev.get("branch", ""), ev.get("source_sha", "")
    if not branch or not sha:
        sys.exit("錯誤：handoff 缺 branch 或 source_sha 欄位，無法核對，拒絕產生提示詞。")
    head = _rev(f"refs/heads/{branch}")
    if head is None:
        sys.exit(f"錯誤：分支 {branch} 不存在（已 merge 清理？）。"
                 "已結案的卡不該再產生查核提示詞；未結案請先恢復分支。")
    recorded = _rev(sha)
    if recorded is None:
        sys.exit(
            f"錯誤：handoff 的 source_sha 無法解析成 commit，拒絕產生提示詞。\n"
            f"  handoff source_sha：{sha}\n"
            "  該 commit 不在本機（未 fetch？打錯？）——確認後再重跑本指令。")
    if recorded != head:
        sys.exit(
            f"錯誤：handoff 的 source_sha 與分支 HEAD 不是同一個 commit，拒絕產生提示詞。\n"
            f"  handoff source_sha：{sha}（解析為 {recorded}）\n"
            f"  {branch} HEAD：{head}\n"
            "  成因通常是 push 了新 commit 卻沒補 handoff event——先補 handoff 再重跑本指令。")


def card_sections(card_id: str, wanted: tuple[str, ...]) -> str:
    path = ROOT / f"docs/tasks/{card_id}.md"
    if not path.exists():
        sys.exit(f"錯誤：找不到卡片檔 {path}")
    out: list[str] = []
    keep = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            keep = any(token in heading for token in wanted)
        if keep:
            out.append(line)
    sections = "\n".join(out).strip()
    if not sections:
        print(
            f"警告：{card_id} 找不到可錨定的驗收章節"
            f"（標題須含：{', '.join(wanted)}）；review prompt 將退化為全文驗收。",
            file=sys.stderr,
        )
    return sections


# --- 查核環境：detached worktree（HANDOFF_CONTRACT.md §3／§5） ---
def review_worktree_block(card_id: str, ev: dict) -> str:
    """產生「建立獨立 detached 查核 worktree」的指令段。

    舊版輸出的是「進駐 worktree：<執行者的 worktree>（指令在此目錄執行）」，
    直接違反 `HANDOFF_CONTRACT.md` §3 receiver acceptance checklist 的
    「查核環境隔離……**不得在執行者的 worktree 上查核**」。

    契約寫了、工具卻教相反的事，而被照著執行的是工具——執行者的 worktree 可能
    有未提交變更、可能已被推進到別的 commit，查核者重跑還會覆寫交付 artifact
    （`CONTROL_PLANE_CONTRACT.md`：受查 artifact 是已提交版本，不是重跑產物）。
    這裡輸出的是 §5 的建立指令與 §3 的兩項自我驗證（工作區乾淨、HEAD ＝ source_sha）。
    """
    sha = ev.get("source_sha", "")
    rel = f".claude/worktrees/{card_id.lower()}-review"
    exec_wt = ev.get("worktree", "") or "（handoff 未記錄）"
    return f"""### 查核環境（HANDOFF_CONTRACT.md §3／§5）

**不得在執行者的 worktree 上查核。** 建立獨立 detached worktree，所有指令在該目錄執行：

```bash
git -C {MAIN_ROOT} worktree add --detach {rel} {sha}
cd {MAIN_ROOT}/{rel}
git status --short      # 必須為空
git rev-parse HEAD      # 必須等於 {sha}
```

- 路徑已被前一輪占用時：先 `git -C {MAIN_ROOT} worktree remove {rel}`；若該目錄有未提交
  內容而移除失敗，改用 `{rel}2` 之類的新路徑——**不得改用執行者的 worktree**。
- 查核結束後清理：`git -C {MAIN_ROOT} worktree remove {rel}`。
- 執行者的 worktree（`{exec_wt}`）**僅供對照，不得進駐**。
- 上列只涵蓋「環境隔離」一項；接收驗證其餘各項（SHA 已推送、本地與遠端 tip 一致、
  分支不含 `docs/control-plane/**` 與 `docs/TASKS.md`、lease 有效…）見
  `docs/HANDOFF_CONTRACT.md` §3 逐項完成。"""


# --- 重現指令：依實際改動路徑判定卡片型態 ---
# 「Python 側」不只 .py：migration 與依賴變更同樣由 pytest／ruff 這一側驗證。
_PY_EXTRA = {"pyproject.toml", "uv.lock"}

# 「讀完就是驗證完」的檔案。這份清單是**白名單**而非殘餘集合：
# iteration 0 把「非 Python 且非 web/」的一切都當成文件，於是 `scripts/scrape-daily.sh`
# 這種可執行變更被靜默判成「純文件卡／沒有標準重現指令」（REVIEW-005 F1，blocking）。
# 可執行的東西被說成不用驗，比不給指令更糟——所以只有明確認得的文件副檔名才算文件，
# 其餘一律進 unknown 並在輸出裡吵。
_DOC_SUFFIXES = (".md", ".rst", ".txt")


def changed_paths(sha: str) -> tuple[list[str], str | None]:
    """回傳 (main...sha 的改動路徑, 無法取得時的原因)。取不到時**不猜**。"""
    if not sha:
        return [], "handoff 缺 source_sha"
    r = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", f"main...{sha}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        detail = (r.stderr.strip().splitlines() or ["git diff 失敗"])[-1]
        return [], f"`git diff --name-only main...{sha}` 失敗：{detail}"
    paths = [p for p in r.stdout.splitlines() if p.strip()]
    if not paths:
        return [], f"`main...{sha}` 沒有任何改動路徑（分支與 main 無差異？）"
    return paths, None


def _split_paths(paths: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """(Python 側, 前端, 文件, **未知**)。未知不是殘餘垃圾桶，是要被講出來的那一類。"""
    web = [p for p in paths if p.startswith("web/")]
    py = [p for p in paths if not p.startswith("web/")
          and (p.endswith((".py", ".sql")) or p in _PY_EXTRA)]
    rest = [p for p in paths if p not in web and p not in py]
    docs = [p for p in rest if p.endswith(_DOC_SUFFIXES)]
    unknown = [p for p in rest if p not in docs]
    return py, web, docs, unknown


_PY_BLOCK = """```bash
uv run ruff check
uv run pytest -q
```"""

# 本專案 web/ 下沒有任何 eslint 設定檔，package.json 的 lint 腳本是 `next lint`：
# 跑下去會進入互動式初始化精靈，卡在 prompt 而不是回報驗證失敗。查核者若把它
# 當成標準前端驗證指令執行，得到的是一個假的紅燈——所以這裡主動排除。
_WEB_BLOCK = """```bash
cd web
npm ci                  # 查核 worktree 是新建的，沒有 node_modules
npm run build:check     # 全路由編譯＋型別檢查（獨立 distDir，不影響 dev 快取）
npm test
```

- **不要跑 `npm run lint`**：本專案未設定 ESLint，`lint` 腳本是 `next lint`，執行會進入
  互動式初始化精靈。那**不是驗證失敗，不得據此開 finding**。
- `npm ci` 不可略過：新建 worktree 沒有 `node_modules`，跳過會讓型別檢查與 build
  整片變紅——那是環境假象，不是被審改動的缺陷。"""


def repro_commands(ev: dict) -> str:
    """依 handoff 的實際改動路徑輸出對應的重現指令。

    舊版對所有卡硬編 `uv run ruff check` ＋ `uv run pytest -q`。對改動集中在 `web/`
    的前端卡，那兩行掃不到任何被審改動，跑完全綠**證明不了任何事**——工具給的是
    寫死的預設值，而該成立的性質是「跑得到這次改動的驗證指令」。

    判不出來時（取不到 diff、或改動落在腳本認不得的路徑）**明講判不出來**，
    不退回任何預設指令組：錯的綠燈比沒有燈更糟。

    REVIEW-005 F1（blocking）：iteration 0 只分 Python／前端／其他三類，且「只有其他」
    一律判成純文件卡。`scripts/scrape-daily.sh` 因此得到「沒有標準重現指令」——
    **可執行的東西被說成不用驗**。修法是把文件改成白名單（`_DOC_SUFFIXES`），
    認不得的路徑一律進 unknown，且 unknown 只要非空就一定在輸出裡出現，
    不論旁邊有沒有 Python／前端改動。
    """
    sha = ev.get("source_sha", "")
    paths, err = changed_paths(sha)
    if err:
        return ("⚠️ **無法判定卡片型態**（" + err + "）——請自行以 "
                f"`git diff --name-only main...{sha}` 看實際改動選擇驗證指令，"
                "**不要**套用任何預設指令組。")
    py, web, docs, unknown = _split_paths(paths)
    tally = (f"型態判定依據：`main...{sha[:7]}` 共 {len(paths)} 個檔案"
             f"（Python 側 {len(py)}、`web/` {len(web)}、文件 {len(docs)}、"
             f"**未知 {len(unknown)}**）。")
    if py and web:
        body = f"**混合卡**，兩組都要跑。\n\nPython 側：\n\n{_PY_BLOCK}\n\n前端側：\n\n{_WEB_BLOCK}"
    elif py:
        body = f"**Python 卡**：\n\n{_PY_BLOCK}"
    elif web:
        body = f"**前端卡**：\n\n{_WEB_BLOCK}"
    elif docs and not unknown:
        body = ("**純文件卡**（改動全為 "
                + "、".join(f"`{s}`" for s in _DOC_SUFFIXES)
                + " 檔）：**沒有標準重現指令**——依卡面〈驗證〉章節與交付摘要核對，"
                "勿套用 Python 或前端的預設指令組。")
    else:
        body = ("⚠️ **無法判定卡片型態**：改動沒有落在任何腳本認得的類別。"
                "**不要**套用任何預設指令組，請依下列路徑自行決定驗證方式。")
    if unknown:
        listed = "\n".join(f"  - `{p}`" for p in unknown[:12])
        more = f"\n  - …另有 {len(unknown) - 12} 項" if len(unknown) > 12 else ""
        body += (
            "\n\n⚠️ **下列改動不在自動判定範圍**（非 Python 側、非 `web/`、非文件副檔名）——"
            "腳本**不猜**它們該怎麼驗（可能是 shell 腳本、Dockerfile、CI 設定、資料檔…），"
            f"請自行判斷並在 findings 說明你怎麼驗的：\n\n{listed}{more}")
    if docs and (py or web or unknown):
        body += f"\n\n（另有 {len(docs)} 個文件檔以閱讀核對，不需指令。）"
    return f"{tally}\n\n{body}"


# --- 獨立性：只保證下限，不宣稱上限 ---
#
# 這一段曾經試圖從卡面自由文字推導出「這張卡需要哪一種查核獨立性」，
# 被同一位跨家族查核者連續三輪以更根本的反例打穿（DEV-REVIEW-PROMPT-GUARD1）：
#
#   iteration 0（REVIEW-005）first-match scalar
#     → 「先跨家族查核，並由需求方人工核可」的 AND 被讀成 OR。
#   iteration 1（REVIEW-007）距離式正則
#     → 條件句「跨家族查核，若失敗或有疑問再人工核可」被讀成二擇一；
#       別名寫死又讓「跨模型或人工」這種明寫的二擇一被誤升為 AND。
#   iteration 2（REVIEW-009）格式字元直連 ＋ 全文 search()
#     → 否定句與引文裡的字樣覆蓋真正要求；
#       「不可由跨家族或人工智慧代理取代」的命中甚至是把「人工智慧」從中切斷。
#
# 中文沒有空白分詞，否定、引文、條件句可任意嵌套。每一輪修法都更嚴謹、每一輪都被更
# 根本的反例打穿——那不是實作品質問題，是路線問題。需求方 2026-07-29 裁定停止推斷。
#
# 現在的性質很簡單：**工具只宣稱一個下限，不宣稱上限。**
# 不宣稱上限，就不可能把需求方寫在卡面的要求說低——三輪的反例全部失去適用對象，
# 不是被更聰明的規則擋掉，是無處可施。要判讀卡面語意的是人，工具只負責把原文攤開。
#
# 機器可讀的獨立性欄位由 DEV-REVIEW-INDEP-FIELD1 承接（含值域與既有卡遷移）。
_TIER_FLOOR = {
    "T4": "跨模型家族（非執行者所屬家族）或人工",
}
_DEFAULT_FLOOR = "新 context／session 即可（不得為執行者本人）"


def card_review_field(card_id: str) -> str | None:
    """卡面 header 的〈查核〉欄原文；找不到回 None。

    只讀第一個 `## ` 標題之前的 header 區塊——正文裡的「查核」二字屬敘述不是欄位。
    **原文照登，不解讀**：這個函式回傳字串，不回傳結論。
    """
    path = _card_path(card_id)
    if path is None:
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if line.lstrip().startswith("-") and "查核：" in line:
            return line.split("查核：", 1)[1].strip()
    return None


def independence(card_id: str, tier: str) -> tuple[str, str]:
    """回傳 (單行摘要, 明細段)。摘要講的是**下限**，不是結論。"""
    floor = _TIER_FLOOR.get(tier, _DEFAULT_FLOOR)
    field = card_review_field(card_id)
    lines = [
        "- **本段只給下限，不給結論。** 腳本不解讀卡面語意——"
        "獨立性要求由你讀卡面決定（理由見 `scripts/review_prompt.py` 的註解："
        "自由文字推斷已連續三輪被否定句、引文與條件句打穿）。",
        f"- tier 推導的下限（{tier}）：{floor}",
    ]
    if field is None:
        print(f"警告：{card_id} 卡面找不到〈查核〉欄，提示詞只能給 tier 下限。",
              file=sys.stderr)
        lines.append("- 卡面〈查核〉欄：**未找到**——**這不代表沒有額外要求**，"
                     "請直接開卡片確認格式與內容，別讓工具替需求方放寬要求。")
    else:
        lines.append(f"- 卡面〈查核〉欄原文（**以此為準**）：`{field}`")
    lines.append(
        "- 卡面若要求得比上述下限嚴（跨家族、人工核可、兩者皆須、先後順序…），"
        "**一律以卡面為準**；判讀有疑義請需求方裁定，**不得自行放寬**。"
        "查核者 ≠ 執行者是所有情況的下限。")
    # 摘要不帶 markdown：呼叫端已把它包進粗體與括號，這裡再加會變成巢狀粗體。
    return f"下限 {floor}；實際要求以卡面〈查核〉欄為準", "\n".join(lines)


def review_gates_block(gates: list[dict]) -> str:
    """已通過但未終結本輪的關卡（Design Gate、本地人工審…）。

    這些裁定是下一位查核者的**前提**：需求方已經在某些爭點上定案，重開那些爭點是
    浪費一輪查核。同時必須講清楚它們不代表本輪結束，否則就複製了守衛原本的誤判。
    """
    if not gates:
        return ""
    blocks = [
        "### 本輪已通過的中繼關卡（**不代表本輪查核已結束**）",
        "",
        "下列關卡已由卡面流程要求先行完成，其裁定為你的前提——**不要重開已定案的爭點**；"
        "你的查核是本輪尚未完成的那一關。",
    ]
    for g in gates:
        blocks += [
            "",
            f"#### {g.get('actor', '?')}　{g.get('occurred_at', '?')}",
            "",
            f"- 結論：{g.get('review_result', '（未填）')}",
            f"- 事件：`{g.get('event_id', '?')}`（state_version {g.get('state_version')}）",
            "",
            str(g.get("evidence", "（無）")),
        ]
    return "\n".join(blocks)


def build_prompt(card_id: str) -> str:
    ev, gates = latest_handoff(card_id)
    tier = ev.get("tier", "T3")
    redline = tier == "T4"
    db_scope = ev.get("db_scope", "none")
    sections = card_sections(card_id, ("驗收", "驗證", "Gate"))
    checklist = sections if sections else "（卡片無明列章節，依卡片全文與 spec 驗收）"
    baseline = baseline_check(card_id)
    if baseline:
        checklist += "\n\n" + baseline
    indep, indep_detail = independence(card_id, tier)
    gates_block = review_gates_block(gates)
    gates_section = f"\n{gates_block}\n" if gates_block else ""
    db_note = {
        "none": "本卡不涉 DB。",
        "read": "本卡 db_scope=read——你的所有查詢**必須唯讀**，嚴禁任何寫入。",
    }.get(db_scope, f"本卡 db_scope={db_scope}——寫入範圍以卡片宣告為準，逾越即 finding。")
    return f"""## {card_id} 獨立查核提示詞〔{tier}{'；🔴紅線' if redline else ''}〕

你是 cpbl-analytics 專案 **{card_id}** 的獨立查核者（{indep}）。
你的職責是對照目標與證據驗收：**發現缺陷只留 finding 退回，不得修改被審分支上的任何檔案**。

### 查核對象

- 功能：{ev.get('feature', '（見卡片）')}
- 分支：`{ev.get('branch', '?')}` @ **{ev.get('source_sha', '?')[:7]}**（完整 SHA {ev.get('source_sha', '?')}）
- 卡片：`docs/tasks/{card_id}.md`

### 獨立性要求

**{indep}**

{indep_detail}

{review_worktree_block(card_id, ev)}

### 環境紅線

{db_note}

### 執行者交付摘要（handoff evidence 原文）

{ev.get('evidence', '（無）')}
{gates_section}
### 卡面驗收條件（逐項核對）

{checklist}

### 基本重現指令

{repro_commands(ev)}

（卡片與交付摘要中列出的專屬驗證指令一併重跑。）

### 產出格式

回覆 **APPROVE 或 REJECT**，附 findings 清單（每條含 severity／證據／建議處置）
與你實際重跑的指令與輸出摘要。依本專案慣例：**APPROVE（零阻塞 findings）後
Coordinator 將直接 merge** 並將結果回傳執行者，部署與後續另由需求方確認；
REJECT 則退回原執行者於原分支修正（iteration+1）。你的結論將由需求方轉錄為
review event（source_sha={ev.get('source_sha', '?')[:7]}）留痕。
"""


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("用法：uv run python scripts/review_prompt.py <CARD_ID>")
    print(build_prompt(sys.argv[1]))


if __name__ == "__main__":
    main()
