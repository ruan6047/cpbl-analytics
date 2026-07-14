import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, Eyebrow, TeamLogo, EmptyState } from "@/components/ui";
import { api } from "@/lib/api";
import PlayerSearch from "@/components/player-search";
import LeagueLeaders from "@/components/league-leaders";
import MiniStandings from "@/components/mini-standings";

export const metadata = {
  title: "CPBL 分析 | 中華職棒數據視覺化",
  description: "非官方中華職棒 [CPBL] 數據視覺化網站——提供當季戰績、官方進階數據、逐球追蹤，以及基於機器學習的賽事預測。",
};

const pad = (n: number) => String(n).padStart(2, "0");

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = await searchParams;
  if (sp.seg || sp.view || sp.kind || sp.year) {
    const qs = new URLSearchParams(
      Object.entries(sp).filter(([, v]) => v != null) as [string, string][],
    ).toString();
    redirect(`/standings${qs ? `?${qs}` : ""}`);
  }

  // 併發獲取首頁所有需要的數據，即使部分失敗也能優雅降級不 500
  // 改採中職年度獎項項目：打者 (AVG, H, HR, RBI, SB) + 投手 (ERA, W, HLD, SV, SO)
  // 移除賽事預測 API outcomeMatchups
  const [
    calR,
    standR,
    avgR,
    hR,
    hrR,
    rbiR,
    sbR,
    eraR,
    wR,
    hldR,
    svR,
    soR,
  ] = await Promise.allSettled([
    api.gamesCalendar(),
    api.officialStandings(0),
    api.battingLeaders("avg", { limit: 5, minPa: 80 }),
    api.battingLeaders("h", { limit: 5, minPa: 0 }),
    api.battingLeaders("hr", { limit: 5, minPa: 0 }),
    api.battingLeaders("rbi", { limit: 5, minPa: 0 }),
    api.battingLeaders("sb", { limit: 5, minPa: 0 }),
    api.pitchingLeaders("era", { limit: 5, minIp: 25 }),
    api.pitchingLeaders("w", { limit: 5, minIp: 0 }),
    api.pitchingLeaders("hld", { limit: 5, minIp: 0 }),
    api.pitchingLeaders("sv", { limit: 5, minIp: 0 }),
    api.pitchingLeaders("so", { limit: 5, minIp: 0 }),
  ]);

  // 今日與近期賽事計算
  const cal = calR.status === "fulfilled" ? calR.value.items : [];
  const now = new Date();
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const days = [...new Set(cal.map((g) => g.game_date))].sort();
  const matchday = days.includes(today)
    ? today
    : [...days].reverse().find((d) => d <= today) ?? days[days.length - 1];
  const dayGames = cal.filter((g) => g.game_date === matchday).slice(0, 4);
  const dayLabel = matchday === today ? "今日賽事" : `近期賽事 · ${matchday?.slice(5) ?? ""}`;

  // 戰績數據
  const standings = standR.status === "fulfilled" ? standR.value.items : [];

  // 領先榜數據轉換
  const getItems = (r: PromiseSettledResult<any>) =>
    r.status === "fulfilled"
      ? (r.value.items || []).map((x: any) => ({
          player_id: x.player_id,
          name: x.name,
          team: x.team,
          val: x[r.value.sort] ?? 0,
        }))
      : [];

  const batting = {
    avg: getItems(avgR),
    h: getItems(hR),
    hr: getItems(hrR),
    rbi: getItems(rbiR),
    sb: getItems(sbR),
  };

  const pitching = {
    era: getItems(eraR),
    w: getItems(wR),
    hld: getItems(hldR),
    sv: getItems(svR),
    so: getItems(soR),
  };

  return (
    <div className="space-y-8">
      {/* Hero section */}
      <header className="relative overflow-hidden rounded-xl border border-line bg-surface-2 px-6 py-8 text-center sm:px-12">
        <div className="relative z-10 mx-auto max-w-2xl space-y-3.5">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl md:text-4xl">
            非官方中華職棒 [CPBL] 數據視覺化網站
          </h1>
          <p className="mx-auto max-w-lg text-xs text-muted sm:text-sm">
            基於官方數據製作提供讓視覺化把中職數據講清楚
          </p>
          <div className="pt-1.5">
            <PlayerSearch />
          </div>
          <div className="flex flex-wrap justify-center gap-2 pt-1 text-xs sm:text-sm">
            <Link
              href="/standings"
              className="rounded-full bg-ink px-4 py-1.5 font-medium text-paper transition hover:opacity-90"
            >
              本季戰績
            </Link>
            <Link
              href="/games"
              className="rounded-full bg-surface px-4 py-1.5 font-medium text-ink border border-line transition hover:bg-surface-2"
            >
              賽況與 Box
            </Link>
            <Link
              href="/predict"
              className="rounded-full bg-surface px-4 py-1.5 font-medium text-ink border border-line transition hover:bg-surface-2"
            >
              賽事預測探索
            </Link>
          </div>
        </div>
      </header>

      {/* 雙欄主版塊 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左側大欄 - 聯盟領先榜 (中職年度獎項指標) */}
        <div className="lg:col-span-2">
          <LeagueLeaders batting={batting} pitching={pitching} />
        </div>

        {/* 右側小欄 */}
        <div className="space-y-6 lg:col-span-1">
          {/* 戰績微縮表 */}
          {standings.length > 0 && <MiniStandings standings={standings} />}

          {/* 今日/近期賽事 */}
          <Card className="flex flex-col">
            <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
              <Eyebrow className="text-xs font-bold text-ink">{dayLabel}</Eyebrow>
              <Link href="/games" className="text-xs text-accent hover:underline">
                完整賽況 →
              </Link>
            </div>
            {dayGames.length === 0 ? (
              <EmptyState className="py-6">目前無排定賽事</EmptyState>
            ) : (
              <ul className="flex-1 space-y-3">
                {dayGames.map((g) => {
                  const done = g.away_score + g.home_score > 0;
                  const awayWin = done && g.away_score > g.home_score;
                  const homeWin = done && g.home_score > g.away_score;
                  return (
                    <li
                      key={g.game_sno}
                      className="flex items-center justify-between text-sm py-1"
                    >
                      <span className="flex items-center gap-2">
                        <TeamLogo
                          code={g.away_team_code}
                          name={g.away_team_name}
                          size={18}
                          decorative
                        />
                        <span className={awayWin ? "font-semibold text-ink" : "text-muted"}>
                          {g.away_team_name}
                        </span>
                      </span>
                      <span className="mx-2 font-mono tabular-nums text-xs">
                        {done ? (
                          <span className="text-ink bg-surface-3 px-2 py-0.5 rounded font-bold">
                            <span className={awayWin ? "text-accent" : ""}>
                              {g.away_score}
                            </span>
                            {" - "}
                            <span className={homeWin ? "text-accent" : ""}>
                              {g.home_score}
                            </span>
                          </span>
                        ) : (
                          <span className="text-faint">{g.delay_kind ?? g.game_time ?? "未開打"}</span>
                        )}
                      </span>
                      <span className="flex items-center gap-2">
                        <span className={homeWin ? "font-semibold text-ink" : "text-muted"}>
                          {g.home_team_name}
                        </span>
                        <TeamLogo
                          code={g.home_team_code}
                          name={g.home_team_name}
                          size={18}
                          decorative
                        />
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
