# ML-SIM1 獨立查核報告（🔴紅線：統計正確性）

- **查核者**：Claude Fable 5（`claude-fable-5`）@ Claude Code CLI —— 非 GPT／OpenAI 家族，符合跨模型家族限制
- **查核日期**：2026-07-15
- **查核對象**：worktree `/Users/ruanruan/Dev/cpbl-analytics-ML-SIM1`，分支 `ai/gpt-5-codex/ML-SIM1`，HEAD `7da3825147837ab2aba2ee9bfaf911e60314cb4b`（與交接宣稱一致；base `f5e520a`，工作區乾淨）
- **實作者**：GPT-5@Codex

## Verdict：**FAIL（↩退回）**

模式 A（固定賽前勝負預測）**通過全部獨立驗證**：無資料洩漏、比較池一致、指標可獨立重算重現、bootstrap 與閘門方向正確。
模式 B（單一打席模擬）存在 **P0 資料重建缺陷**：PA snapshot 未過濾 `is_change_player`（換人宣告列），造成幽靈打席（結果掛錯打者）、狀態污染（出局數／壘況過期）與 deep-link 回傳錯誤打者；且覆蓋率稽核在結構上無法偵測此類問題（rebuild rate ≡ classification rate），「逐年 100%」是在被污染的分母上宣稱的。此為本卡紅線（統計正確性）之核心，故整卡退回。

---

## Findings

### P0-1｜PA 重建未過濾 `is_change_player`：幽靈打席、錯誤歸屬、狀態污染
- **位置**：`src/cpbl/models/pa_sim.py:325-340`（`load_pa_dataset` SQL）、`src/cpbl/models/pa_sim.py:379-394`（`load_game_pa_snapshot` SQL）、`src/cpbl/models/pa_sim.py:198-209`（`_group_events` 以 (inning, half, hitter) 分島，未排除換人列）
- **機制**：livelog 的換人宣告列（`is_change_player=true`）會帶 (a) **被換下場球員**的 `hitter_acnt`、(b) **下一位真實打者結果**的 `batting_action_name`（官方逐列回填 PA 終結動作）、(c) **過期的** `out_cnt`／壘況（常為上個半局終了狀態）。repo 既有同源程式（`winprob.py:64-65`、`winprob.py:246`）都明確過濾 `is_change_player`；`pa_sim.py` 沒有。
- **可重現證據**（2018–2025 kind A，本機 DB 實測）：
  - 稽核 PA 總數 181,842 vs 官方 box（`batting_gamelog`）加總 180,217：**每年多 148–261 個、共 +1,625**。
  - **幽靈島**（整島皆換人列、被誤計為 PA）**1,464 個**；island 首列為換人列（before-state 可疑）**23,072 個（12.7%）**。
  - **非半局結束但出局數倒退**的轉移 **11,340 個（6.2%）**。
  - **反事實**：加上與 `winprob.py` 相同的 `is_change_player`+`hitter_acnt` 過濾後重建 → PA 總數 180,377（與官方差 +160、0.09%），出局倒退降至 543（絕大多數集中 2019/2020）。
  - **產品可見症狀 1**：`GET /api/v1/outcome/plate-appearance?inning=9&half=2&bases=123&outs=1`（滿壘保送必然擠回致勝分）回傳 BB_HBP 再見機率 **0.9921 ≠ 1.0**；artifact kernel 內 `('BB_HBP','123',*)` 共 427 筆樣本含 **20 筆 runs_delta=0** 與多筆保送後出局數增／減的物理不可能轉移。
  - **產品可見症狀 2**：`GET /api/v1/outcome/plate-appearance/from-game?year=2026&kind_code=A&game_sno=3&main_event_no=720001000` 回傳 `available=true`，打者判定為 `0000006240`——該島是換人宣告列，**真實打者是代打 `0000007589`**，且 before-state 出局數 2（真實為 0）。違反 spec「無法唯一定位或資料不完整時回明確 error，不猜測」。
- **統計影響**：(1) empirical Bayes 的 hitter／pitcher／direct 計數含錯誤歸屬（被代打者吸收代打者的結果，集中在比賽後段高槓桿情境，偏誤非隨機）；(2) 轉移核與 leakage-safe run_dist 含 ~6%+ 的假轉移；(3) 走查指標（combined/transition/weighted-WP）train 與 test 同受污染，數字可重現但**母體本身錯誤**；(4) deep-link 契約被違反。
- **建議修正**：比照 `winprob.py`——分島／取 action 前排除 `is_change_player` 列與 `hitter_acnt` 為空列（比分累計仍可走全列）；修正後**全部指標、覆蓋率、artifact 重跑**，並將修正前後指標對照寫入留痕。

### P1-1｜「狀態重建率」與「分類率」在構造上恆等，覆蓋率閘門形同虛設
- **位置**：`src/cpbl/models/pa_sim.py:275-293`（`audit_pa_events`）、`src/cpbl/models/pa_sim.py:77-82`（兩個 rate 的定義）
- **機制**：`rebuilt = len(build_pa_snapshots(...))`，而 builder 只在「action 不可分類」或「終場無 final_score」時跳過；`load_pa_dataset` 永遠提供 final_score → **rebuild rate ≡ classification rate**。所謂「狀態重建 100%」不含任何狀態一致性檢查（出局單調、比分不倒退、PA 數對 box 對帳），P0-1 的 11,340 筆異常全數無感通過。無 action 的島（資料缺口）也被靜默剔出分母。
- **影響**：spec 要求「資料缺口、非單調 event fail-closed」實際上沒有兌現；「逐年 classification／rebuild 100%」的宣稱在審核意義上是空集合＝「用排除失敗列製造 100%」的變體。
- **建議修正**：加入獨立的狀態一致性稽核（半局內出局數不減、比分不減、換人過濾後 PA 數 vs `batting_gamelog` box 差 < 門檻）納入 `assert_audit_coverage` fail-closed；`runs_delta = max(0, ...)`（`pa_sim.py:260`）的負值 clamp 改為計數回報而非靜默吞掉。

### P2-1｜過濾後 2019/2020 仍殘留 ~500 筆出局倒退異常
- **位置**：資料層（`game_livelog` 2019/2020）；由 P1-1 的新稽核閘門承接
- **證據**：反事實過濾後 2019 剩 251、2020 剩 280 筆非單調轉移，其他年份 0–11 筆。
- **影響**：另有一類資料瑕疵（來源改版或早期爬蟲欄位語意）未被解釋；佔比 ~1.4%（該兩年）。
- **建議修正**：修復卡中逐例抽樣定性；無法修復者以 fail-closed 排除該 PA 並記錄於 coverage 報告，不得靜默入庫。

### P2-2｜weighted-WP 相對 current-WP 的改善量僅 0.00007，產品不得以「預測提升」包裝
- **位置**：`src/cpbl/models/pa_backtest.py:197-254`；TASKS log 已自陳「不放大解讀」
- **證據**：獨立重跑重現 weighted 0.1511 vs current 0.1512（在受 P0-1 污染的驗證目標上）。
- **判斷**：單打席模擬的產品價值在「各結果的機率×情境勝率拆解」（delta_wp 展示），非整場勝率預測力。前端／文案不得宣稱加權 WP 比現行 WP 更準；修正 P0-1 後需重測，若仍無實質差異，建議 API 文件明示「weighted 與 current 等效，僅供拆解展示」。

### P3-1｜TASKS.md 留痕誤記賽前走查期間為「2022–2026」
- **位置**：`docs/TASKS.md:149`
- **證據**：持久化 `model_versions(task='outcome_simple')` 與容器重跑皆為 **test_years=[2021..2025]**（符合 spec「最近 5 個完整賽季、2026 不列入正式驗收」）。程式正確、留痕錯誤。
- **建議修正**：改為 2021–2025。

### P3-2｜次要契約與工程備註（無阻擋，修復卡可順帶處理）
1. `src/cpbl/api/routers/outcome.py:184-197`：spec 的 `/plate-appearance` 「可選 cutoff」參數未實作（僅單一 artifact）；已回傳 `trained_through` 揭露，可接受但應在 spec 或 API 說明中明示。
2. `src/cpbl/api/routers/outcome.py:195,211`：artifact 檔**存在但損毀**時 `joblib.load` 直接 500，非乾淨 fail-closed 回應。
3. `src/cpbl/models/run_train_pa_sim.py:68-69`：正式 artifact 的 strength 只在寫死的 2 組候選中選（`(100,400,200)/(200,400,200)`），與走查用的 27 組 `DEFAULT_STRENGTH_GRID` 不一致；無洩漏，但屬未留痕的 ad-hoc 縮限。
4. `_pa_response` 未回傳 spec 說的 shrinkage weight（僅樣本數與 low_sample）；90% 區間為 normal approximation 啟發式（已標注方法），不得對外當正式統計信賴區間。

---

## Independent verification（獨立驗證紀錄）

**環境**：worktree `/Users/ruanruan/Dev/cpbl-analytics-ML-SIM1`（自備 `.venv`）；本機 PG localhost:5433；LightGBM 於容器（`docker compose run --rm --no-deps -e DATABASE_URL=...host.docker.internal:5433... api cpbl-train-outcome-simple`）。沙箱未阻擋 DB 連線，host pytest 無需重跑替代環境。

| 驗證 | 結果 |
|---|---|
| `uv sync --frozen` | OK |
| `uv run ruff check` | All checks passed |
| `uv run pytest` | **156 passed**（與宣稱一致；皆 synthetic/route snapshot，無 DB 依賴） |
| `.venv/bin/python -u -m cpbl.models.run_train_pa_sim` | 重現 combined LogLoss 1.4076／Brier 0.6811／ECE 0.0199、transition LogLoss 1.1573、next-WP MAE 0.0328、weighted 0.1511 vs current 0.1512（test 2021–2025, n=124,255） |
| 容器 `cpbl-train-outcome-simple` | 重現 fixed 0.612618／0.232037／0.656567／ECE 0.0290，baseline 0.528076／0.249372／0.691891，gate 7/7 PASS（test 2021–2025, n=1,585） |
| 獨立重算（自寫 SQL＋sklearn pipeline，fold 2025） | fixed Brier **0.22868**、baseline **0.24884**——與持久化 fold 值完全一致；定向後四係數皆為正、intercept 0.064（主場 ≈ +1.6% odds） |
| `model_versions` 直查 | `pa_sim`／`outcome_simple` payload 與宣稱逐項相符；paired bootstrap CI95 Brier [-0.02287, -0.01213]、LogLoss [-0.04742, -0.02327] 相符 |
| API 冒煙（TestClient） | from-game 2026/206 正常（機率總和=1、方向正確、low_sample 正確）；2025 歷史場 cutoff fail-closed；kind D 422；未見球員回退聯盟分布；artifact 缺失兩端點 fail-closed；`/pregame` 今日 3 場含 90% 區間；`/pregame/backtest` 揭露完整；API 全程唯讀 |
| 洩漏逐項檢查（B 節全項） | 聯盟先驗／posterior／strength 選擇／kernel／run_dist／訊號選擇／補值／scaler／bootstrap 皆僅用各 fold 訓練資料；無測試季校準器；閘門比 spec 更嚴（要求 CI 上界 ≤ 0）——**未發現洩漏** |
| 資料對帳（獨立 SQL） | livelog 覆蓋完成場 100%；**PA 數對官方 box 逐年 +148〜+261（P0-1 證據）**；反事實過濾後收斂至 +0.09% |

## Residual risks
1. **模式 B 全部數值指標須在 P0-1 修正後重跑才有意義**——目前 train/test 同源污染，指標「可重現」但不代表母體正確。
2. weighted-WP 改善量在雜訊水準（P2-2）；上 UI 時的文案紅線需由 UX 卡承接。
3. PA 不確定性區間（normal approximation）與賽前 bootstrap 區間（模型敏感度）皆非正式統計信賴區間，API 已標注方法，對外宣稱時不得升格。
4. artifact freshness：`/pregame` 服務舊 artifact 直到下次離線訓練通過閘門；官網 livelog 改版（換人列語意變動）會直接衝擊 PA 重建，修正時應把 box 對帳做成常態稽核。
5. 模式 A 樣本外泛化：nested 選訊號逐 fold 不穩（offense 群在 runs/OPS 間切換），屬已揭露的模型敏感度，非缺陷。

## Workflow handoff
- 依 AI_WORKFLOW §5：卡轉 **↩退回**，本報告為缺陷報告；由原執行者（GPT-5@Codex）於**同分支同 worktree** 修復後 re-submit 重審。
- 查核者未 merge、未部署、未刪除 worktree、未修改任何實作碼；僅新增本報告與 TASKS.md 留痕。

---

# 複查報告（Re-review，2026-07-16）

- **複查者**：Claude Fable 5（`claude-fable-5`）@ Claude Code CLI（原 reviewer，非 GPT 家族）
- **複查對象**：修復 commit `9b70150`＋留痕 `1231c2e`（HEAD `1231c2e` == origin 分支尖端，工作區乾淨）

## Verdict：**PASS（✅通過）**

## 原 findings 關閉狀態

| Finding | 狀態 | 獨立證據 |
|---|---|---|
| P0 `is_change_player` 污染 | **CLOSED** | `events_from_rows` 排除換人列與缺投打者列、比分仍走全列；獨立重算（自寫 grouping＋SQL）2,335 場、181,316 islands、180,377 可分類，**逐年逐位**與稽核一致；deep-link 2026/A/3/720001000 現回代打 `0000007589`／投手 `0000001821`／0 出局／空壘／PA 720003000–720005000，不再回被換下場的 `0000006240`；換人事件確定性映射同半局下一真實 PA，跨半局以 2018/33/1020020000 真實案例實測回 None fail-closed |
| P1 coverage 恆等 | **CLOSED** | 分母改為全部 islands（含無 action）；rebuild 由比分／出局／局序／滿壘強迫進壘獨立驗證，classification（99.22–99.67%）與 rebuild（99.21–99.65%）不再恆等；box 對帳（0.46–0.94%）納入 `assert_audit_coverage` 三重閘門（任一 >1% 缺口即 fail）；失敗列以 `state_errors` 逐類持久化且**確實排除於 snapshots／kernel**（builder `continue` 於 append 前）|
| P2 2019/2020 out_cnt | **CLOSED** | 根因獨立證實＝「投手牽制」control event `out_cnt=NULL`（2018/2019/2020＝21/1,843/1,921 筆，2021+ 為 0）；修復採同 PA 內第一個已知 out count（`_first_state_event` 僅限本 group，無跨 PA／跨半局回填）；殘留異常列入 state_errors 排除（2019 全類合計 22、2020 全類 18）；99% 門檻未調降 |
| P3 TASKS 年份誤記 | **CLOSED** | `docs/TASKS.md` 已改 2021–2025，與持久化 test_years 一致 |
| P3 artifact 損毀 500 | **CLOSED** | `_read_pa_artifact` 捕捉載入例外＋契約鍵檢查；live 實測損毀檔回 200＋`available=false`＋`pa_sim artifact 無法載入`；另有單元測試 |
| P3 strength grid 不一致 | **CLOSED** | 正式 artifact 改用 `DEFAULT_STRENGTH_GRID`（27 組）內層選擇，選出 (200,400,200) |
| shrinkage weight 缺失 | **CLOSED** | API `sample.shrinkage_weight` 回傳 hitter／pitcher／direct 三層權重；未見球員全為 0.0＋low_sample=true |

## 新增 findings
無 P0–P2。P3 備註兩則（不阻擋）：(1) box 對帳 SQL 未 join 完成場過濾，目前數值與 join 版完全一致，未來若 box 出現未完成場資料會使閘門偏嚴（fail-closed 方向，安全）；(2) `_first_state_event` 以 PA 內首個含 out count 事件錨定 before 壘況，若牽制前有盜壘會取到 mid-PA 壘況——2018–2020 抽樣皆為牽制（不改壘位），影響可忽略。

## 獨立驗證
- `uv sync --frozen`／`ruff` 全綠；`pytest` **163 passed**（新增 7 支，含損毀 artifact、換人映射、滿壘保送 invariant、box 對帳突變測試）。
- 重跑 `.venv/bin/python -u -m cpbl.models.run_train_pa_sim`：**完全重現**宣稱值——n_test 123,279；combined LogLoss 1.406731／Brier 0.680715／ECE 0.019798，league 1.421000／0.685257／0.025999；transition LogLoss 0.610516、next-WP MAE 0.034837；weighted-WP 0.151635 vs current 0.151727（複查重跑覆寫 model_versions 為 `pa-sim-1784131944`，指標同 `pa-sim-1784131303`）。
- **滿壘 BB/HBP invariant**：新 kernel「零得分且出局不變」= 0（污染版為 20）；殘留 2 筆「零得分且出局＋1」經原始 content 逐筆核實為真實事件（2018/100 周思齊三壘遭觸殺後打者補死球；2021/20 梁家榮遭觸殺〔重播輔助判決〕後完成故四）——修復未過度清洗合法轉移，也未把「滿壘四壞必得分」錯當硬規則。
- **transition LogLoss 下降機制分解**（fold 2025，舊碼 vs 新碼同法重算）：clamp（actual 不在 kernel）占比 0.230%→0.247% 幾乎不變、測試列僅少 0.76%；avg NLL 0.9567→0.5104 的下降來自**兩側污染清理後留存列機率集中**——非選擇性刪列、非洩漏；排除規則為物理一致性判準、與 outcome 無關、train/test 同套。
- Deep-link／cutoff／未見球員／損毀 artifact／唯讀性全數實測通過（詳上表）。

## 殘餘風險（維持不變）
weighted-WP 改善 0.000092 在雜訊水準——「僅供結果拆解、不得宣稱整場勝率預測提升」紅線由 UX 卡承接；PA 不確定性區間為 normal approximation、賽前區間為 bootstrap 模型敏感度，均非正式統計信賴區間；artifact freshness 依離線 CLI；官網 livelog 改版（換人列／control event 語意）會直接衝擊重建，box 對帳閘門現在能自動攔截此類回歸。
