# #350 季後賽「系列賽名單」UI/UX 重設計：規劃方案（修訂二，方案 D）

- 卡片：https://github.com/ruan6047/cpbl-analytics/issues/350 ，目前在規劃階段，規劃者為 Claude Opus 5.5。
- 規劃依據是需求重新鎖定後的 Issue body，加上以下需求方裁定：
  - [6309822733](https://github.com/ruan6047/cpbl-analytics/issues/350#issuecomment-6309822733)、[6309977252](https://github.com/ruan6047/cpbl-analytics/issues/350#issuecomment-6309977252)：方案 A／B 不採、決定呈現方向、同意擴充 API
  - [6310001489](https://github.com/ruan6047/cpbl-analytics/issues/350#issuecomment-6310001489)：DH 區門檻
  - [6310023008](https://github.com/ruan6047/cpbl-analytics/issues/350#issuecomment-6310023008)：需求重新確認
- 工作基準：`origin/main` @ `42ce575b`。依卡面規定，**執行時改以 #349 合併後的 main 為基準**。
- 示意素材放在 `docs/design/plans/350-assets/`。mockup 只是示意，不是產品碼，用完可整個目錄刪掉。
- 方案 D 的 mockup 由 `gen_mockup_d.py` 產生（已移除，見 e86bb7a8；原指令：`python3 -I gen_mockup_d.py .`），用的全是正式站唯讀快照：
  - `roster-2026-C-snapshot.json`：名單 API，`last_refresh_at 2026-10-21T10:24:21+08:00`
  - `fielding-2026-A-snapshot.json`：`/api/v1/season/fielding`
  - `batting-leaders-2026-A-snapshot.json`：`/api/v1/season/batting-leaders?min_pa=0`
  - `series-2026-C.json`：由 `derive_series_batting.py`（已移除，見 e86bb7a8）從本系列 G1–G3 的 `/games/{sno}/live` 彙總而成
- **mockup 只是暫時拿其他公開端點湊數；產品版一律由名單 API 擴充欄位提供，⛔ 前端不另抓這些端點。**

---

## 1. 方案 D：兩隊並列，依位置分區，每區先列綜合成績、再列人名

**一句話**：兩隊左右並列；投手依角色分區，野手依主守位分區，另加 DH 區。每區先用灰底列出該位置的綜合成績（成員合計），下方只列人名；個人數值要點人名才看得到。

**截圖**（每種資料範圍各一組）

| 範圍 | 桌機 1280 | 390 |
|---|---|---|
| 例行賽背景 | `350-assets/mockup-d-background-desktop-1280-top.jpg`、`350-assets/mockup-d-background-desktop-1280-fielders.jpg` | `350-assets/mockup-d-background-mobile-390-top.jpg` |
| 本系列實戰 | `350-assets/mockup-d-series-desktop-1280-top.jpg`、`350-assets/mockup-d-series-desktop-1280-fielders.jpg` | `350-assets/mockup-d-series-mobile-390-fielders.jpg`（含 DH 區） |

示意頁：`350-assets/mockup-d-background.html`、`350-assets/mockup-d-series.html`。

### 1.1 版面

1. **頂部**：兩隊各一行，例如「投手 15 · 捕手 3 · 內野 8 · 外野 6」。資料範圍切換（例行賽背景／本系列實戰）沿用現有元件。
2. **投手段**：依角色分區，順序是先發 → 長中繼 → 中繼 → 勝利組 → 拆彈組 → 終結。兩隊都沒有的角色整區省略。
3. **野手段**：依**主守位**分區，順序是捕手 → 一壘 → 二壘 → 三壘 → 游擊 → 左外 → 中外 → 右外 → 指定打擊（DH）。
4. **每區兩欄**：左右各一隊。欄頂是灰底綜合成績，下方是人名，依出賽多到少排。
   - 例行賽背景：投手依例行賽出賽、野手依該守位出賽排序。
   - 本系列實戰：依本系列出賽排序。
5. **DH 區**：跟著資料範圍切換（裁定 6310001489）。例行賽背景列出例行賽 DH 先發 ≥4 場的人（「超過三場」照字面，已在 6310023008 確認）；本系列實戰列出本系列 DH 先發 ≥1 場的人。
   - 列在 DH 區的人，仍會出現在他的主守位區。
   - 例行賽 DH 先發數沒有任何公開端點可取，所以 mockup 的例行賽 DH 區只放佔位，要等 API 擴充後才有真實名單。
6. **點人名**：開啟現有的能力與走勢抽屜。抽屜標頭加一行個人數值：本範圍的 G、ERA·局數或 AVG·OPS、主守位出賽、DH 先發數。
7. **從主視圖拿掉**：個人一行成績、PR 標籤、近 15 場箭頭、球隊／守位篩選、排序。見衝突 2。

**實測高度**（整個名單區塊）：

| 寬度 | 方案 D | 現況 |
|---|---|---|
| 桌機 1280 | 約 1,071px，兩隊都在 | 兩隊全開 3,118px |
| 390 | 約 1,984px，無橫向溢出 | 只看一隊就 4,759px |

### 1.2 綜合成績要算哪些（附建議）

- 原則：每區只放 2 個數字，而且是球迷看得懂的傳統數據。一律**先加總原始計數再算率**，不平均各人的率；分母為 0 時顯示「—」。

| 區 | 數字 | 計算 | 建議理由 |
|---|---|---|---|
| 投手角色區 | ERA、局數 | ΣER×27／Σouts；Σouts 換算成局數（x.y） | 名單 API 的投手 line 已有 `outs`、`er`，前端就能算 |
| 野手守位區 | AVG、OPS | ΣH／ΣAB；OBP＝(ΣH+ΣBB+ΣHBP)／(ΣAB+ΣBB+ΣHBP+ΣSF)，SLG＝ΣTB／ΣAB | 需要 API 在 line 補上 `tb`、`hbp`、`sf`（見 §2）。守備率只有例行賽才有，切到本系列就會變成「—」，所以不建議放（Q1） |
| DH 區 | AVG、OPS | 同野手區，成員是 DH 區名單 | 同上 |

**語意要寫進說明（ⓘ）**：

- 綜合成績是「這一區成員的合計」，不是「打該守位時」的成績。
- 同一人出現在多區時，會分別計入各區，例如投手多角色、野手同時在守位區與 DH 區。

### 1.3 野手要放在哪個守位：主守位

- 主守位＝該球員例行賽一軍各守位出賽最多的守位；出賽數相同時，依上述守位順序取先者。
- 規劃者建議只放主守位，不放「守過的每個守位」。理由：裁定 6309977252 ① 要求「下方列人名、數值點開才看」。名字旁邊沒有數字時，把一人列在只守過 1 場的位置會被誤讀成該位置的人（例：味全姚冠瑋捕手 1G）。此題列為 Q2。
- **兩種資料範圍都用例行賽主守位分區**。理由是本系列場次太少，而且只有打席紀錄的守位資料、沒有守備紀錄，分區會跳動。只有數字與 DH 區跟著範圍切換。
- 沒有一軍守備紀錄的野手：本快照為 0 人。實作時放進「其他（無一軍守備紀錄）」小區，⛔ 不猜守位。

---

## 2. 名單 API 擴充設計

**範圍**：只加唯讀欄位。⛔ 不改 DB schema、⛔ 不加索引、⛔ 不改角色規則、⛔ 不寫任何資料。若執行時發現非動這些不可，就停下並退回需求。

### 2.1 端點與檔案

| 項目 | 內容 |
|---|---|
| 端點 | 沿用 `GET /api/v1/playoffs/roster`（`src/cpbl/api/routers/playoffs_roster.py`），不新增端點 |
| 契約字串 | `contract` 維持 `playoffs-roster/v1`，只加欄位、不改既有欄位 |
| 路由快照 | `tests/test_route_snapshot.py` 的 EXPECTED 只列路徑，第 67 行已有 `/api/v1/playoffs/roster`，**不需修改** |
| 讀取與組裝 | `src/cpbl/playoffs/roster_reader.py`：在 `read_background`（第 485 行起）、`read_series`（第 514 行起）各加一次批次查詢，查詢次數不隨人數增加；`batting_line`（第 105 行）補輸出 `tb`、`hbp`、`sf`；`background_of`／`series_of` 組裝新欄位 |
| 與 #349 的關係 | #349 已核定**不改任何程式碼**（裁定 6310023008 另登記），所以 `roster_reader.py` 沒有程式碼交集。#349 在 10/22 寫入 rev3 角色資料，會改變回應中 `tactical_roles`／`role_provenance` 的內容，形狀不變，本卡分區照常讀取 |

### 2.2 新欄位（只出現在野手；投手不加）

| 欄位 | 型別 | 意義 | 資料來源 |
|---|---|---|---|
| `background.positions` | `{pos: string, g: int}[]`，依 g 降冪 | 例行賽一軍各守位出賽 | `cpbl.fielding_current`（`year`、`kind_code='A'`、`pos <> '投手'`），`leaders.py` 的 `/season/fielding` 也讀這張表（第 556 行起） |
| `background.primary_position` | `string \| null` | 主守位（規則見 §1.3） | 由上一欄推導 |
| `background.dh_starts` | `int \| null` | 例行賽 DH 先發數；判定方式見 §2.3 | `cpbl.batting_gamelog`＋`cpbl.game_livelog` |
| `background.dh_starts_unknown` | `int` | 有先發、但 livelog 找不到守位紀錄的場數 | 同上 |
| `background.line.tb`／`.hbp`／`.sf` | `int` | 補給前端算綜合 OBP／SLG | `BAT_COUNTS_SQL` 已經在查（第 385 行起），只是沒輸出 |
| `series.dh_starts` | `int \| null` | 本系列 DH 先發數；沒有完賽場或來源待更新時為 null | 同 `dh_starts`，限本系列已完賽的場次 |
| `series.dh_starts_unknown` | `int` | 同上 | 同上 |
| `series.line.tb`／`.hbp`／`.sf` | `int` | 同上 | `SERIES_BAT_SQL` 已經在查（第 404 行起） |

**fail-closed 規則**：`dh_starts_unknown > 0` 時，前端 DH 區不能判定此人是否達門檻。該欄要標「待更新」，⛔ 不能把未知當成 0。

### 2.3 DH 先發的判定依據與可信度

**判定方式**：`batting_gamelog.role_type = '先發'`，而且該打者本場第一個「`defend_station_code` 不為空」的 livelog 事件（依 `main_event_no` 排序）是 `'DH'`。

**能不能用官方先發守位？** 不能。官方先發守位只存在 `cpbl.game_lineup_announcement_revisions`，那是 2026 年 E／C 賽前公告，本機只收到 1 場（E 第 4 場）。覆蓋率不夠，不能當資料來源。

**本機唯讀驗證**（下列數字是彙總計數，不是逐人資料）：

1. **與官方公告對照**：E 第 4 場兩隊共 18 名先發，首打席守位與官方公告的 `DefendStation` **18／18 一致**。公告另含 2 名替補，加註括號或 PH，不在比對範圍。樣本只有 1 場。
2. **結構一致性**：2026 年一軍 720 個「隊－場」中，有 716 個的 9 名先發首打席守位恰好是 9 個不重複、而且包含 DH 的守位；不符的 4 個中，2 個是有先發缺首打席守位，其餘 2 個的原因未細查。C／E 季後賽 14 個隊－場全部符合。
3. **覆蓋率**：本名單 34 名野手的例行賽先發共 2,012 場次，找不到守位紀錄的是 0；其中 14 人至少有 1 場 DH 先發。

**可信度判斷**：高。已知的偏差情境是先發打者在第一個打席前就被換下，這時首打席守位是 null，會計入 `dh_starts_unknown`，不會被算錯。

**效能**：本機實測對 34 人做例行賽查詢，執行時間 68ms。`game_livelog` 主鍵是 `(year, kind_code, game_sno, main_event_no)`，不需要新增索引。

### 2.4 後端測試（pytest）

- 加在 `tests/test_playoffs_roster_reader.py`／`tests/test_playoffs_roster_series.py`，用既有的 fixture 方式，可參考 `tests/roster_284_support.py`：
  - `dh_starts`：恰好門檻、多一場、少一場（例行賽）
  - 本系列：0 場完賽時為 null
  - 首打席是 PH、首打席之前被換下 → 計入 `unknown`
  - 投手沒有這些新欄位
  - `positions` 的排序與主守位同分時的決定方式
  - `line.tb`／`hbp`／`sf` 與已輸出的 `obp`、`slg` 一致：用新欄位重算的結果必須等於原值
- 契約回歸：新欄位只能是加上去的；既有欄位的鍵與值不變（快照比對）。
- 依 `docs/AI_RUNBOOK.md` §7.2 跑 DB 契約測試。
- `uv run ruff check`、`uv run pytest` 必跑：這次會改 Python，屬於驗收內。

---

## 3. 前端改動（預估，執行者可調整相鄰檔案）

1. **`web/src/lib/playoffs-roster.ts`**
   - 型別加 §2.2 的欄位，全部可選，舊回應照常可用。
   - 純函式：
     - `pitcherBlocks(teams, scope)`
     - `fielderBlocks(teams, scope)`：依 `primary_position` 分區
     - `dhMembers(team, scope)`：例行賽 ≥4、本系列 ≥1；兩個門檻寫成常數，⛔ 不讓使用者調
     - `battingComposite(members, scope)`、`pitchingComposite(members, scope)`：先加總再算率，分母 0 → null
   - `ROSTER_METHOD_HELP` 補三句：綜合成績的語意、DH 門檻、多區重複計入。
2. **`web/src/components/playoffs/roster-section.tsx`**
   - 用無 hooks 的 `RosterBlocks` 取代主視圖的 `RosterView` 小卡網格。
   - 人名按鈕開啟抽屜；焦點要歸還給**實際被點的那顆按鈕**，因為同一人會出現在多區。
   - 「球員明細」依衝突 2 的裁定處理。
3. **`web/src/components/playoffs/roster-drawer.tsx`**：標頭加一行個人數值，資料取自摘要中的 member，不需新 API。
4. **`playoffs-live.tsx`**：預期不改。
5. **測試**：`cd web && npm test`，也就是 `node --test` 加 `react-dom/server` 靜態渲染，**不是 vitest**。涵蓋：
   - 兩隊欄都存在
   - 區塊順序；空區省略
   - 綜合成績的數值與分母 0 時顯示「—」
   - DH 門檻邊界：例行賽 3／4、本系列 0／1；`unknown > 0` 時顯示「待更新」
   - 切換資料範圍時 DH 區成員跟著改變
   - 多區重複出現的人
   - 舊回應沒有新欄位時，野手退回依官方守位大類分區，不能拋錯
   - `memberRoles` 對 v2 角色空值仍拋錯
   - `npm run build:check` 支持部署能編譯（驗收 2 的前提）

---

## 4. 正式站驗收取證計畫與部署需求

**部署需求**（本 repo 的 CI 不部署）：

1. 本卡 PR 合併。
2. 主站 bump submodule。
3. 主站 CI 重建 **api 與 web 兩個容器**：API 有改，所以 api 容器必須重建。
4. 不需要 migration、不需要資料刷新：新欄位讀的是既有表，每日爬蟲本來就在寫這些表。
5. 部署需要需求方另行授權，窗口由共同主 PM 排定，預設在 #349 之後。

**取證**（全部在正式站，用真實瀏覽器）：

| 驗收 | 證據 |
|---|---|
| 1 人工審 | 需求方在桌機與手機上自己看 |
| 2 截圖 | 從導覽列點擊進入 `/playoffs` →「系列賽名單」→ 截圖 → 重新載入 → 截圖。桌機 1280 與 390 各做一組，**兩種資料範圍都要截** |
| 3 資料來源 | 對正式站 `GET /api/v1/playoffs/roster?season=2026&series=C` 確認 `dh_starts`、`positions` 等欄位存在；畫面上的 DH 區與綜合成績只從這支 API 的回應算出（看 DevTools Network，沒有對 `/games/*/live` 或 `/season/fielding` 的請求）；DB schema 未變（`git diff` 沒有 `migrations/`）；#349 的角色照常出現 |
| 4 DH 對帳 | 從 API 回應取劉俊緯（`player_id 0000007079`）的 `background.dh_starts`／`series.dh_starts`，和畫面上他在兩種範圍下是否列入 DH 區逐一對照。截至快照，他本系列 DH 先發 2 場，應列入本系列 DH 區；例行賽是否 ≥4 以正式站 API 數值為準 |

**回復方式**：`git revert` 本卡的 merge commit，主站再 bump submodule 並重建 api／web。不涉及資料，不需要資料回復。

**停止條件**：

- 需要 schema、索引、角色規則或生產寫入才能完成 → 停下，退回需求。
- 發現 #349 改了 `roster_reader.py` → 停下，交 PM。
- 正式站 `dh_starts_unknown` 大量大於 0 → 停下回報。

**驗收外檢查**（交需求方保留或排除）：

- 容器 `cpbl-train` 回測：本卡不觸及模型與特徵。

---

## 5. 待需求方確認（每題最多兩個選項，附建議）

**Q1 野手區的綜合成績**
- 甲：只放 AVG、OPS，兩種範圍一致。**建議甲**。
- 乙：再加守備率。只有例行賽有，本系列會顯示「—」。

**Q2 野手放在哪個守位**
- 甲：只放主守位，每人只出現一次；DH 區另列。**建議甲**。理由是人名旁沒有數字，放多個守位會誤導。
- 乙：守過的每個守位都放。

**衝突 1：觸控目標 44px**（UI_UX_SYSTEM §1 原則 6、§4、§7）
- 人名按鈕實測高約 24px。
- 甲：人名按鈕維持文字高度，左右間距 ≥10px，明列為本區例外。**建議甲**。
- 乙：放大到 44px，整區會明顯變長（未量測）。

**衝突 2：PRD v2 第 3 區的小卡規格被取代**（`docs/design/PLAYOFFS_PRD_V2.md` 第 164–172 行：PR 標籤、近 15 場箭頭、球隊篩選、排序）
- 甲：主視圖拿掉這些，PR 與走勢只在抽屜看；本卡同時改寫 PRD v2 第 3 區。**建議甲**。
- 乙：保留舊小卡，當作預設收合的「球員明細」。
- **與 #349 的檔案交集**：#349 也要改 `docs/design/PLAYOFFS_PRD_V2.md`（工具人判準描述）。若採甲，兩卡會改同一個檔，**交 PM 排定合併順序**（預設 #349 先，本卡 rebase）。

---

## 6. 對照 `docs/design/UI_UX_SYSTEM.md`（方案 D）

| 節次 | 對照 | 結論 |
|---|---|---|
| §1 原則 1 | 結論層是綜合成績，細節要點人名才出現 | 符合 |
| §1 原則 4 | 分母 0 顯示「—」；`unknown` 顯示「待更新」 | 符合 |
| §1 原則 6、§7 | 390 實測無橫向溢出；觸控見衝突 1 | **衝突 1** |
| §2 | 灰底用 `surface-2`，字用 `ink`／`muted`；mockup 的 hex ⛔ 不帶進 tsx | 實作約束 |
| §3.5 | 人名是實體按鈕。依照 `ENTITY_LINK` 語彙用 `ink` 加細底線、hover 時變 `accent`（mockup 已照做） | 符合 |
| §4.1 | 資料範圍切換沿用 band 軌道加 `bg-ink text-paper` | 符合 |
| §10.1 | 分區與合計放 `lib/` 純函式 | 符合 |

---

## 7. 已不採

### 方案 C「兩隊並列守位表」

- 判斷依據：裁定 6309977252 ①「個人數值點開才看，避免過多數值」。
- 方案 C 的作法：每列都放個人「出賽／ERA／局數」或「該位出賽／OPS／AVG」，數值太多。
- 截圖：`350-assets/mockup-c-desktop-1280-pitchers.jpg`、`350-assets/mockup-c-desktop-1280-fielders.jpg`、`350-assets/mockup-c-mobile-390-pitchers.jpg`、`350-assets/mockup-c-mobile-390-fielders.jpg`
- 示意頁：`mockup-c.html`；產生器：`gen_mockup_c.py`、`derive_series_dh.py`（已移除，見 e86bb7a8）

### 方案 A「陣容對照表」、方案 B「組成摘要＋並列清單」

需求方 6309822733：「兩者的資訊剛好相反，剛好都缺失了點資料。」

| 方案 | 作法與缺點 | 截圖 |
|---|---|---|
| A | 兩隊並列，依角色列名牌，沒有數值 | `350-assets/mockup-a-desktop-1280.jpg`、`350-assets/mockup-a-mobile-390.jpg`、`350-assets/mockup-a-mobile-390-fielders.jpg` |
| B | 人數長條加名單表，名單沒有依位置對照 | `350-assets/mockup-b-desktop-1280.jpg`、`350-assets/mockup-b-mobile-390.jpg` |

產生器：`gen_mockups.py`（已移除，見 e86bb7a8）。

### 現況難讀的證據（仍然成立）

- 截圖：`350-assets/current-desktop-1280.jpg`、`350-assets/current-mobile-390.jpg`
- 預設只顯示一隊；選「全部」後，第二隊在第一隊下方 1,539px 才開始。
- 沒有隊級的組成資訊。
- 390 寬時，4 組控制項各占一列。
- 只看一隊就有 4,759px 高。
