# DEV-TRAILER-GUARD-SCOPE1 修 trailer 守衛的取樣範圍〔T2；🟡工具〕

- 需求：ruan6047（2026-07-28 於 `ML-PITCHER-SCORELESS1` 合併時暴露）　規劃：本卡 spec　分支：`ai/<執行者>/DEV-TRAILER-GUARD-SCOPE1`
- 執行：待指派　查核：待指派（≠ 執行）
- worktree：—（認領後建立）
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`tests/test_commit_trailers.py` 的檢查範圍改為由 commit 本身的性質決定，
  而非由「有沒有推過」決定。

## 問題陳述

守衛用 `origin/main..HEAD` 取樣，docstring 自述是「執行分支模式，在 main 上自動跳過」。

那是拿**「不在 `origin/main` 裡」當作「這是執行分支的 commit」的標記**。兩者在執行者的
情境下重合，但在 Coordinator 的情境下不重合——剛在 main 上合併、還沒 push 的狀態同樣
符合該標記。

後果是**同一個 commit 的判定會因為推沒推過而翻轉**：

- 合併後未推 → 守衛把 main 上的 Coordinator commit 當成執行分支 commit 來驗，亮紅。
- push 之後 → `origin/main..HEAD` 變空 → 自動跳過 → 轉綠。

轉綠不是因為 trailer 補好了，是因為取樣範圍空了。**一個會被 push 動作消音的守衛，
等於鼓勵用 push 來讓它閉嘴。**

2026-07-28 實地發生：Coordinator 的兩個 control-plane commit 確實缺
`Requested-by`／`Implemented-by`（守衛抓對了），但抓到的理由是可疑的——同樣的缺陷
如果發生在已推的 commit 上就完全看不到。

## 為什麼值得修而不是忍

守衛誤鳴的代價不是那一次的紅燈，是**紅燈的可信度**。Coordinator 每一次在 main 上合併
都會撞到它，撞久了就會養成「這個紅燈可以忽略」的反射，而那正是這個守衛當初被寫出來
要取代的東西（原本靠「執行者記得寫＋查核者記得驗」，兩層在同一天失守）。

同一個病在 `ML-PITCHER-SCORELESS1` 出現了十一輪：**檢查某個看得見的標記，
而該成立的性質從來不是那個標記的存在或缺席。** 這次它出現在守衛自己身上。

## 目標

讓「這個 commit 要不要驗 trailer」由 commit 的性質決定。方向由執行者評估，例如：

- 以 commit 是否已存在於**任何** remote-tracking ref 判斷（而非只看 `origin/main`）；
- 或改為驗「所有本地新 commit」，並讓 main 上的 Coordinator commit 也適用同一套必要集合
  ——事實上專案慣例本來就要求它們帶（見 `958caf1`、`150770b`），所以這可能才是正解：
  **不是縮小範圍，是承認範圍本來就該包含它們**；
- 若採後者，需處理歷史 commit 不回溯的問題（既有 `fce189a` 等只帶 `Implemented-by`）。

執行者應先判斷哪一個才是原本的意圖，再改——**不要為了讓紅燈消失而改**。

## 紅線

1. **不得以「推過就跳過」的任何變體收場**。判定必須與 ref 狀態無關。
2. **必須有變異檢驗**：構造一個缺 trailer 的 commit，證明新守衛在**推前與推後**都抓得到。
3. 歷史 commit 的處置（回溯或豁免）要明寫理由，不得靜默放行。

## 驗收條件

- [ ] 判定不再依賴 `origin/main..HEAD`，且理由寫在 docstring。
- [ ] 變異檢驗證明推前推後判定一致。
- [ ] 歷史 commit 的豁免邊界明寫。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 驗證

- [ ] 查核者自行構造缺 trailer 的 commit，在推前與推後各驗一次。
- [ ] 查核者確認新判準不會反過來讓 Coordinator 的正常 main commit 大量誤鳴。

## 邊界

- 只動守衛，不回頭改寫既有歷史。
- 預估 S。

## Log

- 2026-07-28 於 `ML-PITCHER-SCORELESS1` 合併時暴露並開卡。同日該卡的合併事件
  （`ML-PITCHER-SCORELESS1-MERGE-023`）已記錄完整經過。
