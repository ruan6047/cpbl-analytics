"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
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

// 官方進階數據（stats.cpbl）+ 官方 PR。bl=打者標籤、pl=投手標籤；kind 決定數值格式。
type AdvMetric = { key: string; pr: string; bl: string; pl: string; def: string; kind: "kmh" | "pct" | "rate3" };
const ADV: AdvMetric[] = [
  { key: "ev", pr: "ev_pr", bl: "擊球初速", pl: "被擊球初速", def: "平均擊球初速（km/h），擊球品質核心指標", kind: "kmh" },
  { key: "max_ev", pr: "max_ev_pr", bl: "最高初速", pl: "被最高初速", def: "單季最高擊球初速（km/h）", kind: "kmh" },
  { key: "brlp", pr: "brlp_pr", bl: "Barrel%", pl: "被Barrel%", def: "出色擊球率：兼具理想初速與仰角的強勁擊球占比", kind: "pct" },
  { key: "hardhitp", pr: "hardhitp_pr", bl: "強擊球%", pl: "被強擊球%", def: "強勁擊球（高初速）占比", kind: "pct" },
  { key: "woba", pr: "woba_pr", bl: "wOBA", pl: "被wOBA", def: "加權上壘率（官方計算）", kind: "rate3" },
  { key: "iso", pr: "iso_pr", bl: "ISO", pl: "被ISO", def: "純長打率＝長打率 − 打擊率", kind: "rate3" },
  { key: "slg", pr: "slg_pr", bl: "長打率", pl: "被長打率", def: "長打率 SLG", kind: "rate3" },
  { key: "obp", pr: "obp_pr", bl: "上壘率", pl: "被上壘率", def: "上壘率 OBP", kind: "rate3" },
  { key: "ba", pr: "ba_pr", bl: "打擊率", pl: "被打擊率", def: "打擊率 AVG", kind: "rate3" },
  { key: "chasep", pr: "chasep_pr", bl: "追打%", pl: "誘追打%", def: "好球帶外揮棒比率", kind: "pct" },
  { key: "whiffp", pr: "whiffp_pr", bl: "揮空%", pl: "誘揮空%", def: "揮棒落空比率", kind: "pct" },
  { key: "kp", pr: "kp_pr", bl: "K%", pl: "奪三振%", def: "三振率", kind: "pct" },
  { key: "bbp", pr: "bbp_pr", bl: "BB%", pl: "被保送%", def: "保送率", kind: "pct" },
];
const fmtAdv = (v: number, kind: AdvMetric["kind"]) =>
  kind === "kmh" ? v.toFixed(1) : kind === "pct" ? `${(v * 100).toFixed(1)}%` : v.toFixed(3).replace(/^0\./, ".");

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
  const [advanced, setAdvanced] = useState<{ batting: StatRow | null; pitching: StatRow | null } | null>(null);
  const [disc, setDisc] = useState<{ summary: Record<string, number | null>; points: { x: number; y: number; sw: boolean; wh: boolean }[] } | null>(null);
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
    detail.advanced(id).then(setAdvanced).catch(() => setAdvanced(null));
  }, [id]);

  useEffect(() => {
    if (!profile) return;
    const year = scope === "season" ? 2026 : 9999;
    const k = scope === "season" ? "A" : (kinds.length ? kinds.join(",") : "A");
    detail.splits(id, role, year, k).then((d) => setSplits(d.items)).catch(() => setSplits([]));
  }, [id, role, scope, kinds, profile]);

  // 切換打/投時重設逐月指標、抓好球帶紀律
  useEffect(() => {
    setMonthMetric(role === "batting" ? "ops" : "era");
    setDisc(null);
    detail.discipline(id, role).then(setDisc).catch(() => setDisc(null));
  }, [id, role]);

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

  // 官方進階 + 官方 PR（stats.cpbl）
  const prData = useMemo(() => {
    const a = advanced ? (role === "batting" ? advanced.batting : advanced.pitching) : null;
    if (!a) return [];
    return ADV.map((m) => {
      const val = numOf(a[m.key]);
      const pr = numOf(a[m.pr]);
      return {
        name: role === "batting" ? m.bl : m.pl,
        def: m.def,
        value: val === null ? "—" : fmtAdv(val, m.kind),
        pr: pr === null ? null : Math.round(pr),
      };
    }).filter((d): d is { name: string; def: string; value: string; pr: number } => d.pr !== null);
  }, [advanced, role]);

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
          <h3 className="mb-3 text-sm font-medium text-white/70">官方進階數據 · 百分位 PR</h3>
          {prData.length === 0 ? (
            <p className="py-10 text-center text-sm text-white/30">
              {advanced === null ? "載入中…" : "無官方進階資料"}
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
            來源 stats.cpbl.com.tw 官方 TrackMan/Statcast 數據；數值右側為實際成績，色條＝官方 PR
            （0–100，已定向為「越高＝表現越好」）。{role === "batting" ? "打者為進攻數值" : "投手為被打數值"}。滑過數據名看定義。
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

      {/* 好球帶紀律 */}
      <section className="mb-8">
        <h2 className="mb-1 text-lg font-semibold">好球帶紀律 · {role === "batting" ? "打者" : "投手誘導"}</h2>
        <p className="mb-3 text-[11px] text-white/30">
          依逐球進壘點計算（僅含有 TrackMan 的場次）；好球帶為近似框，追打/好球帶% 僅供參考，
          權威 chase%/whiff% 見上方官方數據。
        </p>
        {!disc ? (
          <p className="text-sm text-white/40">載入中…</p>
        ) : disc.points.length === 0 ? (
          <p className="text-sm text-white/40">無逐球資料。</p>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="grid grid-cols-3 gap-2 self-start">
              {([["揮棒%", "swing_pct"], ["接觸%", "contact_pct"], ["揮空%", "whiff_pct"],
                 ["CSW%", "csw_pct"], ["好球帶%", "zone_pct"], ["追打%", "chase_pct"]] as const).map(([l, k]) => (
                <Card key={l} label={l} value={disc.summary[k] == null ? "—" : `${disc.summary[k]}%`} />
              ))}
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <h3 className="mb-2 text-sm font-medium text-white/70">進壘點散布（{disc.points.length} 球）</h3>
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis type="number" dataKey="x" domain={[-0.8, 0.8]} {...axis} tickFormatter={() => ""} />
                  <YAxis type="number" dataKey="y" domain={[-0.2, 1.6]} {...axis} tickFormatter={() => ""} />
                  <ZAxis range={[18, 18]} />
                  <ReferenceArea x1={-0.21} x2={0.21} y1={0.5} y2={1.0}
                    stroke="rgba(255,255,255,0.45)" fill="rgba(255,255,255,0.04)" />
                  <Tooltip {...tooltipStyle} cursor={{ strokeDasharray: "3 3" }} />
                  <Scatter name="未揮棒" data={disc.points.filter((p) => !p.sw)} fill="rgba(255,255,255,0.25)" />
                  <Scatter name="揮棒" data={disc.points.filter((p) => p.sw && !p.wh)} fill="#34d399" />
                  <Scatter name="揮空" data={disc.points.filter((p) => p.wh)} fill="#f87171" />
                </ScatterChart>
              </ResponsiveContainer>
              <p className="mt-1 text-[11px] text-white/30">綠＝揮棒（擊中/界外）、紅＝揮空、灰＝未揮棒；白框＝好球帶(近似)。</p>
            </div>
          </div>
        )}
      </section>

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
