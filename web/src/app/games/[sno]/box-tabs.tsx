"use client";

// Box Score 標籤頁（UX-6）：官網式單隊分頁（客隊/主隊）＋「分析」比較 tab。
// 單隊獨佔全寬 → 補棒次/守位/季AVG（打者）與 面對/好球率（投手）欄；
// 分析四圖（攻擊對比/累計得分/投手用球/球速分布）全部從既有 gameLive payload
// 客戶端推導，零新請求。圖表色：隊伍＝teamColor（entity 固定色，每圖必附隊名
// 標籤，identity 不 color-alone）；軸/格線/tooltip 走 useChartTheme（深淺主題）。
// 好球數＝總球數−壞球（界內球 is_ball/is_strike 皆 f，不能數 is_strike）。

import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { clientGet, type StatRow } from "@/lib/client";
import { fmtIPParts } from "@/lib/format";
import { Card, PlayerLink, TeamLogo, Skeleton, ErrorState, EmptyState, ENTITY_LINK } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { chartAxis, chartTooltip, useChartTheme } from "@/lib/chart-theme";
import { teamColor, teamShort } from "@/lib/teams";
import { DEFEND_ZH, type Live } from "@/components/game-board";
import { SprayChart } from "@/components/spray-chart";

// 主審判決分布（描述性）：逐球位置＋判決（好球/壞球）。刻意無對錯/準確率/誤判欄位
// （§5.12 NO-GO）。固定規則帶僅作散點的空間參考。
type UmpirePitch = {
  side: number;
  height: number;
  called_strike: boolean;
  inning_seq: number | null;
  pitcher_name: string | null;
  hitter_name: string | null;
  ball_cnt: number | null;
  strike_cnt: number | null;
  out_cnt: number | null;
};

type UmpireCardData = {
  season: number;
  game_sno: number;
  summary: {
    umpire: string | null;
    called: number;
    called_strikes: number;
    called_balls: number;
  };
  game: {
    game_date: string;
    venue: string | null;
    home_team_name: string;
    away_team_name: string;
    home_score: number;
    away_score: number;
  } | null;
  zone: {
    half_width: number;
    bot: number;
    top: number;
  };
  pitches: UmpirePitch[];
};

const n = (v: StatRow[string] | undefined) => Number(v) || 0;
const i0 = (v: StatRow[string]) => (v === null || v === undefined ? "—" : String(v));
const avg3 = (v: number) => v.toFixed(3).replace(/^0/, "");
const ipTxt = (r: StatRow) => fmtIPParts(r.inning_pitched_cnt as number | null, r.inning_pitched_div3 as number | null);
const tint = (c: string) => `color-mix(in srgb, ${c} 35%, transparent)`; // 同隊次要段（壞球）

// 打者亮點標記：滿貫/猛打賞(3安+)/致勝打點/MVP
function batterMark(r: StatRow): string {
  const t: string[] = [];
  if (n(r.grand_slam)) t.push("滿貫");
  if (n(r.hits) >= 3) t.push("猛打賞");
  if (n(r.gw_rbi)) t.push("致勝打點");
  if (r.is_mvp) t.push("MVP");
  return t.join("·");
}
const MARK: Record<string, { text: string; tone: "pos" | "neg" }> = {
  W: { text: "勝", tone: "pos" }, L: { text: "敗", tone: "neg" },
  SV: { text: "SV", tone: "pos" }, HLD: { text: "H", tone: "pos" },
  BS: { text: "救援失敗", tone: "neg" }, BH: { text: "中繼失敗", tone: "neg" },
};
function pitcherMarks(r: StatRow, decisions: Record<string, string>): { text: string; tone: "pos" | "neg" }[] {
  const out: { text: string; tone: "pos" | "neg" }[] = [];
  const d = decisions[String(r.pitcher_acnt)];
  if (d) for (const tok of d.split("·")) if (MARK[tok]) out.push(MARK[tok]);
  if (r.is_complete_game) out.push({ text: r.is_shutout ? "完封" : "完投", tone: "pos" });
  return out;
}

// ───────────────────────── 單隊表 ─────────────────────────
function BattingTable({ rows, avgMap, posBy }: {
  rows: StatRow[]; avgMap: Record<string, number>; posBy: Map<string, string>;
}) {
  const cols: [string, (r: StatRow) => string][] = [
    ["打數", (r) => i0(r.at_bats)], ["得分", (r) => i0(r.runs)], ["安打", (r) => i0(r.hits)],
    ["二安", (r) => i0(r.doubles)], ["三安", (r) => i0(r.triples)], ["全打", (r) => i0(r.home_runs)],
    ["打點", (r) => i0(r.rbi)], ["四壞", (r) => i0(r.bb)], ["三振", (r) => i0(r.so)], ["盜壘", (r) => i0(r.sb)],
  ];
  const columns: Column<StatRow>[] = [
    // 「棒次」不做：livelog batting_order 是「該局第幾位」非先發棒次（實測每人一場 2–4 值），無可靠棒次來源
    { header: "守", cell: (r) => posBy.get(String(r.hitter_acnt)) ?? "—", align: "center", nowrap: true, className: "font-sans text-[11px] text-muted" },
    {
      header: "打者",
      cell: (r) => {
        const mark = batterMark(r);
        return (
          <><PlayerLink pid={String(r.hitter_acnt ?? "")} name={String(r.hitter_name ?? "")} className="hover:text-accent hover:underline" />
            <span className="ml-1 text-[10px] text-faint">{String(r.role_type ?? "")}</span>
            {mark && <span className="ml-1 text-[10px] font-semibold text-cpbl">{mark}</span>}</>
        );
      },
      nowrap: true, className: "font-sans text-ink",
    },
    ...cols.map(([h, f]): Column<StatRow> => ({ header: h, cell: f, align: "right" })),
    {
      header: "季AVG", align: "right",
      cell: (r) => { const a = avgMap[String(r.hitter_acnt)]; return a !== undefined ? avg3(a) : "—"; },
      className: "text-muted",
    },
  ];
  return <DataTable columns={columns} rows={rows} rowKey={(_r, i) => i} dense />;
}

function PitchingTable({ rows, decisions, ballsBy, paBy }: {
  rows: StatRow[]; decisions: Record<string, string>;
  ballsBy: Map<string, number>; paBy: Map<string, number>;
}) {
  const strikePct = (r: StatRow) => {
    const total = n(r.pitch_cnt);
    if (!total) return "—";
    const balls = ballsBy.get(String(r.pitcher_acnt)) ?? 0;
    return `${Math.round(((total - balls) / total) * 100)}%`;
  };
  const cols: [string, (r: StatRow) => string][] = [
    ["局數", ipTxt],
    ["面對", (r) => { const pa = paBy.get(String(r.pitcher_acnt)); return pa ? String(pa) : "—"; }],
    ["球數", (r) => i0(r.pitch_cnt)], ["好球率", strikePct],
    ["被安", (r) => i0(r.hits)], ["失分", (r) => i0(r.runs)], ["自責", (r) => i0(r.earned_runs)],
    ["四壞", (r) => i0(r.bb)], ["三振", (r) => i0(r.so)], ["被轟", (r) => i0(r.home_runs)],
    ["最快", (r) => (r.max_speed ? `${r.max_speed}` : "—")],
  ];
  const columns: Column<StatRow>[] = [
    {
      header: "投手",
      cell: (r) => (
        <><PlayerLink pid={String(r.pitcher_acnt ?? "")} name={String(r.pitcher_name ?? "")} className="hover:text-accent hover:underline" />
          {pitcherMarks(r, decisions).map((m, j) => (
            <span key={j} className={`ml-1 text-[10px] font-semibold ${m.tone === "neg" ? "text-down" : "text-accent"}`}>{m.text}</span>
          ))}</>
      ),
      nowrap: true, className: "font-sans text-ink",
    },
    ...cols.map(([h, f]): Column<StatRow> => ({ header: h, cell: f, align: "right" })),
  ];
  return <DataTable columns={columns} rows={rows} rowKey={(_r, i) => i} dense />;
}

// ───────────────────────── 分析圖 ─────────────────────────
function LegendRow({ awayName, homeName, ac, hc }: { awayName: string; homeName: string; ac: string; hc: string }) {
  return (
    <span className="flex items-center gap-3 text-[10px] text-muted">
      <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-full" style={{ background: ac }} />客 {awayName}</span>
      <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-full" style={{ background: hc }} />主 {homeName}</span>
    </span>
  );
}

// 手刻對比條（取代 recharts 蝴蝶條——負值堆疊+LabelList 行為不可控）：
// 中央分軸、客左主右、列內以 max 正規化；粗體＝較佳方（lowBetter 反向）。
type CmpItem = {
  label: string; note?: string; a: number | null; h: number | null;
  fmt: (v: number) => string; subA?: string; subH?: string; lowBetter?: boolean;
};
function CompareRows({ items, ac, hc }: { items: CmpItem[]; ac: string; hc: string }) {
  return (
    <div className="space-y-3 px-1 pb-1">
      {items.map((row) => {
        const max = Math.max(row.a ?? 0, row.h ?? 0);
        const w = (v: number | null) => (v != null && max > 0 ? `${Math.max(4, (v / max) * 100)}%` : "0%");
        const better = (v: number | null, o: number | null) =>
          v != null && o != null && v !== o && (row.lowBetter ? v < o : v > o);
        return (
          <div key={row.label}>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
              <span className={`font-mono tabular-nums ${better(row.a, row.h) ? "font-bold text-ink" : "text-muted"}`}>
                {row.a != null ? row.fmt(row.a) : "—"}
                {row.subA && <span className="ml-1 font-sans text-[9px] font-normal text-faint">{row.subA}</span>}
              </span>
              <span className="whitespace-nowrap text-center text-muted">
                {row.label}
                {row.note && <span className="ml-1 text-[9px] text-faint">{row.note}</span>}
              </span>
              <span className={`text-right font-mono tabular-nums ${better(row.h, row.a) ? "font-bold text-ink" : "text-muted"}`}>
                {row.subH && <span className="mr-1 font-sans text-[9px] font-normal text-faint">{row.subH}</span>}
                {row.h != null ? row.fmt(row.h) : "—"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1">
              <div className="flex justify-end"><div className="h-1.5 rounded-full" style={{ width: w(row.a), background: ac }} /></div>
              <div><div className="h-1.5 rounded-full" style={{ width: w(row.h), background: hc }} /></div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ChartCard({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <Card padding="p-3" className="min-w-0">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 px-1">
        <span className="text-sm font-semibold">{title}</span>
        {note && <span className="text-[10px] text-faint">{note}</span>}
      </div>
      {children}
    </Card>
  );
}

export default function BoxTabs({ data }: { data: Live }) {
  const g = data.game!;
  const ct = useChartTheme();
  const ac = String(g.away_team_code ?? ""), hc = String(g.home_team_code ?? "");
  const awayColor = teamColor(ac), homeColor = teamColor(hc);
  const awayName = String(g.away_team_name ?? ""), homeName = String(g.home_team_name ?? "");

  const sp = useSearchParams();
  const defaultTab = (sp.get("tab") as "away" | "home" | "ana" | "umpire") || "away";
  const [tab, setTab] = useState<"away" | "home" | "ana" | "umpire">(defaultTab);

  const [umpCard, setUmpCard] = useState<UmpireCardData | null>(null);
  const [umpLoading, setUmpLoading] = useState(false);
  const [umpError, setUmpError] = useState(false);

  const gameSno = data.game ? Number(data.game.game_sno) : null;

  // 賽事切換（同頁面元件重用，App Router 不會因 params 變動而重掛載）時，
  // 前一場的主審判決分布不得沿用——依 gameSno 重置後再讓下方 effect 重新抓該場資料。
  useEffect(() => {
    setUmpCard(null);
    setUmpError(false);
    setUmpLoading(false);
  }, [gameSno]);

  useEffect(() => {
    if (tab === "umpire" && !umpCard && !umpError && data.game) {
      let cancelled = false;
      setUmpLoading(true);
      const season = Number(data.game.year || 2026);
      const kindCode = String(data.game.kind_code || "A");
      clientGet<UmpireCardData>(`/api/v1/games/${gameSno}/umpire?season=${season}&kind_code=${kindCode}`)
        .then((c) => {
          if (cancelled) return;   // 換場後才回來的舊請求：捨棄，不覆寫新場次 state
          setUmpCard(c);
          setUmpLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          setUmpError(true);
          setUmpLoading(false);
        });
      // gameSno 變動會先跑這個 cleanup 再重跑 effect：把當次請求標記作廢，
      // 避免前一場較慢的回應在切場後才落地、蓋掉新場次的 umpCard。
      return () => { cancelled = true; };
    }
  }, [tab, umpCard, umpError, data.game, gameSno]);

  const W = 340, H = 400, sc = 178;
  const px = (s: number) => W / 2 + s * sc;
  const py = (h: number) => H - 15 - h * ((H - 30) / 2.05);

  // livelog 衍生：棒次/守位（打者首事件）、壞球數/面對打席（投手）、得點圈打席（隊）
  const derived = useMemo(() => {
    const posBy = new Map<string, string>();
    const ballsBy = new Map<string, number>(), paBy = new Map<string, number>();
    // 得點圈＝打席首事件時二/三壘有人；AB/安打以打席末事件 action_name 判
    const risp: Record<string, { ab: number; hits: number }> = { "1": { ab: 0, hits: 0 }, "2": { ab: 0, hits: 0 } };
    // 投手指數素材（key＝投球方 side：上半客隊打擊→主隊投）：首球好球、揮空/揮擊
    const pIdx: Record<string, { fpS: number; fpTot: number; miss: number; swing: number }> = {
      "1": { fpS: 0, fpTot: 0, miss: 0, swing: 0 }, "2": { fpS: 0, fpTot: 0, miss: 0, swing: 0 },
    };
    let curHitter = "", curHalf = "", lastPitcher = "";
    let paRisp = false, paSide = "", paLast: StatRow | null = null;
    const flush = () => {
      if (curHitter && lastPitcher) paBy.set(lastPitcher, (paBy.get(lastPitcher) ?? 0) + 1);
      if (curHitter && paRisp && paLast && risp[paSide]) {
        const act = String(paLast.action_name ?? "");
        if (act && !/四壞|敬遠|觸身|犧牲|妨礙/.test(act)) {
          risp[paSide].ab++;
          if (/安打|全壘打/.test(act)) risp[paSide].hits++;
        }
      }
      curHitter = ""; paRisp = false; paLast = null;
    };
    for (const r of data.livelog) {
      const half = `${r.inning_seq}|${r.visiting_home_type}`;
      if (half !== curHalf) { flush(); curHalf = half; }
      if (r.is_ball) {
        const p = String(r.pitcher_acnt ?? "");
        if (p) ballsBy.set(p, (ballsBy.get(p) ?? 0) + 1);
      }
      if (r.is_change_player || !r.hitter_acnt) continue;
      const h = String(r.hitter_acnt);
      const pitchSide = String(r.visiting_home_type) === "1" ? "2" : "1";   // 投球方
      if (h !== curHitter) {
        flush();
        curHitter = h;
        paRisp = Boolean(r.second_base || r.third_base);   // 打席開始時的壘況
        paSide = String(r.visiting_home_type ?? "");
        // 首球：打席島首事件即第一球（is_ball 才算壞球；界內/界外/揮空/好球皆好球）
        pIdx[pitchSide].fpTot++;
        if (!r.is_ball) pIdx[pitchSide].fpS++;
      }
      // 揮擊事件：揮空 or 擊出（界外＋場內）；whiff＝揮空/揮擊
      const c = String(r.content ?? "");
      if (/揮棒落空/.test(c)) { pIdx[pitchSide].miss++; pIdx[pitchSide].swing++; }
      else if (/擊出/.test(c)) pIdx[pitchSide].swing++;
      paLast = r;
      lastPitcher = String(r.pitcher_acnt ?? "");
      if (!posBy.has(h)) {
        const z = DEFEND_ZH[String(r.defend_station_code ?? "")];
        if (z) posBy.set(h, z);
      }
    }
    flush();
    return { posBy, ballsBy, paBy, risp, pIdx };
  }, [data.livelog]);

  const side = (vht: string, rows: StatRow[]) => rows.filter((r) => String(r.visiting_home_type) === vht);

  // C1 進攻效率對比：比率型指標（box 一眼看不出的），單場計算
  //   上壘率 (H+BB+HBP)/(AB+BB+HBP+SF)、長打率 TB/AB、得點圈打擊率（livelog 打席島）、
  //   得分效率 得分÷上壘人次、三振率 SO/PA（越低越好）
  const rates = useMemo(() => {
    const calc = (vht: "1" | "2") => {
      const b = side(vht, data.batting);
      const S = (k: string) => b.reduce((s, r) => s + n(r[k]), 0);
      const ab = S("at_bats"), h = S("hits"), bb = S("bb"), hbp = S("hbp"), sf = S("sac_fly");
      const tb = S("total_bases"), so = S("so"), pa = S("plate_appearances");
      const runs = vht === "1" ? n(g.away_score) : n(g.home_score);
      const obpDen = ab + bb + hbp + sf, reach = h + bb + hbp;
      const rp = derived.risp[vht];
      return {
        obp: obpDen ? (h + bb + hbp) / obpDen : null,
        slg: ab ? tb / ab : null,
        risp: rp.ab ? rp.hits / rp.ab : null, rispTxt: rp.ab ? `${rp.hits}/${rp.ab}` : "無打席",
        eff: reach ? runs / reach : null,
        kr: pa ? so / pa : null,
      };
    };
    return { a: calc("1"), h: calc("2") };
  }, [data.batting, derived.risp, g]);

  // C2 投手效率對比（隊級指數；vht＝該隊 pitching box 側）
  const pRates = useMemo(() => {
    const calc = (vht: "1" | "2") => {
      const p = side(vht, data.pitching);
      const S = (k: string) => p.reduce((s, r) => s + n(r[k]), 0);
      const pitches = S("pitch_cnt");
      const balls = p.reduce((s, r) => s + (derived.ballsBy.get(String(r.pitcher_acnt)) ?? 0), 0);
      const pa = p.reduce((s, r) => s + (derived.paBy.get(String(r.pitcher_acnt)) ?? 0), 0);
      const outs = p.reduce((s, r) => s + n(r.inning_pitched_cnt) * 3 + n(r.inning_pitched_div3), 0);
      const idx = derived.pIdx[vht];
      return {
        strike: pitches ? (pitches - balls) / pitches : null,
        fps: idx.fpTot ? idx.fpS / idx.fpTot : null,
        whiff: idx.swing ? idx.miss / idx.swing : null,
        ppa: pa ? pitches / pa : null,
        whip: outs ? (S("hits") + S("bb")) / (outs / 3) : null,
      };
    };
    return { a: calc("1"), h: calc("2") };
  }, [data.pitching, derived]);

  const rate3 = (v: number) => v.toFixed(3).replace(/^0/, "");
  const pct0 = (v: number) => `${Math.round(v * 100)}%`;
  const offRows: CmpItem[] = [
    { label: "上壘率", a: rates.a.obp, h: rates.h.obp, fmt: rate3 },
    { label: "長打率", a: rates.a.slg, h: rates.h.slg, fmt: rate3 },
    { label: "得點圈打擊率", a: rates.a.risp, h: rates.h.risp, fmt: rate3, subA: rates.a.rispTxt, subH: rates.h.rispTxt },
    { label: "得分效率", note: "得分÷上壘人次", a: rates.a.eff, h: rates.h.eff, fmt: pct0 },
    { label: "三振率", note: "越低越好", a: rates.a.kr, h: rates.h.kr, fmt: pct0, lowBetter: true },
  ];
  const pitRows: CmpItem[] = [
    { label: "好球率", a: pRates.a.strike, h: pRates.h.strike, fmt: pct0 },
    { label: "首球好球率", a: pRates.a.fps, h: pRates.h.fps, fmt: pct0 },
    { label: "揮空率", note: "揮空÷揮擊", a: pRates.a.whiff, h: pRates.h.whiff, fmt: pct0 },
    { label: "每打席用球", note: "越低越省", a: pRates.a.ppa, h: pRates.h.ppa, fmt: (v) => v.toFixed(1), lowBetter: true },
    { label: "WHIP", note: "每局被上壘", a: pRates.a.whip, h: pRates.h.whip, fmt: (v) => v.toFixed(2), lowBetter: true },
  ];

  // C3 投手用球（堆疊：好球=隊色、壞球=同隊 tint；好球=總−壞）
  const c3 = useMemo(() =>
    (["1", "2"] as const).flatMap((vht) =>
      side(vht, data.pitching).filter((r) => n(r.pitch_cnt) > 0).map((r) => {
        const total = n(r.pitch_cnt);
        const balls = Math.min(total, derived.ballsBy.get(String(r.pitcher_acnt)) ?? 0);
        return { name: String(r.pitcher_name ?? ""), strikes: total - balls, balls, code: vht === "1" ? ac : hc };
      })), [data.pitching, derived.ballsBy, ac, hc]);

  // 擊球落點（後端 spray：InPlay＋方向/距離；result 已由 _batted_result 分類）依打者隊分側
  const [sprayTeam, setSprayTeam] = useState<"1" | "2">("1");
  const sprayBySide = useMemo(() => {
    const sideOf = new Map(data.batting.map((r) => [String(r.hitter_acnt), String(r.visiting_home_type)]));
    const out: Record<"1" | "2", { dir: number; dist: number; ev: number | null; la: number | null; result: string }[]> = { "1": [], "2": [] };
    for (const p of data.spray ?? []) {
      const s = sideOf.get(String(p.hitter_acnt));
      if (s === "1" || s === "2") out[s].push(p);
    }
    return out;
  }, [data.spray, data.batting]);

  const axis = chartAxis(ct, 10);
  const hasUmpire = !!data.detail?.head_umpire;
  const tabBtn = (v: "away" | "home" | "ana" | "umpire", label: React.ReactNode) => (
    <button key={v} onClick={() => setTab(v)}
      className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-sm transition ${tab === v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}>
      {label}
    </button>
  );

  return (
    <div>
      <div className="mb-3 inline-flex flex-wrap gap-1 rounded-lg bg-surface-2 p-1">
        {tabBtn("away", <><TeamLogo code={ac} name={awayName} size={16} decorative />{teamShort(ac)}</>)}
        {tabBtn("home", <><TeamLogo code={hc} name={homeName} size={16} decorative />{teamShort(hc)}</>)}
        {tabBtn("ana", "分析")}
        {hasUmpire && tabBtn("umpire", "主審判決")}
      </div>

      {(tab === "away" || tab === "home") && (
        <div className="space-y-4">
          <BattingTable rows={side(tab === "away" ? "1" : "2", data.batting)} avgMap={data.batter_avg}
            posBy={derived.posBy} />
          <PitchingTable rows={side(tab === "away" ? "1" : "2", data.pitching)} decisions={data.decisions ?? {}}
            ballsBy={derived.ballsBy} paBy={derived.paBy} />
        </div>
      )}

      {tab === "ana" && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="進攻效率" note="單場小樣本・粗體＝較佳方">
              <div className="mb-2 px-1"><LegendRow awayName={awayName} homeName={homeName} ac={awayColor} hc={homeColor} /></div>
              <CompareRows items={offRows} ac={awayColor} hc={homeColor} />
            </ChartCard>

            <ChartCard title="投手效率" note="首球/揮空自逐球事件重建">
              <div className="mb-2 px-1"><LegendRow awayName={awayName} homeName={homeName} ac={awayColor} hc={homeColor} /></div>
              <CompareRows items={pitRows} ac={awayColor} hc={homeColor} />
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="投手用球" note="實色=好球（含界內）、淡色=壞球">
              <ResponsiveContainer width="100%" height={Math.max(120, 36 + c3.length * 28)}>
                <BarChart data={c3} layout="vertical" margin={{ top: 0, right: 28, bottom: 0, left: -4 }} barSize={13}>
                  <CartesianGrid strokeDasharray="3 3" stroke={ct.line} horizontal={false} />
                  <XAxis type="number" tick={axis.tick} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="name" width={62} tick={{ ...axis.tick, fill: ct.ink }} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{ fill: "transparent" }} contentStyle={chartTooltip(ct)}
                    formatter={(v: number, name: string) => [v, name === "strikes" ? "好球" : "壞球"]} />
                  <Bar dataKey="strikes" stackId="p" isAnimationActive={false} stroke={ct.surface} strokeWidth={1}>
                    {c3.map((r, i) => <Cell key={i} fill={teamColor(r.code)} />)}
                  </Bar>
                  <Bar dataKey="balls" stackId="p" radius={[0, 4, 4, 0]} isAnimationActive={false} stroke={ct.surface} strokeWidth={1}>
                    {c3.map((r, i) => <Cell key={i} fill={tint(teamColor(r.code))} />)}
                    <LabelList dataKey={(r: Record<string, unknown>) => Number(r.strikes) + Number(r.balls)} position="right" style={{ fill: ct.muted, fontSize: 10 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {data.has_tracking ? (
              <ChartCard title="擊球落點" note="InPlay 擊球・依結果著色">
                <div className="mb-2 flex gap-1 px-1">
                  {(["1", "2"] as const).map((s) => (
                    <button key={s} onClick={() => setSprayTeam(s)}
                      className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition ${
                        sprayTeam === s ? "bg-ink text-paper" : "bg-surface-2 text-muted hover:text-ink"}`}>
                      <TeamLogo code={s === "1" ? ac : hc} name={s === "1" ? awayName : homeName} size={13} decorative />
                      {teamShort(s === "1" ? ac : hc)}
                    </button>
                  ))}
                </div>
                {sprayBySide[sprayTeam].length > 0 ? (
                  <SprayChart points={sprayBySide[sprayTeam]} />
                ) : (
                  <div className="py-8 text-center text-xs text-faint">
                    本場尚無{sprayTeam === "1" ? "客隊" : "主隊"}擊球落點資料（TrackMan 發布可能延遲）。
                  </div>
                )}
              </ChartCard>
            ) : (
              <div className="rounded-xl border border-dashed border-line bg-surface-2/50 px-4 py-3 text-xs text-muted">
                本場未提供逐球追蹤資料（該球場未設置 TrackMan 設備），無擊球落點圖。
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "umpire" && (
        <div className="space-y-4">
          {umpLoading && <Skeleton className="h-40 rounded-xl" />}
          {/* 退化語意分類（blueprint §8.1）：載入失敗、無設備、尚未發布各給不同文案，
              一律不把缺資料呈現為零誤判／零影響。 */}
          {umpError && <ErrorState>載入主審判決分布失敗，請稍後再試。</ErrorState>}
          {!umpLoading && !umpError && umpCard && (
            <>
              {umpCard.pitches.length > 0 ? (
                <Card padding="" className="overflow-hidden">
                  <div className="border-b border-line px-4 py-3 bg-surface-2/40 flex flex-wrap items-center justify-between gap-3 text-sm">
                    <div>
                      <span className="font-bold text-ink">主審{" "}
                        <Link
                          href={`/people/umpire/${encodeURIComponent(data.detail?.head_umpire ?? "")}`}
                          className={ENTITY_LINK}
                        >
                          {data.detail?.head_umpire}
                        </Link>{" "}
                        判決分布
                      </span>
                      <span className="ml-3 text-[11px] text-faint">
                        中華職棒 {umpCard.season} 球季　編號 {data.game?.game_sno}
                      </span>
                    </div>
                    <div className="text-[11px] text-faint bg-surface border border-line rounded px-2 py-0.5">
                      推算、非官方
                    </div>
                  </div>

                  {/* 中性計數（非準確率、非評判）：好壞球判決球數分布 */}
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3 border-b border-line text-sm">
                    <span className="text-muted">好壞球判決{" "}
                      <b className="font-mono text-base tabular-nums text-ink">{umpCard.summary.called}</b> 球
                    </span>
                    <span className="flex items-center gap-1.5 text-muted">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-cpbl)" }} />
                      判好球 <b className="font-mono tabular-nums text-ink">{umpCard.summary.called_strikes}</b>
                    </span>
                    <span className="flex items-center gap-1.5 text-muted">
                      <span className="inline-block h-2.5 w-2.5 rounded-full border border-muted" />
                      判壞球 <b className="font-mono tabular-nums text-ink">{umpCard.summary.called_balls}</b>
                    </span>
                  </div>

                  <div className="p-4">
                    <div className="mb-2 text-xs font-semibold text-muted flex flex-col gap-0.5">
                      <span>判決位置分布</span>
                      <span className="font-normal text-faint text-[10px]">
                        每點為一次好壞球判決（捕手視角）；方框＝規則好球帶，僅作空間參考、未依打者身高調整。
                      </span>
                    </div>
                    <div className="flex justify-center">
                      <svg viewBox={`0 0 ${W} ${H}`} role="img"
                        aria-label={`主審單場好壞球判決位置分布：判好球 ${umpCard.summary.called_strikes} 球、判壞球 ${umpCard.summary.called_balls} 球`}
                        className="w-full max-w-[340px] rounded-lg border border-line/60 bg-paper">
                        <rect x={px(-umpCard.zone.half_width)} y={py(umpCard.zone.top)}
                          width={px(umpCard.zone.half_width) - px(-umpCard.zone.half_width)}
                          height={py(umpCard.zone.bot) - py(umpCard.zone.top)}
                          fill="none" strokeWidth="1.5" className="stroke-ink/50" />
                        {umpCard.pitches.map((p, i) => (
                          p.called_strike ? (
                            <circle key={i} cx={px(p.side)} cy={py(p.height)} r={3}
                              fill="var(--color-cpbl)" opacity={0.7}>
                              <title>{`${p.inning_seq ?? "?"}局 ${p.hitter_name ?? ""} vs ${p.pitcher_name ?? ""}　${p.ball_cnt}-${p.strike_cnt}　判好球`}</title>
                            </circle>
                          ) : (
                            <circle key={i} cx={px(p.side)} cy={py(p.height)} r={3}
                              fill="none" strokeWidth={1.2} className="stroke-muted" opacity={0.85}>
                              <title>{`${p.inning_seq ?? "?"}局 ${p.hitter_name ?? ""} vs ${p.pitcher_name ?? ""}　${p.ball_cnt}-${p.strike_cnt}　判壞球`}</title>
                            </circle>
                          )
                        ))}
                      </svg>
                    </div>
                  </div>
                </Card>
              ) : data.has_tracking ? (
                <EmptyState>本場逐球追蹤尚未包含好壞球判決資料（可能延遲發布）。</EmptyState>
              ) : (
                <EmptyState>本場無逐球追蹤資料，無主審判決分布（常見於未設置 TrackMan 的球場）。</EmptyState>
              )}
              <div className="text-[10px] text-faint leading-normal mt-2">
                * 註：主審好壞球判決分布為非官方自動化推算，為<b className="font-semibold">描述性</b>呈現，非評判、非排行。好球帶採固定規則寬度（約外邊 22.0 cm）、高度採 TrackMan 固定邊界，未依每位打者實際蹲姿／身高個體化調整，僅作散點的空間參考。
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
