# DEV-REVIEW-INDEP-FIELD1 Discovery：卡面獨立性要求能不能變成機器可讀欄位

> 卡片：[`../tasks/DEV-REVIEW-INDEP-FIELD1.md`](../tasks/DEV-REVIEW-INDEP-FIELD1.md)　執行者：Claude Opus 5@Claude Code　日期：2026-07-29（iteration 1 修訂 2026-07-30）
> **本文件只回答 Discovery 四問，不含實作。**
>
> **iteration 1 修訂（依 `REVIEW-004` REQUEST_CHANGES）**：P1-3 多關卡盤點改為腳本窮舉（5 → **14 張**，並查明先前漏算的成因）；P1-4 補上卡面欄位與 event log 的職權劃分，消除雙重狀態來源；Q2／Q4 補記 2026-07-30 需求方裁定。**基線：main `81bcd4d`**（本次全部掃描皆以此 SHA 為母體，含已合併的 `DEV-REVIEW-PROMPT-GUARD1` `1155cec` 與 `DEV-REVIEW-PROMPT-GATE1` `9177ee8`）。

## 資料基礎（可重現）

### 掃描一：卡面〈查核〉欄的獨立性字樣

掃描全部卡片的卡面 header〈查核〉欄（第一個 `## ` 標題之前、以 `-` 開頭且含 `查核：` 的行）：

```bash
python3 - <<'PY'
import pathlib
for d in ("docs/tasks","docs/archive/tasks"):
    for p in sorted(pathlib.Path(d).glob("*.md")):
        field = None
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "): break
            if line.lstrip().startswith("-") and "查核：" in line:
                field = line.split("查核：",1)[1].strip(); break
        print(f"{p.stem}\t{field}")
PY
```

**母體 119 張**（活／封存分布為 iteration 0 執行當時的 35／84；main `81bcd4d` 上已是 30／89，母體總數與下表分類皆不受影響，見下方註記）。欄位缺席 4 張：`INIT-GAME-RECAP`、`INIT-OFFICIAL-DATA1`、`INIT-PRODUCT-UX`（三張皆 Initiative 卡）、`DOC-GAME-RECAP1`。

有欄的 115 張依字樣分類：

| 類別 | 張數 | 代表寫法 |
|---|---|---|
| 無強化要求 | 54 | `待指派（建議 L2；≠ 執行）` |
| 含「跨家族」＋「人工」 | 44 | `待指派（跨模型家族或人工，且 ≠ 執行）` |
| 只含「跨家族」 | 17 | `Antigravity（Gemini 3.6 Flash，跨家族，≠ 執行，APPROVE）` |

（iteration 1 以**等價腳本**在 main `81bcd4d` 重驗——唯一差異是檔案改由 `git show 81bcd4d:<path>` 讀取而非讀工作目錄，取檔清單改用 `git ls-tree`，取〈查核〉欄的邏輯逐字相同。結果：母體與四項數字**完全一致**（119／缺欄 4／54／44／17），並補驗「含跨家族＋人工」44 張**全部含「或」**、含「且」而不含「或」者 **0 張**、「只含人工」**0 張**。main 上有 5 張活卡已封存，但母體總數與分類不受活／封存變動影響。）

### 掃描二：多關卡要求（iteration 1 新增，取代原先的人工聲明）

原文以「另掃出 5 張」的**人工聲明**承載這個數字，且同句引用了不在清單內的 `UX-ENTITY-LINKS3`——查核者判為自相矛盾且違反本專案「完整性宣稱必須附腳本產生的窮舉證據」的紅線。改為窮舉三個信號：

- **信號 A**：卡面（`## Log` 之前）以**順序語式**要求「人工關卡在 AI／跨家族查核之前」。
- **信號 B**：卡面〈Design〉欄宣告**待跑的人工 Design Gate**（排除 `N/A`）。這是原先漏掉 `UX-ENTITY-LINKS3` 的成因——見〈發現 2〉。
- **信號 C**：event log 的**實然**多關卡（一筆 APPROVE 的 review 之後、在 `merge` 之前又出現另一筆 review）。

匹配刻意寬鬆，命中後**逐張人工確認**；被判為「引用他卡文字」的誤命中列在腳本的 `QUOTE_ONLY` 常數裡並在下方逐一說明，不隱藏。

```python
import collections, json, re, subprocess

REV = "81bcd4d"  # main @ 2026-07-30
QUOTE_ONLY = {  # 人工確認為「引用他卡文字」的誤命中（見下方說明）
    "docs/archive/tasks/DEV-REVIEW-PROMPT-GATE1.md",
    "docs/tasks/DEV-REVIEW-INDEP-FIELD1.md",
}

cards = [p for p in subprocess.run(
    ["git", "ls-tree", "-r", "--name-only", REV, "docs/tasks/", "docs/archive/tasks/"],
    capture_output=True, text=True, check=True).stdout.split() if p.endswith(".md")]

A_HUMAN = re.compile(r"(人工審|人工核可|人工審核|人工走查|人工審查|本地審|需求方.{0,6}審)")
A_ORDER = re.compile(r"(再交|才交|後才|再由|再給|OK\s*後|後.{0,4}交)")
B_GATE = re.compile(r"Design\s*Gate\s*=|Design\s*Gate.{0,12}核可|待需求方核可|須經需求方\s*sign-off|須\s*sign-off")

sig = collections.defaultdict(dict)
for p in cards:
    lines = subprocess.run(["git", "show", f"{REV}:{p}"], capture_output=True, text=True,
                           check=True).stdout.splitlines()
    log_at = next((i for i, l in enumerate(lines) if l.startswith("## Log")), len(lines))
    for i, line in enumerate(lines[:log_at]):          # 只看卡面 spec，Log 事後紀錄另計
        if A_HUMAN.search(line) and A_ORDER.search(line) and p not in QUOTE_ONLY:
            sig[p].setdefault("A", (i + 1, line.strip()))
        if line.startswith("- Design：") and B_GATE.search(line) and "N/A" not in line:
            sig[p].setdefault("B", (i + 1, line.strip()))

ev = collections.defaultdict(list)
for line in subprocess.run(["git", "show", f"{REV}:docs/control-plane/events.jsonl"],
                           capture_output=True, text=True, check=True).stdout.splitlines():
    if line.strip():
        e = json.loads(line)
        ev[e["card_id"]].append(e)
de_facto = {}
for card, evs in ev.items():
    prev = None
    for e in evs:
        if e.get("type") == "merge":
            prev = None
        elif e.get("type") == "review":
            if prev:
                de_facto.setdefault(card, []).append((prev, e))
            prev = e if (e.get("review_result") or "").startswith("APPROVE") else None

print(f"母體 {len(cards)} 張（活卡 {sum(1 for c in cards if c.startswith('docs/tasks/'))}"
      f"、封存 {sum(1 for c in cards if c.startswith('docs/archive/'))}）\n")
print(f"== 卡面宣告多關卡：{len(sig)} 張 ==")
for p in sorted(sig, key=lambda x: x.split("/")[-1]):
    kinds = "".join(sorted(sig[p]))
    print(f"\n{p.split('/')[-1][:-3]}  [{kinds}]"
          f"{'  ← 封存' if 'archive' in p else '  ← 活卡'}")
    for k in sorted(sig[p]):
        ln, txt = sig[p][k]
        print(f"    {k} L{ln}: {txt[:150]}")
print(f"\n== event log 實然多關卡：{len(de_facto)} 張 ==")
for card, pairs in sorted(de_facto.items()):
    for a, b in pairs:
        print(f"{card}: {a['event_id']}（{a.get('actor','')[:22]}）"
              f" → {b['event_id']}（{b.get('actor','')[:22]}）"
              f"  closes={a.get('closes_review_round','(缺席)')}")
```

完整輸出（未刪節）：

```
母體 119 張（活卡 30、封存 89）

== 卡面宣告多關卡：14 張 ==

DOC-GAME-RECAP1  [B]  ← 封存
    B L10: - Design：本卡即為 Design／Plan 權威文件查核；Design Gate 維持待需求方核可

UX-DESIGN-CONFORM1  [AB]  ← 封存
    A L18: - [ ] `npm run build:check` 通過；上線前依 UX 慣例先開本地環境給需求方人工審，OK 後才交跨家族（非 Claude）或人工查核。
    B L10: - Design：**Design Gate = ruan6047**（修改清單與上線前人工審，依 [[ux-manual-review-before-ai]] 慣例）

UX-DESIGN-SYSTEM1  [B]  ← 封存
    B L13: - Design：**Design Gate = ruan6047**（產出的 canonical 規格須經需求方 sign-off 才成為全站事實）

UX-ENTITY-LINKS1  [AB]  ← 封存
    A L23: - [ ] 驗證：`build:check` + 深淺色截圖 + 鍵盤焦點 + a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。
    B L10: - Design：**Design Gate = ruan6047**（實際連結觀感於本地審微調）

UX-ENTITY-LINKS2  [AB]  ← 封存
    A L40: - [ ] `build:check` 全路由 ✓、`npm test` ✓、深淺色截圖、鍵盤焦點、a11y（連結非色彩單獨可辨識）。**先本地人工審再交跨家族查核**。
    B L10: - Design：**Design Gate = ruan6047**（每點的 block→text-only 觀感於本地審微調）

UX-ENTITY-LINKS3  [B]  ← 封存
    B L11: - Design：**Design Gate = ruan6047**（哪些出現位置該連、哪些不連；列表頁的互動取捨）

UX-GAME-PA1  [B]  ← 活卡
    B L10: - Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補行動版與桌機互動 prototype

UX-GAME-RECAP1  [B]  ← 活卡
    B L10: - Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補 prototype／wireframe 與 Design Gate

UX-LIVE-GAME1  [B]  ← 活卡
    B L10: - Design：[`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §6；Design Gate 待需求方核可

UX-NAV-INTEGRATE1  [B]  ← 封存
    B L11: - Design：**Design Gate = ruan6047**（§4.3 方向已 sign-off 2026-07-24；各頁成品仍須 UI 審）

UX-TEAM-HOTZONE1  [A]  ← 封存
    A L84: - **UX 卡流程**：執行完先開本地環境給需求方人工審核，OK 後才交 AI 查核。

UX-TEAM-RECORDS1  [A]  ← 封存
    A L181: - **UX 卡流程**：執行完先開本地環境給需求方人工審核，OK 後才交 AI 查核。

UX-TEAM-STYLE1  [A]  ← 封存
    A L59: - [ ] 本機開發環境人工走查（依 UX 慣例：先人工審再交 AI 查核）。

UX-TOKEN-HYGIENE1  [B]  ← 封存
    B L11: - Design：**Design Gate = ruan6047**（動到色票須 sign-off）

== event log 實然多關卡：2 張 ==
UX-ENTITY-LINKS2: UX-ENTITY-LINKS2-REVIEW-007（ruan6047（需求方本地人工審／Desi） → UX-ENTITY-LINKS2-REVIEW-008（GPT@Codex（跨模型家族查核者，非 C）  closes=(缺席)
UX-ENTITY-LINKS3: UX-ENTITY-LINKS3-REVIEW-005（ruan6047（需求方本地人工審／Desi） → UX-ENTITY-LINKS3-REVIEW-007（跨模型家族查核者（非 Claude；需求方轉）  closes=(缺席)
```

**兩筆人工排除（`QUOTE_ONLY`）**：`DEV-REVIEW-PROMPT-GATE1` L17 與本卡 L40 的命中都是**引用 `UX-ENTITY-LINKS2` 的卡面文字**來論證問題，不是各自的查核要求（兩卡的〈查核〉欄皆為單關卡寫法、〈Design〉欄皆 `Design Gate N/A`）。**原文的「5 張」把這兩張算進去了**——那正是 `GUARD1` 三輪被打穿的同一種錯（引文命中被當成要求），只是這次發生在人工盤點而非正則。

**一筆人工判斷的邊界案例（腳本刻意不計）**：`UX-PLAYER-SCOPE1` 的〈Design〉欄寫「2026-07-22 需求方核可『保留 Hero 雷達…』」——這是**已完成**的人工關卡紀錄，不是待跑的要求，故不計入 14 張。但它本身是一個發現：**〈Design〉欄和〈查核〉欄一樣兼記「要求」與「結果」**（Q3 的結構問題不只發生在〈查核〉欄），因此「靠掃描既有卡面推導要求」在兩個欄位上都不可靠。

**〈查核〉欄的交叉檢查**：14 張中 13 張有〈查核〉欄（`DOC-GAME-RECAP1` 無），逐張取值後**零張**在該欄表達多關卡——全是 `待指派（≠ 執行；跨家族或人工）`、`待指派（跨模型家族或人工，且 ≠ 執行）`、`待指派（須 ≠ 執行）` 這類單關卡寫法。`UX-TEAM-STYLE1` 的〈查核〉欄甚至只寫 `待指派（≠ 執行；T3 一般查核）`，**完全看不出它的驗證段要求先人工審**。

## Q1：值域夠不夠？

**候選 enum（`context`／`cross_family_or_human`／`human`／`cross_family_and_human`）在字面上涵蓋得了現況，但那是因為現況本身沒把真正的複雜度寫進欄位。** 兩個實測發現：

**發現 1：44 張「跨家族＋人工」全部是 OR 寫法，零 AND、零順序。** 逐張檢視結果一致（`跨模型家族或人工`／`跨家族或人工`），無一張在欄位裡表達「兩者皆須」或「先 A 後 B」。若只看欄位，值域甚至只需要三個值——`human` 與 `cross_family_and_human` 在 115 張裡各出現 **0 次**。

**發現 2：多關卡要求確實存在，數量是 14 張，而且用兩種互不相交的語彙寫在欄位以外的地方。** 數字與清單由〈掃描二〉的腳本輸出承載，不是人工聲明：

- **信號 A（正文順序語式）6 張**：`UX-DESIGN-CONFORM1`、`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`、`UX-TEAM-HOTZONE1`、`UX-TEAM-RECORDS1`、`UX-TEAM-STYLE1`。其中後三張的寫法是 UX 卡慣例句（「執行完先開本地環境給需求方人工審核，OK 後才交 AI 查核」／「先人工審再交 AI 查核」），與 LINKS 系列的「先本地人工審再交跨家族查核」**不是同一句話**。
- **信號 B（〈Design〉欄宣告待跑的人工 Design Gate）11 張**：`DOC-GAME-RECAP1`、`UX-DESIGN-CONFORM1`、`UX-DESIGN-SYSTEM1`、`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`、`UX-ENTITY-LINKS3`、`UX-GAME-PA1`、`UX-GAME-RECAP1`、`UX-LIVE-GAME1`、`UX-NAV-INTEGRATE1`、`UX-TOKEN-HYGIENE1`。
- **union 14 張**（A∩B 3 張：`UX-DESIGN-CONFORM1`、`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`）。**其中 3 張是活卡**（`UX-GAME-PA1`、`UX-GAME-RECAP1`、`UX-LIVE-GAME1`）——也就是說多關卡不只是封存區的歷史，未來就會被產生提示詞。

**`UX-ENTITY-LINKS3` 先前為什麼漏掉。** 它位於封存區，但**位置不是原因**——兩次掃描都涵蓋 `docs/archive/tasks/`。原因是**語式不同**：LINKS3 的卡面**沒有**「先…再交」這句話，它的多關卡要求只寫在〈Design〉欄的 `Design Gate = ruan6047`。原文只用順序語式盤點，於是整個信號 B 家族（11 張）都在視野外，而 LINKS3 恰好是 B-only。

**LINKS3「實際跑了兩關」的說法本身沒有錯，錯的是它不該出現在一份只用順序語式產出的清單裡。** 事件證據（信號 C）：`UX-ENTITY-LINKS3-REVIEW-005`（`ruan6047`，需求方本地人工審／Design Gate，APPROVE）→ `HANDOFF-006` → `REVIEW-007`（跨模型家族查核者，非 Claude，APPROVE）→ `MERGE-008`。`UX-ENTITY-LINKS2` 同型（`REVIEW-007` → `REVIEW-008`）。全庫**只有這 2 張**留下實然多關卡的事件序列，且兩張的中繼關卡事件都**缺 `closes_review_round`**——它們發生在 `GATE1`（`9177ee8`）引入該欄位之前，屬 baseline 之前的歷史，不追溯。

→ **結論**：只在欄位上做 enum，抓不到本專案實際在跑的兩關卡流程；而且**「靠掃描既有卡面推導要求」也不可靠**——同一件事至少有兩種語彙（順序語式、Design Gate 欄），兩個欄位都兼記要求與結果。**順序必須納入值域，或明確宣告不納入並指定它改寫在哪裡**（例如另一個 `review_gates` 陣列欄位，或維持正文但在欄位標記 `multi_gate`）。**不得默默把它留在正文——那正是本卡要離開的「規則寫在自由文字裡」。**

## Q2：既有卡怎麼辦？

**已定案（2026-07-30 需求方裁定，見下方裁定節）：只要求新卡必填，活卡按需回填，封存卡一律不動。** 理由：

- 封存 89 張的欄位**多數已被覆寫成「實際查核者＋結論」**（見 Q3），回填等於改寫歷史紀錄。
- 活卡 30 張中，27 張有欄位、寫法高度一致（OR 形式或 plain），機械回填成本低但**收益只在未來會被產生提示詞的那幾張**。〈掃描二〉指出這裡至少有 3 張非回填不可（`UX-GAME-PA1`、`UX-GAME-RECAP1`、`UX-LIVE-GAME1` 都是待跑的多關卡活卡）。
- 缺欄的 4 張中，3 張是活的 Initiative 卡（`INIT-GAME-RECAP`、`INIT-OFFICIAL-DATA1`、`INIT-PRODUCT-UX`）——Initiative 不會被派查核，**應在範本層宣告 Initiative 卡不需此欄**，而不是硬填一個值；第 4 張 `DOC-GAME-RECAP1` 已封存，照封存規則不動。

**缺欄位時工具的行為（卡面紅線 2）**：明示「未找到，這不代表沒有額外要求」＋以卡面原文為準，**不得回退成「所以只要新 context 就好」**。`DEV-REVIEW-PROMPT-GUARD1` iteration 3 已實作此行為，本卡沿用即可。

## Q3：欄位與自由文字衝突時以誰為準？

**這一問的前提在掃描中被推翻了：〈查核〉欄目前身兼兩用，不是一個「要求」欄位。**

- 待指派時它記**要求**：`待指派（跨模型家族或人工，且 ≠ 執行）`。
- 查核完成後它被**覆寫為實際查核者與結論**：`Antigravity（Gemini 3.6 Flash，跨家族，≠ 執行，APPROVE）`、`Gemini 3.6 Flash@Antigravity（跨模型家族 APPROVE @ 46bdd9e，零阻塞）`、`Claude Opus 4.8（跨模型家族；iteration 2 APPROVE）`。上表「只含跨家族」的 17 張多屬此類。

**一個同時承載「要求」與「結果」的欄位，塞不進 enum。** 這是值域之外的結構問題，且它解釋了為什麼自由文字推斷會失敗——工具讀到的可能根本不是要求，而是事後的紀錄。

→ **建議**：新欄位**獨立於現有〈查核〉欄**（例如 header 另加一行 `review_independence: cross_family_or_human`），現有欄位維持自由文字、繼續兼記實際查核者。**兩者衝突時以新欄位為流程門檻、以自由文字為人可讀補充**；但這個分工必須寫進 `CONTROL_PLANE_CONTRACT.md`，否則就是再造一個「靠人記得」。

## Q4：欄位是宣告，不是保證——要不要驗證？

**已定案（2026-07-30 需求方裁定，見下方裁定節）：接受它只是留痕，並且在契約明講。**

工具能驗的是「卡面宣告了什麼」，不能驗「實際查核者是否真的跨家族」——那需要一個可信的查核者身分來源，本專案沒有（查核結論目前由需求方**人工轉錄**成 event，actor 字串是人打的，本 session 就有兩筆記為「待補正」）。

**已定案的低成本強化**：`review_prompt.py` 產生提示詞時，把宣告值與**上一輪 review event 的 actor**並列印出，讓人一眼看出「宣告要跨家族、上輪是 Claude」這種矛盾。**這是輔助判讀，不是保證**——必須在文件與輸出裡都寫清楚，否則本卡就複製了它要治的病（宣稱有保證但其實沒有）。

補一則本次掃描得到的實證：〈掃描二〉信號 C 的兩張卡，跨家族那一關的 actor 分別是 `GPT@Codex（…需求方轉錄，確切模型版本待補正）` 與 `跨模型家族查核者（非 Claude；需求方轉錄，確切工具／模型待補正）`。**連「是誰查的」本身都是人工轉錄且自帶「待補正」**，這正是「不可能自動驗證實際查核者」的直接證據，不是推測。

## 需求方裁定（2026-07-29，ruan6047）

兩項均已定案，記於此並同步 `HANDOFF-003` 事件：

1. **順序納入值域。** 多關卡要求不得繼續留在正文。
2. **新欄位獨立於現有〈查核〉欄。** 現有欄位維持自由文字、繼續兼記實際查核者與結論。

### 依裁定推導的欄位形態（方向，非定案細節）

順序既然要納入，**用有序清單比用列舉每種組合的 enum 名穩**——`cross_family_and_human` 這種合成名一旦要表達順序就會爆炸（`human_then_cross_family`、`cross_family_then_human`…）。建議：

```
review_independence: [human, cross_family]     # 先人工審，再跨家族（LINKS2／LINKS3 實際流程）
review_independence: [cross_family_or_human]   # 單一關卡，二擇一（現況 44 張）
review_independence: [context]                 # 單一關卡，新 session 即可（現況 54 張）
```

- **單一元素＝單一關卡**，清單長度即關卡數，順序即先後。
- 值本身仍是原候選集（`context`／`cross_family_or_human`／`human`／`cross_family`），**不再需要 `cross_family_and_human`**——兩者皆須就是兩個元素。
- 「兩者皆須但不限順序」若確實存在，第二段須決定是否需要額外表達；**本次掃描 115 張裡 0 次**，建議先不支援並在契約明寫不支援。

**上述為 Discovery 的推導，值域最終形態由第二段實作定案並經查核**；此處只確保裁定不被實作階段悄悄改掉。

### 職權劃分：卡面欄位＝靜態要求，event log＝動態進度（iteration 1 新增）

查核者指出一個真實的風險：`DEV-REVIEW-PROMPT-GATE1`（`9177ee8`）合併後，event log 已經有 `closes_review_round`／`corrects_event_id` 在表達多關卡；本卡又要在卡面加一個有序清單表達多關卡。**同一個性質在兩處各自宣告，就是雙重狀態來源。**

劃分如下，**這不是「取其一」而是「切開維度」**：

- **卡面 `review_independence`＝靜態要求（應然）**：這張卡**應該**有幾關、每關要什麼獨立性、順序為何。它是需求方的宣告，在卡片生命週期內基本不變；要改它就是改要求，須經需求方並留痕。
- **event log 的 `closes_review_round`／`corrects_event_id`＝動態進度（實然）**：這一輪**實際上**跑到哪一關、每關誰查的、本輪結束沒。append-only，只增不改。
- **互不覆寫、也互不為事實來源**：欄位**不參與**守衛放行判定；事件**不參與**提示詞裡的獨立性要求陳述。

兩者不一致時**各管各的維度、並列呈現，不由工具仲裁**（工具一仲裁就回到「替需求方決定要求」的老病）。三種形態的處置：

- **欄位宣告 N>1 關，但本輪沒有任何中繼關卡事件**：照登「卡面要求 N 關，本輪尚無中繼關卡留痕」，**不擋**。欄位是宣告不是保證（Q4），拿它當守衛就是把留痕升級成保證。
- **欄位宣告單一關卡，但事件有中繼關卡**：以事件為實然，照 `GATE1` 邏輯放行並帶出中繼裁定；同時提示「卡面未宣告此關卡，欄位可能過期」。
- **欄位缺席**：沿用卡面紅線 2——明示缺欄＋以卡面原文為準，**不得回退成「所以只要新 context 就好」**。

**第二段實作要怎麼同時消費兩者**（對應 `review_prompt.py` 現行結構，main `81bcd4d`）：

- `independence()`：**只讀欄位**（＋tier 下限＋卡面〈查核〉欄原文照登），產出「這一關要什麼獨立性」。有序清單長度 > 1 時逐關列出；但「你是第幾關」**由事件決定**（已通過的中繼關卡數），不由欄位決定——欄位只知道有幾關，不知道跑到哪。
- 守衛（`latest_handoff()` / `_closes_review_round()`）：**完全不讀欄位**，維持只看 `closes_review_round`／`corrects_event_id`。這一點是硬要求：欄位一旦能影響放行，`GATE1` 的「存在終結本輪者即拒絕」語意就會被第二個來源污染。
- `review_gates_block()`：維持**只吃事件**，不因欄位宣告而虛構關卡。
- 唯一的交會點是**列印**：把欄位宣告值與事件實況（含上一輪 review 的 actor，見 Q4）並列輸出供人判讀，**不做仲裁、不產生結論**。

**這個分工必須寫進 `CONTROL_PLANE_CONTRACT.md`**（〈Event、claim 與 WIP〉的 `closes_review_round` 條目旁增述，並在卡面欄位的定義處反向指回），否則兩個來源的邊界就只存在於本文件與人的記憶裡——那與本卡要治的「規則寫在自由文字裡」是同一種病。

## 需求方裁定（2026-07-30，ruan6047）

`REVIEW-004` 指出 Q2／Q4 停在「建議」而非定案。需求方於 2026-07-30 裁定，**兩題均照原建議定案**：

1. **Q2 遷移策略定案**：**新卡必填** `review_independence`；**活卡按需回填**（只補會被產生提示詞的那幾張，`UX-GAME-PA1`／`UX-GAME-RECAP1`／`UX-LIVE-GAME1` 屬此類）；**封存卡一律不動**——其欄位已被覆寫為實際查核結果，回填等於改寫歷史；**Initiative 卡在範本層宣告不需此欄**，不硬填值。
2. **Q4 定案**：欄位是**留痕，不是保證**，且**契約必須明講**這一點。低成本強化採用：產生提示詞時把宣告值與上一輪 review 事件的 actor 並列印出，**定位為輔助判讀，不得表述為保證**。

## 給執行第二段（改碼）的前置條件

1. ~~`DEV-REVIEW-PROMPT-GUARD1` 合併（同檔互斥解除）~~ → **已解除**：`GUARD1` 於 `1155cec`、`GATE1` 於 `9177ee8` 皆已合併 main。剩餘前置條件是**本 discovery 修訂通過查核**。
2. ~~需求方對 Q1 順序與 Q3 欄位歸屬的裁定~~ → **已於 2026-07-29 定案（見上）。**
3. ~~Q2 遷移策略與 Q4 驗證立場~~ → **已於 2026-07-30 定案（見上）。**

## 待驗證假設（未在本次 Discovery 內證實）

- 「活卡回填成本低」基於欄位寫法一致的觀察，**未實際試填**。〈掃描二〉另指出至少 3 張活卡的值不是機械可推的單一關卡，需求方須逐張確認順序。
- ~~「Initiative 卡不需此欄」…未查證是否有 Initiative 曾被派查核~~ → **iteration 1 已查證**：main `81bcd4d` 的 860 筆事件中，`card_id` 以 `INIT-` 起始且 `type == "review"` 的事件為 **0 筆**。假設成立。
- **新增（iteration 1）**：〈掃描二〉的信號 A／B 是**寬鬆匹配後人工確認**的結果，證明的是「至少 14 張」。同一件事已知有兩種語彙，**不能排除還有第三種語式存在於這兩個 pattern 之外**——這是本次窮舉的邊界，不是零風險宣稱。第二段若要據此清單做回填，須由需求方逐張確認，不得把腳本輸出當成完整宣稱。
- **新增（iteration 1）**：〈Design〉欄與〈查核〉欄一樣兼記「要求」與「結果」（`UX-PLAYER-SCOPE1` 為例），本卡只處理〈查核〉方向的獨立性欄位，**未處理 Design Gate 是否也該結構化**。若第二段的有序清單要涵蓋 Design Gate 這一關，那是另一張卡的範圍。
