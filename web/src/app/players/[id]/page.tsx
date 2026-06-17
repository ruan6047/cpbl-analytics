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
  { key: "era", label: "ERA", dp: 2, get: eraOf },
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
    detail.discipline(id, role).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
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
  const monthData = useMemo(
    () => MONTHS.filter((mo) => byName[mo]).map((mo) => ({ name: mo.replace("月", ""), v: metric.get(byName[mo]) })),
    [byName, metric],
  );
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

      {/* 本季成績卡 */}
      {s && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-ink">本季成績</h2>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            {(role === "batting"
              ? [["打擊率", f3(s.avg), true], ["上壘率", f3(s.obp), false], ["長打率", f3(s.slg), false],
                 ["OPS", f3(s.ops), true], ["全壘打", String(s.hr ?? "—"), false], ["打點", String(s.rbi ?? "—"), false],
                 ["安打", String(s.h ?? "—"), false], ["盜壘", String(s.sb ?? "—"), false], ["打席", String(s.pa ?? "—"), false],
                 ["出賽", String(s.g ?? "—"), false]]
              : [["防禦率", numOf(s.era)?.toFixed(2) ?? "—", true], ["WHIP", numOf(s.whip)?.toFixed(2) ?? "—", false],
                 ["勝-敗", `${s.w ?? 0}-${s.l ?? 0}`, false], ["局數", numOf(s.ip)?.toFixed(1) ?? "—", false],
                 ["三振", String(s.so ?? "—"), true], ["K9", numOf(s.k9)?.toFixed(2) ?? "—", false],
                 ["救援", String(s.sv ?? "—"), false], ["中繼", String(s.hld ?? "—"), false],
                 ["自責", String(s.er ?? "—"), false], ["出賽", String(s.g ?? "—"), false]]
            ).map(([l, v, a]) => <StatTile key={l as string} label={l as string} value={v as string} accent={a as boolean} />)}
          </div>
        </section>
      )}

      {/* 百分位 */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-ink">官方進階數據 · 百分位 PR</h2>
        <Card>
          {prRows.length === 0 ? (
            <p className="py-8 text-center text-sm text-faint">{advanced === null ? "載入中…" : "無官方進階資料"}</p>
          ) : (
            <div className="space-y-1.5">
              {prRows.map((d) => <PercentileBar key={d.name} name={d.name} value={d.value} pr={d.pr} def={d.def} />)}
            </div>
          )}
          <p className="mt-3 text-[11px] text-faint">
            來源 stats.cpbl 官方 TrackMan；色條＝官方 PR（藍低→紅高）。{role === "batting" ? "打者進攻數值" : "投手被打數值"}。
          </p>
        </Card>
      </section>

      {/* 擊球落點 + 進壘點 */}
      <section className="mb-8 grid gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="mb-2 text-sm font-medium text-muted">擊球落點（點＝擊球初速 藍低→紅高，{disc?.spray.length ?? 0} 球）</h3>
          {disc && disc.spray.length > 0 ? <SprayChart points={disc.spray} />
            : <p className="py-12 text-center text-sm text-faint">{disc === null ? "載入中…" : "無擊球追蹤資料"}</p>}
        </Card>
        <Card>
          <h3 className="mb-2 text-sm font-medium text-muted">進壘點（紅＝揮空、藍＝揮棒、灰＝未揮棒，{disc?.points.length ?? 0} 球）</h3>
          {disc && disc.points.length > 0 ? <ZoneScatter points={disc.points} />
            : <p className="py-12 text-center text-sm text-faint">{disc === null ? "載入中…" : "無逐球資料"}</p>}
          {disc && disc.summary.swing_pct != null && (
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              <span>揮棒 {disc.summary.swing_pct}%</span><span>揮空 {disc.summary.whiff_pct}%</span>
              <span>接觸 {disc.summary.contact_pct}%</span><span>CSW {disc.summary.csw_pct}%</span>
              <span>追打 {disc.summary.chase_pct}%（近似）</span>
            </div>
          )}
        </Card>
      </section>

      {/* 範圍切換 + 逐月趨勢 */}
      <section className="mb-8">
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
            <h3 className="text-sm font-medium text-muted">逐月趨勢</h3>
            <select value={monthMetric} onChange={(e) => setMonthMetric(e.target.value)}
              className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none focus:border-ink">
              {metrics.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
          {monthData.length === 0 ? <p className="py-8 text-center text-sm text-faint">無資料</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={monthData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid stroke="#eef2f7" />
                <XAxis dataKey="name" {...axis} />
                <YAxis {...axis} domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => v?.toFixed(metric.dp)} />
                <Line type="monotone" dataKey="v" name={metric.label} stroke="#0a2540" strokeWidth={2} dot={{ r: 3, fill: "#d62839" }} />
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
