"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SprayChart } from "@/components/spray-chart";
import { Card, PercentileBar, StatTile, TeamLogo } from "@/components/ui";
import { ZoneScatter } from "@/components/zone-scatter";
import { detail, type PlayerProfile, type StatRow } from "@/lib/client";
import { codeFromName, teamColor } from "@/lib/teams";

type Role = "batting" | "pitching";
type Disc = {
  summary: Record<string, number | null>;
  points: { x: number; y: number; sw: boolean; wh: boolean }[];
  spray: { dir: number; dist: number; ev: number | null }[];
};

const numOf = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === "" ? null : Number(v);
const f3 = (v: number | string | null | undefined) => {
  const x = numOf(v);
  return x === null ? "—" : x.toFixed(3).replace(/^0\./, ".");
};
const ipOf = (r: StatRow) => {
  const c = numOf(r.inning_pitched_cnt);
  return c === null ? null : c + (numOf(r.inning_pitched_div3) ?? 0) / 3;
};
const eraOf = (r: StatRow) => {
  const ip = ipOf(r), er = numOf(r.earned_runs);
  return ip && ip > 0 && er !== null ? (er * 9) / ip : null;
};

// 官方進階 + PR
type Adv = { key: string; pr: string; bl: string; pl: string; def: string; kind: "kmh" | "pct" | "rate3" };
const ADV: Adv[] = [
  { key: "ev", pr: "ev_pr", bl: "擊球初速", pl: "被擊球初速", def: "平均擊球初速 km/h", kind: "kmh" },
  { key: "max_ev", pr: "max_ev_pr", bl: "最高初速", pl: "被最高初速", def: "單季最高擊球初速 km/h", kind: "kmh" },
  { key: "brlp", pr: "brlp_pr", bl: "Barrel%", pl: "被Barrel%", def: "出色擊球率", kind: "pct" },
  { key: "hardhitp", pr: "hardhitp_pr", bl: "強擊球%", pl: "被強擊球%", def: "強勁擊球占比", kind: "pct" },
  { key: "woba", pr: "woba_pr", bl: "wOBA", pl: "被wOBA", def: "加權上壘率（官方）", kind: "rate3" },
  { key: "iso", pr: "iso_pr", bl: "ISO", pl: "被ISO", def: "純長打率", kind: "rate3" },
  { key: "slg", pr: "slg_pr", bl: "長打率", pl: "被長打率", def: "SLG", kind: "rate3" },
  { key: "obp", pr: "obp_pr", bl: "上壘率", pl: "被上壘率", def: "OBP", kind: "rate3" },
  { key: "chasep", pr: "chasep_pr", bl: "追打%", pl: "誘追打%", def: "好球帶外揮棒率", kind: "pct" },
  { key: "whiffp", pr: "whiffp_pr", bl: "揮空%", pl: "誘揮空%", def: "揮棒落空率", kind: "pct" },
  { key: "kp", pr: "kp_pr", bl: "K%", pl: "奪三振%", def: "三振率", kind: "pct" },
  { key: "bbp", pr: "bbp_pr", bl: "BB%", pl: "被保送%", def: "保送率", kind: "pct" },
];
const fmtAdv = (v: number, k: Adv["kind"]) =>
  k === "kmh" ? v.toFixed(1) : k === "pct" ? `${(v * 100).toFixed(1)}%` : v.toFixed(3).replace(/^0\./, ".");

type Metric = { key: string; label: string; dp: number; get: (r: StatRow) => number | null };
const BAT_METRICS: Metric[] = [
  { key: "ops", label: "OPS", dp: 3, get: (r) => numOf(r.ops) },
  { key: "avg", label: "打擊率", dp: 3, get: (r) => numOf(r.avg) },
  { key: "obp", label: "上壘率", dp: 3, get: (r) => numOf(r.obp) },
  { key: "slg", label: "長打率", dp: 3, get: (r) => numOf(r.slg) },
  { key: "hits", label: "安打", dp: 0, get: (r) => numOf(r.hits) },
  { key: "home_runs", label: "全壘打", dp: 0, get: (r) => numOf(r.home_runs) },
  { key: "rbi", label: "打點", dp: 0, get: (r) => numOf(r.rbi) },
];
const PIT_METRICS: Metric[] = [
  { key: "era", label: "ERA", dp: 2, get: (r) => (r.era != null ? numOf(r.era) : eraOf(r)) },
  { key: "whip", label: "WHIP", dp: 2, get: (r) => numOf(r.whip) },
  { key: "so", label: "三振", dp: 0, get: (r) => numOf(r.so) },
  { key: "hits", label: "被安打", dp: 0, get: (r) => numOf(r.hits) },
  { key: "bb", label: "四壞", dp: 0, get: (r) => numOf(r.bb) },
];
const MONTHS = ["三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月"];
const axis = { tick: { fill: "#5b6b7a", fontSize: 12 }, stroke: "#cbd5e1" };

function Tabs<T extends string>({ opts, v, set }: { opts: { v: T; label: string }[]; v: T; set: (x: T) => void }) {
  return (
    <div className="inline-flex gap-1 rounded-lg bg-surface-2 p-1">
      {opts.map((o) => (
        <button key={o.v} onClick={() => set(o.v)}
          className={`rounded-md px-3 py-1 text-sm transition ${v === o.v ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const PITCH_LABEL: Record<string, string> = { fastball: "速球", breakingball: "變化球" };

function ArsenalTable({ items, role }: { items: StatRow[]; role: Role }) {
  return (
    <table className="w-full text-xs">
      <thead className="text-left text-muted">
        <tr>
          <th className="py-1 font-medium">球種</th>
          <th className="py-1 text-right font-medium">{role === "batting" ? "面對" : "用球"}%</th>
          <th className="py-1 text-right font-medium">均速</th>
          <th className="py-1 text-right font-medium">揮空%</th>
          <th className="py-1 text-right font-medium">擊球初速</th>
        </tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {items.map((r) => (
          <tr key={String(r.pitch_type)} className="border-t border-line">
            <td className="py-1.5 font-sans text-ink">{PITCH_LABEL[String(r.pitch_type)] ?? String(r.pitch_type)}</td>
            <td className="py-1.5 text-right">{String(r.usage)}%</td>
            <td className="py-1.5 text-right">{r.avg_speed ?? "—"}</td>
            <td className="py-1.5 text-right">{r.whiff_pct ?? "—"}%</td>
            <td className="py-1.5 text-right text-muted">{r.avg_ev ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [role, setRole] = useState<Role>("batting");
  const [scope, setScope] = useState<"season" | "career">("season");
  const [kinds, setKinds] = useState<string[]>(["A"]);
  const [season, setSeason] = useState<{ batting: StatRow | null; pitching: StatRow | null } | null>(null);
  const [advanced, setAdvanced] = useState<{ batting: StatRow | null; pitching: StatRow | null } | null>(null);
  const [disc, setDisc] = useState<Disc | null>(null);
  const [arsenal, setArsenal] = useState<StatRow[] | null>(null);
  const [trend, setTrend] = useState<StatRow[] | null>(null);
  const [splits, setSplits] = useState<StatRow[] | null>(null);
  const [monthMetric, setMonthMetric] = useState("ops");

  useEffect(() => {
    detail.profile(id).then((d) => {
      if (!d.player) return setNotFound(true);
      setProfile(d.player);
      setRole(d.player.is_batter ? "batting" : "pitching");
    }).catch(() => setNotFound(true));
    detail.season(id).then(setSeason).catch(() => setSeason(null));
    detail.advanced(id).then(setAdvanced).catch(() => setAdvanced(null));
  }, [id]);

  useEffect(() => {
    setMonthMetric(role === "batting" ? "ops" : "era");
    setDisc(null);
    setArsenal(null);
    setTrend(null);
    detail.discipline(id, role).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
    detail.arsenal(id, role).then((d) => setArsenal(d.items)).catch(() => setArsenal([]));
    detail.trend(id, role).then((d) => setTrend(d.items)).catch(() => setTrend([]));
  }, [id, role]);

  useEffect(() => {
    if (!profile) return;
    const year = scope === "season" ? 2026 : 9999;
    const k = scope === "season" ? "A" : (kinds.length ? kinds.join(",") : "A");
    detail.splits(id, role, year, k).then((d) => setSplits(d.items)).catch(() => setSplits([]));
  }, [id, role, scope, kinds, profile]);

  const byName = useMemo(() => {
    const m: Record<string, StatRow> = {};
    for (const r of splits ?? []) m[String(r.item_name)] = r;
    return m;
  }, [splits]);
  const metrics = role === "batting" ? BAT_METRICS : PIT_METRICS;
  const metric = metrics.find((m) => m.key === monthMetric) ?? metrics[0];
  const monthData = useMemo(() => {
    if (scope === "season") return (trend ?? []).map((r) => ({ name: String(r.name), v: metric.get(r) }));
    return MONTHS.filter((mo) => byName[mo]).map((mo) => ({ name: mo.replace("月", ""), v: metric.get(byName[mo]) }));
  }, [scope, trend, byName, metric]);
  const prRows = useMemo(() => {
    const a = advanced ? (role === "batting" ? advanced.batting : advanced.pitching) : null;
    if (!a) return [];
    return ADV.map((m) => {
      const val = numOf(a[m.key]), pr = numOf(a[m.pr]);
      return { name: role === "batting" ? m.bl : m.pl, def: m.def,
        value: val === null ? "—" : fmtAdv(val, m.kind), pr: pr === null ? null : Math.round(pr) };
    }).filter((d): d is { name: string; def: string; value: string; pr: number } => d.pr !== null);
  }, [advanced, role]);

  if (notFound) return <p className="text-sm text-muted">查無此球員。</p>;
  if (!profile) return <p className="text-sm text-muted">載入中…</p>;

  const roles: { v: Role; label: string }[] = [];
  if (profile.is_batter) roles.push({ v: "batting", label: "打擊" });
  if (profile.is_pitcher) roles.push({ v: "pitching", label: "投球" });
  const s = season ? (role === "batting" ? season.batting : season.pitching) : null;
  const tc = codeFromName(profile.team);

  return (
    <div>
      {/* Hero */}
      <div className="card mb-6 overflow-hidden">
        <div className="h-1.5" style={{ background: teamColor(tc) }} />
        <div className="flex flex-wrap items-end justify-between gap-4 p-5">
          <div className="flex items-center gap-3.5">
            <TeamLogo code={tc} size={48} />
            <div>
              <h1 className="text-3xl font-bold text-ink">{profile.name}</h1>
              <p className="mt-1 text-sm text-muted">
                {profile.team}
                {profile.bats && <span className="ml-3">打 {profile.bats}</span>}
                {profile.throws && <span className="ml-2">投 {profile.throws}</span>}
              </p>
            </div>
          </div>
          {s && role === "batting" && (
            <div className="font-mono text-lg tabular-nums text-ink">
              {f3(s.avg)}/{f3(s.obp)}/{f3(s.slg)} <span className="text-accent">OPS {f3(s.ops)}</span>
            </div>
          )}
          {s && role === "pitching" && (
            <div className="font-mono text-lg tabular-nums text-ink">
              {numOf(s.era)?.toFixed(2) ?? "—"} ERA · {s.w ?? 0}-{s.l ?? 0} · {numOf(s.ip)?.toFixed(1) ?? "—"} 局
            </div>
          )}
        </div>
      </div>

      {roles.length > 1 && <div className="mb-5"><Tabs opts={roles} v={role} set={setRole} /></div>}

      {/* 本季成績 + 官方進階（並排兩欄） */}
      <section className="mb-6 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold text-ink">本季成績</h2>
          {s ? (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {(role === "batting"
                ? [["打擊率", f3(s.avg), true], ["上壘率", f3(s.obp), false], ["長打率", f3(s.slg), false],
                   ["OPS", f3(s.ops), true], ["全壘打", String(s.hr ?? "—"), false], ["打點", String(s.rbi ?? "—"), false],
                   ["安打", String(s.h ?? "—"), false], ["二安", String(s.b2 ?? "—"), false], ["三安", String(s.b3 ?? "—"), false],
                   ["得分", String(s.r ?? "—"), false], ["盜壘", String(s.sb ?? "—"), false], ["四壞", String(s.bb ?? "—"), false],
                   ["三振", String(s.so ?? "—"), false], ["打席", String(s.pa ?? "—"), false], ["出賽", String(s.g ?? "—"), false]]
                : [["防禦率", numOf(s.era)?.toFixed(2) ?? "—", true], ["WHIP", numOf(s.whip)?.toFixed(2) ?? "—", false],
                   ["勝-敗", `${s.w ?? 0}-${s.l ?? 0}`, false], ["救援", String(s.sv ?? "—"), false],
                   ["中繼", String(s.hld ?? "—"), false], ["局數", numOf(s.ip)?.toFixed(1) ?? "—", false],
                   ["先發", String(s.gs ?? "—"), false], ["三振", String(s.so ?? "—"), true],
                   ["K9", numOf(s.k9)?.toFixed(2) ?? "—", false], ["被安", String(s.h ?? "—"), false],
                   ["被轟", String(s.hr ?? "—"), false], ["四壞", String(s.bb ?? "—"), false],
                   ["失分", String(s.r ?? "—"), false], ["自責", String(s.er ?? "—"), false], ["出賽", String(s.g ?? "—"), false]]
              ).map(([l, v, a]) => <StatTile key={l as string} label={l as string} value={v as string} accent={a as boolean} />)}
            </div>
          ) : <p className="text-sm text-muted">本季無{role === "batting" ? "打擊" : "投球"}成績。</p>}
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold text-ink">官方進階 · 百分位 PR</h2>
          <Card>
            {prRows.length === 0 ? (
              <p className="py-8 text-center text-sm text-faint">{advanced === null ? "載入中…" : "無官方進階資料"}</p>
            ) : (
              <div className="space-y-1">
                {prRows.map((d) => <PercentileBar key={d.name} name={d.name} value={d.value} pr={d.pr} def={d.def} />)}
              </div>
            )}
            <p className="mt-2.5 text-[11px] text-faint">
              stats.cpbl 官方 TrackMan；色條＝PR（藍低→紅高）。{role === "batting" ? "打者進攻" : "投手被打"}數值。
            </p>
          </Card>
        </div>
      </section>

      {/* 擊球落點 + 進壘點（左 2/3 放大） + 好球帶紀律（右側直欄） */}
      <section className="mb-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="grid gap-x-4 sm:grid-cols-2">
            <div className="relative flex flex-col">
              <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">擊球落點（藍低→紅高，{disc?.spray.length ?? 0} 球）</h3>
              {disc && disc.spray.length > 0 ? <div className="mt-auto mb-[13%]"><SprayChart points={disc.spray} /></div>
                : <p className="py-12 text-center text-sm text-faint">{disc === null ? "載入中…" : "無擊球追蹤資料"}</p>}
            </div>
            <div className="relative">
              <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">進壘點（紅揮空/藍揮棒/灰未揮，{disc?.points.length ?? 0} 球）</h3>
              {disc && disc.points.length > 0 ? <ZoneScatter points={disc.points} />
                : <p className="py-12 text-center text-sm text-faint">{disc === null ? "載入中…" : "無逐球資料"}</p>}
            </div>
          </div>
        </Card>
        <div className="flex flex-col gap-6">
          <Card>
            <h3 className="mb-3 text-sm font-medium text-muted">好球帶紀律</h3>
            {disc && disc.summary.swing_pct != null ? (
              <>
                <div className="space-y-2">
                  {([["揮棒%", "swing_pct"], ["揮空%", "whiff_pct"], ["接觸%", "contact_pct"],
                     ["CSW%", "csw_pct"], ["追打%", "chase_pct"], ["好球帶%", "zone_pct"]] as const)
                    .filter(([, k]) => disc.summary[k] != null)
                    .map(([label, k]) => (
                      <div key={k} className="flex items-center justify-between border-b border-line pb-1.5 text-xs last:border-0">
                        <span className="text-muted">{label}</span>
                        <span className="font-mono tabular-nums text-ink">{disc.summary[k]}%</span>
                      </div>
                    ))}
                </div>
                <p className="mt-2 text-[10px] leading-snug text-faint">全為逐球追蹤樣本（部分球場未配置設備，涵蓋場次少於全季），與官方進階全季數值會有差異。</p>
              </>
            ) : <p className="py-12 text-center text-sm text-faint">{disc === null ? "載入中…" : "無逐球資料"}</p>}
          </Card>
          <Card>
            <h3 className="mb-3 text-sm font-medium text-muted">球種應對（{role === "batting" ? "面對" : "配球"}）</h3>
            {arsenal === null ? <p className="py-6 text-center text-sm text-faint">載入中…</p>
              : arsenal.length === 0 ? <p className="py-6 text-center text-sm text-faint">無逐球資料</p>
              : <ArsenalTable items={arsenal} role={role} />}
          </Card>
        </div>
      </section>

      {/* 範圍切換 + 逐月趨勢 */}
      <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <Tabs opts={[{ v: "season", label: "本季" }, { v: "career", label: "生涯" }]} v={scope} set={setScope} />
          {scope === "career" && (
            <div className="inline-flex flex-wrap gap-2">
              {([["A", "例行賽"], ["C", "總冠軍"], ["E", "季後賽"]] as const).map(([k, label]) => {
                const on = kinds.includes(k);
                return (
                  <button key={k} onClick={() => setKinds(on ? (kinds.length > 1 ? kinds.filter((x) => x !== k) : kinds) : [...kinds, k])}
                    className={`rounded-full px-3 py-1 text-sm transition ${on ? "bg-accent text-white" : "bg-surface-2 text-muted hover:text-ink"}`}>
                    {label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <Card>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-medium text-muted">{scope === "season" ? "賽季走勢（逐場累積）" : "逐月趨勢"}</h3>
            <select value={monthMetric} onChange={(e) => setMonthMetric(e.target.value)}
              className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none focus:border-ink">
              {metrics.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
          {monthData.length === 0 ? <p className="py-8 text-center text-sm text-faint">無資料</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={monthData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid stroke="#eef2f7" />
                <XAxis dataKey="name" {...axis} minTickGap={28} />
                <YAxis {...axis} domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => v?.toFixed(metric.dp)} />
                <Line type="monotone" dataKey="v" name={metric.label} stroke="#0a2540" strokeWidth={2}
                  dot={monthData.length > 18 ? false : { r: 3, fill: "#d62839" }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </section>

      {/* 分項明細 */}
      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-ink">分項明細</h2>
        {!splits ? <p className="text-sm text-muted">載入中…</p>
          : splits.length === 0 ? <p className="text-sm text-muted">此範圍無分項資料。</p> : (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-muted">
                <tr>
                  {(role === "batting"
                    ? ["分項", "打席", "打數", "安打", "全壘打", "打點", "四壞", "三振", "打擊率", "OPS"]
                    : ["分項", "局數", "面對", "被安", "被轟", "四壞", "三振", "自責", "ERA"]
                  ).map((h) => <th key={h} className="whitespace-nowrap px-2.5 py-2.5 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {splits.map((r, i) => (
                  <tr key={i} className="border-t border-line hover:bg-surface-2">
                    <td className="whitespace-nowrap px-2.5 py-2 font-sans text-ink">{String(r.item_name)}</td>
                    {role === "batting" ? (
                      <>
                        <td className="px-2.5 py-2">{String(r.plate_appearances ?? "—")}</td>
                        <td className="px-2.5 py-2 text-muted">{String(r.at_bats ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.hits ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.home_runs ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.rbi ?? "—")}</td>
                        <td className="px-2.5 py-2 text-muted">{String(r.bb ?? "—")}</td>
                        <td className="px-2.5 py-2 text-muted">{String(r.so ?? "—")}</td>
                        <td className="px-2.5 py-2">{f3(r.avg)}</td>
                        <td className="px-2.5 py-2 text-accent">{f3(r.ops)}</td>
                      </>
                    ) : (
                      <>
                        <td className="px-2.5 py-2">{ipOf(r)?.toFixed(1) ?? "—"}</td>
                        <td className="px-2.5 py-2 text-muted">{String(r.plate_appearances ?? "—")}</td>
                        <td className="px-2.5 py-2 text-muted">{String(r.hits ?? "—")}</td>
                        <td className="px-2.5 py-2 text-muted">{String(r.home_runs ?? "—")}</td>
                        <td className="px-2.5 py-2 text-muted">{String(r.bb ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.so ?? "—")}</td>
                        <td className="px-2.5 py-2 text-accent">{String(r.earned_runs ?? "—")}</td>
                        <td className="px-2.5 py-2 text-accent">{eraOf(r)?.toFixed(2) ?? "—"}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="flex gap-4 text-sm">
        <Link href="/matchups" className="text-accent hover:underline">投打對決 →</Link>
        <Link href="/batters" className="text-muted hover:text-ink">← 返回排行</Link>
      </div>
    </div>
  );
}
