"""UX-HOME-LIVE-STRIP1 取證工具：證明壘包圖上抽為共用元件後，賽況頁的渲染輸出沒有變。

用法（repo 根目錄，需先 `cd web && npm install`）：

    uv run python docs/research/UX-HOME-LIVE-STRIP1/bases_outs_extraction_proof.py

預期輸出（不一致數皆為 0，exit code 0）::

    基準 a6331cc（上抽前）vs 工作樹現況
      逐位對照組合數                 : 96
      (1) 剝掉預期新增後不一致       : 0   ← 零視覺變化
      (2) 預期屬性計數異常           : 0   ← 恰好新增一個 a11y 屬性

## 這支腳本在證明什麼

`BasesOuts`（品字壘包 ＋ 兩顆出局點）原本是 `game-board.tsx` 的私有實作，首頁「今日賽事」
卡另有一份**比例不同**的版本（菱形 25% vs 18%、出局點 r=9 vs 8、viewBox 116 vs 112）。
需求方裁定以賽況頁那份為準上抽到 `ui.tsx`，並要求**賽況頁不得有視覺變化**——那塊是 ESPN
風格狀態板，是需求方在意的東西。後續追加裁定又要補 `role="img"`（全站慣例），於是宣稱
從「零視覺變化」變成「零視覺變化 ＋ 恰好一個 a11y 屬性新增」，兩者都要有證據。

## 取證方式：渲染輸出逐位對照，不是讀碼比對

腳本把**兩個版本的真實原始碼**抽出來編進同一個模組：

* 上抽前那份：`git show a6331cc:web/src/components/game-board.tsx`
* 上抽後那份：工作樹現況的 `web/src/components/ui.tsx`

兩者都是從檔案裡切出來的，不是人工抄寫的副本——手抄的副本只能證明抄得對。接著用
`react-dom/server` 把兩者渲染成字串，窮舉 8 種壘況 × 出局數 0–3 × 三種尺寸 ＝ 96 組
逐位比對。呼叫點的 props 對應（`b1/b2/b3` → `bases.{first,second,third}`）也由這裡涵蓋：
harness 傳入的映射與 `game-board.tsx` 呼叫點寫的完全一致。

**預期差異是參數化的**（`EXPECTED_ADDITIONS`），且拆成兩個獨立斷言：

1. 把預期新增的屬性剝掉後必須逐位相同 → 零視覺變化。
2. 該屬性在上抽前為 0 次、上抽後恰好 1 次 → 沒有夾帶別的東西進來。

第 2 條不是多餘的：只驗第 1 條的話，任何被放進剝除清單的東西都會從縫隙溜過去。

## 這不是常設守衛

刻意**不**掛進 pytest／npm test（查核者亦明示不要求升級）。它是一次性取證工具，基準 SHA
釘死在 `BEFORE`；要升成長期守衛得先想清楚基準怎麼維護（每次改動都要重釘一次基準的守衛
會退化成橡皮圖章）。升級與否見交付報告的提案節。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# 上抽前的最後一個 commit。基準釘死：這支腳本要回答的是「相對於那一版有沒有變」。
BEFORE = "a6331ccff39fe062b2b44e1f6f4542307b8453bd"


def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return Path(out)


def _extract(source: str, marker: str) -> str:
    """從原始碼切出一個頂層函式（自 `marker` 起至配對的收尾大括號）。"""
    start = source.index(marker)
    return source[start:source.index("\n}\n", start) + 3]


def _legacy_source(root: Path) -> str:
    """上抽前的 `BasesOuts` 原始碼。

    優先走 git（權威來源），取不到時退回同目錄的凍結副本。**兩者都拿得到時斷言逐字相同**
    ——否則凍結副本可以悄悄漂移，取證就變成自說自話。

    需要退路是因為本 repo 的 merge 會被 `pull --rebase` 線性化而改寫 SHA：本卡合併之後，
    只有 `main` 的人可能已經 `git show {BEFORE}` 不到了，那時這支腳本就會變成無法重跑的
    擺設——正是它要修的那個 finding。
    """
    frozen_path = Path(__file__).with_name(f"legacy-bases-outs.{BEFORE[:7]}.tsx")
    frozen = _extract(frozen_path.read_text(encoding="utf-8"), "function BasesOuts(")

    from_git = subprocess.run(
        ["git", "-C", str(root), "show", f"{BEFORE}:web/src/components/game-board.tsx"],
        capture_output=True, text=True,
    )
    if from_git.returncode != 0:
        print(f"  （note）{BEFORE[:7]} 已不在此 clone 的歷史中，改用凍結副本 "
              f"{frozen_path.name}")
        return frozen

    live = _extract(from_git.stdout, "function BasesOuts(")
    if live != frozen:
        raise SystemExit(
            f"凍結副本與 {BEFORE[:7]} 的 git 內容不一致——取證基準已被竄改，"
            f"請還原 {frozen_path.name}"
        )
    return live


def _build_proof(root: Path) -> str:
    legacy = _legacy_source(root).replace(
        "function BasesOuts(", "function LegacyBasesOuts(", 1)

    shared_file = (root / "web/src/components/ui.tsx").read_text(encoding="utf-8")
    shared = _extract(shared_file, "export function BasesOuts(").replace(
        "export function BasesOuts(", "function SharedBasesOuts(", 1)

    return f"""import * as React from "react";
import {{ renderToStaticMarkup }} from "react-dom/server";
{legacy}
{shared}
const EXPECTED_ADDITIONS = [' role="img"'];
const strip = (s) => EXPECTED_ADDITIONS.reduce((acc, a) => acc.split(a).join(""), s);

const combos = [];
for (const a of [false, true]) for (const b of [false, true]) for (const c of [false, true]) {{
  combos.push([a, b, c]);
}}

let checked = 0;
const visualDiffs = [];
const attrProblems = [];
for (const [b1, b2, b3] of combos) for (const outs of [0, 1, 2, 3]) for (const size of [52, 38, 18]) {{
  const before = renderToStaticMarkup(React.createElement(LegacyBasesOuts, {{ b1, b2, b3, outs, size }}));
  const after = renderToStaticMarkup(React.createElement(SharedBasesOuts, {{
    bases: {{ first: b1, second: b2, third: b3 }}, outs, size,
  }}));
  checked += 1;
  const key = `bases=${{[b1, b2, b3]}} outs=${{outs}} size=${{size}}`;
  if (strip(after) !== before) {{
    visualDiffs.push(`${{key}}\\n  before: ${{before}}\\n  after : ${{strip(after)}}`);
  }}
  for (const addition of EXPECTED_ADDITIONS) {{
    const nBefore = before.split(addition).length - 1;
    const nAfter = after.split(addition).length - 1;
    if (nBefore !== 0 || nAfter !== 1) {{
      attrProblems.push(`${{key}} → ${{addition}} before=${{nBefore}} after=${{nAfter}}`);
    }}
  }}
}}

console.log(`基準 {BEFORE[:7]}（上抽前）vs 工作樹現況`);
console.log(`  逐位對照組合數                 : ${{checked}}`);
console.log(`  (1) 剝掉預期新增後不一致       : ${{visualDiffs.length}}   ← 零視覺變化`);
console.log(`  (2) 預期屬性計數異常           : ${{attrProblems.length}}   ← 恰好新增一個 a11y 屬性`);
for (const d of [...visualDiffs, ...attrProblems].slice(0, 5)) console.log("  " + d);

const sample = renderToStaticMarkup(React.createElement(SharedBasesOuts, {{
  bases: {{ first: true, second: false, third: true }}, outs: 2, size: 52,
}}));
console.log(`  賽況頁尺寸樣本 svg 開頭        : ${{/<svg[^>]*>/.exec(sample)[0]}}`);
const nul = renderToStaticMarkup(React.createElement(SharedBasesOuts, {{
  bases: {{ first: true, second: false, third: true }}, outs: null, size: 38,
}}));
console.log(`  首頁新增能力 outs=null         : 替代文字「${{/aria-label="([^"]*)"/.exec(nul)[1]}}」`
  + `、亮起的出局點 ${{(nul.match(/circle[^>]*var\\(--color-accent\\)/g) || []).length}} 顆`);
process.exit(visualDiffs.length === 0 && attrProblems.length === 0 ? 0 : 1);
"""


def main() -> int:
    root = _repo_root()
    modules = root / "web/node_modules"
    if not (modules / "react-dom").is_dir():
        print("需要 web 的依賴：先在 repo 根目錄跑 `cd web && npm install`", file=sys.stderr)
        return 2

    # 兩份實作都是 TSX，但抽出來後只用到型別註記；直接交給專案自己的 tsc 轉譯，
    # 不引入任何新的 build 依賴。
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
        # node 的模組解析從檔案往上找 node_modules；symlink 讓暫存目錄借用 web 的依賴，
        # 不必把產物寫進 repo。
        (work / "node_modules").symlink_to(modules)
        (work / "proof.tsx").write_text(_build_proof(root), encoding="utf-8")

        compiled = subprocess.run(
            ["npx", "tsc", str(work / "proof.tsx"), "--jsx", "react", "--module", "esnext",
             "--target", "es2022", "--moduleResolution", "bundler", "--skipLibCheck",
             "--outDir", str(work / "out")],
            cwd=root / "web", capture_output=True, text=True,
        )
        emitted = work / "out/proof.js"
        if not emitted.exists():
            print(compiled.stdout or compiled.stderr, file=sys.stderr)
            print("tsc 未產出 proof.js", file=sys.stderr)
            return 2
        # tsc 的型別錯誤（找不到 react 的宣告檔）不影響轉譯結果，故只在無產出時才視為失敗。
        run_target = emitted.with_suffix(".mjs")
        emitted.rename(run_target)
        return subprocess.run(["node", str(run_target)], cwd=work).returncode


if __name__ == "__main__":
    raise SystemExit(main())
