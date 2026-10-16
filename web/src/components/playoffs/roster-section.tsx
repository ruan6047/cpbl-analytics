"use client";

import { useCallback, useRef, useState } from "react";

import { RosterDrawer } from "./roster-drawer";
import {
  DRAWER_COPY,
  ROSTER_COPY,
  SORTS,
  arrowView,
  gText,
  lineText,
  prLabel,
  sortMembers,
  teamLabel,
  type PlayoffsRoster,
  type RosterMember,
  type RosterSort,
  type RosterTeam,
} from "@/lib/playoffs-roster";
import { teamColor } from "@/lib/teams";

// #286 S05：季後賽第 3 區「系列賽 32 人資格名單」（例行賽與對戰背景）。
//
// 掛點（#285 掛點契約 r3 §2）：
// - S04 外框提供 `#roster` 錨點、client 取數與輪詢；本元件⛔ 不設 `id="roster"`、⛔ 不取摘要。
// - `data == null` ⇒ 第 3 區錯誤態；不影響其他區。
// - 輪詢只換 `data` props：球隊篩選與排序是元件內 state，資料更新不重置；清單以 player_id 為 key，不 remount。
// - 說明性注意事項⛔ 在區內就地顯示（28 人登錄、資格≠可用、G 定義、PR 來源、二軍背景）：一律經 `rosterNotes(data)`
//   交 S04 頁尾；格內只留「—」「待更新」。
// - 統計、層級、PR 標籤全由後端算；元件只排字。

export function RosterSection({ data }: { data: PlayoffsRoster | null }) {
  return (
    <section aria-labelledby="roster-heading" className="min-w-0 space-y-4">
      <h2 id="roster-heading" className="text-lg font-bold text-ink">{ROSTER_COPY.heading}</h2>
      {data == null ? (
        <p role="status" className="rounded border border-line bg-surface p-3 text-sm text-muted">
          {ROSTER_COPY.loadFailed}
        </p>
      ) : data.status === "series_unknown" ? (
        <p role="status" className="rounded border border-line bg-surface p-3 text-sm text-muted">
          {ROSTER_COPY.seriesUnknown}
        </p>
      ) : (
        <RosterBody data={data} />
      )}
    </section>
  );
}

export default RosterSection;

/** 持有篩選／排序／抽屜 state；固定位置、不給 key——輪詢換 `data` 時保留使用者選擇，抽屜不關、不搶焦點。 */
function RosterBody({ data }: { data: PlayoffsRoster }) {
  const [team, setTeam] = useState<string>("all");
  const [sort, setSort] = useState<RosterSort>("position");
  const [open, setOpen] = useState<RosterMember | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const close = useCallback(() => {
    const id = open?.player_id;
    setOpen(null);
    // 焦點回原小卡按鈕（以 player_id 找，輪詢重繪後仍是同一顆）。
    if (id) requestAnimationFrame(() => root.current?.querySelector<HTMLElement>(`[data-open-player="${id}"]`)?.focus());
  }, [open]);
  // 抽屜顯示最新一份資料中的同一人（找不到就沿用開啟時那份）。
  const current = open ? data.teams.flatMap((t) => t.members).find((m) => m.player_id === open.player_id) ?? open : null;
  return (
    <div ref={root}>
      <RosterView data={data} team={team} sort={sort} onTeam={setTeam} onSort={setSort} onOpen={setOpen} />
      {current ? (
        <RosterDrawer member={current} year={data.year} series={data.series} sectionVersion={data.context_version}
          onClose={close} />
      ) : null}
    </div>
  );
}

const SEG = "min-h-11 rounded-full px-3 text-sm font-semibold";
const segClass = (on: boolean) => `${SEG} ${on ? "bg-ink text-paper" : "bg-surface-2 text-muted hover:text-ink"}`;

/** 純呈現（無 hooks，測試可直接以任一篩選／排序渲染）。 */
export function RosterView({ data, team, sort, onTeam, onSort, onOpen }: {
  data: PlayoffsRoster; team: string; sort: RosterSort;
  onTeam?: (t: string) => void; onSort?: (s: RosterSort) => void; onOpen?: (m: RosterMember) => void;
}) {
  const shown = data.teams.filter((t) => team === "all" || t.team_code === team);
  return (
    <div className="min-w-0 space-y-4" data-area-status={data.status}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div role="group" aria-label={ROSTER_COPY.teamFilterLabel} className="flex flex-wrap gap-2">
          {[{ code: "all", label: ROSTER_COPY.all }, ...data.teams.map((t) => ({ code: t.team_code, label: teamLabel(t) }))]
            .map((o) => (
              <button key={o.code} type="button" aria-pressed={team === o.code} onClick={() => onTeam?.(o.code)}
                className={segClass(team === o.code)}>
                {o.label}
              </button>
            ))}
        </div>
        <div role="group" aria-label={ROSTER_COPY.sortLabel} className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-muted">{ROSTER_COPY.sortLabel}</span>
          {SORTS.map((s) => (
            <button key={s.key} type="button" aria-pressed={sort === s.key} onClick={() => onSort?.(s.key)}
              className={segClass(sort === s.key)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {shown.map((t) => <TeamBlock key={t.team_code} team={t} sort={sort} onOpen={onOpen} />)}
    </div>
  );
}

function TeamBlock({ team, sort, onOpen }: { team: RosterTeam; sort: RosterSort; onOpen?: (m: RosterMember) => void }) {
  const headingId = `roster-team-${team.team_code}`;
  return (
    <div className="space-y-2" data-team={team.team_code} data-roster-status={team.roster_status}>
      <h3 id={headingId} className="flex items-center gap-2 text-sm font-bold text-ink">
        <span aria-hidden className="inline-block h-3 w-1 rounded-sm" style={{ background: teamColor(team.team_code) }} />
        {teamLabel(team)}
        {team.roster_status === "submitted"
          ? <span className="text-xs font-semibold text-muted tabular-nums">{team.members.length} 人</span> : null}
      </h3>
      {team.roster_status !== "submitted" ? (
        <p className="rounded border border-line bg-surface p-3 text-sm text-muted">{ROSTER_COPY.pending}</p>
      ) : (
        <ul aria-labelledby={headingId} className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {sortMembers(team.members, sort).map((m) => (
            <li key={m.player_id} className="min-w-0">
              <MemberCard m={m} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MemberCard({ m, onOpen }: { m: RosterMember; onOpen?: (m: RosterMember) => void }) {
  const bg = m.background;
  const line = lineText(m);
  return (
    <div className="h-full min-w-0 rounded border border-line bg-surface p-3 text-left" data-player={m.player_id}
      data-level={bg.level}>
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="truncate font-bold text-ink">{m.name}</span>
        <span className="text-xs text-muted">{m.official_position}</span>
        {bg.level === "D" ? <span className="pm-tag">{ROSTER_COPY.farm}</span> : null}
        <span className="ml-auto font-mono text-sm font-bold tabular-nums text-ink" data-g>{gText(bg)}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted">
        <span data-role>{ROSTER_COPY.roleSource}：<span className="text-ink">{m.tactical_role ?? ROSTER_COPY.missing}</span></span>
        <span className="tabular-nums" data-line>{line ?? ROSTER_COPY.missing}</span>
      </div>
      <ArrowLine m={m} />
      {bg.pr_tags.length ? (
        <ul className="mt-2 flex flex-wrap gap-1" aria-label="官方 PR 90 以上">
          {bg.pr_tags.map((t) => (
            <li key={t.key} data-pr={t.key}
              className="rounded border border-accent px-1.5 py-0.5 text-[11px] font-semibold text-accent">
              {prLabel(t.key, m.role)} <span className="font-mono tabular-nums">PR {t.value}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <button type="button" data-open-player={m.player_id} aria-haspopup="dialog" onClick={() => onOpen?.(m)}
        aria-label={`${m.name} ${DRAWER_COPY.open}`}
        className="mt-2 inline-flex min-h-11 items-center rounded-full border border-line-strong px-3 text-sm font-semibold text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent">
        {DRAWER_COPY.open}
      </button>
    </div>
  );
}

const DIR_CLASS = { up: "text-up", down: "text-down", flat: "text-muted" } as const;

function ArrowLine({ m }: { m: RosterMember }) {
  const a = arrowView(m);
  return (
    <div className="mt-1 flex flex-wrap items-baseline gap-x-2 text-xs text-muted" data-arrow={a.dir ?? "none"}>
      <span>{a.label}</span>
      <span className="font-mono tabular-nums text-ink">{a.value}</span>
      <span className={`font-semibold ${a.dir ? DIR_CLASS[a.dir] : "text-muted"}`}>{a.text}</span>
    </div>
  );
}
