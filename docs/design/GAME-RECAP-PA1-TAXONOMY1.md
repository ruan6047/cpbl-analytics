---
title: "GAME-RECAP-PA1-TAXONOMY1 canonical PA 狀態機 transition taxonomy"
card_id: GAME-RECAP-PA1-TAXONOMY1
status: awaiting-independent-review
taxonomy_version: 1.0.0
date: 2026-07-24
tags:
  - cpbl
  - game-recap
  - pa-taxonomy
  - data-correctness
links:
  - "[[GAME-RECAP-PA1]]"
  - "[[GAME-RECAP-PA1_CONTRACT]]"
  - "[[GAME-RECAP-DATA1]]"
  - "[[GAME-RECAP-PA1-EXPAND1]]"
  - "[[GAME-RECAP-PA1-BUILD1]]"
---

# GAME-RECAP-PA1-TAXONOMY1 canonical PA 狀態機 transition taxonomy

關聯：[[GAME-RECAP-PA1]]、[[GAME-RECAP-PA1_CONTRACT]]（§「PA 狀態機與穩定 ID」）、[[GAME-RECAP-DATA1]]、[[GAME-RECAP-PA1-EXPAND1]]、[[GAME-RECAP-PA1-BUILD1]]。

> [!info] 三份交付物
> 1. 本檔＝**規範文本**（狀態機、轉換 taxonomy、fail-closed、紅燈斷言）。
> 2. [`pa_transition_taxonomy.v1.json`](pa_transition_taxonomy.v1.json)＝**builder 可直接消費**的版本化輸出（`taxonomy_version=1.0.0`）。
> 3. [`../research/GAME-RECAP-PA1-TAXONOMY1_RESULTS.md`](../research/GAME-RECAP-PA1-TAXONOMY1_RESULTS.md)＝**自動產生的完整值域＋客觀效果證據**，供 reviewer 以原始事件複核。
>
> 三者皆由 `scripts/pa_transition_taxonomy.py`（唯讀）一鍵重跑產生。

## 0. 範圍與紅線

- **唯讀稽核**：`db_scope=read`。不物化 PA、不寫 DB、不加 migration、不改 ingest/API/前端。
- **本卡只定義 taxonomy**：實際 build/reconciliation/backfill 是 [[GAME-RECAP-PA1-BUILD1]]；additive schema 是 [[GAME-RECAP-PA1-EXPAND1]]。
- **不決定 WP/WPA/public API**。查核通過才解除 EXPAND1 的 transition schema 前置。
- **反名稱猜測（本卡最重要的紅線）**：每個 `action_name` 的語意**不得**由字面推斷。本 taxonomy 的每一筆分類都以「純 content 文字＋計數旗標」量測的客觀效果比率交叉驗證（見 §5、§8），reviewer 可據此 falsify。

## 1. 逐球/逐打席資料事實（已由證據確認，勿再猜）

以下為 `cpbl.game_livelog`（2018+，逐列＝一球或一事件）在本卡稽核中**實測確認**的欄位語意，是 taxonomy 的地基：

| 事實 | 證據 |
| --- | --- |
| `action_name` / `batting_action_name` 是**打席層級**值，**逐球傳播**到該 PA 的每一列（非只在終結列） | 任一 PA island 內每列 action 相同（§4 island 內同值） |
| `action_name` 表示該 PA 的**結果**；`batting_action_name` 為 `[守位][滾/飛/安/失…]` 縮寫 | 效果剖面 top batting_action 一致（RESULTS §action 剖面） |
| `pitch_cnt` 是**該投手當場累計球數**、**逐投手**，換投即重置 | 紅燈 (B)：陳思仲一個保送對兩位實投投手，pitch_cnt 各自從 1 起算 |
| `pitch_cnt` **非逐列唯一**：牽制/暫停/暴投列共用前一 `pitch_cnt` | 紅燈 (D)：1,236,594 個 `(game,pitcher,pitch_cnt)` 鍵中 65,954 個對到 2+ 列 |
| `is_strike` / `is_ball` **不**標記「擊入場內」的球（接觸列兩者皆 false）；不能當「是否有投球」的完備訊號 | §4 no-pitch 島含首球即擊出的 award/接觸 |
| `is_change_player` 列攜帶**傳播的 action** 與（代打時）**新打者**名；若不排除會製造**幽靈島** | 2018/A/4 含換人列時假象 3 島，排除後正確為各打者 2 島 |
| `is_special_event` 列＝打席**進行中**的跑壘/盜壘/牽制/失誤進壘（成員事件，非 PA 邊界）；可能造成局終截斷 | 紅燈 (C) 2026/A/76：朱育賢打席被二壘牽制第三出局截斷 |
| 空 `action_name` 列＝**截斷碎片**（打者未完成打席）或純跑壘殘列 | §4 分類 truncated_fragment/non_pa_running_fragment |
| **突破僵局上壘**＝延長賽突破僵局跑者放置規則，**非打席、無投球、無打者結果** | 效果剖面：batter_out/hit/walk/reach/scored 全為 0.000、avg_pitch=0.376 |

## 2. PA 狀態機（生命週期角色）

canonical builder 對每一 livelog 事件列（嚴格全序 `main_event_no::bigint`）指派一個**角色**：

```
                ┌─────────────── non-PA context ───────────────┐
                │  substitution announcement (is_change_player) │
                │  tiebreak runner placement (突破僵局上壘)      │
                │  pure running/timeout residue (空 action,0 球) │
                └───────────────────────────────────────────────┘
   PA_START ──▶ PA_MIDDLE* ──▶ PA_END(terminal action)  ──▶ completed_pa
       │            │
       │            └─(member) 換投/代打/跑壘/特殊事件：附掛，不另成 PA
       │
       └─(若被局終跑壘出局打斷且無終結 action) ──▶ truncated_fragment (非 PA)
```

| 狀態 | 機器可判定規則（row-level） | 產出 |
| --- | --- | --- |
| **PA_START** | island 的第一個**非換人**、具 `hitter_acnt` 的事件 | 開新 PA 種子 |
| **PA_MIDDLE** | 與 PA_START 同 island 的後續列（含投球、換投列、代打列、特殊事件列） | 附掛為成員事件 |
| **PA_END** | island 最後一個具**已登錄 `pa_terminal` action** 的列 | 終結，`result_action` 定案 |
| **NON_PA** | `is_change_player` 純換人殘列／`突破僵局上壘`／空 action 且無投球 | 不成 PA（context/ghost） |
| **UNKNOWN** | 非空 `action_name` 但未登錄於 taxonomy | **fail closed**（§7） |

## 3. Island 規則（PA 邊界）

**PA island ＝** 連續同 `(year, kind_code, game_sno, inning_seq, visiting_home_type, hitter_acnt)`、以 `main_event_no::bigint` 嚴格排序的最大連續段，**且計算邊界時排除 `is_change_player` 列**（換人列附掛於當前 PA，永不獨立 seed 或切割）。

理由與證據：

1. **同半局同棒次可二度上場**（大局打線輪轉）：必須用連續同 `hitter_acnt` island，不能用 `(inning, batting_order, hitter)` 去重——後者會吞掉第二次打席（紅燈 A/C）。
2. **打席中換投不切界**：一個打席跨多位投手仍是**一個** PA；`(inning, pitcher, hitter)` 會把它拆碎（紅燈 B）。
3. **換人列若不排除會製造幽靈島**：2018/A/4 含換人列時 `0000003336` 假象 3 島，排除後為各打者正確的 2 島。

## 4. Island 分類（fail-closed 分區，全史實證乾淨）

`scripts/pa_transition_taxonomy.py` 對 2018–2026、kind A/C/D/E 重建 island 後分類（RESULTS §island 分區）：

| 類別 | 判定 | 全史 island 數 | 語意 |
| --- | --- | --- | --- |
| `completed_pa` | 終結列 action ∈ taxonomy 且 `role=pa_terminal`（含無投球 award） | 328,283 | 真正的完成打席 |
| `truncated_fragment` | 空 action 但**有投球** | 1,737 | 打者被跑壘/局終出局截斷，**非** PA |
| `non_pa_tiebreak` | `突破僵局上壘` | 245 | 延長賽跑者放置，**非** PA |
| `non_pa_running_fragment` | 空 action 且**無投球** | 3 | 純跑壘/暫停殘列 |
| `unknown_action` | 非空 action 但未登錄 | **0** | fail-closed（目前 100% 覆蓋，無漏） |

> **無投球 award 的關鍵邊界**：`故意四壞球`（599 島，avg_pitch=1.85）與部分 `妨礙打擊` 是**零或極少投球的完成 PA**。以「有無投球」判 PA 會**錯殺**它們——故 `completed_pa` 的判準是「終結 action ∈ taxonomy」，不是「有投球」。

## 5. 轉換 taxonomy（action → 角色 → outcome_family）

完整 59 個 `action_name` 值域全部登錄；分類**由下表 outcome_family 指派、但由 RESULTS 的客觀效果比率驗證**（§8）。摘要：

| outcome_family | 代表 action（完整見 JSON/RESULTS） | 客觀驗證訊號 |
| --- | --- | --- |
| `out` | 三振、飛球接殺、刺殺、界外飛球接殺、野手接球自踩壘包、雙殺打*、內野高飛球、三殺打*、裁定三振、妨礙守備、跑離三呎線、違規被判出局… | `batter_out_rate` 0.96–1.00 |
| `hit` | 一/二/三壘安打、全壘打、場內全壘打、內野安打、場地安打 | `hit_rate` 0.99–1.00 |
| `walk` | 四壞球、故意四壞球、裁定四壞球 | `walk_hbp_rate` 0.98–1.00 |
| `hbp` | 觸身死球 | `walk_hbp_rate` 1.00 |
| `reach_on_error` | 接球失誤、傳球失誤、雙殺打上壘-失誤、犧牲*上壘-失誤 | `reach_error_rate` 1.00 |
| `fielders_choice` | 野手選擇、趁傳、犧牲短打上壘-野選、雙殺打上壘-趁傳 | `reach_error_rate` 高、`batter_out_rate` 0 |
| `sacrifice` | 犧牲飛球、犧牲界外飛球、犧牲短打* | `batter_out_rate` 0.99–1.00（打者出局、跑者進壘/得分） |
| `interference` | 妨礙打擊（打者獲上壘） | `batter_out_rate` 0、`hit/walk` 0 |
| `uncaught_third_strike` | 不死三振 暴投/捕逸/趁傳/傳球失誤/接球失誤 | 打者可上壘可出局，**語意混合** → 獨立家族，交由計數 delta 定案 |
| `non_pa`（`tiebreak_runner`） | 突破僵局上壘 | 全訊號 0.000（客觀確認非打席） |

> `uncaught_third_strike`（不死三振家族）是**唯一語意混合**族：打者可能上壘或出局，依捕手是否傳殺。本 taxonomy **不**替 builder 定案其 batter fate；builder 須以該 PA 的 `out_cnt` delta 與壘況變化決定，無法確認即 fail closed。這正是「不以名稱猜測」的落實。

## 6. 逐球映射的 taxonomy 約束（交給 BUILD1，本卡只定界）

- 逐球候選鍵**不得**只用 `(inning, pitcher, hitter)`。必須同時滿足 game key、投打身份、PA 事件區間、局/半局與球數單調序。
- `pitch_cnt` 逐投手且非逐列唯一：映射時須挑「真正投球列」（排除牽制/暫停/暴投殘列），且**逐投手**還原球序。
- 候選非唯一、球序倒退、投打不一致或 source revision 不一致 → `mapping_state=failed`（不得傳空陣列假裝無球）。

## 7. Fail-closed 行為（builder 必守）

| 情境 | 行為 |
| --- | --- |
| **UNKNOWN action**（未登錄，目前 0 例但須永久守門） | PA 標 `unreliable`：保留成員事件；WP/WPA 與逐球映射回 `null` + 明確 reason；**不得以名稱猜測補值** |
| **truncated_fragment**（空 action + 有投球） | 不產出 credited outcome；該打者留待下半局新 PA；其投球歸屬 `mapping_failed` |
| **non_pa_tiebreak / running_fragment / ghost** | 不成 PA；作為 inning context，不進 PA 分母 |
| **uncaught_third_strike** batter fate 無法由計數確認 | PA 終結但 `result_action` 標 `unreliable`；不強猜上壘/出局 |
| **歧義逐球鍵**（候選 PA > 1） | `mapping_state=failed`（紅燈 A/C 的同局重複投打即此類） |

## 8. 紅燈案例與斷言（reviewer 以原始事件複核）

全部由 `scripts/pa_transition_taxonomy.py` 重現；抽樣場次可逐列複核。

| # | 案例 | 抽樣 scope | 斷言（RESULTS 對照） |
| --- | --- | --- | --- |
| A | **同局同打者二度上場** | 2026/A/54（郭天信，12 分大局）；全史 20+ scope | island truth＝2 個不同 PA；`(inning,pitcher,hitter)` 三鍵合併 → `ambiguous_pitch_pas=2`；`run_dist` 較 canonical 少 3 |
| B | **打席中換投** | 2025/A/52（陳思仲一保送對 2 實投投手） | island truth＝1 個 PA；三鍵拆成多段；`pitch_cnt` 逐投手重置；`run_dist` 較 canonical 少 6 |
| C | **代打（換人成員事件）** | 更換代打列（cp=1）攜新打者名 | 代打天然為新 island（`hitter_acnt` 變）；換人列附掛不切界、不另成 PA |
| D | **跑壘特殊事件截斷打席** | 2026/A/76（朱育賢二壘牽制第三出局） | 打者 2 球後被跑壘出局截斷，空 action → `truncated_fragment`，非 PA、不產 outcome |
| E | **突破僵局跑者（特殊事件/非 PA）** | 2026/D/137 第 10 局 | `突破僵局上壘` 全客觀訊號 0 → `non_pa_tiebreak`；不進 PA 分母、無投球歸屬 |
| F | **pitch_cnt 非逐列唯一** | 全史 65,954 個多列 pitch 鍵 | 逐球映射須挑真正投球列，一個 pitch_cnt 可能對多列 |

近似鍵 PA 數對照（RESULTS §C，canonical＝本 taxonomy 完成 PA）：

| scope | canonical | run_dist | winprob | frontend | 誤配 |
| --- | --- | --- | --- | --- | --- |
| 2026/A/54 | 77 | 74 | 77 | 77 | run_dist −3（吞第二次打席） |
| 2025/A/52 | 82 | 76 | 82 | 82 | run_dist −6（換投場） |
| 2018/A/4 | 87 | 85 | 88 | 88 | winprob/frontend +1（幽靈/輪轉） |
| 2026/D/137 | 87 | 83 | 89 | 89 | 三套皆偏，且含 tiebreak 汙染 |

## 9. Builder 消費契約（版本化）

- builder 讀 [`pa_transition_taxonomy.v1.json`](pa_transition_taxonomy.v1.json) 的 `actions[]`：`action_name → {role, outcome_family}`。
- `island_rule`、`island_classes`、`fail_closed` 三段是 builder 必須實作的規則常數。
- **版本化**：`taxonomy_version` 遵循 semver。新增 action 值（官網新增賽況用語）＝ minor；改變既有 action 的 `role/outcome_family` 語意＝ major，並須重跑證據 + 重新查核。builder 必須 pin `taxonomy_version` 並在 build record 留痕。
- **未來覆蓋守門**：`unknown_action` 目前為 0，但 builder 不得假設恆為 0——遇未登錄 action 一律 fail closed 並告警，等 taxonomy bump。

## 10. 重跑

```bash
uv run python scripts/pa_transition_taxonomy.py \
    --from-year 2018 --to-year 2026 --kind A --kind C --kind D --kind E \
    --json docs/design/pa_transition_taxonomy.v1.json \
    --output docs/research/GAME-RECAP-PA1-TAXONOMY1_RESULTS.md
```

不變量測試：`uv run pytest tests/test_pa_transition_taxonomy.py`（值域覆蓋、非 PA 客觀零訊號、island 分類守門、無強矛盾）。

## 11. 交接

- 通過跨模型家族或人工 reviewer（以原始事件複核抽樣 + 完整值域）後，解除 [[GAME-RECAP-PA1-EXPAND1]] 的 transition schema 前置。
- EXPAND1 依 §9 契約把 taxonomy 落成 additive schema；BUILD1 依 §2–§7 實作 state machine 並在缺陷版本先跑紅（§8 斷言）。
