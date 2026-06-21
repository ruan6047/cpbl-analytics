import Link from "next/link";
import { TeamBadge, TeamLogo } from "@/components/ui";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const SEGS = [
  { v: 0, label: "全年" },
  { v: 1, label: "上半季" },
  { v: 2, label: "下半季" },
];

// 特殊戰績欄位定義（key 對齊 /api/v1/special-records；皆 [W, L]）
const SPECIAL_COLS: { key: "artificial" | "natural" | "indoor" | "scored_first_against" | "intense" | "tailwind" | "headwind"; label: string; title: string }[] = [
  { key: "natural", label: "天然草皮", title: "天然草皮球場戰績（洲際/澄清湖/新莊/桃園…）" },
  { key: "artificial", label: "人工草皮", title: "人工草皮球場戰績（天母、大巨蛋）" },
  { key: "indoor", label: "室內", title: "室內球場戰績（僅大巨蛋）" },
  { key: "scored_first_against", label: "先失分", title: "對手先得分的場次戰績" },
  { key: "intense", label: "戰況激烈", title: "領先後被追平、最終才分出勝負的場次" },
  { key: "tailwind", label: "順風", title: "比賽中曾領先 ≥3 分的場次戰績" },
  { key: "headwind", label: "逆風", title: "比賽中曾落後 ≥3 分的場次戰績" },
];

// W-L 配對：依勝率上色（>.5 藍、<.5 紅），方便跨隊一覽
function WL({ p }: { p?: [number, number] }) {
  if (!p) return <span className="text-faint">—</span>;
  const [w, l] = p;
  const tot = w + l;
  if (tot === 0) return <span className="text-faint">0-0</span>;
  const pct = w / tot;
  const cls = pct > 0.5 ? "text-up" : pct < 0.5 ? "text-down" : "text-muted";
  return <span className={cls}>{w}-{l}</span>;
}

export default async function Home({ searchParams }: { searchParams: Promise<{ seg?: string; view?: string }> }) {
  const { seg = "0", view = "basic" } = await searchParams;
  const segCode = Number(seg) || 0;
  const isSpecial = view === "special";
  // 特殊戰績為全年累計，故 special view 一律用全年排名
  const effSeg = isSpecial ? 0 : segCode;
  const [{ season, items }, derived, special] = await Promise.all([
    api.officialStandings(effSeg),
    api.standings(),
    isSpecial ? api.specialRecords() : Promise.resolve(null),
  ]);
  // 團隊 OPS/ERA/WHIP 來自即時彙整端點，依 code 併入
  const adv = new Map(derived.standings.map((d) => [d.code, d]));
  const sp = new Map((special?.items ?? []).map((s) => [s.team_code, s]));

  const VIEWS = [
    { v: "basic", label: "基本數據" },
    { v: "special", label: "特殊戰績" },
  ];

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 本季戰績</h1>
        <p className="mt-2 text-sm text-muted">
          {isSpecial
            ? "依場地材質與賽況分類的隊級戰績（全年累計，逐場+逐局計算）。W-L 依勝率上色。"
            : "官方戰績（含和局/勝差/連勝敗/主客場/近十場）。團隊 OPS/ERA/WHIP 為攻守指標。"}
        </p>
      </header>

      <nav className="mb-4 flex flex-wrap items-center gap-2">
        {VIEWS.map((v) => (
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
        {!isSpecial && <span className="mx-1 h-4 w-px bg-line" />}
        {!isSpecial &&
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

      {items.length === 0 ? (
        <p className="text-sm text-faint">此區間尚無戰績（下半季可能未開始）。</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-muted">
              <tr>
                {isSpecial ? (
                  <>
                    <th className="whitespace-nowrap px-2.5 py-3 font-medium">#</th>
                    <th className="whitespace-nowrap px-2.5 py-3 font-medium">球隊</th>
                    {SPECIAL_COLS.map((c) => (
                      <th key={c.key} className="whitespace-nowrap px-2.5 py-3 font-medium" title={c.title}>{c.label}</th>
                    ))}
                    <th className="whitespace-nowrap px-2.5 py-3 font-medium" title="同對手 3 連戰且 3-0 的橫掃次數">橫掃</th>
                  </>
                ) : (
                  ["#", "球隊", "出賽", "勝-和-敗", "勝率", "勝差", "淘汰指數", "連勝/敗", "主場", "客場", "近十場", "OPS", "ERA", "WHIP"].map(
                    (h) => (
                      <th key={h} className="whitespace-nowrap px-2.5 py-3 font-medium"
                        title={h === "淘汰指數" ? "Magic Number：再贏幾場可確保不被該隊超越；領先隊不適用" : undefined}>{h}</th>
                    ),
                  )
                )}
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {items.map((t) => {
                if (isSpecial) {
                  const s = sp.get(t.team_code);
                  return (
                    <tr key={t.team_code} className="border-t border-line hover:bg-surface-2">
                      <td className="px-2.5 py-2.5 text-faint">{t.rank}</td>
                      <td className="whitespace-nowrap px-2.5 py-2.5 font-sans"><TeamBadge code={t.team_code} name={t.team_name} /></td>
                      {SPECIAL_COLS.map((c) => (
                        <td key={c.key} className="px-2.5 py-2.5"><WL p={s?.[c.key]} /></td>
                      ))}
                      <td className="px-2.5 py-2.5 text-muted">{s?.sweeps ? `${s.sweeps} 次` : "—"}</td>
                    </tr>
                  );
                }
                const a = adv.get(t.team_code);
                return (
                  <tr key={t.team_code} className="border-t border-line hover:bg-surface-2">
                    <td className="px-2.5 py-2.5 text-faint">{t.rank}</td>
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-sans"><TeamBadge code={t.team_code} name={t.team_name} /></td>
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
                      <span className="inline-flex flex-col items-center gap-1"><TeamLogo code={c.team_code} size={20} /></span>
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
