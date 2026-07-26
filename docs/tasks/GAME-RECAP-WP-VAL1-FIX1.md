# GAME-RECAP-WP-VAL1-FIX1 修正 E scope 誤標與訓練 proxy 〔T4；🔴統計〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：`ai/fable-5/GAME-RECAP-WP-VAL1-FIX1`（卡族共用 WP-VAL1 原 worktree）
- 執行：Claude Fable 5@Claude Code（建議 L4；統計正確性）　查核：待指派（跨模型家族或人工；須 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`read`（全程唯讀；重跑 artifact 落新路徑）
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：碼已進 main 的事後修復（canonical §3 `<原卡>-FIX<n>`）。DOC-TESTING-GLOSSARY1 以 DB 全史實證發現：`models/winprob_val.py` docstring 將 scope 標為「C 一軍季後／E 二軍季後」且 `train_kind {"E": "D"}` 用二軍例行當 E 的訓練 proxy——實證 E＝**一軍季後挑戰賽**（1998 起 40 場、僅半季冠軍歧異年份、主隊碼 `*011`）、二軍季後＝F（未納入驗證）。修正：
  1. docstring scope 標籤改為實證語意（C＝一軍總冠軍賽、E＝一軍季後挑戰賽）；F 未驗證明文揭露。
  2. `train_kind` E 的 proxy 改 `A`（一軍例行）；資料載入條件同步。
  3. `ruleset_for("E")` 的 `tiebreak_from=10（year≥2025）` 是借二軍規則的假設——以 E 場次 livelog **實證重推**（比照 C 的 non_pa_tiebreak 檢法）後定案。
  4. E scope 以修正後 proxy 重跑 walk-forward，artifact 落新路徑；errata 併列新舊結果。
  5. `docs/reference/GLOSSARY.md` kind_code 條目的 ⚠️ 不一致註記改指向本卡修正。
- Discovery：DB 實證見 GLOSSARY「kind_code」條目（DOC-TESTING-GLOSSARY1 交付 b214418）
- Design：Design Gate N/A；統計 harness 修正，不動 public API／UI

## 紅線（違反即退回）

1. **只修 E scope 與標籤**：A／C／D 的已發布結論、v2 門檻、訓練管線一律不動；diff 逾越即退回。〔statistical-redline #4 #6〕
2. **E 重驗嚴格沿用 WP-VAL1 v2 門檻與 walk-forward 窗口**（proxy scope 訓練窗含當年例行季仍屬時間外，season 開打前例行季已完賽）；結論按門檻判定，**不得因「修正後較合理」放行**——預期仍 unsupported（n=40、每季 3–5 場）。〔#1 #4〕
3. **規則邊界只認實證**：E 的和局／突破僵局設定以 E 場次 livelog 重推（tiebreak 州出現與 non_pa_tiebreak 計數），不得沿用「二軍規則」假設，也不得未經實證改抄 A／C 規則。〔#3〕
4. **原 artifact 不可覆寫**：`docs/research/game_recap_wp_val1_metrics.json` 是已查核交付；重跑一律 `--out` 新路徑，errata 併列新舊供對照。〔#8〕

## 驗收條件

- [ ] docstring／`train_kind`／載入條件三處一致修正；F 未驗證揭露入 docstring。
- [ ] E ruleset 實證重推留痕（E 場次 tiebreak 證據計數）。
- [ ] E scope 修正後 walk-forward artifact（新路徑）＋ errata（新舊並列、結論判定）。
- [ ] GLOSSARY ⚠️ 註記更新指向本卡。
- [ ] `tests/test_winprob_val.py` 不退化；如有 pin 舊映射的測試同步修正並說明。

## 驗證

- [ ] `uv run ruff check`＋`uv run pytest` 全綠；`uv run python -m cpbl.models.winprob_val --kinds E --out <scratch>` 可重跑（host 即可）。
- [ ] 跨家族 reviewer 重跑 E scope 並核對嵌套窗口與規則實證。

## Log

- 2026-07-26T18:05:00+08:00 register by Claude Fable 5@Claude Code（依 ruan6047 指示開卡並派工；源自 DOC-TESTING-GLOSSARY1 的 GLOSSARY 實證發現）。
