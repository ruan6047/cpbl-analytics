import Link from "next/link";
import { DataTable, type Column } from "@/components/table";
import { ActivePill, Eyebrow, GonePill, NameTag, PlayerLink, TeamBadge } from "@/components/ui";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const f3 = (v: number | string | null) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));

type Records = Awaited<ReturnType<typeof api.records>>;
type Franchises = Awaited<ReturnType<typeof api.franchises>>["items"];
type GameRec = NonNullable<Records["games"][keyof Records["games"]]>;
type SeasonRec = { name: string; pid: string; year: number; val: number | string };
type CareerRec = { name: string; pid: string; val: number; active: boolean };

type GameRow = { key: string; label: string; rec: GameRec; value: string };
type SeasonRow = { key: string; group: string; label: string; rec: SeasonRec; format?: "rate" };
type CareerRow = { key: string; label: string; rank: number; rec: CareerRec };

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

function careerRows(groups: { key: string; label: string; rows?: CareerRec[] }[]): CareerRow[] {
  return groups.flatMap((g) => (g.rows ?? []).map((rec, i) => ({ key: `${g.key}-${rec.pid}-${i}`, label: g.label, rank: i + 1, rec })));
}

const gameColumns: Column<GameRow>[] = [
  { header: "紀錄", cell: (r) => r.label, sticky: true, nowrap: true, className: "font-sans font-medium text-ink" },
  { header: "紀錄值", cell: (r) => r.value, align: "right", nowrap: true, className: "font-semibold text-accent" },
  { header: "客隊", cell: (r) => <NameTag name={r.rec.away} />, nowrap: true, className: "font-sans" },
  { header: "比分", cell: (r) => `${r.rec.as}：${r.rec.hs}`, align: "center", nowrap: true, className: "font-bold text-ink" },
  { header: "主隊", cell: (r) => <NameTag name={r.rec.home} />, nowrap: true, className: "font-sans" },
  { header: "日期", cell: (r) => r.rec.date, align: "right", nowrap: true, className: "text-muted" },
];

const seasonColumns: Column<SeasonRow>[] = [
  { header: "類別", cell: (r) => r.group, sticky: true, nowrap: true, className: "font-sans text-muted" },
  { header: "紀錄", cell: (r) => r.label, nowrap: true, className: "font-sans font-medium text-ink" },
  { header: "球員", cell: (r) => <PlayerLink pid={r.rec.pid} name={r.rec.name} />, nowrap: true, className: "font-sans" },
  { header: "球季", cell: (r) => r.rec.year, align: "right", nowrap: true, className: "text-muted" },
  { header: "紀錄值", cell: (r) => r.format === "rate" ? f3(r.rec.val) : r.rec.val, align: "right", nowrap: true, className: "font-semibold text-accent" },
];

const careerColumns: Column<CareerRow>[] = [
  { header: "紀錄", cell: (r) => r.label, sticky: true, nowrap: true, className: "font-sans font-medium text-ink" },
  { header: "名次", cell: (r) => r.rank, align: "right", nowrap: true, className: "text-faint" },
  { header: "球員", cell: (r) => <PlayerLink pid={r.rec.pid} name={r.rec.name} />, nowrap: true, className: "font-sans" },
  { header: "現況", cell: (r) => r.rec.active ? <ActivePill /> : <span className="text-faint">退役</span>, align: "center", nowrap: true, className: "font-sans" },
  { header: "累計", cell: (r) => r.rec.val, align: "right", nowrap: true, className: "font-semibold text-accent" },
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
  const [d, fr] = await Promise.all([api.records(), api.franchises()]);
  const games = gameRows(d.games);
  const seasons = seasonRows(d);
  const battingCareer = careerRows([
    { key: "hr", label: "生涯全壘打", rows: d.career_batting.hr },
    { key: "h", label: "生涯安打", rows: d.career_batting.h },
    { key: "rbi", label: "生涯打點", rows: d.career_batting.rbi },
    { key: "sb", label: "生涯盜壘", rows: d.career_batting.sb },
  ]);
  const pitchingCareer = careerRows([
    { key: "w", label: "生涯勝投", rows: d.career_pitching.w },
    { key: "sv", label: "生涯救援", rows: d.career_pitching.sv },
    { key: "so", label: "生涯三振", rows: d.career_pitching.so },
  ]);

  return (
    <div className="space-y-8">
      <header className="mb-6">
        <Eyebrow className="mb-2">聯盟史冊・1990 至今</Eyebrow>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">歷史紀錄室</h1>
        <p className="mt-1.5 max-w-3xl text-sm text-muted">
          中華職棒一軍歷史之最。比賽紀錄含全史；單季與生涯紀錄以官方歷年彙總為基礎，近兩季另計。
        </p>
      </header>

      <section aria-labelledby="game-records">
        <Eyebrow className="mb-2">一場比賽能走到多極端？</Eyebrow>
        <h2 id="game-records" className="mb-3 text-lg font-semibold text-ink">比賽紀錄</h2>
        <DataTable columns={gameColumns} rows={games} rowKey={(r) => r.key} dense />
      </section>

      <section aria-labelledby="season-records">
        <Eyebrow className="mb-2">單一球季的最高峰</Eyebrow>
        <h2 id="season-records" className="mb-3 text-lg font-semibold text-ink">單季之最</h2>
        <DataTable columns={seasonColumns} rows={seasons} rowKey={(r) => r.key} dense />
      </section>

      <section aria-labelledby="career-records">
        <Eyebrow className="mb-2">長期累積的聯盟標竿</Eyebrow>
        <h2 id="career-records" className="mb-3 text-lg font-semibold text-ink">生涯排行</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink">打者紀錄</h3>
            <DataTable columns={careerColumns} rows={battingCareer} rowKey={(r) => r.key} dense />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink">投手紀錄</h3>
            <DataTable columns={careerColumns} rows={pitchingCareer} rowKey={(r) => r.key} dense />
          </div>
        </div>
      </section>

      <section aria-labelledby="franchise-history">
        <Eyebrow className="mb-2">球團更名、轉賣與存續</Eyebrow>
        <h2 id="franchise-history" className="mb-1 text-lg font-semibold text-ink">歷代球隊</h2>
        <p className="mb-3 text-[11px] text-faint">點球團名稱進入隊史頁；沿革依時間由左至右排列。</p>
        <FranchiseTable rows={fr.items} />
      </section>
    </div>
  );
}
