import Link from "next/link";
import { Card, Eyebrow, TeamLogo, EmptyState, StatusBadge } from "@/components/ui";
import { PregameCard } from "@/components/pregame-card";
import {
  resolvePregameFromDaily,
  refreshCopy,
  refreshAgeText,
  shortDate,
  slateDistanceText,
  gameHref,
  type DailySummary,
  type DailyGame,
} from "@/lib/daily-summary";

// 首頁每日入口 hub（UX-GAME-HOME1）。純展示 server component：依序渲染最近比賽日、
// 資料 freshness、下一批賽事（含 UX-OUTCOME-HOME 的賽前卡）。所有語意由 API 推導，
// 不寫死「昨天／今天」，未完成場次不以 0–0 假裝賽果。

function TeamRow({
  code,
  name,
  score,
  win,
  align = "left",
}: {
  code: string;
  name: string;
  score: number | null;
  win: boolean;
  align?: "left" | "right";
}) {
  const logo = <TeamLogo code={code} name={name} size={20} decorative />;
  return (
    <div className={`flex items-center gap-2 ${align === "right" ? "flex-row-reverse" : ""}`}>
      {logo}
      <span className={`text-sm ${win ? "font-semibold text-ink" : "text-muted"}`}>{name}</span>
      {score != null && (
        <span className={`ml-auto font-mono text-base tabular-nums ${win ? "font-bold text-ink" : "text-muted"} ${align === "right" ? "ml-0 mr-auto" : ""}`}>
          {score}
        </span>
      )}
    </div>
  );
}

// 完賽場次：比分 + 勝方強調 + 進入復盤。未完成場次比分為 null 時只顯示對戰與狀態文字。
function CompletedGame({ g }: { g: DailyGame }) {
  const homeWin = g.completed && (g.home_score ?? 0) > (g.away_score ?? 0);
  const awayWin = g.completed && (g.away_score ?? 0) > (g.home_score ?? 0);
  return (
    <Link
      href={gameHref(g)}
      className="block rounded-lg border border-line bg-surface px-3 py-2.5 transition hover:bg-surface-2"
    >
      <div className="grid grid-cols-1 gap-1">
        <TeamRow code={g.away_team_code} name={g.away_team_name} score={g.away_score} win={awayWin} />
        <TeamRow code={g.home_team_code} name={g.home_team_name} score={g.home_score} win={homeWin} />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[11px] text-faint">
        <span className="truncate">{g.venue ?? "—"}</span>
        <span className="shrink-0 text-accent">賽後復盤 →</span>
      </div>
    </Link>
  );
}

// 下一批賽事：對戰 + 賽前卡（點機率＋1 主訊號），可進入賽事頁。
function NextGame({ g, trainedThrough }: { g: DailyGame; trainedThrough: number | null }) {
  const model = resolvePregameFromDaily(g.pregame, trainedThrough);
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2.5">
      <Link href={gameHref(g)} className="block transition hover:opacity-80">
        <div className="grid grid-cols-1 gap-1">
          <TeamRow code={g.away_team_code} name={g.away_team_name} score={null} win={false} />
          <TeamRow code={g.home_team_code} name={g.home_team_name} score={null} win={false} />
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-faint">
          <span className="truncate">{g.venue ?? "—"}</span>
          <span className="shrink-0 text-accent">賽事詳情 →</span>
        </div>
      </Link>
      <div className="mt-2">
        <PregameCard model={model} homeName={g.home_team_name} />
      </div>
    </div>
  );
}

export default function DailyHub({ summary }: { summary: DailySummary }) {
  const { latest_game_day, next_slate, freshness, availability } = summary;
  const trainedThrough = availability.pregame_model.trained_through;
  const refresh = refreshCopy(freshness.last_refresh.status);
  const ageText = refreshAgeText(freshness.last_refresh.hours_ago);

  return (
    <section className="space-y-4">
      {/* 1. 最近比賽日 */}
      <Card padding="p-4">
        <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
          <Eyebrow className="text-xs font-bold text-ink">
            最近比賽日{latest_game_day ? ` · ${shortDate(latest_game_day.game_date)}` : ""}
          </Eyebrow>
          <Link href="/games" className="text-xs text-accent hover:underline">
            完整賽況 →
          </Link>
        </div>
        {latest_game_day && latest_game_day.games.length > 0 ? (
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {latest_game_day.games.map((g) => (
              <CompletedGame key={`${g.kind_code}-${g.game_sno}`} g={g} />
            ))}
          </div>
        ) : (
          <EmptyState className="py-5">
            {availability.results.status === "not_started"
              ? "本季尚未有完成的比賽"
              : availability.results.status === "source_missing"
                ? "查無賽程資料"
                : "目前沒有可顯示的最近賽果"}
          </EmptyState>
        )}
      </Card>

      {/* 2. 資料 freshness（維護者 fail-fast 安全網；各 status 文案分立） */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-surface-2 px-3 py-2 text-xs">
        <span className="text-muted">
          資料更新至{" "}
          <span className="font-medium text-ink">{shortDate(freshness.last_completed_game_date)}</span>
        </span>
        <StatusBadge tone={refresh.tone}>{refresh.label}</StatusBadge>
        {ageText && <span className="text-faint">刷新於 {ageText}</span>}
      </div>

      {/* 3. 下一批賽事 */}
      <Card padding="p-4">
        <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
          <Eyebrow className="text-xs font-bold text-ink">
            下一批賽事
            {next_slate ? ` · ${shortDate(next_slate.game_date)}` : ""}
          </Eyebrow>
          {next_slate && (
            <span className="text-xs text-muted">{slateDistanceText(next_slate.days_from_as_of)}</span>
          )}
        </div>
        {next_slate && next_slate.games.length > 0 ? (
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {next_slate.games.map((g) => (
              <NextGame key={`${g.kind_code}-${g.game_sno}`} g={g} trainedThrough={trainedThrough} />
            ))}
          </div>
        ) : (
          <EmptyState className="py-5">
            {availability.schedule.status === "season_complete"
              ? "本季賽程已全部結束"
              : availability.schedule.status === "source_missing"
                ? "查無賽程資料"
                : "目前沒有已排定的下一批賽事"}
          </EmptyState>
        )}
      </Card>
    </section>
  );
}
