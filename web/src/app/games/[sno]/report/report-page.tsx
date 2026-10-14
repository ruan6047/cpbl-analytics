"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ReportTeamStyle } from "@/components/report-team-style";
import { AbilityCard } from "@/components/ability-card";
import { FieldDiagram } from "@/components/field-diagram";
import { TraitsContent, type TraitsData } from "@/components/traits-content";
import { Card, ENTITY_LINK, PercentileBar, StatAbbr, TeamBadge } from "@/components/ui";
import { SectionTitle } from "@/components/postmark";
import { reportField, reportFieldPlayer } from "@/lib/report-field";
import { REPORT_TABS, previewLink, reportLink } from "@/lib/between-games";
import { gameLink } from "@/lib/postseason-journey";
import { REPORT_NAMES, monthDay, nextGameName, postseasonGameName, taipeiMinute } from "@/lib/postseason-game-name";
import { teamColor, teamName3 } from "@/lib/teams";
import type { Counts, Period, Report, ReportKind, ReportPlayer, ReportTab, ReportView } from "@/lib/report-types";

const periods = [{ key: "series", label: "本系列" }, { key: "regular", label: "本季例行賽" }, { key: "opponent_regular", label: "本季對該隊" }] as const;
const labels: Record<string, string> = { g: "登場", pa: "PA", ab: "AB", h: "安打", hr: "全壘打", xbh: "長打", bb: "保送", so: "三振", ip: "局數", pitch_cnt: "球數", era: "ERA", whip: "WHIP", ops: "OPS", avg: "AVG", slg: "SLG", obp: "OBP", k_pct: "K%", bb_pct: "BB%", r: "得分", rbi: "打點", sb: "盜壘", hbp: "觸身球", er: "自責分", bf: "面對打者" };
// N07（UI_UX_SYSTEM §3.4）：縮寫與記法首次出現時白話解釋；METRIC_DESCRIPTIONS 已有的（OPS／ERA／WHIP／AVG／OBP／SLG）沿用。
const GLOSS: Record<string, string> = {
  PA: "打席數：打者上場打擊的次數（含保送、觸身球）。",
  AB: "打數：打席扣掉保送、觸身球與犧牲打。",
  "K%": "三振率：三振 ÷ 打席。",
  "BB%": "保送率：四壞保送 ÷ 打席。",
  局數: "局數記法：小數點後是出局數，2.1 代表 2⅓ 局。",
};
const Term = ({ label }: { label: string }) => GLOSS[label] || ["OPS", "ERA", "WHIP", "AVG", "OBP", "SLG"].includes(label) ? <StatAbbr abbr={label} customDesc={GLOSS[label]} /> : <>{label}</>;
const d = (v: number | string | null | undefined, key?: string) => v == null ? "—" : typeof v === "number" && ["ops", "avg", "slg", "obp"].includes(key ?? "") ? v.toFixed(3).replace(/^0/, "") : typeof v === "number" && ["era", "whip"].includes(key ?? "") ? v.toFixed(2) : String(v);
const hand = (value: string | null, suffix: "打" | "投") => value ? `${value.replace(new RegExp(`${suffix}$`), "")}${suffix}` : `${suffix}側未取得`;
const officialValue = (value: number | string | null | undefined, key: string) => typeof value === "number" ? ["kp", "bbp", "hardhitp"].includes(key) ? `${(value * 100).toFixed(1)}%` : value.toFixed(3).replace(/^0/, "") : d(value);
const name = (p: ReportPlayer) => p.name ?? p.player_id;
function PlayerButton({ player, open }: { player: ReportPlayer; open: (p: ReportPlayer) => void }) {
  return <button type="button" onClick={() => open(player)} className={`${ENTITY_LINK} min-h-11 text-left font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent`} aria-haspopup="dialog">{name(player)}</button>;
}
/** `explain`：該區第一次出現時為縮寫加白話提示（N07）；其餘卡片不重複加底線。 */
function CountLine({ counts, role, full = false, explain = false }: { counts: Counts; role: string; full?: boolean; explain?: boolean }) {
  const keys = role === "pitching"
    ? full ? ["ip", "era", "whip", "h", "hr", "so", "bb", "er", "pitch_cnt"] : ["ip", "so", "bb", "pitch_cnt"]
    : full ? ["pa", "ab", "h", "hr", "r", "rbi", "bb", "so", "sb", "avg", "obp", "slg", "ops"] : ["pa", "h", "hr", "ops"];
  return <dl className={`grid gap-x-4 gap-y-3 ${full ? "grid-cols-3 sm:grid-cols-4" : "grid-cols-2 text-xs"}`}>{keys.map(k => <div key={k}><dt className="text-xs text-muted">{explain ? <Term label={labels[k]} /> : labels[k]}</dt><dd className={`font-mono tabular-nums text-ink ${full ? "mt-1 text-lg font-bold" : "font-semibold"}`}>{d(counts[k], k)}</dd></div>)}</dl>;
}
function PeriodRow({ period, role, full = false }: { period: Period; role: string; full?: boolean }) {
  return <div className="space-y-3"><CountLine counts={period.counts} role={role} full={full} explain={full} /><p className="text-xs text-muted">樣本 {d(period.sample.pa)} PA{role === "batting" ? ` · ${d(period.sample.ab)} AB` : ""}。</p><p className="text-xs text-muted">{period.status === "not_appeared" ? "完整登錄名單及使用紀錄：未登場" : period.status === "missing" ? "本站未取得" : period.coverage_status !== "complete" ? "覆蓋未完整，僅列已取得場次" : `${period.covered_game_count ?? period.covered_game_keys?.length} 場有出賽資料`}</p></div>;
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
/** `usageCutoff`：頁面以季後場次名組好的截至說明（「截至季後挑戰賽 G4 完賽」）；未給時沿後端原字串。 */
export function ReportPlayerPeriod({ player, period, hasTarget = true, usageCutoff = null }: { player: ReportPlayer; period: PlayerPeriod; hasTarget?: boolean; usageCutoff?: string | null }) {
  if (period !== "usage") return <PeriodRow period={player.periods[period]} role={player.role} full />;
  const usage = player.pitching_usage;
  if (!usage) return <p className="text-sm text-muted">本站未取得可靠使用紀錄</p>;
  return <>
    {(usageCutoff ?? usage.cutoff_label) && <p className="mb-2 text-xs text-muted">近期使用 · {usageCutoff ?? String(usage.cutoff_label)}</p>}
    <p className="text-sm text-muted">合計 {String(usage.ip ?? "—")} 局 · {String(usage.pitch_total ?? "—")} 球 · 連續出賽 {String(usage.consecutive_days ?? "—")} 天{hasTarget && <> · 距下一場 {String(usage.days_to_next ?? "—")} 天</>}</p>
    <ul className="mt-2 space-y-1 text-xs text-muted">{((usage.appearances ?? []) as { game_key: string; date: string; role_type: string; outs: number | null; pitch_cnt: number | null }[]).map(a => <li key={a.game_key}>{a.date} · {a.role_type ?? "角色未取得"} · {a.outs == null ? "—" : `${Math.floor(a.outs / 3)}.${a.outs % 3}`} 局 · {d(a.pitch_cnt)} 球</li>)}</ul>
  </>;
}
export function ReportPlayerDialog({ player, close, season, hasTarget = true, usageCutoff = null }: { player: ReportPlayer; close: () => void; season: number; hasTarget?: boolean; usageCutoff?: string | null }) {
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
      <section className="py-4" aria-label={tabs.find(t => t.key === period)?.label}><ReportPlayerPeriod player={player} period={period} hasTarget={hasTarget} usageCutoff={usageCutoff} /></section>
      {hasTarget && player.role === "batting" && player.vs_starter.pitcher_id && <section className="border-t border-line py-4"><h3 className="mb-2 font-bold">本季對該場公告先發</h3>{player.vs_starter.counts ? <><CountLine counts={player.vs_starter.counts} role="batting" /><p className="mt-1 text-xs text-muted">{d(player.vs_starter.sample?.pa)} PA · {d(player.vs_starter.sample?.ab)} AB；覆蓋未核實，更新 {player.vs_starter.updated_at?.slice(0, 10) ?? "時點未取得"}</p></> : <p className="text-sm text-muted">本站未取得投打配對</p>}</section>}
      {player.role === "pitching" && <section className="mt-5"><h3 className="font-bold">本季左右打分項</h3>{player.splits.length ? <ul className="mt-2 space-y-2 text-sm text-muted">{player.splits.map(s => <li key={String(s.item_index)}>{String(s.item_name ?? s.item_index)} · {d(s.plate_appearances)} PA · {d(s.hits)} H · {d(s.home_runs)} HR · {d(s.bb)} BB · {d(s.so)} SO</li>)}</ul> : <p className="mt-2 text-sm text-muted">本站未取得可靠左右分項</p>}</section>}
      <p className="mt-5 text-xs text-muted">能力、官方 PR 與特性固定 {season} 年一軍例行賽，不隨期間重算。</p><Link className={`${ENTITY_LINK} mt-4 inline-block min-h-11`} href={`/players/${player.player_id}?year=${season}`}>完整球員頁</Link>
    </div>
  </dialog>;
}
/** `seriesNote`：系列還沒開打時的說明（N02）；有值時預設期間改「本季例行賽」，不讓整頁都是「本站未取得」。 */
function TeamPlayers({ report, team, role, open, hasTarget, seriesNote = null }: { report: Report; team: string; role: "pitching" | "batting"; open: (p: ReportPlayer) => void; hasTarget: boolean; seriesNote?: string | null }) {
  // N06：野手頁不列守位只有投手的人（打擊紀錄屬投手本人，投手頁已列）。
  const players = (report.players ?? []).filter(p => p.team_code === team && p.role === role
    && !(role === "batting" && p.fielding.length > 0 && p.fielding.every(f => f.pos === "投手")));
  const [period, setPeriod] = useState<"series" | "regular" | "opponent_regular">(seriesNote ? "regular" : "series");
  const starter = report.next_game && [report.next_game.away_starter, report.next_game.home_starter].find(s => s.team_code === team);
  const nextStarter = hasTarget && starter?.status === "announced" ? players.find(p => p.player_id === starter.acnt) : null;
  const field = reportField(report, team);
  const others = players.filter(p => p !== nextStarter);
  return <section className="min-w-0"><SectionTitle><TeamBadge code={team} name={teamName3(team)} /> {role === "pitching" ? "投手" : "野手"}</SectionTitle>
    {!report.population?.find(p => p.team_code === team)?.complete && <p className="mb-4 text-sm text-muted">正式登錄名單尚未核實；下列為已取得紀錄，未列出不代表未登板或未出賽。</p>}
    {role === "pitching" && hasTarget && <Card className="mb-5"><h3 className="mb-2 font-bold">該場公告先發</h3>{nextStarter ? <><PlayerButton player={nextStarter} open={open} /><AbilityPanel player={nextStarter} /><div className="mt-4 border-t border-line pt-4"><PeriodRow period={nextStarter.periods[period]} role={role} full /></div></> : <p className="py-4 text-sm text-muted">本站尚未取得可靠先發公告</p>}</Card>}
    {role === "batting" && <div className="mb-5"><FieldDiagram cells={field.cells} designatedHitter={field.dh} caption={field.announced ? "該場公告先發" : "本季主力守位 · 候選"} onSelect={cell => { const pid = cell.href?.replace("#report-player-", ""); const p = pid ? reportFieldPlayer(report, team, pid) : null; if (p) open(p); }} /><p className="mt-2 text-xs text-muted">{field.announced ? "已核實賽前公告版本；棒次與守位依公告" : "依已取得本季守位場數列主力候選，非公告先發；並列保留"}。指定打擊（DH）：{field.dh?.main ?? "本站未取得"}。</p></div>}
    {seriesNote && <p className="mb-2 text-xs text-muted">{seriesNote}</p>}<div className="mb-4 flex flex-wrap gap-1" role="group" aria-label={`${teamName3(team)}統計期間`}>{periods.map(({ key, label }) => <button key={key} type="button" aria-pressed={period === key} onClick={() => setPeriod(key)} className={`min-h-11 rounded px-3 text-xs ${period === key ? "bg-ink text-paper" : "bg-band text-ink"}`}>{label}</button>)}</div>
    <h3 className="mb-3 text-sm font-bold">{role === "pitching" ? "其他投手 · 含後援" : "野手個人卡"}</h3>
    <div className="grid gap-3 sm:grid-cols-2">{others.map((p, i) => <Card key={p.player_id} className="min-w-0"><PlayerButton player={p} open={open} /><p className="mb-3 text-xs text-muted">{role === "pitching" ? p.pitching_usage?.started ? "近期曾先發" : "近期未先發" : p.fielding.map(f => f.pos).join("／") || "守位未取得"}</p><CountLine counts={p.periods[period].counts} role={role} explain={i === 0 && !nextStarter} /><p className="mt-3 text-xs text-muted">{p.periods[period].status === "missing" ? "本站未取得此期間紀錄" : p.periods[period].coverage_status !== "complete" ? "僅列已取得場次" : "期間資料已取得"}</p>{role === "pitching" && <p className="mt-2 text-xs text-muted">連續出賽 {String(p.pitching_usage?.consecutive_days ?? "—")} 天{hasTarget && <> · 距下一場 {String(p.pitching_usage?.days_to_next ?? "—")} 天</>}</p>}<p className="mt-2 text-xs text-accent">點選姓名看能力與完整指標 →</p></Card>)}</div>
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
// N08：頁尾來源說明給一般讀者讀——時戳到分鐘（台北）、內部表名改中文、逐筆連結再收一層。
const SOURCE_NAMES: Record<string, string> = {
  game_completion: "完賽判定", official_schedule: "官網賽程", schedule: "本站賽程", livelog: "逐打席紀錄",
  scoreboard: "逐局比分", box_pitching: "投手逐場成績", official_registration: "官方登錄名單", advanced_stats_A: "官方進階數據（例行賽）",
};
const COVERAGE_NAMES: Record<string, string> = { available: "已取得", verified: "已核實", complete: "完整", partial: "部分", missing: "未取得" };
const sourceName = (key: string) => SOURCE_NAMES[key] ?? `其他來源（${key}）`;
function ReportSources({ report, journey }: { report: Report; journey: ReportView["journey"] }) {
  const sources = report.sources ?? [];
  const groups = [...sources.reduce((m, s) => m.set(s.source, [...(m.get(s.source) ?? []), s]), new Map<string, typeof sources>())];
  const when = (s: (typeof sources)[number]) => taipeiMinute(s.updated_at ?? s.fetched_at ?? null);
  return <details className="border-t border-line pt-4 text-xs text-muted"><summary className="min-h-11 cursor-pointer">資料截至與來源</summary>
    <p className="my-3">本頁資料讀取於 {taipeiMinute(report.read_at) ?? "時點未取得"}；本季例行賽背景{report.regular_coverage?.closed_before_X ? "已完整，且只算到這場比賽之前" : "的截止時點本站尚未核實"}。來源的更新時間不代表官方更正發生的時間。</p>
    {journey && <p className="mb-2"><a className="underline" href={journey.announcement.source.url}>季後賽官方公告</a> · 本站取得 {taipeiMinute(journey.announcement.source.capturedAt)}</p>}
    {groups.length > 0 && <ul className="mb-2 space-y-1">{groups.map(([key, items]) => { const latest = items.map(when).filter(Boolean).sort().at(-1); return <li key={key}>{sourceName(key)}：{items.length} 筆{latest ? `，最近更新 ${latest}` : ""}</li>; })}</ul>}
    {sources.length > 0 && <details><summary className="min-h-11 cursor-pointer">逐筆來源連結（{sources.length} 筆）</summary><ul className="space-y-2">{sources.map((s, i) => <li key={`${s.source}-${i}`}><a className="underline" href={s.reference}>{sourceName(s.source)}</a> · 更新 {when(s) ?? "時點未取得"} · {s.coverage_status ? COVERAGE_NAMES[s.coverage_status] ?? s.coverage_status : "覆蓋未核實"}</li>)}</ul></details>}
  </details>;
}
/** N02：比較對象的系列還沒有完賽場時，投手／野手頁預設期間改「本季例行賽」並說明原因。
 *  只讀 `report.comparison` 與旅程模型的系列名，⛔ 不引用頁首段的任何變數（頁首屬 #278）。 */
function seriesNoteOf(report: Report, journey: ReportView["journey"]): string | null {
  const comparison = report.comparison;
  if (!comparison || comparison.series_game_keys.length !== 0) return null;
  const seriesName = journey?.series[comparison.kind_code]?.name ?? (comparison.kind_code === "C" ? "台灣大賽" : "季後挑戰賽");
  return `${seriesName}還沒開打，下列先顯示本季例行賽；可切換「本系列」「本季對該隊」。`;
}
export default function ReportPage({ view, tab, preview, nextPreview }: { view: ReportView; tab: ReportTab; preview?: { kind: ReportKind; sno: number }; nextPreview?: string | null }) {
  const { report, journey, updating } = view;
  const [selected, select] = useState<ReportPlayer | null>(null);
  const original = gameLink(report.kind_code, report.game_sno, report.season);
  if (report.status !== "ok" || !report.game) return <Card><h1 className="text-xl font-bold">{report.status === "not_final" ? "完賽後提供場間報告" : "本站尚未取得這場季後賽"}</h1><Link className="mt-4 inline-block min-h-11 text-accent underline" href={original}>返回原賽況</Link></Card>;
  const historyGame = report.game;
  const comparison = report.comparison;
  const displayReport: Report = comparison ? {...report, ...comparison, game: historyGame, next_game: comparison.game} : report;
  const series = journey?.series[comparison?.kind_code ?? report.kind_code];
  const hasTarget = !!comparison || !!journey?.next;
  const pendingTransition = !!journey?.next && journey.next.kind !== report.kind_code && !comparison;
  // #273 D1：H1 一律是這份報告所屬的那一場——場間報告＝已完賽的 X、觀戰報告＝下一場 Y（E1–E4 一致）。
  // 兩隊卡、中央勝場與投野手左右（N35）沿「開賽前背景」所指的下一場；沒有可靠下一場時沿 X。
  // 跨系列但尚無比較資料（pendingTransition）時，名單仍是 X 系列兩隊，不沿下一場。
  const nextGame = hasTarget && !pendingTransition ? displayReport.next_game : null;
  const titleGame = preview && nextGame ? nextGame : historyGame;
  // 第二讀沒帶下一場時，同系列的旅程 next 已有兩隊就沿它（與 H2 同源），否則才沿 X。
  const nextSlot = hasTarget && !pendingTransition && journey?.next?.awayCode && journey.next.homeCode ? journey.next : null;
  const teamCodes = nextGame ? [nextGame.away_team_code, nextGame.home_team_code]
    : nextSlot ? [nextSlot.awayCode!, nextSlot.homeCode!] : [historyGame.away_team_code, historyGame.home_team_code];
  // 季後場次名（N31）：場序取自公告歸併或系列完賽場，⛔ 不從場號推；查不到時退回不含場序的說法。
  const xName = postseasonGameName(journey, report.kind_code, report.game_sno);
  const xLabel = `${xName ?? "本場"}（${monthDay(historyGame.game_date)}）`;
  const yName = hasTarget ? nextGameName(journey) : null;
  const ySeries = comparison ? journey?.series[comparison.kind_code]?.name ?? (comparison.kind_code === "C" ? "台灣大賽" : "季後挑戰賽") : null;
  // N04（D8）：觀戰報告的返回連結指向下一場自己的單場頁；場間報告返回已完賽那一場。
  const back = preview ? gameLink(preview.kind, preview.sno, report.season) : original;
  const backText = preview ? `返回${yName ? `${yName} ` : "該場"}賽況` : `返回${xName ? `${xName} ` : "本場"}賽況`;
  const tabLink = (t: ReportTab) => preview ? previewLink(preview.sno, preview.kind, report.season, t) : reportLink(report.game_sno, report.kind_code, report.season, t);
  return <div className="mx-auto max-w-6xl space-y-6 pb-10">
    <header><Link href={back} className="inline-block min-h-11 py-3 text-sm text-accent underline">{backText}</Link>
      <h1 className="text-3xl font-bold tracking-tight">{teamName3(titleGame.away_team_code)}對{teamName3(titleGame.home_team_code)} · {preview ? `${yName ? `${yName} ` : ""}${REPORT_NAMES.preview}` : REPORT_NAMES.between}</h1>
      <p className="mt-2 text-sm text-muted">{preview
        ? <>開賽前背景 · 資料截至{xLabel}完賽</>
        : <>{xLabel}完賽後{hasTarget && <> · 下一場{yName ? `${yName} ` : ""}的開賽前背景</>}</>}</p>
      {!preview && nextPreview && <Link href={nextPreview} className="inline-block min-h-11 py-3 text-sm font-semibold text-accent underline">下一場：{yName ? `${yName} ` : ""}{REPORT_NAMES.preview}</Link>}
      {preview && <Link href={reportLink(report.game_sno, report.kind_code, report.season)} className="inline-block min-h-11 py-3 text-sm text-accent underline">上一場：{xName ? `${xName} ` : ""}{REPORT_NAMES.between}</Link>}
    </header>
    <nav aria-label="場間報告頁籤" className="flex gap-1 rounded-t-md bg-band p-1">{REPORT_TABS.map(t => <Link key={t.value} href={tabLink(t.value)} aria-current={tab === t.value ? "page" : undefined} className={`min-h-11 flex-1 px-4 py-3 text-center text-sm ${tab === t.value ? "bg-paper font-bold text-ink" : "text-muted hover:text-ink"}`}>{t.label}</Link>)}</nav>
    {comparison && comparison.series_game_keys.length === 0 && <p className="text-sm text-muted">{ySeries}還沒開打，「本系列」尚無紀錄；投手近期使用算到{xName ?? "本場"}。部分球員的個別數字本站尚未取得。</p>}
    {pendingTransition && <p role="status" className="text-sm text-muted">{journey?.next?.awayLabel}對{journey?.next?.homeLabel}的本站正式場次資料尚未取得；下列保留原系列兩隊資料，不以公告G1猜正式場號。</p>}
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
        <p className="mt-4 text-xs text-muted">球風以本季一軍六隊相比 · <Link href={tabLink("pitchers")} className="inline-flex min-h-11 items-center text-accent underline">比較投手</Link> · <Link href={tabLink("fielders")} className="inline-flex min-h-11 items-center text-accent underline">比較野手</Link></p>
      </section>
      <section><SectionTitle>{hasTarget ? "該場觀察重點" : "本場觀察"}</SectionTitle><div className="grid gap-5 md:grid-cols-2">{teamCodes.map(team => <div key={team} className="min-w-0"><h3 className="mb-2 font-bold"><TeamBadge code={team} name={teamName3(team)} /></h3>{(displayReport.watch_points ?? []).filter(p => p.team_code === team).map(point => { const p = displayReport.players?.find(p => p.player_id === point.player_id && p.team_code === team); return p ? <div key={p.player_id} className="py-3"><PlayerButton player={p} open={select} /><WatchLine point={point} player={p} /></div> : null; })}{!(displayReport.watch_points ?? []).some(p => p.team_code === team) && <p className="py-4 text-sm text-muted">已取得樣本尚無可核實的觀察點</p>}</div>)}</div>{(displayReport.watch_points ?? []).length > 0 && <p className="mt-3 text-xs text-muted">讀法：PA＝打席數；局數 2.1＝2⅓ 局（小數點後是出局數）。</p>}</section>

    </> : <div className="grid gap-8 md:grid-cols-2">{teamCodes.map(team => <TeamPlayers key={`${team}-${tab}`} report={displayReport} team={team} role={tab === "pitchers" ? "pitching" : "batting"} open={select} hasTarget={hasTarget} seriesNote={seriesNoteOf(report, journey)} />)}</div>}
    <ReportSources report={report} journey={journey} />
    {selected && <ReportPlayerDialog key={`${selected.team_code}-${selected.role}-${selected.player_id}`} player={selected} close={() => select(null)} season={report.season} hasTarget={hasTarget} usageCutoff={xName ? `截至${xName}完賽` : null} />}
  </div>;
}
