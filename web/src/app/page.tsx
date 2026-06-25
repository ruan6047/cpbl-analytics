import Link from "next/link";
import { TeamBadge, TeamLogo } from "@/components/ui";
import { StandingsTrend } from "@/components/standings-trend";
import { YearSelect } from "@/components/year-select";
import { api } from "@/lib/api";
import type { OfficialStanding, SpecialRecord, WL, WTL } from "@/lib/api";
import { teamPageCode } from "@/lib/teams";

export const dynamic = "force-dynamic";

const SEGS = [
  { v: 0, label: "全年" },
  { v: 1, label: "上半季" },
  { v: 2, label: "下半季" },
];

// 球隊徽章連到各隊獨立頁；改名/轉賣的歷史隊連到現役 franchise 頁；已解散隊不連
function LinkedTeam({ code, name }: { code: string; name: string }) {
  const tc = teamPageCode(code);
  if (!tc) return <TeamBadge code={code} name={name} />;
  return (
    <Link href={`/teams/${tc}`} className="hover:underline">
      <TeamBadge code={code} name={name} />
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

// 系列 勝-平-負：依勝(>負)藍、負(>勝)紅上色
function WtlCell({ p }: { p?: WTL }) {
  if (!p) return <span className="text-faint">—</span>;
  const [w, t, l] = p;
  if (w + t + l === 0) return <span className="text-faint">—</span>;
  const cls = w > l ? "text-up" : l > w ? "text-down" : "text-muted";
  return <span className={cls}>{w}-{t}-{l}</span>;
}

// 特殊戰績分主題小表配置
type SpCol = { key: keyof SpecialRecord; label: string; title?: string; count?: boolean; unit?: string; wtl?: boolean };
type SpSection = { title: string; note?: string; cols: SpCol[] };

const SPECIAL_SECTIONS: SpSection[] = [
  {
    title: "場地",
    cols: [
      { key: "natural", label: "天然草皮", title: "天然草皮球場（洲際/澄清湖/新莊/桃園…）" },
      { key: "artificial", label: "人工草皮", title: "人工草皮球場（天母、大巨蛋）" },
      { key: "indoor", label: "室內", title: "室內球場（僅大巨蛋）" },
    ],
  },
  {
    title: "比分型",
    cols: [
      { key: "one_run", label: "一分差", title: "最終分差 1 分的場次" },
      { key: "blowout", label: "大勝大敗", title: "分差 ≥5 分的場次" },
      { key: "shutout", label: "完封 勝-被", title: "完封勝（對手 0 分）- 被完封（我方 0 分）次數" },
      { key: "comeback", label: "逆轉 勝-被", title: "逆轉勝（曾落後仍勝）- 被逆轉（曾領先卻敗）次數" },
    ],
  },
  {
    title: "賽況軌跡",
    cols: [
      { key: "scored_first", label: "得分先馳", title: "我方全場最先得分的場次" },
      { key: "scored_first_against", label: "先失分", title: "對手最先得分的場次" },
      { key: "intense", label: "戰況激烈", title: "領先後被追平、最終才分勝負" },
      { key: "tailwind", label: "順風", title: "比賽中曾領先 ≥3 分" },
      { key: "headwind", label: "逆風", title: "比賽中曾落後 ≥3 分" },
      { key: "big_inning", label: "大局", title: "我方單局曾得 ≥4 分" },
    ],
  },
  {
    title: "終局與守備",
    cols: [
      { key: "extra", label: "延長賽", title: "打超過 9 局的場次" },
      { key: "save", label: "救援守成 成-敗", title: "第 8 局結束領先 1–3 分（救援情境），守成獲勝-失敗次數" },
      { key: "errorful", label: "失誤場", title: "我方該場有失誤（≥1）的場次" },
    ],
  },
  {
    title: "賽程",
    cols: [
      { key: "weekday", label: "平日", title: "週一至週五" },
      { key: "weekend", label: "假日", title: "週六、週日" },
    ],
  },
  {
    title: "連勝連敗",
    note: "全季最長連續段；和局中斷連勝/連敗",
    cols: [
      { key: "max_win_streak", label: "最大連勝", title: "本季最長連勝場數", count: true, unit: "場" },
      { key: "max_lose_streak", label: "最大連敗", title: "本季最長連敗場數", count: true, unit: "場" },
    ],
  },
  {
    title: "對手先發",
    note: "對手先發投手慣用手未知者不計",
    cols: [
      { key: "vs_lhp", label: "vs 左投", title: "對手先發為左投的場次" },
      { key: "vs_rhp", label: "vs 右投", title: "對手先發為右投的場次" },
    ],
  },
  {
    title: "系列賽",
    note: "連戰（同對手、間隔 ≤2 天）拿多數場＝系列勝",
    cols: [
      { key: "series3", label: "三連戰 勝-平-負", title: "三連戰系列：多數獲勝記一勝（2-1 或 3-0 同記）；1-1-1 平", wtl: true },
      { key: "sweeps", label: "三連戰橫掃", title: "三連戰 3-0 次數（系列勝的子集）", count: true },
      { key: "swept", label: "被三連戰橫掃", title: "三連戰 0-3 次數", count: true },
      { key: "series2", label: "雙連賽 勝-平-負", title: "雙連賽：2-0 勝(橫掃)／1-1 平／0-2 負(被橫掃)", wtl: true },
    ],
  },
];

// 再見致勝方式顯示順序（只渲染實際發生的類型）
const WALKOFF_TYPE_ORDER = ["安打", "全壘打", "保送", "觸身", "犧牲打", "失誤", "野手選擇", "趁傳進壘", "暴投", "捕逸", "其他"];

function SpecialTable({ section, rows, sp }: { section: SpSection; rows: OfficialStanding[]; sp: Map<string, SpecialRecord> }) {
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink">
        {section.title}
        {section.note && <span className="ml-2 text-[11px] font-normal text-faint">{section.note}</span>}
      </h3>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-muted">
            <tr>
              <th className="whitespace-nowrap px-2.5 py-2.5 font-medium">球隊</th>
              {section.cols.map((c) => (
                <th key={c.key} className="whitespace-nowrap px-2.5 py-2.5 font-medium" title={c.title}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {rows.map((t) => {
              const s = sp.get(t.team_code);
              return (
                <tr key={t.team_code} className="border-t border-line hover:bg-surface-2">
                  <td className="whitespace-nowrap px-2.5 py-2 font-sans"><LinkedTeam code={t.team_code} name={t.team_name} /></td>
                  {section.cols.map((c) => (
                    <td key={c.key} className="px-2.5 py-2">
                      {c.count ? (
                        <span className="text-muted">{(s?.[c.key] as number) ? `${s![c.key]} ${c.unit ?? "次"}` : "—"}</span>
                      ) : c.wtl ? (
                        <WtlCell p={s?.[c.key] as WTL | undefined} />
                      ) : (
                        <WLCell p={s?.[c.key] as WL | undefined} />
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MonthsTable({ rows, sp }: { rows: OfficialStanding[]; sp: Map<string, SpecialRecord> }) {
  const monthSet = new Set<number>();
  sp.forEach((s) => Object.keys(s.months).forEach((m) => monthSet.add(Number(m))));
  const months = [...monthSet].sort((a, b) => a - b);
  if (months.length === 0) return null;
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink">月份趨勢</h3>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-muted">
            <tr>
              <th className="whitespace-nowrap px-2.5 py-2.5 font-medium">球隊</th>
              {months.map((m) => (
                <th key={m} className="whitespace-nowrap px-2.5 py-2.5 font-medium">{m} 月</th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {rows.map((t) => {
              const s = sp.get(t.team_code);
              return (
                <tr key={t.team_code} className="border-t border-line hover:bg-surface-2">
                  <td className="whitespace-nowrap px-2.5 py-2 font-sans"><LinkedTeam code={t.team_code} name={t.team_name} /></td>
                  {months.map((m) => (
                    <td key={m} className="px-2.5 py-2"><WLCell p={s?.months[String(m)]} /></td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function WalkoffTable({ rows, sp }: { rows: OfficialStanding[]; sp: Map<string, SpecialRecord> }) {
  // 動態類型欄：只取實際發生過的致勝方式，依固定順序排列
  const present = new Set<string>();
  sp.forEach((s) => Object.keys(s.walkoff_types ?? {}).forEach((t) => present.add(t)));
  const types = WALKOFF_TYPE_ORDER.filter((t) => present.has(t));
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink">
        再見 [Walk-off]
        <span className="ml-2 text-[11px] font-normal text-faint">主隊最終局下半超前致勝；致勝方式只列實際發生的類型</span>
      </h3>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-muted">
            <tr>
              <th className="whitespace-nowrap px-2.5 py-2.5 font-medium">球隊</th>
              <th className="whitespace-nowrap px-2.5 py-2.5 font-medium" title="主隊最終局下半超前致勝的場次">再見勝</th>
              {types.map((t) => (
                <th key={t} className="whitespace-nowrap px-2.5 py-2.5 font-medium">{t}</th>
              ))}
              <th className="whitespace-nowrap px-2.5 py-2.5 font-medium" title="客場吞再見敗的場次">被再見</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {rows.map((t) => {
              const s = sp.get(t.team_code);
              return (
                <tr key={t.team_code} className="border-t border-line hover:bg-surface-2">
                  <td className="whitespace-nowrap px-2.5 py-2 font-sans"><LinkedTeam code={t.team_code} name={t.team_name} /></td>
                  <td className="px-2.5 py-2 text-up">{s?.walkoff ? `${s.walkoff} 次` : "—"}</td>
                  {types.map((ty) => (
                    <td key={ty} className="px-2.5 py-2 text-muted">{s?.walkoff_types?.[ty] ?? "—"}</td>
                  ))}
                  <td className="px-2.5 py-2 text-down">{s?.walked_off ? `${s.walked_off} 次` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const LEVELS = [
  { v: "A", label: "一軍" },
  { v: "D", label: "二軍" },
];

export default async function Home({ searchParams }: { searchParams: Promise<{ seg?: string; view?: string; year?: string; kind?: string }> }) {
  const { seg = "0", view = "basic", year: yearParam, kind: kindParam } = await searchParams;
  const segCode = Number(seg) || 0;
  const kind = kindParam === "D" ? "D" : "A";
  const isMinor = kind === "D";
  const { years } = await api.seasons(kind);
  const currentYear = years[0] ?? new Date().getFullYear();
  const selectedYear = yearParam ? Number(yearParam) : currentYear;
  // 官方 rich view（半季/特殊戰績/即時 OPS）只在「一軍當季」；二軍與歷年皆由 games 即時算
  const useOfficial = !isMinor && selectedYear === currentYear;
  const isSpecial = view === "special" && useOfficial;
  const effSeg = isSpecial ? segCode : 0;
  const [{ season, items }, derived, special, trend] = await Promise.all([
    api.officialStandings(effSeg, useOfficial ? undefined : selectedYear, kind),
    useOfficial ? api.standings() : Promise.resolve({ standings: [] }),
    isSpecial ? api.specialRecords() : Promise.resolve(null),
    isSpecial ? Promise.resolve(null) : api.standingsTrend(useOfficial ? undefined : selectedYear, kind),
  ]);
  // 團隊 OPS/ERA/WHIP 來自即時彙整端點，依 code 併入
  const adv = new Map(derived.standings.map((d) => [d.code, d]));
  const sp = new Map((special?.items ?? []).map((s) => [s.team_code, s]));

  const VIEWS = [
    { v: "basic", label: "基本數據" },
    { v: "special", label: "特殊戰績" },
  ];
  const levelLabel = isMinor ? "二軍" : "";
  const subtitle = isMinor ? `${levelLabel}戰績` : useOfficial ? "本季戰績" : "歷年戰績";

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · {subtitle}</h1>
        <p className="mt-2 text-sm text-muted">
          {!useOfficial
            ? `${isMinor ? "二軍" : "歷史"}年度戰績（由逐場結果即時計算：勝-和-敗/勝率/勝差/對戰/主客場）。`
            : isSpecial
            ? "依場地、比分型、賽況軌跡、賽程與對手分類的隊級戰績（全年累計，逐場+逐局計算）。配對數值依勝率／正向比例以藍↔紅上色。"
            : "官方戰績（含和局/勝差/連勝敗/主客場/近十場）。團隊 OPS/ERA/WHIP 為攻守指標。"}
        </p>
      </header>

      <nav className="mb-4 flex flex-wrap items-center gap-2">
        {LEVELS.map((lv) => (
          <Link
            key={lv.v}
            href={lv.v === "A" ? "/" : "/?kind=D"}
            className={`rounded-full px-3 py-1 text-sm font-medium transition ${
              (lv.v === "D") === isMinor ? "bg-ink text-white" : "bg-surface-2 text-muted hover:bg-surface-2"
            }`}
          >
            {lv.label}
          </Link>
        ))}
        <span className="mx-1 h-4 w-px bg-line" />
        <YearSelect years={years} value={selectedYear} kind={kind} />
        {useOfficial && <span className="mx-1 h-4 w-px bg-line" />}
        {useOfficial && VIEWS.map((v) => (
          <Link
            key={v.v}
            href={`/?view=${v.v}${v.v === "basic" ? `&seg=${segCode}` : ""}`}
            className={`rounded-full px-3 py-1 text-sm font-medium transition ${
              (v.v === "special") === isSpecial ? "bg-accent text-white" : "bg-surface-2 text-muted hover:bg-surface-2"
            }`}
          >
            {v.label}
          </Link>
        ))}
        {useOfficial && !isSpecial && <span className="mx-1 h-4 w-px bg-line" />}
        {useOfficial && !isSpecial &&
          SEGS.map((s) => (
            <Link
              key={s.v}
              href={`/?seg=${s.v}`}
              className={`rounded-full px-3 py-1 text-sm transition ${
                segCode === s.v ? "bg-ink text-white" : "bg-surface-2 text-muted hover:bg-surface-2"
              }`}
            >
              {s.label}
            </Link>
          ))}
      </nav>

      {isSpecial ? (
        items.length === 0 ? (
          <p className="text-sm text-faint">尚無戰績資料。</p>
        ) : (
          <>
            {SPECIAL_SECTIONS.map((sec) => (
              <SpecialTable key={sec.title} section={sec} rows={items} sp={sp} />
            ))}
            <WalkoffTable rows={items} sp={sp} />
            <MonthsTable rows={items} sp={sp} />
          </>
        )
      ) : items.length === 0 ? (
        <p className="text-sm text-faint">此區間尚無戰績（下半季可能未開始）。</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-muted">
              <tr>
                {["#", "球隊", "出賽", "勝-和-敗", "勝率", "勝差", "淘汰指數", "連勝/敗", "主場", "客場", "近十場", "OPS", "ERA", "WHIP"].map(
                  (h) => (
                    <th key={h} className="whitespace-nowrap px-2.5 py-3 font-medium"
                      title={h === "淘汰指數" ? "Magic Number：再贏幾場可確保不被該隊超越；領先隊不適用" : undefined}>{h}</th>
                  ),
                )}
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {items.map((t) => {
                const a = adv.get(t.team_code);
                return (
                  <tr key={t.team_code} className="border-t border-line hover:bg-surface-2">
                    <td className="px-2.5 py-2.5 text-faint">{t.rank}</td>
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-sans"><LinkedTeam code={t.team_code} name={t.team_name} /></td>
                    <td className="px-2.5 py-2.5 text-muted">{t.g}</td>
                    <td className="px-2.5 py-2.5">{t.w}-{t.t}-{t.l}</td>
                    <td className="px-2.5 py-2.5 text-accent">{t.win_pct?.toFixed(3) ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-muted">{t.gb === 0 ? "—" : t.gb}</td>
                    <td className="px-2.5 py-2.5 text-muted">{t.elim && t.elim !== "" ? t.elim : "—"}</td>
                    <td className="px-2.5 py-2.5 text-muted">{t.streak ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-muted">{t.home_record ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-muted">{t.away_record ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-muted">{t.last10 ?? "—"}</td>
                    <td className="px-2.5 py-2.5">{a?.ops?.toFixed(3) ?? "—"}</td>
                    <td className="px-2.5 py-2.5">{a?.era?.toFixed(2) ?? "—"}</td>
                    <td className="px-2.5 py-2.5">{a?.whip?.toFixed(2) ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {items.length > 0 && !isSpecial && trend && trend.points.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-1 text-lg font-semibold">戰績走勢</h2>
          <p className="mb-3 text-[11px] text-faint">各隊累積勝-敗差（高於 .500 的場數）隨賽季變化；0 即五成勝率，越高越強。</p>
          <div className="rounded-xl border border-line p-4">
            <StandingsTrend teams={trend.teams} points={trend.points} names={trend.names} />
          </div>
        </section>
      )}

      {items.length > 0 && !isSpecial && (
        <section className="mt-8">
          <h2 className="mb-1 text-lg font-semibold">對戰成績</h2>
          <p className="mb-3 text-[11px] text-faint">每列為該隊對各對手的 勝-和-敗（{SEGS.find((s) => s.v === segCode)?.label}）。</p>
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-muted">
                <tr>
                  <th className="whitespace-nowrap px-2.5 py-3 font-medium">球隊＼對手</th>
                  {items.map((c) => (
                    <th key={c.team_code} className="px-2.5 py-3 text-center font-medium">
                      <span className="inline-flex flex-col items-center gap-1"><TeamLogo code={c.team_code} name={c.team_name} size={20} /></span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {items.map((row) => (
                  <tr key={row.team_code} className="border-t border-line hover:bg-surface-2">
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-sans"><TeamBadge code={row.team_code} name={row.team_name} /></td>
                    {items.map((col) => (
                      <td key={col.team_code} className="px-2.5 py-2.5 text-center text-muted">
                        {col.team_code === row.team_code ? (
                          <span className="text-faint">—</span>
                        ) : (
                          row.h2h?.[col.team_code] ?? "—"
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
