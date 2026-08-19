# 模型路由（可替換操作知識）

> 本檔是本專案的模型選擇事實來源；協作流程鐵律見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。模型名稱與可用性會變動，執行前以當前工具可選清單為準；不得以 `latest` alias 作為自動化依賴。

| 層級 | 適用 | 本專案慣例 |
|---|---|---|
| L1 經濟型 | 格式、文件搬移、驗證、爬蟲與同步 | Haiku 或等價 deterministic automation |
| L2 主力型 | 已知模式的 API／前端／遷移與一般 review | Sonnet 或等價主力模型 |
| L3 高階型 | 跨模組取捨、未知根因、架構與官網逆向 | Opus 或等價高階模型 |
| L4 特殊型 | 統計／ML 正確性、新演算法、難以察覺的決策 | Fable 或等價 frontier 模型；不取代跨家族／人工查核 |

> **⚠️ L4「特殊型」是文件層概念，不是第四個能力層級——卡面不得填。**
> （需求方 2026-08-19 裁定選項 C，`DOC-ENTRY-ROUTING1` #140。）
>
> `wfcli` 的 `CAPABILITY_TIERS` 只有**三層**：`經濟型`｜`主力型`｜`高階型`。實測 `wf_cli.card`：
> `wfcli open` / `assign` 的 `--exec-capability` argparse `choices` **直接拒收** `L4`（`SystemExit 2`）；
> 合規格式的卡面把層級寫成 `L4` 時 `compare_capability_to_card` 回 `outcome='ambiguous'`，
> detail 為「執行建議層級 'L4' 不在 MODEL_ROUTING.md 語彙 ('經濟型', '主力型', '高階型') 內」。
> 連帶：`L1`–`L3` 加上 `L` 編號寫進卡面同樣回 `ambiguous`——**卡面只認裸層級名**（見 [`TEMPLATES.md`](TEMPLATES.md)）。
>
> **規劃時判為 L4 怎麼寫**：卡面層級欄填 **`高階型`**，並在**理由欄註明「統計／ML 正確性」**
> （或該卡實際觸發 L4 的原因）。上表第 4 列保留，因為它承載的判準——統計／ML 正確性、
> 新演算法、難以察覺的決策應派 frontier 模型且**不取代跨家族／人工查核**——仍然有效，
> 只是它表達的是**風險判準**，不是 CLI 可填的值。
>
> 裁定理由：改動最小且不丟語意；「下一張卡又寫一次 L4」的痛點已由 `TEMPLATES.md`
> 明列卡面可填值大幅削弱。

## 路由規則

- 先依風險決定能力，再選供應商；紅線卡的 review 必須跨模型家族或人工。
- 答案唯一且可沿用既有模式時降級；跨檔、不可逆或錯誤難察覺時升級。
- LightGBM、資料庫 schema／資料 migration、Marcel baseline 與賽果／球員統計結論屬紅線；執行與 review 皆需實測證據。
- 部署、migration 轉態與格式檢查優先 deterministic automation；異常且根因不明時升至 L3。
- 每次對話開頭標示建議層級與原因；實際模型切換由使用者決定。

## 路由決定於規劃期（WF-17，canonical `MODEL_ROUTING.md`）

- 開卡／Plan Gate 時規劃者**必填**建議執行與查核層級＋理由，寫在卡面「執行／查核」行。**範例（層級欄只能是裸層級名）**：`執行：待指派（建議 高階型；統計／ML 正確性）`——這正是上表 L4 判準對應的寫法；紅線卡查核欄必標「跨家族或人工」。
- 卡面引用**層級**而非模型名——名單會過期，層級是穩定介面。⚠️ 但**卡面能填的只有裸層級名 `經濟型`｜`主力型`｜`高階型`**；`L1`–`L4` 是上表的文件層編號，寫進卡面一律被 `compare_capability_to_card` 判 `ambiguous`（見表下裁定區塊與 [`TEMPLATES.md`](TEMPLATES.md)）。
- 建議反映**任務風險**，不得因當下額度預先降級；派工時可依可用性偏離建議，但實際模型與偏離理由記入 claim event 的 evidence（先例：2026-07 執行者家族週限）。
