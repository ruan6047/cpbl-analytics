"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ReportTeamStyle } from "@/components/report-team-style";
import { AbilityCard } from "@/components/ability-card";
import { FieldDiagram } from "@/components/field-diagram";
import { TraitsContent, type TraitsData } from "@/components/traits-content";
import { Card, ENTITY_LINK, PercentileBar, TeamBadge } from "@/components/ui";
import { SectionTitle } from "@/components/postmark";
import { reportField, reportFieldPlayer } from "@/lib/report-field";
import { REPORT_TABS, reportLink } from "@/lib/between-games";
import { gameLink } from "@/lib/postseason-journey";
import { teamColor, teamName3 } from "@/lib/teams";
import type { Counts, Period, Report, ReportPlayer, ReportTab, ReportView } from "@/lib/report-types";

const periods = [{ key: "series", label: "本系列" }, { key: "regular", label: "本季例行賽" }, { key: "opponent_regular", label: "本季對該隊" }] as const;
const labels: Record<string, string> = { g: "登場", pa: "PA", ab: "AB", h: "安打", hr: "全壘打", xbh: "長打", bb: "保送", so: "三振", ip: "局數", pitch_cnt: "球數", era: "ERA", whip: "WHIP", ops: "OPS", avg: "AVG", slg: "SLG", obp: "OBP", k_pct: "K%", bb_pct: "BB%", r: "得分", rbi: "打點", sb: "盜壘", hbp: "觸身球", er: "責失", bf: "面對打者" };
const d = (v: number | string | null | undefined, key?: string) => v == null ? "—" : typeof v === "number" && ["ops", "avg", "slg", "obp"].includes(key ?? "") ? v.toFixed(3).replace(/^0/, "") : typeof v === "number" && ["era", "whip"].includes(key ?? "") ? v.toFixed(2) : String(v);
const hand = (value: string | null, suffix: "打" | "投") => value ? `${value.replace(new RegExp(`${suffix}$`), "")}${suffix}` : `${suffix}側未取得`;
const officialValue = (value: number | string | null | undefined, key: string) => typeof value === "number" ? ["kp", "bbp", "hardhitp"].includes(key) ? `${(value * 100).toFixed(1)}%` : value.toFixed(3).replace(/^0/, "") : d(value);
const name = (p: ReportPlayer) => p.name ?? p.player_id;
function PlayerButton({ player, open }: { player: ReportPlayer; open: (p: ReportPlayer) => void }) {
  return <button type="button" onClick={() => open(player)} className={`${ENTITY_LINK} min-h-11 text-left font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent`} aria-haspopup="dialog">{name(player)}</button>;
}
function CountLine({ counts, role, full = false }: { counts: Counts; role: string; full?: boolean }) {
  const keys = role === "pitching"
    ? full ? ["ip", "era", "whip", "h", "hr", "so", "bb", "er", "pitch_cnt"] : ["ip", "so", "bb", "pitch_cnt"]
    : full ? ["pa", "ab", "h", "hr", "r", "rbi", "bb", "so", "sb", "avg", "obp", "slg", "ops"] : ["pa", "h", "hr", "ops"];
  return <dl className={`grid gap-x-4 gap-y-3 ${full ? "grid-cols-3 sm:grid-cols-4" : "grid-cols-2 text-xs"}`}>{keys.map(k => <div key={k}><dt className="text-xs text-muted">{labels[k]}</dt><dd className={`font-mono tabular-nums text-ink ${full ? "mt-1 text-lg font-bold" : "font-semibold"}`}>{d(counts[k], k)}</dd></div>)}</dl>;
}
function PeriodRow({ period, role, full = false }: { period: Period; role: string; full?: boolean }) {
  return <div className="space-y-3"><CountLine counts={period.counts} role={role} full={full} /><p className="text-xs text-muted">樣本 {d(period.sample.pa)} PA{role === "batting" ? ` · ${d(period.sample.ab)} AB` : ""}。</p><p className="text-xs text-muted">{period.status === "not_appeared" ? "完整登錄名單及使用紀錄：未登場" : period.status === "missing" ? "本站未取得" : period.coverage_status !== "complete" ? "覆蓋未完整，僅列已取得場次" : `${period.covered_game_keys.length} 場有出賽資料`}</p></div>;
}
function AbilityPanel({ player }: { player: ReportPlayer }) {
  const axes = player.ability.axes ?? [];
  const available = player.ability.available && axes.length > 0;
  const complete = available && axes.every(a => a.pr != null && Number.isFinite(a.pr));
  return <section aria-label="能力特色" className="space-y-4">
    <h3 className="text-sm font-bold">能力特色 · 本季一軍</h3>
    {available ? <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {complete ? <AbilityCard card={player.ability} title="本季能力" color={teamColor(player.team_code)} /> : <p className="text-sm text-muted">能力軸未完整，僅列已取得軸</p>}
      <div className="min-w-0 space-y-3 self-center">{axes.map(a => a.pr == null ? <p key={a.key} className="text-xs text-muted">{a.label} —</p> : <div key={a.key}><PercentileBar name={a.label} value={a.grade ?? "—"} pr={a.pr} /><p className="mt-1 text-right font-mono text-xs text-muted">PR {d(a.pr)}</p></div>)}</div>
    </div> : <p className="py-4 text-sm text-muted">本站未取得可核實的本季能力</p>}
    {player.official_pr && <div className="space-y-2"><h3 className="text-sm font-semibold">官方 PR · 本季一軍</h3>{[["kp", "K%"], ["bbp", "BB%"], ["woba", "wOBA"], ["iso", "ISO"], ["hardhitp", "強擊球率"]].map(([k, label]) => typeof player.official_pr?.[`${k}_pr`] === "number" ? <PercentileBar key={k} name={label} value={officialValue(player.official_pr[k], k)} pr={Number(player.official_pr[`${k}_pr`])} /> : null)}<p className="text-xs text-muted">樣本 {d(player.official_pr.pa)} PA；PR 越高越有利，沿官方方向。</p></div>}
  </section>;
}
type PlayerPeriod = typeof periods[number]["key"] | "usage";
export function ReportPlayerPeriod({ player, period, hasTarget = true }: { player: ReportPlayer; period: PlayerPeriod; hasTarget?: boolean }) {
  if (period !== "usage") return <PeriodRow period={player.periods[period]} role={player.role} full />;
  const usage = player.pitching_usage;
  if (!usage) return <p className="text-sm text-muted">本站未取得可靠使用紀錄</p>;
  return <>
    {usage.cutoff_label && <p className="mb-2 text-xs text-muted">近期使用 · {String(usage.cutoff_label)}</p>}
    <p className="text-sm text-muted">合計 {String(usage.ip ?? "—")} 局 · {String(usage.pitch_total ?? "—")} 球 · 連續 {String(usage.consecutive_days ?? "—")} 天{hasTarget && <> · 距該場 {String(usage.days_to_next ?? "—")} 天</>}</p>
    <ul className="mt-2 space-y-1 text-xs text-muted">{((usage.appearances ?? []) as { game_key: string; date: string; role_type: string; outs: number | null; pitch_cnt: number | null }[]).map(a => <li key={a.game_key}>{a.date} · {a.role_type ?? "角色未取得"} · {a.outs == null ? "—" : `${Math.floor(a.outs / 3)}.${a.outs % 3}`} 局 · {d(a.pitch_cnt)} 球</li>)}</ul>
  </>;
}
export function ReportPlayerDialog({ player, close, season, hasTarget = true }: { player: ReportPlayer; close: () => void; season: number; hasTarget?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [period, setPeriod] = useState<PlayerPeriod>("series");
  const tabs = player.role === "pitching" ? [...periods, { key: "usage" as const, label: "逐場使用" }] : periods;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    dialog.showModal();
    dialog.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
    return () => { dialog.close(); previous?.focus({ preventScroll: true }); };
  }, []);
  return <dialog ref={ref} onCancel={e => { e.preventDefault(); close(); }} onClick={e => { if (e.target === e.currentTarget) close(); }} aria-labelledby="report-player-title" className="m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-3xl overflow-y-auto rounded-md bg-paper p-0 text-ink backdrop:bg-black/40">
    <div className="p-5 sm:p-6">
      <header className="grid min-w-0 gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div><h2 id="report-player-title" tabIndex={-1} className="text-2xl font-bold">{name(player)}</h2><p className="mt-1 text-sm text-muted">{teamName3(player.team_code)} · {hand(player.bats, "打")} · {hand(player.throws, "投")}</p></div>
        <div className="min-w-0"><p className="text-xs text-muted">守位：{player.role === "pitching" ? "投手" : player.fielding.map(f => `${f.pos} ${d(f.g)} 場`).join("／") || "本站未取得"}</p><TraitsContent data={player.traits as TraitsData | null} role={player.role} /></div>
      </header>
      <section className="mt-5 border-y border-line py-5"><AbilityPanel player={player} /></section>
      <div className="mt-5 flex flex-wrap gap-1" role="group" aria-label="選手資料期間">{tabs.map(t => <button key={t.key} type="button" aria-pressed={period === t.key} onClick={() => setPeriod(t.key)} className={`min-h-11 rounded px-3 text-xs ${period === t.key ? "bg-ink text-paper" : "bg-band text-ink"}`}>{t.label}</button>)}</div>
      <section className="py-4" aria-label={tabs.find(t => t.key === period)?.label}><ReportPlayerPeriod player={player} period={period} hasTarget={hasTarget} /></section>
      {hasTarget && player.role === "batting" && player.vs_starter.pitcher_id && <section className="border-t border-line py-4"><h3 className="mb-2 font-bold">本季對該場公告先發</h3>{player.vs_starter.counts ? <><CountLine counts={player.vs_starter.counts} role="batting" /><p className="mt-1 text-xs text-muted">{d(player.vs_starter.sample?.pa)} PA · {d(player.vs_starter.sample?.ab)} AB；覆蓋未核實，更新 {player.vs_starter.updated_at?.slice(0, 10) ?? "時點未取得"}</p></> : <p className="text-sm text-muted">本站未取得投打配對</p>}</section>}
      {player.role === "pitching" && <section className="mt-5"><h3 className="font-bold">本季左右打分項</h3>{player.splits.length ? <ul className="mt-2 space-y-2 text-sm text-muted">{player.splits.map(s => <li key={String(s.item_index)}>{String(s.item_name ?? s.item_index)} · {d(s.plate_appearances)} PA · {d(s.hits)} H · {d(s.home_runs)} HR · {d(s.bb)} BB · {d(s.so)} SO</li>)}</ul> : <p className="mt-2 text-sm text-muted">本站未取得可靠左右分項</p>}</section>}
      <p className="mt-5 text-xs text-muted">能力、官方 PR 與特性固定 {season} 年一軍例行賽，不隨期間重算。</p><Link className={`${ENTITY_LINK} mt-4 inline-block min-h-11`} href={`/players/${player.player_id}?year=${season}`}>完整球員頁</Link>
    </div>
  </dialog>;
}
function TeamPlayers({ report, team, role, open, hasTarget }: { report: Report; team: string; role: "pitching" | "batting"; open: (p: ReportPlayer) => void; hasTarget: boolean }) {
  const players = (report.players ?? []).filter(p => p.team_code === team && p.role === role);
  const [period, setPeriod] = useState<"series" | "regular" | "opponent_regular">("series");
  const starter = report.next_game && [report.next_game.away_starter, report.next_game.home_starter].find(s => s.team_code === team);
  const nextStarter = hasTarget && starter?.status === "announced" ? players.find(p => p.player_id === starter.acnt) : null;
  const field = reportField(report, team);
  const others = players.filter(p => p !== nextStarter);
  return <section className="min-w-0"><SectionTitle><TeamBadge code={team} name={teamName3(team)} /> {role === "pitching" ? "投手" : "野手"}</SectionTitle>
    {!report.population?.find(p => p.team_code === team)?.complete && <p className="mb-4 text-sm text-muted">正式登錄名單尚未核實；下列為已取得紀錄，未列出不代表未登板或未出賽。</p>}
    {role === "pitching" && hasTarget && <Card className="mb-5"><h3 className="mb-2 font-bold">該場公告先發</h3>{nextStarter ? <><PlayerButton player={nextStarter} open={open} /><AbilityPanel player={nextStarter} /><div className="mt-4 border-t border-line pt-4"><PeriodRow period={nextStarter.periods[period]} role={role} full /></div></> : <p className="py-4 text-sm text-muted">本站尚未取得可靠先發公告</p>}</Card>}
    {role === "batting" && <div className="mb-5"><FieldDiagram cells={field.cells} designatedHitter={field.dh} caption={field.announced ? "該場公告先發" : "本季主力守位 · 候選"} onSelect={cell => { const pid = cell.href?.replace("#report-player-", ""); const p = pid ? reportFieldPlayer(report, team, pid) : null; if (p) open(p); }} /><p className="mt-2 text-xs text-muted">{field.announced ? "已核實賽前公告版本；棒次與守位依公告" : "依已取得本季守位場數列主力候選，非公告先發；並列保留"}。DH {field.dh?.main ?? "本站未取得"}。</p></div>}
    <div className="mb-4 flex flex-wrap gap-1" role="group" aria-label={`${teamName3(team)}統計期間`}>{periods.map(({ key, label }) => <button key={key} type="button" aria-pressed={period === key} onClick={() => setPeriod(key)} className={`min-h-11 rounded px-3 text-xs ${period === key ? "bg-ink text-paper" : "bg-band text-ink"}`}>{label}</button>)}</div>
    <h3 className="mb-3 text-sm font-bold">{role === "pitching" ? "其他投手 · 含後援" : "野手個人卡"}</h3>
    <div className="grid gap-3 sm:grid-cols-2">{others.map(p => <Card key={p.player_id} className="min-w-0"><PlayerButton player={p} open={open} /><p className="mb-3 text-xs text-muted">{role === "pitching" ? p.pitching_usage?.started ? "近期曾先發" : "投手 · 角色依使用紀錄" : p.fielding.map(f => f.pos).join("／") || "守位未取得"}</p><CountLine counts={p.periods[period].counts} role={role} /><p className="mt-3 text-xs text-muted">{p.periods[period].status === "missing" ? "本站未取得此期間紀錄" : p.periods[period].coverage_status !== "complete" ? "僅列已取得場次" : "期間資料已取得"}</p>{role === "pitching" && <p className="mt-2 text-xs text-muted">連續 {String(p.pitching_usage?.consecutive_days ?? "—")} 天{hasTarget && <> · 距該場 {String(p.pitching_usage?.days_to_next ?? "—")} 天</>}</p>}<p className="mt-2 text-xs text-accent">點選姓名看能力與完整指標 →</p></Card>)}</div>
    {!players.length && <p className="py-6 text-sm text-muted">本站尚未取得此隊{role === "pitching" ? "投手" : "野手"}背景</p>}
  </section>;
}
function WatchLine({ point, player }: { point: NonNullable<Report["watch_points"]>[number]; player: ReportPlayer }) {
  const background = point.origin === "last_game" ? player.last_game.counts : point.origin === "series" ? player.periods.series.counts : player.vs_starter.counts ?? {};
  const counts = {...background, ...point.count_line};
  const allowed = player.role === "pitching" ? ["ip", "outs", "er", "h", "so", "bb"] : ["pa", "h", "hr", "xbh", "rbi", "bb"];
  const entries = Object.entries(counts).filter(([key, value]) => value != null && allowed.includes(key) && (key !== "outs" || counts.ip == null));
  return <p className="mt-2 text-sm text-ink"><span className="mr-2 text-xs text-muted">{point.origin === "last_game" ? "前場" : point.origin === "series" ? "本系列" : "本季對特定投手"}</span>{entries.map(([key, value]) => key === "outs" && typeof value === "number" && player.role === "pitching" ? `局數 ${Math.floor(value / 3)}.${value % 3}` : labels[key] ? `${labels[key]} ${d(value, key)}` : null).filter(Boolean).join(" · ") || "本站尚未取得完整表現指標"}</p>;
}
export default function ReportPage({ view, tab }: { view: ReportView; tab: ReportTab }) {
  const { report, journey, updating } = view;
  const [selected, select] = useState<ReportPlayer | null>(null);
  const original = gameLink(report.kind_code, report.game_sno, report.season);
  if (report.status !== "ok" || !report.game) return <Card><h1 className="text-xl font-bold">{report.status === "not_final" ? "完賽後提供場間報告" : "本站尚未取得這場季後賽"}</h1><Link className="mt-4 inline-block min-h-11 text-accent underline" href={original}>返回原賽況</Link></Card>;
  const historyGame = report.game;
  const comparison = report.comparison;
  const displayReport: Report = comparison ? {...report, ...comparison, game: historyGame, next_game: comparison.game} : report;
  const game = comparison?.game ?? historyGame;
  const teamCodes = [game.away_team_code, game.home_team_code];
  const series = journey?.series[comparison?.kind_code ?? report.kind_code];
  const hasTarget = !!comparison || !!journey?.next;
  const pendingTransition = !!journey?.next && journey.next.kind !== report.kind_code && !comparison;
  return <div className="mx-auto max-w-6xl space-y-6 pb-10">
    <header><Link href={original} className="inline-block min-h-11 text-sm text-accent underline">返回原賽況</Link><h1 className="text-3xl font-bold tracking-tight">{teamName3(game.away_team_code)}對{teamName3(game.home_team_code)} · 場間報告</h1><p className="mt-2 text-sm text-muted">{hasTarget && "開賽前背景 · "}{historyGame.game_date} 完賽後 · {report.anchor?.cutoff_label}{comparison && <> · {teamName3(historyGame.away_team_code)}對{teamName3(historyGame.home_team_code)}回顧</>}</p></header>
    <nav aria-label="場間報告頁籤" className="flex gap-1 rounded-t-md bg-band p-1">{REPORT_TABS.map(t => <Link key={t.value} href={reportLink(report.game_sno, report.kind_code, report.season, t.value)} aria-current={tab === t.value ? "page" : undefined} className={`min-h-11 flex-1 px-4 py-3 text-center text-sm ${tab === t.value ? "bg-paper font-bold text-ink" : "text-muted hover:text-ink"}`}>{t.label}</Link>)}</nav>
    {comparison && comparison.series_game_keys.length === 0 && <p className="text-sm text-muted">{comparison.kind_code === "C" ? "台灣大賽" : "季後挑戰賽"}本系列尚無完賽資料（截至原完賽場）；近期使用另截至原完賽場，個人缺值仍未取得。</p>}
    {pendingTransition && <p role="status" className="text-sm text-muted">{journey?.next?.awayLabel}對{journey?.next?.homeLabel}的本站正式場次資料尚未取得；下列保留原系列回顧，不以公告G1猜正式場號。</p>}
    {updating && <p role="status" className="text-sm text-muted">資料更新中，背景稍後重新載入。</p>}
    {tab === "overview" ? <>
      <section><SectionTitle>{journey?.next ? `開賽前背景：${journey.next.awayLabel}對${journey.next.homeLabel}` : series?.tally.decided ? "系列已分勝負" : "下一場安排待核實"}</SectionTitle>
        {journey?.next && <p className="mb-4 text-sm text-muted">{journey.next.date} {journey.next.start ?? "時間未取得"} · {journey.next.venue ?? journey.next.venueNote}{report.next_game && <> · <Link className="text-accent underline" href={gameLink(report.next_game.kind_code, report.next_game.game_sno, report.season)}>查看該場賽況</Link></>}</p>}
        <div className="grid items-start gap-5 md:grid-cols-[minmax(0,1fr)_8rem_minmax(0,1fr)]">
          {teamCodes.map((team, index) => { const tally = series && [series.tally.a, series.tally.b].find(t => t.code === team); const style = displayReport.teams?.find(t => t.team === team); return <div key={team} className={`min-w-0 ${index === 0 ? "md:col-start-1 md:row-start-1" : "md:col-start-3 md:row-start-1"}`}><Card><p className="mb-2 text-xs text-muted">{index === 0 ? "客隊" : "主隊"}</p><TeamBadge code={team} name={teamName3(team)} /><p className="mt-4 text-xl font-bold">{tally ? tally.remaining === 0 ? series?.tally.winner === team ? "已晉級／封王" : "系列結束" : `還差 ${tally.remaining} 勝` : "進度待核實"}</p><p className="mt-1 text-xs text-muted">{tally ? `實際 ${tally.gameWins} 勝${tally.ruleWins ? `＋規則 ${tally.ruleWins} 勝` : ""}` : "本站未取得"}</p><h3 className="mt-6 border-t border-line pt-4 text-sm font-bold">本季球風</h3>{style ? <ReportTeamStyle style={style} /> : <p className="py-8 text-sm text-muted">本站未取得完整本季球風</p>}</Card></div>; })}
          <div className="order-first py-3 text-center md:order-none md:col-start-2 md:row-start-1 md:pt-16" aria-label="客隊對主隊系列勝場">
            <p className="text-xs font-semibold text-muted">系列勝場</p><p className="mt-2 font-mono text-3xl font-bold tabular-nums">{teamCodes.map(team => series ? [series.tally.a, series.tally.b].find(t => t.code === team)?.total ?? "—" : "—").join(" : ")}</p>
            <p className="mt-3 text-xs text-muted">{series ? `${series.winsNeeded} 勝${(comparison?.kind_code ?? report.kind_code) === "E" ? "晉級" : "封王"}` : "門檻待核實"}</p>{series && series.tally.a.ruleWins + series.tally.b.ruleWins > 0 && <p className="mt-1 text-xs text-muted">含公告規則讓勝</p>}
          </div>
        </div>
        <p className="mt-4 text-xs text-muted">本季一軍固定尺度 · <Link href={reportLink(report.game_sno, report.kind_code, report.season, "pitchers")} className="inline-flex min-h-11 items-center text-accent underline">比較投手</Link> · <Link href={reportLink(report.game_sno, report.kind_code, report.season, "fielders")} className="inline-flex min-h-11 items-center text-accent underline">比較野手</Link></p>
      </section>
      <section><SectionTitle>{hasTarget ? "該場觀察重點" : "本場觀察"}</SectionTitle><div className="grid gap-5 md:grid-cols-2">{teamCodes.map(team => <div key={team} className="min-w-0"><h3 className="mb-2 font-bold"><TeamBadge code={team} name={teamName3(team)} /></h3>{(displayReport.watch_points ?? []).filter(p => p.team_code === team).map(point => { const p = displayReport.players?.find(p => p.player_id === point.player_id && p.team_code === team); return p ? <div key={p.player_id} className="py-3"><PlayerButton player={p} open={select} /><WatchLine point={point} player={p} /></div> : null; })}{!(displayReport.watch_points ?? []).some(p => p.team_code === team) && <p className="py-4 text-sm text-muted">已取得樣本尚無可核實的觀察點</p>}</div>)}</div></section>

    </> : <div className="grid gap-8 md:grid-cols-2">{teamCodes.map(team => <TeamPlayers key={`${team}-${tab}`} report={displayReport} team={team} role={tab === "pitchers" ? "pitching" : "batting"} open={select} hasTarget={hasTarget} />)}</div>}
    <details className="border-t border-line pt-4 text-xs text-muted"><summary className="min-h-11 cursor-pointer">資料截至與來源</summary><p className="my-3">讀取 {report.read_at ?? "時點未取得"}；本季背景 {report.regular_coverage?.closed_before_X ? "A 季完成且早於前場" : "年度截至未核實"}。來源更新時點不代表官方更正發生時刻。</p>{journey && <p className="mb-2"><a className="underline" href={journey.announcement.source.url}>季後賽官方公告</a> · 取得 {journey.announcement.source.capturedAt}</p>}<ul className="space-y-2">{report.sources?.map((s,i) => <li key={`${s.source}-${i}`}><a className="underline" href={s.reference}>{s.source}</a> · 更新 {s.updated_at ?? s.fetched_at ?? "時點未取得"} · {s.coverage_status ?? "覆蓋未核實"}</li>)}</ul></details>
    {selected && <ReportPlayerDialog key={`${selected.team_code}-${selected.role}-${selected.player_id}`} player={selected} close={() => select(null)} season={report.season} hasTarget={hasTarget} />}
  </div>;
}
