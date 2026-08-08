-- BOX-REVISION-R1-001（跨家族查核 blocking finding，iteration 4）：071 的
-- UNIQUE(year, kind_code, game_sno, pitcher_acnt, content_hash) 是**全域**內容
-- 去重，不是「與最近一次觀測比較」。後果：A→B→A 這種回改（聯盟推翻後又推翻
-- 回來，或抓取瞬間看到中間態）第三次觀測的 content_hash 會撞回第一次那列，
-- ON CONFLICT 只會把它當成「重複」+seen_count，B→A 這次真實發生的改判會直接
-- 消失在快照裡——而「能不能數出改判次數」正是本卡存在的唯一理由。
--
-- 修法：拿掉這個全域 UNIQUE。「只與該 (場,投手) 最近一次觀測比較」的去重邏輯
-- 改由寫入端（cpbl.ingest.box_revisions.record_box_pitching_revisions）用
-- 「INSERT ... WHERE NOT EXISTS（該 PK 最近一列 content_hash 相同）」的寫入
-- 語句保證，不再由 DB 約束提供——DB 只保留 append-only 的寫入權限，不對「這列
-- 算不算重複」有意見，語意判斷交給應用邏輯（見該函式 docstring 的併發假設）。
--
-- 只做 additive／drop 舊約束；不新增資料行為以外的表結構、不改 071 既有欄位。
ALTER TABLE cpbl.box_pitching_revisions
    DROP CONSTRAINT IF EXISTS box_pitching_revisions_year_kind_code_game_sno_pitcher_acnt_key;

COMMENT ON TABLE cpbl.box_pitching_revisions IS
    'DATA-BOX-REVISION-SNAPSHOT1：官方 box 逐場逐投手 append-only 快照。'
    '去重只比較「該 (year,kind_code,game_sno,pitcher_acnt) 最近一次觀測」，'
    '不是全域內容去重（BOX-REVISION-R1-001 修正，072）——冪等由寫入邏輯'
    '（INSERT ... WHERE NOT EXISTS 最近一列同 hash）保證，非 DB UNIQUE 約束。'
    '只從上線日起累積；2018-2026 既有歷史場次無回溯快照，不能回答「這些場過去被改過嗎」。'
    '零觀測不代表官方沒有改判——只代表在部署後、當前抓取窗口內沒有觀測到（見 AI_RUNBOOK.md）。';
