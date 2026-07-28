import Link from "next/link";
import { Card, EmptyState, TeamLogo } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { PregameCard } from "@/components/pregame-card";
import { resolvePregameCard, type PregameResponse } from "@/lib/pregame-card";
import { shortDate } from "@/lib/daily-summary";
import type { CalendarGame, TeamHotBattersResponse } from "@/lib/api";

// 近日焦點的擴充內容（UX-TEAM-FOCUS2）：
//   1. 下一場對戰卡／先發預告——複用既有 <PregameCard/>（不自造平行的勝率元件），
//      整份 pregame response 交給 resolvePregameCard（單一來源守衛，見
//      pregame-single-source.test.ts）；先發未公布時明示「未公布」，不留白也不誤植上一場先發。
//   2. 近期球員熱區（v1 只做打者；口徑見後端 cpbl.api.team_focus docstring，
//      需求方 2026-07-28 定案，不得自行更動）。
//
// 「近日焦點」語意＝當季近況，不隨 ?year= 變動（本元件的資料一律來自當季 fetch，
// page.tsx 呼叫時不傳所選年度）。

const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));

function NextGameCard({ upcoming, pregame }: {
  upcoming: CalendarGame | undefined;
  pregame: PregameResponse | null;
}) {
  const model = upcoming
    ? resolvePregameCard({
        response: pregame,
        fetchFailed: pregame == null,
        game: { season: upcoming.year, game_sno: upcoming.game_sno, kind_code: upcoming.kind_code },
      })
    : null;

  return (
    <Card padding="p-4">
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
        <span className="text-sm font-bold text-ink">下一場</span>
        {upcoming && (
          <span className="text-xs text-faint">
            {shortDate(upcoming.game_date)}{upcoming.venue ? `・${upcoming.venue}` : ""}
          </span>
        )}
      </div>
      {!upcoming ? (
        <EmptyState className="py-3">本季近期無排定賽事。</EmptyState>
      ) : (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <TeamLogo code={upcoming.away_team_code} name={upcoming.away_team_name} size={22} />
              <span className="text-sm text-ink">{upcoming.away_team_name}</span>
              <span className="ml-auto text-xs text-muted">先發(客) {upcoming.away_starter ?? "未公布"}</span>
            </div>
            <div className="flex items-center gap-2">
              <TeamLogo code={upcoming.home_team_code} name={upcoming.home_team_name} size={22} />
              <span className="text-sm text-ink">{upcoming.home_team_name}</span>
              <span className="ml-auto text-xs text-muted">先發(主) {upcoming.home_starter ?? "未公布"}</span>
            </div>
          </div>
          {model && <PregameCard model={model} homeName={upcoming.home_team_name} />}
        </div>
      )}
    </Card>
  );
}

function HotBattersCard({ data }: { data: TeamHotBattersResponse }) {
  const columns: Column<TeamHotBattersResponse["items"][number]>[] = [
    { header: "球員", cell: (b) => <Link href={`/players/${b.player_id}`} className="text-ink hover:text-accent">{b.name}</Link>, className: "font-sans", nowrap: true },
    { header: "打席", cell: (b) => b.pa, align: "right" },
    { header: "OPS", cell: (b) => f3(b.ops), align: "right", className: "text-accent" },
    { header: "現行連續安打", cell: (b) => (b.streak > 0 ? `${b.streak} 場` : "—"), align: "right" },
  ];

  return (
    <Card padding="p-4">
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
        <span className="text-sm font-bold text-ink">近期球員熱區</span>
        {data.available && data.window && (
          <span className="text-xs text-faint">
            {shortDate(data.window.start)}–{shortDate(data.window.end)}・打席≥10
          </span>
        )}
      </div>
      {!data.available ? (
        <EmptyState className="py-3">本季尚無完賽，暫無熱區資料。</EmptyState>
      ) : data.items.length === 0 ? (
        <EmptyState className="py-3">窗口內無打者累積達 10 打席，暫不列榜。</EmptyState>
      ) : (
        <DataTable columns={columns} rows={data.items} rowKey={(b) => b.player_id} dense bare />
      )}
    </Card>
  );
}

export function TeamFocusSection({ upcoming, pregame, hotBatters }: {
  upcoming: CalendarGame | undefined;
  pregame: PregameResponse | null;
  hotBatters: TeamHotBattersResponse;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <NextGameCard upcoming={upcoming} pregame={pregame} />
      <HotBattersCard data={hotBatters} />
    </div>
  );
}
