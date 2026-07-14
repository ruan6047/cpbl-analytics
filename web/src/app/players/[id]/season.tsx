"use client";

// 本季成績卡 + 官方進階 PR（dataTab=season）；生涯成績 + 最佳單季 + 里程碑（dataTab=career）。
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Card, EmptyState, PercentileBar, Skeleton, StatAbbr, StatTile, TeamLogo, prColor } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { detail, type PlayerProfile, type StatRow } from "@/lib/client";
import { fmtIP } from "@/lib/format";
import { ADV, type CareerStats, type Role, f3, fmtAdv, numOf } from "./lib";
import { BestSeasonGrid } from "./parts";

type AdvPair = { batting: StatRow | null; pitching: StatRow | null } | null;

// 主指標 tile 融入官方 PR（UX-7A）：值下方加 prColor 迷你條＋PR 數字。
// PR 一律用官方 `_pr` 欄（F1 紅線：官方沒有的指標不自算、不顯示條）。
// label 為英文縮寫時走 StatAbbr 名詞解釋（換裝語彙）。
function PrTile({ label, value, accent, pr }: { label: string; value: string; accent?: boolean; pr?: number | null }) {
  return (
    <div className="rounded-lg bg-surface-2 px-2 py-3 text-center">
      <div className="text-[11px] text-muted"><StatAbbr abbr={label} /></div>
      <div className={`mt-1 font-mono text-2xl leading-none tabular-nums ${accent ? "text-accent" : "text-ink"}`}>{value}</div>
      {pr != null && (
        <div className="mx-auto mt-1.5 flex max-w-24 items-center gap-1" title={`官方百分位 PR ${pr}（0–100，越高越好）`}>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line/60">
            <div className="h-full rounded-full" style={{ width: `${pr}%`, background: prColor(pr) }} />
          </div>
          <span className="font-mono text-[10px] leading-none tabular-nums text-faint">{pr}</span>
        </div>
      )}
    </div>
  );
}

export function SeasonSection({ profile, s, role, seasonKind, setSeasonKind, advanced }: {
  profile: PlayerProfile;
  s: StatRow | null;
  role: Role;
  seasonKind: "A" | "D";
  setSeasonKind: (k: "A" | "D") => void;
  advanced: AdvPair;
}) {
  const advRow = advanced ? (role === "batting" ? advanced.batting : advanced.pitching) : null;
  // 官方 PR 查值（Math.round 對齊 PercentileBar 口徑）；供 tile 融入與去重共用。
  const advPr = (key: string): number | null => {
    const v = advRow ? numOf(advRow[key]) : null;
    return v === null ? null : Math.round(v);
  };
  const prRows = useMemo(() => {
    if (!advRow) return [];
    // tile 已融入的指標不在柱狀圖區重複列（打者 ba/obp/slg）；brl 為 brlp 的計數重複（F3 成對取一）。
    const fused = new Set(role === "batting" ? ["ba", "obp", "slg", "brl"] : ["brl"]);
    return ADV.filter((m) => !fused.has(m.key)).map((m) => {
      const val = numOf(advRow[m.key]), pr = numOf(advRow[m.pr]);
      return { name: role === "batting" ? m.bl : m.pl, def: m.def,
        value: val === null ? "—" : fmtAdv(val, m.kind), pr: pr === null ? null : Math.round(pr) };
    }).filter((d): d is { name: string; def: string; value: string; pr: number } => d.pr !== null);
  }, [advRow, role]);

  return (
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
            // [label, value, accent, 官方 PR（僅打者 rate 三圍有官方 _pr；其餘 null 不畫條）]
            const primary: [string, string, boolean, number | null][] = role === "batting"
              ? [["打擊率", f3(s.avg), true, advPr("ba_pr")], ["上壘率", f3(s.obp), false, advPr("obp_pr")],
                 ["長打率", f3(s.slg), false, advPr("slg_pr")],
                 ["OPS+", String(s.ops_plus ?? "—"), true, null], ["全壘打", String(s.hr ?? "—"), false, null],
                 ["打點", String(s.rbi ?? "—"), false, null]]
              : [["防禦率", numOf(s.era)?.toFixed(2) ?? "—", true, null], ["WHIP", numOf(s.whip)?.toFixed(2) ?? "—", false, null],
                 ["FIP", numOf(s.fip)?.toFixed(2) ?? "—", false, null], ["三振", String(s.so ?? "—"), true, null],
                 ["勝-敗", `${s.w ?? 0}-${s.l ?? 0}`, false, null], ["ERA+", String(s.era_plus ?? "—"), false, null]];
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
              <Card hoverable className="flex flex-1 flex-col gap-3">
                <div className="grid grid-cols-3 gap-2">
                  {primary.map(([l, v, a, pr]) => <PrTile key={l} label={l} value={v} accent={a} pr={pr} />)}
                </div>
                {/* 次要計數：輕量表列（label–值成對、細分隔線），取代同重量級的盒子牆降低視覺噪音 */}
                <div className="grid grid-cols-3 gap-x-5 gap-y-0.5 sm:grid-cols-4">
                  {secondary.filter(([, v]) => v !== "0").map(([l, v]) => (
                    <div key={l} className="flex items-baseline justify-between gap-2 border-b border-line/60 py-1 text-xs">
                      <span className="truncate text-muted"><StatAbbr abbr={l} /></span>
                      <span className="font-mono tabular-nums text-ink">{v}</span>
                    </div>
                  ))}
                </div>
              </Card>
            );
          })() : <Card className="flex-1"><EmptyState>本季無{role === "batting" ? "打擊" : "投球"}成績</EmptyState></Card>}
        </div>
        <div className="flex flex-col">
          <h2 className="mb-3 text-lg font-semibold text-ink">官方進階 · 百分位 PR
            {role === "batting" && prRows.length > 0 &&
              <span className="ml-2 align-middle text-xs font-normal text-faint">三圍 PR 已融入左側主指標</span>}
          </h2>
          <Card hoverable className="flex-1">
            {advanced === null ? (
              <div className="space-y-2.5 py-1" aria-hidden>
                {Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} className="h-3.5 w-full" />)}
              </div>
            ) : prRows.length === 0 ? (
              <EmptyState>無官方進階資料</EmptyState>
            ) : (
              <div className="space-y-1">
                {prRows.map((d) => <PercentileBar key={d.name} name={d.name} value={d.value} pr={d.pr} def={d.def} />)}
              </div>
            )}
          </Card>
        </div>
      </section>
  );
}

// 選手特性（livelog 推算）：P/PA 耗球/滾飛比/方向傾向/兩好球後——與聯盟均值對照
export function TraitsChips({ id, role }: { id: string; role: Role }) {
  const [t, setT] = useState<{
    traits: Record<string, number | string | null> | null;
    league: { p_pa: number | null; go_fo: number | null; two_strike_k_pct: number | null };
  } | null>(null);
  useEffect(() => {
    detail.traits(id, role).then(setT).catch(() => setT(null));
  }, [id, role]);
  const tr = t?.traits;
  const pa = Number(tr?.[role === "batting" ? "pa" : "bf"] ?? 0);
  if (!tr || pa < 50) return null;
  const lg = t!.league;
  const chip = (label: string, val: string, cmp?: string) => (
    <span key={label} className="inline-flex items-baseline gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-xs">
      <span className="text-muted">{label}</span>
      <span className="font-mono font-semibold tabular-nums text-ink">{val}</span>
      {cmp && <span className="text-[10px] text-faint">聯盟 {cmp}</span>}
    </span>
  );
  const items: React.ReactNode[] = [];
  if (tr.p_pa != null) items.push(chip("打席耗球 P/PA", String(tr.p_pa), lg.p_pa != null ? String(lg.p_pa) : undefined));
  if (tr.go != null && Number(tr.fo) > 0) {
    items.push(chip("滾飛比 GO/FO", (Number(tr.go) / Number(tr.fo)).toFixed(2), lg.go_fo != null ? String(lg.go_fo) : undefined));
  }
  if (tr.two_strike_k_pct != null) {
    items.push(chip(role === "batting" ? "兩好球後被三振" : "兩好球後解決率",
      `${tr.two_strike_k_pct}%`, lg.two_strike_k_pct != null ? `${lg.two_strike_k_pct}%` : undefined));
  }
  if (role === "batting") {
    const l = Number(tr.dir_left ?? 0), c = Number(tr.dir_center ?? 0), r = Number(tr.dir_right ?? 0);
    const tot = l + c + r;
    if (tot >= 30) items.push(chip("擊球方向 左/中/右", `${Math.round(100 * l / tot)}/${Math.round(100 * c / tot)}/${Math.round(100 * r / tot)}%`));
  }
  if (!items.length) return null;
  return (
    <div className="mt-4">
      <div className="mb-1.5 text-xs font-semibold text-muted">選手特性 <span className="font-normal text-faint">（逐打席推算・本季一軍）</span></div>
      <div className="flex flex-wrap gap-1.5">{items}</div>
    </div>
  );
}

// 生涯成績 + 最佳單季 + 里程碑 + 史上排名（依 role 分支；無生涯資料回 null）
export function CareerSummary({ careerStats, role }: { careerStats: CareerStats | null; role: Role }) {
  const hasManager = careerStats?.manager_stats && careerStats.manager_stats.length > 0;
  const hasCoachHistory = careerStats?.coach_history && careerStats.coach_history.length > 0;

  const coachSections = (
    <>
      {careerStats?.coach_ambiguous && (
        <div className="mb-6 rounded-lg bg-amber/10 p-3 text-xs text-amber border border-amber/20">
          ⚠️ 系統檢測到同名同姓球員，為保障資料精確度，已暫停自動關聯教練與總教練經歷。
        </div>
      )}
      {hasManager && (
        <section className="mb-6">
          <h2 className="mb-2.5 text-base font-semibold text-ink">總教練生涯執教戰績</h2>
          <DataTable
            columns={[
              { header: "執教時期", cell: (m) => <span className="font-medium">{m.era_name || "—"}</span>, nowrap: true },
              { header: "球隊", cell: (m) => m.team_code ? (
                <Link href={`/teams/${m.team_code}`} className="inline-flex items-center gap-1.5 hover:underline">
                  <TeamLogo code={m.team_code} size={16} />
                  {m.team_name || m.team_code}
                </Link>
              ) : "—", nowrap: true },
              { header: "年度", cell: (m) => m.from_year === m.to_year ? String(m.from_year) : `${m.from_year}–${m.to_year}`, nowrap: true, className: "text-muted" },
              { header: "出賽", cell: (m) => String(m.g ?? "—"), className: "font-mono" },
              { header: "勝-和-敗", cell: (m) => `${m.w ?? 0}-${m.ties ?? 0}-${m.l ?? 0}`, className: "font-mono" },
              { header: "勝率", cell: (m) => m.win_pct == null ? "—" : m.win_pct.toFixed(3).replace(/^0\./, "."), className: "font-mono text-accent font-semibold" },
              { header: "季後賽", cell: (m) => m.postseason || "—", className: "text-muted" },
              { header: "總冠軍", cell: (m) => m.championships ? <span className="inline-flex items-center gap-0.5 text-up font-bold">🏆 {m.championships}</span> : "—" },
            ] satisfies Column<NonNullable<CareerStats["manager_stats"]>[number]>[]}
            rows={careerStats.manager_stats || []}
            rowKey={(m, i) => `${m.team_code}-${m.from_year}-${i}`}
            dense
          />
        </section>
      )}
      {hasCoachHistory && (
        <section className="mb-6">
          <h2 className="mb-2.5 text-base font-semibold text-ink">生涯歷程</h2>
          <DataTable
            columns={[
              {
                header: "期間",
                cell: (r) => {
                  if (r.from_year && r.to_year) {
                    return r.from_year === r.to_year ? String(r.from_year) : `${r.from_year}–${r.to_year}`;
                  }
                  if (r.from_year) return `${r.from_year}–`;
                  return "—";
                },
                align: "right",
                nowrap: true,
              },
              {
                header: "類別",
                cell: (r) => {
                  const labels: Record<string, string> = {
                    player: "球員",
                    coach: "教練",
                    amateur: "業餘",
                    other: "行政",
                  };
                  return labels[r.phase] ?? r.phase;
                },
                nowrap: true,
              },
              { header: "聯盟/層級", cell: (r) => r.league ?? "—", nowrap: true },
              {
                header: "球隊/單位",
                cell: (r) => (
                  <span className="flex items-center gap-1.5 font-sans">
                    {r.team_code ? (
                      <Link href={`/teams/${r.team_code}`} className="inline-flex items-center gap-1.5 hover:underline">
                        <TeamLogo code={r.team_code} size={16} />
                        {r.team_raw}
                      </Link>
                    ) : (
                      r.team_raw
                    )}
                  </span>
                ),
                nowrap: true,
              },
              { header: "職務/身分", cell: (r) => r.pos, nowrap: true, className: "font-sans text-ink" },
            ] satisfies Column<NonNullable<CareerStats["coach_history"]>[number]>[]}
            rows={careerStats.coach_history || []}
            rowKey={(r, i) => `${r.from_year}-${r.to_year}-${r.team_raw}-${i}`}
            dense
          />
        </section>
      )}
    </>
  );

  if (role === "pitching" && careerStats?.pitching) {
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
        {coachSections}
      </>
    );
  }

  if (role === "batting" && careerStats?.batting) {
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
        {coachSections}
      </>
    );
  }

  if (hasManager || hasCoachHistory || careerStats?.coach_ambiguous) {
    return coachSections;
  }

  return null;
}
