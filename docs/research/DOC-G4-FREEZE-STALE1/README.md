# DOC-G4-FREEZE-STALE1 掃描 artifact

`scan.json` 是全庫 G4 觀測凍結相關陳述的逐行盤點與判定；由同目錄的
`scan_g4_freeze.py` 產生，禁止手改。

```bash
uv run python docs/research/DOC-G4-FREEZE-STALE1/scan_g4_freeze.py
uv run python docs/research/DOC-G4-FREEZE-STALE1/scan_g4_freeze.py --verify
```

掃描涵蓋所有 Git 追蹤檔，但排除本 artifact 目錄以避免掃描器與輸出對自身產生自指。
每筆命中皆有 `disposition` 與 `rationale`；`needs_pm_followup` 表示本卡寫入集外、需由
PM 判定是否另開卡的現行用詞。
