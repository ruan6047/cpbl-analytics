# LIVE-GAME-BACKEND1 來源觀測紀錄

> 卡片：`LIVE-GAME-BACKEND1`　spec 基線：v1.0
> 目的：只記錄官方來源實際觀測；T-24h／T-60m 是採樣窗口，不是公布 SLA。

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

下一個觀測窗口為 2026-07-28 A-226／227；worker 需保留 `first_observed_at`。本表未完成前不得宣稱官方會在固定時點提供欄位。

| 場次 | T-30h | T-90m | T-60m | T-30m | START | exact key path／結論 |
|---|---|---|---|---|---|---|
| A-226 | 待觀測 | 待觀測 | 待觀測 | 待觀測 | 待觀測 | 待補 |
| A-227 | 待觀測 | 待觀測 | 待觀測 | 待觀測 | 待觀測 | 待補 |
| 第三場 | 待觀測 | 待觀測 | 待觀測 | 待觀測 | 待觀測 | 待補 |
