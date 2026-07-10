# 球種細分實作規劃（交接文件）

> 研究於 2026-07-08 完成（Fable session），本文件為**實作交接**：所有 API 結構、座標軸、
> 公式、sanity 數字皆已實測驗證，實作時**不需重新逆向**。建議模型：Opus（分類命名邏輯）
> ＋ Sonnet（migration/爬蟲/前端照 pattern 寫）。

## 0. 背景與動機（已驗證的事實）

1. **`pitch_tracking.auto_pitch_type` 是源頭壞資料**：全 DB 98.5% 標 `breakingball`
   （151 km/h 速球也標變化球）。源頭 API 即如此（艾菩樂 1,250 球全 breakingball），
   非解析錯誤。**前端好球帶卡目前顯示的球種標籤是垃圾**。
2. `tagged_pitch_type`（人工標）可靠但僅二元：fastball / breakingball。
3. logs API 有**未入庫**的軌跡資料，可導出 Statcast 式分類特徵（見 §1）。
4. 可分性已實測：3 位樣本投手 k-means 手肘皆在 k=3–4，叢集中心可教科書命名（見 §3）。

## 1. 資料來源（已實測）

- Endpoint：`GET https://stats.cpbl.com.tw/api/proxy/v1/players/logs`
  params `{playerType:"pitcher", acnt, year, kindCode}`——httpx 直連、無反爬，
  現有爬蟲 `src/cpbl/ingest/cpbl_pitch_tracking.py` 就是打這支。
- 每球 `Trackman.Pitch` 下有 **`Flight.PolyFit.PitchTrajectory.X/Y/Z`**：
  各為 `[c0, c1, c2]` 二次多項式係數（位置 = c0 + c1·t + c2·t²，公尺/秒）。
  TrackMan 球 100% 有（無設備場 Trackman=null，維持不收）。
- 另有 `Pitch.Location.ZoneTime`（出手到本壘飛行秒數，~0.41s）。
- **座標軸（已用 Release 欄位對照實證）**：
  - `X` = 朝本壘方向（c1 ≈ −球速）
  - `Y` = 垂直（`Y[0] ≈ RelHeight`）
  - `Z` = 水平（`Z[0] ≈ −RelSide`，注意符號相反）
- payload **沒有** SpinAxis / Tilt / InducedVertBreak 現成欄位——必須自己從軌跡導。

## 2. 特徵公式（已 sanity check）

```
垂直加速度 ay = 2·Y[2]          # m/s²（含重力）
水平加速度 az = 2·Z[2]          # m/s²
t = ZoneTime（缺值 fallback 0.42）
IVB = 0.5·(ay + 9.81)·t²·100    # cm，正=四縫線上飄
HB  = 0.5·az·t²·100             # cm，符號：右投四縫線為負（臂側）
```

分類特徵 4 維：`(rel_speed, IVB, HB, spin_rate)`，逐投手 z-score 標準化。

Sanity 基準（實測，偏離太多=軸解讀或公式寫錯）：
- 四縫線速球：IVB **+48~+56cm**、轉速 2,200–2,330 rpm、HB 臂側 −18~−34cm。
- 指叉/變速群：轉速 **< 1,500 rpm**（低轉是指叉招牌）。
- 曲/滑群：IVB 負（下墜）、HB 手套側（右投為正）。

## 3. 實測叢集範例（驗收對照用）

羅戈（右投，1,012 球，k=4）：

| 佔比 | 速度 | IVB | HB | 轉速 | 命名 |
|---|---|---|---|---|---|
| 41% | 149.3 | +53 | −25 | 2188 | 速球 |
| 8%  | 140.7 | +23 | −8  | 2380 | 卡特/硬滑 |
| 20% | 133.6 | +33 | −29 | **1274** | 指叉/變速 |
| 31% | 132.3 | **−22** | +17 | 2730 | 滑球 |

魔爾曼/艾菩樂同樣 4 群乾淨可命名。實作後跑同樣三位投手對照此表驗收。

## 4. 實作步驟

### Step 1：migration（下一個可用編號起）
`pitch_tracking` 加欄（`IF NOT EXISTS`，冪等）：
```sql
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_accel_y real;   -- 2·Y[2]
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS traj_accel_z real;   -- 2·Z[2]
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS zone_time   real;
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS ivb_cm      real;    -- 導出值，一併存
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS hb_cm       real;
ALTER TABLE cpbl.pitch_tracking ADD COLUMN IF NOT EXISTS pitch_type_pred text; -- 分類結果（推算）
```

### Step 2：爬蟲補收
`cpbl_pitch_tracking.py::_record()` 加取 `Flight.PolyFit.PitchTrajectory` 與
`Location.ZoneTime`，算 accel/ivb/hb 一併 UPSERT（`_COLS` 同步加欄）。
然後**重爬全季**：`uv run cpbl-scrape-pitches 2026 A`（已改為全出賽投手，~139 位，
1s delay ≈ 3 分鐘；D 二軍視需求）。**只能本機爬**，爬完同步生產（Runbook §3）。

### Step 3：離線分類 CLI（新增 `cpbl-classify-pitches`）
逐投手（year × kind，樣本 **n ≥ 150** 球才分類，不足者 fallback 用
`tagged_pitch_type` 二元直翻「速球/變化球」）：

1. 特徵 4 維 z-score → **GMM，k 以 BIC 選 2–6**（或 k-means + 手肘，GMM 較穩）。
2. 左右手推定：`avg(rel_side)` 正=右投、負=左投。
   ⚠️ 此符號約定**需用一位已知左投驗證**（研究只看了三位右投）。
3. 叢集命名規則（保守分群，寧粗勿錯）：
   - `速球`：速度最高群且 IVB > +35cm
   - `卡特/滑球`：速度次高、|HB| < 12cm、IVB +10~+35
   - `指叉/變速`：轉速 < 1,600 或（速差 > 8km/h 且 HB 臂側且 IVB > 0）
   - `滑球/橫掃`：IVB < +10 且 HB 手套側
   - `曲球`：IVB < −10 且速度最低群
   - 對不上任何規則 → `變化球`（不硬命名）
   - **臂側/手套側依左右手翻轉 HB 符號後判**。
4. 寫回 `pitch_type_pred`；同場多次出現取眾數平滑（同打席內球種可信度高）。

### Step 4：API + 前端
- `games.py::game_live` tracking SELECT 加 `pitch_type_pred`（沿用現有欄位白名單寫法）。
- `game-board.tsx::StrikeZone`：`pitchZh(auto_pitch_type)` → 改顯示 `pitch_type_pred`，
  缺值 fallback `tagged_pitch_type`（fastball→速球/breakingball→變化球）。
  `PITCH_ZH` map 淘汰。卡片標題補「（推算）」。
- 球員頁「球種應對」如有用 auto_pitch_type 的地方一併換（grep `auto_pitch_type`）。

### Step 5：驗收（過不了不上線）
1. 三位基準投手叢集對照 §3 表（佔比 ±5%、中心值方向一致）。
2. `pitch_type_pred='速球'` 對 `tagged_pitch_type='fastball'` 的一致率 **≥ 90%**
   （tagged 是弱標籤，允許卡特被歸滑球之類的邊界差異）。
3. 抽 3–5 位知名投手對照公開球路配置（新聞/球探報導）。
4. 一位左投 sanity：HB 符號翻轉後命名仍合理。

## 5. 紅線與限制

- **誠實標註**：所有顯示處標「推算」；聚合統計要註明設備場偏誤樣本
  （花蓮/嘉義市無設備，見 memory `pitch-tracking-venue-coverage`）。
- 逐球查詢一律 `kind_code` 過濾（pitch_tracking 含二軍，混了會對不上 box）。
- 不猜 SpinAxis、不做縫線偏移（資料沒有）；四縫 vs 二縫不強分（無轉軸佐證時
  併稱「速球」）。
- migration 冪等、不改舊檔；爬蟲失敗單投手略過不中斷（現有 pattern）。

## 6. Quick win（可獨立先做，5 分鐘）

不等完整實作：`StrikeZone` 先把 `auto_pitch_type` 換成 `tagged_pitch_type`
（fastball→速球、breakingball→變化球），至少不再出現「151km/h 變化球」。
需要 API 的 tracking SELECT 加 `tagged_pitch_type` 欄。
