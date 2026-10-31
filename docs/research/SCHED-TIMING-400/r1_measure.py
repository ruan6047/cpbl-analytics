#!/usr/bin/env python3
"""#400 R1 唯讀量測：launchd 排程實際觸發／完成時間分布 vs 服務事件。

唯讀保證：
  * 只讀主 checkout 的 logs/（檔案 open 讀取）與 `launchctl`／`pmset` 不在本檔呼叫。
  * DB 只經 `docker exec ... psql`，以 PGOPTIONS=default_transaction_read_only=on 開唯讀交易，只下 SELECT。
  * 不連網、不執行任何 cpbl-* 入口或 scripts/*.sh。
用法（產出 Markdown 到 stdout）：
  python3 -I docs/research/SCHED-TIMING-400/r1_measure.py > docs/research/SCHED-TIMING-400/R1_measurements.md
環境變數：CPBL_LOGS（預設 ~/Dev/cpbl-analytics/logs）、CPBL_DB_CONTAINER（預設 cpbl-analytics-db-1）
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import os
import re
import subprocess

LOGS = os.environ.get("CPBL_LOGS", os.path.expanduser("~/Dev/cpbl-analytics/logs"))
DBC = os.environ.get("CPBL_DB_CONTAINER", "cpbl-analytics-db-1")
TZ = dt.timezone(dt.timedelta(hours=8))
OUT: list[str] = []


def p(s: str = "") -> None:
    OUT.append(s)


def sql(q: str) -> list[list[str]]:
    cmd = ["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on", DBC, "sh", "-c",
           'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -A -t -F "|" -P footer=off']
    r = subprocess.run(cmd, input=q, capture_output=True, text=True, check=True)
    return [ln.split("|") for ln in r.stdout.splitlines() if ln.strip()]


def parse_ts(s: str) -> dt.datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S.%f%z"):
        try:
            return dt.datetime.strptime(s, fmt).astimezone(TZ)
        except ValueError:
            pass
    return dt.datetime.fromisoformat(s).astimezone(TZ)


def local(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)


def q(vals, pct):
    v = sorted(vals)
    if not v:
        return None
    k = (len(v) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def dist(vals, fmt=lambda x: f"{x:.1f}"):
    if not vals:
        return "n=0"
    return (f"n={len(vals)} min={fmt(min(vals))} p50={fmt(q(vals, .5))} p90={fmt(q(vals, .9))} "
            f"max={fmt(max(vals))}")


def hhmm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def tod_min(t: dt.datetime) -> float:
    return t.hour * 60 + t.minute + t.second / 60


# ---------------------------------------------------------------- 賽程日曆（DB）
games = sql("""select kind_code, game_sno, game_date from cpbl.games where year=2026 order by game_date""")
played_by_date: dict[dt.date, set[str]] = collections.defaultdict(set)
for k, _sno, d in games:
    played_by_date[dt.date.fromisoformat(d)].add(k)
LAST = {k: max(dt.date.fromisoformat(d) for kk, _, d in games if kk == k) for k in {g[0] for g in games}}
FIRST = {k: min(dt.date.fromisoformat(d) for kk, _, d in games if kk == k) for k in {g[0] for g in games}}
REG_END = LAST["A"]
C_DECIDED = dt.date(2026, 10, 26)  # 由 games 推導：C 最後完賽日（見 M1 輸出）


def phase(d: dt.date) -> str:
    if d <= REG_END:
        return "例行賽期"
    if d <= dt.date(2026, 10, 27):
        return "季後賽期"
    return "休季"


p("# R1 量測輸出（r1_measure.py 自動產生，勿手改）")
p()
p(f"產生時刻：{dt.datetime.now(TZ).isoformat(timespec='seconds')}；logs 目錄：`{LOGS}`")
p()

# ---------------------------------------------------------------- M0 覆蓋
p("## M0 資料來源覆蓋期間")
p()


def span_files(pattern, rx):
    fs = sorted(glob.glob(os.path.join(LOGS, pattern)))
    ds = [re.search(rx, os.path.basename(f)).group(1) for f in fs]
    return len(fs), (ds[0] if ds else "-"), (ds[-1] if ds else "-")


for pat, rx in [("refresh-*.log", r"refresh-(\d{8})"), ("weekly-game-pitches-*.log", r"(\d{8})"),
                ("weekly-box-revisions-*.log", r"(\d{8})"), ("postseason-evening-2*.log", r"(\d{8})"),
                ("availability-sentinel-*.tsv", r"(\d{8})")]:
    n, a, b = span_files(pat, rx)
    p(f"- `{pat}`：{n} 份，{a} → {b}")
for f in sorted(glob.glob(os.path.join(LOGS, "schedule-history", "*.jsonl"))):
    rows = [json.loads(x) for x in open(f) if x.strip()]
    ts = [r["started_at"] for r in rows if r.get("started_at")]
    p(f"- `schedule-history/{os.path.basename(f)}`：{len(rows)} 列，{min(ts)[:10]} → {max(ts)[:10]}")
lo = [ln for ln in open(os.path.join(LOGS, "launchd.out.log")) if ln.startswith("[20")]
p(f"- `launchd.out.log`（每日鏈 launchd stdout）：{lo[0][1:11]} → {lo[-1][1:11]}")
aw = [ln for ln in open(os.path.join(LOGS, "launchd-alert-watch.out.log")) if ln.startswith("[20")]
p(f"- `launchd-alert-watch.out.log`：{len(aw)} 行，{aw[0][1:20]} → {aw[-1][1:20]}")
for tbl, col, _extra in [("refresh_log", "refreshed_at", ""), ("game_schedule_status_revisions", "fetched_at", ""),
                        ("game_source_revisions", "fetched_at", ""), ("box_pitching_revisions", "fetched_at", ""),
                        ("official_change_signals", "detected_at", "")]:
    r = sql(f"select count(*), min({col} at time zone 'Asia/Taipei')::date, max({col} at time zone 'Asia/Taipei')::date from cpbl.{tbl}")[0]
    p(f"- DB `cpbl.{tbl}.{col}`：{r[0]} 列，{r[1]} → {r[2]}")
p()

# ---------------------------------------------------------------- M1 日曆
p("## M1 2026 賽程日曆（cpbl.games）")
p()
for k in sorted(LAST):
    n = sum(1 for g in games if g[0] == k)
    p(f"- {k}：{FIRST[k]} → {LAST[k]}，{n} 場")
p(f"- 本文件分期：例行賽期 ≤ {REG_END}；季後賽期 {REG_END + dt.timedelta(days=1)} → 2026-10-27；休季 ≥ 2026-10-28")
p()

# ---------------------------------------------------------------- M2 每日鏈
p("## M2 每日鏈 com.cpbl.scrape-daily")
p()
# 2a launchd.out.log 分相（launchd 觸發；07-03 起）
blocks = []
cur = None
for ln in lo:
    m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)", ln)
    if not m:
        continue
    t, msg = local(m.group(1)), m.group(2)
    if msg.startswith("start:"):
        cur = {"start": t}
        blocks.append(cur)
    elif cur is None:
        continue
    elif re.match(r"(scrape )?exit=", msg) and "scrape_end" not in cur:
        cur["scrape_end"] = t
        cur["scrape_exit"] = msg.split("=")[-1].strip()
    elif msg.startswith("sync prod ("):
        cur["sync_start"] = t
    elif msg.startswith("overall exit="):
        cur["end"] = t
        cur["exit"] = msg.split("=")[1].split()[0]
    elif msg.startswith("day type="):
        cur["day_type"] = msg.split("=")[1].split("（")[0]
    elif "sync prod" in msg and ("ok" in msg or "exit" in msg or "fail" in msg.lower()):
        cur["sync_end"] = t
p(f"### M2a launchd.out.log 分相（{len(blocks)} 次 launchd 觸發）")
p()
by = collections.defaultdict(list)
for b in blocks:
    d = b["start"].date()
    yday = d - dt.timedelta(days=1)
    tag = "昨有賽" if (played_by_date.get(yday, set()) & {"A", "D", "E", "C", "F"}) else "昨無賽"
    b["phase"], b["tag"] = phase(d), tag
    by[(b["phase"], tag)].append(b)
for key in sorted(by):
    bs = by[key]
    off = [(b["start"] - b["start"].replace(hour=10, minute=10, second=0)).total_seconds() / 60 for b in bs
           if b["start"].hour >= 10]  # 07-03／07-04 的 03:xx 舊時刻另列
    tot = [(b["end"] - b["start"]).total_seconds() / 60 for b in bs if "end" in b]
    scr = [(b["scrape_end"] - b["start"]).total_seconds() / 60 for b in bs if "scrape_end" in b]
    syn = [(b["sync_end"] - b["sync_start"]).total_seconds() / 60 for b in bs if "sync_end" in b and "sync_start" in b]
    fin = [tod_min(b["end"]) for b in bs if "end" in b]
    after11 = sum(1 for b in bs if "end" in b and tod_min(b["end"]) > 11 * 60)
    noend = sum(1 for b in bs if "end" not in b)
    ex = collections.Counter(b.get("exit", "無終行") for b in bs)
    p(f"- **{key[0]}／{key[1]}**（{len(bs)} 次，{bs[0]['start'].date()} → {bs[-1]['start'].date()}）")
    p(f"  - 觸發延遲（分，相對 10:10）：{dist(off)}")
    p(f"  - 爬取相耗時（分）：{dist(scr)}；同步相耗時（分）：{dist(syn)}；全程（分）：{dist(tot)}")
    p(f"  - 完成時刻：{dist(fin, hhmm)}；晚於 11:00 完成：{after11} 次；無 overall 行：{noend} 次；exit 分布：{dict(ex)}")
late = [b for b in blocks if (b["start"] - b["start"].replace(hour=10, minute=10, second=0)).total_seconds() > 300]
p(f"- 觸發延遲 > 5 分的 launchd 觸發：{len(late)} 次："
  + "、".join(f"{b['start']:%m-%d %H:%M}" for b in late))
early = [b for b in blocks if b["start"].hour < 10 or (b["start"].hour == 10 and b["start"].minute < 10)]
p(f"- 早於 10:10 的 launchd 觸發（plist 改時刻前的 03:xx 等）：{len(early)} 次："
  + "、".join(f"{b['start']:%m-%d %H:%M}" for b in early))
p()

# 2b 日型（refresh log DAY_TYPE 行，#364 上線後）
p("### M2b 日型分布（launchd.out.log 的 `day type=` 行）")
p()
dts = [(b["start"].date(), b.get("day_type"), round((b["end"] - b["start"]).total_seconds() / 60, 1) if "end" in b else None)
       for b in blocks if b.get("day_type")]
for d, t, m in dts:
    p(f"- {d} {phase(d)}：{t}，全程 {m} 分")
if not dts:
    p("- 無（day type 行尚未出現）")
p()

# 2c 歷史 jsonl
p("### M2c schedule-history（08-18 起；含 manual）")
p()
hist = [json.loads(x) for x in open(os.path.join(LOGS, "schedule-history", "com.cpbl.scrape-daily.jsonl")) if x.strip()]
fins = [r for r in hist if r["state"] != "running"]
starts = {(r["started_at"], r.get("log")) for r in hist if r["state"] == "running"}
orph = starts - {(r["started_at"], r.get("log")) for r in fins}
p(f"- 終態列 {len(fins)}；running 列無對應終態：{len(orph)}")
cnt = collections.Counter((r["trigger"], r["state"], r["exit_code"]) for r in fins)
for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
    p(f"  - trigger={k[0]} state={k[1]} exit={k[2]}：{v}")
man = [r for r in fins if r["trigger"] == "manual"]
p("- manual 觸發時刻：" + "、".join(r["started_at"][5:16] for r in man))
p()

# 2d refresh_log 爬取相時刻（06-17 起，較長的覆蓋）
p("### M2d cpbl.refresh_log（scope=recent-games）寫入時刻（06-17 起）")
p()
rl = sql("""select (refreshed_at at time zone 'Asia/Taipei')::text, ok from cpbl.refresh_log
            where scope='recent-games' order by refreshed_at""")
hours = collections.Counter(r[0][11:13] for r in rl)
p(f"- {len(rl)} 列；寫入時（台北）分布：" + "、".join(f"{h}時×{n}" for h, n in sorted(hours.items())))
p(f"- ok=false：{sum(1 for r in rl if r[1] == 'f')} 列")
p()

# ---------------------------------------------------------------- M3 比賽結束時刻
p("## M3 比賽開始／結束時刻（官方賽程 payload GameDateTimeS／E，取每場最新一筆 revision）")
p()
gt = sql("""select distinct on (kind_code, game_sno) kind_code, game_sno, raw_payload->>'GameDateTimeS',
            raw_payload->>'GameDateTimeE', raw_payload->>'GameDate'
            from cpbl.game_schedule_status_revisions where year=2026 and coalesce(raw_payload->>'GameDateTimeE','')<>''
            order by kind_code, game_sno, id desc""")
ends = collections.defaultdict(list)
starts_k = collections.defaultdict(list)
over_mid = collections.Counter()
durs = collections.defaultdict(list)
night_last_end: dict[dt.date, dt.datetime] = {}
for k, _sno, s, e, _gd in gt:
    sd, ed = dt.datetime.fromisoformat(s), dt.datetime.fromisoformat(e)
    day = sd.date()
    m_end = (ed - dt.datetime.combine(day, dt.time())).total_seconds() / 60
    if (ed - sd).total_seconds() > 8 * 3600:  # 保留賽／續賽：終場與開賽不在同一晚
        over_mid[k] += 1
        continue
    ends[k].append(m_end)
    durs[k].append((ed - sd).total_seconds() / 60)
    starts_k[k].append(tod_min(sd))
    if k in "ACE":
        cur = night_last_end.get(day)
        if cur is None or ed > cur:
            night_last_end[day] = ed
for k in sorted(ends):
    e = ends[k]
    p(f"- {k}：開賽 {dist(starts_k[k], hhmm)}；終場 {dist(e, hhmm)}；"
      f"終場 >22:00 {sum(x > 22*60 for x in e)}、>23:00 {sum(x > 23*60 for x in e)}、>23:35 {sum(x > 23*60+35 for x in e)}、跨日 {sum(x >= 24*60 for x in e)}")
for k in sorted(durs):
    p(f"- {k}：開賽→終場時長 {dist(durs[k], hhmm)}；> 300 分（晚間告警『開賽＋5h』門檻）{sum(x > 300 for x in durs[k])} 場、> 270 分 {sum(x > 270 for x in durs[k])} 場")
for k in sorted(over_mid):
    p(f"- {k}：終場距開賽 > 8 小時（保留賽續賽，不計入上列）{over_mid[k]} 場")
le = [(ed - dt.datetime.combine(d, dt.time())).total_seconds() / 60 for d, ed in night_last_end.items()]
p(f"- 一軍（A／E／C）每晚最後一場終場：{dist(le, hhmm)}；>23:35 的夜數 {sum(x > 23*60+35 for x in le)}/{len(le)}")
p()

# ---------------------------------------------------------------- M4 官方 stats 完賽出現延遲（晚間鏈 timeline）
p("## M4 官方 stats 出現完賽的時刻（晚間鏈 timeline，5 分輪詢解析度）vs 終場")
p()
st = json.load(open(os.path.join(LOGS, "last-postseason-evening.json")))
gend = {f"2026-{k}-{sno}": dt.datetime.fromisoformat(e).replace(tzinfo=TZ) for k, sno, s, e, gd in gt}
for t in st.get("timeline", []):
    if t.get("type") != "final_not_ingested":
        continue
    e = gend.get(t["key"])
    t1, t3 = parse_ts(t["t1_stats_first_seen"]), parse_ts(t["t3_synced"])
    p(f"- {t['key']}：終場 {e:%m-%d %H:%M}｜stats 首見完賽 {t1:%H:%M:%S}（+{(t1 - e).total_seconds() / 60:.1f} 分）"
      f"｜正式站同步完成 {t3:%H:%M:%S}（+{(t3 - e).total_seconds() / 60:.1f} 分）")
for b in st.get("boxpa", []):
    e = gend.get(b["key"])
    bp = parse_ts(b["box_prod_at"]) if b.get("box_prod_at") else None
    p(f"- {b['key']} box／PA 送達正式站：{bp:%m-%d %H:%M}（終場後 +{(bp - e).total_seconds() / 60:.1f} 分；reason={b.get('reason')}）")
p()

# ---------------------------------------------------------------- M5 我方首見完賽（例行賽：每日鏈首見）
p("## M5 我方首次觀測到「完賽」的時刻 vs 終場（game_schedule_status_revisions，07-20 起）")
p()
fs = sql("""select kind_code, game_sno, min(fetched_at at time zone 'Asia/Taipei')::text
            from cpbl.game_schedule_status_revisions
            where year=2026 and raw_present_status=1 and coalesce(raw_payload->>'GameDateTimeE','')<>''
            group by 1,2""")
lag = collections.defaultdict(list)
for k, sno, f in fs:
    e = gend.get(f"2026-{k}-{sno}")
    if not e:
        continue
    fdt = dt.datetime.fromisoformat(f).replace(tzinfo=TZ)
    if fdt < dt.datetime(2026, 7, 21, tzinfo=TZ):
        continue  # 07-20 首灌：全季一次寫入，不代表觀測延遲
    lag[(phase(e.date()), k)].append((fdt - e).total_seconds() / 3600)
for key in sorted(lag):
    p(f"- {key[0]}／{key[1]}：首見完賽距終場（小時）{dist(lag[key])}")
p()

# ---------------------------------------------------------------- M6 box 修訂
p("## M6 box 投手列修訂（cpbl.box_pitching_revisions）：第 2 版以後被誰、在賽後第幾天觀測到")
p()
br = sql("""with r as (select year, kind_code, game_sno, pitcher_acnt, content_hash,
              fetched_at at time zone 'Asia/Taipei' f,
              row_number() over (partition by year,kind_code,game_sno,pitcher_acnt order by fetched_at) rn
            from cpbl.box_pitching_revisions)
            select r.kind_code, r.game_sno, r.f::text, g.game_date::text, r.rn from r
            join cpbl.games g using (year, kind_code, game_sno) where r.rn>1""")
first = sql("""select min(fetched_at at time zone 'Asia/Taipei')::text from cpbl.box_pitching_revisions""")[0][0]


def who(t: dt.datetime) -> str:
    if t.weekday() == 0 and 14 <= t.hour < 16:
        return "週一14時段(weekly-box)"
    if t.weekday() == 0 and t.hour == 13:
        return "週一13時段"
    if 10 <= t.hour < 12:
        return "10–12時(每日鏈)"
    if t.hour >= 17 or t.hour < 3:
        return "17–03時(晚間/手動)"
    return "其他時段(手動等)"


c = collections.Counter()
lagd = collections.defaultdict(list)
games_rev = collections.defaultdict(set)
for k, sno, f, gd, _rn in br:
    t = dt.datetime.fromisoformat(f[:19]).replace(tzinfo=TZ)
    w = who(t)
    c[w] += 1
    lagd[w].append((t.date() - dt.date.fromisoformat(gd)).days)
    games_rev[w].add((k, sno))
p(f"- 表首筆 fetched_at：{first[:19]}（深度層部署前的修訂不可觀測）")
p(f"- 第 2 版以後的修訂列 {len(br)}，涉及場次 {len({(k, s) for k, s, *_ in br})}")
for w in sorted(c):
    p(f"  - {w}：{c[w]} 列／{len(games_rev[w])} 場；距比賽日（天）{dist(lagd[w], lambda x: f'{x:.0f}')}")
p()

# ---------------------------------------------------------------- M7 來源修訂
p("## M7 逐場來源修訂（cpbl.game_source_revisions）：同一場同來源第 2 版以後的觀測時段")
p()
sr = sql("""with r as (select kind_code, game_sno, source, outcome, fetched_at at time zone 'Asia/Taipei' f,
              row_number() over (partition by year,kind_code,game_sno,source order by fetched_at) rn
            from cpbl.game_source_revisions where year=2026)
            select r.kind_code, r.game_sno, r.source, r.outcome, r.f::text, g.game_date::text from r
            join cpbl.games g on g.year=2026 and g.kind_code=r.kind_code and g.game_sno=r.game_sno where r.rn>1""")
c2 = collections.defaultdict(collections.Counter)
lag2 = collections.defaultdict(list)
for _k, _sno, src, _oc, f, gd in sr:
    t = dt.datetime.fromisoformat(f[:19]).replace(tzinfo=TZ)
    c2[src][who(t)] += 1
    lag2[src].append((t.date() - dt.date.fromisoformat(gd)).days)
for src in sorted(c2):
    p(f"- {src}：{dict(c2[src])}；距比賽日（天）{dist(lag2[src], lambda x: f'{x:.0f}')}")
p()

# ---------------------------------------------------------------- M8 週跑逐球差異
p("## M8 週一全季逐球重跑：相鄰兩週同一場球數變化（weekly-game-pitches-*.log）")
p()
wl = sorted(glob.glob(os.path.join(LOGS, "weekly-game-pitches-*.log")))
snap = {}
for f in wl:
    d = re.search(r"(\d{8})", f).group(1)
    m = {}
    for ln in open(f):
        mm = re.search(r"\] (2026-[AD]-\d+) → (\d+) 球", ln)
        if mm:
            m[mm.group(1)] = int(mm.group(2))
    snap[d] = m
gdate = {f"2026-{k}-{sno}": dt.date.fromisoformat(d) for k, sno, d in games}
keys = sorted(snap)
for a, b in zip(keys, keys[1:], strict=False):
    ch = [(g, snap[a].get(g), snap[b][g]) for g in snap[b] if snap[a].get(g) != snap[b][g]]
    newly = [x for x in ch if x[1] is None]
    grew = [x for x in ch if x[1] is not None and x[2] > x[1]]
    shrank = [x for x in ch if x[1] is not None and x[2] < x[1]]
    ad = [(dt.datetime.strptime(b, "%Y%m%d").date() - gdate[g]).days for g, *_ in grew if g in gdate]
    p(f"- {a}→{b}：場數 {len(snap[a])}→{len(snap[b])}；新出現（該週新完賽，非晚發布）{len(newly)}，其中 0 球 {sum(1 for x in newly if x[2] == 0)}；球數增加 {len(grew)} 場"
      f"（+{sum(x[2] - x[1] for x in grew)} 球；距比賽日天數 {dist(ad, lambda x: f'{x:.0f}')}）；減少 {len(shrank)} 場")
zero_last = [g for g, n in snap[keys[-1]].items() if n == 0]
p(f"- 最後一份（{keys[-1]}）仍為 0 球的場：{len(zero_last)}（無設備球場或源頭未發布，本表無法區分）")
p("- 註：週跑 log 只有 6 份（09-21 起），09-21 首跑之前的晚發布由 registry 證據欄記載（33 場／9,464 球），本表不重算")
p()

# ---------------------------------------------------------------- M9 週跑時刻
p("## M9 週跑觸發與完成時刻（schedule-history＋launchd stdout）")
p()
for lab, out in [("com.cpbl.weekly-game-pitches", "launchd-weekly-pitches.out.log"),
                 ("com.cpbl.weekly-box-revisions", "launchd-weekly-box-revisions.out.log")]:
    runs = []
    curr = None
    for ln in open(os.path.join(LOGS, out)):
        m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)", ln)
        if not m:
            continue
        t, msg = local(m.group(1)), m.group(2)
        if msg.startswith("start:"):
            curr = {"start": t}
            runs.append(curr)
        elif curr and msg.startswith("overall exit="):
            curr["end"], curr["exit"] = t, msg.split("=")[1]
        elif curr and msg.startswith("FATAL"):
            curr["end"], curr["exit"] = t, "FATAL:" + msg[7:30]
    hrows = [json.loads(x) for x in open(os.path.join(LOGS, "schedule-history", lab + ".jsonl")) if x.strip()]
    busy = [r for r in hrows if r["state"] != "running" and r.get("exit_code") == 75]
    p(f"- **{lab}**")
    for r in runs:
        dur = f"{(r['end'] - r['start']).total_seconds() / 60:.1f} 分" if "end" in r else "無終行"
        p(f"  - {r['start']:%m-%d %a %H:%M:%S} → {r.get('end', r['start']):%H:%M:%S}（{dur}；exit={r.get('exit')}）")
    for r in busy:
        p(f"  - 歷史列 exit=75（refresh lock busy 跳過）：{r['started_at'][:19]} note={r.get('note')}")
p()

p("- 週一每日鏈完成時刻（對照 13:10 週跑）："
  + "、".join(f"{b['start']:%m-%d}→{b['end']:%H:%M}" for b in blocks if b["start"].weekday() == 0 and "end" in b))
p()

# ---------------------------------------------------------------- M10 watchdog
p("## M10 com.cpbl.schedule-watchdog 執行時刻與判定")
p()
wh = [json.loads(x) for x in open(os.path.join(LOGS, "schedule-history", "com.cpbl.schedule-watchdog.jsonl")) if x.strip()]
p(f"- {len(wh)} 列，{wh[0]['started_at'][:10]} → {wh[-1]['started_at'][:10]}；執行時（台北）分布："
  + "、".join(f"{h}時×{n}" for h, n in sorted(collections.Counter(r['started_at'][11:13] for r in wh).items())))
p("- 非 21 時的執行（RunAtLoad／手動）：" + "、".join(r["started_at"][:16] for r in wh if r["started_at"][11:13] != "21"))
p("- note 分布：" + str(dict(collections.Counter(r.get("note") for r in wh))))
daysw = {r["started_at"][:10] for r in wh}
d0 = dt.date.fromisoformat(wh[0]["started_at"][:10])
missing = [str(d0 + dt.timedelta(days=i)) for i in range((dt.date.fromisoformat(wh[-1]["started_at"][:10]) - d0).days + 1)
           if str(d0 + dt.timedelta(days=i)) not in daysw]
p(f"- 期間內沒有任何 watchdog 列的日期：{len(missing)} 天：" + "、".join(m[5:] for m in missing))
# 每日鏈完成 vs 21:10
p("- 每日鏈最晚完成時刻（M2a 全部 launchd 觸發）："
  + (max((b["end"] for b in blocks if "end" in b), key=tod_min).strftime("%m-%d %H:%M")))
p()

# ---------------------------------------------------------------- M11 晚間鏈
p("## M11 com.cpbl.postseason-evening 每晚喚醒與動作（postseason-evening-YYYYMMDD.log）")
p()
p("| 日期 | 分期 | 當日一軍場 | 喚醒 | quiet | idle | FATAL | 有動作行 | 首／末動作 | 喚醒間隔>10分 |")
p("|---|---|---|---|---|---|---|---|---|---|")
for f in sorted(glob.glob(os.path.join(LOGS, "postseason-evening-2*.log"))):
    d = dt.datetime.strptime(re.search(r"(\d{8})", f).group(1), "%Y%m%d").date()
    wake, quiet, idle, fatal, acts, gaps = [], 0, 0, 0, [], 0
    for ln in open(f):
        m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)", ln)
        if not m:
            continue
        t, msg = local(m.group(1)), m.group(2)
        if msg.startswith("plan →") or msg.startswith("FATAL: plan"):
            wake.append(t)
            quiet += msg == "plan → quiet"
            idle += msg == "plan → idle"
            fatal += msg.startswith("FATAL")
        if re.match(r"(scrape →|sync →|boxpa sync →|boxpa-detail|boxpa-tracking|plan → (scrape|sync))", msg):
            acts.append(t)
    for a, b in zip(wake, wake[1:], strict=False):
        gaps += (b - a).total_seconds() > 600
    kinds = "".join(sorted(played_by_date.get(d, set()) & {"A", "E", "C"})) or "-"
    fa = f"{acts[0]:%H:%M}／{acts[-1]:%H:%M}" if acts else "-"
    p(f"| {d:%m-%d} | {phase(d)} | {kinds} | {len(wake)} | {quiet} | {idle} | {fatal} | {len(acts)} | {fa} | {gaps} |")
p()
p("- 喚醒＝`plan →` 或 `FATAL: plan` 行數；一天 288 次＝Mac 全天醒著。FATAL 全數為 psycopg_pool.PoolTimeout（見 R1 本文）")
lb = []
for f in sorted(glob.glob(os.path.join(LOGS, "postseason-evening-2*.log"))):
    for ln in open(f):
        if "refresh lock busy" in ln:
            lb.append(ln[1:20])
p(f"- 晚間鏈 `refresh lock busy`：{len(lb)} 次：" + "、".join(lb))
p()

# ---------------------------------------------------------------- M12 alert-watch
p("## M12 com.cpbl.alert-watch")
p()
kinds = collections.Counter(re.sub(r"[\d:.T+-]{19,}", "", ln.split("] ", 1)[-1]).strip()[:60] for ln in aw)
for k, v in kinds.most_common():
    p(f"- `{k}`：{v}")
ev = json.load(open(os.path.join(LOGS, "alert-watch", "state.json")))["evening"]
p(f"- state.json evening 段：night={ev.get('night')} armed={ev.get('armed')} success_sent={ev.get('success_sent')}")
p()

# ---------------------------------------------------------------- M13 pmset
p("## M13 Mac 睡眠（`pmset -g log`，唯讀；系統只保留近幾天）")
p()
try:
    pm = subprocess.run(["pmset", "-g", "log"], capture_output=True, text=True, timeout=60).stdout.splitlines()
except Exception as exc:  # noqa: BLE001
    pm = []
    p(f"- pmset 讀取失敗：{exc}")
sl = collections.Counter()
dw = collections.Counter()
sleeps = []
for ln in pm:
    m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) [+-]\d{4} (Sleep|DarkWake|Wake)\s", ln)
    if not m:
        continue
    t = local(m.group(1))
    if m.group(2) == "Sleep":
        sl[t.date()] += 1
        sleeps.append(t)
    elif m.group(2) == "DarkWake":
        dw[t.date()] += 1
if pm:
    first = next((ln[:19] for ln in pm if re.match(r"\d{4}-", ln)), "-")
    p(f"- 覆蓋起點：{first}")
    for d in sorted(set(sl) | set(dw)):
        p(f"  - {d}：Sleep {sl[d]} 次、DarkWake {dw[d]} 次")
    for b in blocks:
        if "end" in b and (b["end"] - b["start"]).total_seconds() > 3600 and sleeps and b["start"] >= sleeps[0]:
            n = sum(1 for t in sleeps if b["start"] <= t <= b["end"])
            p(f"- 每日鏈 {b['start']:%m-%d %H:%M}→{b['end']:%H:%M}（{(b['end'] - b['start']).total_seconds() / 60:.0f} 分）期間 Sleep {n} 次")
p()

print("\n".join(OUT))
