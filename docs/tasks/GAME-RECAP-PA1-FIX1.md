# GAME-RECAP-PA1-FIX1 canonical PA 表的打席切分與出局數正確性〔T4；🔴資料正確性〕

- 需求：ruan6047（2026-07-29 依 `ML-PITCHER-SCORELESS2` §8 點名的底層資料缺陷指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/GAME-RECAP-PA1-FIX1`
- 執行：Claude Fable 5@Claude Code（建議 L4；canonical 表的資料正確性，錯誤不會讓測試變紅）　查核：待指派（≠ 執行；**跨模型家族或人工**——本卡有統計紅線）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: data-migration`（重建全庫 published PA build；無 schema 變更）
- 部署：是　環境：production（本機重建通過並經查核後另議）　PR：—　Merge SHA：—
- 範圍：修 `cpbl-build-pa` 的 island 切分與 `pre_state.outs` 來源，加不變式 fail-closed，重建本機 canonical PA 表。

## 問題陳述

`cpbl.game_plate_appearances` 有兩類資料正確性缺陷，皆由 2026-07-29 的診斷實測確認
（全庫 4,276 場、1,334,122 個 livelog 事件）。

**缺陷一：一個打席被切成兩個 PA。** 134 個半局的 `outcome_family in ('out','sacrifice')`
且 `state='ready'` 的 PA 超過 3 筆——一個半局不可能有超過 3 個出局。

**缺陷二：`pre_state.outs` 未遞增。** 1,175 組 `(year, kind_code, game_sno, half, inning, pre_outs)`
有多筆出局 PA；例 `2018/A/78` 第 4 局下四筆 PA 的 `pre_outs` 全是 0。

兩者合計使「以 PA 出局歸屬證明某出局屬於別的投手」這條路不可用。
`docs/research/ML-PITCHER-SCORELESS2_RESULTS.md` §8 記載該路徑可把連續無自責分尾段採計率
從一軍 29 場／156 outs 提到 46 場／248 outs、二軍 22／167 提到 66／379，
但因上述前提被證偽而**刻意未出貨**（該指標有「只能低估不得高估」的紅線）。
本卡修好資料正確性，該路徑才有重新評估的基礎——**但本卡不做那個評估**。

## 根因（已實測確認，非推測）

**缺陷一是 builder bug，不是來源重複。**

關鍵事實：`game_livelog.action_name` 是**打席層級的最終結果，被複製到該打席的每一列**，
不是逐事件動作。證據在 `2018/A/116` 7 局下——`0720010000`／`0720011000` 兩列在三振發生前
就已標 `action_name=三振`，真正的三振在 `0720014000`。

在此前提下，`pa_build.build_islands` 以 `(inning_seq, visiting_home_type, hitter_acnt)` 切界
就會出錯：livelog 把**打席中途代打換人**記成打者變化（`is_change_player` 公告列，
球數 1-2 續投到 1-3、`batting_order` 全程不變），island 被切成兩段，
兩段各自被 `_terminal_event` 取到**同一個被複製的 `action_name`**，
於是雙雙分類為 `completed_pa` → 一個打席記成兩個 PA、一個出局記成兩次。

全庫共 **303 對 island** 屬此型態（2018–2026 每年皆有，2022 後每年 50–65 例）。
來源本身自洽（球數續投、棒次不變）——**問題是 island 規則沒有涵蓋這個型態**。

**缺陷二是 builder 信任了一個會落後的來源欄位。**

`_state_snapshot(start_ev)` 直接讀 island 首列的 `out_cnt`。以 `content` 的「N人出局」
（＝該事件後的累計出局數）重建每半局 running outs 當權威值對照：有真實投球的 island
328,508 個，`out_cnt` 與推導值**不一致 2,157 個（0.657%）**，差值 `-1` 有 2,148 例、
`-2` 有 7 例、`+2` 有 2 例——幾乎全是來源欄位慢一拍。
推導值本身可信：71,023 個半局收在恰好 3 出局。

## 離線驗證（開卡前已跑，用真實資料，未寫入任何東西）

合併判準：同半局的打者變化，若 (R1) 球數未歸零續投（新打席首列球數必 ≤1，
故 ≥2 且未回退即同一 PA），或 (R2) 同一 `batting_order` 槽位且原打者未面對任何真實投球
／球數未回退 → 視為同一 PA。

- 現況：半局 >3 出局 PA = 134；`(半局, pre_outs)` 重複 = 1,175
- 只修 island 切分：**1** ／ 1,013
- 併修 outs 推導：**1** ／ **1**

殘留的 1 例是 `2019/A/173`：來源列 `0110002000` 的 `inning_seq` 誤標成 7（應為 1）、
且 `0110001000` 帶 `action_name=三振`（該打席實際是四壞球）——**真正的來源資料損壞**，
應由本卡的 fail-closed 不變式隔離，不得被修正邏輯吞掉。

較寬鬆的合併規則會把「零投球故意四壞（`故意四壞球上壘。`）＋緊接著的打席間代打」
誤併成一個 PA（如 `2018/A/9` 9 局下、`2018/A/16` 8 局下）。**這是設計邊界，
執行者與查核者都必須確認新規則沒有踩進去。**

## 需求方已定案（2026-07-29，不重新討論）

1. **`pre_state.outs` 改用 `content` 推導的 running outs**；`out_cnt` 只作對照。
   canonical 欄位語意改變，須在 `docs/reference/GLOSSARY.md` 記錄。
2. **不變式 fail-closed 粒度＝逐場**：任一半局出局 PA > 3 → 該場不 publish
   （build 標 `reconciliation_required`／PA 標 `unreliable`、保留舊 published 供稽核），
   其餘場次照常發布。不得只記 log。
3. **本機全庫重建押到 `ML-PITCHER-SCORELESS2` 查核結案後**再跑（見「邊界」）。

## 待執行者設計並在交付說明的關鍵決策

`reconcile()` 比對新 PA 與 published fingerprint；island 合併會改變 membership →
fingerprint 全面改變 → 依現行邏輯**每一場都會落入 `reconciliation_required`，零場發布**。
reconciliation 的用途是攔截**來源漂移**，不是攔截**builder 升級**；
執行者須設計一條可稽核的區分方式（例如：published build 的 `builder_version` 與新 build
不同時，fingerprint 變更屬預期，可發布並把 diff 記入 `validation_summary`；
`builder_version` 相同時的變更仍一律 fail closed）。
**fail-closed 行為不得因此被削弱**，此設計是查核重點。

## 同步 SSoT（漏改會被 conformance test 擋，且造成語意漂移）

island 規則有四處事實來源，改 `build_islands` 必須同步：
`docs/reference/GLOSSARY.md` 的 `island` 條、taxonomy JSON
（`src/cpbl/resources/pa_transition_taxonomy.v1.json`，含 `taxonomy_version` 是否需進版）、
`scripts/pa_transition_taxonomy.py` 的 `_island_starts`、
以及 `tests/test_pa_builder.py` 釘住兩者一致的 conformance 測試。

## 紅線（違反即退回）

1. **合併規則只能合併同一打席，不得合併兩個真打席。** 具體門檻：`2018/A/9` 9 局下
   （零投球故意四壞 → 打席間代打）與 `2018/A/16` 8 局下必須維持為**兩個** PA；
   全庫合併對數須逐對可列舉並附產生腳本。〔清單 #8〕
2. **不變式不得有例外清單。** 半局出局 PA > 3 一律 fail closed；已知的
   `2019/A/173` 是**來源損壞**，正確處置是隔離該場，不是加白名單繞過。
3. **完整性宣稱須由 artifact 自動產生。**「全部／全數／零例外」等字樣必須附窮舉證據，
   不得人工聲明。〔清單 #8〕
4. **fail-closed 不得因 builder 升級的發布路徑而削弱**：`builder_version` 相同時的
   fingerprint 變更仍須落 `reconciliation_required`，且不得刪除或覆寫舊 published build。
5. **`cpbl.pitch_tracking` 唯讀**（`pa_build` 模組既有紅線，且 `INGEST-GAME-TM-REFACTOR1`
   Gate 3 觀測窗進行中）：不得改逐球 parser、`run_refresh_recent.py` 正式路徑、
   `game_tm_shadow.py` 比較邏輯或 `pitch_tracking` schema／寫入契約——**違反＝重置該卡 14 天觀測窗**。
6. **本卡不做採計率評估。** 修完資料正確性即止；`ML-PITCHER-SCORELESS2` 的 PA 歸屬路徑
   是否重新評估由需求方另裁。

## 驗收條件

- [ ] 半局出局 PA > 3 的半局數：134 → 0（`2019/A/173` 以 fail-closed 隔離而非修正吞掉）。
- [ ] `(半局, pre_outs)` 有多筆出局 PA 的組數：1,175 → 0（同上例外處置）。
- [ ] 303 對合併逐對列出（腳本產生），並確認未觸及「零投球故意四壞＋打席間代打」邊界。
- [ ] `pre_state.outs` 改用推導值；2,157 筆變動逐筆可稽核，`GLOSSARY.md` 記錄語意變更。
- [ ] 不變式 fail-closed 逐場生效；本機重建後被隔離的場次清單與理由逐場列出。
- [ ] 四處 island SSoT 同步，conformance test 通過。
- [ ] builder 升級的發布路徑設計寫明，並說明為何不削弱 fail closed。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠（新端點須同步 EXPECTED 路由快照）。

## 驗證

- [ ] 查核者自行重跑診斷腳本，獨立確認 134／1,175 的基線與修正後數字。
- [ ] 查核者**自行構造反例**挑戰合併規則：找出會被誤併的真打席對，或證明找不到。
      （`ML-PITCHER-SCORELESS1/2` 共八輪的有效驗收手段皆是查核者構造的反例。）
- [ ] 查核者確認 `pre_state.outs` 的推導在「打席中途出局」（盜壘刺、牽制出局）
      情形下語意正確——這是 `out_cnt` 與推導值合法不一致的唯一來源，不得與缺陷二混淆。
- [ ] 查核者確認 fail-closed 未被發布路徑繞過：以 `builder_version` 不變但來源變動的
      情境實測，應仍落 `reconciliation_required`。
- [ ] 查核者確認 `pitch_tracking` 相關檔案零改動（`git diff --stat` 佐證）。

## 邊界

- **不做**：`splits_calc.py` 是否有同樣的重複計數（它用同一條 `(inning, vh, hitter)` 切分、
  只排除完全無投球的幽靈島）。**尚未驗證，也不清楚官方分項是否本來就這樣算**——
  另開卡查證，不併進來。
- **不做**：`ML-PITCHER-SCORELESS2` 的 PA 歸屬採計率評估（見紅線 6）。
- **時序**：本機全庫重建須排在每日 10:10 launchd 爬蟲之外（`game_livelog` 是 PA build 的
  來源，跨過更新會使當日場次落入 `reconciliation_required`），且 lease 須宣告
  `db:cpbl`、`container:cpbl-analytics-db-1` 互斥——`scrape-daily.sh` 的
  `/private/tmp/cpbl-analytics-refresh.lock` 擋不住 PA 重建。
- **時序**：全庫重建押到 `ML-PITCHER-SCORELESS2` 查核結案後（該卡 `db_scope: read`，
  無寫入衝突，但查核者若重跑讀 `game_plate_appearances` 的東西，數字會在他腳下移動）。
- **生產**：`refresh-cpbl-prod.sh` 的同步表清單**不含** PA 四表
  （`INGEST-PA-DAILY1` 仍在 Backlog），本機重建不會外洩到生產；
  生產重建是另一次決策，需求方裁定。
- 預估 M。

## Design Gate

`N/A`——純技術卡，無使用者可見介面變更。PA 表的消費面（`/recap-wp`、未來 `UX-GAME-PA1`）
只會看到既有欄位的值變正確，不新增或移除契約欄位。

## Log

- 2026-07-29 依 ruan6047 指示開卡。診斷於開卡前完成（全庫實測），
  `pre_state.outs` 修法、fail-closed 粒度、重建時序三項由需求方當場定案。
  來源為 `ML-PITCHER-SCORELESS2` iteration 1 handoff 主動交出的「刻意不出貨」段落
  ——執行者發現 134 個異常半局後選擇不出貨並另開 task chip，本卡即該 chip 的正式化。
