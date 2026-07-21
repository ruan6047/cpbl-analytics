# MATCHUP-DATA2 對戰對手歷史隊別歸屬修正〔T4；🔴資料正確性〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/MATCHUP-DATA2`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：—　spec 基線：matchups-redesign.md（§API／資料工作「確認對手隊伍名稱的歷史 mapping」）
- DB：`db_scope: read`（先驗證為 API 彙總邏輯問題；若查出來源 `pitcher_team_no` 本身錯置再升級為資料修復）
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：修正跨隊／改名球員在對戰清單被歸到錯誤（甚至主角自家）franchise 的顯示。

## 問題（已由程式與資料查證，非臆測）

- 症狀：林立（`0000002286`，AJL 樂天 franchise，2017– 生涯全在此隊）**打擊對戰投手**清單把**自家隊「樂天」**列為對手——`opp_franchise=AJL011` 有 10 位（陳鴻文／索沙／紐維拉／包林傑／陳柏豪／艾璞樂／肯特／邦威／呂詠臻／楊彬…）。主角不可能對戰自家隊，屬歸屬錯誤。
- 機制：對手隊號 `opp_team_code = cpbl.batter_pitcher_matchups.{opp}_team_no`（爬蟲逐年對戰列各自帶）；`aggregate_matchup_rows`（`src/cpbl/api/matchups.py:89`）以 `opp_id` 分組後，**取最新年度那列的 `opp_team_code`/`opp_team` 當代表**（`latest = ordered[-1]`）。跨隊或改名的對手，其「最新對戰年」的隊號會蓋掉歷史歸屬 → 顯示成對手後來所屬隊，可能等於主角自家 franchise 或誤導的歷年隊名。
- spec 早已標記此紅線：matchups-redesign.md「確認對手隊伍名稱的歷史 mapping；不要用當季隊名直接推論歷年隊名」。

## 驗收條件

- [ ] 對戰清單彙總列的顯示隊別能正確反映「該對戰實際發生時的對手隊」，不得以最新年度隊號覆蓋歷史；跨隊球員不得被歸到單一誤導隊。
- [ ] 主角自身 franchise 不得出現在其對戰對手的隊別歸屬中（同隊不對戰）。
- [ ] 連帶驗證 UX-MATCHUP2 的「對手球隊下拉只列交手過的隊」：下拉來源即這些 franchise 歸屬，資料修正後下拉不得再出現主角自家隊。
- [ ] Discovery 須先判定根因層級：純 API 彙總代表列選取問題（read）／或來源 `pitcher_team_no` 錯置（需資料修復，升級 db_scope）。

## 驗證與依賴

- 驗證：跨隊對手 fixture（如索沙等跨隊洋投）、改名隊（Lamigo↔樂天同 franchise、La New↔Lamigo）、主角自家隊排除；route snapshot／API 測試同步；跨模型家族或人工查核（紅線）。
- 依賴：MATCHUP-DATA1（已結案）；與 UX-MATCHUP2 的對手下拉過濾為下游消費者，資料修正後其行為自動改善。
- 預估範圍：S–M。

## Log

- 2026-07-22 註冊（REGISTER-001）：UX-MATCHUP2 審核走查時發現，需求方 ruan6047 裁決另開資料修復卡，不併入 UX-MATCHUP2（一般 UI 查核不得替代資料正確性紅線查核）。維持 Backlog 待排序。
