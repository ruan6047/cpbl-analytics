# OPS-REMOTE-CRAWL1 核可契約與 Discovery Gate 決策

> 本檔是 OPS-REMOTE-CRAWL1（T3 Discovery umbrella）的**交付物**：把已核可的 Discovery
> brief（[`OPS-REMOTE-CRAWL1.md`](OPS-REMOTE-CRAWL1.md)）與研究計畫
> （[`../research/OPS-REMOTE-CRAWL1_PLAN.md`](../research/OPS-REMOTE-CRAWL1_PLAN.md)）收斂為
> 子卡可直接實作／執行的**契約**與**Gate 決策**。事實層以
> [`../CPBL_SITE_MAP.md`](../CPBL_SITE_MAP.md) 為準；本卡不寫 probe code、不寫 DB、不跑 live probe。
>
> 對應 canonical 流程：本檔即 Discovery Gate 的決策依據（[`../../.ai-workflow/AI_WORKFLOW.md`](../../.ai-workflow/AI_WORKFLOW.md) §3）。
> 狀態：待 ≠ 執行者之獨立 T3 查核；shadow worker／cutover 之 GO 另待需求方 sign-off。

---

## 0. 範圍與非目標（重申紅線）

- **本卡交付**：核可 (1) 安全 probe contract、(2) 候選路線＋取樣＋停止條件＋證據強度、(3) Gate 決策。
- **本卡不做**：不寫 probe code（切 `OPS-REMOTE-PROBE1`）、不執行 live probe（切 `OPS-REMOTE-ROUTE1`
  且每次 live 需 Coordinator 明確授權）、不建 shadow worker（切 `OPS-REMOTE-WORKER1`）、不 cutover。
- **不可逾越**：不部署遠端排程、不繞過／不嘗試解 HiNet challenge、不採購或接入代理、不偽造身份、
  不連續重試、不改 production 資料管線、不宣稱單次成功＝長期可靠。

---

## 1. 安全 Probe Contract（核可 → `OPS-REMOTE-PROBE1` 實作）

`OPS-REMOTE-PROBE1` 交付一支 **opt-in DEBUG CLI**，唯一職責是**分類單一公開入口的可達性**，
不做資料擷取、不重建 token/AJAX 流程。以下為本卡核可、實作卡不得放寬的邊界。

### 1.1 觸發與預設（opt-in）

| 規則 | 內容 |
|---|---|
| 預設關閉 | 無環境旗標時 CLI 直接拒絕執行並回非零；不建立任何公開 HTTP debug endpoint。 |
| 明確啟用 | 僅接受明確 opt-in 旗標（如 `CPBL_PROBE_ENABLE=1` + `--i-understand-single-shot`）。 |
| live 授權 | 對真實網路發話**每次**另需 Coordinator 明確授權；預設 transport 為 fixture（見 §1.5）。 |
| 交付形態 | 本機 CLI 或受保護 CI artifact；輸出 sanitized JSON 到 stdout／檔案，不入 DB、不入 repo。 |

### 1.2 Allowlist（僅既有公開入口；grounded in CPBL_SITE_MAP §4/§4b）

只允許對下列**已知公開頁面**發 **單一 GET**。禁止 POST、禁止 AJAX action 端點、禁止
帶 token、禁止自動展開或發現新路徑。

| host | 允許的 probe target（GET） | 用途 |
|---|---|---|
| `www.cpbl.com.tw` | `/schedule` | 主站 challenge/redirect 行為的代表入口 |
| `www.cpbl.com.tw` | `/robots.txt` | 已知會被挑戰以 307 擋（redirect 行為對照） |
| `stats.cpbl.com.tw` | `/api/proxy/v1/players/logs`（無參數探活） | 進階站公開 JSON API 可達性對照（無挑戰基準） |

> allowlist 以**常數清單**寫死於程式；新增目標須改本契約並重新核可，CLI 不得由參數任意指定 host。
> 每個 target 每次 run **最多一請求**；`schedule` 與 `logs` 用於區分「主站挑戰態」與「站台整體可達態」。

### 1.3 單次／零重試／零 DB

- **單次**：每 (route × target) 每次 run 只發一個請求；無分頁、無跟進、無 retry loop、無 backoff 重打。
- **失敗即止**：任何非成功狀態一律**記錄後結束**該 target，不重試、不升級請求頻率。
- **零 DB**：不連線 local／production DB，不寫 `refresh_log` 或任何表（`db_scope=none`）。
- **冷卻遵循**：跨 run 冷卻是操作紀律，不是 CLI 自癒；CLI 不得內建跨 run 自動重跑。

### 1.4 Sanitized 輸出 schema（redaction 白名單）

輸出**只允許**下列欄位；任何未列欄位一律不輸出。實作須以 fixture 證明敏感值被移除。

```jsonc
{
  "schema_version": "1",
  "probe_id": "uuid4",              // 本次 run 隨機
  "route": "vps_direct | tw_egress | residential",   // 出口標籤，不含 IP
  "target_host": "www.cpbl.com.tw", // allowlist 內固定值
  "target_path": "/schedule",       // allowlist 內固定值
  "requested_at": "ISO8601",        // 到分鐘即可，避免精細指紋
  "outcome": "reachable | challenge | redirect_loop | ip_blocked | transient | error",
  "http_status": 200,               // 整數或 null
  "redirect_count": 0,
  "latency_ms": 0,
  "tls_ok": true,
  "body_signature": {               // 僅結構訊號，不含正文
    "bytes": 0,
    "looks_like_challenge": false,  // 由固定啟發式判定（見 §1.6）
    "content_type": "text/html"
  },
  "notes": "free text，禁止含敏感值"
}
```

**強制 redaction（絕不輸出）**：`Cookie` / `Set-Cookie`、`Authorization`、任何 token
（`RequestVerificationToken` 等）、完整 client IP、完整 URL query secret、回應正文本身、
使用者 profile 路徑。輸出前以 allowlist 過濾，非黑名單過濾（預設拒絕）。

### 1.5 Fake-transport 契約（fixture-first，先於任何 live）

- 提供 `--transport=fixture|live`，**預設 fixture**。fixture 以錄製／構造的假回應涵蓋六種
  outcome，證明：(a) no-retry、(b) 每種 outcome 分類正確、(c) redaction 生效、(d) 兩出口
  （local/VPS）產出**同一 schema**。
- 契約測試須先對「未 redact／會 retry」的缺陷版本跑紅（canonical §2.6：不可偽造測試證據）。
- 只有 fixture 全綠 + Coordinator 授權後，才可 `--transport=live` 發單次真實請求。

### 1.6 失敗分類 taxonomy（grounded in CPBL_SITE_MAP §5）

| outcome | 觀測訊號（實測依據） | 意義 |
|---|---|---|
| `reachable` | HTTP 200 且非挑戰頁指紋 | 該出口對該 target 當下可達 |
| `challenge` | 428，或 200 但正文含 HiNet 挑戰指紋 | 反爬挑戰生效（純 httpx 主站典型） |
| `redirect_loop` | `ERR_TOO_MANY_REDIRECTS` / redirect_count 超閾 | 深度封鎖／壞 cookie（§2 深度封鎖狀態） |
| `ip_blocked` | 404（機房 IP 特徵） / 連線層拒絕 | VPS 機房 IP 被擋（§5「VPS 上全部 404」） |
| `transient` | timeout / 5xx / TLS 暫時失敗 | 暫時性，不等於封鎖，不得據此重打 |
| `error` | 前述以外 | 待人工判讀 |

> 分類為**唯讀啟發式**：偵測到 `challenge`/`redirect_loop` 只記錄，**不得**視為可繞過目標。

### 1.7 威脅邊界（probe 本身的風險）

- probe 也算打站：`challenge`/`redirect_loop` 出現後，該出口該時窗最多再探 1 次即停（§2 紅線）。
- 不得以 probe 頻率逼近爬蟲；跨 run 冷卻由 `OPS-REMOTE-ROUTE1` 的取樣設計約束（§2.2）。

---

## 2. 候選路線／取樣／停止條件／證據強度（核可 → `OPS-REMOTE-ROUTE1` 執行）

### 2.1 候選路線（三選一，事實與現況）

| 路線 | 定義 | 現有證據（CPBL_SITE_MAP / RUNBOOK） | 合規／成本風險 |
|---|---|---|---|
| `vps_direct` | 現有 VPS 機房 IP 直連 | 主站 404（機房 IP 被擋）；進階站待驗 | 低成本；主站可靠性存疑 |
| `tw_egress` | 合規台灣出口（如自有台灣節點；**非**購買住宅代理） | 專案內尚無實測 | 須另查服務條款與資料處理邊界 |
| `residential` | 現行台灣住宅 Mac worker（遠端控制／監測化） | Playwright 平時可過、深夜加嚴；Mac 為單點故障 | 維護成本／單點；不共享住宅憑證 |

> **明確排除**：購買住宅代理、challenge 繞過、共享住宅憑證 —— 不在授權範圍（rollout Notes）。

### 2.2 跨時窗取樣設計

- **維度**：route ∈ {vps_direct, tw_egress, residential} × target ∈ allowlist × 時窗。
- **時窗**：至少涵蓋「白天非加嚴」與「深夜加嚴」兩態（§2 實測：兩態行為不同），分離時窗執行。
- **頻率上限**：每 (route × target × 時窗) 每次授權**最多一請求**；不同時窗之間**強制冷卻 ≥ 20 分鐘**
  （main challenge 態），深度封鎖徵兆出現時 ≥ 2 小時（§2 深度冷卻）。
- **樣本量**：以「可重現方向性」為準而非統計顯著；每格 3–5 個分離時窗即足以分類，禁止為衝樣本連打。

### 2.3 停止／冷卻條件（fail-closed）

立即停止該時窗、進入冷卻、不重試的條件：

1. 任一 target 回 `challenge` 或 `redirect_loop`（該出口該時窗**最多再探 1 次**後停）。
2. 連續兩個時窗同一 route 皆非 `reachable` → 該 route 標記待人工判讀，暫停該 route 取樣。
3. 觀測到深度封鎖徵兆（瞬間 redirect、2h 冷卻無效）→ 全面停手，改白天單次重試。
4. 任何疑似節流升級（token 時好時壞）→ 停止，紀錄，冷卻，不加頻。

### 2.4 證據強度 rubric

| 等級 | 條件 |
|---|---|
| 強 | ≥3 分離時窗、涵蓋白天+深夜、outcome 一致且 schema 完整、redaction 通過 |
| 中 | 2 時窗一致，或跨時窗方向一致但含 1 個 transient |
| 弱 | 單一時窗、或含未解釋的 error/transient；**不得**作為 GO 依據 |

### 2.5 每路線 GO／NO-GO 判準

- **GO（可進 WORKER1 候選）**：該 route 在「強」證據下多時窗 `reachable`，且合規／維護風險可接受。
- **NO-GO**：多時窗 `ip_blocked`/`challenge`/`redirect_loop`，或合規無法釐清（如 `tw_egress` 條款不明）。
- **補研究**：證據僅「弱／中」或時窗覆蓋不足 → 回 Discovery 補樣本，不得跳 WORKER1。

---

## 3. Discovery Gate 決策

| 子卡 | 決策 | 條件與理由 |
|---|---|---|
| `OPS-REMOTE-PROBE1` | **建議 GO** | §1 契約已定；fixture-first、零 DB、零 retry、sanitized，風險低。live 請求仍逐次需 Coordinator 授權。 |
| `OPS-REMOTE-ROUTE1` | **條件 GO** | 前置：PROBE1 fixture 全綠並合併。每次 live probe 需 Coordinator 明確授權；依 §2 取樣／停止／rubric 執行。 |
| `OPS-REMOTE-WORKER1` | **HOLD** | 未取得 ROUTE1「強」證據下的 GO 路線 **＋需求方 sign-off** 前不得 claim（本卡驗收條件 3）。 |
| `OPS-REMOTE-CUTOVER1` | **HOLD** | 依賴 WORKER1 通過；production canary／回滾另屬 T4，需備份、互斥與人工 sign-off。 |

> **本卡不自行解鎖 WORKER1／CUTOVER1**：Gate 條件 3 明訂 shadow worker 之 GO 須「明確 GO＋需求方
> sign-off」。需求方 sign-off 屬 ruan6047 之最終核可權（canonical §1），執行者不得代行。本卡僅**建議**
> 上列決策，最終 Gate 由需求方於獨立查核後確認。

---

## 4. Guardrails（貫穿所有子卡，對應驗收條件 4）

- 不部署遠端排程；任何階段失敗一律保留現有本機 launchd fallback（rollout Goal / Done When）。
- 不繞過／不嘗試解 challenge；challenge 只作為**分類訊號**。
- 不採購代理、不共享住宅憑證、不建未隔離的 production 寫入。
- 不改 production 資料管線；`db_scope=none`。
- secrets／token／cookie／完整 IP 永不進 git、輸出或文件。

---

## 5. 驗收對照與交付狀態

| 本卡驗收（[`OPS-REMOTE-CRAWL1.md`](OPS-REMOTE-CRAWL1.md) §目標與驗收） | 對應章節 | 狀態 |
|---|---|---|
| 核可安全 probe contract（opt-in/allowlist/單次/零 retry/零 DB/sanitized） | §1 | ✅ 已定義，待查核 |
| 核可候選路線／跨時窗取樣／冷卻停止條件／證據強度 | §2 | ✅ 已定義，待查核 |
| 以 Discovery Gate 決定是否允許隔離 shadow worker | §3 | ✅ 建議 HOLD（待需求方 sign-off） |
| 不部署遠端排程／不繞 challenge／不採購代理／不改 production | §0、§4 | ✅ 已明訂為紅線 |

- **驗證方式**：本交付為 B2 權威文件（契約／決策），無程式碼；驗證＝獨立事實查核／校讀
  （canonical 類型 B2），對照 CPBL_SITE_MAP 事實與 rollout 邊界。子卡的程式與 live evidence 各自負責。
- **獨立查核**：須由 ≠ 執行者（Claude Opus 4.8@Claude Code）之新 context／人工進行；查核者留 finding，不代改本檔。
- **後續**：查核 APPROVE 後，需求方確認 §3 Gate；`OPS-REMOTE-PROBE1` 方可 claim。
