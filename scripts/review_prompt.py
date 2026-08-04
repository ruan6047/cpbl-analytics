"""審核提示詞產生器：從 control-plane 最新 handoff event + 卡片檔自動生成查核提示詞。

用法（**在帶有 main 的 checkout 執行**，見下）：
    uv run python scripts/review_prompt.py <CARD_ID>            # 印到 stdout
    uv run python scripts/review_prompt.py <CARD_ID> | pbcopy   # 直接進剪貼簿貼給查核者

**先產生提示詞，再建查核 worktree**——順序不能反。event log 依契約只存在於 main，執行分支
不攜帶，所以在交付 SHA 的 detached worktree 裡跑本腳本必然讀不到該卡的 handoff。而
`HANDOFF_CONTRACT.md` §3 的驗收清單要求查核者建那個 worktree，照清單順序做的人第一步就會
撞到（2026-08-04 `DEV-BASELINE-GUARD-DECL1` 因此被誤退一輪）。撞到時本腳本會分辨成因並給
指令，不再一律報「尚未交付查核」（DEV-REVIEW-PROMPT-BASE1）。

資料來源（零 AI 成本、永遠反映最新交接狀態）：
- docs/control-plane/events.jsonl：該卡最新 handoff event（分支、worktree、source_sha、
  tier、db_scope、執行者交付摘要）
- docs/tasks/<CARD_ID>.md：標題含「驗收」「驗證」「Gate」的章節原文、卡面〈查核〉欄、
  卡面 header 的 `review_independence` 欄位（機器可讀的查核獨立性宣告）
- git diff main...<source_sha>：該卡實際改動路徑（決定重現指令）

慣例（CONTROL_PLANE_CONTRACT.md「Review→merge 慣例」）：查核 APPROVE（零阻塞
findings）後 Coordinator 直接 merge，結果回傳執行者，部署另由需求方確認。

**產出物是查核者實際照著做的那一份**（DEV-REVIEW-PROMPT-GUARD1）：契約寫了什麼、
卡面要求什麼，若沒出現在這裡就等於沒有。因此三件事一律由輸出本身承載，不靠
「查核者自己會知道」——查核環境（HANDOFF_CONTRACT §3 的 detached worktree）、
重現指令（依實際改動路徑而非寫死）、獨立性（tier 下限＋卡面 `review_independence`
宣告＋〈查核〉欄原文照登；**不從自由文字推斷**，DEV-REVIEW-INDEP-FIELD1）。
三者任一判不出來時**明講判不出來**，不得靜默退回預設值。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

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
# 欄位以全形空格分隔（同一行還有 Initiative 等欄），故切到 `　` 或行尾為止。
_BASELINE_FIELD_RE = re.compile(r"spec 基線：\s*([^　\n]+)")
# 括號（全形／半形，含未閉合）內是說明文字或 markdown 連結目標，兩者都不是宣告值。
_PARENTHETICAL_RE = re.compile(r"（[^）]*(?:）|$)|\([^)]*(?:\)|$)")
# 複合基線的分隔符：一張卡可同時受兩份 spec 約束。刻意只認 `＋`／`、`（實際卡面用法），
# 不認逗號分號——那些在說明散文裡太常見，認了等於把剛堵上的破口從另一邊打開
#（`v2，因 v1 過窄` 會被切成兩個子句而抽出 v1）。
_COMPOSITE_SEP_RE = re.compile(r"[＋+、]")
# 版本 token 必須有字元邊界：`rev1`／`v1beta`／`SPEC_v1` 都**不是**宣告版本。無邊界時
# `v\d+` 會在 `rev1` 裡撈到 `v1`——卡面正好有「卡面修訂：rev2」這種相鄰欄位，混用時
# 「spec 基線：rev1」會被判成宣告了 v1 而放行（查核 finding DECL1-F001 實測）。
# 邊界只排除 ASCII 英數與底線，不排除中日文——「基線v1」仍算宣告。
_VERSION_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z_])v\d+(?:\.\d+)*(?![0-9A-Za-z_])")


def baseline_declaration(text: str) -> tuple[str | None, set[str]]:
    """卡面 `spec 基線` 欄的原文，與**宣告值**中的版本 token 集合。

    宣告值 ≠ 整段欄位文字。欄位常在版本後接括號說明（`v2（v1 範圍過窄，見背景節）`），
    說明裡出現的版本是敘述、不是宣告；若整段一起抽 token，卡面等於可以「解釋自己
    填錯的理由」來通過守衛——2026-08-03 `INGEST-PLAYER-BIO-GAP2` 與
    `INGEST-SPLITS-IMPORT-RESTATE1` 兩卡把「spec 基線」誤當本卡 spec 修訂號而填 v2，
    說明文字裡剛好提到父卡的 v1，守衛全綠放行，最後由獨立查核者以 PREFLIGHT_FAILED
    擋下，燒掉一輪送審。與 UX-TEAM-SPLIT-SCOPE1（填卡名而非版本）同型：
    **檢查哨兵值的缺席，不等於檢查該成立的性質**。

    抽取規則：
    1. 欄位切到全形空格或行尾（同一行還有其他欄位）。
    2. 去掉括號內文字——說明與 markdown 連結目標都在此排除。
    3. 其餘以複合分隔符切成宣告子句，允許複合基線
       （`GAME_RECAP v1.3＋PRODUCT_UX_BLUEPRINT v0.2`），那類卡確實同時受兩份 spec 約束。
    4. **每個子句只取第一個版本 token**：子句內第一個 token 才是宣告值，其後為敘述。
       token 取整段相等而非子字串，否則 `v1.0` 會被 `v1` 誤放行。

    以文件連結表示基線（無版本 token）時回空集合，由呼叫端退回人工核對，
    不得當成「不一致」——那是誤報，不是防線。
    """
    m = _BASELINE_FIELD_RE.search(text)
    if not m:
        return None, set()
    raw = m.group(1).strip()
    declared = _PARENTHETICAL_RE.sub("　", raw)
    versions = set()
    for clause in _COMPOSITE_SEP_RE.split(declared):
        first = _VERSION_TOKEN_RE.search(clause)
        if first:
            versions.add(first.group(0))
    return raw, versions


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
    判定只看 `baseline_declaration()` 抽出的**宣告值**：括號說明不計（否則卡面填錯版本
    卻在說明裡提到正確版本就會被判一致），且允許複合基線（父卡版本是其一即可）。
    """
    path = _card_path(card_id)
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8")
    m_init = _INITIATIVE_RE.search(text)
    if not m_init:
        return ""
    parent_id = m_init.group(1)
    child_raw, child_vers = baseline_declaration(text)

    parent_path = _card_path(parent_id)
    parent_raw, parent_vers = None, set()
    if parent_path is not None:
        parent_raw, parent_vers = baseline_declaration(parent_path.read_text(encoding="utf-8"))

    lines = [
        "### spec 基線一致性（canonical baseline-cascade §5）",
        "",
        f"- Initiative 父卡：{parent_id}"
        + (f"（`{parent_path.relative_to(ROOT)}`）" if parent_path else "（**卡片檔不存在**）"),
    ]
    if parent_vers and child_vers:
        verdict = "一致" if parent_vers & child_vers else "**不一致——舊基線交付，直接退回**"
        lines.append(
            f"- 父卡當前 spec 基線：`{'／'.join(sorted(parent_vers))}`；"
            f"本卡卡面 spec 基線：`{'／'.join(sorted(child_vers))}` → {verdict}"
        )
        lines.append(
            f"  - 卡面原文：父卡「{parent_raw}」／本卡「{child_raw}」"
            "（判定只取宣告值，括號說明不計入）"
        )
    else:
        missing = "父卡" if not parent_vers else "本卡"
        lines.append(
            f"- {missing}的 spec 基線欄未宣告可解析的版本（缺欄，或以文件連結／卡名表示）"
            "，無法自動核對——**人工核對**：對照父卡「基線變更紀錄」"
            "與本卡範圍是否仍在當前基線內。"
        )
    lines.append(
        "- 本段為產生提示詞當下的快照；查核時以父卡**當前**檔案再核對一次，"
        "不一致即退回（不進 finding 協商）。"
    )
    return "\n".join(lines)


CONTROL_PLANE_REL = "docs/control-plane/events.jsonl"


def _events_in(text: str, card_id: str) -> list[dict]:
    """從 event log 原文取出該卡的事件（容忍空行）。"""
    return [
        e for line in text.splitlines() if line.strip()
        if (e := json.loads(line)).get("card_id") == card_id
    ]


def card_events(card_id: str) -> list[dict]:
    """該卡的所有 event，維持 append-only 的原始順序。

    **來源固定是本 checkout（`ROOT`）**，不偷偷改讀別處：提示詞的內容必須來自一份
    說得出是哪裡的事實。本 checkout 讀不到時由 `_exit_without_handoff()` 診斷後給指引，
    而不是靜默換來源——後者會讓「這份提示詞根據的是哪一版 event log」變得不可追。
    """
    return _events_in((ROOT / CONTROL_PLANE_REL).read_text(encoding="utf-8"), card_id)


def _checkout_description(path: Path) -> str:
    """`<短SHA>（分支名／detached）`，取不到時明講取不到。"""
    def git(*args: str) -> str | None:
        r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    sha = git("rev-parse", "--short", "HEAD")
    if sha is None:
        return "無法解析 HEAD"
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    return f"{sha}（{'detached HEAD' if branch == 'HEAD' else branch}）"


def _other_control_plane_sources() -> list[tuple[str, str]]:
    """本 checkout 以外、可能帶有 control-plane 的來源：(來源描述, event log 原文)。

    只用於「找不到 handoff」時的診斷，不參與提示詞內容。兩個來源對應兩種已實際發生的
    成因：查核者在**交付 SHA 的 detached worktree** 內產生提示詞（執行分支依契約不攜帶
    control-plane），以及**主 checkout 落後於 origin/main**。兩者症狀相同，故都要查。
    """
    sources: list[tuple[str, str]] = []
    if MAIN_ROOT != ROOT:
        path = MAIN_ROOT / CONTROL_PLANE_REL
        try:
            sources.append((f"主 checkout `{MAIN_ROOT}`（{_checkout_description(MAIN_ROOT)}）",
                            path.read_text(encoding="utf-8")))
        except OSError:
            pass
    r = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"origin/main:{CONTROL_PLANE_REL}"],
        capture_output=True, text=True)
    if r.returncode == 0 and r.stdout:
        sources.append(("`origin/main`", r.stdout))
    return sources


def _exit_without_handoff(card_id: str) -> NoReturn:
    """本 checkout 找不到 handoff 時，先分辨成因再退出（DEV-REVIEW-PROMPT-BASE1）。

    舊版一律吐「沒有 handoff event（尚未交付查核）」——那句話指控執行者未交付，但最常見的
    成因其實是**產生提示詞的位置不對**：control-plane 依契約只存在於 main，而
    `HANDOFF_CONTRACT.md` §3 要求查核者建交付 SHA 的 detached worktree，照清單順序做的人
    第一步就會撞到這個假性失敗。2026-08-04 `DEV-BASELINE-GUARD-DECL1` 因此被誤退一輪。

    兩種輸出刻意完全不同：別處找得到 → 說明成因並給可直接執行的指令；到處都沒有 → 才是
    真的尚未交付，並列出已查過哪些來源（讓「查過了」本身可稽核）。
    """
    found = [
        (label, handoffs[-1])
        for label, text in _other_control_plane_sources()
        if (handoffs := [e for e in _events_in(text, card_id) if e.get("type") == "handoff"])
    ]
    if not found:
        checked = "、".join(["本 checkout"] + [label for label, _ in _other_control_plane_sources()])
        sys.exit(
            f"錯誤：{card_id} 尚未交付查核——查無任何 handoff event。\n"
            f"已查來源：{checked}。"
        )
    label, ev = found[0]
    sys.exit(
        f"錯誤：本 checkout 讀不到 main 的 control-plane，因此看不到 {card_id} 的 handoff event。\n"
        f"**這不是「執行者未交付」**：{label} 有 {ev.get('event_id')}"
        f"（source_sha {str(ev.get('source_sha'))[:7]}，{ev.get('occurred_at')}）。\n\n"
        f"成因：`{CONTROL_PLANE_REL}` 依 CONTROL_PLANE_CONTRACT 只存在於 main，執行分支不攜帶；"
        f"本 checkout 目前是 {_checkout_description(ROOT)}。\n"
        f"（另一種同症狀的成因是主 checkout 落後於 origin/main，下面的指令一併涵蓋。）\n\n"
        f"處置——先在帶有 main 的 checkout 產生提示詞，再依提示詞建交付 SHA 的 detached worktree：\n"
        f"  cd {MAIN_ROOT} && git pull --ff-only && uv run python scripts/review_prompt.py {card_id}"
    )


def latest_handoff(card_id: str) -> tuple[dict, list[dict]]:
    """回傳 (最新 handoff event, 該 handoff 之後已發生的 review 事件)。

    第二個回傳值只在「這些 review（經更正後）都沒有終結本輪」時才非空——那是多關卡的卡
    （Design Gate、本地人工審先於跨家族查核）；它們的裁定是下一位查核者的前提，
    必須帶進提示詞，不能只留在 event log 裡。
    """
    ev = None
    events = card_events(card_id)
    for e in events:
        if e.get("type") == "handoff":
            ev = e  # append-only → 最後一筆即最新
    if ev is None:
        _exit_without_handoff(card_id)
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
# 機器可讀的獨立性欄位由 DEV-REVIEW-INDEP-FIELD1 承接（見下方 `review_independence`）：
# 那是**結構化宣告**，與這裡的下限並存——欄位不存在時本段照給下限，並明示宣告缺席。
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


# --- 獨立性欄位：卡面 `review_independence`（DEV-REVIEW-INDEP-FIELD1） ---
#
# GUARD1 三輪的教訓不是「正則寫得不夠好」，是**不該從自由文字推流程門檻**。本段的
# 欄位是**結構化宣告**：解析只做語法檢查與值域比對，一個中文字都不參與判定。因此
# 三輪的四類反例（AND 複合、條件句、否定句與引文、「人工智慧」詞邊界）在這裡全部
# **無處可施**——不是被更聰明的規則擋掉，是它們所在的自由文字根本沒被讀成要求。
# 〈查核〉欄照舊原文照登；欄位存在時它退為人可讀補充。**欄位缺席一律明示**
# （紅線 2）：tier 下限與卡面原文照舊，但輸出會講明「這張卡沒有機器可讀宣告」，
# 不讓「缺欄」與「工具本來就只給下限」長得一模一樣。
#
# 職權劃分（docs/CONTROL_PLANE_CONTRACT.md）：
#   卡面 `review_independence` ＝ **靜態要求（應然）**：這張卡該有幾關、每關要什麼
#     獨立性、順序為何。
#   event log `closes_review_round`／`corrects_event_id` ＝ **動態進度（實然）**：
#     本輪實際跑到哪一關、誰查的、結束沒。
# 兩者互不覆寫、互不為事實來源。本欄位**不參與任何守衛放行判定**——
# `_assert_no_review_supersedes_handoff()` 與 `review_gates_block()` 完全不讀它，
# 否則 GATE1 的「存在終結本輪者即拒絕」語意會被第二個來源污染。唯一交會點是
# **並列印出**供人判讀：不仲裁、不產生結論、不因宣告與事件不一致而擋下任何東西。
REVIEW_INDEPENDENCE_FIELD = "review_independence"

# 值域（Q1 定案）：有序清單，單一元素＝單一關卡，清單順序＝關卡先後。
# 「兩者皆須但不限順序」**不支援**（掃描 119 張卡出現 0 次），要兩關就寫兩個元素。
_INDEPENDENCE_VALUES = {
    "context": "新 context／session 即可，不得為執行者本人",
    "cross_family": "跨模型家族的查核者，非執行者所屬家族",
    "cross_family_or_human": "跨模型家族或需求方人工，二擇一",
    "human": "需求方人工審，不得由 AI 代理",
}
_INDEPENDENCE_SHORT = {
    "context": "新 context",
    "cross_family": "跨家族",
    "cross_family_or_human": "跨家族或人工",
    "human": "人工審",
}
# 欄名一律 ASCII。冒號同時接受半形與全形，是因為卡面 header 其餘欄位慣用全形「：」。
#
# **整行錨定**（iteration 2 REVIEW REJECT F2）：iteration 2 只檢查「這個 bullet 含
# `review_independence` 字樣」，於是 `- note: review_independence: [human]` 這種**敘述**
# 會被解析成宣告——那正是本卡要離開的病（把自由文字讀成流程要求），只是換了個位置
# 復發。現在整行必須精確符合契約格式：`- ` 之後緊接完整 key，才算宣告。
# `\b` 讓 `review_independence_note:` 這類**相似 key** 自然不匹配（`_` 是 word char，
# key 之後沒有詞邊界），不需另外列舉排除。
#
# 錨定變嚴之後「寫錯格式＝被當成沒宣告」的風險由 F1 的修法承接：缺欄現在會在提示詞裡
# **明示**「機器可讀宣告缺席」，不再與正常 fallback 混為一談，所以嚴格錨定不會製造靜默。
_INDEP_LINE_RE = re.compile(
    rf"^\s*-\s*`?{REVIEW_INDEPENDENCE_FIELD}`?\s*[:：]\s*(.*?)\s*$")
# 行首就是本欄位、但格式不合契約（例：漏冒號）——這是**寫壞**不是敘述，fail loud。
_INDEP_LINE_PREFIX_RE = re.compile(rf"^\s*-\s*`?{REVIEW_INDEPENDENCE_FIELD}\b")


def _independence_syntax_help() -> str:
    return (f"寫法：卡面 header 獨立一行 `- {REVIEW_INDEPENDENCE_FIELD}: [human, cross_family]`"
            "（有序清單；單一元素＝單一關卡，順序＝關卡先後）。"
            f"值域：{'／'.join(f'`{v}`' for v in sorted(_INDEPENDENCE_VALUES))}。"
            "語意與遷移程序見 docs/TEMPLATES.md、職權劃分見 docs/CONTROL_PLANE_CONTRACT.md。")


def _parse_independence_value(card_id: str, value: str) -> list[str]:
    """把欄位值解析成有序清單。語法／值域不合即 fail loud，不當成缺席。

    比照 `closes_review_round` 的先例：欄位**缺席**有明確定義的行為（tier 下限＋
    卡面原文照登），把**寫壞**當成缺席帶過，就是讓一個打字錯誤靜默放寬查核要求。
    """
    fail = (f"錯誤：{card_id} 卡面 `{REVIEW_INDEPENDENCE_FIELD}` 的值 "
            f"{value!r} 無效，拒絕產生提示詞。\n  ")
    tail = ("\n  拒絕臆測：欄位缺席另有明確定義的行為，寫壞不會被當成缺席帶過——"
            "請先修正卡面再重跑本指令。")
    if not (value.startswith("[") and value.endswith("]")):
        sys.exit(f"{fail}值不是清單（必須以 `[` 開頭、`]` 結尾）。"
                 f"{_independence_syntax_help()}{tail}")
    inner = value[1:-1]
    if not inner.strip():
        sys.exit(f"{fail}空清單沒有語意——沒有額外要求就整行刪掉（缺欄行為明確定義），"
                 f"要宣告就至少一個關卡。{_independence_syntax_help()}{tail}")
    items = [x.strip() for x in inner.split(",")]
    bad = [x for x in items if x not in _INDEPENDENCE_VALUES]
    if bad:
        listed = "、".join(repr(x) for x in bad)
        sys.exit(f"{fail}下列元素不在值域：{listed}。{_independence_syntax_help()}"
                 "\n  「兩者皆須」請寫成兩個元素（例 `[cross_family, human]`），"
                 f"不要自造合成值。{tail}")
    return items


def card_review_independence(card_id: str) -> list[str] | None:
    """卡面 header 的 `review_independence` 有序清單；欄位缺席回 None。

    只讀第一個 `## ` 標題之前的 header 區塊，且**整行**須符合契約格式
    `- review_independence: [...]`：正文、程式碼區塊、以及 header 裡夾在別的文字中的
    同名字樣（`- note: review_independence: [human]`）一律是敘述，不是宣告——
    本欄位存在的理由就是「不從自由文字讀流程要求」，解析自己更不能破例。
    """
    path = _card_path(card_id)
    if path is None:
        return None
    raw: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        m = _INDEP_LINE_RE.match(line)
        if m is not None:
            raw.append(m.group(1).strip())
        elif _INDEP_LINE_PREFIX_RE.match(line):
            sys.exit(f"錯誤：{card_id} 卡面有一行以 `{REVIEW_INDEPENDENCE_FIELD}` 起始但格式不合"
                     f"契約（原行：{line.strip()!r}），拒絕產生提示詞。"
                     f"\n  {_independence_syntax_help()}")
    if not raw:
        return None
    if len(raw) > 1:
        sys.exit(f"錯誤：{card_id} 卡面 header 有 {len(raw)} 行 `{REVIEW_INDEPENDENCE_FIELD}`"
                 f"（值：{raw}），無法判定以哪一行為準，拒絕產生提示詞。"
                 "\n  多關卡請寫成同一行的有序清單，不是多行。"
                 f"\n  {_independence_syntax_help()}")
    return _parse_independence_value(card_id, raw[0])


def _declared_gates_lines(declared: list[str]) -> list[str]:
    """把宣告的關卡序列翻成人可讀，並講明它是留痕不是保證。"""
    seq = "；".join(f"第 {i} 關 `{v}`（{_INDEPENDENCE_VALUES[v]}）"
                    for i, v in enumerate(declared, 1))
    lines = [f"- 卡面 `{REVIEW_INDEPENDENCE_FIELD}` 宣告 {len(declared)} 關"
             f"（清單順序即關卡先後）：{seq}"]
    if len(declared) > 1:
        lines.append(
            "- 你負責的是本輪**尚未完成的那一關**；已完成的關卡以 event log 為準"
            "（見〈本輪已通過的中繼關卡〉一節；沒有該節即代表本輪尚無中繼關卡留痕，"
            "**這不擋你查核**）。卡面欄位只說有幾關，**不說跑到哪一關**。")
    lines.append(
        f"- **`{REVIEW_INDEPENDENCE_FIELD}` 是留痕，不是保證**：它記錄需求方宣告的要求，"
        "工具**無法驗證**實際查核者是否真的跨家族、是否真的是人（查核結論由需求方人工"
        "轉錄，本專案沒有可信的查核者身分來源）。下列並列資訊供你與需求方判讀，"
        "**工具不做一致性仲裁，也不據此擋下任何流程**。")
    return lines


def _actor_parallel_lines(events: list[dict]) -> list[str]:
    """把宣告值與 event log 的實況並列（Q4 的低成本強化）——只並列事實，不下結論。"""
    reviews = [e for e in events if e.get("type") == "review"]
    if not reviews:
        return ["- 對照（**輔助判讀，非保證**）：本卡 event log 尚無任何 review 事件。"]
    last = reviews[-1]
    return [f"- 對照（**輔助判讀，非保證**）：最近一筆 review 事件 "
            f"`{last.get('event_id', '?')}`　actor：{last.get('actor', '?')}；"
            f"review_result：{last.get('review_result', '（未填）')}。"
            "與宣告值不一致時（例：宣告要跨家族、最近一輪 actor 卻同家族），"
            "請向需求方確認後再開始——工具只並列事實，不替任何人下結論。"]


def independence(card_id: str, tier: str, events: list[dict] | None = None) -> tuple[str, str]:
    """回傳 (單行摘要, 明細段)。摘要講的是**下限**，不是結論。

    卡面有 `review_independence` 時多印宣告的關卡序列，並與 event log 實況並列；
    **欄位缺席時明示缺席**（紅線 2），tier 下限與卡面〈查核〉欄原文照舊不放寬。
    """
    floor = _TIER_FLOOR.get(tier, _DEFAULT_FLOOR)
    field = card_review_field(card_id)
    declared = card_review_independence(card_id)
    lines = [
        "- **本段只給下限，不給結論。** 腳本不解讀卡面語意——"
        "獨立性要求由你讀卡面決定（理由見 `scripts/review_prompt.py` 的註解："
        "自由文字推斷已連續三輪被否定句、引文與條件句打穿）。",
        f"- tier 推導的下限（{tier}）：{floor}",
    ]
    if declared is not None:
        lines += _declared_gates_lines(declared)
    else:
        # iteration 2 REVIEW REJECT F1（blocking）：iteration 2 讓缺欄輸出與加入本欄位
        # 之前**逐字相同**，於是查核者分不出「這張卡沒有機器可讀宣告」與「工具本來就
        # 只給下限」。卡面紅線 2 要的是「**明示**缺欄＋以卡面原文為準」——沉默地退回
        # 正確行為仍然是沉默，讀提示詞的人得不到「該回填了」這個訊號。
        print(f"警告：{card_id} 卡面找不到 `{REVIEW_INDEPENDENCE_FIELD}` 欄位。"
              "活卡採按需回填（docs/TEMPLATES.md）——這張卡正要被產生提示詞，"
              "請需求方裁定該填什麼值，**不得由執行者或工具推定**。",
              file=sys.stderr)
        lines.append(
            f"- 卡面 `{REVIEW_INDEPENDENCE_FIELD}` 欄位：**未找到**——"
            "**這不代表沒有額外要求**，只代表這張卡還沒有機器可讀的獨立性宣告"
            "（活卡按需回填，見 docs/TEMPLATES.md）。一律以本段的 tier 下限與卡面"
            "〈查核〉欄原文為準，**不得據此放寬**。")
    if field is None:
        print(f"警告：{card_id} 卡面找不到〈查核〉欄，提示詞只能給 tier 下限。",
              file=sys.stderr)
        lines.append("- 卡面〈查核〉欄：**未找到**——**這不代表沒有額外要求**，"
                     "請直接開卡片確認格式與內容，別讓工具替需求方放寬要求。")
    elif declared is None:
        lines.append(f"- 卡面〈查核〉欄原文（**以此為準**）：`{field}`")
    else:
        lines.append(f"- 卡面〈查核〉欄原文（**照登，不解讀**；機器可讀的要求已由上列欄位承載，"
                     f"本欄為人可讀補充）：`{field}`")
    lines.append(
        "- 卡面若要求得比上述下限嚴（跨家族、人工核可、兩者皆須、先後順序…），"
        "**一律以卡面為準**；判讀有疑義請需求方裁定，**不得自行放寬**。"
        "查核者 ≠ 執行者是所有情況的下限。")
    if declared is not None and events is not None:
        lines += _actor_parallel_lines(events)
    # 摘要不帶 markdown：呼叫端已把它包進粗體與括號，這裡再加會變成巢狀粗體。
    if declared is None:
        summary = f"下限 {floor}；實際要求以卡面〈查核〉欄為準"
    else:
        seq = " → ".join(_INDEPENDENCE_SHORT[v] for v in declared)
        summary = f"下限 {floor}；卡面宣告 {len(declared)} 關：{seq}"
    return summary, "\n".join(lines)


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
    indep, indep_detail = independence(card_id, tier, card_events(card_id))
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

先分類再給結論：若是卡面／baseline／SHA／依賴／必要證據等送審前條件不成立，
回覆 **PREFLIGHT_FAILED**（外部等待改回 **BLOCKED**），不得用 REQUEST_CHANGES；
若查核順序、artifact、環境或獨立性使本次查核不成立，回覆 **REVIEW_INVALID**。
只有 preflight 通過且查核有效時，才回覆 **APPROVE 或 REQUEST_CHANGES**。

APPROVE／REQUEST_CHANGES 必須附結構化 findings；每條含
`finding_id`、`severity`、`blocking`、`finding_class`、`attribution`、
`root_cause_id`、`evidence`、`disposition`。`accepted`、`status` 與
`counts_toward_escalation` 由 lifecycle writer 依 canonical `review-escalation.md`
及可重現證據裁定，reviewer 不得用自由文字自行宣告。另附你實際重跑的指令與輸出摘要。

依本專案慣例：**APPROVE（零未閉合 blocking findings）後 Coordinator 將直接 merge**
並將結果回傳執行者，部署與後續另由需求方確認；REQUEST_CHANGES 才會退回原執行者
於原分支修正並增加 iteration。你的結論將由需求方轉錄為 event
（source_sha={ev.get('source_sha', '?')[:7]}）留痕。
"""


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("用法：uv run python scripts/review_prompt.py <CARD_ID>")
    print(build_prompt(sys.argv[1]))


if __name__ == "__main__":
    main()
