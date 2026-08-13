# DOC-CPBL-ROADMAP1 建立 CPBL 藍圖：目標排序、任務線與卡片執行規範　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：Claude Fable 5@Claude Code (PM)　查核：待指派
- Initiative：—　spec 基線：ai-workflow/docs/ROADMAP.md @ 71df157（§0 開卡前檢查／§4 驗收政策／§5 finding 分流，本卡引用不複述）＋ cpbl docs/PRODUCT_UX_BLUEPRINT.md v0.2 @ cc7d81e（產品面，本卡劃界不覆蓋）
- DB：db_scope=none
- 服務的原始目標：卡片的取捨與排程要有唯一依據，而不是靠開卡當下的印象
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DOC-CPBL-ROADMAP1），不重複於此檔。

## 核心痛點

- **痛點**：CPBL 側 39 張未結案卡沒有「這張卡在解決什麼問題」的唯一依據：既有 PRODUCT_UX_BLUEPRINT.md 寫的是產品長什麼樣，不管卡片取捨；ai-workflow/docs/ROADMAP.md 只管 ai-workflow。後果實測可見——三張在途卡分別停滯 5／6／8 天無人察覺（#119 認領後零事件、#53 派了審 8 天沒人接、#79 等部署驗證 6 天）；OPS-REMOTE-* 四張與 ML-WP-* 三張長期躺著而沒有人能說出它們到哪算完成；2026-08-08 由查核者 disposition 直接開卡（#120），沒有任何一步問過這件事在整體規劃裡的位置

## 驗收條件

- [ ] §0 目標排序寫成需求方 2026-08-13 裁定的四級：不出錯 > 不退化 > 看得懂 > 深度，每級附「怎樣才算達成」的判準；判準須是可判定的，不得寫成態度宣示
- [ ] §1 定義五條任務線並沿用 Project 既有 initiative 欄（不發明新欄位）；每條線必須寫出「何時算完」，寫不出來的線要標記為此狀態而非略過
- [ ] §2 執行規則四條：每線 WIP=1；完成時間從認領起算逾 3 天觸發強制重新檢視需求（不自動退，由需求方裁去留）；執行者四種停下回報情形；開新卡須引母卡「服務的原始目標」原文並確認母卡仍成立
- [ ] §2.1 過渡條款：欄位要求只對新卡強制，舊卡於逾時重新檢視觸發時以 Issue comment 補記；須寫明漸進的理由是 wfcli 無開卡後欄位更正能力（ai-workflow#12），一次補 39 張在現行工具下做不到
- [ ] §3 只填分線（機械事實），去留欄一律留白交需求方裁定；表頭須註明「線別為藍圖分派、非 Project 欄位，兩者可不同步」
- [ ] §4／§5 引用 ai-workflow ROADMAP 對應節次，不複述其內容與數字（避免兩份文件漂移）
- [ ] 不得修改任何現有卡、不得裁定任何卡的去留、不得改動 PRODUCT_UX_BLUEPRINT.md

## 驗證

- [ ] 39 張未結案卡逐張可歸入五條線之一，無遺漏無重複；歸屬清單由指令輸出產生而非人工列舉
- [ ] 以本專案已發生的真實事故回放檢驗規則可執行性：分項誤計 83 筆、覆蓋告警響兩個半月無人讀、weekly 排程交付後從未掛上、D/97 續賽後 PA 衍生表未重建——逐件說明藍圖的哪一條會接住它，接不住的要誠實標記
- [ ] uv run ruff check 與 uv run pytest 不受影響（本卡純文件）；須說明為何不需新增測試
