import Link from "next/link";
import { notFound } from "next/navigation";
import { DataTable, type Column } from "@/components/table";
import { Card, Eyebrow, PlayerLink, StatGrid } from "@/components/ui";
import {
  FACTOR_STATS,
  api,
  type VenueBatter,
  type VenueEnvLine,
  type VenueFactorsResponse,
  type VenuePitcher,
} from "@/lib/api";
import { optionalNotFound } from "@/lib/http-error";
import { canonicalVenue, hasSplitRows } from "./page-logic";
import { FACTOR_LABEL, LowSample, PfBar, VsLeague, f1, f2, f3, num, pfPhrase } from "./parts";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ venue: string }> }) {
  const { venue } = await params;
  return { title: `${decodeURIComponent(venue)} | 球場 | CPBL 分析` };
}

const SHOW = 6;      // 每端顯示人數
const POOL = 30;     // 向 API 要的兩端長度（> SHOW，供過濾後仍有餘裕）
const VENUE_DATA_FROM = 2018;

// API 的 best/worst＝同一排序的頭尾各 limit 名。**達門檻選手可能不足 2×limit**
// （例：花蓮投手全史僅 5 人達 30 局）→ 頭尾會撈到同一批人，且「差於生涯最多」那端
// 可能全是 delta 方向相反的人。UI 不得照抄：先按方向濾號，再對另一端去重。
function split<T extends { player_id: string }>(
  best: T[], worst: T[], d: (r: T) => number, betterIsNegative: boolean,
): { top: T[]; bottom: T[] } {
  const better = (r: T) => (betterIsNegative ? d(r) < 0 : d(r) > 0);
  const top = best.filter(better).slice(0, SHOW);
  const seen = new Set(top.map((r) => r.player_id));
  const bottom = worst
    .filter((r) => !better(r) && d(r) !== 0 && !seen.has(r.player_id))
    .slice(0, SHOW);
  return { top, bottom };
}

export default async function VenuePage({ params }: { params: Promise<{ venue: string }> }) {
  const { venue: rawParam } = await params;
  const venueParam = canonicalVenue(decodeURIComponent(rawParam));
  const [list, factors, stats, bat, pit] = await Promise.all([
    api.venues(),
    optionalNotFound(api.venueFactors(venueParam)),
    optionalNotFound(api.venueStats(venueParam)),
    optionalNotFound(api.venuePlayers<VenueBatter>(venueParam, "batting", POOL)),
    optionalNotFound(api.venuePlayers<VenuePitcher>(venueParam, "pitching", POOL)),
  ]);
  const spec = list.items.find((v) => v.venue === venueParam);
  if (!factors && !stats && !spec) notFound();

  const batSplit = bat && split(bat.best, bat.worst, (r) => r.delta_ops, false);
  const pitSplit = pit && split(pit.best, pit.worst, (r) => r.delta_era, true);
  const showBat = batSplit != null && hasSplitRows(batSplit);
  const showPit = pitSplit != null && hasSplitRows(pitSplit);

  // API 端已把歷史別名歸一（桃園→樂天桃園）；規格卡以歸一後短名回列表查。
  const venue = factors?.venue ?? stats?.venue ?? venueParam;
  const name = spec?.full_name ?? stats?.item_name ?? venue;
  const league = new Map((stats?.league ?? []).map((l) => [l.year, l]));

  return (
    <div className="space-y-8">
      <header>
        <Link href="/venues" className="text-xs text-faint hover:text-accent">← 球場</Link>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-ink">{name}</h1>
        {/* 刻意不顯示 venue_dim 的「一軍使用年份」：該欄以場名 GROUP BY，未歸一歷史別名
            （樂天桃園 2022 起才算，2010–2021 的「桃園」682 場不計）→ 會與本頁資料範圍打架。
            本頁一律只講「有資料背書的涵蓋範圍」。 */}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm text-muted">
          <span>{spec?.city}</span>
          {factors && (
            <span>· 資料涵蓋 {factors.from_year}–{factors.to_year}，共 {factors.pooled.games} 場一軍例行賽</span>
          )}
          {!factors && spec?.first_year != null && (
            <span>· CPBL 一軍使用 {spec.first_year}–{spec.last_year}</span>
          )}
        </div>
        {spec && (
          <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
            {spec.indoor && <span className="rounded-full bg-cpbl/10 px-2 py-0.5 font-medium text-cpbl">室內</span>}
            {spec.turf && (
              <span className="rounded-full bg-line/60 px-2 py-0.5 text-muted">
                {spec.turf === "artificial" ? "人工草皮" : "天然草皮"}
              </span>
            )}
            {spec.big_screen && <span className="rounded-full bg-line/60 px-2 py-0.5 text-muted">大螢幕</span>}
            {spec.home_teams && (
              <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">{spec.home_teams} 主場</span>
            )}
          </div>
        )}
      </header>

      {/* 規格（沿用 venue_dim；外野距離單位為呎）*/}
      {spec && (
        <section>
          <Eyebrow className="mb-2">球場規格</Eyebrow>
          <Card>
            <div className="grid gap-6 sm:grid-cols-2">
              <StatGrid
                cols={2}
                items={[
                  { label: "容量", value: num(spec.capacity) },
                  { label: "場均觀眾", value: num(spec.avg_attendance) },
                  { label: "內野席", value: num(spec.infield_seats) },
                  { label: "外野席", value: num(spec.outfield_seats) },
                ]}
              />
              <div className="space-y-1.5">
                {([["左外野", spec.lf_dist], ["中外野", spec.cf_dist], ["右外野", spec.rf_dist]] as const).map(
                  ([label, ft]) =>
                    ft != null && (
                      <div key={label} className="flex items-center gap-2 text-[11px]">
                        <span className="w-10 shrink-0 whitespace-nowrap text-faint">{label}</span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line/60">
                          <div className="h-full rounded-full bg-accent/70" style={{ width: `${(ft / 410) * 100}%` }} />
                        </div>
                        <span className="w-12 text-right font-mono tabular-nums text-muted">{ft} 呎</span>
                      </div>
                    ),
                )}
                {spec.address && <div className="pt-1 text-[11px] text-faint">{spec.address}</div>}
              </div>
            </div>
          </Card>
        </section>
      )}

      {!factors && !stats && spec && (
        <Card>
          <p className="text-sm font-medium text-ink">歷史 CPBL 場地</p>
          <p className="mt-1 text-sm text-muted">
            逐場分析資料目前自 {VENUE_DATA_FROM} 年起；此場地沒有可用的 Park Factor 與打擊環境資料。
            本頁僅呈現官方規格與 CPBL 一軍使用紀錄，未據此推論場地目前是否營運。
          </p>
        </Card>
      )}

      {factors && <ParkFactors factors={factors} />}

      {/* 打擊環境：球場逐年 vs 聯盟同年 */}
      {stats && stats.seasons.length > 0 && (
        <section>
          <Eyebrow className="mb-1">打擊環境</Eyebrow>
          <h2 className="mb-1 text-lg font-semibold">逐年打擊數據（小字＝與聯盟同年差）</h2>
          <p className="mb-3 text-sm text-muted">
            此球場所有出賽選手的合計，非球隊成績；差值僅為對照，未控制出賽球隊組成（控制後的結果見上方 Park Factor）。
          </p>
          <DataTable
            columns={envColumns(league)}
            rows={stats.seasons}
            rowKey={(r) => r.year}
            dense
          />
          <p className="mt-2 text-[11px] text-faint">{stats.note}</p>
        </section>
      )}

      {/* 選手極端表現（生涯口徑，含 2018 以前）*/}
      {(showBat || showPit) && (
        <section>
          <Eyebrow className="mb-1">選手表現差距</Eyebrow>
          <h2 className="mb-1 text-lg font-semibold">在此球場與自身生涯基準差距最大的選手</h2>
          <p className="mb-2 text-sm text-muted">
            差距＝該球場成績減去自身生涯成績，屬<span className="font-semibold text-ink">描述性統計</span>，
            不代表選手適應或不適應此球場——樣本仍小，且未控制對戰投手、年份與傷勢。請一併看樣本欄（PA／IP）。
          </p>
          <p className="mb-3 text-[11px] text-faint">
            全頁色規則：<span className="font-medium text-accent">紅＝高於基準</span>、
            <span className="font-medium text-up">藍＝低於基準</span>（僅表方向，不含好壞；投手 ERA 越低越好，故藍色為佳）。
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {bat && batSplit && showBat && (
              <Card>
                <h3 className="mb-2 text-sm font-semibold text-ink">
                  打者 <span className="font-normal text-faint">（生涯在此 ≥ {bat.thresholds.min_pa} PA）</span>
                </h3>
                <ExtremeTable rows={batSplit.top} columns={batColumns} title="OPS 高於自身生涯" />
                <ExtremeTable rows={batSplit.bottom} columns={batColumns} title="OPS 低於自身生涯" className="mt-4" />
              </Card>
            )}
            {pit && pitSplit && showPit && (
              <Card>
                <h3 className="mb-2 text-sm font-semibold text-ink">
                  投手 <span className="font-normal text-faint">（生涯在此 ≥ {(pit.thresholds.min_outs / 3).toFixed(0)} 局）</span>
                </h3>
                <ExtremeTable rows={pitSplit.top} columns={pitColumns} title="ERA 優於自身生涯" />
                <ExtremeTable rows={pitSplit.bottom} columns={pitColumns} title="ERA 差於自身生涯" className="mt-4" />
              </Card>
            )}
          </div>
          <p className="mt-2 text-[11px] text-faint">{bat?.note ?? pit?.note}</p>
        </section>
      )}
    </div>
  );
}

// —— Park Factor 區塊 ——

function ParkFactors({ factors }: { factors: VenueFactorsResponse }) {
  const p = factors.pooled;
  // 首屏只講 2 句：得分與全壘打。其餘留給長條與逐季表，不堆砌斷言。
  const headline = (["r", "hr"] as const).map((s) => pfPhrase(s, p.factors[s].pf, p.games, p.low_sample));

  const seasonCols: Column<VenueFactorsResponse["seasons"][number]>[] = [
    { header: "年", cell: (r) => r.year, align: "left", nowrap: true, sticky: true },
    {
      header: "場次",
      align: "right",
      cell: (r) => (
        <span className="inline-flex items-center gap-1.5">
          {r.games}
          {r.low_sample && <LowSample />}
        </span>
      ),
    },
    ...FACTOR_STATS.map(
      (s): Column<VenueFactorsResponse["seasons"][number]> => ({
        header: FACTOR_LABEL[s],
        align: "right",
        cell: (r) => {
          const pf = r.factors[s].pf;
          if (pf == null) return <span className="text-faint">—</span>;
          const tone = Math.abs(pf - 1) < 0.03 ? "text-muted" : pf > 1 ? "text-accent" : "text-up";
          return <span className={`${tone} ${r.low_sample ? "opacity-60" : ""}`}>{pf.toFixed(2)}</span>;
        },
      }),
    ),
  ];

  return (
    <section>
      <Eyebrow className="mb-1">球場數據特色</Eyebrow>
      <h2 className="mb-1 text-lg font-semibold">Park Factor（主客對照法）</h2>
      <p className="mb-3 text-sm text-muted">
        {factors.method_note}
        <br />
        <span className="text-faint">{factors.data_floor_note}</span>
      </p>

      <Card className="mb-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink">
            合併 {factors.from_year}–{factors.to_year}
            <span className="ml-2 font-normal text-faint">{p.games} 場</span>
          </h3>
          {p.low_sample && <LowSample />}
        </div>
        <ul className="mb-3 space-y-1 text-sm text-ink">
          {headline.map((h) => (
            <li key={h}>· {h}</li>
          ))}
        </ul>
        <div className="mb-1 flex items-center gap-3 text-[10px] text-faint">
          <span className="w-16 shrink-0">項目</span>
          <span className="flex-1 text-center">← 壓制　基準 1.00　放大 →</span>
          <span className="w-12 shrink-0 text-right">PF</span>
          <span className="hidden w-28 shrink-0 text-right sm:block">實際 / 期望</span>
        </div>
        {FACTOR_STATS.map((s) => (
          <PfBar key={s} stat={s} f={p.factors[s]} lowSample={p.low_sample} />
        ))}
        {p.excluded_team_games > 0 && (
          <p className="mt-2 text-[11px] text-faint">
            另有 {p.excluded_team_games} 個「隊-場」因該隊該季沒有其他球場的場次可當基準而排除於估計外。
          </p>
        )}
      </Card>

      <h3 className="mb-2 text-sm font-semibold text-ink">逐季（PF &gt; 1＝放大該事件）</h3>
      <DataTable columns={seasonCols} rows={factors.seasons} rowKey={(r) => r.year} dense />
    </section>
  );
}

// —— 打擊環境欄位 ——

function envColumns(league: Map<number, VenueEnvLine>): Column<VenueEnvLine>[] {
  const lg = (r: VenueEnvLine) => league.get(r.year);
  const cmp = (
    header: string,
    pick: (l: VenueEnvLine) => number | null,
    fmt: (v: number | null | undefined) => string,
  ): Column<VenueEnvLine> => ({
    header,
    align: "right",
    cell: (r) => <VsLeague value={pick(r)} league={lg(r) ? pick(lg(r)!) : null} fmt={fmt} />,
  });
  return [
    { header: "年", cell: (r) => r.year, nowrap: true, sticky: true },
    { header: "PA", align: "right", cell: (r) => num(r.pa) },
    cmp("AVG", (l) => l.avg, f3),
    cmp("OBP", (l) => l.obp, f3),
    cmp("SLG", (l) => l.slg, f3),
    cmp("OPS", (l) => l.ops, f3),
    cmp("HR%", (l) => l.hr_pct, f1),
    cmp("SO%", (l) => l.so_pct, f1),
    cmp("BB%", (l) => l.bb_pct, f1),
    cmp("GO/AO", (l) => l.go_ao, f2),
  ];
}

// —— 選手極端值表 ——

function ExtremeTable<T>({ rows, columns, title, className = "" }: {
  rows: T[];
  columns: Column<T>[];
  title: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">{title}</div>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(_r, i) => i}
        dense
        bare
        emptyText="無達門檻且落在此方向的選手"
      />
    </div>
  );
}

// 全頁單一色規則：紅＝高於基準、藍＝低於基準（純方向，不含好壞判斷——好壞隨角色而異，
// 投手 ERA 越低越好）。與 PF 長條、聯盟對照同一條軸，避免紅色在同頁有兩種意思。
const delta = (v: number, digits: 2 | 3) => (
  <span className={v > 0 ? "text-accent" : v < 0 ? "text-up" : "text-faint"}>
    {v > 0 ? "+" : "−"}
    {Math.abs(v).toFixed(digits).replace(/^0\./, ".")}
  </span>
);

const batColumns: Column<VenueBatter>[] = [
  {
    header: "選手",
    nowrap: true,
    sticky: true,
    className: "font-sans",
    cell: (r) => <PlayerLink pid={r.player_id} name={r.name ?? r.player_id} />,
  },
  { header: "PA", align: "right", cell: (r) => r.venue_pa },
  { header: "此場 OPS", align: "right", cell: (r) => f3(r.venue_ops) },
  { header: "生涯 OPS", align: "right", cell: (r) => <span className="text-muted">{f3(r.career_ops)}</span> },
  { header: "差", align: "right", cell: (r) => delta(r.delta_ops, 3) },
];

const pitColumns: Column<VenuePitcher>[] = [
  {
    header: "選手",
    nowrap: true,
    sticky: true,
    className: "font-sans",
    cell: (r) => <PlayerLink pid={r.player_id} name={r.name ?? r.player_id} />,
  },
  { header: "IP", align: "right", cell: (r) => r.venue_ip },
  { header: "此場 ERA", align: "right", cell: (r) => f2(r.venue_era) },
  { header: "生涯 ERA", align: "right", cell: (r) => <span className="text-muted">{f2(r.career_era)}</span> },
  { header: "差", align: "right", cell: (r) => delta(r.delta_era, 2) },
];
