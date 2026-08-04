# DEV-REVIEW-DEACCEPT-TRAIL1 plain-review 翻案缺 correction 留痕〔T3〕

- 需求：ruan6047（WF-21 iteration 3 查核 finding WF21-R-13 轉開）　規劃：待指派　分支：未認領
- 執行：待指派　查核：待指派（≠ 執行者）
- Initiative：—　spec 基線：WF-21 canonical `templates/review-escalation.md`（ai-workflow b113617）
- DB：`none`
- 部署：否　環境：—　PR：—　Merge SHA：—

## 問題

`scripts/workflow_ledger.py` 的 `_apply_finding_state` 由 review 與 `review-correction` 共用：普通 review 事件跨 attempt 把先前已採認的 open finding 重新列為 `accepted=false`（或降級 `blocking`／分類），即會把它移出有效 open set、消除後續 unresolved carry，全程無 `review-correction` 留痕。canonical §2 規定「若事後翻案，以 `review-correction` 追加新 disposition」。相同終態經 `review-correction` 通道完全合法（WF21-R-10 修正本身），故**不構成新的規避能力**，僅是翻案軌跡（`target_attempt_id`／`finding_updates`）完整性缺口。

## 驗收條件

- [ ] review 事件中對「已在有效 open set 的 finding」的 `accepted`／`blocking`／`finding_class` 降級，被偵測並 fail loud（視為 pending conflict 要求 `review-correction` 裁決）；或需求方裁定改走 canonical 明文化「review 通道降級為合法翻案模式」，二擇一定案。
- [ ] finding 首次出現於該 attempt 且 `accepted=false`（尚未採認的新報告）不受影響。
- [ ] 既有 WF-21 契約測試與反例（withdrawn／resolved／carry／checkpoint）全數維持綠。
- [ ] 若走守衛路線：新增紅測試釘住「plain-review 降級 → fail loud」與「correction 通道降級 → 合法」對照。

## 驗證

- [ ] `uv run pytest -q tests/test_workflow_ledger.py tests/test_review_prompt.py`
- [ ] `uv run python scripts/workflow_ledger.py --check`
- [ ] `uv run ruff check`

## Log

- 2026-07-31：由 WF-21 iteration 3 跨家族查核（Claude Fable 5）finding WF21-R-13（minor、non-blocking）轉開；證據與重現腳本見 WF-21 查核報告（探針 P7）。
