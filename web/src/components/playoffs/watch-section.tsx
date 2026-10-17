import type { ReactNode } from "react";

import { Tooltip } from "@/components/tooltip";
import { Card, InfoDot, TeamLogo } from "@/components/ui";
import {
  ROSTER_ROLE_TEXT,
  shortDate,
  taipeiTime,
  type PlayoffsWatch,
  type WatchTeam,
} from "@/lib/playoffs-watch";
import { teamShortName } from "@/lib/postseason-journey";
import { PitcherLoadRow, dayLabel } from "./watch-load-strip";

export function WatchSection({ data }: { data: PlayoffsWatch | null }) {
  return (
    <section aria-labelledby="watch-heading" className="space-y-4">
      <h2 id="watch-heading" className="sr-only">觀戰重點</h2>
      {data == null ? (
        <p role="status" className="card p-3 text-sm text-muted">
          第 4 區資料暫時無法讀取，其他區不受影響。
        </p>
      ) : data.status !== "ok" ? (
        <p role="status" className="card p-3 text-sm text-muted">
          {data.text ?? "目前沒有可呈現的觀戰重點。"}
        </p>
      ) : (
        <>
          <Starters data={data} />
          <Bullpen data={data} />
        </>
      )}
    </section>
  );
}

// —— 官方先發投手 ——————————————————————————————————————————————————

function Starters({ data }: { data: PlayoffsWatch }) {
  if (!data.starters?.length) return null;
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-bold text-ink">官方先發投手</h3>
      <ul className="grid gap-2.5 sm:grid-cols-2">
        {data.starters.map((s) => (
          <li key={s.team_code} data-starter-status={s.status}
            className="card flex min-w-0 items-center justify-between gap-2 px-3.5 py-2.5">
            <span className="flex items-center gap-1.5 text-sm font-bold text-ink">
              <TeamLogo code={s.team_code} name={teamShortName(s.team_code)} size={20} decorative />
              {teamShortName(s.team_code)}
            </span>
            <span className={s.status === "announced" && s.name
              ? "break-words text-base font-bold text-ink" : "break-words text-sm text-muted"}>
              {s.text}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// —— 4A：牛棚近期使用負荷 ——————————————————————————————————————————————

function bullpenNote(data: PlayoffsWatch): ReactNode {
  return (
    <div className="space-y-1">
      <p>球數與出賽日的描述，不是健康判斷、可用性或教練調度。</p>
      {data.teams.some((t) => t.roster_status === "submitted") ? (
        <p>預設列名單中 #終結、#勝利組、#長中繼；{ROSTER_ROLE_TEXT}。</p>
      ) : null}
    </div>
  );
}

function Bullpen({ data }: { data: PlayoffsWatch }) {
  const refreshed = taipeiTime(data.as_of.last_refresh_at);
  const scaleMax = Math.max(0, ...data.teams.flatMap((t) => t.pitchers.flatMap((p) => p.load.days.map((d) => d.pitches))));
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 className="text-sm font-bold text-ink">牛棚近期使用負荷</h3>
        <InfoDot label="牛棚負荷說明" content={bullpenNote(data)} />
        {/proposed/.test(data.policy_version) ? (
          <Tooltip suppressUnderline content={<p>門檻為本站建議值（{data.policy_version}，尚未經歷史資料校準）。</p>}>
            <button type="button" data-proposed aria-label="建議門檻：顯示說明"
              className="pm-st pm-st--sample relative touch-manipulation before:absolute before:-inset-y-2.5 before:inset-x-0 before:content-[''] hover:text-ink">
              建議門檻
            </button>
          </Tooltip>
        ) : null}
        {refreshed ? <span className="ml-auto text-xs text-muted tabular-nums">資料更新 {refreshed}</span> : null}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {data.teams.map((t) => <TeamLoad key={t.team_code} team={t} scaleMax={scaleMax} />)}
      </div>
    </div>
  );
}

function TeamLoad({ team, scaleMax }: { team: WatchTeam; scaleMax: number }) {
  const shown = team.pitchers.filter((p) => p.default_visible);
  const others = team.pitchers.filter((p) => !p.default_visible);
  const gaps = team.days.filter((d) => !d.complete);
  return (
    <Card padding="p-3.5" className="min-w-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line pb-2">
        <TeamLogo code={team.team_code} name={teamShortName(team.team_code)} size={20} decorative />
        <h4 className="text-sm font-bold text-ink">{teamShortName(team.team_code)}</h4>
        {team.roster_status === "submitted" && gaps.length ? (
          <Tooltip suppressUnderline content={
            <ul className="space-y-0.5">
              {gaps.map((d) => <li key={d.date}>{shortDate(d.date)}（{dayLabel(d.offset)}）：{d.text.join("；")}</li>)}
            </ul>
          }>
            <button type="button" data-team-gaps aria-label="部分日期資料不完整：顯示理由"
              className="relative inline-flex min-h-6 touch-manipulation items-center rounded border border-dashed border-line-strong px-1.5 text-xs text-muted before:absolute before:-inset-y-2.5 before:inset-x-0 before:content-[''] hover:text-ink">
              部分日期資料不完整
            </button>
          </Tooltip>
        ) : null}
      </div>
      {team.roster_status !== "submitted" ? (
        <p role="status" className="mt-2 text-sm text-muted">{team.roster_text}；不以出賽紀錄代替名單。</p>
      ) : (
        <>
          {shown.length ? (
            <ul className="mt-1 divide-y divide-line">{shown.map((p) => <PitcherLoadRow key={p.player_id} p={p} scaleMax={scaleMax} />)}</ul>
          ) : <p className="mt-2 text-sm text-muted">名單中沒有標記為終結、勝利組或長中繼的投手。</p>}
          {others.length ? (
            <details className="mt-2 border-t border-line pt-1">
              <summary className="flex min-h-9 cursor-pointer items-center text-xs font-semibold text-accent">
                其他投手（{others.length}）
              </summary>
              <ul className="divide-y divide-line">{others.map((p) => <PitcherLoadRow key={p.player_id} p={p} scaleMax={scaleMax} />)}</ul>
            </details>
          ) : null}
        </>
      )}
    </Card>
  );
}

export default WatchSection;
