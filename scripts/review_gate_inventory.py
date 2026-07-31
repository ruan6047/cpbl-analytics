"""多關卡（multi-gate）查核要求的可重現盤點——**含分類與計數**。

用法：
    uv run python scripts/review_gate_inventory.py                # 工作目錄，markdown 報告
    uv run python scripts/review_gate_inventory.py --rev 81bcd4d  # 釘住某個 commit
    uv run python scripts/review_gate_inventory.py --json         # 機器可讀

**這支腳本的輸出是規劃用的盤點，不是流程判定。**
它為了分類而讀中文自由文字（「交 AI 查核」vs「交跨家族查核」、actor 是不是 `ruan6047`）。
`DEV-REVIEW-PROMPT-GUARD1` 連續三輪證明**從自由文字推流程門檻會被打穿**，因此：

    分類欄一律是「建議分類，待人工確認」，**不得**被任何守衛、preflight 或 gate 判定消費。
    流程門檻只能來自卡面 `review_gates` 與 handoff snapshot（結構化欄位）。

盤點的存在理由正是「這些要求現在還沒有結構化欄位」——分類是為了把它們搬進欄位，
搬完之後這支腳本對那張卡就沒有用了。

## 應然信號（卡面宣告，五種語式）

- **A 正文順序語式**：「人工審…再交…」。並判別後半段交給誰（跨家族／一般 AI／未指明）。
- **B 〈Design〉欄待跑的人工 Design Gate**（排除 `N/A`）。
- **E 章節標題 Gate**：`## Plan Gate`／`## Design Gate` 這類**獨立章節**。
  iteration 1 的腳本沒有這個信號，因此**整張 `OPS-LIVE-SHADOW1` 在視野外**——
  它的兩關（Plan Gate → implementation review）寫在章節標題與驗收條目裡。
- **D 卡面結構化宣告**：`review_gates`／`review_independence` 清單長度 > 1。
- **F 〈查核〉欄與正文互相矛盾**：兩處都宣告了要求但要求不同（`UX-TEAM-HOTZONE1`
  的〈查核〉欄寫「跨模型家族或人工」、正文寫「交 AI 查核」）。

## 實然信號（event log 已發生）

- **C1 同輪多筆 review**：再依 actor 分類細分成「多關卡」與「同一關第二意見」。
- **C2 跨輪不同性質的 review**：`UX-ENTITY-LINKS3` 那種「人工審 → 新 handoff → 跨家族」。
- **C3 第一筆 handoff 之前就有 review**，再分兩種：
  - **Plan Gate 型**（卡有 handoff，只是 review 更早）：`OPS-LIVE-SHADOW1`。
  - **孤兒 review**（整張卡從未寫過 handoff）：`ML-MATCHUP1`、`GAME-RECAP-PA1-BUILD1`…
  兩者都是 handoff-snapshot 模型的邊界案例：**關卡發生時沒有任何一輪可以掛快照**。

引文誤命中以**機械判準**標記（命中行含別張卡卡號），不用人工排除清單。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_DIRS = ("docs/tasks", "docs/archive/tasks")
EVENTS_REL = "docs/control-plane/events.jsonl"

# 需求方 2026-07-31 指定必須逐張重檢的卡；即使零命中也要出現在報告裡並說明為什麼。
FOCUS = ("OPS-LIVE-SHADOW1", "UX-DESIGN-CONFORM1", "UX-ENTITY-LINKS1", "UX-ENTITY-LINKS2",
         "UX-TEAM-HOTZONE1", "UX-TEAM-RECORDS1", "UX-TEAM-STYLE1",
         "DEV-REVIEW-PROMPT-GATE1", "DEV-REVIEW-INDEP-FIELD1")

A_HUMAN = re.compile(r"(人工審|人工核可|人工審核|人工走查|人工審查|本地審|需求方.{0,6}審)")
A_ORDER = re.compile(r"(再交|才交|後才|再由|再給|OK\s*後|後.{0,4}交)")
B_GATE = re.compile(r"Design\s*Gate\s*=|Design\s*Gate.{0,12}核可|待需求方核可|"
                    r"須經需求方\s*sign-off|須\s*sign-off")
E_HEADING = re.compile(r"^##+\s*(Plan\s*Gate|Design\s*Gate|規劃\s*Gate)")
CARD_TOKEN = re.compile(r"[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+")
D_FIELD = re.compile(r"^\s*-\s*`?(review_gates|review_independence)`?\s*[:：]\s*\[(.*)\]\s*$")
REVIEW_FIELD = re.compile(r"^\s*-.*查核：\s*(.*?)\s*$")

# 「交給誰」的判別。**只用於分類欄，不用於任何判定。**
CROSS_FAMILY = re.compile(r"跨模型家族|跨家族|非\s*Claude|非\s*GPT|其他家族")
PLAIN_AI = re.compile(r"AI\s*查核|AI\s*代理|交\s*AI|AI\b")
HUMAN_ACTOR = re.compile(r"ruan6047|需求方")
CROSS_ACTOR = re.compile(r"跨模型家族|跨家族|Gemini|GPT|Codex|Antigravity|非\s*Claude")
# Ledger 投影欄，非查核判定；C2 用它近似「這一輪有沒有被退回」。
REJECTED_STATUSES = {"↩退回", "🔧修正中", "⏸阻塞", "🚨已升級"}


def _read(rev: str | None, rel: str) -> str:
    if rev is None:
        return (ROOT / rel).read_text(encoding="utf-8")
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"],
                          capture_output=True, text=True, check=True).stdout


def _card_paths(rev: str | None) -> list[str]:
    if rev is None:
        return sorted(str(p.relative_to(ROOT)) for d in CARD_DIRS
                      for p in (ROOT / d).glob("*.md"))
    out = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", rev,
                          *(f"{d}/" for d in CARD_DIRS)],
                         capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.split() if p.endswith(".md"))


def _target_of(line: str) -> str:
    """順序語式的後半段交給誰。回傳 cross_family／ai／unspecified。"""
    tail = re.split(r"再交|才交|後才|再由|再給|OK\s*後", line, maxsplit=1)
    seg = tail[-1] if len(tail) > 1 else line
    if CROSS_FAMILY.search(seg):
        return "cross_family"
    if PLAIN_AI.search(seg):
        return "ai"
    return "unspecified"


def _actor_class(actor: str) -> str:
    """review 事件的 actor 屬於哪一類。**建議分類，工具無法驗證真實身分。**

    判別順序有意義，兩個踩過的坑：

    - 「同家族／非跨家族」必須先判：`OPS-LIVE-SHADOW1-REVIEW-002` 的 actor 是
      「GPT-5.6 sibling context@Codex（獨立 Plan Gate；**非跨家族**）」，只看到 `GPT`
      就判跨家族會把它說成它明講自己不是的東西。
    - 「需求方」三個字必須只在 actor **前綴**（`（`／`@` 之前）才算人工：
      `GPT@Codex（跨模型家族查核者…**需求方**轉錄…）` 與
      `獨立查核者@獨立 session（≠ 執行者；**需求方**轉錄）` 都含這三個字，
      但它們講的是「誰轉錄的」，不是「誰查核的」。
    """
    if re.search(r"非跨家族|同家族|sibling", actor):
        return "same_family"
    if CROSS_ACTOR.search(actor):
        return "cross_family"
    if HUMAN_ACTOR.search(re.split(r"[（(@]", actor)[0]):
        return "human"
    return "ai_unspecified"


def scan_cards(rev: str | None) -> tuple[dict[str, dict], dict[str, str]]:
    found: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    paths: dict[str, str] = {}
    for path in _card_paths(rev):
        card_id = path.rsplit("/", 1)[-1][:-3]
        lines = _read(rev, path).splitlines()
        header_end = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
        log_at = next((i for i, l in enumerate(lines) if l.startswith("## Log")), len(lines))
        paths[card_id] = path
        review_field = None
        for i, line in enumerate(lines[:log_at], 1):
            if A_HUMAN.search(line) and A_ORDER.search(line):
                found[card_id]["A"].append(
                    {"line": i, "text": line.strip(), "target": _target_of(line),
                     "citation": any(t != card_id for t in CARD_TOKEN.findall(line))})
            if E_HEADING.match(line):
                found[card_id]["E"].append(
                    {"line": i, "text": line.strip(), "target": "impl", "citation": False})
        for i, line in enumerate(lines[:header_end], 1):
            if line.startswith("- Design：") and B_GATE.search(line) and "N/A" not in line:
                found[card_id]["B"].append(
                    {"line": i, "text": line.strip(), "target": "impl",
                     "citation": any(t != card_id for t in CARD_TOKEN.findall(line))})
            m = D_FIELD.match(line)
            if m and len([x for x in m.group(2).split(",") if x.strip()]) > 1:
                found[card_id]["D"].append(
                    {"line": i, "text": line.strip(), "target": "declared", "citation": False})
            mr = REVIEW_FIELD.match(line)
            if mr and "查核：" in line and review_field is None:
                review_field = mr.group(1)
        # F：〈查核〉欄與正文順序語式對「交給誰」的說法不一致。
        if review_field and found[card_id].get("A"):
            field_cf = bool(CROSS_FAMILY.search(review_field))
            for hit in found[card_id]["A"]:
                if hit["citation"]:
                    continue
                if field_cf and hit["target"] == "ai":
                    found[card_id]["F"].append(
                        {"line": hit["line"], "target": "conflict", "citation": False,
                         "text": f"〈查核〉欄要求跨家族／人工（{review_field[:60]}），"
                                 f"正文卻只寫交 AI 查核（L{hit['line']}）"})
    hit = {c: dict(s) for c, s in found.items() if any(k in s for k in "ABDEF")}
    return hit, paths


def scan_events(rev: str | None) -> tuple[dict[str, dict], dict[str, int]]:
    """實然信號 C1／C2／C3，附 actor 分類。"""
    by_card: dict[str, list[dict]] = defaultdict(list)
    total = 0
    for line in _read(rev, EVENTS_REL).splitlines():
        if line.strip():
            e = json.loads(line)
            by_card[e["card_id"]].append(e)
            total += 1
    out: dict[str, dict] = {}
    stats = {"events": total, "cards": len(by_card), "reviews": 0,
             "reviews_without_result": 0, "rounds": 0}
    for card, evs in by_card.items():
        rounds: list[list[dict]] = []
        pre_handoff: list[dict] = []
        current: list[dict] | None = None
        for e in evs:
            t = e.get("type")
            if t == "review":
                stats["reviews"] += 1
                if not (e.get("review_result") or "").strip():
                    stats["reviews_without_result"] += 1
            if t == "handoff":
                if current is not None:
                    rounds.append(current)
                current, stats["rounds"] = [], stats["rounds"] + 1
            elif t == "merge":
                if current is not None:
                    rounds.append(current)
                current = None
            elif t == "review":
                (current if current is not None else pre_handoff).append(e)
        if current is not None:
            rounds.append(current)

        def brief(e: dict) -> dict:
            return {"event_id": e["event_id"], "actor": e.get("actor", ""),
                    "actor_class": _actor_class(e.get("actor", "")),
                    "occurred_at": e.get("occurred_at", ""),
                    "delivery_status": e.get("delivery_status", ""),
                    "review_result": e.get("review_result", "")}

        c1 = [[brief(e) for e in r] for r in rounds if len(r) > 1]
        # C2 只在「前一輪**沒有被退回**、下一輪換了另一種性質的查核者」時成立。
        # 少了退回這一項，`DEV-REVIEW-PROMPT-GATE1` 的三次 iteration（REJECT → 修 →
        # 換人再查）會被誤判成多關卡——那是同一關重跑，不是兩關。
        # `delivery_status` 是 Ledger 投影欄、不是查核判定；這裡拿它當**盤點**的
        # 近似訊號，正因為現行 schema 沒有 `gate_result` 可用（契約 §1 第四點）。
        nonempty = [r for r in rounds if r]
        c2_pairs = []
        for prev, nxt in zip(nonempty, nonempty[1:], strict=False):
            if prev[-1].get("delivery_status") in REJECTED_STATUSES:
                continue
            if {_actor_class(e.get("actor", "")) for e in prev} != \
               {_actor_class(e.get("actor", "")) for e in nxt}:
                c2_pairs.append([brief(e) for e in prev + nxt])
        c2 = bool(c2_pairs) and not c1
        has_handoff = any(e.get("type") == "handoff" for e in evs)
        if c1 or c2 or pre_handoff:
            out[card] = {
                "no_handoff_at_all": not has_handoff,
                "c1_rounds": c1,
                "c1_kinds": ["multi_gate" if len({e["actor_class"] for e in r}) > 1
                             else "second_opinion" for r in c1],
                "c2_cross_round": c2_pairs if c2 else [],
                "c3_pre_handoff": [brief(e) for e in pre_handoff],
            }
    return out, stats


# 建議分類的優先序（**僅供人工確認，不得被判定消費**）。
KIND_LABEL = {
    "human_then_cross_family": "人工審 → 跨家族查核",
    "human_then_ai": "人工審 → 一般 AI 查核（未要求跨家族）",
    "human_then_unspecified": "人工審 → 未指明交給誰",
    "plan_gate_then_impl": "Plan／Design Gate → 實作查核",
    "declared_multi_gate": "卡面結構化欄位已宣告多關卡",
    "single_gate": "單一關卡",
}


def classify(sig: dict) -> list[str]:
    kinds = []
    for hit in sig.get("A", []):
        if hit["citation"]:
            continue
        kinds.append({"cross_family": "human_then_cross_family",
                      "ai": "human_then_ai"}.get(hit["target"], "human_then_unspecified"))
    if any(not h["citation"] for h in sig.get("E", []) + sig.get("B", [])):
        kinds.append("plan_gate_then_impl")
    if sig.get("D"):
        kinds.append("declared_multi_gate")
    return sorted(set(kinds)) or ["single_gate"]


def build(rev: str | None) -> dict:
    cards, paths = scan_cards(rev)
    events, stats = scan_events(rev)
    rows = []
    for card_id in sorted(set(cards) | set(events) | set(FOCUS)):
        sig = cards.get(card_id, {})
        evt = events.get(card_id, {})
        substantive = {k: v for k, v in sig.items()
                       if any(not h["citation"] for h in v)}
        kinds = classify(substantive) if substantive else []
        de_facto = []
        de_facto += evt.get("c1_kinds", [])
        if evt.get("c2_cross_round"):
            de_facto.append("cross_round_gates")
        if evt.get("c3_pre_handoff"):
            de_facto.append("orphan_review_no_handoff" if evt.get("no_handoff_at_all")
                            else "pre_handoff_gate")
        if not (sig or evt or card_id in FOCUS):
            continue
        rows.append({
            "card_id": card_id,
            "focus": card_id in FOCUS,
            "path": paths.get(card_id, "（卡片檔不存在）"),
            "signals": "".join(k for k in "ABDEF" if k in sig)
                       + ("C" if evt else ""),
            "citation_only": bool(sig) and not substantive,
            "declared_kinds": kinds,
            "de_facto_kinds": sorted(set(de_facto)),
            "hits": sig,
            "events": evt,
        })
    matched = [r for r in rows if r["signals"]]
    tally_declared = Counter(k for r in matched if not r["citation_only"]
                             for k in r["declared_kinds"])
    tally_de_facto = Counter(k for r in matched for k in r["de_facto_kinds"])
    return {"rev": rev or "（工作目錄）", "cards_scanned": len(_card_paths(rev)),
            "stats": stats, "rows": rows,
            "counts": {
                "matched": len(matched),
                "substantive": sum(1 for r in matched if not r["citation_only"]),
                "citation_only": sum(1 for r in matched if r["citation_only"]),
                "declared_kinds": dict(tally_declared),
                "de_facto_kinds": dict(tally_de_facto)}}


def render(data: dict) -> str:
    c, st = data["counts"], data["stats"]
    out = [f"# 多關卡查核要求盤點（rev={data['rev']}）", "",
           f"卡片母體 {data['cards_scanned']} 張；event log {st['events']} 筆／{st['cards']} 張卡；"
           f"review 事件 {st['reviews']} 筆，其中 **{st['reviews_without_result']} 筆沒有 "
           f"`review_result`**；查核輪次 {st['rounds']} 輪。", "",
           f"**命中 {c['matched']} 張**（實質 {c['substantive']}、僅引文嫌疑 {c['citation_only']}）。", "",
           "> **分類欄是建議，待人工確認。** 它讀中文自由文字，"
           "**不得被守衛／preflight／gate 判定消費**——流程門檻只能來自結構化的 "
           "`review_gates` 與 handoff snapshot。", "",
           "## 計數：卡面宣告的關卡型態（一張卡可落在多型）", "",
           "| 型態 | 張數 |", "|---|---|"]
    for k, n in sorted(c["declared_kinds"].items(), key=lambda x: -x[1]):
        out.append(f"| {KIND_LABEL.get(k, k)} | {n} |")
    out += ["", "## 計數：event log 的實然型態", "", "| 型態 | 卡數 |", "|---|---|"]
    labels = {"multi_gate": "同輪多關卡（不同性質的查核者）",
              "second_opinion": "同輪第二意見（同性質查核者再查一次）",
              "cross_round_gates": "跨輪不同性質關卡（人工審 → 新 handoff → AI 查核）",
              "pre_handoff_gate": "有 handoff，但第一次 handoff 之前就有 review（Plan Gate 型）",
              "orphan_review_no_handoff": "**全卡沒有任何 handoff 事件**，review 無所依附"
                                          "（新契約的 snapshot 無處可放）"}
    for k, n in sorted(c["de_facto_kinds"].items(), key=lambda x: -x[1]):
        out.append(f"| {labels.get(k, k)} | {n} |")

    def block(row: dict) -> list[str]:
        flag = "　⚠**全部命中皆疑為引用他卡**" if row["citation_only"] else ""
        b = ["", f"### {row['card_id']}　[{row['signals'] or '無命中'}]{flag}", "",
             f"- 檔案：`{row['path']}`"]
        if row["declared_kinds"]:
            b.append("- 宣告型態（建議）：" + "、".join(
                str(KIND_LABEL.get(k, k)) for k in row["declared_kinds"]))
        if row["de_facto_kinds"]:
            b.append("- 實然型態：" + "、".join(
                str(labels.get(k, k)) for k in row["de_facto_kinds"]))
        for kind in "ABDEF":
            for h in row["hits"].get(kind, []):
                mark = "　⚠引用他卡" if h["citation"] else ""
                tgt = f"（交給：{h['target']}）" if h["target"] not in ("declared", "conflict") else ""
                b.append(f"- 信號 {kind} L{h['line']}{mark}{tgt}：{h['text'][:165]}")
        evt = row["events"]
        for r, kind in zip(evt.get("c1_rounds", []), evt.get("c1_kinds", []), strict=False):
            b.append(f"- 信號 C1 同輪多筆 review（{labels.get(kind, kind)}）：")
            b += [f"    - `{e['event_id']}`　{e['occurred_at'][:16]}　[{e['actor_class']}] "
                  f"{e['actor'][:38]}　{e['delivery_status']}　"
                  f"{e['review_result'][:40] or '（result 未填）'}" for e in r]
        if evt.get("c2_cross_round"):
            b.append("- 信號 C2 跨輪不同性質關卡：")
            b += [f"    - `{e['event_id']}`　{e['occurred_at'][:16]}　[{e['actor_class']}] "
                  f"{e['actor'][:38]}" for r in evt["c2_cross_round"] for e in r]
        if evt.get("c3_pre_handoff"):
            b.append("- 信號 C3 **第一次 handoff 之前**的 review：")
            b += [f"    - `{e['event_id']}`　{e['occurred_at'][:16]}　[{e['actor_class']}] "
                  f"{e['actor'][:38]}　{e['delivery_status']}" for e in evt["c3_pre_handoff"]]
        if not row["signals"]:
            b.append("- **零命中**：五個應然信號與三個實然信號皆未觸發"
                     "（見〈讀法〉——零命中不等於單關卡，只等於沒有可機械辨識的語式）。")
        return b

    out += ["", "## 需求方指定重檢的卡", ""]
    for row in data["rows"]:
        if row["focus"]:
            out += block(row)
    out += ["", "## 其餘命中", ""]
    for row in data["rows"]:
        if not row["focus"] and row["signals"]:
            out += block(row)
    out += ["", "## 讀法", "",
            "- 應然（A／B／D／E／F）是卡面宣告，實然（C1／C2／C3）是 event log 已發生的事；"
            "**兩者經常不一致**，不一致本身就是要搬進結構化欄位的理由。",
            "- **零命中 ≠ 單關卡**：只代表沒有可機械辨識的語式。已知至少五種語式，"
            "不能排除第六種。任何回填都須由需求方逐張確認。",
            "- `⚠引用他卡` 是機械判準（命中行含別張卡卡號），不是人工排除清單；"
            "腳本不隱藏任何命中。",
            "- actor 分類讀的是人工轉錄的字串，**工具無法驗證真實模型家族或人類身分**"
            "（契約 §8 Q4）。", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default=None, help="git revision（預設讀工作目錄）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    data = build(args.rev)
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else render(data))


if __name__ == "__main__":
    main()
