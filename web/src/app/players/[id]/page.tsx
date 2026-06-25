"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LaEvScatter } from "@/components/la-ev-scatter";
import { SprayChart } from "@/components/spray-chart";
import { Card, LetterBadge, PercentileBar, StatTile, TeamLogo } from "@/components/ui";
import { type HeatMetric, PerfHeatmap } from "@/components/perf-heatmap";
import { ZoneScatter } from "@/components/zone-scatter";
import { detail, type PlayerProfile, type StatRow } from "@/lib/client";
import { fmtIP, fmtIPParts } from "@/lib/format";
import { codeFromName, eraBadge, teamColor, teamShort } from "@/lib/teams";

type Role = "batting" | "pitching";
type Disc = {
  summary: Record<string, number | null>;
  quality: Record<string, number | null>;
  points: { x: number; y: number; sw: boolean; wh: boolean; result: string; ev: number | null }[];
  spray: { dir: number; dist: number; ev: number | null; result: string }[];
  batted: { la: number; ev: number; result: string }[];
};

const numOf = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === "" ? null : Number(v);
const n0 = (v: number | string | null | undefined) => (v === null || v === undefined ? "—" : String(v));
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
type Adv = { key: string; pr: string; bl: string; pl: string; def: string; kind: "kmh" | "pct" | "rate3" | "cnt" };
const ADV: Adv[] = [
  { key: "ev", pr: "ev_pr", bl: "擊球初速", pl: "被擊球初速", def: "平均擊球初速 km/h", kind: "kmh" },
  { key: "max_ev", pr: "max_ev_pr", bl: "最高初速", pl: "被最高初速", def: "單季最高擊球初速 km/h", kind: "kmh" },
  { key: "brlp", pr: "brlp_pr", bl: "Barrel%", pl: "被Barrel%", def: "出色擊球率", kind: "pct" },
  { key: "brl", pr: "brl_pr", bl: "Barrel數", pl: "被Barrel數", def: "出色擊球次數", kind: "cnt" },
  { key: "hardhitp", pr: "hardhitp_pr", bl: "強擊球%", pl: "被強擊球%", def: "強勁擊球占比", kind: "pct" },
  { key: "woba", pr: "woba_pr", bl: "wOBA", pl: "被wOBA", def: "加權上壘率（官方）", kind: "rate3" },
  { key: "ba", pr: "ba_pr", bl: "打擊率", pl: "被打擊率", def: "BA", kind: "rate3" },
  { key: "iso", pr: "iso_pr", bl: "ISO", pl: "被ISO", def: "純長打率", kind: "rate3" },
  { key: "slg", pr: "slg_pr", bl: "長打率", pl: "被長打率", def: "SLG", kind: "rate3" },
  { key: "obp", pr: "obp_pr", bl: "上壘率", pl: "被上壘率", def: "OBP", kind: "rate3" },
  { key: "chasep", pr: "chasep_pr", bl: "追打%", pl: "誘追打%", def: "好球帶外揮棒率", kind: "pct" },
  { key: "whiffp", pr: "whiffp_pr", bl: "揮空%", pl: "誘揮空%", def: "揮棒落空率", kind: "pct" },
  { key: "kp", pr: "kp_pr", bl: "K%", pl: "奪三振%", def: "三振率", kind: "pct" },
  { key: "bbp", pr: "bbp_pr", bl: "BB%", pl: "被保送%", def: "保送率", kind: "pct" },
];
const fmtAdv = (v: number, k: Adv["kind"]) =>
  k === "kmh" ? v.toFixed(1) : k === "cnt" ? String(Math.round(v))
    : k === "pct" ? `${(v * 100).toFixed(1)}%` : v.toFixed(3).replace(/^0\./, ".");

// 擊球品質與彈道（讀 advanced.metrics jsonb；官方 /rankings 全套）
const _pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const _kmh = (v: number) => v.toFixed(1);
const _m = (v: number) => `${v.toFixed(1)}m`;
const _deg = (v: number) => `${v.toFixed(1)}°`;
const _cnt = (v: number) => String(Math.round(v));
const QUALITY_GROUPS: { title: string; items: { k: string; label: string; fmt: (v: number) => string }[] }[] = [
  { title: "擊球品質", items: [
    { k: "evAvg", label: "平均初速", fmt: _kmh }, { k: "ev90Th", label: "EV90", fmt: _kmh },
    { k: "evMax", label: "最大初速", fmt: _kmh }, { k: "laAvg", label: "平均仰角", fmt: _deg },
    { k: "distanceAvgHr", label: "全壘打均距", fmt: _m }, { k: "distanceMax", label: "最遠擊球", fmt: _m },
  ] },
  { title: "彈道分布", items: [
    { k: "gbp", label: "滾地球%", fmt: _pct }, { k: "ldp", label: "平飛球%", fmt: _pct },
    { k: "fbp", label: "高飛球%", fmt: _pct }, { k: "pup", label: "內野飛球%", fmt: _pct },
  ] },
  { title: "拉打方向", items: [
    { k: "pullp", label: "拉打%", fmt: _pct }, { k: "straightp", label: "中間%", fmt: _pct },
    { k: "oppop", label: "推打%", fmt: _pct },
  ] },
  { title: "強擊 / Barrel", items: [
    { k: "hardHitp", label: "強擊球%", fmt: _pct }, { k: "barrels", label: "Barrel 數", fmt: _cnt },
    { k: "brlsPAp", label: "Barrel/PA", fmt: _pct },
  ] },
];

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

const ipText = (r: StatRow) =>
  fmtIPParts(r.inning_pitched_cnt as number | null, r.inning_pitched_div3 as number | null);

function VsTeamTable({ items, role }: { items: StatRow[]; role: Role }) {
  const cols: { h: string; cell: (r: StatRow) => string; tone?: string }[] = role === "batting"
    ? [{ h: "PA", cell: (r) => n0(r.plate_appearances) },
       { h: "安打", cell: (r) => n0(r.hits) },
       { h: "HR", cell: (r) => n0(r.home_runs) },
       { h: "打點", cell: (r) => n0(r.rbi) },
       { h: "OPS", cell: (r) => f3(numOf(r.ops)), tone: "text-ink" }]
    : [{ h: "局數", cell: ipText },
       { h: "ERA", cell: (r) => numOf(r.era)?.toFixed(2) ?? "—", tone: "text-ink" },
       { h: "WHIP", cell: (r) => numOf(r.whip)?.toFixed(2) ?? "—" },
       { h: "被安", cell: (r) => n0(r.hits) },
       { h: "三振", cell: (r) => n0(r.so) }];
  return (
    <div className="max-h-[230px] overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-surface text-left text-muted">
          <tr>
            <th className="py-1 font-medium">對手</th>
            {cols.map((c) => <th key={c.h} className="py-1 text-right font-medium">{c.h}</th>)}
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {items.map((r) => (
            <tr key={String(r.fight_team_name)} className="border-t border-line">
              <td className="py-1.5 font-sans text-ink">{teamShort(codeFromName(String(r.fight_team_name))) || String(r.fight_team_name)}</td>
              {cols.map((c) => <td key={c.h} className={`py-1.5 text-right ${c.tone ?? ""}`}>{c.cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CareerTable({ seasons, role }: { seasons: StatRow[]; role: Role }) {
  const cols: { h: string; cell: (r: StatRow) => string; tone?: string }[] = role === "batting"
    ? [{ h: "G", cell: (r) => n0(r.g) }, { h: "PA", cell: (r) => n0(r.pa) },
       { h: "AVG", cell: (r) => f3(numOf(r.avg)) }, { h: "OBP", cell: (r) => f3(numOf(r.obp)) },
       { h: "SLG", cell: (r) => f3(numOf(r.slg)) }, { h: "OPS", cell: (r) => f3(numOf(r.ops)), tone: "text-ink" },
       { h: "HR", cell: (r) => n0(r.hr) }, { h: "打點", cell: (r) => n0(r.rbi) }, { h: "盜壘", cell: (r) => n0(r.sb) }]
    : [{ h: "G", cell: (r) => n0(r.g) }, { h: "先發", cell: (r) => n0(r.gs) },
       { h: "勝-敗", cell: (r) => `${r.w ?? 0}-${r.l ?? 0}` }, { h: "救援", cell: (r) => n0(r.sv) },
       { h: "局數", cell: (r) => fmtIP(r.ip as number | string | null) }, { h: "ERA", cell: (r) => numOf(r.era)?.toFixed(2) ?? "—", tone: "text-ink" },
       { h: "WHIP", cell: (r) => numOf(r.whip)?.toFixed(2) ?? "—" }, { h: "三振", cell: (r) => n0(r.so) },
       { h: "K9", cell: (r) => numOf(r.k9)?.toFixed(2) ?? "—" }];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">年度</th>
            <th className="px-3 py-2 font-medium">球隊</th>
            {cols.map((c) => <th key={c.h} className="px-3 py-2 text-right font-medium">{c.h}</th>)}
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {seasons.map((r) => (
            <tr key={String(r.year)} className="border-t border-line">
              <td className="px-3 py-2 font-sans text-ink">{String(r.year)}</td>
              <td className="px-3 py-2 font-sans text-muted">{String(r.teams ?? "—")}</td>
              {cols.map((c) => <td key={c.h} className={`px-3 py-2 text-right ${c.tone ?? ""}`}>{c.cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// 分項類別：官網 item_group_code 在打/投間不一致，改用 item_name 內容判斷（穩健、跨角色）。
const SPLIT_CATS: { key: string; label: string; test: (n: string) => boolean }[] = [
  { key: "ha", label: "主客場", test: (n) => n === "主場" || n === "客場" },
  { key: "order", label: "棒次", test: (n) => /第.+棒/.test(n) },
  { key: "hand", label: "左右投打", test: (n) => /右投|左投|右打|左打/.test(n) },
  { key: "natfor", label: "本土／外籍", test: (n) => n.includes("本土") || n.includes("外籍") },
  { key: "role", label: "先發／中繼／後援", test: (n) => /先發|中繼|救援|後援|最後一任/.test(n) },
  { key: "base", label: "壘上狀況", test: (n) => n.includes("跑者") || n.includes("滿壘") },
  { key: "out", label: "出局數", test: (n) => n.includes("出局") },
  { key: "inning", label: "局數", test: (n) => /第.+局/.test(n) },
  { key: "score", label: "比分", test: (n) => n.includes("比分") },
  { key: "month", label: "月份", test: (n) => /月$/.test(n) },
  { key: "venue", label: "球場", test: (n) => n.includes("球場") || n.includes("中心") || n.includes("巨蛋") },
];
const splitCat = (name: string) => SPLIT_CATS.find((c) => c.test(name))?.key ?? "other";

function SplitsTable({ rows, role }: { rows: StatRow[]; role: Role }) {
  const heads = role === "batting"
    ? ["分項", "打席", "打數", "安打", "全壘打", "打點", "四壞", "三振", "打擊率", "OPS"]
    : ["分項", "局數", "面對", "被安", "被轟", "四壞", "三振", "自責", "ERA"];
  return (
    <table className="w-full text-sm">
      <thead className="bg-surface-2 text-left text-muted">
        <tr>{heads.map((h) => <th key={h} className="whitespace-nowrap px-2.5 py-2.5 font-medium">{h}</th>)}</tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {rows.map((r, i) => (
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
  const [zoneView, setZoneView] = useState<"scatter" | "heat">("scatter");
  const [heatMetric, setHeatMetric] = useState<HeatMetric>("density");
  const [pitchMix, setPitchMix] = useState<{ bucket: string; n: number; fastball: number; breakingball: number }[] | null>(null);
  const [arsenal, setArsenal] = useState<StatRow[] | null>(null);
  const [fielding, setFielding] = useState<StatRow[] | null>(null);
  const [vsTeam, setVsTeam] = useState<StatRow[] | null>(null);
  const [career, setCareer] = useState<StatRow[] | null>(null);
  const [careerStats, setCareerStats] = useState<Awaited<ReturnType<typeof detail.careerStats>> | null>(null);
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
    detail.fielding(id).then((d) => setFielding(d.items)).catch(() => setFielding([]));
    detail.careerStats(id).then(setCareerStats).catch(() => setCareerStats(null));
  }, [id]);

  useEffect(() => {
    setMonthMetric(role === "batting" ? "ops" : "era");
    setDisc(null);
    setArsenal(null);
    setTrend(null);
    setVsTeam(null);
    setCareer(null);
    setPitchMix(null);
    detail.pitchMix(id, role).then((d) => setPitchMix(d.items)).catch(() => setPitchMix([]));
    detail.discipline(id, role).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
    detail.arsenal(id, role).then((d) => setArsenal(d.items)).catch(() => setArsenal([]));
    detail.trend(id, role).then((d) => setTrend(d.items)).catch(() => setTrend([]));
    detail.vsTeam(id, role).then((d) => setVsTeam(d.items)).catch(() => setVsTeam([]));
    detail.career(id, role).then((d) => setCareer(d.seasons)).catch(() => setCareer([]));
  }, [id, role]);

  useEffect(() => {
    if (!profile) return;
    const year = scope === "season" ? 2026 : 9999;
    const k = scope === "season" ? "A" : (kinds.length ? kinds.join(",") : "A");
    detail.splits(id, role, year, k).then((d) => setSplits(d.items)).catch(() => setSplits([]));
  }, [id, role, scope, kinds, profile]);

  const metrics = role === "batting" ? BAT_METRICS : PIT_METRICS;
  const metric = metrics.find((m) => m.key === monthMetric) ?? metrics[0];
  const monthData = useMemo(
    () => (trend ?? []).map((r) => ({ name: String(r.name), v: metric.get(r) })),
    [trend, metric],
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
              {profile.former_names?.length > 0 && (
                <p className="mt-0.5 text-[11px] text-faint">曾用名：{profile.former_names.join("、")}</p>
              )}
              <p className="mt-1 text-sm text-muted">
                {profile.team}
                {profile.bats && <span className="ml-3">打 {profile.bats}</span>}
                {profile.throws && <span className="ml-2">投 {profile.throws}</span>}
              </p>
              {careerStats?.teams && careerStats.teams.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {careerStats.teams.map((t) => {
                    const b = eraBadge(t.name, t.code);
                    return (
                      <span key={`${t.code}-${t.from}`}
                        className="inline-flex items-center gap-1 rounded-full py-0.5 pl-0.5 pr-2 text-[11px] font-medium"
                        style={{ background: `${b.color}1a`, color: b.color }}
                        title={`${t.name}　${t.from === t.to ? t.from : `${t.from}–${t.to}`}`}>
                        <LetterBadge meta={b} round />
                        {t.name}
                        <span className="font-mono tabular-nums opacity-70">
                          {t.from === t.to ? `'${String(t.from).slice(2)}` : `'${String(t.from).slice(2)}–'${String(t.to).slice(2)}`}
                        </span>
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
          {s && role === "batting" && (
            <div className="font-mono text-lg tabular-nums text-ink">
              {f3(s.avg)}/{f3(s.obp)}/{f3(s.slg)} <span className="text-accent">OPS {f3(s.ops)}</span>
            </div>
          )}
          {s && role === "pitching" && (
            <div className="font-mono text-lg tabular-nums text-ink">
              {numOf(s.era)?.toFixed(2) ?? "—"} ERA · {s.w ?? 0}-{s.l ?? 0} · {fmtIP(s.ip as number | string | null)} 局
            </div>
          )}
        </div>
      </div>

      {roles.length > 1 && <div className="mb-5"><Tabs opts={roles} v={role} set={setRole} /></div>}

      {/* 本季成績 + 官方進階（並排兩欄） */}
      <section className="mb-6 grid items-stretch gap-6 lg:grid-cols-2">
        <div className="flex flex-col">
          <h2 className="mb-3 text-lg font-semibold text-ink">本季成績</h2>
          {s ? (() => {
            const primary: [string, string, boolean][] = role === "batting"
              ? [["打擊率", f3(s.avg), true], ["上壘率", f3(s.obp), false], ["長打率", f3(s.slg), false],
                 ["OPS+", String(s.ops_plus ?? "—"), true], ["全壘打", String(s.hr ?? "—"), false], ["打點", String(s.rbi ?? "—"), false]]
              : [["防禦率", numOf(s.era)?.toFixed(2) ?? "—", true], ["WHIP", numOf(s.whip)?.toFixed(2) ?? "—", false],
                 ["FIP", numOf(s.fip)?.toFixed(2) ?? "—", false], ["三振", String(s.so ?? "—"), true],
                 ["勝-敗", `${s.w ?? 0}-${s.l ?? 0}`, false], ["ERA+", String(s.era_plus ?? "—"), false]];
            const secondary: [string, string][] = role === "batting"
              ? [["OPS", f3(s.ops)], ["安打", String(s.h ?? "—")], ["二安", String(s.b2 ?? "—")],
                 ["三安", String(s.b3 ?? "—")], ["壘打數", String(s.tb ?? "—")], ["得分", String(s.r ?? "—")],
                 ["盜壘", String(s.sb ?? "—")], ["盜壘失敗", String(s.cs ?? "—")], ["四壞", String(s.bb ?? "—")],
                 ["故四", String(s.ibb ?? "—")], ["觸身", String(s.hbp ?? "—")], ["三振", String(s.so ?? "—")],
                 ["雙殺打", String(s.gidp ?? "—")], ["犧觸", String(s.sh ?? "—")], ["犧飛", String(s.sf ?? "—")],
                 ["打席", String(s.pa ?? "—")], ["出賽", String(s.g ?? "—")]]
              : [["救援", String(s.sv ?? "—")], ["K9", numOf(s.k9)?.toFixed(2) ?? "—"], ["中繼", String(s.hld ?? "—")],
                 ["局數", fmtIP(s.ip as number | string | null)], ["先發", String(s.gs ?? "—")], ["完投", String(s.cg ?? "—")],
                 ["完封", String(s.sho ?? "—")], ["被安", String(s.h ?? "—")], ["被轟", String(s.hr ?? "—")],
                 ["四壞", String(s.bb ?? "—")], ["故四", String(s.ibb ?? "—")], ["觸身", String(s.hbp ?? "—")],
                 ["暴投", String(s.wp ?? "—")], ["犯規", String(s.bk ?? "—")], ["投球數", String(s.np ?? "—")],
                 ["失分", String(s.r ?? "—")], ["自責", String(s.er ?? "—")], ["出賽", String(s.g ?? "—")]];
            return (
              <Card className="flex flex-1 flex-col gap-2">
                <div className="grid grid-cols-3 gap-2">
                  {primary.map(([l, v, a]) => (
                    <div key={l} className="rounded-lg bg-surface-2 px-2 py-3 text-center">
                      <div className="text-[11px] text-muted">{l}</div>
                      <div className={`mt-1 font-mono text-2xl leading-none tabular-nums ${a ? "text-accent" : "text-ink"}`}>{v}</div>
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-5">
                  {secondary.filter(([, v]) => v !== "0").map(([l, v]) => (
                    <div key={l} className="rounded-lg bg-surface-2 px-1.5 py-1.5 text-center">
                      <div className="text-[10px] leading-tight text-muted">{l}</div>
                      <div className="mt-0.5 font-mono text-sm leading-none tabular-nums text-ink">{v}</div>
                    </div>
                  ))}
                </div>
              </Card>
            );
          })() : <p className="text-sm text-muted">本季無{role === "batting" ? "打擊" : "投球"}成績。</p>}
        </div>
        <div className="flex flex-col">
          <h2 className="mb-3 text-lg font-semibold text-ink">官方進階 · 百分位 PR</h2>
          <Card className="flex-1">
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

      {/* 生涯成績 + 最佳單季 + 里程碑 + 史上排名（打者）*/}
      {careerStats?.batting && (() => {
        const cb = careerStats.batting!;
        const bs = careerStats.best;
        const ms = careerStats.milestones;
        const rk = careerStats.rank;
        return (
          <section className="mb-6">
            <h2 className="mb-1 text-lg font-semibold text-ink">生涯成績</h2>
            <p className="mb-3 text-[11px] text-faint">一軍例行賽各季合計（近兩季由逐場補；史上排名以官方歷年累計，近兩季另計）。</p>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-8">
              <StatTile label={`生涯 ${cb.seasons} 季`} value={`${cb.g} 場`} />
              <StatTile label="安打" value={String(cb.h)} accent />
              <StatTile label="全壘打" value={String(cb.hr)} accent />
              <StatTile label="打點" value={String(cb.rbi)} />
              <StatTile label="盜壘" value={String(cb.sb)} />
              <StatTile label="打擊率" value={f3(cb.avg)} />
              <StatTile label="OPS" value={f3(cb.ops)} />
              {(() => {
                const parts = rk
                  ? ([["轟", rk.hr], ["安", rk.h], ["盜", rk.sb]] as [string, number][])
                      .filter(([, v]) => v != null && v <= 20)
                      .map(([l, v]) => `${l}#${v}`)
                  : [];
                return parts.length > 0 ? <StatTile label="史上排名" value={parts.join("·")} /> : null;
              })()}
            </div>
            <p className="mt-2 text-[11px] text-faint">
              最佳單季：
              {bs.ops && `OPS ${f3(bs.ops.value)}(${bs.ops.year})`}
              {bs.hr && `・全壘打 ${bs.hr.value}(${bs.hr.year})`}
              {bs.avg && `・打擊率 ${f3(bs.avg.value)}(${bs.avg.year})`}
              {(ms.first_hit || ms.first_hr) && (
                <span className="ml-2">｜里程碑：{ms.first_hit && `首安 ${ms.first_hit}`}{ms.first_hr && `・首轟 ${ms.first_hr}`}</span>
              )}
            </p>
          </section>
        );
      })()}

      {/* 擊球品質與彈道（官方 /rankings 全季進階；非逐球樣本） */}
      {(() => {
        const a = role === "batting" ? advanced?.batting : advanced?.pitching;
        const m = a?.metrics as Record<string, number> | undefined;
        if (!m || m.gbp == null) return null;
        return (
          <section className="mb-6">
            <h2 className="mb-1 text-lg font-semibold text-ink">擊球品質與彈道</h2>
            <p className="mb-3 text-[11px] text-faint">
              官方 stats.cpbl 全季進階（{role === "batting" ? "打者擊球" : "投手被擊球"}）；非逐球設備樣本。
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {QUALITY_GROUPS.map((g) => (
                <Card key={g.title} className="p-4">
                  <div className="mb-2 text-sm font-semibold text-ink">{g.title}</div>
                  <div className="grid grid-cols-2 gap-2">
                    {g.items.map((it) => (
                      <StatTile key={it.k} label={it.label}
                        value={m[it.k] == null ? "—" : it.fmt(m[it.k])} />
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          </section>
        );
      })()}

      {/* 擊球落點 + 進壘點（左 2/3 放大） + 好球帶紀律（右側直欄） */}
      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-ink">逐球追蹤</h2>
        <div className="grid items-stretch gap-6 lg:grid-cols-3">
        <Card className="flex flex-col lg:col-span-2">
          <div className="grid gap-x-4 sm:grid-cols-2">
            <div className="relative flex flex-col">
              <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">擊球落點（{disc?.spray.length ?? 0} 球）</h3>
              {disc && disc.spray.length > 0 ? <div className="mt-auto mb-[13%]"><SprayChart points={disc.spray} /></div>
                : <p className="py-12 text-center text-sm text-faint">{disc === null ? "載入中…" : "無擊球追蹤資料"}</p>}
            </div>
            <div className="relative">
              <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">進壘點（{disc?.points.length ?? 0} 球）</h3>
              <div className="absolute right-0 top-0 z-10 flex gap-1 text-[11px]">
                {(["scatter", "heat"] as const).map((v) => (
                  <button key={v} onClick={() => setZoneView(v)}
                    className={`rounded px-1.5 py-0.5 ${zoneView === v ? "bg-ink text-white" : "bg-surface-2 text-muted"}`}>
                    {v === "scatter" ? "散點" : "熱區"}
                  </button>
                ))}
              </div>
              {zoneView === "heat" && (
                <div className="absolute right-0 top-6 z-10 flex flex-wrap justify-end gap-1 text-[11px]">
                  {([["density", "密度"], ["ev", "初速"], ["ba", "安打率"], ["whiff", "揮空"]] as const).map(([m, l]) => (
                    <button key={m} onClick={() => setHeatMetric(m)}
                      className={`rounded px-1.5 py-0.5 ${heatMetric === m ? "bg-accent text-white" : "bg-surface-2 text-muted"}`}>
                      {l}
                    </button>
                  ))}
                </div>
              )}
              {disc && disc.points.length > 0
                ? (zoneView === "scatter" ? <ZoneScatter points={disc.points} />
                    : <PerfHeatmap points={disc.points} metric={heatMetric} />)
                : <p className="py-12 text-center text-sm text-faint">{disc === null ? "載入中…" : "無逐球資料"}</p>}
              {zoneView === "heat" && (
                <div className="mt-1 flex items-center justify-center gap-2 text-[11px] text-muted">
                  <span>低</span>
                  <span className="inline-block h-2 w-24 rounded-full" style={{ background: "linear-gradient(90deg,#cfe2ff,#fff7cc,#d62839)" }} />
                  <span>高{heatMetric === "ev" ? "(初速)" : heatMetric === "ba" ? "(安打率)" : heatMetric === "whiff" ? "(揮空)" : "(密度)"}</span>
                </div>
              )}
            </div>
          </div>
          {disc && (() => {
            const q = disc.quality;
            const tiles: [string, number | null, string][] = role === "batting"
              ? [["平均仰角", q.avg_launch_angle, "°"], ["最遠擊球", q.max_hit_dist, "m"], ["平均初速", q.avg_exit_speed, "km/h"]]
              : [["平均球速", q.avg_speed, "km/h"], ["平均延伸", q.avg_extension, "m"], ["平均放球高", q.avg_rel_height, "m"]];
            if (tiles.every(([, v]) => v == null)) return null;
            return (
              <div className="mt-auto border-t border-line pt-3">
                <div className="mb-2 text-xs text-muted">{role === "batting" ? "擊球品質" : "球質"}<span className="text-faint">（逐球追蹤樣本）</span></div>
                <div className="grid grid-cols-3 gap-2">
                  {tiles.map(([l, v, u]) => (
                    <div key={l} className="card px-3 py-2 text-center">
                      <div className="text-[11px] text-muted">{l}</div>
                      <div className="mt-0.5 font-mono text-base tabular-nums text-ink">{v == null ? "—" : v}<span className="ml-0.5 text-[10px] text-faint">{u}</span></div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}
        </Card>
        <div className="flex flex-col gap-6">
          <Card className="flex-1">
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
        </div>
      </section>

      {/* 打者：擊球品質散點 / 投手：配球傾向 */}
      {role === "batting" ? (
        (disc?.batted.length ?? 0) > 0 && (
          <section className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-ink">擊球品質分布（仰角 × 初速）</h2>
            <Card>
              <LaEvScatter balls={disc!.batted} />
              <p className="mt-1 text-[10px] text-faint">紅框＝強勁擊球的理想仰角帶（近似 barrel 甜蜜區）；逐球追蹤樣本。</p>
            </Card>
          </section>
        )
      ) : (
        (pitchMix?.length ?? 0) > 0 && (
          <section className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-ink">配球傾向（依球數）</h2>
            <Card>
              <div className="space-y-2.5">
                {pitchMix!.map((b) => (
                  <div key={b.bucket} className="flex items-center gap-2 text-xs">
                    <span className="w-16 shrink-0 text-muted">{b.bucket}</span>
                    <div className="flex h-5 flex-1 overflow-hidden rounded">
                      <div className="flex items-center justify-center text-[10px] text-white" style={{ width: `${b.fastball}%`, background: "#1d6fb8" }}>
                        {b.fastball >= 12 ? `${b.fastball}%` : ""}
                      </div>
                      <div className="flex items-center justify-center text-[10px] text-white" style={{ width: `${b.breakingball}%`, background: "#f59e0b" }}>
                        {b.breakingball >= 12 ? `${b.breakingball}%` : ""}
                      </div>
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-faint">{b.n}</span>
                  </div>
                ))}
              </div>
              <div className="mt-2.5 flex justify-center gap-4 text-[11px] text-muted">
                <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ background: "#1d6fb8" }} />速球</span>
                <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ background: "#f59e0b" }} />變化球</span>
              </div>
            </Card>
          </section>
        )
      )}

      {/* 賽季走勢（逐場累積）+ 對戰各隊 */}
      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-ink">賽季走勢 · 對戰各隊</h2>
        <div className="grid items-stretch gap-6 lg:grid-cols-2">
          <Card className="h-full">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-medium text-muted">賽季走勢（逐場累積）</h3>
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
          <Card className="h-full">
            <h3 className="mb-3 text-sm font-medium text-muted">對戰各隊（本季）</h3>
            {vsTeam === null ? <p className="py-8 text-center text-sm text-faint">載入中…</p>
              : vsTeam.length === 0 ? <p className="py-8 text-center text-sm text-faint">無資料</p>
              : <VsTeamTable items={vsTeam} role={role} />}
          </Card>
        </div>
      </section>

      {/* 守備 */}
      {fielding && fielding.length > 0 && (() => {
        const hasC = fielding.some((r) => String(r.pos).includes("捕") || numOf(r.cs) || numOf(r.pb) || numOf(r.sba));
        const cols: { key: string; label: string; tip: string; tone?: string; catcher?: boolean }[] = [
          { key: "g", label: "出賽", tip: "該守位出賽場數 G", tone: "text-muted" },
          { key: "tc", label: "守備機會", tip: "TC＝刺殺＋助殺＋失誤" },
          { key: "po", label: "刺殺", tip: "PO：直接使打者/跑者出局" },
          { key: "a", label: "助殺", tip: "A：傳球協助使對方出局" },
          { key: "e", label: "失誤", tip: "E", tone: "text-accent" },
          { key: "dp", label: "雙殺", tip: "參與的雙殺次數" },
          { key: "tp", label: "三殺", tip: "參與的三殺次數" },
          { key: "pb", label: "捕逸", tip: "PB：捕手漏接致跑者進壘", catcher: true },
          { key: "cs", label: "盜壘阻殺", tip: "阻殺：捕手傳殺盜壘跑者", catcher: true },
          { key: "sba", label: "被盜成功", tip: "被盜壘成功數", catcher: true },
        ].filter((c) => !c.catcher || hasC);
        return (
          <section className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-ink">守備</h2>
            <div className="overflow-x-auto rounded-xl border border-line bg-surface">
              <table className="w-full text-sm">
                <thead className="bg-surface-2 text-left text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">守位</th>
                    {cols.map((c) => (
                      <th key={c.key} title={c.tip} className="cursor-help px-3 py-2 text-right font-medium">{c.label}</th>
                    ))}
                    <th title="(刺殺＋助殺) ÷ 守備機會" className="cursor-help px-3 py-2 text-right font-medium">守備率</th>
                  </tr>
                </thead>
                <tbody className="font-mono tabular-nums">
                  {fielding.map((r) => (
                    <tr key={String(r.pos)} className="border-t border-line">
                      <td className="px-3 py-2 font-sans text-ink">{String(r.pos)}</td>
                      {cols.map((c) => (
                        <td key={c.key} className={`px-3 py-2 text-right ${c.tone ?? ""}`}>{n0(r[c.key])}</td>
                      ))}
                      <td className="px-3 py-2 text-right text-ink">{r.fpct == null ? "—" : Number(r.fpct).toFixed(3).replace(/^0\./, ".")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })()}

      {/* 生涯逐年 */}
      {career && career.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-3 text-lg font-semibold text-ink">生涯逐年</h2>
          <CareerTable seasons={career} role={role} />
          <p className="mt-2 text-[11px] text-faint">資料源 cpbl-opendata（逐年彙總），不含當季；當季數據見上方「本季成績」。</p>
        </section>
      )}

      {/* 分項明細 */}
      <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold text-ink">分項明細</h2>
          <Tabs opts={[{ v: "season", label: "本季" }, { v: "career", label: "生涯" }]} v={scope} set={setScope} />
          {scope === "career" && (
            <div className="inline-flex flex-wrap gap-2">
              {([["A", "例行賽"], ["C", "總冠軍"], ["E", "季後賽"]] as const).map(([k, label]) => {
                const on = kinds.includes(k);
                return (
                  <button key={k} onClick={() => setKinds(on ? (kinds.length > 1 ? kinds.filter((x) => x !== k) : kinds) : [...kinds, k])}
                    className={`rounded-full px-3 py-1 text-xs transition ${on ? "bg-accent text-white" : "bg-surface-2 text-muted hover:text-ink"}`}>
                    {label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        {!splits ? <p className="text-sm text-muted">載入中…</p>
          : splits.length === 0 ? <p className="text-sm text-muted">此範圍無分項資料。</p> : (() => {
            const groups = [...SPLIT_CATS, { key: "other", label: "其他" }]
              .map((cat) => ({ cat, rows: (splits ?? []).filter((r) => splitCat(String(r.item_name)) === cat.key) }))
              .filter((g) => g.rows.length > 0);
            return (
              <div className="space-y-2">
                {groups.map((g, gi) => (
                  <details key={g.cat.key} open={gi === 0} className="overflow-hidden rounded-xl border border-line bg-surface">
                    <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface-2">
                      {g.cat.label}<span className="ml-2 text-xs font-normal text-faint">{g.rows.length}</span>
                    </summary>
                    <div className="overflow-x-auto border-t border-line"><SplitsTable rows={g.rows} role={role} /></div>
                  </details>
                ))}
              </div>
            );
          })()}
      </section>

      <div className="flex gap-4 text-sm">
        <Link href="/matchups" className="text-accent hover:underline">投打對決 →</Link>
        <Link href="/batters" className="text-muted hover:text-ink">← 返回排行</Link>
      </div>
    </div>
  );
}
