import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, Eyebrow, TeamLogo, EmptyState } from "@/components/ui";
import { api } from "@/lib/api";
import { teamPageCode } from "@/lib/teams";

// 首頁＝網站門面 hub（非戰績頁；戰績已搬 /standings）。
// v1：slim 定位 hero ＋ 三張關鍵訊息卡（今日賽事／戰績領先／賽事預測），各卡為
// 「指路牌」——1 個核心數字＋1 句結論＋連向該頁，完整內容留各頁（避免與 /standings 重複）。
// 完整版（更多卡＋更豐富摘要）待 UX-6〜9 各頁換裝、資料形態穩定後再收尾。

export const metadata = {
  title: "CPBL 分析 | 中華職棒數據視覺化",
  description: "非官方中華職棒 [CPBL] 數據網站——戰績、進階數據、成績與賽事預測，用視覺化把數字講清楚。",
};

const pad = (n: number) => String(n).padStart(2, "0");
const pct = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0/, ""));

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = await searchParams;
  // 舊書籤 /?seg=&view=&kind=&year= 指向戰績 → 保留參數轉址到新位址。
  if (sp.seg || sp.view || sp.kind || sp.year) {
    const qs = new URLSearchParams(
      Object.entries(sp).filter(([, v]) => v != null) as [string, string][],
    ).toString();
    redirect(`/standings${qs ? `?${qs}` : ""}`);
  }

  // 各卡獨立降級：單一端點失敗不整頁 500（landing 誠實三態）。
  const [calR, standR, mueR] = await Promise.allSettled([
    api.gamesCalendar(),
    api.officialStandings(0),
    api.outcomeMatchups(3),
  ]);

  // 今日賽事：優先今天，否則退回「最近有比賽的一天」。
  const cal = calR.status === "fulfilled" ? calR.value.items : [];
  const now = new Date();
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const days = [...new Set(cal.map((g) => g.game_date))].sort();
  const matchday = days.includes(today)
    ? today
    : [...days].reverse().find((d) => d <= today) ?? days[days.length - 1];
  const dayGames = cal.filter((g) => g.game_date === matchday).slice(0, 4);
  const dayLabel = matchday === today ? "今日賽事" : `近期賽事 · ${matchday?.slice(5) ?? ""}`;

  // 戰績領先：龍頭 + 對第二名勝差（teaser，不含半季形勢面板——那是 /standings 主角）。
  const stand = standR.status === "fulfilled" ? standR.value : null;
  const leader = stand?.items?.[0] ?? null;
  const gbToSecond = stand?.items?.[1]?.gb ?? null;
  const half = stand?.half ?? null;

  // 賽事預測：即時 fit 的最近一場主隊勝率（誠實：連向可自選特徵的探索器）。
  const matchups = mueR.status === "fulfilled" ? mueR.value.items : [];
  const topMatch = matchups[0] ?? null;

  return (
    <div className="space-y-8">
      {/* slim 定位 hero */}
      <header className="rounded-xl border border-line bg-surface-2 px-6 py-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
          用視覺化把中職數據講清楚
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          非官方中華職棒 [CPBL] 數據網站——戰績、官方進階數據、逐球追蹤，以及成績預測
          [projection] 與賽事預測 [outcome]。目標是把散落的數字整理成一眼看懂的圖表。
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-sm">
          <Link href="/standings" className="rounded-full bg-ink px-3.5 py-1.5 font-medium text-paper transition hover:opacity-90">
            本季戰績
          </Link>
          <Link href="/games" className="rounded-full bg-surface px-3.5 py-1.5 font-medium text-ink border border-line transition hover:bg-surface-2">
            賽況
          </Link>
          <Link href="/predict" className="rounded-full bg-surface px-3.5 py-1.5 font-medium text-ink border border-line transition hover:bg-surface-2">
            賽事預測
          </Link>
        </div>
      </header>

      {/* 關鍵訊息卡 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {/* 今日賽事 */}
        <Card className="flex flex-col">
          <div className="mb-2 flex items-center justify-between">
            <Eyebrow>{dayLabel}</Eyebrow>
            <Link href="/games" className="text-xs text-accent hover:underline">看賽況 →</Link>
          </div>
          {dayGames.length === 0 ? (
            <EmptyState className="py-6">目前無排定賽事</EmptyState>
          ) : (
            <ul className="flex-1 space-y-2">
              {dayGames.map((g) => {
                const done = g.away_score + g.home_score > 0;
                const awayWin = done && g.away_score > g.home_score;
                const homeWin = done && g.home_score > g.away_score;
                return (
                  <li key={g.game_sno} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-1.5">
                      <TeamLogo code={g.away_team_code} name={g.away_team_name} size={18} decorative />
                      <span className={awayWin ? "font-semibold text-ink" : "text-muted"}>{g.away_team_name}</span>
                    </span>
                    <span className="mx-2 font-mono tabular-nums text-xs text-faint">
                      {done ? (
                        <span className="text-ink">
                          <span className={awayWin ? "font-bold text-accent" : ""}>{g.away_score}</span>
                          {" - "}
                          <span className={homeWin ? "font-bold text-accent" : ""}>{g.home_score}</span>
                        </span>
                      ) : (
                        g.delay_kind ?? g.game_time ?? "未開打"
                      )}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className={homeWin ? "font-semibold text-ink" : "text-muted"}>{g.home_team_name}</span>
                      <TeamLogo code={g.home_team_code} name={g.home_team_name} size={18} decorative />
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        {/* 戰績領先（teaser） */}
        <Card className="flex flex-col">
          <div className="mb-2 flex items-center justify-between">
            <Eyebrow>戰績領先</Eyebrow>
            <Link href="/standings" className="text-xs text-accent hover:underline">完整戰績 →</Link>
          </div>
          {!leader ? (
            <EmptyState className="py-6">尚無戰績資料</EmptyState>
          ) : (
            <div className="flex flex-1 flex-col justify-center">
              <Link href={`/teams/${teamPageCode(leader.team_code)}`} className="flex items-center gap-3 group">
                <TeamLogo code={leader.team_code} name={leader.team_name} size={40} decorative />
                <div>
                  <div className="font-bold text-ink group-hover:text-accent">{leader.team_name}</div>
                  <div className="text-xs text-muted">{leader.w}-{leader.t}-{leader.l}</div>
                </div>
                <div className="ml-auto text-right">
                  <div className="font-mono text-2xl font-bold tabular-nums text-ink">{pct(leader.win_pct)}</div>
                  <div className="text-[11px] text-faint">勝率</div>
                </div>
              </Link>
              <p className="mt-3 text-xs text-muted">
                {gbToSecond && gbToSecond > 0
                  ? `領先第二名 ${gbToSecond} 場`
                  : "與第二名同勝差"}
                {half?.champion_code ? " · 本半季已封王 👑" : ""}
              </p>
            </div>
          )}
        </Card>

        {/* 賽事預測（teaser） */}
        <Card className="flex flex-col">
          <div className="mb-2 flex items-center justify-between">
            <Eyebrow>賽事預測</Eyebrow>
            <Link href="/predict" className="text-xs text-accent hover:underline">自選特徵探索 →</Link>
          </div>
          {!topMatch ? (
            <EmptyState className="py-6">近期無排定賽事</EmptyState>
          ) : (
            <div className="flex flex-1 flex-col justify-center">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5">
                  <TeamLogo code={topMatch.away.code} name={topMatch.away.name} size={18} decorative />
                  <span className="text-muted">{topMatch.away.name}</span>
                </span>
                <span className="text-[11px] text-faint">@</span>
                <span className="flex items-center gap-1.5">
                  <span className="text-ink">{topMatch.home.name}</span>
                  <TeamLogo code={topMatch.home.code} name={topMatch.home.name} size={18} decorative />
                </span>
              </div>
              <div className="mt-3 text-center">
                <div className="font-mono text-2xl font-bold tabular-nums text-accent">
                  {Math.round(topMatch.home_win_prob * 100)}%
                </div>
                <div className="text-[11px] text-faint">主隊 {topMatch.home.name} 勝率</div>
              </div>
              <p className="mt-3 text-[11px] text-faint">
                即時 fit 定向特徵子集；單場勝負天花板約 60%，重點在透明而非擊敗賭盤。
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
