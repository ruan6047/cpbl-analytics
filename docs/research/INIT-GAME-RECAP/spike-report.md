# UX-GAME-RECAP1 Phase A — spike 驗證報告

> 卡片：[Issue #80](https://github.com/ruan6047/cpbl-analytics/issues/80)（T3，Initiative `INIT-GAME-RECAP`，`db_scope=read`）
> spec 基線：[`docs/research/INIT-GAME-RECAP_DISCOVERY-BRIEF.md`](../INIT-GAME-RECAP_DISCOVERY-BRIEF.md) @ main `8f250d9`
> 執行：Claude Opus 5@Claude Code，2026-08-06（Asia/Taipei）
> 授權範圍：Phase A（設計稿＋spike）。**未寫任何實作碼**；poc 腳本留在 scratch，本報告內嵌可重現片段。

## 0. 結論摘要

| # | 假設 | 判定 | 一句話 |
|---|---|---|---|
| 1 | 逐打席 ΔRE24 即時算正確 | **PASS（附條件）** | canonical PA × RE 矩陣算得出逐打席 ΔRE24；與 `batter_re24` 的差異全部落入 4 類**已知且 canonical 較正確**的語意差，零未歸類。驗收語應改為「差異可窮舉歸因」而非「數值吻合」。 |
| 2 | 一句事實句模板可讀 | **PASS（待人工審）** | 4 場真實樣例已生成，模板分支全機器可判定；發現兩個必須進設計的陷阱（再見打席 ΔRE24 為負、球員名不可靠 `players` 表）。 |
| 3 | 首頁雙態沿用既有端點即足 | **PARTIAL** | 賽程／比分／賽前機率齊備（`/api/v1/daily/summary`）；**live 態逐場快照**與**昨日戰果的結論欄位**兩處缺口，需 #80 的結論 API 補。 |
| 4 | 全即時算成本低 | **PASS** | 單場端到端（3 次查詢＋計算）本機 4.5–5.7 ms（p95 ≤ 7.1 ms）；純計算 mean 0.58 ms／max 4.75 ms。 |
| 5 | final snapshot 的 livelog 完整 | **PASS（附兩個缺口）** | 5 場 final 皆含末打席、與 DB 逐列比對零缺列；但 **勝敗投只有 2/5**、**無致勝方式欄**。 |
| 6 | canonical PA 切界核心可 library 化跑 snapshot | **PASS** | `pa_build.plate_appearances` 是純函式，直接吃映射後的 snapshot 事件；5 場 PA 數全等、邊界差異僅末打席 `post_state.outs`（不影響 ΔRE24），**逐打者 ΔRE24 與權威源零差異**。 |

**對 brief 的三處實查修正**（詳見 §7）：
1. `game_detail.winning_type` **不是「致勝方式」**，是勝方旗標（主/客），資訊量為零 → recap ①結論行的「致勝方式」欄無資料源。
2. `batter_re24`（`models/sabr.build_re24`）把**突破僵局上壘**記成該跑者的一個打席並給 +0.6356 RE24（2026/A 全季 49 筆）——canonical PA 路徑不會犯，但季彙總表目前帶著這個偏差。
3. `cpbl.players` 缺列（實例 `0000007822` 威克）會讓 MVP／關鍵打席顯示成球員 ID；`game_livelog.hitter_name` 與 snapshot `HitterName` 都有名字，應改為顯示層的姓名來源。

---

## 1. 環境與可重現指令

```bash
# worktree（本卡）
cd ~/Dev/cpbl-analytics
git worktree add .claude/worktrees/ux-game-recap1-execution -b ai/opus-5/UX-GAME-RECAP1 8f250d9
cd .claude/worktrees/ux-game-recap1-execution && uv sync

# 資料面（全部唯讀）
docker compose up -d db                      # 本機 PostgreSQL :5433
docker exec -e PGPASSWORD=cpbl cpbl-analytics-db-1 psql -U cpbl -d cpbl -c "<query>"
```

spike 腳本置於 scratch（未 commit，全文見 §8 附錄）：

```bash
SP=<scratchpad>/spike
uv run python $SP/spike1_re24.py 241 243 244        # 假設 1：季彙總對帳 + 逐場 S vs C
uv run python $SP/spike1b_season.py                  # 假設 1：全季逐打者對帳
uv run python $SP/spike1c_pa_level.py                # 假設 1：全季**逐打席**窮舉歸類（定案證據）
uv run python $SP/spike2_sentence.py 241 243 244 245 # 假設 2：事實句樣例
uv run python $SP/spike56_snapshot.py $SP/prodsnap 241 242 243 244 245  # 假設 5/6
```

snapshot 取得（**只讀，未跑任何爬蟲**）：

```bash
# (a) 本機 live worker 的 Redis（另一 worktree 的容器，2026-07-30 build）
docker exec live-game-backend1-execution-redis-1 redis-cli --scan --pattern 'cpbl:live*'
docker exec live-game-backend1-execution-redis-1 redis-cli --raw GET cpbl:live:2026:A:243 > snap_243.json

# (b) 生產（唯讀 HTTP GET，最終採用的證據來源）
curl -s "https://cpbl.ruan-ruan.com/api/v1/games/243/live?season=2026&kind_code=A" \
  | python3 -c 'import sys,json;json.dump(json.load(sys.stdin)["live_snapshot"],open("snap_243.json","w"),ensure_ascii=False)'
```

樣本場次：2026/A 的 **241、242、243、244、245**（2026-08-04～08-05，皆 final；243 為 10 局再見、突破僵局場）。

---

## 2. 假設 1 — 逐打席 ΔRE24 即時算

### 2.1 兩條路徑與對帳設計

| 路徑 | 打席邊界 | 出局數來源 | 用途 |
|---|---|---|---|
| **S**（naive） | `models/sabr.build_re24`：半局內「連續同 hitter」 | livelog `out_cnt` ＋ `content` 的「N人出局」補正 | 產出季彙總 `cpbl.batter_re24` |
| **C**（canonical） | `cpbl.game_plate_appearances`（published build，`pa-build-1.3.0`）＋ `game_pa_events` 成員 | `pa_build.derive_half_inning_outs`（純由 `content` 推導） | 本卡打算採用的即時算 |

兩路徑用**同一個 RE24 慣例**（Retrosheet；跑者桶與打者桶分離）：

```
ΔRE24(打席) = RE(下一個真實打席的打席前狀態) + 終結事件得分 − RE(終結事件之前的狀態)
半局最後一個打席的 RE(after) = 0
```

> ⚠️ 實作陷阱（第一版寫錯過）：錨點必須是「**終結事件之前**的出局數」。若誤用 canonical `post_state.outs`（＝終結事件**之後**），全場每個打席都會系統性偏移一個出局的 RE 差（實測固定 +0.2475＝RE(空壘,0出)−RE(空壘,1出)）。canonical PA 表只存 pre(before)／post(after)，**terminal 事件的 before-outs 必須另外由 `derive_half_inning_outs` 取回**——這是「打席事實流」服務必須同時吃 PA 表與 livelog 的原因。

### 2.2 先證明 S 路徑是忠實複製

`batter_re24` 是離線批次產物、會落後於 livelog。以「前綴 N 場累計」尋找與 stored 逐值全等的切點：

| 檢查 | 值 |
|---|---|
| 2026/A 有 livelog 的場次 | 239 |
| 重算得到的打者數 / `batter_re24` 現存打者數 | 166 / 158 |
| **累計逐值全等的前綴場次** | **`game_sno ≤ 189`**（158 名打者的 `pa` 與 `re24` 全數逐值相等） |
| 全季重跑耗時 | 0.34 s |

→ S 路徑複製無誤；`batter_re24` 現值僅停在 189 場（該表非每日重建）。**故「同場加總對照 `batter_re24`」在近期場次上本來就對不起來，原因是新鮮度不是演算法。**

### 2.3 全季逐打席窮舉歸類（定案證據）

以「終結事件 `main_event_no`」對齊兩路徑的每一個打席，2026/A × 239 場：

| 類別 | 筆數 | 誰比較正確 | 說明 |
|---|---|---|---|
| `equal` | **17,536** | — | 打席身分、歸屬打者、ΔRE24 完全相同 |
| `outs_anchor_differs` | 306 | **canonical** | 錨點出局數來源不同：`out_cnt` 落後 vs `content` 推導。PA1-FIX1 已實證 `out_cnt` 有 0.653% 事件不一致 |
| `naive_fragment_merged_into_canonical_pa` | 68 | **canonical** | naive 把一個打席（打席中途代打接替、截斷碎片）切成多段 |
| `canonical_pa_absent_in_naive` | 60 | — | canonical 的 `truncated` PA（`end_event_no` 為 NULL），兩路徑都不記打者 ΔRE24 |
| `canonical_state_non_pa` | **49** | **canonical** | **突破僵局上壘**：naive 記成該跑者一個打席、給 +0.6356；canonical 分類為 `non_pa` 排除 |
| `naive_pa_absent_in_canonical` | 9 | **canonical** | 同上碎片類 |
| `charge_rule_915b_differs` | 1 | **canonical** | 代打接替後三振，記錄規則 9.15(b) 歸最初擊球員；ΔRE24 數值相同、歸屬不同 |
| **未歸類** | **0** | — | 歸類為 fail-closed：任何未歸類即結論不成立 |

77 筆「naive 有、canonical 對不到終結事件」中，**只有 8 筆帶非空 ΔRE24**（其餘皆是兩路徑都排除的截斷碎片）。

場級（逐打者加總）視角：239 場中 **113 場完全相同**；其餘全部可由上表歸因，其中 `outs_anchor_differs` 因望遠鏡求和多半在場級抵銷（77 場場級總和守恆）。

### 2.4 逐場抽驗（brief 要求的 2–3 場）

| 場次 | canonical PA | ready | livelog 事件 | 打者級 ΔRE24 差異 | 說明 |
|---|---|---|---|---|---|
| 2026/A/241 | 78 | 77 | 325 | **0**（24 名打者逐值相同，場級 −0.637） | 乾淨場 |
| 2026/A/244 | 79 | 78 | 288 | **0**（28 名逐值相同，場級 +3.1797） | 乾淨場 |
| 2026/A/243 | 84 | 82（2 `non_pa`） | 318 | 2 名打者各差 −0.6356 | 10 局突破僵局；canonical 正確排除跑者佈局列 |

243 的差異可逐列驗證：`1010002000` 與 `1020003000` 兩列 `ActionName=突破僵局上壘`，naive 記給被放上二壘的跑者一個打席，ΔRE24 = RE(_2_,0) − RE(___,0) = 1.1625 − 0.5269 = **+0.6356**。

### 2.5 判定

**PASS，但驗收語必須改寫。** 「同場同打者加總對照 `batter_re24` 吻合」不能當通過條件，因為：
(a) `batter_re24` 只更新到 189 場；(b) 兩者打席語意本就不同，且**canonical 在每一類差異上都比較正確**。
建議把實作卡的迴歸測試釘成：**逐打席窮舉歸類，未歸類筆數必須為 0**（本報告 §2.3 即該測試的基準值）。

---

## 3. 假設 4 — 即時算成本

本機（PostgreSQL :5433，Python 3.12）：

| 量測 | 值 |
|---|---|
| 單場端到端（載 livelog + 載 published PA + 載成員 + 計算） | 241 / 243 / 244 = **5.72 / 4.52 / 4.46 ms**（20 次平均），p95 ≤ 7.12 ms |
| 純計算（不含查詢），239 場 | mean **0.58 ms**、p95 1.12 ms、max 4.75 ms |
| RE 矩陣載入（24 列，可 process 級 cache） | 0.30 ms |
| snapshot 路徑：`plate_appearances()` 純函式 | 2.2–2.9 ms／場 |
| snapshot 路徑：ΔRE24 計算 | 0.18–0.24 ms／場 |

→ **PASS**。單場 recap 完全可在 request 內算完，無需物化表、無需進每日鏈（G4 凍結無涉）。

---

## 4. 假設 5 — final snapshot 的 livelog 完整性

### 4.1 樣本來源說明（誠實揭露）

- 本機 Redis（`live-game-backend1-execution-redis-1`）確有 9 把 key、5 場 final，TTL 剩 30,669–172,422 s（設定 `live_game_snapshot_ttl_seconds=172800`＝48 h），**留存窗確認足以覆蓋「當晚＋隔日」**。
- 但該容器映像建於 **2026-07-30**，早於 `672e0c7`（08-01 加 `decisions`）與 `0a88ec9`（加 `IsBall`／`IsStrike`）→ 本機 snapshot 缺這些欄位。
- 因此**最終證據改用生產**（`GET /api/v1/games/{sno}/live` 的 `live_snapshot`，唯讀）。生產 snapshot 已含 `decisions`／`IsBall`／`IsStrike`／`venue`／`umpires`／`skip_trackman`，證明生產 worker ≥ `0a88ec9`。

### 4.2 逐列對照（生產 snapshot vs DB `game_livelog`）

| 場次 | snapshot 列數 | DB 列數 | 只在 snapshot | 只在 DB | 末事件一致 | 欄位差異 |
|---|---|---|---|---|---|---|
| 241 | 326（含 1 筆重複 `MainEventNo`） | 325 | 0 | 0 | ✅ | `is_special_event` 19、`content` 1 |
| 242 | 255 | 255 | 0 | 1（`0720016010`） | ✅ | `is_special_event` 18、`content` 2、`pitch_cnt` 5 |
| 243 | 319 | 318 | 0 | 0 | ✅ | `is_special_event` 30、`content` 1 |
| 244 | 289 | 288 | 0 | 0 | ✅ | `is_special_event` 24、`content` 1 |
| 245 | 280 | 279 | 0 | 0 | ✅ | `is_special_event` 14、`content` 2 |

差異解讀（兩者是**不同官方端點**：DB 走 www 主站 `getlive`，snapshot 走 `stats.cpbl`）：

- **末列 `content`**：DB 的最後一列被覆寫為「比賽結束」，snapshot 保留真實敘述（例 244 `擊出中外野高飛球， 打者-中外野手 飛球接殺出局。 3人出局。`）。**snapshot 在這一列比 DB 更完整。**
- **`is_special_event`**：snapshot 為 true 的列 DB 記 false（14–30 列／場）。不參與 PA 邊界與 ΔRE24。
- **242 的 `pitch_cnt` 差 2（5 列）與多出的 `0720016010`**：DB 多一列子事件並使後續球數位移；該場仍以完全相同的 PA 邊界收斂。
- **`content` 個別差異**：242 的 `0420015000` DB 多「(中信兄弟重播輔助判決-原判)」；245 的 `0420004000` 判定敘述不同（「好球沒揮棒。」vs「擊出界外球。」）。**兩來源的逐球敘述不保證逐字一致**，recap 若要引用敘述文字須註明來源。
- snapshot 的 `livelog` **可能含重複 `MainEventNo`**（實測 241 末列重複一次）→ 消費端必須以 `main_event_no` 去重。
- snapshot **沒有** DB 的 `is_score`／`catcher_acnt`／`defend_station_code`；三者皆不參與 PA 邊界與 ΔRE24。
- snapshot 的 `IsChangePlayer`／`IsSpecialEvent`（以及舊版的 `IsBall`／`IsStrike`）是官方原始**字串 `"0"`／`"1"`**，DB ingest 已轉 bool。**未轉型會讓 `pa_build._usable()` 把每一列都當換人列，PA 數直接歸零**（本 spike 第一版踩過）。

### 4.3 `decisions` 與致勝方式（**缺口**）

生產 snapshot 的 `decisions` 區塊在 5 場 final 的填充率：

| 欄位 | snapshot（當晚） | DB `cpbl.games`（隔日權威） |
|---|---|---|
| `mvp` | **5 / 5** | 5 / 5 |
| `winning_pitcher` | **2 / 5**（僅 243、245） | 5 / 5 |
| `losing_pitcher` | **2 / 5** | 5 / 5 |
| `closer` | 1 / 1（僅 245 有救援） | 1 / 1 |
| 致勝方式 | **無此欄**（全 snapshot 文字搜尋 `winning_type` 不命中） | 見下 |

`game_detail.winning_type` 實查（全庫 4,316 場）：

| `winning_type` | 場次 | 主隊勝 | 客隊勝 | 平均分差 |
|---|---|---|---|---|
| `2` | 2,184 | 2,184 | 0 | 3.61 |
| `1` | 1,979 | 0 | 1,979 | 4.07 |
| NULL | 153 | 3 | 2 | 0.05 |

→ **`winning_type` 是「勝方是主隊還客隊」，不是致勝方式**，與比分 100% 共變、資訊量為零。brief 與舊 design brief 把它當「官方致勝方式欄」是誤解。

### 4.4 判定

**PASS**（livelog 完整性成立、TTL 窗足），但帶兩個必須進設計的缺口：
1. **勝敗投在當晚只有 2/5 可得** → 暫定期不得顯示錯值，該列走「官方確認中」。
2. **致勝方式無資料源** → ①結論行改以可查證事實承載（再見打席／最大單局／|ΔRE24| 首位打席）。

---

## 5. 假設 6 — canonical PA 切界核心 library 化

### 5.1 可行性（讀碼）

`src/cpbl/ingest/pa_build.py` 的模組 docstring 明寫「**純核心 + 薄 DB 層**」：`build_islands`／`continues_same_plate_appearance`／`classify_island`／`derive_half_inning_outs`／`charged_hitter`／`plate_appearances` 全部只吃 `list[dict]`，DB 只出現在 `_fetch_events`／`_write_pas`。**無須改碼即可 library 化**，只要把 snapshot 列映射成 `_EVENT_COLS` 同名 dict。

欄位映射（snapshot → `pa_build` Event）：

| snapshot | Event | snapshot | Event |
|---|---|---|---|
| `MainEventNo` | `main_event_no` | `HitterAcnt` | `hitter_acnt` |
| `InningSeq` | `inning_seq` | `PitcherAcnt` | `pitcher_acnt` |
| `VisitingHomeType` | `visiting_home_type` | `FirstBase`/`SecondBase`/`ThirdBase` | `first_base`/… |
| `BattingOrder` | `batting_order` | `IsStrike`/`IsBall` | `is_strike`/`is_ball` |
| `OutCnt`/`BallCnt`/`StrikeCnt`/`PitchCnt` | 同名 snake | `IsChangePlayer`/`IsSpecialEvent` | 同名 snake |
| `Content`/`ActionName`/`BattingActionName` | 同名 snake | `VisitingScore`/`HomeScore` | `visiting_score`/`home_score` |
| （無） | `is_score`、`catcher_acnt`、`defend_station_code` | — | 皆不參與切界／ΔRE24 |

必要正規化：`"0"/"1"` → bool；空字串壘位 → `None`；`main_event_no` 去重。

### 5.2 對照結果（生產 snapshot vs DB published PA）

| 場次 | snapshot 建出 PA | DB published PA | 邊界差異 | 逐打者 ΔRE24 差異 | 關鍵打席 Top5 一致 |
|---|---|---|---|---|---|
| 241 | 78 | 78 | 1 | **0** | ✅ |
| 242 | 69 | 69 | 1 | **0** | ✅ |
| 243 | 84 | 84 | **0** | **0** | ✅ |
| 244 | 79 | 79 | 1 | **0** | ✅ |
| 245 | 65 | 65 | 1 | **0** | ✅ |

比對維度：`state`、`hitter_acnt`、`end_hitter_acnt`、`result_action`、`end_event_no`、`pre_state`、`post_state` 逐欄全等。

**唯一差異**永遠是全場最後一個打席的 `post_state.outs`（snapshot 3 vs DB 2），成因即 §4.2 的「DB 末列 `content` 被覆寫成『比賽結束』，失去『3人出局。』敘述」。**snapshot 才是對的**，且該值被 `min(outs, 2)` 吃掉，對 ΔRE24 零影響。

### 5.3 一個必須守住的前置條件

`continues_same_plate_appearance` 的 `pinch_hit_slot` 佐證會呼叫 `_is_real_pitch()`，而後者需要 `is_strike`／`is_ball`。2026/A 全季 8 次打席合併中 **7 次走 `pinch_hit_slot`**。若 snapshot 缺這兩欄，`_is_real_pitch` 恆假 → 該分支變成**無條件合併**（跳過 `non_decreasing` 守門），會過度合併。

- 生產 snapshot 已含這兩欄（實測），故現況安全。
- 本機舊版 snapshot 缺這兩欄；本 spike 以「注入 DB 值」作對照變體，5 場結果與 as-is 完全相同（樣本未觸發該分支）——**「未觸發」不等於「不需要」**。
- → 實作時應在 snapshot 路徑加一個明確前置檢查：`IsBall`/`IsStrike` 任一缺席即不走暫定 recap（fail closed）。

### 5.4 判定

**PASS。** 當晚 snapshot 與隔日權威源在打席邊界與 ΔRE24 上**零分歧**（5/5 場），brief 假設 6 的「能＝當晚與隔日零分歧」成立，**不需要「暫定標記」來遮蓋數值差**；暫定標記的用途縮小為「來源揭露 + 少數官方欄位（勝敗投）尚未到位」。

---

## 6. 假設 2 與假設 3

### 6.1 假設 2 — 一句事實句模板

模板分支條件全部機器可判定，槽位全部是可查證事實（比分／局半／打者／官方 `action_name`／ΔRE24／該半局得分／最大單局）。**不含形容詞、不含球迷暱稱、不用 WPA。**

| shape | 判定條件 | 模板 |
|---|---|---|
| `walkoff` | 主隊勝 ∧ 最後一個 ready 打席在 ≥9 局下半 | `{winner} {ws}：{ls} 擊敗 {loser}，{inning} 局下 {hitter} 的{action}是再見致勝的一擊（ΔRE24 {dre}）。` |
| `blowout` | 分差 ≥ 5 | `{winner} {ws}：{ls} 擊敗 {loser}，{big_inning} 局{big_half}的 {big_runs} 分是最大單局進帳；全場對得分期望值影響最大的打席是 {inning} 局{half} {hitter} 的{action}（ΔRE24 {dre}）。` |
| `close` | 其餘 | `{winner} {ws}：{ls} 擊敗 {loser}，全場對得分期望值影響最大的打席是 {inning} 局{half} {hitter} 的{action}（ΔRE24 {dre}），該半局共得 {half_runs} 分。` |
| `tie` | 同分 | `{home} {hs}：{as_} {away} 和局；…` |

真實生成樣例（2026/A，資料全來自 DB）：

> **241（08-04，blowout）**
> 樂天桃猿 8：1 擊敗 台鋼雄鷹，6 局上的 4 分是最大單局進帳；全場對得分期望值影響最大的打席是 1 局上 `0000007822` 的全壘打（ΔRE24 +1.94）。

> **243（08-05，walkoff）**
> 台鋼雄鷹 7：6 擊敗 樂天桃猿，10 局下 王柏融 的一壘安打是再見致勝的一擊（ΔRE24 −0.16）。

> **244（08-05，blowout）**
> 富邦悍將 10：2 擊敗 中信兄弟，5 局上的 5 分是最大單局進帳；全場對得分期望值影響最大的打席是 1 局上 范國宸 的全壘打（ΔRE24 +1.87）。

> **245（08-05，close）**
> 味全龍 3：0 擊敗 統一7-ELEVEn獅，全場對得分期望值影響最大的打席是 3 局下 陳子豪 的全壘打（ΔRE24 +1.00），該半局共得 2 分。

**三個必須進設計的發現**：

1. **再見打席的 ΔRE24 是負的**（243：−0.16）。因為半局結束使 RE(after)=0，一支只帶 1 分的再見安打會被記成 1 − RE(_2_,0)=1 − 1.1625。→ **再見打席永遠拿不到 |ΔRE24| 排行前段**，必須由①結論行以「賽果事實」單獨承載，不能指望②關鍵打席選到它。這正好佐證 brief 把①②分開是對的。
2. **球員名不可靠 `cpbl.players`**：241 的 MVP `0000007822`（威克）在 `players` 無列，join 後顯示成 ID，`games.mvp_id` 走 `LEFT JOIN players` 的 `/api/v1/games/calendar` 也會顯示 null。`game_livelog.hitter_name` 與 snapshot `HitterName` 都有正確中文名 → **姓名解析改以逐場來源為主、`players` 為輔**。
3. `blowout`／`close` 的門檻（5 分／其餘）是我暫定的，**需要需求方裁定**；245 的 3:0 被歸為 `close` 讀起來略勉強。

**判定：PASS（模板機制可行），可讀性待需求方人工審。**

### 6.2 假設 3 — 首頁雙態的既有端點

| #81 需要 | 既有端點 | 是否足夠 |
|---|---|---|
| 今日／下一批賽事清單 | `/api/v1/daily/summary` → `next_slate.games` | ✅ |
| 賽前勝率點值＋1 個訊號 | 同上 `games[].pregame`（`home_win_probability` + `signals`） | ✅（07-17 藍圖決議已落地） |
| 最近比賽日的比分 | 同上 `latest_game_day.games` | ✅ |
| 資料新鮮度／降級揭露 | 同上 `freshness` / `availability` | ✅ |
| **比賽中：逐場 live 比分＋局數壘況** | `/api/v1/games/{sno}/live` 或 `/status` 的 `live_snapshot` | ⚠️ **逐場各一次請求**；`daily/summary` 本身不帶任何 live 欄位 |
| **昨日戰果一行的「結論」** | 無 | ❌ **缺**：勝敗投／MVP 只在 `/api/v1/games/calendar`（全季）與 `/live`（單場）；一句事實句與關鍵打席完全沒有 |

**判定：PARTIAL。** 賽前態 100% 足夠；live 態需要在 `daily/summary` 增補逐場 snapshot 摘要（或接受首頁 N 次請求）；賽後一行需要 #80 產出的**結論 API**——這與 brief「#81 每場一行消費 #80 結論 API」的規劃一致，本 spike 只是把「缺口具體到欄位」。

---

## 7. 範圍外發現（回報 PM，本卡不處理）

| # | 發現 | 影響 | 建議 |
|---|---|---|---|
| O-1 | `models/sabr.build_re24` 把「突破僵局上壘」當一個打席記給被放上壘的跑者，每筆 +0.6356 RE24（2026/A 已 49 筆） | `cpbl.batter_re24`／`pitcher_re24` 與其消費端（球員頁 SABR 區）帶系統性偏差；2024+ 一軍與延長賽場次愈多偏差愈大 | 另開小卡：`build_re24` 改吃 canonical PA（或至少排除 taxonomy `role=non_pa` 的 action） |
| O-2 | `game_detail.winning_type` 被 brief／舊 design brief 當「官方致勝方式」，實為勝方旗標（4,163 場 100% 共變） | recap ①結論行原定欄位無資料源 | 修正 brief 用詞；若真要「致勝方式」，唯一既有分類器是 `models/special_records._walkoff_type()`（僅再見場） |
| O-3 | `cpbl.players` 缺列（實例 `0000007822` 威克），而 `game_livelog.hitter_name` 有名字 | MVP／決勝資訊顯示成 10 碼 ID；`/api/v1/games/calendar` 的 `mvp` 回 null | 對照記憶錨點 `player-name-authority`：`players.name` 同步鏈可能漏補當季新登錄球員，值得查 |
| O-4 | DB `game_livelog` 末列 `content` 被覆寫為「比賽結束」，遺失該打席的真實敘述與「N人出局」 | canonical PA 末打席 `post_state.outs` 少 1（實測 4/5 場）；未來若要顯示「最後一球」敘述會拿到佔位字串 | 屬 ingest 語意；記錄在案，ΔRE24 不受影響（`min(outs,2)` 吃掉） |
| O-5 | 生產 snapshot 的 `decisions.winning_pitcher/losing_pitcher` 在 final 後仍常為 null（2/5） | 當晚 recap 無法顯示勝敗投 | 已納入本卡設計的降級階梯；若需要當晚就有，須另查 stats 站是否有其它欄位 |
| O-6 | 兩個官方來源（www `getlive` vs `stats.cpbl`）的 `content`／`pitch_cnt`／`is_special_event` 不保證逐字一致 | recap 引用逐球敘述時來源不同會有微差 | 設計上只引用 `action_name`（taxonomy 已規範）與結構化欄位，不引用自由文字 |

---

## 8. 附錄：核心程式片段（可重現）

### 8.1 canonical PA → 逐打席 ΔRE24（假設 1／4 的核心）

```python
from cpbl.ingest.pa_build import derive_half_inning_outs

def bases_str(bases: list[str]) -> str:
    return ("1" if "1" in bases else "_") + ("2" if "2" in bases else "_") + ("3" if "3" in bases else "_")

def bases_of_event(e: dict) -> str:                      # livelog 壘位＝該事件「之前」的壘況
    return (("1" if e.get("first_base") else "_") + ("2" if e.get("second_base") else "_")
            + ("3" if e.get("third_base") else "_"))

def delta_re24(pas, events, re_map):
    """pas = published game_plate_appearances（依 pa_index），events = 該場 livelog。"""
    # livelog 語意：壘位/out_cnt 是事件前、比分是事件後 → 先標每列的事件前比分
    pv = ph = 0
    for e in sorted(events, key=lambda x: int(x["main_event_no"])):
        e["_pre_vs"], e["_pre_hs"] = pv, ph
        pv = e["visiting_score"] if e.get("visiting_score") is not None else pv
        ph = e["home_score"] if e.get("home_score") is not None else ph
        e["_post_vs"], e["_post_hs"] = pv, ph
    outs_by_event = derive_half_inning_outs(events)       # {event_no: (before, after)}
    by_no = {str(e["main_event_no"]): e for e in events}

    real = [i for i, p in enumerate(pas) if p["state"] != "non_pa"]   # 佈局列不當錨點
    nxt = {i: (real[j + 1] if j + 1 < len(real) else None) for j, i in enumerate(real)}

    out = []
    for i, p in enumerate(pas):
        pre = p["pre_state"] or {}
        vht = str(pre.get("half"))
        pre_k, post_k = ("_pre_vs", "_post_vs") if vht == "1" else ("_pre_hs", "_post_hs")
        term = by_no.get(str(p["end_event_no"])) if p["end_event_no"] else None
        if p["state"] != "ready" or term is None:
            out.append({"pa_index": p["pa_index"], "delta_re24": None, "reason": p["state"]})
            continue
        outs_before_term = outs_by_event[str(p["end_event_no"])][0]        # ⚠️ before，不是 post_state.outs
        re_f = re_map[(bases_of_event(term), min(outs_before_term, 2))]
        runs = term[post_k] - term[pre_k]
        j, re_after = nxt.get(i), 0.0
        if j is not None:
            npre = pas[j]["pre_state"] or {}
            if (npre.get("inning"), str(npre.get("half"))) == (pre.get("inning"), vht):   # 半局末 → 0
                re_after = re_map[(bases_str(npre.get("bases") or []), min(int(npre.get("outs") or 0), 2))]
        if runs < 0:                                                       # 比分修正列歸跑者桶
            out.append({"pa_index": p["pa_index"], "delta_re24": None, "reason": "negative_runs"})
            continue
        out.append({"pa_index": p["pa_index"], "delta_re24": round(re_after + runs - re_f, 4)})
    return out
```

### 8.2 snapshot → `pa_build` Event（假設 6 的核心）

```python
FIELD_MAP = {
    "MainEventNo": "main_event_no", "InningSeq": "inning_seq",
    "VisitingHomeType": "visiting_home_type", "BattingOrder": "batting_order",
    "OutCnt": "out_cnt", "BallCnt": "ball_cnt", "StrikeCnt": "strike_cnt",
    "PitchCnt": "pitch_cnt", "IsBall": "is_ball", "IsStrike": "is_strike",
    "Content": "content", "ActionName": "action_name",
    "BattingActionName": "batting_action_name", "HitterAcnt": "hitter_acnt",
    "PitcherAcnt": "pitcher_acnt", "FirstBase": "first_base",
    "SecondBase": "second_base", "ThirdBase": "third_base",
    "VisitingScore": "visiting_score", "HomeScore": "home_score",
    "IsChangePlayer": "is_change_player", "IsSpecialEvent": "is_special_event",
}
_BOOLS = ("is_ball", "is_strike", "is_change_player", "is_special_event")

def snapshot_events(snapshot: dict) -> list[dict]:
    out, seen = [], set()
    for row in snapshot["livelog"]:
        ev = {dst: row.get(src) for src, dst in FIELD_MAP.items()}
        ev["main_event_no"] = str(ev["main_event_no"])
        if ev["main_event_no"] in seen:          # 官方 LiveLog 末列可能重複（實測 A-241）
            continue
        seen.add(ev["main_event_no"])
        for f in _BOOLS:                          # ⚠️ 官方是字串 "0"/"1"；不轉型 PA 會歸零
            v = ev.get(f)
            ev[f] = None if v in (None, "") else (
                v.strip() not in ("0", "false", "False") if isinstance(v, str) else bool(v))
        for f in ("first_base", "second_base", "third_base"):
            ev[f] = (ev.get(f) or "").strip() or None
        out.append(ev)
    return out

# 之後即可：
#   from cpbl.ingest.pa_build import load_taxonomy, plate_appearances
#   pas = plate_appearances(year, kind, sno, snapshot_events(snap), load_taxonomy())
```

### 8.3 當晚 mini 對帳閘門（fail-closed；本 spike 5/5 通過）

```python
def mini_reconcile(snapshot, snap_pas) -> tuple[bool, str | None]:
    from cpbl.ingest.pa_build import half_inning_out_violations
    if snapshot.get("phase") != "final":
        return False, "phase_not_final"
    if not all(r.get("IsBall") is not None and r.get("IsStrike") is not None
               for r in snapshot["livelog"]):
        return False, "missing_ball_strike_flags"     # 見 §5.3
    evs = snapshot_events(snapshot)
    last = max(evs, key=lambda e: int(e["main_event_no"]))
    if (last["visiting_score"], last["home_score"]) != (
            snapshot["away"]["score"], snapshot["home"]["score"]):
        return False, "score_mismatch"
    if half_inning_out_violations(snap_pas):          # 既有不變式：任一半局打者出局 PA > 3
        return False, "half_inning_out_violation"
    return True, None
```
