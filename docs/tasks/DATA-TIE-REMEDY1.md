# DATA-TIE-REMEDY1 5 場隱形和局補救：取證＋判準修法（兩段式，鏈端等 G4 Phase B）　〔T4〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code（PM 祕書，依 AUDIT1＋三輪 Codex 處方）
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：AUDIT1 REPORT（a3b84b6）D1 節＋c233fp artifact
- DB：db_scope=write
- 服務的原始目標：資料正確性——完成場語意與官方一致，5 場和局資料入庫
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-TIE-REMEDY1），不重複於此檔。

## 核心痛點

- **痛點**：完成場判準 score>0 使 5 場真實 0:0 和局全庫不可見且自我隱蔽（AUDIT1 頭獎，standings.tie 7/7 對帳）；官方 box 存在性尚無直接取證

## 驗收條件

- [ ] 首步取證：Playwright 本機抓 5 場官方 box（單次嘗試/失敗冷卻 15-20 分/HTML+sha256+fetched_at 存證 docs/research/；至少 2 場成功才續行，全敗則停下回報改人工截證）
- [ ] additive migration：新表 cpbl.game_completion_evidence（year,kind_code,game_sno,evidence_kind,source_url,payload_sha256,approved_by,created_at；IF NOT EXISTS）——不改 games 既有欄
- [ ] canonical helper：is_completed_game 判準＝Codex 處方 SQL（日期界線最外層＋score>0 OR evidence 存在；present_status 不得單獨採信；0:0 無證據隔離）——新 helper 供非鏈消費端；refresh 鏈模組本階段不換（明寫 Phase 2 於 G4 Phase B 後執行，避免觀測污染）
- [ ] 非鏈消費端切換：features/outcome、API routers 等清點後改用 helper（逐點列表入交付）；5 場 evidence 列以需求方核准清單寫入
- [ ] 5 場核心資料補爬回填：box/livelog/scoreboard/gamelog 走既有單場路徑（2018-2025 歷史年不入當季 lagging 集合，鏈安全）＋canonical PA build 逐場；衍生表（splits/SABR 歷史年重建）只做影響評估交需求方裁定，不自動執行
- [ ] 四重回歸（語意斷言非字串比對）：5 場納入/standings 和局對帳仍 7/7/288 偽陽不誤納/未來日期保留賽仍排除
- [ ] **Phase 1b（2026-08-05 二次裁定翻案後）**：連段語意**維持原實作「和局中斷」**——PM 外部查證推翻首次裁定：官方連勝榜（twbsball 聯盟紀錄）15+ 條 break 全命中、2003 兄弟官方 9（skip 會是 12）、skip 虛構三筆官方榜不存在的歷史前三（1997 統一 13／1990 三商 12／2003 統一 11）；連敗側 2022 富邦「13 連不勝、一度 11 連敗追平隊史」＝break 精確重現（skip 會是 12 連敗破紀錄，查無此報導）。撤回 skip 語意 commit（af41dd6、57e7049），回歸測試改錨官方值：2003 兄弟連勝=9、2022 富邦連敗=11、1997 統一連勝=7（非13）、和局可見下 2023 統一連敗=4／富邦=7（Phase 1 首報的 5→4/8→7 即正確行為）；streak_impact.json 重定性為 skip 語意反證存證

## 需求方裁定紀錄（2026-08-05）

- **斷連語意（二次裁定，翻案）**：首裁「官方＝跳過」被外部證據推翻，**終裁「官方＝中斷」＝原實作正確**，AUDIT1 候選 4 撤銷缺陷定性；「連續不勝／不敗」是官方對跨和局段的另一獨立概念（可另提案為新指標）。順帶挖出兩筆資料側異常入提案清單：1991 兄弟官方 10 連勝 vs 我方 9（起點落在我方和局，疑早年缺場）、2018 Lamigo 我方 10 vs 官方榜 9。
- **衍生表重建（splits/SABR/RE/WP 矩陣、game_features 歷史年）**：**延後**，與 IBB 幽靈 281 席修復打包成單一「衍生層重建批次」卡（G4 穩定後排程），避免全庫矩陣重算兩次。本卡只交影響評估。
- **winprob 家族 4 消費點**：**定案保留舊判準**（既有紀錄可重現雜湊優先；影響量級 5/13,000 已記錄）——由「暫不切換」升格為定案，不再列待辦。

## 驗證

- [ ] 全部宣稱由指令輸出產生；詭異數據交人工判讀；新聞佐證通道可用（和局場次應有當日報導）
