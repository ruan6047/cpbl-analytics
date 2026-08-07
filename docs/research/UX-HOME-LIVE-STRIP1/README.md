# UX-HOME-LIVE-STRIP1 取證產物

> 卡片：[Issue #81](https://github.com/ruan6047/cpbl-analytics/issues/81)（T3，`INIT-PRODUCT-UX`）
> 本目錄回應查核 finding **HOMESTRIP1-R1-001**：交付報告主張「96 組逐位對照零差異」，
> 但產生器留在 scratchpad，該宣稱無法從分支單獨重跑。

## `bases_outs_extraction_proof.py`

證明壘包圖（`BasesOuts`）從 `game-board.tsx` 上抽到 `ui.tsx` 之後，**賽況頁的渲染輸出沒有
視覺變化**，而唯一的差異是後續追加裁定要求補上的 `role="img"`。

```bash
cd web && npm install    # 只需一次；腳本借用 web 的 react-dom 與 tsc
cd .. && uv run python docs/research/UX-HOME-LIVE-STRIP1/bases_outs_extraction_proof.py
```

預期輸出（exit code 0）：

```
基準 a6331cc（上抽前）vs 工作樹現況
  逐位對照組合數                 : 96
  (1) 剝掉預期新增後不一致       : 0   ← 零視覺變化
  (2) 預期屬性計數異常           : 0   ← 恰好新增一個 a11y 屬性
  賽況頁尺寸樣本 svg 開頭        : <svg viewBox="0 0 120 116" width="52" height="50.266666666666666" aria-label="壘上一壘、三壘，2 出局" role="img">
  首頁新增能力 outs=null         : 替代文字「壘上一壘、三壘，出局數未知」、亮起的出局點 0 顆
```

任一不一致數非 0 時 **exit code 為 1**，並印出前 5 組不符的實際輸出。

### 它比對的是什麼

兩份**真實原始碼**（不是人工抄寫的副本——抄本只能證明抄得對）被抽出來編進同一個模組：

| | 來源 |
|---|---|
| 上抽前 | `git show a6331cc:web/src/components/game-board.tsx` 的私有 `BasesOuts`；取不到時退回同目錄的凍結副本 `legacy-bases-outs.a6331cc.tsx` |
| 上抽後 | 工作樹現況 `web/src/components/ui.tsx` 的共用 `BasesOuts` |

需要凍結副本是因為本 repo 的 merge 會被 `pull --rebase` 線性化而**改寫 SHA**：本卡合併之後，
只有 `main` 的人可能已經 `git show a6331cc` 不到了，那時腳本會變成無法重跑的擺設——正是它
要修的那個 finding。git 仍是權威來源，**兩者都拿得到時腳本會斷言逐字相同**，所以凍結副本
無法悄悄漂移；不一致時腳本拒絕作證（exit 1）而不是挑一個來用。

以 `react-dom/server` 渲染成字串，窮舉 **8 種壘況 × 出局數 0–3 × 3 種尺寸 ＝ 96 組**逐位
比對。呼叫點的 props 對應（`b1/b2/b3` → `bases.{first,second,third}`）也涵蓋在內：harness
傳入的映射與 `game-board.tsx` 呼叫點寫的完全一致。

預期差異參數化為 `EXPECTED_ADDITIONS`，拆成兩個獨立斷言：

1. 剝掉預期新增的屬性後必須逐位相同 → **零視覺變化**。
2. 該屬性在上抽前 0 次、上抽後恰好 1 次 → **沒有夾帶別的東西進來**。

第 2 條不是多餘的：只驗第 1 條，任何被放進剝除清單的東西都會從縫隙溜過去。

### 反例對照（證明它不是橡皮圖章）

| 注入的缺陷 | 結果 |
|---|---|
| 菱形改回首頁舊比例（30→22） | (1) 96 組不一致、exit 1 |
| 偷渡一個 `data-extra="x"` 屬性 | (1) 96 組不一致、exit 1 |
| 竄改凍結副本（git 仍取得到） | 拒絕作證、exit 1 |
| 在沒有 `a6331cc` 的 clone 上跑 | 走凍結副本、印出 note、exit 0 |
| 未注入缺陷 | 兩項皆 0、exit 0 |

### 為什麼不掛進 pytest／npm test

刻意不升成常設守衛（跨家族查核者亦明示不要求）。基準 SHA 釘死在腳本的 `BEFORE` 常數，
它回答的是「相對於上抽前那一版有沒有變」——這個問題只在上抽這一次成立。改成常設守衛
就得回答「基準怎麼維護」：每次改動都重釘基準的守衛會退化成橡皮圖章，而不重釘就會在下一次
合理的視覺調整時擋路。要升級請另開卡先解決基準策略。
