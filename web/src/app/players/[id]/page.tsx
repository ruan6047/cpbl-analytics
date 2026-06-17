"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { detail, type PlayerProfile, type StatRow } from "@/lib/client";

type Role = "batting" | "pitching";

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
  const ip = ipOf(r);
  const er = numOf(r.earned_runs);
  return ip && ip > 0 && er !== null ? (er * 9) / ip : null;
};
const whipOf = (r: StatRow) => {
  const ip = ipOf(r);
  const h = numOf(r.hits);
  const bb = numOf(r.bb);
  return ip && ip > 0 && h !== null && bb !== null ? (h + bb) / ip : null;
};

const MONTHS = ["三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月"];

// 逐月趨勢可選的數據
type Metric = { key: string; label: string; dp: number; get: (r: StatRow) => number | null };
const BAT_METRICS: Metric[] = [
  { key: "ops", label: "OPS", dp: 3, get: (r) => numOf(r.ops) },
  { key: "avg", label: "打擊率", dp: 3, get: (r) => numOf(r.avg) },
  { key: "obp", label: "上壘率", dp: 3, get: (r) => numOf(r.obp) },
  { key: "slg", label: "長打率", dp: 3, get: (r) => numOf(r.slg) },
  { key: "hits", label: "安打", dp: 0, get: (r) => numOf(r.hits) },
  { key: "home_runs", label: "全壘打", dp: 0, get: (r) => numOf(r.home_runs) },
  { key: "rbi", label: "打點", dp: 0, get: (r) => numOf(r.rbi) },
  { key: "bb", label: "四壞", dp: 0, get: (r) => numOf(r.bb) },
  { key: "so", label: "三振", dp: 0, get: (r) => numOf(r.so) },
];
const PIT_METRICS: Metric[] = [
  { key: "era", label: "ERA", dp: 2, get: eraOf },
  { key: "whip", label: "WHIP", dp: 2, get: whipOf },
  { key: "so", label: "三振", dp: 0, get: (r) => numOf(r.so) },
  { key: "bb", label: "四壞", dp: 0, get: (r) => numOf(r.bb) },
  { key: "hits", label: "被安打", dp: 0, get: (r) => numOf(r.hits) },
  { key: "ip", label: "局數", dp: 1, get: ipOf },
];

// 百分位 PR：以本季成績對全聯盟母體排名。higher=數值越大越好；fmt 顯示實際值；def 為說明。
type PrMetric = {
  label: string;
  def: string;
  higher: boolean;
  fmt: (v: number) => string;
  get: (r: StatRow) => number | null;
};
const f3s = (v: number) => v.toFixed(3).replace(/^0\./, ".");
const f2s = (v: number) => v.toFixed(2);
const f1p = (v: number) => `${v.toFixed(1)}%`;
const iStr = (v: number) => String(Math.round(v));
const rate = (a: number | null, b: number | null) => (a !== null && b && b > 0 ? a / b : null);

const BAT_PR: PrMetric[] = [
  { label: "打擊率", def: "AVG＝安打 ÷ 打數", higher: true, fmt: f3s, get: (r) => numOf(r.avg) },
  { label: "上壘率", def: "OBP＝(安打+四壞+死球) ÷ (打數+四壞+死球+高飛犧牲)", higher: true, fmt: f3s, get: (r) => numOf(r.obp) },
  { label: "長打率", def: "SLG＝壘打數 ÷ 打數", higher: true, fmt: f3s, get: (r) => numOf(r.slg) },
  { label: "OPS", def: "上壘率＋長打率，綜合攻擊力", higher: true, fmt: f3s, get: (r) => numOf(r.ops) },
  { label: "ISO", def: "純長打率＝長打率 − 打擊率，衡量長打能力", higher: true, fmt: f3s, get: (r) => {
      const slg = numOf(r.slg), avg = numOf(r.avg);
      return slg !== null && avg !== null ? slg - avg : null;
    } },
  { label: "BABIP", def: "場內球安打率＝(安打−全壘打) ÷ (打數−三振−全壘打+高飛犧牲)，反映場內球運氣/品質", higher: true, fmt: f3s, get: (r) => {
      const h = numOf(r.h), hr = numOf(r.hr), ab = numOf(r.ab), so = numOf(r.so), sf = numOf(r.sf) ?? 0;
      if (h === null || hr === null || ab === null || so === null) return null;
      const den = ab - so - hr + sf;
      return den > 0 ? (h - hr) / den : null;
    } },
  { label: "全壘打", def: "本季全壘打數", higher: true, fmt: iStr, get: (r) => numOf(r.hr) },
  { label: "打點", def: "本季打點數", higher: true, fmt: iStr, get: (r) => numOf(r.rbi) },
  { label: "盜壘", def: "本季盜壘成功數", higher: true, fmt: iStr, get: (r) => numOf(r.sb) },
  { label: "BB%", def: "保送率＝四壞 ÷ 打席，選球能力（越高越好）", higher: true, fmt: f1p, get: (r) => { const x = rate(numOf(r.bb), numOf(r.pa)); return x === null ? null : x * 100; } },
  { label: "K%", def: "三振率＝三振 ÷ 打席（越低越好）", higher: false, fmt: f1p, get: (r) => { const x = rate(numOf(r.so), numOf(r.pa)); return x === null ? null : x * 100; } },
];

const PIT_PR: PrMetric[] = [
  { label: "防禦率", def: "ERA＝自責分 ×9 ÷ 投球局數（越低越好）", higher: false, fmt: f2s, get: (r) => numOf(r.era) },
  { label: "WHIP", def: "每局被上壘率＝(被安打+四壞) ÷ 局數（越低越好）", higher: false, fmt: f2s, get: (r) => numOf(r.whip) },
  { label: "被打擊率", def: "對戰打者被打出安打的機率（近似 安打 ÷ (打席−四壞−死球)）", higher: false, fmt: f3s, get: (r) => rate(numOf(r.h), (numOf(r.pa) ?? 0) - (numOf(r.bb) ?? 0) - (numOf(r.hbp) ?? 0)) },
  { label: "K%", def: "三振率＝奪三振 ÷ 面對打席（越高越好）", higher: true, fmt: f1p, get: (r) => { const x = rate(numOf(r.so), numOf(r.pa)); return x === null ? null : x * 100; } },
  { label: "BB%", def: "保送率＝投出四壞 ÷ 面對打席（越低越好）", higher: false, fmt: f1p, get: (r) => { const x = rate(numOf(r.bb), numOf(r.pa)); return x === null ? null : x * 100; } },
  { label: "K9", def: "每九局奪三振＝三振 ×9 ÷ 局數", higher: true, fmt: f2s, get: (r) => numOf(r.k9) },
  { label: "LOB%", def: "殘壘率＝(被安+四壞+死球−失分) ÷ (被安+四壞+死球−1.4×被全壘打)，越高越能化解危機", higher: true, fmt: f1p, get: (r) => {
      const h = numOf(r.h), bb = numOf(r.bb), hbp = numOf(r.hbp) ?? 0, run = numOf(r.r), hr = numOf(r.hr);
      if (h === null || bb === null || run === null || hr === null) return null;
      const den = h + bb + hbp - 1.4 * hr;
      return den > 0 ? Math.min(100, ((h + bb + hbp - run) / den) * 100) : null;
    } },
  { label: "局數", def: "本季投球局數", higher: true, fmt: (v) => v.toFixed(1), get: ipOf },
];

function percentile(pop: (number | null)[], val: number | null, higher: boolean): number | null {
  if (val === null) return null;
  const vals = pop.filter((v): v is number => v !== null && !Number.isNaN(v));
  if (!vals.length) return null;
  const cnt = vals.filter((v) => (higher ? v <= val : v >= val)).length;
  return Math.round((cnt / vals.length) * 100);
}

const prColor = (v: number) => (v >= 80 ? "#34d399" : v >= 55 ? "#a3e635" : v >= 35 ? "#fbbf24" : "#f87171");

function Toggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { v: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex gap-1 rounded-lg bg-white/5 p-1">
      {options.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className={`rounded-md px-3 py-1 text-sm transition ${
            value === o.v ? "bg-emerald-500 text-black" : "text-white/60 hover:text-white"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Card({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-3 text-center">
      <div className="text-[11px] text-white/40">{label}</div>
      <div className={`mt-1 font-mono text-lg tabular-nums ${accent ? "text-emerald-400" : ""}`}>{value}</div>
    </div>
  );
}

const axis = { tick: { fill: "rgba(255,255,255,0.4)", fontSize: 12 }, stroke: "rgba(255,255,255,0.15)" };
const tooltipStyle = {
  contentStyle: { background: "#27272a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#fff" },
};

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [role, setRole] = useState<Role>("batting");
  const [scope, setScope] = useState<"season" | "career">("season");
  const [kinds, setKinds] = useState<string[]>(["A"]); // 生涯可複選賽別
  const [season, setSeason] = useState<{ batting: StatRow | null; pitching: StatRow | null } | null>(null);
  const [splits, setSplits] = useState<StatRow[] | null>(null);
  const [monthMetric, setMonthMetric] = useState("ops");
  const [population, setPopulation] = useState<StatRow[] | null>(null);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);

  useEffect(() => {
    detail
      .profile(id)
      .then((d) => {
        if (!d.player) return setNotFound(true);
        setProfile(d.player);
        setRole(d.player.is_batter ? "batting" : "pitching");
      })
      .catch(() => setNotFound(true));
    detail.season(id).then(setSeason).catch(() => setSeason(null));
  }, [id]);

  useEffect(() => {
    if (!profile) return;
    const year = scope === "season" ? 2026 : 9999;
    const k = scope === "season" ? "A" : (kinds.length ? kinds.join(",") : "A");
    detail.splits(id, role, year, k).then((d) => setSplits(d.items)).catch(() => setSplits([]));
  }, [id, role, scope, kinds, profile]);

  // 切換打/投時，重設逐月指標並抓對應母體
  useEffect(() => {
    setMonthMetric(role === "batting" ? "ops" : "era");
    setPopulation(null);
    detail.leaders(role).then((d) => setPopulation(d.items)).catch(() => setPopulation([]));
  }, [role]);

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

  // 百分位 PR：以本季成績對全聯盟（有門檻）母體排名
  const prData = useMemo(() => {
    const s = season ? (role === "batting" ? season.batting : season.pitching) : null;
    if (!s || !population) return [];
    const defs = role === "batting" ? BAT_PR : PIT_PR;
    const pop = population.filter((p) =>
      role === "batting" ? (numOf(p.pa) ?? 0) >= 50 : (numOf(p.ip) ?? 0) >= 20,
    );
    return defs
      .map((d) => {
        const val = d.get(s);
        return {
          name: d.label,
          def: d.def,
          value: val === null ? "—" : d.fmt(val),
          pr: percentile(pop.map((p) => d.get(p)), val, d.higher),
        };
      })
      .filter((d): d is { name: string; def: string; value: string; pr: number } => d.pr !== null);
  }, [season, population, role]);

  if (notFound) return <p className="text-sm text-white/50">查無此球員。</p>;
  if (!profile) return <p className="text-sm text-white/40">載入中…</p>;

  const roles: { v: Role; label: string }[] = [];
  if (profile.is_batter) roles.push({ v: "batting", label: "打擊" });
  if (profile.is_pitcher) roles.push({ v: "pitching", label: "投球" });

  const s = season ? (role === "batting" ? season.batting : season.pitching) : null;

  return (
    <div>
      <header className="mb-6">
        <Link href="/batters" className="text-xs text-white/40 hover:text-emerald-400">← 返回排行</Link>
        <h1 className="mt-2 text-3xl font-bold">{profile.name}</h1>
        <p className="mt-1 text-sm text-white/50">
          {profile.team ?? "—"}
          {profile.bats && <span className="ml-3">打 {profile.bats}</span>}
          {profile.throws && <span className="ml-2">投 {profile.throws}</span>}
        </p>
      </header>

      {roles.length > 1 && (
        <div className="mb-5">
          <Toggle<Role> options={roles} value={role} onChange={setRole} />
        </div>
      )}

      {/* 本季成績卡 */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">本季成績</h2>
        {!s ? (
          <p className="text-sm text-white/40">本季無{role === "batting" ? "打擊" : "投球"}成績。</p>
        ) : (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            {role === "batting"
              ? [
                  ["打擊率", f3(s.avg), true],
                  ["上壘率", f3(s.obp)],
                  ["長打率", f3(s.slg)],
                  ["OPS", f3(s.ops), true],
                  ["全壘打", String(s.hr ?? "—")],
                  ["打點", String(s.rbi ?? "—")],
                  ["安打", String(s.h ?? "—")],
                  ["盜壘", String(s.sb ?? "—")],
                  ["打席", String(s.pa ?? "—")],
                  ["出賽", String(s.g ?? "—")],
                ].map(([l, v, a]) => <Card key={l as string} label={l as string} value={v as string} accent={a as boolean} />)
              : [
                  ["防禦率", numOf(s.era)?.toFixed(2) ?? "—", true],
                  ["WHIP", numOf(s.whip)?.toFixed(2) ?? "—"],
                  ["勝-敗", `${s.w ?? 0}-${s.l ?? 0}`],
                  ["局數", numOf(s.ip)?.toFixed(1) ?? "—"],
                  ["三振", String(s.so ?? "—"), true],
                  ["K9", numOf(s.k9)?.toFixed(2) ?? "—"],
                  ["救援", String(s.sv ?? "—")],
                  ["中繼", String(s.hld ?? "—")],
                  ["自責", String(s.er ?? "—")],
                  ["出賽", String(s.g ?? "—")],
                ].map(([l, v, a]) => <Card key={l as string} label={l as string} value={v as string} accent={a as boolean} />)}
          </div>
        )}
      </section>

      {/* 分項範圍切換 */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Toggle
          options={[
            { v: "season", label: "本季" },
            { v: "career", label: "生涯" },
          ]}
          value={scope}
          onChange={setScope}
        />
        {scope === "career" && (
          <div className="inline-flex flex-wrap gap-2">
            {([["A", "例行賽"], ["C", "總冠軍"], ["E", "季後賽"]] as const).map(([k, label]) => {
              const on = kinds.includes(k);
              return (
                <button
                  key={k}
                  onClick={() =>
                    setKinds(on ? (kinds.length > 1 ? kinds.filter((x) => x !== k) : kinds) : [...kinds, k])
                  }
                  className={`rounded-full px-3 py-1 text-sm transition ${
                    on ? "bg-emerald-500 text-black" : "bg-white/5 text-white/60 hover:bg-white/10"
                  }`}
                >
                  {label}
                </button>
              );
            })}
            <span className="self-center text-xs text-white/30">可複選</span>
          </div>
        )}
      </div>

      {/* 選手分析圖表 */}
      <section className="mb-8 grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-medium text-white/70">逐月趨勢</h3>
            <select
              value={monthMetric}
              onChange={(e) => setMonthMetric(e.target.value)}
              className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs outline-none focus:border-emerald-400"
            >
              {metrics.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          {monthData.length === 0 ? (
            <p className="py-10 text-center text-sm text-white/30">無資料</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={monthData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="name" {...axis} />
                <YAxis {...axis} domain={["auto", "auto"]} />
                <Tooltip {...tooltipStyle} formatter={(v: number) => v?.toFixed(metric.dp)} />
                <Line type="monotone" dataKey="v" name={metric.label} stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <h3 className="mb-3 text-sm font-medium text-white/70">本季百分位 PR（vs 全聯盟）</h3>
          {prData.length === 0 ? (
            <p className="py-10 text-center text-sm text-white/30">
              {population === null ? "計算中…" : "本季無足夠資料"}
            </p>
          ) : (
            <div className="space-y-1.5">
              {prData.map((d) => (
                <div key={d.name} className="flex items-center gap-2.5 text-sm">
                  <span
                    onMouseEnter={(e) => setTip({ text: d.def, x: e.clientX, y: e.clientY })}
                    onMouseMove={(e) => setTip({ text: d.def, x: e.clientX, y: e.clientY })}
                    onMouseLeave={() => setTip(null)}
                    className="w-16 shrink-0 cursor-help text-white/70 underline decoration-white/25 decoration-dotted underline-offset-4"
                  >
                    {d.name}
                  </span>
                  <div className="relative h-4 flex-1 overflow-hidden rounded bg-white/5">
                    <div className="h-full rounded" style={{ width: `${d.pr}%`, background: prColor(d.pr) }} />
                  </div>
                  <span className="w-12 shrink-0 text-right font-mono tabular-nums">{d.value}</span>
                  <span className="w-9 shrink-0 text-right font-mono text-xs text-white/40">{d.pr}</span>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-[11px] text-white/30">
            數值右側為實際成績，色條長度＝PR（0–100，50＝聯盟中位）。母體為{role === "batting" ? "打席≥50" : "局數≥20"}的球員；
            防禦率/WHIP/被打擊率/打者K% 已轉為「PR 越高＝表現越好」。滑過數據名看定義。
          </p>
        </div>
      </section>

      {tip && (
        <div
          className="pointer-events-none fixed z-50 max-w-xs rounded-md border border-white/10 bg-zinc-800 px-2.5 py-1.5 text-xs leading-relaxed text-white shadow-xl"
          style={{ left: tip.x + 14, top: tip.y + 16 }}
        >
          {tip.text}
        </div>
      )}

      {/* 分項明細表 */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">分項明細</h2>
        {!splits ? (
          <p className="text-sm text-white/40">載入中…</p>
        ) : splits.length === 0 ? (
          <p className="text-sm text-white/40">此範圍無分項資料。</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-left text-white/50">
                <tr>
                  {(role === "batting"
                    ? ["分項", "打席", "打數", "安打", "全壘打", "打點", "四壞", "三振", "打擊率", "上壘率", "長打率", "OPS"]
                    : ["分項", "局數", "面對", "被安", "被轟", "四壞", "三振", "失分", "自責", "ERA"]
                  ).map((h) => (
                    <th key={h} className="whitespace-nowrap px-2.5 py-2.5 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {splits.map((r, i) => (
                  <tr key={i} className="border-t border-white/5 hover:bg-white/5">
                    <td className="whitespace-nowrap px-2.5 py-2 font-sans text-white/80">{String(r.item_name)}</td>
                    {role === "batting" ? (
                      <>
                        <td className="px-2.5 py-2">{String(r.plate_appearances ?? "—")}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.at_bats ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.hits ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.home_runs ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.rbi ?? "—")}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.bb ?? "—")}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.so ?? "—")}</td>
                        <td className="px-2.5 py-2">{f3(r.avg)}</td>
                        <td className="px-2.5 py-2">{f3(r.obp)}</td>
                        <td className="px-2.5 py-2">{f3(r.slg)}</td>
                        <td className="px-2.5 py-2 text-emerald-400">{f3(r.ops)}</td>
                      </>
                    ) : (
                      <>
                        <td className="px-2.5 py-2">{ipOf(r)?.toFixed(1) ?? "—"}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.plate_appearances ?? "—")}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.hits ?? "—")}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.home_runs ?? "—")}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.bb ?? "—")}</td>
                        <td className="px-2.5 py-2">{String(r.so ?? "—")}</td>
                        <td className="px-2.5 py-2 text-white/50">{String(r.runs ?? "—")}</td>
                        <td className="px-2.5 py-2 text-rose-400/80">{String(r.earned_runs ?? "—")}</td>
                        <td className="px-2.5 py-2 text-emerald-400">{eraOf(r)?.toFixed(2) ?? "—"}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="mt-8">
        <Link href="/matchups" className="text-sm text-emerald-400 hover:underline">
          查看投打對決 →
        </Link>
      </div>
    </div>
  );
}
