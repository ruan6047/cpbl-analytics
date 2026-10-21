"use client";

import { useCallback, useRef, useState } from "react";

import { ENTITY_LINK, InfoDot, TeamLogo } from "@/components/ui";
import { RosterDrawer } from "./roster-drawer";
import {
  DRAWER_COPY,
  ROSTER_COPY,
  ROSTER_METHOD_HELP,
  SCOPES,
  compositeParts,
  fielderBlocks,
  hasSeriesScope,
  initialScope,
  pitcherBlocks,
  teamComposition,
  teamLabel,
  type BlockColumn,
  type PlayoffsRoster,
  type RosterBlock,
  type RosterMember,
  type RosterScope,
  type RosterTeam,
} from "@/lib/playoffs-roster";

// #350 方案 D：兩隊並列；投手依角色、野手依主守位分區（另設 DH 區）；每區先列灰底綜合成績、下方只列人名，
// 個人數值點人名開抽屜才看（需求方裁定 6309977252 ①、6310146254）。

export function RosterSection({ data }: { data: PlayoffsRoster | null }) {
  return (
    <section aria-labelledby="roster-heading" className="min-w-0 space-y-3">
      <div className="flex items-center gap-2">
        <h2 id="roster-heading" className="text-sm font-bold text-ink">{ROSTER_COPY.heading}</h2>
        <InfoDot
          label="系列賽名單說明"
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

/** 持有資料範圍與抽屜 state；輪詢換 `data` 時保留使用者選擇。 */
function RosterBody({ data }: { data: PlayoffsRoster }) {
  const [scope, setScope] = useState<RosterScope>(() => initialScope(data));
  const [open, setOpen] = useState<RosterMember | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const onOpen = useCallback((m: RosterMember, el?: HTMLElement) => {
    trigger.current = el ?? null;
    setOpen(m);
  }, []);
  // 同一人會出現在多區（多角色、主守位＋DH），焦點要還給「實際被點的那顆」按鈕，⛔ 以 player_id 找第一顆。
  const close = useCallback(() => {
    const id = open?.player_id;
    const el = trigger.current;
    setOpen(null);
    requestAnimationFrame(() => {
      if (el?.isConnected) el.focus();
      else if (id) root.current?.querySelector<HTMLElement>(`[data-open-player="${id}"]`)?.focus();
    });
  }, [open]);
  const shownScope: RosterScope = hasSeriesScope(data) ? scope : "background";
  const current = open ? data.teams.flatMap((t) => t.members).find((m) => m.player_id === open.player_id) ?? open : null;
  return (
    <div ref={root}>
      <RosterBlocks data={data} scope={scope} onScope={setScope} onOpen={onOpen} />
      {current ? (
        <RosterDrawer member={current} scope={shownScope} year={data.year} series={data.series}
          sectionVersion={data.context_version} sectionRosterVersion={data.roster_version} onClose={close} />
      ) : null}
    </div>
  );
}

const SEG_TRACK = "flex h-8 w-fit max-w-full items-center overflow-x-auto overscroll-x-contain rounded-md bg-band p-0.5";
const segBtnClass = (on: boolean) =>
  `inline-flex shrink-0 touch-manipulation items-center whitespace-nowrap rounded-sm px-2.5 py-1 text-xs font-medium transition-colors ${
    on ? "bg-ink font-bold text-paper" : "text-muted hover:text-ink"
  }`;

/** 純呈現（無 hooks，測試可直接以任一資料範圍渲染）。 */
export function RosterBlocks({ data, scope: scopeIn = "background", onScope, onOpen }: {
  data: PlayoffsRoster; scope?: RosterScope; onScope?: (s: RosterScope) => void;
  onOpen?: (m: RosterMember, el?: HTMLElement) => void;
}) {
  const scope: RosterScope = hasSeriesScope(data) ? scopeIn : "background";
  const teams = data.teams;
  return (
    <div className="card min-w-0 space-y-5 p-3 sm:p-4" data-area-status={data.status} data-scope={scope}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <ul className="min-w-0 space-y-1" aria-label="兩隊名單組成">
          {teams.map((t) => <TeamSummary key={t.team_code} team={t} scope={scope} />)}
        </ul>
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
      <BlockGroup id="roster-pitchers" title={ROSTER_COPY.pitchers} blocks={pitcherBlocks(teams, scope)}
        teams={teams} onOpen={onOpen} />
      <BlockGroup id="roster-fielders" title={ROSTER_COPY.fielders} blocks={fielderBlocks(teams, scope)}
        teams={teams} onOpen={onOpen} />
      <p className="text-xs text-muted">{ROSTER_COPY.legend[scope]}</p>
    </div>
  );
}

function TeamSummary({ team, scope }: { team: RosterTeam; scope: RosterScope }) {
  const submitted = team.roster_status === "submitted";
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm" data-team={team.team_code}
      data-roster-status={team.roster_status}>
      <TeamLogo code={team.team_code} name={teamLabel(team)} size={20} decorative />
      <span className="font-bold text-ink">{teamLabel(team)}</span>
      <span className="text-xs text-muted tabular-nums" data-composition>
        {submitted ? teamComposition(team) : ROSTER_COPY.pending}
      </span>
      {scope === "series" && submitted && team.series_pending_games?.length
        ? <span className="pm-tag" data-series-pending>{ROSTER_COPY.pending}</span> : null}
    </li>
  );
}

function BlockGroup({ id, title, blocks, teams, onOpen }: {
  id: string; title: string; blocks: RosterBlock[]; teams: readonly RosterTeam[];
  onOpen?: (m: RosterMember, el?: HTMLElement) => void;
}) {
  if (!blocks.length) return null;
  return (
    <section aria-labelledby={id} className="space-y-3" data-block-group={id}>
      <h3 id={id} className="border-b-2 border-ink pb-1 text-sm font-bold text-ink">{title}</h3>
      <div className="grid gap-x-8 gap-y-4 lg:grid-cols-2">
        {blocks.map((b) => <Block key={b.key} block={b} teams={teams} onOpen={onOpen} />)}
      </div>
    </section>
  );
}

function Block({ block, teams, onOpen }: {
  block: RosterBlock; teams: readonly RosterTeam[]; onOpen?: (m: RosterMember, el?: HTMLElement) => void;
}) {
  const hid = `roster-block-${block.key}`;
  return (
    <div className="min-w-0 space-y-1.5" data-block={block.key}>
      <h4 id={hid} className="flex flex-wrap items-baseline gap-x-2 text-sm font-bold text-ink">
        <span>{block.label}</span>
        {block.note ? <span className="text-xs font-normal text-muted" data-block-note>{block.note}</span> : null}
      </h4>
      <div className="grid grid-cols-2 gap-x-3">
        {block.columns.map((c, i) => <Column key={c.team_code} col={c} team={teams[i]} block={block} onOpen={onOpen} />)}
      </div>
    </div>
  );
}

function Column({ col, team, block, onOpen }: {
  col: BlockColumn; team: RosterTeam; block: RosterBlock; onOpen?: (m: RosterMember, el?: HTMLElement) => void;
}) {
  const parts = compositeParts(col.composite);
  return (
    <div className="min-w-0 space-y-1" data-column={col.team_code}>
      <div className="flex flex-wrap items-baseline gap-x-1.5 rounded bg-surface-2 px-2 py-1 font-mono text-xs tabular-nums text-muted"
        data-composite={col.composite.kind}>
        <TeamLogo code={team.team_code} name={teamLabel(team)} size={14} decorative />
        <span className="sr-only">{teamLabel(team)} {block.label} 綜合成績</span>
        {typeof parts === "string" ? <span className="font-sans">{parts}</span> : (
          <span className="whitespace-nowrap">
            {parts[0].label} <b className="text-ink">{parts[0].value}</b>
          </span>
        )}
        {typeof parts === "string" ? null : (
          <span className="whitespace-nowrap">
            · {block.role === "pitching"
              ? <><b className="text-ink">{parts[1].value}</b> {parts[1].label}</>
              : <>{parts[1].label} <b className="text-ink">{parts[1].value}</b></>}
          </span>
        )}
      </div>
      {col.members.length ? (
        // 刻意：人名按鈕維持文字高度、左右間距 ≥10px，不撐到 44px（需求方裁定 6310146254 ③，列為 UI_UX_SYSTEM
        // §1 原則 6 觸控 ≥44px 的本區例外）；撐高會讓整區長一倍，違背「一眼看懂兩隊對照」。
        <ul className="flex flex-wrap gap-x-2.5 gap-y-1 px-1" aria-label={`${teamLabel(team)} ${block.label}`}>
          {col.members.map(({ m, farm, uncertain }) => (
            <li key={m.player_id} className="inline-flex items-baseline gap-1">
              <button type="button" data-open-player={m.player_id} aria-haspopup="dialog"
                aria-label={`${m.name} ${DRAWER_COPY.open}`}
                onClick={(e) => onOpen?.(m, e.currentTarget)}
                className={`text-sm ${ENTITY_LINK} rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`}>
                {m.name}
              </button>
              {farm ? <span className="pm-tag" data-farm>{ROSTER_COPY.farm}</span> : null}
              {uncertain ? <span className="pm-tag" data-uncertain>{ROSTER_COPY.pending}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-1 text-sm text-faint">{ROSTER_COPY.missing}</p>
      )}
    </div>
  );
}
