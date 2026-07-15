import Link from "next/link";
import { DataTable, type Column } from "@/components/table";
import { ActivePill, GonePill, NameTag, Notice, PlayerLink, TeamBadge, TeamLogo } from "@/components/ui";
import { api } from "@/lib/api";
import { teamColor, teamFullName } from "@/lib/teams";
import { ChampionsPlayerTable, type ChampRow } from "./champions-player-table";

export const dynamic = "force-dynamic";

const f3 = (v: number | string | null) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));

type Records = Awaited<ReturnType<typeof api.records>>;
type Championships = Awaited<ReturnType<typeof api.championships>>;
type Franchises = Awaited<ReturnType<typeof api.franchises>>["items"];
type GameRec = NonNullable<Records["games"][keyof Records["games"]]>;
type SeasonRec = { name: string; pid: string; year: number; val: number | string };
type CareerRec = { name: string; pid: string; val: number; active: boolean };
type Dynasty = NonNullable<Championships["franchise_ranking"]>[number];
type ChampSeason = Championships["seasons"][number];

type GameRow = { key: string; label: string; rec: GameRec; value: string };
type SeasonRow = { key: string; group: string; label: string; rec: SeasonRec; format?: "rate" };

function gameRows(games: Records["games"]): GameRow[] {
  const defs: { key: keyof Records["games"]; label: string; value: (r: GameRec) => string }[] = [
    { key: "max_margin", label: "單場最大分差", value: (r) => `${Math.abs(r.hs - r.as)} 分` },
    { key: "max_team_runs", label: "單隊單場最多得分", value: (r) => `${Math.max(r.hs, r.as)} 分` },
    { key: "max_combined", label: "單場雙方最多得分", value: (r) => `${r.hs + r.as} 分` },
  ];
  return defs.flatMap((d) => {
    const rec = games[d.key];
    return rec ? [{ key: d.key, label: d.label, rec, value: d.value(rec) }] : [];
  });
}

function seasonRows(d: Records): SeasonRow[] {
  const defs: { group: string; key: string; label: string; rec?: SeasonRec[]; format?: "rate" }[] = [
    { group: "打者", key: "hr", label: "最多全壘打", rec: d.season_batting.hr },
    { group: "打者", key: "avg", label: "最高打擊率", rec: d.season_batting.avg, format: "rate" },
    { group: "打者", key: "rbi", label: "最多打點", rec: d.season_batting.rbi },
    { group: "打者", key: "sb", label: "最多盜壘", rec: d.season_batting.sb },
    { group: "投手", key: "w", label: "最多勝投", rec: d.season_pitching.w },
    { group: "投手", key: "sv", label: "最多救援", rec: d.season_pitching.sv },
    { group: "投手", key: "so", label: "最多三振", rec: d.season_pitching.so },
  ];
  return defs.flatMap((d) => d.rec?.[0] ? [{ key: `${d.group}-${d.key}`, group: d.group, label: d.label, rec: d.rec[0], format: d.format }] : []);
}

// 生涯排行：每一項獨立一張排行卡（勿把 HR/H/RBI/SB 黏在同一表用「紀錄」欄硬分，看不清）。
function LeaderCard({ title, rows }: { title: string; rows?: CareerRec[] }) {
  const items = rows ?? [];
  return (
    <div className="card p-4">
      <h4 className="mb-2.5 text-sm font-semibold text-ink">{title}</h4>
      <ol className="space-y-1.5">
        {items.map((r, i) => (
          <li key={`${r.pid}-${i}`} className="flex items-center gap-2 text-sm">
            <span className="w-4 shrink-0 text-right font-mono text-xs tabular-nums text-faint">{i + 1}</span>
            <span className="min-w-0 flex-1 truncate font-sans">
              <PlayerLink pid={r.pid} name={r.name} />
              {r.active && <span className="ml-1.5 text-[10px] font-medium text-up">現役</span>}
            </span>
            <span className="shrink-0 font-mono font-semibold tabular-nums text-accent">{r.val}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

const gameColumns: Column<GameRow>[] = [
  { header: "紀錄", cell: (r) => r.label, sticky: true, nowrap: true, className: "font-sans font-medium text-ink" },
  { header: "紀錄值", cell: (r) => r.value, align: "right", nowrap: true, className: "font-semibold text-accent" },
  { header: "客隊", cell: (r) => <NameTag name={r.rec.away} />, nowrap: true, className: "font-sans" },
  { header: "比分", cell: (r) => `${r.rec.as}：${r.rec.hs}`, align: "center", nowrap: true, className: "font-bold text-ink" },
  { header: "主隊", cell: (r) => <NameTag name={r.rec.home} />, nowrap: true, className: "font-sans" },
  { header: "日期", cell: (r) => r.rec.date, align: "right", nowrap: true, className: "text-muted" },
];

// 單季之最：打者／投手分開兩表（勿用「類別」欄把兩者黏在一起，語意不同看不清）。
const seasonColumns: Column<SeasonRow>[] = [
  { header: "紀錄", cell: (r) => r.label, sticky: true, nowrap: true, className: "font-sans font-medium text-ink" },
  { header: "球員", cell: (r) => <PlayerLink pid={r.rec.pid} name={r.rec.name} />, nowrap: true, className: "font-sans" },
  { header: "球季", cell: (r) => r.rec.year, align: "right", nowrap: true, className: "text-muted" },
  { header: "紀錄值", cell: (r) => r.format === "rate" ? f3(r.rec.val) : r.rec.val, align: "right", nowrap: true, className: "font-semibold text-accent" },
];

// —— 冠軍王朝榜：緊湊表格（每隊一列），並列排名（rk）。冠軍數帶迷你長條（∝ titles/榜首），
// 奪冠年份 inline，密度高又保留視覺。
function DynastyTable({ rows }: { rows: Dynasty[] }) {
  const max = rows[0]?.titles ?? 1;
  const columns: Column<Dynasty>[] = [
    { header: "名次", cell: (r) => r.rk, sticky: true, align: "right", nowrap: true, className: "text-faint" },
    {
      header: "球團",
      cell: (r) => <Link href={`/teams/${r.team_code}`} className="font-medium hover:underline"><TeamBadge code={r.team_code} name={r.team} /></Link>,
      nowrap: true,
      className: "font-sans",
    },
    {
      header: "冠軍",
      cell: (r) => (
        <span className="inline-flex items-center gap-2">
          <span className="hidden h-2 w-20 overflow-hidden rounded-full bg-surface-2 sm:inline-block">
            <span className="block h-full rounded-full" style={{ width: `${Math.max(8, (r.titles / max) * 100)}%`, background: teamColor(r.team_code) }} />
          </span>
          <span className="w-5 text-right font-bold tabular-nums text-accent">{r.titles}</span>
        </span>
      ),
      nowrap: true,
    },
    { header: "奪冠年份", cell: (r) => r.years.join("、"), nowrap: true, className: "font-mono text-[11px] tabular-nums text-muted" },
  ];
  return <DataTable columns={columns} rows={rows} rowKey={(r) => r.team_code} dense />;
}

// 徽章色用當年隊名（nameMeta 全涵蓋含已解散隊），顯示文字補成全名（teamFullName）。
function ChampTeam({ name }: { name: string | null }) {
  if (!name) return null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <TeamLogo name={name} size={16} decorative />
      <span>{teamFullName(name)}</span>
    </span>
  );
}

const seasonChampColumns: Column<ChampSeason>[] = [
  { header: "年度", cell: (r) => r.year, sticky: true, align: "right", nowrap: true, className: "font-semibold text-ink" },
  { header: "冠軍", cell: (r) => <ChampTeam name={r.champion} />, nowrap: true, className: "font-sans font-semibold text-ink" },
  // 沒有亞軍（1992/94/95 包辦上下半季，無台灣大賽對手）→ 不顯示、不留空白佔位。
  { header: "亞軍", cell: (r) => r.runner_up_team_code ? <ChampTeam name={r.runner_up} /> : null, nowrap: true, className: "font-sans text-muted" },
  { header: "奪冠總教練", cell: (r) => r.manager_name ?? "—", nowrap: true, className: "font-sans text-muted" },
];

function FranchiseTable({ rows }: { rows: Franchises }) {
  const columns: Column<Franchises[number]>[] = [
    {
      header: "球團",
      cell: (r) => <Link href={`/teams/${r.code}`} className="font-medium hover:underline"><TeamBadge code={r.code} name={r.name} /></Link>,
      sticky: true,
      nowrap: true,
      className: "font-sans",
    },
    { header: "現況", cell: (r) => r.active ? <ActivePill /> : <GonePill />, align: "center", nowrap: true, className: "font-sans" },
    { header: "年代", cell: (r) => `${r.from}–${r.to}`, align: "right", nowrap: true, className: "text-muted" },
    { header: "勝–和–敗", cell: (r) => `${r.w}–${r.t}–${r.l}`, align: "right", nowrap: true },
    { header: "勝率", cell: (r) => f3(r.win_pct), align: "right", nowrap: true, className: "font-semibold text-ink" },
    {
      header: "隊史沿革",
      cell: (r) => r.eras.map((e) => `${e.name}（${e.from}–${e.to}）`).join(" → "),
      nowrap: true,
      className: "font-sans text-muted",
    },
  ];
  return <DataTable columns={columns} rows={rows} rowKey={(r) => r.code} dense />;
}

export default async function RecordsPage() {
  const [d, fr, ch] = await Promise.all([api.records(), api.franchises(), api.championships()]);
  const games = gameRows(d.games);
  const seasons = seasonRows(d);
  const battingCareer = [
    { title: "生涯全壘打", rows: d.career_batting.hr },
    { title: "生涯安打", rows: d.career_batting.h },
    { title: "生涯打點", rows: d.career_batting.rbi },
    { title: "生涯盜壘", rows: d.career_batting.sb },
  ];
  const pitchingCareer = [
    { title: "生涯勝投", rows: d.career_pitching.w },
    { title: "生涯救援", rows: d.career_pitching.sv },
    { title: "生涯三振", rows: d.career_pitching.so },
  ];

  // 冠軍資料 coverage fail-closed：缺年時 API 不回傳 franchise/player_ranking，前端據此
  // 不呈現「歷史最多冠軍」累計結論（看板紅線：冠軍資料缺年不得公開歷史最多）。
  const covComplete = ch.coverage.complete;
  const dynasties = ch.franchise_ranking ?? [];
  const champPlayers = ch.player_ranking ?? [];

  // 把奪冠年份解析成「當年隸屬球隊」徽章（含教練身分年份）。用**當年隊名**（era-accurate）：
  // 張泰山 2004/05 是興農牛奪冠（興農 franchise 今為富邦），顯示富邦是錯的；已解散隊
  // （三商虎/中信鯨）更沒有現役 franchise。依**當年隊碼**去重：同隊合併一枚，改過名的隊
  // （Lamigo→樂天桃猿 是不同碼）獨立列出。每枚帶自己的奪冠年份供 hover。
  const yearInfo = new Map(ch.seasons.map((s) => [s.year, s]));
  const teamsOf = (years: number[]) => {
    const byCode = new Map<string, { code: string; name: string; years: number[] }>();
    for (const y of years) {
      const s = yearInfo.get(y);
      if (!s?.champion_team_code || !s.champion) continue;
      const e = byCode.get(s.champion_team_code);
      if (e) e.years.push(y);
      else byCode.set(s.champion_team_code, { code: s.champion_team_code, name: teamFullName(s.champion), years: [y] });
    }
    return [...byCode.values()].sort((a, b) => Math.min(...a.years) - Math.min(...b.years));
  };

  // 合併同一行：奪冠年份 + 狀態（現役/教練）皆相同的選手併成一列（如樂天/Lamigo 王朝
  // 群 7 冠現役球員）。champPlayers 已依 rk（冠軍次數 desc）排序，Map 保序 → 群仍由高到低。
  const champGroups = new Map<string, ChampRow>();
  for (const p of champPlayers) {
    const key = `${p.years.join(",")}|${p.active}|${p.is_manager}`;
    const g = champGroups.get(key);
    if (g) g.players.push({ pid: p.pid, name: p.name });
    else champGroups.set(key, {
      key, titles: p.titles, players: [{ pid: p.pid, name: p.name }],
      teams: teamsOf(p.years), active: p.active, isManager: p.is_manager,
    });
  }
  const champRows = [...champGroups.values()];

  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-extrabold tracking-tight text-ink">歷史紀錄室</h1>

      <section aria-labelledby="dynasty">
        <h2 id="dynasty" className="mb-3 text-lg font-semibold text-ink">冠軍王朝榜</h2>
        {covComplete && dynasties.length ? (
          <DynastyTable rows={dynasties} />
        ) : (
          <Notice>{ch.note ?? "冠軍資料尚未補齊，暫不呈現累計王朝排行。"}</Notice>
        )}
      </section>

      <section aria-labelledby="career-records" className="space-y-4">
        <h2 id="career-records" className="text-lg font-semibold text-ink">生涯排行</h2>
        <div>
          <h3 className="mb-2 text-sm font-semibold text-muted">打者紀錄</h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {battingCareer.map((c) => <LeaderCard key={c.title} title={c.title} rows={c.rows} />)}
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold text-muted">投手紀錄</h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {pitchingCareer.map((c) => <LeaderCard key={c.title} title={c.title} rows={c.rows} />)}
          </div>
        </div>
      </section>

      <section aria-labelledby="champ-seasons">
        <h2 id="champ-seasons" className="mb-3 text-lg font-semibold text-ink">歷年冠亞軍</h2>
        <DataTable columns={seasonChampColumns} rows={ch.seasons} rowKey={(r) => r.year} dense maxHeight="26rem" />
      </section>

      {covComplete && champPlayers.length > 0 && (
        <section aria-labelledby="champ-players">
          <h2 id="champ-players" className="mb-3 text-lg font-semibold text-ink">個人冠軍次數榜</h2>
          <ChampionsPlayerTable rows={champRows} />
        </section>
      )}

      <section aria-labelledby="season-records">
        <h2 id="season-records" className="mb-3 text-lg font-semibold text-ink">單季之最</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink">打者紀錄</h3>
            <DataTable columns={seasonColumns} rows={seasons.filter((r) => r.group === "打者")} rowKey={(r) => r.key} dense />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink">投手紀錄</h3>
            <DataTable columns={seasonColumns} rows={seasons.filter((r) => r.group === "投手")} rowKey={(r) => r.key} dense />
          </div>
        </div>
      </section>

      <section aria-labelledby="game-records">
        <h2 id="game-records" className="mb-3 text-lg font-semibold text-ink">比賽紀錄</h2>
        <DataTable columns={gameColumns} rows={games} rowKey={(r) => r.key} dense />
      </section>

      <section aria-labelledby="franchise-history">
        <h2 id="franchise-history" className="mb-3 text-lg font-semibold text-ink">歷代球隊</h2>
        <FranchiseTable rows={fr.items} />
      </section>
    </div>
  );
}
