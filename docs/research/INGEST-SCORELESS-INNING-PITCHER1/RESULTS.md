# INGEST-SCORELESS-INNING-PITCHER1 交付：**不可用** — stats.cpbl 單場 API 沒有逐局責任投手

- 卡：[`ruan6047/cpbl-analytics#103`](https://github.com/ruan6047/cpbl-analytics/issues/103)（T2；`db_scope=read`）
- spec 基線：[`ML-PITCHER-SCORELESS2_RESULTS.md`](../ML-PITCHER-SCORELESS2_RESULTS.md) 的未查證路徑
  （卡面寫 §5／§7，實際落在 **§3 第 7 點與 §9 第 1 點**；見 §7 範圍外發現 F1）
- 查證對象：`GET https://stats.cpbl.com.tw/api/proxy/v1/games/{year}-{kind}-{sno}`
- as-of：**2026-08-07**
- 對帳與清冊由 [`probe_inning_pitcher.py`](probe_inning_pitcher.py) 產生；本報告所有數字皆出自它，
  無人工計數。重跑：`uv run python docs/research/INGEST-SCORELESS-INNING-PITCHER1/probe_inning_pitcher.py`

## 0. 一句話

**該端點的責任歸屬粒度只有兩層：逐球的「當下投手是誰」與逐場的「每位投手總計自責分」，
中間沒有任何一層。** 逐局責任投手不存在、逐局自責分不存在、繼承跑者歸屬不存在。
`ML-PITCHER-SCORELESS1/2` 的尾段鴿籠推論**無法靠這條路消除**，該報告點名的
「唯一有機會讓問題直接消失的方向」**到此關閉**。

## 1. 驗收條件一：請求禁令狀態（先確認，後行動）

`ML-PITCHER-SCORELESS2` §3 寫的「TrackMan 14 天觀測窗期間禁止對官網發任何請求，約 8/7 結束」
**已過期**。逐條查證：

1. **站台凍結的來源與解除**：該凍結是 Gate 3 shadow 觀測窗的需求方裁定，隨觀測窗
   **2026-08-03 第 9 天提前收窗而解除**（[`GAME_TM_SHADOW_OBSERVATION.md`](../GAME_TM_SHADOW_OBSERVATION.md) §5
   「條件 1–3 皆已達成，Gate 3 觀測階段可結案」）。
   「約 8/7」是對**原 14 天預設值**的推算，而該預設值同日被裁示改為 9 天，故此陳述失效。
2. **已有解除後的既成先例**：[`INGEST-PLAYER-BIO-GAP1_DIAGNOSIS.md`](../INGEST-PLAYER-BIO-GAP1_DIAGNOSIS.md)
   §8.0 明列「阻塞解除依據＝Gate 3 觀測窗提前收窗，站台凍結隨之解除」，並於 2026-08-03
   14:36 起對 `www.cpbl.com.tw` 實地抓取 14/14 人。凍結解除不是我的推論，是已執行的事實。
3. **新閘門不含站台凍結**：2026-08-05 起算的 Phase A 觀測閘門，四條件為「每 equipped 場館
   各一完成場 A/D、非場館失效端對端證據、真實自癒一例、無回滾觸發」（#53 第 3 則留言）。
   四條皆為**增量路徑自身的行為與覆蓋條件**，沒有一條是站台凍結或請求量條件。
   #53 的資源宣告凍結範圍是 `src/cpbl/ingest/run_refresh_recent.py`、
   `src/cpbl/ingest/cpbl_pitch_tracking.py`、`db:dev:table:pitch_tracking`——**檔案與表，不含請求行為**。
4. **量級佐證**：G4 自己的 `request_volume.json` 記載 live worker 對**同一支端點**的容量模型是
   `same_endpoint_requests_per_game_day = 5700`，並明寫增量路徑的絕對請求量「在該端點的整體
   負載中屬雜訊等級」。少量探查不可能影響觀測。
5. **時間無交疊**：今日排程鏈已於 13:15:40 +0800 完成（`logs/last-status.json`：
   `state=succeeded`、`sync_ok=true`），下一次在明日 10:10。

**判定：可以發請求。** 但本卡實際只發 **1 次**——因為主要證據來自已保存的官方回應全文。

### 請求逐筆紀錄（總計 1 次，0 重試，0 失敗）

| # | 時間（+0800） | URL | 結果 |
|---|---|---|---|
| 1 | 16:00:57.382 → 16:00:57.679（2026-08-07） | `https://stats.cpbl.com.tw/api/proxy/v1/games/2026-A-246` | HTTP 200，498,072 bytes |

機器可讀版見 [`request_log.json`](request_log.json)（含 `raw_sha256`）。
[`confirm_live_schema.py`](confirm_live_schema.py) 對已落檔的 payload **不重打**，
故重跑本卡 artifact 不會產生新請求。

## 2. 證據語料：為什麼 1 次請求就夠

主要證據是 `INGEST-GAME-TM-REFACTOR1-G4` Phase A **已保存的 10 份官方回應全文**
（`docs/research/INGEST-GAME-TM-REFACTOR1-G4/payloads/*.json.gz`）。那些檔案由
`dryrun_game_tm_fullseason.py` 以 `f.write(raw)` **逐位元原樣保存**，端點與本卡待查者
是同一支，sha256 錨定於該卡 `dryrun_fetch_log.jsonl` 與 `manifest.json`。
本卡重算 11 份 payload 的 sha256，**11/11 與各自的錨點相符**（`field_inventory.json.sources`）。

那 10 份是**偏差樣本**：G4 只為「有 TrackMan 差異」的場次保存 payload。該選擇條件
（逐球物理欄位不一致）與「回應是否帶逐局責任投手」正交，但為徹底堵掉抽樣質疑，
本卡對一場**中性完成場** `2026-A-246`（2026-08-06，未落在 G4 樣本內）補一次確認。

**結果：兩份語料 schema 完全一致**——中性場沒有任何 G4 樣本沒有的鍵；
G4 樣本多出的只有 `Closer.Acnt`／`Closer.Name` 兩個**情境性欄位**（A-246 是 2:8，
無救援情境故無 Closer），不構成 schema 差異。

語料合計：**11 場**（kind A 6 場、kind D 5 場）、**262 個欄位路徑**、
**3,496 筆 LiveLog**、**117 筆投手列**。

## 3. 事實：粒度到底停在哪裡

對 262 個欄位路徑做**樣態窮舉**（`responsib|charg|inherit|earned|selfrun|duty|owner`，
不分大小寫），全語料命中的只有兩個：

```
$.Data.Game.Home.Pitchers[].EarnedRunCnt
$.Data.Game.Visiting.Pitchers[].EarnedRunCnt
```

兩者都是**逐場逐投手總計**。逐局層完全空白：

- **`InningScore[]` 只有 `{Seq, Score}`** ——逐局**球隊**得分，無投手歸屬、無自責分拆分。
  程式化檢查 `InningScore_carries_pitcher_attribution = false`（全 11 場）。
- **`LiveLog[]` 無任何自責分標記**：`LiveLog_carries_earned_run_marker = false`（全 11 場）。
  它有 `IsScoreCnt`（該事件是否得分）但**沒有自責／非自責之分**。
- **`WinningPitcher`／`LoserPitcher`／`Closer`** 是逐場勝敗救的裁決，不是逐局責任。

自責分確實存在於官方資料中、且非自責分確實會發生：11 場裡有 **10 個隊伍-場次**
出現 `RunCnt ≠ EarnedRunCnt`（如 `2026-D-100` 客隊 R=6 / ER=4）。**官方做了自責分判定，
但只在逐場逐投手這一層公開。**

### 3.1 退一步只求「失分」也不行：繼承跑者把路堵死

就算放棄自責分、只想從 LiveLog 逐球的 `PitcherAcnt` 重建逐局失分歸屬——**連失分都重現不了**。

把每個得分事件的比分推進量記給「該事件當下的 `PitcherAcnt`」，再對照官方
`Pitchers[].RunCnt`：**117 筆投手列中 18 筆不一致（15.4%）**（[`run_attribution.json`](run_attribution.json)）。

例：`2026-A-155` 投手 `0000006127` 官方 `RunCnt=0`，但他在場上時比分推進了 2 分；
同場 `0000006848` 官方 `RunCnt=5`，在場上時只推進 3 分。這正是規則 9.16 的繼承跑者歸屬
——得分記給**讓跑者上壘的那位投手**，不是得分當下站在投手丘上的人。

失分尚且如此，自責分只會更糟：自責分還要額外做「假想無失誤的重建」，那是記錄員判斷，
逐球資料裡沒有、也推不出來。

### 3.2 順帶：SCORELESS2 的零投球反例在實資料上看得到

`ML-PITCHER-SCORELESS2` §1 用規則 5.10(g)【加註】與 9.16 論證「零投球仍可拿到出局／自責分」。
本語料觀測到 **221 筆**「同投手 `PitchCnt` 未推進」的 LiveLog 事件（牽制、教練暫停、換投、
突破僵局上壘），實例見 `granularity.json.zero_pitch_event_examples`。這**不是**該反例本身
（未觀測到零投球自責分的實例），但證實「零投球事件會出現在逐球流裡」這個前提為真，
SCORELESS2 的撤回論證在資料面沒有被打穿。

## 4. 驗收條件二：該來源本身可對帳嗎？

可對帳，而且**完美對帳**——但那恰好是它沒有價值的原因。

把 11 場的 `Pitchers[]` 與 `cpbl.pitching_gamelog` 逐格比對（後者來源是
**www.cpbl.com.tw `/box/getlive`**，是**獨立的第二個站台**，不是同源自比）：

- 比對 **117 筆投手列 × 15 個欄位 = 1,755 格**
- **cell mismatch = 0，PK 集合差異 = 0**

明細見 [`reconcile_pitchers.json`](reconcile_pitchers.json)。值得一提：連 G4 裁定一那場
「兩支官方端點互相矛盾」的 `2026-D-180` 也**完美對帳**——那場的矛盾侷限在逐球 TrackMan
物理欄位，**投手 box 兩站台一致**。

**結論**：stats.cpbl 單場 API 的投手區塊與我們已入庫的 `pitching_gamelog` 是**同一組數字**。
它不是新資訊來源，是既有資訊的第二份副本。

## 5. 判定：**不可用**

| 問 | 答 |
|---|---|
| 提供逐局責任投手？ | **否**。責任投手只有逐球（誰在投）與逐場（勝敗救）兩層 |
| 提供逐局自責分？ | **否**。自責分只有逐場逐投手總計 |
| 缺的是欄位還是粒度？ | **粒度**。欄位存在（`EarnedRunCnt`）但只在逐場層；不是欄位漏抓 |
| 該來源可對帳嗎？ | 可，1,755 格對 www 來源 0 差異——但因此**零增量資訊** |
| 需要什麼 ingest 改動？ | **不需要**。沒有任何未入庫的欄位可撈 |

需要說清楚的是**這是「粒度不對」而非「欄位不存在」**：官方**做了**逐投手自責分判定
（`EarnedRunCnt` 就是產物），只是**不公開比逐場更細的拆分**。所以這不是換個 parser
就能解的問題，是官方公開介面的邊界。

### 對 SCORELESS 鴿籠推論的影響：零

`ML-PITCHER-SCORELESS1/2` 的下界需要的是「**這一場裡，該投手的自責分發生在第幾個出局之後**」。
本端點能提供的上限是「他這場總共幾分自責分、投了幾局」——那正是
`pitching_gamelog.earned_runs` / `inning_pitched_cnt` **已經有的東西**，也正是鴿籠推論
**現在的輸入**。輸入沒變，下界就不會變緊。

### 什麼樣的資料才能讓問題消失（給未來重走這條路的人）

需要下列任一，且皆**不在官方公開介面內**：

1. **逐局（或逐打席）的自責分歸屬**——官方記錄員的 inning reconstruction 結果。
2. **繼承跑者的責任投手標記**——每個上壘跑者對應「讓他上壘的投手」。
   LiveLog 的 `FirstBase`／`SecondBase`／`ThirdBase` 只有跑者 acnt，**沒有責任投手欄**。
3. **失誤與其影響的逐事件標記**足以重建「假想無失誤」局面。`ActionName` 有
   「接球失誤」等文字，但要把它推成 9.16 的重建結果屬記錄員判斷，不是解析問題。

在這三者出現之前，SCORELESS2 §9 的第二建議（**改變產品宣稱**，以「連續無自責分**出賽**」
為主詞、`strict_outs` 為值、零推論）仍是唯一誠實的出路。**本卡的結論是把它從
「備案」升格為「現況下唯一可行方案」。**

## 6. 我認為最可能被反例打穿的地方（主動揭露）

1. **樣本仍是 11 場，不是全季窮舉。** schema 缺席是以 11 場（A 6／D 5、含一場中性場）
   的窮舉欄位路徑為據，不是對全季 400+ 場逐場驗證。若官方對特定場次（如季後賽 kind C／E）
   回傳不同結構，本結論不涵蓋。我判斷風險低（同一支端點、同一組 handler），但那是判斷不是事實。
2. **未查證「換參數是否回更多欄位」。** 我沒有嘗試 `?includeXXX=` 之類的參數——`CPBL_SITE_MAP.md`
   §4b 未記載該端點接受任何 query 參數，臆測參數名等於腦補。若需求方要，這是一個明確的
   後續探查項（見 §8）。
3. **`/api/proxy/v1/leaderboards/summary` 與 `/home` 仍是 ⬜ 未探查**（`CPBL_SITE_MAP.md` §4b）。
   我判斷兩者皆為聯盟／首頁聚合，不可能帶單場逐局投手責任，故未查。這是推論，不是否證。
4. **「零投球自責分」仍未在實資料上觀測到實例。** §3.2 只證實零投球事件存在，
   沒有證實零投球自責分發生過。SCORELESS2 的撤回本來就建立在規則推導而非頻率上，
   本卡沒有改變那個論證的地位。

## 7. 範圍外發現（交 PM，本卡不自行開卡）

- **F1｜卡面 spec 基線指錯章節。** #103 與派工包都寫「`ML-PITCHER-SCORELESS2_RESULTS.md`
  §5／§7 的未查證路徑」，但該檔 §5 是「採計率」、§7 是「方法論教訓」。未查證路徑實際在
  **§3 第 7 點**與**§9 第 1 點**。不影響本卡執行（內容唯一、不會認錯），但基線引用應更正。
- **F2｜`ML-PITCHER-SCORELESS2_RESULTS.md` 的禁令陳述已過期且會誤導後續。**
  §3／§9 的「約 8/7 結束」建立在已被裁示推翻的 14 天預設值上。該檔是**已結案卡的交付物**，
  依 `INGEST-PLAYER-BIO-GAP1_DIAGNOSIS.md` §6 的先例（凍結交付物的價值來自不會再變），
  我**未動它**。建議由 PM 裁定：(A) 補一行指回本報告，或 (B) 只靠本報告單向指回。我傾向 (B)。
- **F3｜`CPBL_SITE_MAP.md` §4b 可補一條事實。** 該端點條目詳述了 `LiveLog[]` 與 TrackMan，
  但未記載「`Pitchers[]` 逐場 box 與 www `/box/getlive` 的 `pitching_gamelog` 1,755 格 0 差異」
  與「無任何逐局投手責任欄位」。後者正是本卡查證的結論，寫進 SSoT 可讓下一個人不用重查。
  本卡寫入授權只有 `docs/research/INGEST-SCORELESS-INNING-PITCHER1/`，故未動。
- **F4｜`2026-D-180` 的矛盾範圍比 #53 裁定一描述的窄。** 該場被列為「兩支官方端點互相矛盾」
  並進入凍結例外清單，但本卡量到其**投手 box 與 www 來源 0 差異**——矛盾侷限於逐球 TrackMan
  物理欄位。這不影響該凍結裁定（凍結保護的正是逐球表），但若日後有人以 D-180 為由懷疑
  該場其他資料，這是反向證據。

## 8. 待需求方裁決

1. **本條路線是否就此關閉？** 我的建議是關閉，並依 §5 把「改變產品宣稱」
   （連續無自責分**出賽**、`strict_outs` 為值）從備案升為正案，另開實作卡。
2. **要不要再花 1–2 次請求試 query 參數？**（§6.2）我的建議是**不要**——參數名無文件依據，
   等於用請求做窮舉猜測，違反「最小可回答問題的範圍」。若需求方另有情報（例如觀察到官網
   前端打過帶參數的同端點）再開。
3. **F2 的凍結交付物處理**：(A) 補指標連結／(B) 維持單向指回。
4. **F3 是否併入 `CPBL_SITE_MAP.md`**：若要，需另開小卡（本卡無該檔寫入授權）。
