# AI 協作工作流（cpbl-analytics 採用）

> **2026-08-04 新治理全面生效（WF-22 Wave 0/1/2 完結）**：作業狀態唯一事實來源＝
> **GitHub Issues＋user Project #4「cpbl-analytics 任務看板」**；唯一狀態寫入通道＝
> ai-workflow repo 的 **`wfcli`**（`cli/`）。`docs/control-plane/events.jsonl` 與
> `docs/TASKS.md` 投影**已封存唯讀**（終筆 `8271d7c`）——不得再追加事件或重建 Ledger。
> 決策（開卡／派工／merge／結案）＝需求方本人；機械寫入＝PM 祕書 session 專責。
> **canonical v2（2026-08-05）為唯一權威正文**；
> [`research/WORKFLOW-REVIEW-2026-08-04.md`](research/WORKFLOW-REVIEW-2026-08-04.md) 為決議沿革紀錄。

> **完整規則見 canonical（submodule）：[`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md)**（唯一權威來源；規則改動在 [ruan6047/ai-workflow](https://github.com/ruan6047/ai-workflow)）。既有專案升級依 [`../.ai-workflow/MIGRATION.md`](../.ai-workflow/MIGRATION.md)。
> 本專案任務看板見 **GitHub Issues＋[user Project #4「cpbl-analytics 任務看板」](https://github.com/users/ruan6047/projects/4)**（[`TASKS.md`](TASKS.md) 為 2026-08-04 cutover 的封存快照，唯讀、不再是投影），控制平面見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)，新卡範本索引見 [`TEMPLATES.md`](TEMPLATES.md)，資料庫與部署操作分別見 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) 與 [`AI_RUNBOOK.md`](AI_RUNBOOK.md) §7。模型選擇見 [`MODEL_ROUTING.md`](MODEL_ROUTING.md)。

## 核心鐵律（速查）

1. **變更分級 + 部署閘門**：依 canonical T0–T4 按風險、範圍、可逆性選閘門；T2 以上程式碼（A 類）每卡開分支，每卡／卡族有獨立 worktree；只有已審核合併至 `main` 的提交可部署。
2. **實作／審核分離**：同一張卡的執行與查核須由不同經手者；查核發現缺陷以 PR review／event 留 finding，原執行者在原分支修正，查核者不得改 source branch。卡面／baseline／SHA／依賴等 preflight 失敗不建立 review、不增加 iteration；第三個可計數實質退回先進 escalation checkpoint，只有重複根因、舊 finding 未修或需求方裁定才轉 `🚨已升級`（canonical [`review-escalation.md`](../.ai-workflow/templates/review-escalation.md)）。有效但不計數的 review 仍可閉合 finding；同 attempt finding 衝突須以 `review-correction` 裁決，epoch 切換須有需求方明示授權。查核結論統一用 `APPROVE | REQUEST_CHANGES`（`core_pain_resolved` 與 `self_run` 必填——**無 `self_run` 的 APPROVE 無效**，canonical §5.2）；舊的自由文字 `REJECT` 不得用於 WF-21 baseline 後新事件。**查核第一判準＝核心痛點是否消失，具否決權**（canonical §5.1）。
3. **紅線獨立性**：安全、金流、統計／ML、資料正確性、資安部署與 production migration 一律 T4；review 必換模型家族或人工，且須附實測證據與必要 sign-off。
4. **Discovery → Design → Plan**：T3/T4 先確認問題、證據與成功條件；使用者可見的 T3/T4 卡必過 Design Gate，純技術 T3/T4 卡必記錄 Design Gate `N/A` 理由；大型工作以 Initiative 管理 spec 基線、依賴、里程碑與變更。
5. **聯邦式控制平面**：GitHub remote coordination 管 task、review、lease、CI；local resource lock 管 worktree／port／container；event log 是歷史，Ledger 是投影，不可各自手改。
6. **留痕**：T0/T1 commit 至少 `Requested-by`、`Implemented-by`；T2 以上實作 commit 再加 `Planned-by`；merge、PR 結案或 B2 權威文件核可再加 `Reviewed-by`。
7. **驗證與封存**：先讀再說、不虛構 API／表／指令；secrets 永不進 git；交付須附改動、原因與實測。需部署的卡僅在驗證成功後可 `🏁完成`，失敗／回滾不得封存。
8. **卡範圍與鏈式停損**：一根問題一張卡（卡內多個窄寫入授權）；每卡必填「服務的原始目標」，鏈深硬上限＝原始目標下 2 層，全域問題脫鏈獨立卡（canonical §2.11–2.12／§3.2–3.3）。
9. **三級閘門**：Initiative／不可逆 T4 同步 grilling；T3 核心痛點三問批註放行；T2+ 前提逐條附實查證據（canonical §3.1）。
10. **資源與 worktree**：派工前寫入集交集檢查（`file:`／`db:` 宣告；**merge 後 file 資源即釋放**、`📦已合併` 仍佔活卡）；worktree 註冊制＋doctor 對帳（canonical §4.4–4.5）。
11. **派工包六條**：範圍外發現回報 PM 禁 spawn_task／不停等背景通知／禁 `gh pr update-branch`／詭異數據人工判讀＋新聞佐證四約束（僅定性、官方數值權威、URL＋日期、第三方泛化）／trailer 連續單一區塊／CLI 探索紅線（[`dispatch-package.md`](../.ai-workflow/templates/dispatch-package.md)）。**本專案當前仍有副作用的 CLI 入口：`cpbl-refresh-recent`（連 `--help` 都會觸發每日鏈）；此限制仍在，但 Gate 3 已於 2026-08-03 提前收窗並解除 G4 凍結，修正 `--help` 行為的前置條件已滿足**（[`INGEST-GAME-TM-REFACTOR1-G4.md`](tasks/INGEST-GAME-TM-REFACTOR1-G4.md) L21、L362）。

決策（開卡／派工／merge／結案）＝需求方本人；機械寫入、派工包組裝與查核詞產製＝PM 祕書 session（canonical §1.1，Coordinator 職責由該 session 承擔）。同一卡的執行者不得兼任查核者：一般卡查核以新 context／session 為獨立即可，紅線卡須換模型家族或人工審核。

---

## 派工前三問（PM 祕書自檢，不分級別）

canonical §3.1 的三級閘門是**下限，不是上限**。用「這張卡只有 T2，所以不必走 Discovery／Design」當作跳過的許可，是誤用——那些階段存在的理由是**避免在還沒準備好時就執行，導致做白工或走錯方向**，而風險級別只是它的其中一個代理指標，不是全部。

因此 PM 祕書在 `wfcli assign` 之前，**不分級別**，必須先回答三題：

1. **解法大概長什麼形狀？**
2. **哪一個假設錯了，這張卡的做法就整個不同？**
3. **那個假設現在是查證過的，還是我猜的？**

**第 3 題答「猜的」→ 先查證或先規劃，不得派工。**

三題的答案寫進派工包（或卡面留言），使查核者能事後檢核「派工當下 PM 知道什麼」。答不出第 1 題不代表不能做，但代表這張卡的射程還沒收斂，該補的是規劃不是執行者。

### 觸發這條規則的實例：`DEV-WEB-COMPONENT-TEST-HARNESS1`（#152，2026-08-20）

該卡從 `open` 到 `assign` 相隔 **2 分 17 秒**，未經任何規劃階段。PM 當時把問題框成「**採用一套元件測試環境**」，並據此：資源預先宣告 `web/package-lock.json`（＝預期會裝套件）、派工包要求執行者「先回報 runner 設定檔名」、驗收要求「量出新增依賴數與其傳遞依賴」。

執行者交付的結論是：**不引入新 runner，0 個新 direct dependency，`package-lock.json` 完全沒有變動**——它自行把問題重新框成「node 內建 runner 缺什麼，各補一個 hook」。

⚠️ **是執行者不照卡面框架做才得到對的解。** 換一個照著驗收條件推進的執行者，會去裝 vitest＋jsdom＋RTL，因為「量出新增依賴的代價」這句話本身就在暗示要裝。**這次沒有白做，是運氣，不是流程。**

對照三問：PM 當時答不出第 1 題（以為要裝套件，實際不用），第 3 題的答案是「猜的」。**照本規則，這張卡當時不該派。**

### 第 3 題答「猜的」之後：依級別決定補什麼

三問只負責**攔下來**，不規定補救方式。出口依級別分流，與 canonical §3.1 的三級閘門對齊：

| 卡的級別 | 第 3 題答「猜的」時要補的 |
|---|---|
| Initiative／不可逆 T4 | **invoke `grilling` skill 做同步真對話**。存活的反駁寫回 discovery brief 的「待驗證假設」與「非目標」，被推翻的前提直接修正問題陳述。⚠️ Issue 留言**不是** brief 的替代品 |
| T3 | 核心痛點三問非同步輕質詢，需求方批註放行 |
| T0–T2 | **唯讀查證**（可派子代理做，但那是本卡的**前置**不是執行階段），答案補進卡面後**重答三問** |

補完之後重新回答三題；第 3 題仍答「猜的」就繼續擋，不得因為已經補過一輪就放行。

### ⚠️ 已知的兩個漂移，記錄以便日後檢核

**一、`grilling` 曾正常運作但已中斷。** 留痕可查：`docs/research/INIT-GAME-RECAP_DISCOVERY-BRIEF.md` 的對抗式質詢欄記載 2026-08-06 完成 Q1–Q8 並列出被推翻的前提；`docs/discovery/DEV-REVIEW-PREFLIGHT-GATE1-discovery.md` 記載 2026-07-31 對抗式質詢後改採新路線；`OPS-STATE-PLANE-MIG1` 直接以 grilling 作為該卡 Discovery。**最近一次為 2026-08-06。**

**二、2026-08-19 `DATA-BOX-DEEP-SILENT-FAIL1`（#131）的四題質詢，時機與載體都不對。** 該卡 2026-08-13 開立，質詢在 **08-19 派工前**才做——canonical 要求的是「Discovery／規劃時」，不是派工前補一輪；且存活的反駁寫成 Issue 留言而非 discovery brief，該卡至今無 brief。**質詢的實質有做，流程位置錯了。**

成因是可重複的、不是一次疏忽：PM 祕書接手的多為**存量卡**（他人所開，Discovery 階段早已過去），能做質詢的最早位置就是派工前。⚠️ 這意味著「存量卡如何補 Discovery」是一個**尚未解決的問題**，不是靠紀律就能修的——在解決之前，派工前補一輪仍好過不補，但**不得記載成「已完成 Discovery Gate」**。

---

## 入口路由稽核（`DOC-ENTRY-ROUTING1` #140，2026-08-19）

### 入口文件指向清單（機械抽取，非人工聲明）

下表由 `CLAUDE.md` 機械抽取全部文件指向並逐一驗存在性，是該卡驗收條 3 的可稽核產物。

**重跑方式＝跑下面這支腳本，散文描述不是規格。**
理由是實證：三方曾照同一段散文說明各自重跑，因為各自補上不同的隱含過濾，得出
**25／34／95** 三個數字。過濾與正規化規則只要用散文寫就必然漏項，故一律以程式碼表達。
把下列區塊存成 `audit.py`（或以 heredoc 餵給 `python3`），**於 repo 根目錄執行**：

```python
"""入口路由稽核：抽出 CLAUDE.md 的全部文件指向並驗存在性。

於 repo 根目錄執行：python3 audit.py
本腳本即規格——三方曾照散文描述各自補上不同的隱含過濾，得出 25／34／95 三個數字，
故過濾規則一律以程式碼表達，不另寫散文。
"""
import re
import subprocess
import pathlib

# 裸檔名 → 實際路徑的正規化表。CLAUDE.md 為了可讀性寫 `models/train.py` 這種
# 相對於 src/cpbl/ 的短路徑，甚至只寫 `train.py`；比對存在性前必須還原。
CODE_PREFIXES = {
    "features/": "src/cpbl/",
    "models/": "src/cpbl/",
    "ingest/": "src/cpbl/",
    "train.py": "src/cpbl/models/",
    "_browser.py": "src/cpbl/ingest/",
}

# 不在本 repo 但已逐一查證「非壞路由」者的歸類理由。
NOTES = {
    ".ai-workflow/AI_WORKFLOW.md": "submodule 內容；主 checkout 實存（本 worktree 未 init）",
    "discovery-brief.md": "canonical `templates/` 內容；主 checkout 實存",
    "docs/SUB_PROJECT_GUIDE.md": "CLAUDE.md 明標「主站」；PersonalWebsite repo 內實存",
    "apps/subprojects/cpbl-analytics/": "主站掛載路徑，非本 repo",
    ".venv/": "禁 commit 清單（git 未追蹤；uv 會在本機生成）",
    "data/": "禁 commit 清單（git 未追蹤）",
    "artifacts/": "禁 commit 清單（git 未追蹤）",
    "00X_description.sql": "migration 檔名慣例，非實檔",
    "https://github.com/users/ruan6047/projects/4": "外部 URL（本卡新增）",
}


def extract(md: str) -> dict[str, set[int]]:
    """兩條、且只有兩條收錄規則。

    1. markdown 連結目標 `[文字](目標)` —— 全收，含外部 URL。理由：連結是作者
       明示的「請去讀這個」，外部 URL 也該驗它還在不在。
    2. 行內反引號片段 `` `x` `` —— **只收**副檔名為 .md／.py／.sql 或以 / 結尾者。
       理由：反引號在本檔同時用於路徑、指令、API 路徑、環境變數、欄位名、型別名。
       只有前述形狀是「文件指向」；`/api/info`、`/predict`、`.env`、`.python-version`、
       `github.com/ldkrsi/cpbl-opendata` 因此**不收**——它們不是本 repo 的檔案路徑。

    fenced code block（``` 圍起來的區塊）**不會**貢獻任何指向：那些行本身不含
    行內反引號，規則 2 掃不到，規則 1 也不匹配。這是規則的推論，不是額外過濾。
    """
    refs: dict[str, set[int]] = {}
    for lineno, line in enumerate(md.splitlines(), 1):
        for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", line):
            refs.setdefault(m.group(1), set()).add(lineno)
        for m in re.finditer(r"`([^`]+)`", line):
            token = m.group(1)
            if re.search(r"\.(md|py|sql)$", token) or token.endswith("/"):
                refs.setdefault(token, set()).add(lineno)
    return refs


def tracked(path: str) -> bool:
    """存在性一律問 git，**不可用檔案系統**——.venv/、data/、artifacts/ 等禁 commit
    目錄會被本機工具生成，os.path.exists 會把它們誤判為實存。"""
    out = subprocess.run(["git", "ls-files", "--", path], capture_output=True, text=True)
    return bool(out.stdout.strip())


def resolve(token: str) -> str | None:
    if tracked(token):
        return token
    for prefix, base in CODE_PREFIXES.items():
        if token.startswith(prefix) and tracked(base + token):
            return base + token
    return None


def main() -> None:
    refs = extract(pathlib.Path("CLAUDE.md").read_text(encoding="utf-8"))
    rows, n_ok, n_out = [], 0, 0
    for token in sorted(refs):
        lines = ",".join(str(n) for n in sorted(refs[token]))
        target = resolve(token)
        if target:
            date = subprocess.run(
                ["git", "log", "-1", "--format=%ad", "--date=short", "--", target],
                capture_output=True, text=True).stdout.strip()
            extra = "" if target == token else f"解析為 `{target}`；"
            rows.append(f"| `{token}` | {lines} | ✅ git 已追蹤 | {extra}最後改動 {date} |")
            n_ok += 1
        else:
            rows.append(f"| `{token}` | {lines} | — 不在本 repo | {NOTES.get(token, '⚠️ 未歸類')} |")
            n_out += 1
    print("| 指向 | CLAUDE.md 行 | 存在性 | 備註 |")
    print("|---|---|---|---|")
    print("\n".join(rows))
    print()
    print(f"共 {len(refs)} 個指向：{n_ok} 個 git 已追蹤，{n_out} 個不在本 repo")


if __name__ == "__main__":
    main()
```

**預期輸出的末行**（可證偽；下一個人跑不出這行就是本節壞了）：

```
共 25 個指向：16 個 git 已追蹤，9 個不在本 repo
```

| 指向 | CLAUDE.md 行 | 存在性 | 備註 |
|---|---|---|---|
| `.ai-workflow/AI_WORKFLOW.md` | 5 | — 不在本 repo | submodule 內容；主 checkout 實存（本 worktree 未 init） |
| `.venv/` | 213 | — 不在本 repo | 禁 commit 清單（git 未追蹤；uv 會在本機生成） |
| `00X_description.sql` | 121 | — 不在本 repo | migration 檔名慣例，非實檔 |
| `_browser.py` | 189 | ✅ git 已追蹤 | 解析為 `src/cpbl/ingest/_browser.py`；最後改動 2026-07-04 |
| `apps/subprojects/cpbl-analytics/` | 14 | — 不在本 repo | 主站掛載路徑，非本 repo |
| `artifacts/` | 213 | — 不在本 repo | 禁 commit 清單（git 未追蹤） |
| `data/` | 213 | — 不在本 repo | 禁 commit 清單（git 未追蹤） |
| `discovery-brief.md` | 221 | — 不在本 repo | canonical `templates/` 內容；主 checkout 實存 |
| `docs/AI_RUNBOOK.md` | 3,224 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/AI_WORKFLOW.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/CPBL_SITE_MAP.md` | 175,190 | ✅ git 已追蹤 | 最後改動 2026-07-30 |
| `docs/DATABASE_CONTRACT.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/MODEL_ROUTING.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/ROADMAP.md` | 6 | ✅ git 已追蹤 | 最後改動 2026-08-14 |
| `docs/SUB_PROJECT_GUIDE.md` | 167 | — 不在本 repo | CLAUDE.md 明標「主站」；PersonalWebsite repo 內實存 |
| `docs/TASKS.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-05 |
| `docs/reference/GLOSSARY.md` | 222 | ✅ git 已追蹤 | 最後改動 2026-08-10 |
| `features/outcome.py` | 145 | ✅ git 已追蹤 | 解析為 `src/cpbl/features/outcome.py`；最後改動 2026-08-05 |
| `https://github.com/users/ruan6047/projects/4` | 5 | — 不在本 repo | 外部 URL（本卡新增） |
| `ingest/_browser.py` | 181 | ✅ git 已追蹤 | 解析為 `src/cpbl/ingest/_browser.py`；最後改動 2026-07-04 |
| `migrations/` | 121 | ✅ git 已追蹤 | 最後改動 2026-08-08 |
| `models/matchup.py` | 95 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/matchup.py`；最後改動 2026-08-05 |
| `models/outcome.py` | 137 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/outcome.py`；最後改動 2026-06-26 |
| `models/outcome_gbm.py` | 96 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/outcome_gbm.py`；最後改動 2026-08-05 |
| `train.py` | 132 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/train.py`；最後改動 2026-08-05 |

共 25 個指向：16 個 git 已追蹤，9 個不在本 repo

### 本卡明確「不做」的四項與理由

依「流程會不會執行」判準逐項查證，四項皆**無受害者或不屬本卡射程**，故不做：

1. **`wfcli doctor` 對 cutover 後 cpbl 的失能** — 流程確有要求，但修正點在上游
   `ai-workflow` repo，不在本卡宣告的五個檔案內。
2. **`.wfcli.json` 缺失** — 原判「3 張 smoke 卡不在板是漏 `--repo` 所致」經查為**誤**：
   那些是拋棄式 smoke 卡，本就不該在板，故無受害者。
3. **卡面缺四個標頭欄位** — `card.render_issue_body` 根本不輸出這四欄，屬上游結構性
   drift，非本專案文件問題。
4. **卡面標題兩種格式混用** — 實測 **0 張**解不出 `card_id`，無受害者。
