# 單場賽況頁三態體驗 — 結構規格（UX-GAME-RECAP1 Phase A 設計稿）

> 卡片：[Issue #80](https://github.com/ruan6047/cpbl-analytics/issues/80)（T3，`INIT-GAME-RECAP` Wave 1）
> spec 基線：[`docs/research/INIT-GAME-RECAP_DISCOVERY-BRIEF.md`](../research/INIT-GAME-RECAP_DISCOVERY-BRIEF.md) @ main `91457b2`（含 2026-08-06 WPA 禁令兩次修訂）
> 設計系統：[`docs/design/UI_UX_SYSTEM.md`](UI_UX_SYSTEM.md)（canonical；本檔只引用節次，不複述 token 數值）
> spike 證據：[`docs/research/INIT-GAME-RECAP/spike-report.md`](../research/INIT-GAME-RECAP/spike-report.md)
> 狀態：**待需求方人工審**。本檔是**結構規格**（元件層級 + 欄位 + 資料源 + 狀態機），不是像素稿。
> 版本：v0.4（2026-09-05，GPT-5@Codex）——`UX-COMPLETED-JUDGMENT-DATE-BOUNDARY1`（[#161](https://github.com/ruan6047/cpbl-analytics/issues/161)）實作：完成場判準加台北日期界線，並新增 §1.1.2 中斷比分態。
> 版本：v0.3（2026-08-21，Claude Opus 5@Claude Code）——`UX-GAME-COMPLETED-SCOREBAR1`（[#160](https://github.com/ruan6047/cpbl-analytics/issues/160)）Design Gate：新增 §1.1.1「賽後態記分條逐欄位定稿」。**本次只動 §1.1 的賽後欄**，其餘章節未變更。
> 版本：v0.2（2026-08-06，Claude Opus 5@Claude Code）——第五輪人工審裁決：②關鍵打席改 |ΔWP| 選取＋直接顯示擺動量、③得分半局鏈移除、Δ 符號 tooltip、`/methodology#key-plays` 新段

---

## 0. 範圍與紅線

- 本檔涵蓋 `/games/[sno]` 的**三態一次設計**（brief §「三態設計原則」Q8 定案），實作分波：完賽態＝本卡 Wave 1，賽前態＝Wave 2，逐打席探索器（#79）＝Wave 3。
- **不引入 brief 以外的新範圍**：每個區塊在 §8 溯源表列出 brief 出處；無出處者一律不畫。
- 紅線沿用（2026-08-06 修訂）：WP 機率**水平值**不作敘事宣稱，**\|ΔWP\| 序數選取與變化量顯示為可**（brief 非目標欄兩次修訂；守門條件見 §4.2）；正式文案**禁球迷暱稱**（暱稱僅限賽況頁焦點區既有用法）；`/api/info` 契約不動；每日鏈與 G4 凍結檔不動；API 唯讀。
- 「進行中態＝現行 ESPN 板，不動」是 brief 明訂的非目標——本設計對 live 態的唯一改變是**換底不換臉**（Recent Plays 改吃共用的打席事實流），**行為與外觀不得變化**，此為驗收條件。

---

## 1. 恆定骨架（三態共用）

頁面自上而下永遠是同一組區位，只有「主區塊」被置換。骨架元件全部取自 `components/ui.tsx`（UI_UX_SYSTEM §3、§10.4 registry），**禁平行發明**。

| 區位 | 元件 | 三態共通契約 |
|---|---|---|
| **A. 麵包屑 / 標題列** | 現行 `game-live-page.tsx` 既有 | 隊名走 `lib/teams.ts`（§9.2 解析三路徑）；`StatusBadge` 承載場次狀態（`done`/`live`/`warn`/`scheduled`，§3.2） |
| **B. 頂部記分條 `<GameScorebar>`**（新抽出，三態共用） | `Card`（`padding="px-4 py-3"`）＋ `TeamBadge`／`LetterBadge` | 內容依態切換，**版面高度與欄位骨架不變**（避免態切換時 CLS，§3.3） |
| **C. 主區塊（置換）** | `<PregameMain>` / `<LiveMain>` / `<RecapMain>` | 見 §2–§4 |
| **D. 資料狀態揭露列** | `Notice`（amber）或 inline `Pill` | freshness／availability 語意**不得共用同一空態文案**（§3.3 的 blueprint 例外） |
| **E. 恆定尾部** | `MainTabs`（§4.1）＋ `BoxTabs`（既有 622 行，不動） | 賽前：預告資訊；賽中／賽後：box tabs／逐球；賽後另加 WP 曲線（收合，下移保留） |

### 1.1 記分條 B 的三態欄位

| 欄位 | 賽前 | 賽中 | 賽後 |
|---|---|---|---|
| 兩隊識別 | `TeamBadge` + 隊名 + 本季戰績 | 同左 | 同左 |
| 中央 | 開賽時間（`starts_at`） | 比分 + `▲/▼ N 局` + 壘包圖 + 球數 | **終場比分**（逐欄位定稿見 §1.1.1） |
| 副行 | 先發投手（雙方） | 當前投打 | **勝敗投／救援／MVP**（見 §5 暫定規則） |
| 右側 | `StatusBadge scheduled` | `StatusBadge live` + 更新秒數 | `StatusBadge done` + 資料來源標記 |

> 局數文案沿用既有 `lib/live-game.ts` 的 `inningLabel()`／`hasStartedPlay()`——**未開打場次 worker 會回 `inning=1` 佔位**，不可只判 truthy（該檔已有的紅線註解）。

### 1.1.1 賽後態記分條逐欄位定稿

> 狀態：**已於 2026-08-21 經需求方核可**（[核可留言](https://github.com/ruan6047/cpbl-analytics/issues/160#issuecomment-5368688414)，`UX-GAME-COMPLETED-SCOREBAR1` Design Gate）。本檔其餘章節仍為 §0 所述之「待需求方人工審」。
> 裁定來源：[需求方 2026-08-21 裁定](https://github.com/ruan6047/cpbl-analytics/issues/160#issuecomment-5367339034)——該裁定只答「孰先」半題，本節的逐欄位定稿是新內容，須另行核可。

#### 裁定與孰先

**完賽態頁首記分條不顯示 `TOP/BOT`、壘包與球數，只呈現終場比分。**

三份文字的孰先在 2026-08-21 已裁定：`docs/tasks/UX-GAME-RECAP1.md:19` 的**驗收條**（`#80`，經跨家族查核 APPROVE 並合併，逐字「完賽頁首…不得顯示成正在進行的 `TOP/BOT`、壘包或球數」）與本檔 §1.1 的**設計規格**（「賽後＝終場比分」）同向且勝出；`CLAUDE.md` `## Roadmap` 段那句「賽況頁 ESPN 風格狀態板：頂部記分條 + 壘包/球數」是由 `8241dce8`「align CLAUDE.md and README with **current shipped state**」加入的**進度描述**（記分條本身是 16 分鐘後的 `f31d13205` 才建立），不構成推翻驗收條的依據，並須同步限定為賽中態。

#### 現況的具體傷害（2026-08-21 本機實測，`/games/276`，2026-08-20 中信兄弟 4：3 味全龍）

該場末筆 livelog 為 `inning_seq=9`、`visiting_home_type='2'`、`out_cnt=2`、`ball_cnt=2`、`strike_cnt=2`、`second_base='9'`、`content='比賽結束'`。因 `out_cnt` 語意是**打席前**計數，畫面呈現的是「最後一個出局發生之前」的局面：

- 可讀文字：`▼ BOT 9`、`B ●●○`、`S ●●`
- 螢幕閱讀器：`<svg aria-label="壘上二壘，2 出局">`——**比賽結束後仍被念成正在進行的局面**
- 375 px 版面：中央區塊佔 108 px，兩側隊伍欄各只剩 70.5 px，隊名「中信兄弟」被壓成 18.5 px 寬 × 80 px 高（**每行一字**）

#### 逐欄位定稿

⚠️ 本節描述的是**現行 `web/src/components/game-board.tsx` 的 `ScoreBar`**，不是 §9.2 目標元件樹裡尚未抽出的 `<GameScorebar>`。§1.1 表的「副行／右側」兩格在現行 `ScoreBar` **未實作**（勝敗投／救援／MVP 實作於 `<RecapMain>` 的 §4.1 結論行；`StatusBadge` 位於區位 A 的標題列），故那兩格在此標記為**非本卡**，維持 §1.1 表所載的未來目標。

| 格 | 欄位與內容 | 資料源 | 空 | 不可用 | 錯誤 |
|---|---|---|---|---|---|
| **G0 狀態列**（§1.1 表未涵蓋，記分條第 1 列） | `phaseLabel`「比賽結束」＋`inningLabel(glyph)`＋日期／賽事編號／球場＋最後更新＋`sr-only aria-live` | `snapshot`；**整列以 `{snapshot && …}` 閘門**，歷史場（`live_snapshot === null`）只剩日期／編號／球場 | 局數不成立 → `inningLabel` 回 `null` → 顯示「等待賽況」 | 無 snapshot → 整段狀態文字不渲染 | `source_status==="error"`／`freshness==="stale"` 由**頁面層** `Notice` 承載，不入記分條 |
| **G1／G5 兩隊識別**（左＝客、右＝主）**不變** | `TeamLogo`(40, decorative) ＋ 隊名 ＋ `{w}-{l}` 本季戰績 | `game.away_team_name`／`home_team_name`；`data.records[teamCode]` | 戰績缺 → 該行留空字串（不寫 `0-0`） | 非現役 franchise（`isCurrentTeam` 為 false）→ 退化為純文字、不連結 | 不適用 |
| **G2／G4 終場比分**（左客、右主）**不變** | `font-mono text-4xl font-bold tabular-nums` 兩個大數字 | `liveScorebarScores(game, e)`：優先 `game.away_score`／`home_score`，缺值才降階到當前事件的 `visiting_score`／`home_score` | 賽後態**構造上不會為空**——`canShowPostgameConclusions` 要求 `away+home > 0` 才成立 | 同左 | 不適用 |
| **G3 中央 ⭐本卡唯一變更** | **賽後＋總覽**：只一行 `終場`（`text-xs font-semibold tracking-wide`，**`text-muted`**）。**不渲染** `▲/▼ N 局`、**不渲染** `<BasesOuts>`、**不渲染** B/S `Dots`。<br>**賽後＋逐打席**：維持賽中形狀（選中打席的 `▲/▼ N 局`＋壘包＋球數）——見下方「兩個頁籤共用同一元素」 | 無資料依賴（純態標籤）。態＝`canShowPostgameConclusions(live_snapshot, away+home) && view === "overview"` | 不適用 | 不適用 | 不適用 |

#### 為什麼中央格是「終場」而不是留白

G0 狀態列整列以 `{snapshot && …}` 為閘門，**歷史存檔場沒有 snapshot，「比賽結束」那段整個不渲染**，只剩日期／賽事編號／球場（本機 `/games/276` 實測即為此形狀；生產端以 `2024 A/100`、`A/200` 實測 `live_snapshot = None` 且有真實比分，證實整個歷史存檔都走這一支）。若中央格留白，這些場次的記分條將沒有任何文字說明那兩個大數字是**終場**比分而非即時比分。`終場` 二字同時是 §1.1 表「賽後＝終場比分」的最小忠實實作。

色票用 `text-muted` 而非現行的 `text-accent`：accent 在本記分條是「進行中」的訊號色（G0 的 `phase === "live"` 用 `text-accent` ＋脈動圓點），完賽態沿用會把「已結束」畫成「進行中」。

#### 兩個頁籤共用同一元素（誤傷防線）

`ScoreBar` 在 DOM 上位於 `{tabs}` **之前**（`game-board.tsx:773` vs `:775`），賽後戰報與逐打席**共用同一個元素**。逐打席頁籤裡，中央區塊是「選中打席的局面」，是該頁籤的核心資訊，**不得一併移除**。因此態閘門必須是 `completed && view === "overview"`（與 `game-live-page.tsx:212` 既有的 `plainLinescore` 同一條件），**不是裸 `completed`**。

⚠️ 態判定不得寫成 `snapshot?.phase === "final"`：`canShowPostgameConclusions` 的定義是 `scoreTotal > 0 && (snapshot === null || snapshot.phase === "final")`，**歷史場 `snapshot === null` 時兩者分歧**（`completed` 為 true、`phase==="final"` 為 false）。生產端實測 `2024 A/100`、`A/200` 皆 `live_snapshot = None` 且有真實比分 ⇒ 整個歷史存檔都走這一支，寫成 phase 判定會讓這張卡對絕大多數場次完全失效。⚠️ 當日場另當別論：生產上 `2026 A/276` 是 `phase: 'final'`（本機因 `cpbl.live_game_snapshots` 表不存在而回 `None`，勿以本機形狀推論生產）。

#### 版面

grid 樣板 `grid-cols-[1fr_auto_auto_auto_1fr] gap-4 px-5 py-4` **不變**；唯一的版面調整是完賽態的中央格**不掛 `px-2`**、並加 `whitespace-nowrap`（那 16 px 內距是留給壘包圖與球數燈的，兩個字不需要；不加 nowrap 時 375 px 下「終場」會被壓成直排）。

下表為同一場（`/games/276`）在同一組視窗尺寸下、修正前後各量一次的實測值：

| | 修正前 | 修正後 |
|---|---|---|
| 桌機 1280 px：記分條高 | 169.3 px | **124 px** |
| 桌機 1280 px：中央格 | 108 × 85.3 px | **40.6 × 16 px** |
| 桌機 1280 px：兩側 `1fr` 欄寬 | 423.8 px | **457.5 px** |
| 375 px：grid 欄寬 | `70.5 / 21.2 / 108 / 21.2 / 69.8` | **`77 / 21.2 / 24.6 / 21.2 / 77`** |
| 375 px：欄總寬 vs 容器內容寬 | 354.7 vs 285 → **溢出 69.7 px（被 `overflow-hidden` 裁掉）** | 285 vs 285 → **溢出 0** |
| 375 px：記分條高 | 196 px | 196 px（**不變**） |
| 375 px：隊名排版 | 「中信兄弟」18.5 px 寬、每行一字 | 25 px 寬、**仍每行一字** |

⚠️ **一項原先寫錯、經實測更正的預測**：初稿寫「中央格釋出約 80 px 給兩側 `1fr` 欄，隊名可單行排列」——**實測不成立**。兩側欄確實從 70.5 px 長到 77 px，但「中信兄弟」單行需要約 64 px，仍差得遠，折行照舊。375 px 真正的改善是**內容不再溢出容器被裁切**（69.7 px → 0），高度則完全沒變（列高由兩側隊伍欄決定，不是中央格）。⇒ **375 px 的隊名折行是既有問題，本卡未解決**，若要處理需另開卡（可能得改成窄螢幕換行版面，屬 §1 區位 B 的骨架變更）。

⚠️ **對 §1 區位 B「版面高度與欄位骨架不變（避免態切換時 CLS）」的刻意偏離**：本定稿**不維持賽中／賽後等高**（桌機 169.3 → 124 px；375 px 因列高由兩側隊伍欄決定，實測不變）。理由有二——(a) 高度變化只發生在「使用者正看著直播、比賽剛結束」的那一次輪詢，且該次同時伴隨主區塊由總覽整體置換為賽後戰報，記分條單獨保持等高並不能讓版面穩定；(b) 為等高而在賽後保留約 45 px 空白，等於在**絕大多數瀏覽情境**（所有歷史存檔場都是完賽態）長期付出代價，只為了換一次性的態切換平順。⇒ 取捨為「賽後版面正確」優先於「態切換零 CLS」。

⚠️ 需求方 2026-08-21 核可此偏離時另補一項理由：§1 區位 B 那條的理由指向 **`§3.3`，而該節不存在**（`## 3. 賽中態（不動）` 沒有子節，全檔兩處 `§3.3` 皆懸空）——該條款的理由從未被寫下來。⚠️ 懸空引用本身不在本卡射程，未修。

#### 無障礙

移除 `<BasesOuts>` 即移除其 `aria-label="壘上…，N 出局"`——那是本痛點的螢幕閱讀器受害面（實測完賽場仍念「壘上二壘，2 出局」）。`終場` 是可讀文字，不需額外 `aria-*`。共用元件 `ui.tsx` 的 `BasesOuts` 幾何與文案**不得改動**（首頁今日賽事卡是另一個消費者）。

### 1.1.2 帶中止比分、排定於未來的保留／延賽場

> 狀態：**需求方已於 #161 Design Gate 裁定，2026-09-05 實作。**

完成場的必要條件是 `scoreTotal > 0 && game_date <= today`，再套用既有的
`live_snapshot` final／歷史無 snapshot 判準；`delay_kind` **不是**完成判準，因為已完成的補賽仍會保留該歷史標記。

- `today` 固定以 `Asia/Taipei` 的日曆日計算，不採瀏覽器本地時區；這與後端
  `src/cpbl/completion.py:120-128` 的「先判 `game_date > as_of`」方向一致。
- 尚未跨過日期界線、卻已有中止比分時，G3 中央格不得顯示「終場」、`TOP/BOT`、壘包或球數。
  `delay_kind="保留"` 顯示既有詞彙「保留比賽」；`delay_kind="延賽"` 顯示既有
  canonical phase 詞彙「延期」。兩者皆沿用 `text-muted` 與 `whitespace-nowrap`。
- 未知或缺漏的 `delay_kind` 不新增猜測性標籤；缺 `game_date` 時也 fail closed，不宣稱完賽。

#### 明確排除（非本節、非本卡）

- **G0 狀態列的 `▼ 9 局` 不動**：該列在有 snapshot 的完賽場會顯示「比賽結束　▼ 9 局」。此處半局符號的語意是「比賽在第 9 局下**結束**」，是完賽事實（等同記分板慣例的 `F/9`／延長賽 `F/10`），與中央格「正在進行中的 BOT 9」語意不同——決定性差異是**同列有沒有 phase 標籤**：`live-game.ts:94-99` 的 `PHASE_LABEL.final = "比賽結束"` 就在 `▼ 9 局` 隔壁，中央格則沒有任何 phase 標籤。需求方 2026-08-21 核可時複驗此理由並裁定**保留、不動**。
- **延長賽／提前結束的局數不另顯示**：中央格只寫 `終場`，不加「N 局」。裁定與 §1.1 表均未要求，屬新增資訊。
- **賽前態**：`GameBoard`（含 `ScoreBar`）只在 `data.livelog.length > 0` 時渲染（`game-live-page.tsx:281`），賽前場走另一條分支，故 §1.1 表的賽前中央格「開賽時間」與現行 `ScoreBar` 無關。
- **`WpBar`**（`game-board.tsx:794`）無 live／completed 閘門一事屬另案（需求方 2026-08-21 裁定第 3 節，統計揭露紅線 3）。
- **`out_cnt` 的資料語意**不改，不新增衍生欄位。

---

## 2. 賽前態（Wave 2 — 本卡只畫結構占位）

主區塊 `<PregameMain>` 僅定義**槽位**，實作屬後續 wave：

| 槽位 | 內容 | 資料源（皆既有） |
|---|---|---|
| P1 先發對決 | 兩位先發投手近況卡 | `/api/v1/players/{id}/pitching`、`/season` |
| P2 兩隊近十場 | 戰績走勢 | `/api/v1/games/recent` |
| P3 勝率預測 | 點機率 ＋ 1 個主要訊號 | `/api/v1/outcome/pregame`（`serving_state` 降級揭露不得省略） |
| P4 探索器入口 | 連往 `/predict`（#79 於 Wave 3 接入） | — |

- 現行 `Pregame`／`PregameCard`（`overview.tsx`）已實作 P3 雛形，Wave 2 併入而非重寫。
- 本卡交付**不含** P1–P4 的實作與視覺細節。

---

## 3. 賽中態（不動）

主區塊 `<LiveMain>` ＝ 現行 ESPN 風格狀態板（頂部記分條／壘包球數／逐球好球帶／Recent Plays），**從 `game-live-page.tsx` 原樣搬出**。

唯一變更（brief §架構定案「三消費者共用」）：

- Recent Plays 的資料由頁面內自建的逐列掃描，改為消費 §6 的**單場打席事實流服務**。
- **驗收＝換底不換臉**：搬移前後同一場次的 Recent Plays 逐列文字、順序、跳轉錨點必須完全相同。實作卡須以既有場次快照對照。

---

## 4. 賽後態 — recap 區塊（原五塊，③得分半局鏈於 2026-08-06 人工審移除）

主區塊 `<RecapMain>`。ΔRE24 一律為**打者觀點**（正＝對打擊方有利）。

### 4.1 ①結論行 `<ConclusionLine>`

| 欄位 | 內容 | 資料源 | 缺值行為 |
|---|---|---|---|
| 終場比分 | `{away} {a}：{h} {home}` | `cpbl.games`（權威）／snapshot `away.score`/`home.score`（暫定） | 無 → 不進入賽後態（見 §7 階梯） |
| 一句事實句 | 見 §4.1.1 | 打席事實流 ＋ `game_scoreboard` | 槽位缺 → 降級到只有比分句 |
| 勝敗投／救援 | 姓名 + 本季第 N 次 | `cpbl.games.winning_pitcher_id`… ＋ `pitching_gamelog` | **暫定期常缺（spike 實測 2/5）→ 顯示「官方確認中」，不留空、不猜** |
| 官方單場 MVP | ⭐ + 姓名 + 本季第 N 次 | `cpbl.games.mvp_id`／snapshot `decisions.mvp`（實測 5/5） | 缺 → 整個 chip 不顯示 |

> **「致勝方式」欄取消**（對 brief 的修正）：spike 實查 `game_detail.winning_type` 是「勝方是主隊還客隊」的旗標，與比分 100% 共變、**不是致勝方式**（4,163 場零例外）。該語意改由一句事實句的 `walkoff`／`blowout`／`close` 分支承載，全部可查證。

#### 4.1.1 一句事實句：模板 ＋ 事實槽

分支條件全部機器可判定，槽位全部是可查證事實。**不含形容詞、不含暱稱、不用 WPA。**

| shape | 條件 | 句型骨架 |
|---|---|---|
| `walkoff` | 主隊勝 ∧ 最後一個 `ready` 打席在 ≥9 局下半 | 「{勝隊} {W}：{L} 擊敗 {負隊}，{N} 局下 {打者} 的{官方結果}是再見致勝的一擊（ΔRE24 {±x.xx}）。」 |
| `blowout` | 分差 ≥ 5 | 「…，{N} 局{上/下}的 {R} 分是最大單局進帳；全場對得分期望值影響最大的打席是 {N} 局{上/下} {打者} 的{官方結果}（ΔRE24 {±x.xx}）。」 |
| `close` | 其餘 | 「…，全場對得分期望值影響最大的打席是 {N} 局{上/下} {打者} 的{官方結果}（ΔRE24 {±x.xx}），該半局共得 {R} 分。」 |
| `tie` | 同分 | 「{主} {h}：{a} {客} 和局；…」 |

- 「官方結果」＝ canonical PA 的 `result_action`（taxonomy 已規範的封閉集合），**不引用逐球自由文字**（兩個官方來源的 `content` 不保證逐字一致，spike §4.2）。
- **`blowout`／`close` 的分差門檻需要需求方裁定**（現值 5 分為 spike 暫定；3:0 被歸為 `close` 讀來略勉強）。
- **再見打席的 ΔRE24 是負值**（半局結束使 RE(after)=0）→ 這正是①與②必須分開的理由：再見打席永遠上不了 |ΔRE24| 排行，必須由結論行單獨承載。（改採 |ΔWP| 選取後②通常也會選到再見打席——勝率直接收斂到 1——但那是選取訊號的副產品，①不改為依賴②。）

### 4.2 ②關鍵打席 3–5 `<KeyPlays>`

| 項目 | 規格 |
|---|---|
| 選取 | **主排序＝\|ΔWP\|**（勝率擺動絕對值）取前 3–5，**呈現時改回時間序**（brief §recap 五塊「時間序呈現」） |
| 每列欄位 | 局數＋上/下、打者（`PlayerLink`，§3.5 實體連結）、投手、**打席前局面**（出局數／壘況／分差）、官方結果、**勝率變化**（主資訊；受益隊＋恆正整數百分點，受益隊隊色淡底 chip）、ΔRE24（次要 chip）、**雙色勝率條**（打席後水平＋受益隊輔助色位移段，視覺對齊生產「關鍵時刻」卡） |
| 勝率視角 | 資料層與勝率條幾何維持**主隊視角**（條的客左主右與 WP 曲線同方向）；**標示層轉受益隊視角**（「某隊 +N pt」，同生產「關鍵時刻」卡），讀者不需解讀負號。卡片標頭 deep-link `/methodology#key-plays` |
| 局面脈絡 | 壘況以 3 格壘包圖示 ＋ 文字替代（§8 可及性：不只靠顏色） |
| 垃圾時間 | 分差 ≥7 的**淡底降飽和已移除**：\|ΔWP\| 選取下 81 場實測 0 命中（舊 \|ΔRE24\| 選法 15 命中），呈現層補丁已無對象；事實旗標與「分差 ≥7」文字標籤保留（降級路徑仍可能選到） |
| 降級 | 勝率模型不可用（無分布 artifact／賽事類型不支援）→ 後端退回 \|ΔRE24\| 選取並以 `key_play_selection` 揭露，卡片**必須顯示降級註記** |
| 互動 | 點列 → 跳該打席逐球（既有 `jumpToPa`）；Wave 3 接 #79 探索器 |
| 紅線 | 勝率水平值只作**視覺化**（與已上線 WP 曲線同資訊類），**不作文字宣稱**；顯示夾層沿 `lib/win-prob-display.ts`（終場點豁免靠 `wp_after_terminal`）；`plate_appearances`（逐打席頁籤）不得帶任何 WP 欄位；此契約由 `tests/test_pa_facts.py` 釘住 |
| 排除 | `state != 'ready'` 的 PA（`non_pa` 突破僵局佈局列、`truncated`、`unreliable`）一律不進候選；`delta_re24` 缺值者亦不入選 |

> **選取準則沿革**：v1＝\|ΔRE24\|（禁 WPA 排序）→ v2＝\|ΔWP\| 選取 → v2.1 直接顯示擺動量
> → v2.2 加回雙色勝率條（水平值視覺化）→ v2.3 標示與條的視覺對齊生產「關鍵時刻」卡
> （受益隊＋恆正值、位移段輔助色）（2026-08-06 需求方第五輪人工審逐階裁決）。禁令精確化為「WP 機率**水平值**不作宣稱」，
> 序數選取與變化量顯示不依賴水平校準；統計依據與守門條件見 `/methodology#key-plays`
> 與 brief 非目標欄的修訂段。

### 4.3 ~~③得分半局事實鏈 `<ScoringChain>`~~（2026-08-06 人工審移除）

需求方第五輪人工審裁定移除：與②關鍵打席重複，且得分脈絡已由每列的得分 chip
（`RunsBadge`，含得分後比分）承載。前端元件已刪除；後端 `pa_facts.scoring_chain()`
與 `facts.scoring_chain` 欄位**保留**（事實流服務的輸出，#79 探索器等消費者可用），
但賽後態總覽不再呈現。

### 4.4 ④兩隊表現行 `<TeamLines>`

**吸收既有雛形，不重寫**：現行 `game-live-page.tsx` 的 `highlights`（本場焦點）／`decisions`（決勝資訊）／`mvp` 區塊與 `overview.tsx` 的 `GameOverview` 直接搬入本元件。

| 子區 | 內容 | 資料源 |
|---|---|---|
| 兩隊打線摘要 | 安打／得分／失誤／殘壘 | `game_scoreboard` 隊級 R/H/E |
| 投手線 | 先發＋牛棚逐人 IP／ER／K／BB | `pitching_gamelog` |
| 本場焦點 | 既有 `highlights` 產生器（含已量化的球迷用語） | 既有 |
| 決勝資訊 | 勝敗投／中繼／救援／致勝打點 | 既有 `decisions`／`gw_rbi` |

> 焦點區的球迷用語**維持現況**（brief 非目標明訂「recap **正式文案**禁暱稱」，焦點區既有用法不在此限）。

### 4.5 ⑤跳入點 `<JumpLinks>`

| 入口 | 目標 | 狀態 |
|---|---|---|
| 全打席探索器 | #79（Wave 3） | 本卡只放 disabled 占位或不放（需求方裁定） |
| 逐球好球帶 | 既有 box tabs 的逐球分頁 | 現有 |
| WP 曲線 | 頁面下方既有位置（**收合**，掛 `wp_reliability` 揭露） | 現有；**recap 區塊內不重複內嵌**（brief 非目標） |

---

## 5. 雙源、暫定標記與升級行為

### 5.1 兩個資料源

| 源 | 取得 | 打席邊界 | 何時用 |
|---|---|---|---|
| **權威源** | `cpbl.game_plate_appearances`（`state='published'`）＋ `game_pa_events` ＋ `game_livelog` | canonical PA builder 已物化 | 隔日起（爬蟲入庫＋PA build 完成） |
| **後備源** | live worker final snapshot（Redis，TTL 48 h） | 以 `pa_build.plate_appearances()` **純函式**現算 | 當晚（權威源尚未入庫） |

**權威源路徑必吃 canonical PA 表**，不得從 raw livelog 重刻切界（brief §端到端檢視補充）。後備源路徑**復用同一份純函式**，不另刻輕量切界——spike 已證此路可行且與權威源零分歧。

### 5.2 暫定標記的範圍（依 spike 實測縮小）

spike 5 場實測：snapshot 與權威源在**打席邊界、逐打者 ΔRE24、關鍵打席 Top5 全等**。因此暫定標記**不掛在個別數字上**，改為：

| 對象 | 暫定期行為 |
|---|---|
| 頁面級 | 記分條右側一枚 `Pill`：「當晚即時計算 · 官方資料入庫後自動更新」，連結 `/methodology` |
| 比分／局面／關鍵打席／ΔRE24／得分鏈 | **照常顯示，不加標記**（實測與權威源一致） |
| 勝敗投／救援 | **顯示「官方確認中」**，不顯示可能錯誤的值（實測 snapshot 僅 2/5 有勝投） |
| MVP | 照常顯示（實測 5/5） |
| 逐球 TrackMan | 沿現行 `tracking_availability` 語彙（`pending`／`no_equipment`…），不與本標記混用 |

### 5.3 升級行為

- 升級是**資料驅動**，無人工步驟：服務每次取數先問權威源，`is_completed_game` 為真 **且** 該場有 `published` PA build → 走權威源、頁面級 Pill 消失、勝敗投填入。
- 兩層完賽觸發（brief §端到端檢視補充，把現行 `canShowPostgameConclusions` 形式化）：

| 層 | 判準 | 用途 |
|---|---|---|
| 頁面層 | `snapshot.phase == 'final'` | 當晚切入賽後態 |
| 資料層 | `cpbl.completion.is_completed_game()`（**新判準**，比分 OR 外部證據，含台北日界） | 隔日權威源判定；`INIT-GAME-RECAP` 是該 helper 的首個新消費者 |

- **嚴禁以時間推斷硬切完賽**（`present_status` 教訓：該欄對完賽零鑑別力，全庫 13,480 場皆為 1）。

---

## 6. 單場打席事實流（底層共用服務）

三個消費者（live Recent Plays／賽後 recap／#79 探索器）共用同一服務，**不各自重建打席邏輯**（前科：leaders 自建勝敗序列與 special_records 分歧）。

### 6.1 建議模組邊界

```
src/cpbl/models/pa_facts.py          # 新：純核心 + 薄 adapter
  ├─ delta_re24(pas, events, re_map) # 純函式（spike 報告 §8.1 已驗）
  ├─ from_db(season, kind, sno)      # adapter：published PA + pa_events + livelog
  ├─ from_snapshot(snapshot)         # adapter：pa_build.plate_appearances() on snapshot events
  └─ mini_reconcile(snapshot, pas)   # fail-closed 閘門（spike 報告 §8.3）
src/cpbl/api/routers/facts.py        # 新：GET /api/v1/games/{sno}/facts
```

- **不動** `pa_build.py`（G4 凍結期外仍屬 canonical builder，本卡只 import 其純函式）。
- **不動** `recap.py`（WP-API1 所有，語意為「參考級 WP」，與本服務正交）。
- `live_game_worker.py` 為單檔窄授權：**本 wave 不需改動**（spike 證實 `decisions`／`IsBall`／`IsStrike` 生產已具備）。

### 6.2 回傳契約（草案）

```jsonc
{
  "season": 2026, "kind_code": "A", "game_sno": 243,
  "source": "authoritative",          // authoritative | provisional
  "completed": true,
  "completion_evidence": "is_completed_game",   // 或 snapshot_final
  "final": { "home_score": 7, "away_score": 6, "result": "home_win" },
  "conclusion": {
    "shape": "walkoff",
    "sentence": "…",                  // §4.1.1 模板產生
    "slots": { /* 事實槽原值，供前端重排／i18n */ },
    "decisions": { "winning_pitcher": {...}, "losing_pitcher": null, "closer": null,
                   "mvp": {...}, "availability": "official_pending" }
  },
  "plate_appearances": [
    { "pa_id": "…", "pa_index": 12, "state": "ready",
      "inning": 7, "half": "2", "outs_before": 2, "bases_before": ["2","3"],
      "away_score_before": 5, "home_score_before": 4,
      "hitter": {"player_id": "…", "name": "…"},   // 姓名來源見 §6.3
      "pitcher": {"player_id": "…", "name": "…"},
      "result_action": "一壘安打", "outcome_family": "…",
      "runs_on_play": 2, "delta_re24": 1.6065, "garbage_time": false }
  ],
  "scoring_chain": [ { "inning": 7, "half": "2", "team_code": "…", "runs": 2, "pa_ids": ["…"] } ],
  "re_matrix": { "span": "2018-2025", "kind_code": "A" }
}
```

### 6.3 三個必須遵守的實作細節（皆由 spike 取證）

1. **ΔRE24 錨點是「終結事件之前」的出局數**，必須用 `pa_build.derive_half_inning_outs()` 取回；誤用 `post_state.outs`（事件之後）會讓全場每個打席系統性偏移一個出局的 RE 差。
2. **姓名不走 `cpbl.players`**：實測 `0000007822`（威克）無 players 列 → 會顯示成 10 碼 ID。`game_livelog.hitter_name`／snapshot `HitterName` 兩源皆有正確中文名，應以逐場來源為主、`players` 為輔。
3. **snapshot 事件需正規化**：官方旗標是字串 `"0"/"1"`；`main_event_no` 可能重複（實測 A-241 末列）。未處理會使 PA 數歸零或重複計算。

---

## 7. 異常降級階梯（fail-closed，由上往下第一個成立者生效）

| 階 | 條件 | 呈現 |
|---|---|---|
| **1 權威完整** | `is_completed_game` ∧ 該場有 `published` PA build | 完整 recap 區塊，無來源標記 |
| **2 暫定完整** | `snapshot.phase == 'final'` ∧ **mini 對帳閘門全過** | 完整 recap 區塊 ＋ 頁面級暫定 Pill ＋ 勝敗投「官方確認中」 |
| **3 簡版** | `snapshot.phase == 'final'` ∧ **mini 對帳不過**（或缺 `IsBall`/`IsStrike`） | ①結論行（僅比分句）＋③得分半局鏈（走 snapshot `inning_score`）＋④兩隊表現行；**不出②關鍵打席**，以 `EmptyState` 說明「打席資料一致性檢查未通過，待官方資料入庫」 |
| **4 stale live** | 有 snapshot 但 `phase` 仍為 `live`／`unknown`，且已超過 `stale_after_seconds` | **停在賽中態**＋`Notice` 揭露最後更新時間；**嚴禁時間推斷硬切完賽** |
| **5 無即時源** | 無 snapshot（Redis 掛／二軍 D／賽制無 worker） | 走權威源；若權威源也未到 → 顯示賽程與 freshness，不產生假打席 |
| **6 保留賽／延賽** | `games.delay_kind` 有值 | **沿現行**：`StatusBadge warn` ＋ `Notice` 說明；不進賽後態（保留賽帶比分但日期在未來，`is_completed_game` 的日期界線已排除） |
| **7 PA build 未 publish** | 存在 `reconciliation_required` build（來源修正未對帳） | 視同②不可用 → 走階 3 的簡版，並揭露「官方資料有修正，對帳中」 |

### 7.1 mini 對帳閘門（階 2 的進入條件）

snapshot 屬 **LIVE 暫態**（#54 領域），暫定 recap 出手前必須自證內部一致；**任一項不過即不出暫定版**：

| 檢查 | 判準 | spike 實測 |
|---|---|---|
| G1 | `snapshot.phase == 'final'` | 5/5 |
| G2 | 每列都有 `IsBall`／`IsStrike`（缺則 `pinch_hit_slot` 合併判準失效，見 spike §5.3） | 5/5（生產） |
| G3 | livelog 末列推導比分 == `snapshot.away.score`／`home.score` | 5/5 |
| G4 | `pa_build.half_inning_out_violations()` 為空（任一半局打者出局 PA > 3 即紅） | 5/5 |

### 7.2 二軍（kind D）

**無 live worker**（worker 只打 `kindCode=A` 排程）→ D 卡永遠只有隔日權威源。賽後態在當晚不出現，頁面停在「等待官方資料」而非空白 recap。此為**預期行為，須在文案明寫**。

---

## 8. 快取策略

| 態／源 | 渲染 | 快取 | 理由 |
|---|---|---|---|
| 賽中 | client 輪詢（現行不動） | 不快取 | 12 秒級更新 |
| 賽後 **暫定源** | SSR（動態） | `s-maxage=60, stale-while-revalidate=60` | 勝敗投可能在當晚補齊；短窗即可 |
| 賽後 **權威源 · 當季** | ISR | `revalidate = 3600` | 官方更正／改判由即時算零工序吸收，但仍需窗口讓 PA build 修正生效 |
| 賽後 **權威源 · 歷史**（`game_date` < 本季） | ISR | `revalidate = false`（永久） | 歷史場次不可變 |
| 首頁昨日戰果列（#81） | 消費結論 API | 同「賽後」規則 | 一致性由同一服務保證 |

- **切換機制**：`source` 欄位決定快取標頭；由暫定升級為權威時，第一個 `revalidate` 週期自然翻新。若要即時翻新，另加 on-demand revalidate（本卡不做，列為選配）。
- ⚠️ 現況 `/games/[sno]` 是 client component + client fetch，**全站唯一 ISR 路由是 `/methodology`（600 s）**。本設計把 recap 主區塊改為 server component + ISR，是**新的部署面**：驗證須依記憶錨點 `isr-deploy-verification`（等 revalidate 到期重測 mtime，不可看一次就下結論）。

---

## 9. 重構切分：從 721 行單體到元件樹

### 9.1 現況

| 檔 | 行 | 問題 |
|---|---|---|
| `web/src/app/games/[sno]/game-live-page.tsx` | 721 | 資料載入、輪詢、三態分支、highlights 產生器、決勝資訊、MVP、tab 路由全在一個 client component |
| `web/src/app/games/[sno]/overview.tsx` | 239 | `GameOverview` / `Pregame` / `buildMoments` 混住 |
| `web/src/app/games/[sno]/box-tabs.tsx` | 622 | **本卡不動** |

### 9.2 目標元件樹

```
app/games/[sno]/
├─ page.tsx                     # server：metadata（不動）+ 取數 + 決定態
├─ game-shell.tsx               # client island：輪詢與 tab 狀態（取代 game-live-page.tsx 的殼）
├─ parts/
│  ├─ scorebar.tsx              # <GameScorebar>（三態共用，§1.1）
│  ├─ status-notice.tsx         # <DataStateNotice> freshness/availability 揭露（區位 D）
│  └─ page-tabs.tsx             # MainTabs 包裝（區位 E）
├─ states/
│  ├─ pregame-main.tsx          # Wave 2 占位（§2）
│  ├─ live-main.tsx             # ESPN 板原樣搬出（§3，換底不換臉）
│  └─ recap-main.tsx            # Wave 1 新（§4）
├─ recap/
│  ├─ conclusion-line.tsx       # ①
│  ├─ key-plays.tsx             # ②
│  ├─ team-lines.tsx            # ④（吸收 overview.tsx 的 GameOverview + highlights/decisions/mvp）
│  └─ jump-links.tsx            # ⑤
├─ overview.tsx                 # 縮減：只留 Pregame/PregameCard（供 Wave 2）
└─ box-tabs.tsx                 # 不動
```

`web/src/lib/`：
- `live-game.ts`：既有純函式（`canShowPostgameConclusions`／`inningLabel`／`resolveStatusSnapshot`）保留，新增 §5.3 的兩層完賽判定包裝。
- 新增 `game-facts.ts`：結論 API 的型別與 `EXPECTED` 路由快照更新（`npm test` 路由快照契約，push 前必跑）。

### 9.3 切分原則（對齊 UI_UX_SYSTEM §10）

- **Presentational（server-safe）**：`scorebar`、`conclusion-line`、`key-plays`、`team-lines` — 無 hook、不加 `"use client"`。
- **Client island**：`game-shell`（輪詢／tab）、`live-main`（即時更新）、`jump-links`（互動跳轉）。
- **可序列化 props 鐵則**：server → client 一律傳可序列化物件，不傳函式。
- **抽取準則**（§10.3）：三態共用的記分條、三態共用的狀態揭露列都達「跨頁重用／設計系統元素」門檻，必須上抽。
- **零硬編色**：全部走語意 token；隊色只走 `lib/teams.ts`（§9.1「隊色＝身分，不進 @theme」）。

### 9.4 分步落地（實作卡建議切法）

1. **S1** 抽出 `<GameScorebar>` 與 `<DataStateNotice>`，三態共用，行為零變化（純重構，可獨立驗證）。
2. **S2** 後端 `pa_facts.py` + `/api/v1/games/{sno}/facts`（權威源路徑），加逐打席窮舉歸類迴歸測試（spike §2.3 為基準值）。
3. **S3** `<LiveMain>` 搬出並換底吃 facts API — **換底不換臉**對照驗收。
4. **S4** `<RecapMain>` 各區塊 + 降級階梯 + 快取。
5. **S5** 後備源（snapshot）adapter + mini 對帳閘門。

> S5 可與 S4 並行但**不得先於 S4**：沒有權威源基準就無法驗證暫定源等價。

---

## 10. 可及性與響應式（沿用 canonical，不新增規則）

依 UI_UX_SYSTEM §7／§8 與舊 design brief 的驗收條款：

- 所有圖表與壘包圖有文字替代；選取狀態不只靠顏色。
- 關鍵打席列可鍵盤選擇；控制項 ≥ 44×44 px。
- 375 px 無整頁水平捲動；寬內容（打席表）自帶橫向捲動容器。
- 尊重 `prefers-reduced-motion`；動效只用 §11.1 的 closed set，**禁發明新 keyframes**。
- **降飽和的垃圾時間打席仍須通過對比度檢查**。
- 深色模式走 §2.2 token；active 標籤 `bg-ink + text-paper`（**禁 `text-white`**）。

---

## 11. 溯源表（每一項對 brief 的出處）

| 本檔章節 | brief 出處 | 備註 |
|---|---|---|
| §1 恆定骨架 | §三態設計原則（Q8 定案）表格「區位／賽前／賽中／賽後」 | 具體化到元件層級 |
| §2 賽前態 | §子卡與 wave 第 3 點（Wave 2 屆時開小卡） | 只畫占位 |
| §3 賽中態不動 | §非目標「賽中即時 recap（進行中態＝現行 ESPN 板，不動）」＋§架構定案「live 頁換底不換臉、行為不變為驗收條件」 | — |
| §4.1 結論行 | §recap 五塊①「比分＋致勝方式＋一句事實句」 | **「致勝方式」欄取消**，見下 |
| §4.1.1 事實句 | §待驗證假設 2「模板＋事實槽，人工審把關」 | 分支門檻待需求方裁定 |
| §4.2 關鍵打席 | §recap 五塊②「時間序呈現、帶局面脈絡」＋§非目標欄 2026-08-06 兩次修訂（\|ΔWP\| 序數選取＋直接顯示擺動量） | 選取準則升為 v2；淡底降飽和移除 |
| §4.3 得分半局鏈 | §recap 五塊③ | **2026-08-06 人工審移除**（與②重複，得分 chip 已承載） |
| §4.4 兩隊表現行 | §recap 五塊④「吸收既有 decisions／highlights／MVP 雛形」 | — |
| §4.5 跳入點 | §recap 五塊⑤＋§非目標「recap 區塊重複內嵌 WP 曲線」 | — |
| §5 雙源／暫定 | §雙源打席事實流（2026-08-06 需求方修訂）＋§待驗證假設 6 | 暫定範圍依 spike 實測**縮小**（見下） |
| §5.3 兩層完賽 | §端到端檢視補充「完賽觸發雙層」 | `canShowPostgameConclusions` 形式化 |
| §6 打席事實流 | §架構定案「單一底層服務…三消費者共用」 | 模組邊界為本檔新增之實作建議 |
| §7 降級階梯 | §官方系統異常韌性（mini 對帳閘門／final 永不到殘局）＋§端到端檢視補充（二軍無 live worker／保留賽） | 階 7（reconciliation_required）為本檔補全 |
| §8 快取 | §端到端檢視補充「快取切換：暫定（短快取）→權威（長快取／ISR）」 | ISR 部署面風險為本檔補註 |
| §9 重構切分 | §證據與假設「`game-live-page.tsx`（721 行）已含 completed 分支與雛形區塊」 | 切法為本檔新增之實作建議 |
| §10 可及性 | `GAME_RECAP_DESIGN_BRIEF.md` §驗收與風險（v1.3 已核可） | 未新增規則 |

### 11.1 本檔對 brief 的三處偏離（需求方裁定項）

1. **取消①結論行的「致勝方式」欄**：`game_detail.winning_type` 實查為勝方旗標（主/客），非致勝方式，4,163 場零例外。→ 該語意改由事實句 shape 承載。
2. **暫定標記範圍縮小**：brief 假設 6 預留「當晚版掛暫定標記（隔日權威源自動除）」；spike 實測當晚與隔日**零分歧**，故標記降為頁面級來源揭露，只有**勝敗投／救援**（snapshot 實測 2/5）真的走「官方確認中」。
3. **降級階梯新增第 7 階**（PA build `reconciliation_required`）：brief 未提，但這是 canonical builder 既有的 fail-closed 狀態，不處理會出現「有 build 卻不是 published」的空窗。

---

## 12. 未決事項（人工審時請裁定）

| # | 問題 | 我的建議 |
|---|---|---|
| Q1 | 事實句 `blowout`／`close` 的分差門檻 | 建議 `blowout ≥ 5`、`close ≤ 2`、其餘用中性句；現值 3:0 落在 `close` 讀來勉強 |
| Q2 | ⑤跳入點是否在 Wave 1 就放 #79 的 disabled 占位 | 建議**不放**（避免死連結）；Wave 3 再加 |
| Q3 | 暫定期是否顯示 MVP | 建議顯示（實測 5/5 可得），掛頁面級標記即可 |
| Q4 | 賽後態是否預設展開 WP 曲線 | 建議維持**收合**（WP 全 scope unsupported，只作參考） |
| Q5 | 首頁（#81）live 態：`daily/summary` 增補逐場 snapshot 摘要 vs 前端 N 次請求 | 建議增補（單次聚合，與 `daily/summary` 既有「取代十餘組請求」的設計意圖一致），但屬 #81 範圍 |
