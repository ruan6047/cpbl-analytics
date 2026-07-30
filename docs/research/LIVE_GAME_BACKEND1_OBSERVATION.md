# LIVE-GAME-BACKEND1 來源觀測紀錄

> 卡片：`LIVE-GAME-BACKEND1`　spec 基線：v1.0
> 目的：只記錄官方來源實際觀測；T-30h／T-90m／T-60m／T-30m 是採樣窗口，不是公布 SLA。

## 2026-07-26 live canary

### 賽中來源

| 時間（Asia/Taipei） | 場次 | raw status | stats LiveLog | www getlive | TrackMan 非空 | 觀測 |
|---|---:|---|---:|---:|---:|---|
| 17:15:30 | A-223 | START | 109 | 109 | 0 | 五局，文字逐球可用 |
| 17:15:30 | A-224 | START | 20 | 20 | 0 | 一局，文字逐球可用 |
| 17:15:30 | A-225 | START | 133 | 133 | 0 | 五局，文字逐球可用 |
| 17:16:18 | A-223 | START | 111 | 109 | 0 | stats 一度領先 2 事件 |
| 17:16:48 | A-223 | START | 112 | 112 | 0 | www 約 10 秒後追平 |

- 三場 stats 單場 endpoint 均 HTTP 200；單請求約 42–125 ms。
- production VPS 對 stats A-223 單場 endpoint HTTP 200、約 174 ms；同機 `www /box` HTTP 404。
- 結論：stats 適合作 production live 主來源；賽中 TrackMan 不可用，`SkipTrackman=false` 亦不得映射 available。

### 實作後 one-shot shadow（20:06）

`REDIS_URL=redis://localhost:6379/0 LIVE_GAME_WORKER_ENABLED=true uv run cpbl-live-worker --once`

```json
{"cached":3,"errors":0,"next_poll_seconds":1800,"phases":{"final":3},"selected":3,"state":"ok"}
```

| 場次 | phase | LiveLog | TrackMan count | 公開 snapshot 含 Trackman payload | lineup |
|---|---|---:|---:|---|---|
| A-223 | final | 266 | 249 | 否 | 兩隊 announced |
| A-224 | final | 287 | 0 | 否 | 兩隊 announced |
| A-225 | final | 252 | 0 | 否 | 兩隊 announced |

A-224／225 完賽當下仍為 0 筆 TrackMan，故 final 後仍需低頻 postgame refresh；不可把 `final + 0` 判為 no-equipment。

## 預告先發／lineup 觀測矩陣

### Evidence 完整性

- production observer 白名單固定為 `2026-A-226`～`228`；觀測期間 2026-07-26 23:07 至
  2026-07-30 00:00（Asia/Taipei）。
- `manifest.jsonl` 共 4,614 entries，HTTP status 全為 200；A-226／227 各 1,077 筆，
  A-228 為 2,076 筆。三場皆留下 `SCHEDULED → START → FINISHED`。
- deadline marker：`2026-07-30T00:00:00.000488+08:00`；state 的
  `terminal_game_ids` 為三場全數。observer 已 clean exit，沒有等待 7/30 晚場。
- export manifest 共 4,614 raw gzip；`manifest_sha256` =
  `528b994730d461ad12382220c2043c1aabd5c85343d75c3bed9f5c2c2f487f8f`，
  `total_checksum` =
  `e110083caf371e5c7902364a1af35b4f76e8cdbbeb261bd5f931984f14166abd`。
- 本節只記錄唯讀對帳結果；raw evidence 與 volume 仍保留在 VPS，未刪除。

### 固定窗口

以下 `H/P/L` 依序代表客／主隊 `Hitters` 數、客／主隊 `Pitchers` 數、`LiveLog` 數；
括號內為距目標窗口的採樣誤差。所有時間為 Asia/Taipei。

| 場次 | T-30h | T-90m | T-60m | T-30m | 名目 START 附近 |
|---|---|---|---|---|---|
| A-226（7/28 18:35） | 12:42:57（+7m57s）`0/0/0/0/0` | 17:01:37（−3m22s）`0/0/0/0/0` | 17:35:17（+17s）`0/0/0/0/0` | 18:05:13（+14s）`0/0/0/0/0` | 18:35:17 `SCHEDULED`，`9/9/0/0/0` |
| A-227（7/28 18:35） | 12:42:57（+7m57s）`0/0/0/0/0` | 17:01:37（−3m22s）`0/0/0/0/0` | 17:35:17（+17s）`0/0/0/0/0` | 18:05:13（+14s）`0/0/0/0/0` | 18:35:17 `START`，`9/9/0/0/1` |
| A-228（7/29 18:35） | 12:30:08（−4m52s）`0/0/0/0/0` | 17:02:58（−2m02s）`0/0/0/0/0` | 17:34:40（−20s）`0/0/0/0/0` | 18:04:35（−25s）`0/0/0/0/0` | 18:34:36 `SCHEDULED`，`0/0/0/0/0` |

### First observed 與 exact key path

| 場次 | 兩隊 `Hitters[]` 首見 | raw `START`／`LiveLog` 首見 | 兩隊 `Pitchers[]` 首見 | raw `FINISHED` 首見 |
|---|---|---|---|---|
| A-226 | 18:35:17，兩隊各 9 人，raw 仍 `SCHEDULED` | 18:36:08，LiveLog 1 | 18:36:21，兩隊各 1 人 | 21:33:37 |
| A-227 | 18:35:17，兩隊各 9 人 | 18:35:17，LiveLog 1 | 18:36:21，兩隊各 1 人 | 21:19:55 |
| A-228 | 18:35:39，兩隊各 9 人，raw 仍 `SCHEDULED` | 18:45:44，LiveLog 14 | 18:45:44，兩隊各 1 人 | 21:41:11 |

- lineup exact paths：`Data.Game.Visiting.Hitters[]`、`Data.Game.Home.Hitters[]`；球員欄位為
  `Lineup`、`HitterAcnt`、`HitterName`、`DefendStation`。三場直到 T-30m 都是空陣列，
  僅能證明接近／進入 START 時可取得，不能宣稱「賽前一小時公布」。
- 全期間 key-path universe 未出現 `Probable`、`Starter` 或獨立預告先發欄位。
  `Data.Game.Visiting.Pitchers[]`／`Home.Pitchers[]` 首次非空都晚於 raw `START`，且內容含
  `PitchCnt`、`InningPitchedCnt`、`Era`、`Whip`、`RoleType` 等 box 統計；這是已上場投手，
  **不得映射成 probable pitcher**。
- A-228 的 raw `START` 比名目時間晚約 10 分鐘，證明 phase 必須依官方 raw status，不能依
  `PreExeDate` 或排程時鐘推定。

## Gate 結論

1. stats single-game 足以支援 `START → FINISHED` 的集中式 live feed、lineup 接近開賽後的
   呈現，以及 final 後短期補抓；不需等待 7/30 晚場才能下此結論。
2. stats **不支援已驗證的賽前預告先發來源**，也未證明 T-60m lineup。現行 parser 已改為
   fail closed：保留 `Pitchers[]` 作 box 資料，但不再產生 `probable_pitcher=announced`。
3. `LIVE-GAME-BACKEND1` 若要維持「賽前一天預告先發」成功條件，必須依 spec §4.1 回到
   Design Gate，決定本機 `www` relay 的 freshness／故障退化／單點風險；在需求方定案前，
   不得把 stats 欄位改名冒充、不得啟動 `UX-LIVE-GAME1`。
