# GAME-RECAP-WP-VAL1-FIX1 Errata — E scope 誤標與訓練 proxy 修正

> 修正對象：[`GAME-RECAP-WP-VAL1_RESULTS.md`](GAME-RECAP-WP-VAL1_RESULTS.md) 的 E scope 標籤語意與 proxy。
> 原 artifact `game_recap_wp_val1_metrics.json` **未改動**（已查核交付）；修正後重跑落
> [`game_recap_wp_val1_fix1_metrics.json`](game_recap_wp_val1_fix1_metrics.json)。
> A／C／D scope 的程式路徑、已發布結論與 v2 門檻一律未動。

## 1. 缺陷內容（DOC-TESTING-GLOSSARY1 實證發現）

| 項目 | 原（誤） | 修正後 | 佐證 |
|---|---|---|---|
| E scope 標籤 | 「二軍季後」 | **一軍季後挑戰賽** | DB 全史：E 共 40 場（1998–2025）、僅出現在半季冠軍歧異年份、主隊碼皆 `*011`（一軍實體）；二軍季後實為 F（103 場、`*022`，未納入驗證，已於 docstring 明文揭露） |
| 訓練 proxy | `{"E": "D"}`（二軍例行分布） | `{"E": "A"}`（一軍例行分布） | 季後 proxy 原則＝借**同軍**例行賽；已抽出 `TRAIN_PROXY` 常數＋測試釘住 |
| E ruleset | `RuleSet(15, 10 if year>=2025 else None, False)`（借二軍 2025 突破僵局） | `RuleSet(20, None, False)`（同 C 的一軍季後語意） | 實證：全史 E 僅 2025 #4 超過 9 局（10 局），該局上半 livelog `first/second_base` 皆空＝**空壘開局，無突破僵局跑者**；E 無和局（0 場平手）。cap 15→20 無可觀測影響（無場次超過 10 局） |

## 2. E scope 修正前後對照（pooled walk-forward，n_pa=988／13 場）

| 指標 | 原（proxy D） | 修正後（proxy A） | v2 門檻 |
|---|---|---|---|
| Brier | 0.15452 | **0.14928** | 每季勝主場常數基準 |
| ECE（weighted） | 0.10054 | **0.08536** | proxy 池化 ≤ 0.05 |
| E2025 Brier vs 主場基準 | 0.28928 vs 0.25045（敗） | 0.28886 vs 0.25289（敗） | 須勝 |
| **verdict** | **unsupported** | **unsupported** | — |

- 修正讓校準指標一致性改善（proxy 換對母體），但**兩條硬性門檻仍未過**：E2025 Brier 輸主場常數基準、池化 ECE 0.08536 > 0.05。
- **結論不變：E scope unsupported**——與缺陷版判定相同，本卡不改變 WP-VAL1 的任何 Go/No-Go 結論，僅修正語意標籤、proxy 母體與規則邊界的正確性。逐季 v1 點估計 ECE 全數改善（0.206/0.197/0.216/0.217 → 0.181/0.192/0.196/0.221）供稽核參考，不作支持證據。

## 3. 重現

```bash
uv run python -m cpbl.models.winprob_val --kinds E --out <scratch>/e_rerun.json   # host 即可，全程唯讀
uv run pytest tests/test_winprob_val.py -q                                        # 14 passed
```

先紅後綠：對缺陷版（stash 修正後）跑新測試 `test_ruleset_eras`（E 規則）與
`test_train_proxy_pairs_postseason_with_same_level_regular` → **2 failed**；修正版全綠。

- 執行：Claude Fable 5@Claude Code（GAME-RECAP-WP-VAL1-FIX1）；查核：跨模型家族（T4 統計紅線）。
