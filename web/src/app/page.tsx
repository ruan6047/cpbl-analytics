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
  const [
    calR,
    standR,
    mueR,
    opsR,
    avgR,
    hrR,
    rbiR,
    eraR,
    whipR,
    soR,
    svR,
  ] = await Promise.allSettled([
    api.gamesCalendar(),
    api.officialStandings(0),
    api.outcomeMatchups(3),
    api.battingLeaders("ops", { limit: 5, minPa: 80 }),
    api.battingLeaders("avg", { limit: 5, minPa: 80 }),
    api.battingLeaders("hr", { limit: 5, minPa: 0 }),
    api.battingLeaders("rbi", { limit: 5, minPa: 0 }),
    api.pitchingLeaders("era", { limit: 5, minIp: 25 }),
    api.pitchingLeaders("whip", { limit: 5, minIp: 25 }),
    api.pitchingLeaders("so", { limit: 5, minIp: 0 }),
    api.pitchingLeaders("sv", { limit: 5, minIp: 0 }),
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

  // 戰績與預測
  const standings = standR.status === "fulfilled" ? standR.value.items : [];
  const matchups = mueR.status === "fulfilled" ? mueR.value.items : [];
  const topMatch = matchups[0] ?? null;

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
    ops: getItems(opsR),
    avg: getItems(avgR),
    hr: getItems(hrR),
    rbi: getItems(rbiR),
  };

  const pitching = {
    era: getItems(eraR),
    whip: getItems(whipR),
    so: getItems(soR),
    sv: getItems(svR),
  };

  return (
    <div className="space-y-8">
      {/* Hero section */}
      <header className="relative overflow-hidden rounded-xl border border-line bg-surface-2 px-6 py-10 text-center sm:px-12">
        <div className="relative z-10 mx-auto max-w-2xl space-y-4">
          <h1 className="text-3xl font-extrabold tracking-tight text-ink sm:text-4xl md:text-5xl">
            用視覺化把中職數據講清楚
          </h1>
          <p className="mx-auto max-w-lg text-sm text-muted sm:text-base">
            非官方中華職棒 [CPBL] 數據視覺化網站——提供當季戰績、官方進階數據、
            逐球追蹤，以及基於機器學習的賽事預測。
          </p>
          <div className="pt-2">
            <PlayerSearch />
          </div>
          <div className="flex flex-wrap justify-center gap-2 pt-2 text-xs sm:text-sm">
            <Link
              href="/standings"
              className="rounded-full bg-ink px-4 py-2 font-medium text-paper transition hover:opacity-90"
            >
              本季戰績
            </Link>
            <Link
              href="/games"
              className="rounded-full bg-surface px-4 py-2 font-medium text-ink border border-line transition hover:bg-surface-2"
            >
              賽況與 Box
            </Link>
            <Link
              href="/predict"
              className="rounded-full bg-surface px-4 py-2 font-medium text-ink border border-line transition hover:bg-surface-2"
            >
              賽事預測探索
            </Link>
          </div>
        </div>
      </header>

      {/* 雙欄主版塊 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左側大欄 - 聯盟領先榜 */}
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

          {/* 賽事預測 (Teaser) */}
          <Card className="flex flex-col">
            <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
              <Eyebrow className="text-xs font-bold text-ink">賽事勝率預測</Eyebrow>
              <Link href="/predict" className="text-xs text-accent hover:underline">
                特徵探索 →
              </Link>
            </div>
            {!topMatch ? (
              <EmptyState className="py-6">近期無排定賽事</EmptyState>
            ) : (
              <div className="flex flex-1 flex-col justify-center space-y-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <TeamLogo
                      code={topMatch.away.code}
                      name={topMatch.away.name}
                      size={18}
                      decorative
                    />
                    <span className="font-medium text-ink">{topMatch.away.name}</span>
                  </span>
                  <span className="text-xs text-faint">@</span>
                  <span className="flex items-center gap-2">
                    <span className="font-medium text-ink">{topMatch.home.name}</span>
                    <TeamLogo
                      code={topMatch.home.code}
                      name={topMatch.home.name}
                      size={18}
                      decorative
                    />
                  </span>
                </div>

                {/* 雙色進度條展示勝率 */}
                <div className="space-y-1.5">
                  <div className="flex justify-between font-mono text-xs font-semibold">
                    <span className="text-muted">
                      {topMatch.away.name} {100 - Math.round(topMatch.home_win_prob * 100)}%
                    </span>
                    <span className="text-accent">
                      {topMatch.home.name} {Math.round(topMatch.home_win_prob * 100)}%
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-surface-3 flex overflow-hidden border border-line/20">
                    <div
                      className="h-full bg-muted/30 transition-all duration-500"
                      style={{ width: `${100 - Math.round(topMatch.home_win_prob * 100)}%` }}
                    />
                    <div
                      className="h-full bg-accent transition-all duration-500"
                      style={{ width: `${Math.round(topMatch.home_win_prob * 100)}%` }}
                    />
                  </div>
                </div>

                <p className="text-[10px] leading-relaxed text-faint">
                  預測基於機器學習模型（已排除資訊洩漏），即時適配當前勝率、近況與先發投手等特徵。
                  單場勝負天花板約 60%，預測結果僅供學術與球迷互動探索。
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
