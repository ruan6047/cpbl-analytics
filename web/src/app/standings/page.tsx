import Link from "next/link";
import { StatAbbr, TeamBadge, TeamLogo, divBg, prColor } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { StandingsTrend } from "@/components/standings-trend";
import { YearSelect } from "@/components/year-select";
import { api } from "@/lib/api";
import type { OfficialStanding, OfficialStandingsResponse, SpecialRecord, WL } from "@/lib/api";
import { teamPageCode, teamShort } from "@/lib/teams";

export const dynamic = "force-dynamic";

const SEGS = [
  { v: 0, label: "全年" },
  { v: 1, label: "上半季" },
  { v: 2, label: "下半季" },
  { v: 3, label: "季後賽" },
];

function displayTeamName(name: string) {
  return name === "統一7-ELEVEn獅" ? "統一獅" : name;
}

// 球隊徽章連到各隊獨立頁；改名/轉賣的歷史隊連到現役 franchise 頁；已解散隊不連
function LinkedTeam({ code, name }: { code: string; name: string }) {
  const tc = teamPageCode(code);
  const shown = displayTeamName(name);
  if (!tc) return <TeamBadge code={code} name={shown} />;
  return (
    <Link href={`/teams/${tc}`} className="hover:underline">
      <TeamBadge code={code} name={shown} />
    </Link>
  );
}

// W-L 配對：依勝率上色（>.5 藍、<.5 紅），方便跨隊一覽
function WLCell({ p }: { p?: WL }) {
  if (!p) return <span className="text-faint">—</span>;
  const [w, l] = p;
  const tot = w + l;
  if (tot === 0) return <span className="text-faint">0-0</span>;
  const pct = w / tot;
  const cls = pct > 0.5 ? "text-up" : pct < 0.5 ? "text-down" : "text-muted";
  return <span className={cls}>{w}-{l}</span>;
}

// 正-負 數對（如 再見勝-被再見、橫掃-被橫掃、最大連勝-連敗）：好值綠、壞值紅，中性灰。
function NumPairCell({ good, bad }: { good: number; bad: number }) {
  if (!good && !bad) return <span className="text-faint">0-0</span>;
  return (
    <span className="tabular-nums">
      <span className={good > bad ? "text-up" : "text-muted"}>{good}</span>
      <span className="text-faint">-</span>
      <span className={bad > good ? "text-down" : "text-muted"}>{bad}</span>
    </span>
  );
}

// 特殊戰績跨隊對照（UX-SPECIAL-COMPARE1）：把高訊號隊級特殊戰績收成單一精簡表，
// 補回 UX-STANDINGS-FOCUS1 移出後的跨隊比較（不重現舊 8 張密表；細項留球隊頁）。
// 沿用 WLCell/NumPairCell 色階 → 「哪隊最會逆轉／再見」5 秒可讀。
function SpecialCompareTable({ rows, sp }: { rows: OfficialStanding[]; sp: Map<string, SpecialRecord> }) {
  const columns: Column<OfficialStanding>[] = [
    { header: "球隊", cell: (t) => <LinkedTeam code={t.team_code} name={t.team_name} />, nowrap: true, className: "font-sans", sticky: true },
    { header: <span title="曾落後仍逆轉獲勝 - 曾領先卻被逆轉">逆轉 勝-被</span>, cell: (t) => <WLCell p={sp.get(t.team_code)?.comeback} />, nowrap: true },
    { header: <span title="最終局下半超前致勝 - 客場吞再見敗">再見 勝-被</span>, cell: (t) => { const s = sp.get(t.team_code); return <NumPairCell good={s?.walkoff ?? 0} bad={s?.walked_off ?? 0} />; }, nowrap: true },
    { header: <span title="最終分差 1 分的勝 - 敗">一分差</span>, cell: (t) => <WLCell p={sp.get(t.team_code)?.one_run} />, nowrap: true },
    { header: <span title="完封對手 - 被完封">完封 勝-被</span>, cell: (t) => <WLCell p={sp.get(t.team_code)?.shutout} />, nowrap: true },
    { header: <span title="本季最長連勝 - 最長連敗場數">最長 連勝-連敗</span>, cell: (t) => { const s = sp.get(t.team_code); return <NumPairCell good={s?.max_win_streak ?? 0} bad={s?.max_lose_streak ?? 0} />; }, nowrap: true },
    { header: <span title="三連戰橫掃(3-0) - 被橫掃(0-3)">橫掃 勝-被</span>, cell: (t) => { const s = sp.get(t.team_code); return <NumPairCell good={s?.sweeps ?? 0} bad={s?.swept ?? 0} />; }, nowrap: true },
  ];
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink">
        特殊戰績對照
        <span className="ml-2 text-[11px] font-normal text-faint">高訊號隊級戰績跨隊比較；更多細項見各隊球隊頁</span>
      </h3>
      <DataTable columns={columns} rows={rows} rowKey={(t) => t.team_code} dense />
    </section>
  );
}

function MonthsTable({ rows, sp }: { rows: OfficialStanding[]; sp: Map<string, SpecialRecord> }) {
  const monthSet = new Set<number>();
  sp.forEach((s) => Object.keys(s.months).forEach((m) => monthSet.add(Number(m))));
  const months = [...monthSet].sort((a, b) => a - b);
  if (months.length === 0) return null;
  const columns: Column<OfficialStanding>[] = [
    { header: "球隊", cell: (t) => <LinkedTeam code={t.team_code} name={t.team_name} />, nowrap: true, className: "font-sans" },
    ...months.map((m) => ({
      header: `${m} 月`,
      cell: (t: OfficialStanding) => <WLCell p={sp.get(t.team_code)?.months[String(m)]} />,
      nowrap: true,
    })),
  ];
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink">月份趨勢</h3>
      <DataTable columns={columns} rows={rows} rowKey={(t) => t.team_code} dense />
    </section>
  );
}

const LEVELS = [
  { v: "A", label: "一軍" },
  { v: "D", label: "二軍" },
];


// H2H 「勝-和-敗」字串 → 勝率底色（無對戰不上色）
function h2hBg(rec: string | null | undefined): React.CSSProperties | undefined {
  if (!rec) return undefined;
  const [w, , l] = rec.split("-").map(Number);
  if (!Number.isFinite(w) || !Number.isFinite(l) || w + l === 0) return undefined;
  return { background: prColor((w / (w + l)) * 100).replace("rgb", "rgba").replace(")", ",0.3)") };
}

// 連勝/連敗標籤（資料格式 '勝3'/'敗3'）：綠連勝、紅連敗。取代獨立欄位，貼在隊名旁。
function StreakBadge({ streak }: { streak: string | null }) {
  if (!streak) return null;
  const win = streak.startsWith("勝");
  const lose = streak.startsWith("敗");
  const cls = win ? "bg-up/15 text-up" : lose ? "bg-down/15 text-down" : "bg-surface-2 text-muted";
  return <span className={`ml-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold tabular-nums ${cls}`}>{streak}</span>;
}

// 近十場（資料格式 'W-T-L'，如 '3-0-7'）：W-L 文字 + 勝率迷你條（數字不裸列）。
function L10({ s }: { s: string | null }) {
  if (!s) return <span className="text-faint">—</span>;
  const [w, , l] = s.split("-").map(Number);
  if (!Number.isFinite(w) || !Number.isFinite(l)) return <span className="text-faint">—</span>;
  const tot = w + l;
  const wpct = tot ? (w / tot) * 100 : 0;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="tabular-nums text-muted">{w}-{l}</span>
      <span className="inline-block h-1.5 w-10 overflow-hidden rounded-full bg-down/30" aria-hidden>
        <span className="block h-full rounded-full bg-up" style={{ width: `${wpct}%` }} />
      </span>
    </span>
  );
}

// 戰績主表隊名格（手機用縮寫避免撐爆版面；桌機全名）＋連結各隊頁
function TeamNameCell({ code, name }: { code: string; name: string }) {
  const tc = teamPageCode(code);
  const shown = displayTeamName(name);
  const inner = (
    <span className="inline-flex items-center gap-1.5">
      <TeamLogo code={code} name={name} size={20} decorative />
      <span className="hidden font-medium lg:inline">{shown}</span>
      <span className="font-medium lg:hidden">{teamShort(code) || shown}</span>
    </span>
  );
  return tc ? <Link href={`/teams/${tc}`} className="hover:underline" aria-label={shown}>{inner}</Link> : inner;
}

// 勝差標籤（取代獨立欄）：領先隊不顯示；落後隊以中性 chip 呈現
function GbTag({ gb }: { gb: number | null }) {
  if (!gb) return null;
  return <span className="ml-1.5 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted" title="勝差 Games Behind">-{gb}</span>;
}

// 淘汰指數（魔術數字）是否已「點亮」：官方僅在賽季末段（剩餘場次逼近淘汰指數）才填值。
function elimActive(elim: string | null): boolean {
  if (!elim) return false;
  const s = elim.trim();
  return s !== "" && s !== "-" && s !== "—";
}

// 淘汰指數標籤（取代獨立欄）：官方值為 'E' 代表已淘汰 → 標「E」（紅）；數字則為魔術數字 → 標「M{n}」（琥珀）。
function ElimTag({ elim }: { elim: string | null }) {
  if (!elimActive(elim)) return null;
  const eliminated = elim!.trim().toUpperCase() === "E";
  if (eliminated) {
    return (
      <span
        className="ml-1.5 rounded bg-down/15 px-1.5 py-0.5 text-[10px] font-semibold text-down"
        title="已淘汰：本區間無法取得季後賽資格"
      >
        E
      </span>
    );
  }
  return (
    <span
      className="ml-1.5 rounded bg-amber/15 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-amber"
      title="魔術數字（M）：再拿下幾場即確保晉級"
    >
      M{elim}
    </span>
  );
}

// 戰績細項：主客場（團隊攻守回主戰績表，便於快速判讀）。
function TeamStatsTable({ rows }: { rows: OfficialStanding[] }) {
  const columns: Column<OfficialStanding>[] = [
    { header: "球隊", cell: (t) => <LinkedTeam code={t.team_code} name={t.team_name} />, nowrap: true, className: "font-sans" },
    { header: "主場", cell: (t) => <span className="text-muted">{t.home_record ?? "—"}</span>, nowrap: true },
    { header: "客場", cell: (t) => <span className="text-muted">{t.away_record ?? "—"}</span>, nowrap: true },
  ];
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink">主客場</h3>
      <DataTable columns={columns} rows={rows} rowKey={(t) => t.team_code} dense />
    </section>
  );
}

// 對戰各隊 H2H 矩陣：自主戰績表移出（原本塞在主表使窄螢幕水平爆版），改於進階展開呈現。
// 首欄 sticky，橫向捲動時鎖住隊名。
function H2HTable({ rows }: { rows: OfficialStanding[] }) {
  const columns: Column<OfficialStanding>[] = [
    { header: "球隊", cell: (t) => <LinkedTeam code={t.team_code} name={t.team_name} />, nowrap: true, className: "font-sans", sticky: true },
    ...rows.map((col) => ({
      header: <span className="inline-flex flex-col items-center" title={`對 ${col.team_name}`}><TeamLogo code={col.team_code} name={col.team_name} size={20} decorative /></span>,
      cell: (t: OfficialStanding) => col.team_code === t.team_code ? <span className="text-faint">—</span> : (t.h2h?.[col.team_code] ?? "—"),
      cellStyle: (t: OfficialStanding) => col.team_code === t.team_code ? undefined : h2hBg(t.h2h?.[col.team_code]),
      align: "center" as const,
      nowrap: true,
    })),
  ];
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink">對戰各隊</h3>
      <DataTable columns={columns} rows={rows} rowKey={(t) => t.team_code} dense />
    </section>
  );
}

// ── 季後賽 bracket（淘汰賽專屬圖表；規則見 memory postseason-format-rules / 聯盟規章 60-63）──
type PostGame = {
  game_no: number; date: string | null;
  home_code: string; home_name: string; home_score: number;
  away_code: string; away_name: string; away_score: number;
};
type PostSeries = {
  kind_code: string; kind_name: string;
  team1_code: string; team1_name: string; team1_wins: number;
  team2_code: string; team2_name: string; team2_wins: number;
  games?: PostGame[];
};
// bracket 系列一方：隊伍代碼、種子註記、是否依規則先勝 1 場（讓分）。
type SeriesSide = { code: string | null; seed: string; handicap: boolean };

// 系列計分卡：兩隊為列、逐場小比分為欄（類似計分表的局數位）；勝方該場得分標色；
// 「讓」為規則先勝 1 場、以一欄呈現並計入大比分。games 空（進行中/未打）時退為種子預覽。
function SeriesCard({ title, format, sideA, sideB, games = [], needed, crownWinner, nameOf }: {
  title: string; format: string; sideA: SeriesSide; sideB: SeriesSide;
  games?: PostGame[]; needed: number; crownWinner?: boolean;
  nameOf: (c: string | null) => string;
}) {
  const gameWinner = (g: PostGame) =>
    g.home_score > g.away_score ? g.home_code : g.away_score > g.home_score ? g.away_code : null;
  const runsOf = (g: PostGame, code: string) => (g.home_code === code ? g.home_score : g.away_score);
  const officialWins = (s: SeriesSide) =>
    (s.code ? games.filter((g) => gameWinner(g) === s.code).length : 0) + (s.handicap ? 1 : 0);
  const aWins = officialWins(sideA);
  const bWins = officialWins(sideB);
  const hasGames = games.length > 0;
  const decided = hasGames && Math.max(aWins, bWins) >= needed;
  const winnerCode = decided ? (aWins >= bWins ? sideA.code : sideB.code) : null;
  const anyHandicap = sideA.handicap || sideB.handicap;

  const scoreRow = (s: SeriesSide, wins: number) => {
    const isWin = winnerCode != null && s.code === winnerCode;
    return (
      <tr>
        <td className="py-1 pr-2">
          <div className="flex items-center gap-2">
            {s.code ? (
              <TeamLogo code={s.code} name={nameOf(s.code)} size={20} decorative />
            ) : (
              <span className="h-5 w-5 shrink-0 rounded-full border border-dashed border-line" aria-hidden />
            )}
            <span className="min-w-0">
              <span className="flex items-center gap-1 text-sm font-medium text-ink">
                <span className="truncate">{s.code ? displayTeamName(nameOf(s.code)) : "挑戰賽勝隊"}</span>
                {crownWinner && isWin && <span title="年度總冠軍">🏆</span>}
              </span>
              <span className="block text-[10px] text-faint">{s.seed}</span>
            </span>
          </div>
        </td>
        {anyHandicap && (
          <td className={`px-1 text-center font-mono text-xs tabular-nums ${s.handicap ? "font-bold text-up" : "text-faint"}`}>
            {s.handicap ? 1 : "·"}
          </td>
        )}
        {games.map((g, i) => {
          const won = s.code != null && gameWinner(g) === s.code;
          return (
            <td key={i} className={`px-1 text-center font-mono text-xs tabular-nums ${won ? "font-bold text-up" : "text-faint"}`}>
              {s.code ? runsOf(g, s.code) : "—"}
            </td>
          );
        })}
        <td className={`pl-2.5 text-center font-mono text-sm tabular-nums ${isWin ? "font-bold text-ink" : "text-muted"}`}>
          {hasGames ? wins : "—"}
        </td>
      </tr>
    );
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-ink">{title}</span>
        <span className="text-[10px] font-medium text-faint">{format}</span>
      </div>
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-[10px] text-faint">
            <th />
            {anyHandicap && <th className="px-1 font-medium" title="依規則先勝 1 場">讓</th>}
            {games.map((g) => <th key={g.game_no} className="px-1 font-medium">{g.game_no}</th>)}
            <th className="pl-2.5 font-medium">大比分</th>
          </tr>
        </thead>
        <tbody>
          {scoreRow(sideA, aWins)}
          {scoreRow(sideB, bWins)}
        </tbody>
      </table>
    </div>
  );
}

function PostseasonBracket({ isCurrent, h0, h1, h2, series }: {
  isCurrent: boolean;
  h0: OfficialStandingsResponse | null;
  h1: OfficialStandingsResponse | null;
  h2: OfficialStandingsResponse | null;
  series: PostSeries[];
}) {
  const full = h0?.items ?? [];
  const nameMap = new Map<string, string>();
  for (const t of full) nameMap.set(t.team_code, t.team_name);
  for (const t of h1?.items ?? []) nameMap.set(t.team_code, t.team_name);
  for (const t of h2?.items ?? []) nameMap.set(t.team_code, t.team_name);
  const nameOf = (c: string | null) => (c ? nameMap.get(c) ?? c : "");
  const pct = new Map(full.map((t) => [t.team_code, t.win_pct ?? 0]));

  const h1c = h1?.half?.champion_code ?? h1?.items?.[0]?.team_code ?? null;
  const h2c = h2?.half?.champion_code ?? h2?.items?.[0]?.team_code ?? null;
  const h1Clinched = !!h1?.half?.champion_code;
  const h2Clinched = !!h2?.half?.champion_code;
  const projected = isCurrent || !h1Clinched || !h2Clinched;
  if (!h1c || !h2c || full.length < 3) {
    return <p className="text-sm text-faint">此年度尚無季後賽資料（半季冠軍未產生）。</p>;
  }
  const totalGames = series.reduce((n, s) => n + (s.games?.length ?? 0), 0);
  if (!isCurrent && totalGames === 0) {
    return <p className="text-sm text-faint">此年度無季後賽對戰資料（可能由半季冠軍直接封王，或當年無此賽制）。</p>;
  }
  const sameChamp = h1c === h2c;
  const rankOf = new Map(full.map((t, i) => [t.team_code, i + 1]));
  const seedLabel = (code: string | null): string => {
    if (!code) return "";
    if (sameChamp && code === h1c) return "上下半季雙冠";
    if (code === h1c) return "上半季冠軍";
    if (code === h2c) return "下半季冠軍";
    const r = rankOf.get(code);
    return r ? `全年 #${r}` : "";
  };
  const heading = (
    <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 className="text-lg font-semibold text-ink">季後賽</h2>
      {projected ? (
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-muted">形勢預測 · 未定案</span>
      ) : (
        <span className="text-[11px] text-faint">依實際對戰結果</span>
      )}
    </div>
  );

  // ── 歷史年：依實際存在的系列（E/C）與參賽隊呈現，不用現行規則反推 ──
  // 季後挑戰賽 2022 起才對「不同半季冠軍」實施；更早的不同冠軍年由兩半季冠軍直接打台灣大賽。
  if (series.length > 0) {
    const chal = series.find((s) => s.kind_code === "E");
    const tw = series.find((s) => s.kind_code === "C");
    // 讓一勝由資料反推：勝隊 game 勝場＝需求−1 → 該隊曾先勝 1 場（跨賽制皆準）。
    const build = (s: PostSeries, needed: number): { a: SeriesSide; b: SeriesSide } => {
      const winnerGW = Math.max(s.team1_wins, s.team2_wins);
      const winner = s.team1_wins > s.team2_wins ? s.team1_code : s.team2_wins > s.team1_wins ? s.team2_code : null;
      const handicapCode = winner && winnerGW === needed - 1 ? winner : null;
      const label = (code: string, oppCode: string): string => {
        const inChal = !!chal && (chal.team1_code === code || chal.team2_code === code);
        const bye = s.kind_code === "C" && !!chal && (code === h1c || code === h2c) && !inChal;
        let base: string;
        if (sameChamp && code === h1c) base = "上下半季雙冠";
        else if (code === h1c) base = "上半季冠軍";
        else if (code === h2c) base = "下半季冠軍";
        else {
          const r = rankOf.get(code);
          // 現行制挑戰賽＝半季冠軍 vs 外卡：僅當對手是半季冠軍時才標「外卡」，否則單純以全年名次示之。
          const oppIsChamp = oppCode === h1c || oppCode === h2c;
          base = s.kind_code === "E" && oppIsChamp
            ? (r ? `外卡・全年 #${r}` : "外卡")
            : (r ? `全年 #${r}` : "");
        }
        return bye ? (base ? `${base}・保送` : "保送") : base;
      };
      return {
        a: { code: s.team1_code, seed: label(s.team1_code, s.team2_code), handicap: s.team1_code === handicapCode },
        b: { code: s.team2_code, seed: label(s.team2_code, s.team1_code), handicap: s.team2_code === handicapCode },
      };
    };
    const chalSides = chal ? build(chal, 3) : null;
    const twSides = tw ? build(tw, 4) : null;
    return (
      <section>
        {heading}
        {chal && tw && chalSides && twSides ? (
          <div className="grid items-center gap-4 lg:grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)]">
            <SeriesCard title="季後挑戰賽" format="5 戰 3 勝" sideA={chalSides.a} sideB={chalSides.b} games={chal.games ?? []} needed={3} nameOf={nameOf} />
            <div className="hidden items-center justify-center text-2xl text-faint lg:flex" aria-hidden>→</div>
            <SeriesCard title="台灣大賽" format="7 戰 4 勝" sideA={twSides.a} sideB={twSides.b} games={tw.games ?? []} needed={4} crownWinner nameOf={nameOf} />
          </div>
        ) : (
          <div className="lg:max-w-xl">
            {tw && twSides && <SeriesCard title="台灣大賽" format="7 戰 4 勝" sideA={twSides.a} sideB={twSides.b} games={tw.games ?? []} needed={4} crownWinner nameOf={nameOf} />}
            {chal && !tw && chalSides && <SeriesCard title="季後挑戰賽" format="5 戰 3 勝" sideA={chalSides.a} sideB={chalSides.b} games={chal.games ?? []} needed={3} nameOf={nameOf} />}
          </div>
        )}
        <p className="mt-3 text-[11px] leading-relaxed text-faint">
          {chal
            ? "季後挑戰賽勝隊晉級台灣大賽。"
            : "此年度由上、下半季冠軍直接進行台灣大賽（該賽季無季後挑戰賽）。"}
          {" "}表內數字為各場得分、勝方標色；「讓」欄為依規則先勝 1 場（已計入大比分）。
        </p>
      </section>
    );
  }

  // ── 當季進行中（尚無對戰資料）：依現行制（2022+）預測 bracket 席位 ──
  let byeCode: string, challHomeCode: string | null, challAwayCode: string | null;
  let handicapSlot: "challenge" | "taiwan";
  if (sameChamp) {
    byeCode = h1c;
    const others = full.filter((t) => t.team_code !== byeCode);
    challHomeCode = others[0]?.team_code ?? null;
    challAwayCode = others[1]?.team_code ?? null;
    handicapSlot = "taiwan";
  } else {
    const higherIsH1 = (pct.get(h1c) ?? 0) >= (pct.get(h2c) ?? 0);
    byeCode = higherIsH1 ? h1c : h2c;
    challHomeCode = higherIsH1 ? h2c : h1c;
    challAwayCode = full.find((t) => t.team_code !== h1c && t.team_code !== h2c)?.team_code ?? null;
    handicapSlot = "challenge";
  }
  const sideChallHome: SeriesSide = { code: challHomeCode, seed: seedLabel(challHomeCode), handicap: handicapSlot === "challenge" };
  const sideChallAway: SeriesSide = { code: challAwayCode, seed: challAwayCode ? `外卡・${seedLabel(challAwayCode)}` : "外卡", handicap: false };
  const sideBye: SeriesSide = { code: byeCode, seed: `${seedLabel(byeCode)}・保送`, handicap: handicapSlot === "taiwan" };
  const sideTwOpp: SeriesSide = { code: null, seed: "挑戰賽勝隊", handicap: false };
  return (
    <section>
      {heading}
      <div className="grid items-center gap-4 lg:grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)]">
        <SeriesCard title="季後挑戰賽" format="5 戰 3 勝" sideA={sideChallHome} sideB={sideChallAway} games={[]} needed={3} nameOf={nameOf} />
        <div className="hidden items-center justify-center text-2xl text-faint lg:flex" aria-hidden>→</div>
        <SeriesCard title="台灣大賽" format="7 戰 4 勝" sideA={sideBye} sideB={sideTwOpp} games={[]} needed={4} crownWinner nameOf={nameOf} />
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-faint">
        現行制（2022 起）：
        {sameChamp
          ? "同隊包辦上下半季 → 全年 #2、#3 打挑戰賽，勝隊與雙冠隊爭冠（雙冠隊先勝 1 場）。"
          : "全年勝率較高的半季冠軍保送台灣大賽；較低者與外卡打挑戰賽並先勝 1 場。"}
        （聯盟規章第 60–63 條）
      </p>
    </section>
  );
}

// 二軍季後賽＝單一「二軍總冠軍賽」系列（無半季/挑戰賽）；用同一 SeriesCard 計分表呈現。
function FarmChampion({ isCurrent, series, standings }: {
  isCurrent: boolean; series: PostSeries[]; standings: OfficialStanding[];
}) {
  const champ = series.find((s) => s.kind_code === "F");
  if (!champ) {
    return <p className="text-sm text-faint">{isCurrent ? "本季二軍總冠軍賽尚未進行。" : "此年度無二軍總冠軍賽對戰資料。"}</p>;
  }
  const nameMap = new Map(standings.map((t) => [t.team_code, t.team_name]));
  const rankOf = new Map(standings.map((t, i) => [t.team_code, i + 1]));
  const nameOf = (c: string | null) => (c ? nameMap.get(c) ?? c : "");
  const seed = (code: string) => { const r = rankOf.get(code); return r ? `全年 #${r}` : ""; };
  // 賽制逐年不同（五/七戰）→ 由勝隊勝場反推所需勝場（系列已完成，勝隊勝場＝門檻）。
  const needed = Math.max(champ.team1_wins, champ.team2_wins);
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold text-ink">二軍總冠軍賽</h2>
        <span className="text-[11px] text-faint">依實際對戰結果</span>
      </div>
      <div className="lg:max-w-xl">
        <SeriesCard
          title="二軍總冠軍賽"
          format={`${needed * 2 - 1} 戰 ${needed} 勝`}
          sideA={{ code: champ.team1_code, seed: seed(champ.team1_code), handicap: false }}
          sideB={{ code: champ.team2_code, seed: seed(champ.team2_code), handicap: false }}
          games={champ.games ?? []}
          needed={needed}
          crownWinner
          nameOf={nameOf}
        />
      </div>
    </section>
  );
}

export default async function Standings({ searchParams }: { searchParams: Promise<{ seg?: string; year?: string; kind?: string }> }) {
  const { seg = "0", year: yearParam, kind: kindParam } = await searchParams;
  const segCode = Number(seg) || 0;
  const kind = kindParam === "D" ? "D" : "A";
  const isMinor = kind === "D";
  const { years } = await api.seasons(kind);
  const currentYear = years[0] ?? new Date().getFullYear();
  const selectedYear = yearParam ? Number(yearParam) : currentYear;
  // 官方 rich view（半季冠軍判定/即時 OPS/近十場/連勝連敗）只在「一軍當季」；二軍與歷年皆由 games 即時算
  const useOfficial = !isMinor && selectedYear === currentYear;
  // 季後賽分頁（seg=3）：一軍＝挑戰賽/台灣大賽 bracket；二軍＝二軍總冠軍賽單一系列。
  const isPostseason = segCode === 3;
  // 季後賽為全年概念 → officialStandings 強制 seg=0（0/1/2 才是有效 season_code）。
  const effSeg = isPostseason ? 0 : segCode;
  // 半季資料（一軍專屬）：供 bracket 判半季冠軍 + 種子上色（含歷史年）。
  const needPlayoffData = !isMinor;
  // 進階展開的「月份趨勢」需 special-records（一軍；端點吃 season、由 games+scoreboard 即時算，
  // <2018 無 livelog 的類型自然退化為空）。對戰各隊/主客場來自 standings 本體，不另抓。
  const needAdvanced = !isMinor && !isPostseason;
  // 季後賽系列大比分：歷年有結果、或當季開了季後賽分頁；一軍抓 E/C、二軍抓 F。
  const needPostseasonSummary = selectedYear < currentYear || isPostseason;
  const [{ season, items, half }, derived, special, trend, h1r, h2r, h0r, postseason] = await Promise.all([
    api.officialStandings(effSeg, useOfficial ? undefined : selectedYear, kind),
    !isMinor ? api.standings(selectedYear) : Promise.resolve({ standings: [] }),
    needAdvanced ? api.specialRecords(selectedYear) : Promise.resolve(null),
    api.standingsTrend(useOfficial ? undefined : selectedYear, kind),
    needPlayoffData ? api.officialStandings(1, selectedYear, kind) : Promise.resolve(null),
    needPlayoffData ? api.officialStandings(2, selectedYear, kind) : Promise.resolve(null),
    needPlayoffData ? api.officialStandings(0, selectedYear, kind) : Promise.resolve(null),
    needPostseasonSummary ? api.postseasonSummary(selectedYear, kind) : Promise.resolve(null),
  ]);
  const hasPlayoffPanel = !!(h0r?.items?.length && h1r?.items?.length && h2r?.items?.length);
  const half1Champ = h1r?.half?.champion_code ?? null;
  const half2Champ = h2r?.half?.champion_code ?? null;
  // 年度總冠軍＝台灣大賽(C)／二軍總冠軍賽(F)系列的勝隊；僅歷年（有 postseason）才有值。
  const twSeries = (postseason?.series ?? []).find((s) => s.kind_code === "C" || s.kind_code === "F");
  const championCode = twSeries
    ? (twSeries.team1_wins > twSeries.team2_wins ? twSeries.team1_code : twSeries.team2_code)
    : null;
  // 季後賽系列大比分改由「季後賽」分頁的 bracket 呈現；隊名旁只留簡短種子章。
  // 團隊 OPS/ERA/WHIP 來自即時彙整端點，依 code 併入
  const adv = new Map(derived.standings.map((d) => [d.code, d]));
  const sp = new Map((special?.items ?? []).map((s) => [s.team_code, s]));
  // 主戰績表發散上色比較基準（勝率與團隊攻守）
  const pcts = items.map((x) => x.win_pct);
  const opsVals = items.map((r) => adv.get(r.team_code)?.ops);
  const eraVals = items.map((r) => adv.get(r.team_code)?.era);
  const whipVals = items.map((r) => adv.get(r.team_code)?.whip);

  // 分頁列：一軍＝全年/上半季/下半季/季後賽（＋戰績細項）；二軍無半季/挑戰賽，只有全年＋總冠軍。
  const segTabs = isMinor ? [{ v: 0, label: "全年" }, { v: 3, label: "總冠軍" }] : SEGS;
  const levelLabel = isMinor ? "二軍" : "";
  const subtitle = isMinor ? `${levelLabel}戰績` : useOfficial ? "本季戰績" : "歷年戰績";

  return (
    <div>
      <header className="mb-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">{season} 球季 · {subtitle}</h1>
          <div className="flex flex-wrap items-center gap-2 lg:justify-end">
            <div className="inline-flex items-center rounded-full border border-line bg-surface p-1">
              {LEVELS.map((lv) => (
                <Link
                  key={lv.v}
                  href={lv.v === "A" ? "/standings" : "/standings?kind=D"}
                  className={`rounded-full px-3 py-1 text-sm font-medium transition ${
                    (lv.v === "D") === isMinor ? "bg-ink text-paper" : "text-muted hover:bg-surface-2"
                  }`}
                >
                  {lv.label}
                </Link>
              ))}
            </div>
            <YearSelect years={years} value={selectedYear} kind={kind} basePath="/standings" />
          </div>
        </div>
      </header>

      {/* 單一分頁列——時間切分收成一列。一軍：全年/上半季/下半季/季後賽；二軍：全年/總冠軍。
          特殊戰績（場地/比分型/逆轉/再見…）已移出：per-team 版見各隊球隊頁。 */}
      <div className="mb-4">
        <div className="inline-flex flex-wrap items-center rounded-full border border-line bg-surface p-1">
          {segTabs.map((s) => (
            <Link
              key={s.v}
              href={`/standings?kind=${kind}&year=${selectedYear}&seg=${s.v}`}
              className={`rounded-full px-3 py-1 text-sm transition ${
                segCode === s.v ? "bg-ink text-paper" : "text-muted hover:bg-surface-2"
              }`}
            >
              {s.label}
            </Link>
          ))}
        </div>
      </div>

      {isPostseason ? (
        isMinor ? (
          <FarmChampion isCurrent={useOfficial} series={postseason?.series ?? []} standings={items} />
        ) : (
          <PostseasonBracket
            isCurrent={useOfficial}
            h0={h0r}
            h1={h1r}
            h2={h2r}
            series={postseason?.series ?? []}
          />
        )
      ) : items.length === 0 ? (
        <p className="text-sm text-faint">此區間尚無戰績（下半季可能未開始）。</p>
      ) : (
        <>
          <DataTable
            columns={[
              { header: "#", cell: (t) => <span className="text-faint">{t.rank}</span>, nowrap: true, className: "w-10" },
              {
                header: "球隊",
                cell: (t) => {
                  // 只留簡短的種子章（上冠/下冠）標記席位；系列大比分見「季後賽」分頁。
                  const playoffTags: string[] = [];
                  if (hasPlayoffPanel && segCode === 0) {
                    if (t.team_code === half1Champ) playoffTags.push("上冠");
                    if (t.team_code === half2Champ) playoffTags.push("下冠");
                  }
                  const isChampion = segCode === 0 && t.team_code === championCode;
                  return (
                    // 手機：標籤折到隊名下一行；桌機：隊名/標籤固定雙欄，讓標籤起點對齊。
                    <span className="grid grid-cols-1 items-start gap-0.5 md:grid-cols-[8.5rem_auto] md:items-center md:gap-1.5">
                      <span className="min-w-0">
                        <TeamNameCell code={t.team_code} name={t.team_name} />
                      </span>
                      <span className="inline-flex flex-wrap items-center gap-1 md:justify-start">
                        {isChampion && (
                          <span
                            title="年度總冠軍（台灣大賽勝隊）"
                            className="rounded bg-amber px-1.5 py-0.5 text-[10px] font-bold text-paper"
                          >
                            🏆 總冠軍
                          </span>
                        )}
                        <StreakBadge streak={t.streak} />
                        <GbTag gb={t.gb} />
                        <ElimTag elim={t.elim} />
                        {playoffTags.map((tag) => (
                          <span key={tag} className="rounded bg-amber/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber">{tag}</span>
                        ))}
                        {t.is_champion && (
                          <span
                            title={`${SEGS.find((s) => s.v === segCode)?.label}冠軍${half?.finalized ? "" : "（提前封王）"}`}
                            className="ml-1.5 rounded-full bg-amber/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber"
                          >
                            👑
                          </span>
                        )}
                      </span>
                    </span>
                  );
                },
                sticky: true,
                nowrap: true,
                className: "font-sans",
              },
              { header: "勝-和-敗", cell: (t) => `${t.w}-${t.t}-${t.l}`, nowrap: true },
              {
                header: "勝率",
                cell: (t) => <span className="font-medium text-ink">{t.win_pct != null ? t.win_pct.toFixed(3).replace(/^0/, "") : "—"}</span>,
                cellStyle: (t) => divBg(t.win_pct, pcts),
                nowrap: true,
              },
              ...(useOfficial ? [{ header: "近十場", cell: (t: OfficialStanding) => <L10 s={t.last10} />, nowrap: true }] : []),
              {
                header: <StatAbbr abbr="OPS" />,
                cell: (t) => {
                  const v = adv.get(t.team_code)?.ops;
                  return v == null ? "—" : v.toFixed(3).replace(/^0/, "");
                },
                cellStyle: (t) => divBg(adv.get(t.team_code)?.ops, opsVals),
                className: "hidden text-ink lg:table-cell",
                headClassName: "hidden lg:table-cell",
                nowrap: true,
                align: "right",
              },
              {
                header: <StatAbbr abbr="ERA" />,
                cell: (t) => {
                  const v = adv.get(t.team_code)?.era;
                  return v == null ? "—" : v.toFixed(2);
                },
                cellStyle: (t) => divBg(adv.get(t.team_code)?.era, eraVals, true),
                className: "hidden text-ink lg:table-cell",
                headClassName: "hidden lg:table-cell",
                nowrap: true,
                align: "right",
              },
              {
                header: <StatAbbr abbr="WHIP" />,
                cell: (t) => {
                  const v = adv.get(t.team_code)?.whip;
                  return v == null ? "—" : v.toFixed(2);
                },
                cellStyle: (t) => divBg(adv.get(t.team_code)?.whip, whipVals, true),
                className: "hidden text-ink lg:table-cell",
                headClassName: "hidden lg:table-cell",
                nowrap: true,
                align: "right",
              },
            ] satisfies Column<OfficialStanding>[]}
            rows={items}
            rowKey={(t) => t.team_code}
            dense
          />
          {trend && trend.points.length > 0 && (
            <section className="mt-8">
              <h2 className="mb-1 text-lg font-semibold">戰績走勢</h2>
              <div className="rounded-xl border border-line p-4">
                <StandingsTrend teams={trend.teams} points={trend.points} names={trend.names} />
              </div>
            </section>
          )}

          {/* 進階展開：把對戰各隊/主客場/月份收合，首屏聚焦競爭位置（§5.4）。
              原生 <details> 免 client island、SSR 友善、鍵盤可及。 */}
          <details className="mt-8 rounded-xl border border-line bg-surface">
            <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-ink marker:text-faint">
              進階展開：對戰各隊 · 主客場{sp.size > 0 ? " · 特殊戰績對照 · 月份趨勢" : ""}
            </summary>
            <div className="border-t border-line px-4 pt-4">
              <H2HTable rows={items} />
              <TeamStatsTable rows={items} />
              {sp.size > 0 && <SpecialCompareTable rows={items} sp={sp} />}
              {sp.size > 0 && <MonthsTable rows={items} sp={sp} />}
            </div>
          </details>

          {!isMinor && (
            <p className="mt-6 text-[11px] leading-relaxed text-faint">
              進階展開的「特殊戰績對照」列出高訊號隊級戰績跨隊比較；場地／賽況軌跡／對手先發／
              系列賽等更多細項，見各隊球隊頁（點上方球隊名進入）。
            </p>
          )}
        </>
      )}

      {(segCode === 1 || segCode === 2) && items.length > 0 && half && (
        <p className="mt-2 text-[11px] text-faint">
          {half.champion_code
            ? `👑 ${SEGS.find((s) => s.v === segCode)?.label}冠軍${half.finalized ? "已定案" : "勝場數已無人能追平，提前封王"}。半季冠軍取得季後賽資格；兩半季冠軍中全年勝率較高者保送台灣大賽，另一隊與外卡打季後挑戰賽（同隊包辦上下半季則該隊保送、由全年第 2、3 名爭挑戰賽）。`
            : "半季冠軍取得季後賽資格；本半季冠軍尚未產生（賽程進行中）。"}
        </p>
      )}

    </div>
  );
}
