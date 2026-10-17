"use client";

import { useCallback, useRef, useState } from "react";

import { Card, InfoDot, TeamLogo } from "@/components/ui";
import { RosterDrawer } from "./roster-drawer";
import {
  DRAWER_COPY,
  POS_FILTERS,
  ROSTER_COPY,
  ROSTER_METHOD_HELP,
  SCOPES,
  SORTS,
  arrowView,
  filterMembersByPos,
  gText,
  hasSeriesScope,
  initialScope,
  lineText,
  memberRoles,
  scopeG,
  seriesPending,
  prLabel,
  sortMembers,
  teamLabel,
  type PlayoffsRoster,
  type RosterMember,
  type RosterPosFilter,
  type RosterScope,
  type RosterSort,
  type RosterTeam,
} from "@/lib/playoffs-roster";

export function RosterSection({ data }: { data: PlayoffsRoster | null }) {
  return (
    <section aria-labelledby="roster-heading" className="min-w-0 space-y-3">
      <div className="flex items-center gap-2">
        <h2 id="roster-heading" className="text-sm font-bold text-ink">{ROSTER_COPY.heading}</h2>
        <InfoDot
          label="資格名單說明"
          content={
            <div className="space-y-1">
              {ROSTER_METHOD_HELP.map((line) => <p key={line}>{line}</p>)}
            </div>
          }
        />
      </div>
      {data == null ? (
        <p role="status" className="card p-3 text-sm text-muted">
          {ROSTER_COPY.loadFailed}
        </p>
      ) : data.status === "series_unknown" ? (
        <p role="status" className="card p-3 text-sm text-muted">
          {ROSTER_COPY.seriesUnknown}
        </p>
      ) : (
        <RosterBody data={data} />
      )}
    </section>
  );
}

export default RosterSection;

/** 持有篩選／排序／抽屜 state；預設選第一支球隊（不再一次攤開 64 張卡），輪詢換 `data` 時保留使用者選擇。 */
function RosterBody({ data }: { data: PlayoffsRoster }) {
  const [team, setTeam] = useState<string>(() => data.teams[0]?.team_code ?? "all");
  const [pos, setPos] = useState<RosterPosFilter>("all");
  const [sort, setSort] = useState<RosterSort>("games");
  const [scope, setScope] = useState<RosterScope>(() => initialScope(data));
  const [open, setOpen] = useState<RosterMember | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const close = useCallback(() => {
    const id = open?.player_id;
    setOpen(null);
    if (id) requestAnimationFrame(() => root.current?.querySelector<HTMLElement>(`[data-open-player="${id}"]`)?.focus());
  }, [open]);
  const current = open ? data.teams.flatMap((t) => t.members).find((m) => m.player_id === open.player_id) ?? open : null;
  return (
    <div ref={root}>
      <RosterView data={data} team={team} pos={pos} sort={sort} scope={scope}
        onTeam={setTeam} onPos={setPos} onSort={setSort} onScope={setScope} onOpen={setOpen} />
      {current ? (
        <RosterDrawer member={current} year={data.year} series={data.series} sectionVersion={data.context_version}
          sectionRosterVersion={data.roster_version}
          onClose={close} />
      ) : null}
    </div>
  );
}

const SEG_TRACK = "flex h-8 w-fit max-w-full items-center overflow-x-auto overscroll-x-contain rounded-md bg-band p-0.5";
const segBtnClass = (on: boolean) =>
  `inline-flex shrink-0 touch-manipulation items-center whitespace-nowrap rounded-sm px-2.5 py-1 text-xs font-medium transition-colors ${
    on ? "bg-ink font-bold text-paper" : "text-muted hover:text-ink"
  }`;

/** 純呈現（無 hooks，測試可直接以任一篩選／排序渲染）。 */
export function RosterView({ data, team, pos = "all", sort = "games", scope: scopeIn = "background", onTeam, onPos, onSort, onScope, onOpen }: {
  data: PlayoffsRoster; team: string; pos?: RosterPosFilter; sort?: RosterSort; scope?: RosterScope;
  onTeam?: (t: string) => void; onPos?: (p: RosterPosFilter) => void; onSort?: (s: RosterSort) => void; onScope?: (s: RosterScope) => void;
  onOpen?: (m: RosterMember) => void;
}) {
  const shown = data.teams.filter((t) => team === "all" || t.team_code === team);
  const scope: RosterScope = hasSeriesScope(data) ? scopeIn : "background";
  return (
    <div className="min-w-0 space-y-3" data-area-status={data.status} data-scope={scope} data-pos={pos}>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label={ROSTER_COPY.teamFilterLabel} className={SEG_TRACK}>
            {[...data.teams.map((t) => ({ code: t.team_code, label: teamLabel(t) })), { code: "all", label: ROSTER_COPY.all }]
              .map((o) => (
                <button key={o.code} type="button" aria-pressed={team === o.code} onClick={() => onTeam?.(o.code)}
                  className={segBtnClass(team === o.code)}>
                  {o.label}
                </button>
              ))}
          </div>
          {hasSeriesScope(data) ? (
            <div role="group" aria-label={ROSTER_COPY.scopeLabel} className={SEG_TRACK}>
              {SCOPES.map((o) => (
                <button key={o.key} type="button" aria-pressed={scope === o.key} onClick={() => onScope?.(o.key)}
                  className={segBtnClass(scope === o.key)}>
                  {o.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label={ROSTER_COPY.posFilterLabel} className={SEG_TRACK}>
            {POS_FILTERS.map((p) => (
              <button key={p.key} type="button" aria-pressed={pos === p.key} onClick={() => onPos?.(p.key)}
                className={segBtnClass(pos === p.key)}>
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="whitespace-nowrap text-xs text-muted">{ROSTER_COPY.sortLabel}</span>
            <div role="group" aria-label={ROSTER_COPY.sortLabel} className={SEG_TRACK}>
              {SORTS.map((s) => (
                <button key={s.key} type="button" aria-pressed={sort === s.key} onClick={() => onSort?.(s.key)}
                  className={segBtnClass(sort === s.key)}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      {shown.map((t) => <TeamBlock key={t.team_code} team={t} pos={pos} sort={sort} scope={scope} onOpen={onOpen} />)}
    </div>
  );
}

function MemberGrid({ members, labelId, scope, onOpen }: {
  members: RosterMember[]; labelId?: string; scope: RosterScope; onOpen?: (m: RosterMember) => void;
}) {
  return (
    <ul aria-labelledby={labelId} className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {members.map((m) => (
        <li key={m.player_id} className="min-w-0">
          <MemberCard m={m} scope={scope} onOpen={onOpen} />
        </li>
      ))}
    </ul>
  );
}

function TeamBlock({ team, pos, sort, scope, onOpen }: {
  team: RosterTeam; pos: RosterPosFilter; sort: RosterSort; scope: RosterScope; onOpen?: (m: RosterMember) => void;
}) {
  const headingId = `roster-team-${team.team_code}`;
  const filtered = sortMembers(filterMembersByPos(team.members, pos), sort, scope);
  const pitchers = pos === "all" ? filtered.filter((m) => m.role === "pitching") : [];
  const batters = pos === "all" ? filtered.filter((m) => m.role !== "pitching") : [];

  return (
    <div className="space-y-3" data-team={team.team_code} data-roster-status={team.roster_status}>
      <h3 id={headingId} className="flex items-center gap-2 text-sm font-bold text-ink">
        <TeamLogo code={team.team_code} name={teamLabel(team)} size={20} decorative />
        {teamLabel(team)}
        {team.roster_status === "submitted"
          ? <span className="text-xs font-semibold text-muted tabular-nums">{filtered.length} 人</span> : null}
        {scope === "series" && team.roster_status === "submitted" && team.series_pending_games?.length
          ? <span className="pm-tag" data-series-pending>{ROSTER_COPY.pending}</span> : null}
      </h3>
      {team.roster_status !== "submitted" ? (
        <p className="card p-3 text-sm text-muted">{ROSTER_COPY.pending}</p>
      ) : pos === "all" ? (
        <div className="space-y-3">
          {pitchers.length > 0 && (
            <div className="space-y-1.5" data-role-group="pitching">
              <h4 id={`${headingId}-pit`} className="flex items-center gap-1.5 text-xs font-bold text-muted">
                <span>投手</span>
                <span className="font-mono font-normal tabular-nums text-faint">{pitchers.length}</span>
              </h4>
              <MemberGrid members={pitchers} labelId={`${headingId}-pit`} scope={scope} onOpen={onOpen} />
            </div>
          )}
          {batters.length > 0 && (
            <div className="space-y-1.5" data-role-group="batting">
              <h4 id={`${headingId}-bat`} className="flex items-center gap-1.5 text-xs font-bold text-muted">
                <span>野手</span>
                <span className="font-mono font-normal tabular-nums text-faint">{batters.length}</span>
              </h4>
              <MemberGrid members={batters} labelId={`${headingId}-bat`} scope={scope} onOpen={onOpen} />
            </div>
          )}
        </div>
      ) : (
        <MemberGrid members={filtered} labelId={headingId} scope={scope} onOpen={onOpen} />
      )}
    </div>
  );
}

const DIR_CLASS = { up: "text-up", down: "text-down", flat: "text-muted" } as const;

/** 緊湊小卡：整卡可點開啟能力與走勢抽屜，省去重複的滿版按鈕，四欄可一眼掃描。 */
export function MemberCard({ m, scope = "background", onOpen }: {
  m: RosterMember; scope?: RosterScope; onOpen?: (m: RosterMember) => void;
}) {
  const bg = m.background;
  const series = scope === "series";
  const pending = seriesPending(m, scope);
  const line = pending ? ROSTER_COPY.pending : lineText(m, scope);
  const a = arrowView(m);
  return (
    <div className="card h-full min-w-0 p-0" data-player={m.player_id} data-level={bg.level}>
      <button
        type="button"
        data-open-player={m.player_id}
        aria-haspopup="dialog"
        aria-label={`${m.name} ${DRAWER_COPY.open}`}
        onClick={() => onOpen?.(m)}
        className="group flex h-full w-full flex-col justify-between gap-1.5 rounded p-2.5 text-left transition-colors hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <div className="w-full space-y-1.5">
          <div className="flex min-w-0 items-baseline justify-between gap-1.5">
            <span className="flex min-w-0 items-baseline gap-1.5">
              <span className="truncate text-sm font-bold text-ink group-hover:text-accent">{m.name}</span>
              <span className="shrink-0 text-xs text-muted">{m.official_position}</span>
              {!series && bg.level === "D" ? <span className="pm-tag shrink-0">{ROSTER_COPY.farm}</span> : null}
            </span>
            <span className="shrink-0 font-mono text-xs font-bold tabular-nums text-ink" data-g>
              {pending ? ROSTER_COPY.pending : gText({ g: scopeG(m, scope) })}
            </span>
          </div>
          {memberRoles(m).length ? (
            <div className="flex flex-wrap items-center gap-1 text-[11px] font-medium [&>[data-role]]:rounded [&>[data-role]]:bg-band [&>[data-role]]:px-1.5 [&>[data-role]]:py-0.5">
              {memberRoles(m).map((role) => (
                <span key={role} data-role className="text-ink">{role}</span>
              ))}
            </div>
          ) : null}
          <div className="font-mono text-xs tabular-nums text-muted" data-line>{line ?? ROSTER_COPY.missing}</div>
        </div>
        {!series && (
          <div className="w-full space-y-1.5 border-t border-line pt-1.5 text-[11px] text-muted" data-arrow={a.dir ?? "none"}>
            <div className="flex items-baseline justify-between gap-1">
              <span>{a.label}</span>
              <span className="flex items-baseline gap-1">
                <span className="font-mono font-bold tabular-nums text-ink">{a.value}</span>
                <span className={`font-semibold ${a.dir ? DIR_CLASS[a.dir] : "text-muted"}`}>{a.text}</span>
              </span>
            </div>
            {bg.pr_tags.length ? (
              <div className="flex flex-wrap gap-1" aria-label="官方 PR 90 以上">
                {bg.pr_tags.map((t) => (
                  <span key={t.key} data-pr={t.key}
                    className="rounded border border-accent px-1 py-0.2 text-[10px] font-semibold text-accent">
                    {prLabel(t.key, m.role)} <span className="font-mono tabular-nums">PR {t.value}</span>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </button>
    </div>
  );
}
