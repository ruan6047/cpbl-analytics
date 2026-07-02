"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, Cell, ComposedChart, Line, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LaEvScatter } from "@/components/la-ev-scatter";
import { SprayChart } from "@/components/spray-chart";
import { AbilityCard, GradeChip } from "@/components/ability-card";
import { Card, LetterBadge, PercentileBar, StatTile, TeamLogo } from "@/components/ui";
import { type HeatMetric, Grid3x3, PlateDisciplineBars } from "@/components/perf-heatmap";
import { ZoneScatter } from "@/components/zone-scatter";
import { detail, type PlayerProfile, type StatRow } from "@/lib/client";
import { fmtIP, fmtIPParts } from "@/lib/format";
import { codeFromName, eraBadge, teamColor, teamShort } from "@/lib/teams";

type Role = "batting" | "pitching";
type Disc = {
  summary: Record<string, number | null>;
  quality: Record<string, number | null>;
  quality_by_pt: Record<string, Record<string, number | null>>;
  points: { x: number; y: number; sw: boolean; wh: boolean; result: string; ev: number | null; la: number | null; pt: string | null }[];
  spray: { dir: number; dist: number; ev: number | null; la: number | null; result: string; pt: string | null }[];
  batted: { la: number; ev: number; result: string }[];
};

const numOf = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === "" ? null : Number(v);

// 洋將身分徽章樣式（local 不顯示）
const IMPORT_BADGE: Record<string, { color: string; hint: string }> = {
  import: { color: "#2563EB", hint: "外籍洋將，占球隊洋將登錄名額" },
  loree: { color: "#0F766E", hint: "羅力條款：在台累積球季並申請，視為本土洋將，不占洋將名額" },
  nagata: { color: "#7C3AED", hint: "永田條款：循台灣學生棒球體系選秀進入職棒，視同本土選手" },
};

// hero 內「教練／行政」所屬隊伍列：依隊聚合年份、職稱進 tooltip（比照球員所屬隊伍）
type Tenure = { team: string; role: string | null; from: number | null; to: number | null };
function TenureChips({ label, tenures }: { label: string; tenures: Tenure[] }) {
  const agg = new Map<string, { team: string; from: number | null; to: number | null; roles: Set<string>; ongoing: boolean }>();
  for (const t of tenures) {
    const g = agg.get(t.team) ?? { team: t.team, from: t.from, to: t.to, roles: new Set<string>(), ongoing: false };
    if (t.from != null) g.from = g.from == null ? t.from : Math.min(g.from, t.from);
    if (t.to == null && t.from != null) g.ongoing = true;
    else if (t.to != null) g.to = g.to == null ? t.to : Math.max(g.to, t.to);
    if (t.role) g.roles.add(t.role);
    agg.set(t.team, g);
  }
  const list = [...agg.values()].sort((a, b) => (a.from ?? 9999) - (b.from ?? 9999));
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] text-faint">{label}</span>
      {list.map((t) => {
        const b = eraBadge(t.team, codeFromName(t.team) ?? "");
        const yr = t.from == null ? "" : t.ongoing ? `'${String(t.from).slice(2)}–`
          : t.from === t.to ? `'${String(t.from).slice(2)}`
          : `'${String(t.from).slice(2)}–'${String(t.to).slice(2)}`;
        return (
          <span key={t.team}
            className="inline-flex items-center gap-1 rounded-full py-0.5 pl-0.5 pr-2 text-[11px] font-medium"
            style={{ background: `${b.color}1a`, color: b.color }}
            title={`${t.team} ${label}${t.roles.size ? `（${[...t.roles].join("、")}）` : ""}`}>
            <LetterBadge meta={b} round />
            {t.team}
            {yr && <span className="font-mono tabular-nums opacity-70">{yr}</span>}
          </span>
        );
      })}
    </div>
  );
}
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
const QUALITY_GROUPS: { title: string; pie?: boolean; items: { k: string; label: string; fmt: (v: number) => string }[] }[] = [
  { title: "擊球品質", items: [
    { k: "evAvg", label: "平均初速", fmt: _kmh }, { k: "ev90Th", label: "EV90", fmt: _kmh },
    { k: "evMax", label: "最大初速", fmt: _kmh }, { k: "laAvg", label: "平均仰角", fmt: _deg },
    { k: "distanceAvgHr", label: "全壘打均距", fmt: _m }, { k: "distanceMax", label: "最遠擊球", fmt: _m },
  ] },
  { title: "彈道分布", pie: true, items: [
    { k: "gbp", label: "滾地球", fmt: _pct }, { k: "ldp", label: "平飛球", fmt: _pct },
    { k: "fbp", label: "高飛球", fmt: _pct }, { k: "pup", label: "內野飛球", fmt: _pct },
  ] },
  { title: "拉打方向", pie: true, items: [
    { k: "pullp", label: "拉打", fmt: _pct }, { k: "straightp", label: "中間", fmt: _pct },
    { k: "oppop", label: "推打", fmt: _pct },
  ] },
  { title: "強擊 / Barrel", items: [
    { k: "hardHitp", label: "強擊球%", fmt: _pct }, { k: "barrels", label: "Barrel 數", fmt: _cnt },
    { k: "brlsPAp", label: "Barrel/PA", fmt: _pct },
  ] },
];

// 組成型百分位 → 甜甜圈圖 + 圖例（彈道分布/拉打方向；值總和≈100%）
const PIE_COLORS = ["#1B4DA1", "#3B82C4", "#E8842B", "#9AA3AF"];
function CompositionPie({ items, m }: { items: { k: string; label: string }[]; m: Record<string, number> }) {
  const data = items
    .map((it, i) => ({ name: it.label, value: m[it.k] == null ? 0 : +(m[it.k] * 100).toFixed(1), color: PIE_COLORS[i % PIE_COLORS.length] }))
    .filter((d) => d.value > 0);
  if (!data.length) return <p className="py-6 text-center text-xs text-faint">無資料</p>;
  return (
    <div className="flex items-center gap-3">
      <div className="h-28 w-28 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={26} outerRadius={52} paddingAngle={2} stroke="none">
              {data.map((d) => <Cell key={d.name} fill={d.color} />)}
            </Pie>
            <Tooltip formatter={(v: number | string) => `${v}%`} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="min-w-0 flex-1 space-y-1.5 text-xs">
        {data.map((d) => (
          <li key={d.name} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-muted">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: d.color }} />{d.name}
            </span>
            <span className="font-mono tabular-nums text-ink">{d.value}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// roll=近15場滾動(rate/adjusted，看冷熱手)；無 roll=累積配速線(計數型)。ref=基準參考線。
type Metric = { key: string; label: string; dp: number; get: (r: StatRow) => number | null; roll?: boolean; ref?: number };
const BAT_METRICS: Metric[] = [
  { key: "ops_plus", label: "OPS+", dp: 0, get: (r) => numOf(r.ops_plus), roll: true, ref: 100 },
  { key: "ops", label: "OPS", dp: 3, get: (r) => numOf(r.ops), roll: true },
  { key: "avg", label: "打擊率", dp: 3, get: (r) => numOf(r.avg), roll: true },
  { key: "obp", label: "上壘率", dp: 3, get: (r) => numOf(r.obp), roll: true },
  { key: "slg", label: "長打率", dp: 3, get: (r) => numOf(r.slg), roll: true },
  // 逐場趨勢用 hits/home_runs、生涯逐年用 h/hr → 兩者皆容
  { key: "hits", label: "安打", dp: 0, get: (r) => numOf(r.hits ?? r.h) },
  { key: "home_runs", label: "全壘打", dp: 0, get: (r) => numOf(r.home_runs ?? r.hr) },
  { key: "rbi", label: "打點", dp: 0, get: (r) => numOf(r.rbi) },
];
const PIT_METRICS: Metric[] = [
  { key: "era_plus", label: "ERA+", dp: 0, get: (r) => numOf(r.era_plus), roll: true, ref: 100 },
  { key: "era", label: "ERA", dp: 2, get: (r) => (r.era != null ? numOf(r.era) : eraOf(r)), roll: true },
  { key: "whip", label: "WHIP", dp: 2, get: (r) => numOf(r.whip), roll: true },
  { key: "so", label: "三振", dp: 0, get: (r) => numOf(r.so) },
  { key: "hits", label: "被安打", dp: 0, get: (r) => numOf(r.hits) },
  { key: "bb", label: "四壞", dp: 0, get: (r) => numOf(r.bb) },
];
const axis = { tick: { fill: "#5b6b7a", fontSize: 12 }, stroke: "#cbd5e1" };

function Tabs<T extends string>({ opts, v, set, vertical = false }: { opts: { v: T; label: string }[]; v: T; set: (x: T) => void; vertical?: boolean }) {
  return (
    <div className={`inline-flex gap-1 rounded-lg bg-surface-2 p-1 ${vertical ? "flex-col" : ""}`}>
      {opts.map((o) => (
        <button key={o.v} onClick={() => set(o.v)}
          className={`rounded-md px-3 py-1 text-sm transition ${v === o.v ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// 最佳單季：獨立區塊，每項一張卡（指標／數值／年份）
function BestSeasonGrid({ items }: { items: { label: string; value: string; year: number }[] }) {
  if (!items.length) return null;
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-lg font-semibold text-ink">最佳單季</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {items.map((b) => (
          <div key={b.label} className="card flex flex-col items-center p-4 text-center">
            <div className="text-xs text-muted">{b.label}</div>
            <div className="mt-1 font-mono text-2xl font-bold tabular-nums text-accent">{b.value}</div>
            <div className="mt-1 rounded-full bg-surface-2 px-2 text-[11px] text-muted">{b.year} 年</div>
          </div>
        ))}
      </div>
    </section>
  );
}

// 球種鏡頭：整頁逐球資料共用一個 pitchType state（速球/變化球；資料只有 tagged 二分）。
type PitchType = "all" | "fastball" | "breakingball";
const PITCH_TYPES: [PitchType, string][] = [["all", "全部"], ["fastball", "速球"], ["breakingball", "變化球"]];
function PitchTypeToggle({ value, onChange }: { value: PitchType; onChange: (v: PitchType) => void }) {
  return (
    <div className="flex gap-1 text-[11px]">
      {PITCH_TYPES.map(([v, l]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`rounded px-2 py-0.5 ${value === v ? "bg-ink text-white" : "bg-surface-2 text-muted"}`}>{l}</button>
      ))}
    </div>
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
  const [pitchType, setPitchType] = useState<PitchType>("all");
  const [pitchMix, setPitchMix] = useState<{ bucket: string; n: number; fastball: number; breakingball: number }[] | null>(null);
  const [fielding, setFielding] = useState<StatRow[] | null>(null);
  const [fieldingCareer, setFieldingCareer] = useState<StatRow[] | null>(null);
  const [fieldFromYear, setFieldFromYear] = useState<number | null>(null);
  const [fieldScope, setFieldScope] = useState<"season" | "career">("season");
  const [vsTeam, setVsTeam] = useState<StatRow[] | null>(null);
  const [career, setCareer] = useState<StatRow[] | null>(null);
  const [careerMonthly, setCareerMonthly] = useState<StatRow[] | null>(null);
  const [careerStats, setCareerStats] = useState<Awaited<ReturnType<typeof detail.careerStats>> | null>(null);
  const [ability, setAbility] = useState<Awaited<ReturnType<typeof detail.abilityCard>> | null>(null);
  const [trend, setTrend] = useState<StatRow[] | null>(null);
  const [splits, setSplits] = useState<StatRow[] | null>(null);
  const [monthMetric, setMonthMetric] = useState("ops_plus");
  const [trendScope, setTrendScope] = useState<"season" | "career">("season");
  // 本季成績層級：二軍選手預設採計二軍(D)、可切換看一軍(A)。
  const [seasonKind, setSeasonKind] = useState<"A" | "D">("A");
  // 版面分頁：數據區（本季/生涯）、明細區（逐年/分項）。
  const [dataTab, setDataTab] = useState<"season" | "career">("season");
  const [detailTab, setDetailTab] = useState<"yearly" | "splits">("yearly");

  useEffect(() => {
    detail.profile(id).then((d) => {
      if (!d.player) return setNotFound(true);
      setProfile(d.player);
      const p = d.player;
      // role 預設：含本季一軍(is_*)、生涯曾任(was_*)、本季二軍(farm_*) 任一即可。
      const hasBat = p.is_batter || p.was_batter || p.farm_batter;
      const hasPit = p.is_pitcher || p.was_pitcher || p.farm_pitcher;
      setRole(hasBat || !hasPit ? "batting" : "pitching");
      // 退役/教練（本季無登錄層級）分項/數據預設生涯；二軍選手本季成績預設採計二軍。
      if (!p.roster_level) { setScope("career"); setDataTab("career"); }
      if (p.roster_level === "二軍") setSeasonKind("D");
    }).catch(() => setNotFound(true));
    detail.fielding(id, "career").then((d) => { setFieldingCareer(d.items); setFieldFromYear(d.from_year ?? null); })
      .catch(() => setFieldingCareer([]));
    detail.careerStats(id).then(setCareerStats).catch(() => setCareerStats(null));
    detail.abilityCard(id).then(setAbility).catch(() => setAbility(null));
  }, [id]);

  useEffect(() => {
    detail.season(id, seasonKind).then(setSeason).catch(() => setSeason(null));
  }, [id, seasonKind]);

  useEffect(() => {
    setMonthMetric(role === "batting" ? "ops_plus" : "era_plus");
    setTrend(null);
    setVsTeam(null);
    setCareer(null);
    detail.trend(id, role).then((d) => setTrend(d.items)).catch(() => setTrend([]));
    detail.vsTeam(id, role).then((d) => setVsTeam(d.items)).catch(() => setVsTeam([]));
    detail.career(id, role).then((d) => setCareer(d.seasons)).catch(() => setCareer([]));
  }, [id, role]);

  // 生涯時段分項：固定以「週」跨年合併
  useEffect(() => {
    setCareerMonthly(null);
    detail.trendCareer(id, role, "week").then((d) => setCareerMonthly(d.items)).catch(() => setCareerMonthly([]));
  }, [id, role]);

  // 逐球追蹤（好球帶紀律 + 配球傾向）+ 當季守備隨一/二軍鏡頭切換：二軍有獨立樣本
  useEffect(() => {
    setPitchType("all");
    setDisc(null);
    setPitchMix(null);
    detail.discipline(id, role, seasonKind).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
    detail.pitchMix(id, role, seasonKind).then((d) => setPitchMix(d.items)).catch(() => setPitchMix([]));
    detail.fielding(id, "season", seasonKind).then((d) => setFielding(d.items)).catch(() => setFielding([]));
    detail.advanced(id, seasonKind).then(setAdvanced).catch(() => setAdvanced(null));
  }, [id, role, seasonKind]);

  useEffect(() => {
    if (!profile) return;
    const year = scope === "season" ? 2026 : 9999;
    // 本季分項依一/二軍鏡頭(seasonKind)；生涯分項用 kind 頁籤(A/C/E)
    const k = scope === "season" ? seasonKind : (kinds.length ? kinds.join(",") : "A");
    detail.splits(id, role, year, k).then((d) => setSplits(d.items)).catch(() => setSplits([]));
  }, [id, role, scope, kinds, seasonKind, profile]);

  const metrics = role === "batting" ? BAT_METRICS : PIT_METRICS;
  const metric = metrics.find((m) => m.key === monthMetric) ?? metrics[0];
  const monthData = useMemo(
    () => (trend ?? []).map((r) => ({ name: String(r.name), v: metric.get(r) })),
    [trend, metric],
  );
  // 生涯月份分項：跨年份把同一月份合併為一點（看慢熱/各月強弱、當下月參考）
  const careerTrendData = useMemo(
    () => (careerMonthly ?? []).filter((r) => metric.get(r) != null)
      .map((r) => ({ name: String(r.name), v: metric.get(r) })),
    [careerMonthly, metric],
  );
  // 本季計數型(柱狀)：逐場太細 → 以 7 天為一箱加總,看期間變化（須在早期 return 前宣告）
  const seasonBars = useMemo(() => {
    if (metric.roll) return [];
    const rows = trend ?? [];
    if (rows.length === 0) return [];
    const t0 = new Date(String(rows[0].date)).getTime();
    const buckets = new Map<number, { name: string; v: number }>();
    for (const r of rows) {
      const dt = new Date(String(r.date));
      const wk = Math.floor((dt.getTime() - t0) / (7 * 86400000));
      const b = buckets.get(wk) ?? { name: `${dt.getMonth() + 1}/${dt.getDate()}`, v: 0 };
      b.v += metric.get(r) ?? 0;
      buckets.set(wk, b);
    }
    return [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([, b]) => b);
  }, [trend, metric]);
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

  // 退役/教練：本季完全無登錄層級(roster_level=null) → 本季數值與官方進階必空，整段隱藏。
  // 二軍-only 球員有 roster_level（二軍）故不算退役。
  const isRetired = !profile.roster_level;
  // role tab：含本季一軍(is_*)、生涯曾任(was_*)、本季二軍(farm_*) 任一即列。
  const roles: { v: Role; label: string }[] = [];
  if (profile.is_batter || profile.was_batter || profile.farm_batter) roles.push({ v: "batting", label: "打擊" });
  if (profile.is_pitcher || profile.was_pitcher || profile.farm_pitcher) roles.push({ v: "pitching", label: "投球" });
  const s = season ? (role === "batting" ? season.batting : season.pitching) : null;
  // hero 隊伍：本季球員登錄隊 > 進行中執教隊（教練 tenure 未結束）> 生涯主隊（年資最長）
  const ongoingCoach = careerStats?.coach_tenures?.find((t) => t.to == null) ?? null;
  const primaryTeam = (careerStats?.teams ?? []).length
    ? [...(careerStats?.teams ?? [])].sort((a, b) => (b.to - b.from) - (a.to - a.from))[0]
    : null;
  const heroName = profile.team ?? ongoingCoach?.team ?? primaryTeam?.name ?? null;
  const tc = profile.team ? codeFromName(profile.team)
    : ongoingCoach ? codeFromName(ongoingCoach.team)
    : (primaryTeam?.code ?? null);
  // 逐球追蹤是否有資料（無則整段隱藏；載入中仍顯示避免閃爍）
  const trackingReady = disc !== null;
  const hasTracking = !!(
    disc && (disc.points.length || disc.spray.length || disc.batted.length || disc.summary.swing_pct != null)
  );
  const showTracking = !trackingReady || hasTracking;
  // 球種篩選（速球/變化球；資料只有 tagged 二分，見 AI_RUNBOOK）。all 不過濾。
  const sprayF = disc ? (pitchType === "all" ? disc.spray : disc.spray.filter((p) => p.pt === pitchType)) : [];
  const pointsF = disc ? (pitchType === "all" ? disc.points : disc.points.filter((p) => p.pt === pitchType)) : [];
  // 賽季走勢/對戰各隊：本季逐場、生涯逐年、對戰各隊任一有料即顯示（載入中仍顯示）
  const showTrendVs = trend === null || vsTeam === null || monthData.length > 0
    || careerTrendData.length > 0 || (vsTeam?.length ?? 0) > 0;
  // 走勢有效範圍：本季無資料(退役)但有生涯逐年 → 自動切生涯
  const effTrend: "season" | "career" =
    trendScope === "season" && monthData.length === 0 && careerTrendData.length > 0 ? "career" : trendScope;
  const trendData = effTrend === "career" ? careerTrendData : (metric.roll ? monthData : seasonBars);

  // 能力值卡：尺度跟隨下方資料分頁 dataTab（本季/生涯），不再有獨立切換鈕
  const abSel = (() => {
    const sa = (sc: "season" | "career") => !!(ability?.batting?.[sc]?.available || ability?.pitching?.[sc]?.available);
    if (!sa("season") && !sa("career")) return null;
    const eff = sa(dataTab) ? dataTab : sa("season") ? "season" : "career";
    const card = ability?.[role]?.[eff]?.available ? ability[role][eff]
      : ability?.batting?.[eff]?.available ? ability.batting[eff] : ability?.pitching?.[eff];
    if (!card?.available) return null;
    return { eff, card };
  })();
  // 生涯資料是否存在（打者或投手任一）→ 控制「生涯」分頁顯示
  const hasCareer = !!(careerStats?.batting || careerStats?.pitching);

  return (
    <div>
      {/* Hero */}
      <div className="card mb-6 overflow-hidden">
        <div className="h-1.5" style={{ background: teamColor(tc) }} />
        <div className="p-5">
        <div className="grid items-stretch gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          {/* 左欄：身分資訊（置頂）＋得獎（置底） */}
          <div className="flex min-w-0 flex-col">
          <div className="min-w-0">
            <div className="flex items-start gap-3.5">
              <TeamLogo code={tc} size={48} />
              <div className="min-w-0 flex-1">
              {/* 名字＋徽章列（左）／本季數值（區塊右上角） */}
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-3xl font-bold text-ink">{profile.name}</h1>
                    {profile.import_status && profile.import_status !== "local" && (
                      <span
                        className="rounded-md px-2 py-0.5 text-[11px] font-semibold leading-none"
                        style={{
                          background: `${IMPORT_BADGE[profile.import_status].color}1a`,
                          color: IMPORT_BADGE[profile.import_status].color,
                        }}
                        title={`${IMPORT_BADGE[profile.import_status].hint}${profile.country ? `（國籍：${profile.country}）` : ""}`}>
                        {profile.import_label}
                      </span>
                    )}
                    {profile.roster_level && (
                      <span
                        className="rounded-md px-2 py-0.5 text-[11px] font-semibold leading-none"
                        style={profile.roster_level === "一軍"
                          ? { background: "#1B4DA11a", color: "#1B4DA1" }
                          : { background: "#B4540025", color: "#9A4A00" }}
                        title={`目前登錄層級（依最後一次升降事件判定）${profile.roster_days
                          ? `：本季累計 一軍 ${profile.roster_days.first} 天 · 二軍 ${profile.roster_days.farm} 天` : ""}`}>
                        {profile.roster_level}選手
                      </span>
                    )}
                    {abSel?.card.signature && (
                      <span className="rounded-md bg-accent/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-accent"
                        title={role === "pitching"
                          ? "投球風格：最突出的出局方式（三振／滾地／飛球）"
                          : "打擊特色：進攻工具中最突出者（多項頂尖＝全能）"}>
                        {abSel.card.signature}型
                      </span>
                    )}
                    {profile.pitcher_role && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink"
                        title="投手類型：先發＝先發場數佔半數以上；後援＝救援>中繼（終結者傾向）；中繼＝其餘後援投手">
                        {profile.pitcher_role}
                      </span>
                    )}
                    {profile.primary_position && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink"
                        title="主守位：本季出賽最多的守位或指定打擊（DH 由打擊出賽扣守備推算；本季無資料則取生涯守備）">
                        {profile.primary_position}
                      </span>
                    )}
                    {profile.bats && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink" title="打擊慣用手">
                        {profile.bats}
                      </span>
                    )}
                    {profile.throws && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink" title="投球慣用手">
                        {profile.throws}
                      </span>
                    )}
                  </div>
                  {profile.former_names?.length > 0 && (
                    <p className="mt-0.5 text-[11px] text-faint">曾用名：{profile.former_names.join("、")}</p>
                  )}
                  {(() => {
                    const bio: string[] = [];
                    if (profile.height_cm && profile.weight_kg)
                      bio.push(`${profile.height_cm} cm / ${profile.weight_kg} kg`);
                    if (profile.birthday) {
                      const b = new Date(profile.birthday);
                      const age = Math.floor((Date.now() - b.getTime()) / 31557600000);
                      bio.push(`${profile.birthday}（${age} 歲）`);
                    }
                    if (profile.debut) bio.push(`初登場 ${profile.debut}`);
                    if (profile.birthplace && profile.birthplace !== "中華民國")
                      bio.push(`國籍 ${profile.birthplace}`);
                    if (profile.education) bio.push(profile.education);
                    if (profile.draft) bio.push(profile.draft);
                    return bio.length > 0 ? (
                      <p className="mt-1 text-xs text-muted">{bio.join(" · ")}</p>
                    ) : null;
                  })()}
                </div>
                {/* 本季數值：區塊右上角 */}
                {s && role === "batting" && (
                  <div className="shrink-0 text-right font-mono leading-tight text-ink">
                    <div className="text-2xl font-semibold tabular-nums">{f3(s.avg)}/{f3(s.obp)}/{f3(s.slg)}</div>
                    <div className="text-base font-semibold tabular-nums text-accent">OPS {f3(s.ops)}</div>
                  </div>
                )}
                {s && role === "pitching" && (
                  <div className="shrink-0 text-right font-mono leading-tight text-ink">
                    <div className="text-2xl font-semibold tabular-nums">{numOf(s.era)?.toFixed(2) ?? "—"} ERA</div>
                    <div className="text-base tabular-nums text-muted">{s.w ?? 0}-{s.l ?? 0} · {fmtIP(s.ip as number | string | null)} 局</div>
                  </div>
                )}
              </div>
              <div className="my-3 border-t border-line" />
              {(!careerStats?.teams || careerStats.teams.length === 0) && heroName && (
                <p className="text-sm text-muted">
                  {heroName}{!profile.team && ongoingCoach && <span className="ml-1 text-faint">（教練）</span>}
                </p>
              )}
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
              {careerStats?.coach_tenures && careerStats.coach_tenures.length > 0 && (
                <TenureChips label="教練" tenures={careerStats.coach_tenures} />
              )}
              {careerStats?.exec_tenures && careerStats.exec_tenures.length > 0 && (
                <TenureChips label="行政" tenures={careerStats.exec_tenures} />
              )}
              {careerStats?.overseas && careerStats.overseas.length > 0 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="text-faint">旅外</span>
                  {careerStats.overseas.map((o) => (
                    <span key={`${o.league}-${o.year}`}
                      className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-muted"
                      title={`${o.league}${o.team ? ` · ${o.team}` : ""} · ${o.year} 加盟`}>
                      ✈ {o.league}{o.team ? ` · ${o.team}` : ""}
                      <span className="font-mono opacity-70">'{String(o.year).slice(2)}</span>
                    </span>
                  ))}
                </div>
              )}
              </div>
            </div>
          </div>
          {/* 得獎/國際賽：置於左欄底部（mt-auto 推到最下） */}
          {((careerStats?.awards?.length ?? 0) > 0 || (careerStats?.medals?.length ?? 0) > 0 || !!careerStats?.championships) && (
            <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
              {careerStats?.championships && (
                <span title={`總冠軍年份：${careerStats.championships.years.join("、")}`}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold"
                  style={{ background: "#E6B42220", color: "#9A6B00", border: "1px solid #E6B42255" }}>
                  <span>🏆 總冠軍</span>
                  <span className="rounded px-1 text-[10px] font-bold" style={{ background: "#E6B422", color: "#3a2a00" }}>×{careerStats.championships.count}</span>
                </span>
              )}
              {(() => {
                const grp = new Map<string, { label: string; years: number[] }>();
                for (const a of careerStats?.awards ?? []) {
                  const posCat = a.category === "金手套" || a.category === "最佳十人";
                  const label = posCat ? `${a.category}(${a.award})` : a.award;
                  const g = grp.get(label) ?? { label, years: [] };
                  g.years.push(a.year);
                  grp.set(label, g);
                }
                const groups = [...grp.values()].sort((x, y) => y.years.length - x.years.length || y.years[0] - x.years[0]);
                const MC: Record<string, string> = { 金: "#E6B422", 銀: "#9AA3AF", 銅: "#B0703C" };
                return (
                  <>
                    {groups.map((g) => (
                      <span key={g.label} title={[...new Set(g.years)].sort((a, b) => a - b).map((y) => `'${String(y).slice(2)}`).join(" ")}
                        className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-xs">
                        <span className="font-medium text-ink">🏆 {g.label}</span>
                        {g.years.length > 1 && <span className="rounded bg-accent/10 px-1 text-[10px] font-bold text-accent">×{g.years.length}</span>}
                      </span>
                    ))}
                    {(careerStats?.medals ?? []).map((m, i) => (
                      <span key={`${m.competition}-${m.year}-${i}`} title={m.year ? `'${String(m.year).slice(2)}` : undefined}
                        className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-xs">
                        <span className="grid h-4 w-4 place-items-center rounded-full text-[10px] font-bold text-white" style={{ background: MC[m.color] ?? "#7C8696" }}>{m.color}</span>
                        <span className="font-medium text-ink">{m.competition}</span>
                      </span>
                    ))}
                  </>
                );
              })()}
            </div>
          )}
          </div>
          {/* 右欄：能力值雷達 ＋ 本季/生涯（雷達正下方右側、往上收） */}
          {abSel && (
            <div className="flex items-center gap-2 lg:border-l lg:border-line lg:pl-5">
              <div className="min-w-0 flex-1">
                <AbilityCard card={abSel.card}
                  color={teamColor(tc) || (role === "batting" ? "#1B4DA1" : "#15543C")} hideNote />
              </div>
              {/* 雷達右側：總評＋本季/生涯（直排），用側欄消化雷達下方空白 */}
              <div className="flex w-16 shrink-0 flex-col items-center justify-center gap-3">
                {abSel.card.overall && (
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-[10px] text-muted">總評</span>
                    <GradeChip grade={abSel.card.overall.grade} size="lg" />
                  </div>
                )}
                {(!isRetired || hasCareer) && (
                  <Tabs vertical opts={[
                    ...(!isRetired ? [{ v: "season" as const, label: "本季" }] : []),
                    ...(hasCareer ? [{ v: "career" as const, label: "生涯" }] : []),
                  ]} v={dataTab} set={setDataTab} />
                )}
              </div>
            </div>
          )}
        </div>
        </div>
      </div>

      {roles.length > 1 && <div className="mb-5"><Tabs opts={roles} v={role} set={setRole} /></div>}
      {dataTab === "season" && !isRetired && (
      <section className="mb-6 grid items-stretch gap-6 lg:grid-cols-2">
        <div className="flex flex-col">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold text-ink">本季成績</h2>
            {/* 二軍選手：預設採計二軍(D)，提供切換看一軍(A) */}
            {profile.roster_level === "二軍" && (
              <div className="inline-flex overflow-hidden rounded-full border border-line text-xs">
                {(["D", "A"] as const).map((k) => (
                  <button key={k} onClick={() => setSeasonKind(k)}
                    className={`px-3 py-1 transition ${seasonKind === k ? "bg-accent text-white" : "bg-surface-2 text-muted hover:text-ink"}`}>
                    {k === "D" ? "二軍" : "一軍"}
                  </button>
                ))}
              </div>
            )}
            {profile.roster_level === "二軍" && (
              <span className="text-[11px] text-faint">
                {seasonKind === "D" ? "二軍選手 · 採計二軍數據" : "一軍數據（本季一軍出賽）"}
              </span>
            )}
          </div>
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
          </Card>
        </div>
      </section>
      )}

      {/* 生涯成績 + 最佳單季 + 里程碑 + 史上排名（打者）*/}
      {dataTab === "career" && role === "pitching" && careerStats?.pitching && (() => {
        const cp = careerStats.pitching!;
        const bp = careerStats.best_p ?? {};
        const rkp = careerStats.rank_p;
        const bestP = [
          bp.era && { label: "ERA", value: numOf(bp.era.value)?.toFixed(2) ?? "—", year: bp.era.year },
          bp.w && { label: "勝投", value: String(bp.w.value), year: bp.w.year },
          bp.so && { label: "三振", value: String(bp.so.value), year: bp.so.year },
          bp.sv && bp.sv.value > 0 && { label: "救援", value: String(bp.sv.value), year: bp.sv.year },
        ].filter(Boolean) as { label: string; value: string; year: number }[];
        return (
          <>
          <section className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-ink">生涯成績</h2>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-8">
              <StatTile label={`生涯 ${cp.seasons} 季`} value={`${cp.g} 場`} />
              <StatTile label="先發" value={String(cp.gs)} />
              <StatTile label="勝-敗" value={`${cp.w}-${cp.l}`} accent />
              <StatTile label="勝率" value={f3(cp.winpct)} />
              <StatTile label="救援" value={String(cp.sv)} />
              <StatTile label="中繼" value={String(cp.hld)} />
              <StatTile label="局數" value={String(cp.ip)} />
              <StatTile label="ERA" value={numOf(cp.era)?.toFixed(2) ?? "—"} accent />
              <StatTile label="三振" value={String(cp.so)} accent />
              <StatTile label="被安打" value={String(cp.h)} />
              <StatTile label="四壞" value={String(cp.bb)} />
              <StatTile label="自責分" value={String(cp.er)} />
              <StatTile label="WHIP" value={numOf(cp.whip)?.toFixed(2) ?? "—"} />
              <StatTile label="K/9" value={numOf(cp.k9)?.toFixed(2) ?? "—"} />
              <StatTile label="K/BB" value={numOf(cp.kbb)?.toFixed(2) ?? "—"} />
              {(() => {
                const parts = rkp
                  ? ([["勝", rkp.w], ["救", rkp.sv], ["奪", rkp.so]] as [string, number][])
                      .filter(([, v]) => v != null && v <= 30)
                      .map(([l, v]) => `${l}#${v}`)
                  : [];
                return parts.length > 0 ? <StatTile label="史上排名" value={parts.join("·")} /> : null;
              })()}
            </div>
          </section>
          <BestSeasonGrid items={bestP} />
          </>
        );
      })()}

      {dataTab === "career" && role === "batting" && careerStats?.batting && (() => {
        const cb = careerStats.batting!;
        const bs = careerStats.best;
        const ms = careerStats.milestones;
        const rk = careerStats.rank;
        const bestB = [
          bs.ops && { label: "OPS", value: f3(bs.ops.value), year: bs.ops.year },
          bs.hr && { label: "全壘打", value: String(bs.hr.value), year: bs.hr.year },
          bs.rbi && { label: "打點", value: String(bs.rbi.value), year: bs.rbi.year },
          bs.avg && { label: "打擊率", value: f3(bs.avg.value), year: bs.avg.year },
          bs.sb && { label: "盜壘", value: String(bs.sb.value), year: bs.sb.year },
        ].filter(Boolean) as { label: string; value: string; year: number }[];
        return (
          <>
          <section className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-ink">生涯成績</h2>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-8">
              <StatTile label={`生涯 ${cb.seasons} 季`} value={`${cb.g} 場`} />
              <StatTile label="打數" value={String(cb.ab)} />
              <StatTile label="安打" value={String(cb.h)} accent />
              <StatTile label="二安" value={String(cb.b2)} />
              <StatTile label="三安" value={String(cb.b3)} />
              <StatTile label="全壘打" value={String(cb.hr)} accent />
              <StatTile label="打點" value={String(cb.rbi)} />
              <StatTile label="盜壘" value={String(cb.sb)} />
              <StatTile label="四壞" value={String(cb.bb)} />
              <StatTile label="三振" value={String(cb.so)} />
              <StatTile label="壘打數" value={String(cb.tb)} />
              <StatTile label="打擊率" value={f3(cb.avg)} />
              <StatTile label="上壘率" value={f3(cb.obp)} />
              <StatTile label="長打率" value={f3(cb.slg)} />
              <StatTile label="OPS" value={f3(cb.ops)} accent />
              {(() => {
                const parts = rk
                  ? ([["轟", rk.hr], ["安", rk.h], ["盜", rk.sb]] as [string, number][])
                      .filter(([, v]) => v != null && v <= 30)
                      .map(([l, v]) => `${l}#${v}`)
                  : [];
                return parts.length > 0 ? <StatTile label="史上排名" value={parts.join("·")} /> : null;
              })()}
            </div>
          </section>
          <BestSeasonGrid items={bestB} />
          {(ms.first_hit || ms.first_hr) && (
            <p className="-mt-3 mb-6 text-[11px] text-faint">
              里程碑：{ms.first_hit && `首安 ${ms.first_hit}`}{ms.first_hr && `・首轟 ${ms.first_hr}`}
            </p>
          )}
          </>
        );
      })()}

      {/* 逐球追蹤（整併：落點/進壘點散點 + 揮棒紀律 + 進壘熱區×打擊成績，共用單一球種鏡頭）。無資料整段隱藏 */}
      {showTracking && (
      <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-ink">逐球追蹤
            {seasonKind === "D" && <span className="ml-2 align-middle rounded bg-accent/10 px-1.5 py-0.5 text-xs font-semibold text-accent">二軍</span>}
            <span className="ml-2 align-middle text-xs font-normal text-faint">本季 · TrackMan 2026 起</span></h2>
          {disc && disc.points.length > 0 && <PitchTypeToggle value={pitchType} onChange={setPitchType} />}
        </div>
        <div className="grid items-stretch gap-6 lg:grid-cols-3">
          <Card className="flex flex-col lg:col-span-2">
            <div className="grid gap-x-4 sm:grid-cols-2">
              <div className="relative flex flex-col">
                <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">擊球落點（{sprayF.length} 球）</h3>
                {disc === null ? <p className="py-12 text-center text-sm text-faint">載入中…</p>
                  : sprayF.length > 0 ? <div className="mt-auto mb-[13%]"><SprayChart points={sprayF} /></div>
                  : <p className="py-12 text-center text-sm text-faint">{disc.spray.length ? "此球種無擊球" : "無擊球追蹤資料"}</p>}
              </div>
              <div className="relative">
                <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">進壘點（{pointsF.length} 球）</h3>
                {disc === null ? <p className="py-12 text-center text-sm text-faint">載入中…</p>
                  : pointsF.length > 0 ? <ZoneScatter points={pointsF} />
                  : <p className="py-12 text-center text-sm text-faint">{disc.points.length ? "此球種無資料" : "無逐球資料"}</p>}
              </div>
            </div>
          </Card>
          {/* 揮棒紀律(打者)：揮/不揮 分歧長條；投手為「誘使揮棒」去標題並在下方接球質（皆依球種鏡頭）*/}
          {disc && disc.summary.swing_pct != null && (
            <Card className="flex flex-col">
              {role === "batting" && <h3 className="mb-3 text-sm font-medium text-muted">揮棒紀律</h3>}
              <PlateDisciplineBars points={pointsF} />
              {role === "pitching" && (() => {
                const q = pitchType === "all" ? disc.quality : (disc.quality_by_pt[pitchType] ?? {});
                const tiles: [string, number | null, string][] =
                  [["平均球速", q.avg_speed ?? null, "km/h"], ["平均延伸", q.avg_extension ?? null, "m"], ["平均放球高", q.avg_rel_height ?? null, "m"]];
                if (tiles.every(([, v]) => v == null)) return null;
                return (
                  <div className="mt-auto border-t border-line pt-3">
                    <div className="mb-2 text-xs text-muted">球質<span className="text-faint">（逐球追蹤樣本）</span></div>
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
          )}
        </div>
        {/* 進壘熱區 × 打擊成績（3×3＋四角 熱圖，依球種篩）*/}
        {disc && disc.points.length > 0 && (
          <div className="mt-6">
            <h3 className="mb-2 text-sm font-medium text-muted">進壘熱區 × 打擊成績</h3>
            <div className="grid grid-cols-2 gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-3 lg:grid-cols-5">
              {(([["ev", "擊球初速 AVG"], ["la", "擊球仰角 AVG"], ["ba", "安打率"], ["hard", "強擊球%"], ["whiff", "揮空率"]] as [HeatMetric, string][])).map(([m, t]) => (
                <Grid3x3 key={m} points={pointsF} metric={m} title={t} />
              ))}
            </div>
            <div className="mt-2 flex items-center justify-center gap-2 text-[10px] text-faint">
              低<span className="inline-block h-2 w-20 rounded-full" style={{ background: "linear-gradient(90deg,#1e5bb8,#e8e8e8,#c4122f)" }} />高
              <span>白＝本人均值 · 每格 n&lt;3 顯「—」· 捕手視角</span>
            </div>
          </div>
        )}
      </section>
      )}

      {/* 擊球品質與彈道（官方 /rankings 全季進階；非逐球樣本） */}
      {(() => {
        const a = role === "batting" ? advanced?.batting : advanced?.pitching;
        const m = a?.metrics as Record<string, number> | undefined;
        if (!m || m.gbp == null) return null;
        return (
          <section className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-ink">擊球品質與彈道<span className="ml-2 align-middle text-xs font-normal text-faint">本季 · 官方進階 2026 起</span></h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {QUALITY_GROUPS.map((g) => (
                <Card key={g.title} className="p-4">
                  <div className="mb-2 text-sm font-semibold text-ink">{g.title}</div>
                  {g.pie ? (
                    <CompositionPie items={g.items} m={m} />
                  ) : (
                    <div className="grid grid-cols-2 gap-2">
                      {g.items.map((it) => (
                        <StatTile key={it.k} label={it.label}
                          value={m[it.k] == null ? "—" : it.fmt(m[it.k])} />
                      ))}
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </section>
        );
      })()}

      {/* 打者：擊球品質散點 / 投手：配球傾向 */}
      {role === "batting" ? (
        (disc?.batted.length ?? 0) > 0 && (
          <section className="mb-6">
            <h2 className="mb-3 text-lg font-semibold text-ink">擊球品質分布（仰角 × 初速）</h2>
            <Card>
              <LaEvScatter balls={disc!.batted} />
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

      {/* 賽季走勢（逐場累積）+ 對戰各隊。兩者皆空（退役球員）則隱藏 */}
      {showTrendVs && (
      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-ink">賽季走勢 · 對戰各隊</h2>
        <div className="grid items-stretch gap-6 lg:grid-cols-2">
          <Card className="h-full">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-muted">{effTrend === "career" ? "生涯各週（跨年合併）" : (metric.roll ? "賽季走勢（近 15 場滾動）" : "賽季走勢（每 7 天）")}</h3>
                {careerTrendData.length > 1 && monthData.length > 0 && (
                  <div className="inline-flex overflow-hidden rounded-full border border-line text-[11px]">
                    {(["season", "career"] as const).map((s) => (
                      <button key={s} onClick={() => setTrendScope(s)}
                        className={`px-2.5 py-0.5 transition ${effTrend === s ? "bg-ink text-white" : "bg-surface text-muted hover:text-ink"}`}>
                        {s === "season" ? "本季" : "生涯"}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <select value={monthMetric} onChange={(e) => setMonthMetric(e.target.value)}
                className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none focus:border-ink">
                {metrics.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>
            {trendData.length === 0 ? <p className="py-8 text-center text-sm text-faint">無資料</p> : (
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={trendData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid stroke="#eef2f7" />
                  {/* 生涯=月份分項(3月/4月…類別)；本季=逐場/週期日期 */}
                  <XAxis dataKey="name" {...axis} minTickGap={effTrend === "career" ? 4 : 28} />
                  <YAxis {...axis} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number) => v?.toFixed(metric.dp)} />
                  {metric.ref != null && (
                    <ReferenceLine y={metric.ref} stroke="#94a3b8" strokeDasharray="4 3"
                      label={{ value: `聯盟 ${metric.ref}`, position: "insideTopRight", fill: "#94a3b8", fontSize: 10 }} />
                  )}
                  {metric.roll ? (
                    <Line type="monotone" dataKey="v" name={metric.label} stroke="#0a2540" strokeWidth={2}
                      isAnimationActive={false} connectNulls
                      dot={trendData.length > 18 ? false : { r: 3, fill: "#d62839" }} />
                  ) : (
                    <Bar dataKey="v" name={metric.label} fill="#1B4DA1" isAnimationActive={false}
                      maxBarSize={18} />
                  )}
                </ComposedChart>
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
      )}

      {/* 守備（本季 fielding_current / 生涯 1990– 彙總；退役無本季 → 自動生涯）*/}
      {((fielding?.length ?? 0) > 0 || (fieldingCareer?.length ?? 0) > 0) && (() => {
        const effField: "season" | "career" =
          fieldScope === "season" && (fielding?.length ?? 0) === 0 && (fieldingCareer?.length ?? 0) > 0
            ? "career" : fieldScope;
        const fld = (effField === "career" ? fieldingCareer : fielding) ?? [];
        if (fld.length === 0) return null;
        const hasC = fld.some((r) => String(r.pos).includes("捕") || numOf(r.cs) || numOf(r.pb) || numOf(r.sba));
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
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-ink">守備</h2>
              {(fielding?.length ?? 0) > 0 && (fieldingCareer?.length ?? 0) > 0 && (
                <div className="inline-flex overflow-hidden rounded-full border border-line text-[11px]">
                  {(["season", "career"] as const).map((s) => (
                    <button key={s} onClick={() => setFieldScope(s)}
                      className={`px-2.5 py-0.5 transition ${effField === s ? "bg-ink text-white" : "bg-surface text-muted hover:text-ink"}`}>
                      {s === "season" ? "本季" : "生涯"}
                    </button>
                  ))}
                </div>
              )}
              {effField === "career" && fieldFromYear && (
                <span className="text-[11px] text-faint">生涯累計（{fieldFromYear} 起）</span>
              )}
            </div>
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
                  {fld.map((r) => (
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

      {/* 明細：生涯逐年 / 分項 分頁切換 */}
      <div className="mb-3"><Tabs opts={[
        ...(career && career.length > 0 ? [{ v: "yearly" as const, label: "生涯逐年" }] : []),
        { v: "splits" as const, label: "分項明細" },
      ]} v={detailTab} set={setDetailTab} /></div>

      {/* 生涯逐年 */}
      {detailTab === "yearly" && career && career.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-3 text-lg font-semibold text-ink">生涯逐年</h2>
          <CareerTable seasons={career} role={role} />
        </section>
      )}

      {/* 分項明細 */}
      {(detailTab === "splits" || !(career && career.length > 0)) && (
      <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold text-ink">分項明細</h2>
          {/* 退役/教練本季無分項 → 只留生涯切換 */}
          <Tabs opts={isRetired
            ? [{ v: "career", label: "生涯" }]
            : [{ v: "season", label: "本季" }, { v: "career", label: "生涯" }]} v={scope} set={setScope} />
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
      )}

      {/* 資料說明（統一彙整於頁尾，各區不再重複） */}
      <details className="mb-6 rounded-xl border border-line bg-surface">
        <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium text-muted hover:text-ink">
          資料說明與名詞解釋
        </summary>
        <div className="space-y-1.5 border-t border-line px-4 py-3 text-[11px] leading-relaxed text-faint">
          <p>· <span className="text-muted">能力值卡</span>：各軸為多項指標綜合的全聯盟百分位 [PR]（本季 打 AB≥50／投 IP≥20；生涯 AB≥300／IP≥100）。本季納官方進階（初速／強擊球%／Barrel%／揮空率／wOBA，覆蓋稀疏，無則退回傳統指標）；等級 S–G 由 PR 換算，皆客觀自算。滑鼠移到軸名看組成與權重。</p>
          <p>· <span className="text-muted">官方進階 · PR</span>：stats.cpbl 官方 TrackMan 全季值；色條＝PR（藍低→紅高）。打者為進攻、投手為被打數值。</p>
          <p>· <span className="text-muted">生涯／史上排名</span>：一軍例行賽各季合計（近兩季由逐場補）；史上排名以官方歷年累計、近兩季另計。生涯逐年源 cpbl-opendata（不含當季）。</p>
          <p>· <span className="text-muted">逐球追蹤</span>：部分球場未配置設備、涵蓋場次少於全季，與官方進階全季值會有差異；擊球品質分布紅框＝強勁擊球理想仰角帶（近似 barrel 甜蜜區）。</p>
          <p>· <span className="text-muted">一／二軍</span>：本季主要登錄層級由官網升降事件重建登錄天數判定。主守位＝本季出賽最多的守位或指定打擊（DH 由打擊出賽扣守備推算）。</p>
        </div>
      </details>

      <div className="flex gap-4 text-sm">
        <Link href="/matchups" className="text-accent hover:underline">投打對決 →</Link>
        <Link href="/batters" className="text-muted hover:text-ink">← 返回排行</Link>
      </div>
    </div>
  );
}
