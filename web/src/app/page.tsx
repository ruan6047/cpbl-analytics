import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const SEGS = [
  { v: 0, label: "全年" },
  { v: 1, label: "上半季" },
  { v: 2, label: "下半季" },
];

const ABBR: Record<string, string> = {
  AAA011: "味全", ACN011: "兄弟", ADD011: "統一", AEO011: "富邦", AJL011: "樂天", AKP011: "台鋼",
};

export default async function Home({ searchParams }: { searchParams: Promise<{ seg?: string }> }) {
  const { seg = "0" } = await searchParams;
  const segCode = Number(seg) || 0;
  const [{ season, items }, derived] = await Promise.all([
    api.officialStandings(segCode),
    api.standings(),
  ]);
  // 團隊 OPS/ERA/WHIP 來自即時彙整端點，依 code 併入
  const adv = new Map(derived.standings.map((d) => [d.code, d]));

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 本季戰績</h1>
        <p className="mt-2 text-sm text-white/50">官方戰績（含和局/勝差/連勝敗/主客場/近十場）。團隊 OPS/ERA/WHIP 為攻守指標。</p>
      </header>

      <nav className="mb-4 flex gap-2">
        {SEGS.map((s) => (
          <Link
            key={s.v}
            href={`/?seg=${s.v}`}
            className={`rounded-full px-3 py-1 text-sm transition ${
              segCode === s.v ? "bg-emerald-500 text-black" : "bg-white/5 text-white/60 hover:bg-white/10"
            }`}
          >
            {s.label}
          </Link>
        ))}
      </nav>

      {items.length === 0 ? (
        <p className="text-sm text-white/40">此區間尚無戰績（下半季可能未開始）。</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-white/5 text-left text-white/50">
              <tr>
                {["#", "球隊", "出賽", "勝-和-敗", "勝率", "勝差", "連勝/敗", "主場", "客場", "近十場", "OPS", "ERA", "WHIP"].map(
                  (h) => (
                    <th key={h} className="whitespace-nowrap px-2.5 py-3 font-medium">{h}</th>
                  ),
                )}
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {items.map((t) => {
                const a = adv.get(t.team_code);
                return (
                  <tr key={t.team_code} className="border-t border-white/5 hover:bg-white/5">
                    <td className="px-2.5 py-2.5 text-white/40">{t.rank}</td>
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-sans">{t.team_name}</td>
                    <td className="px-2.5 py-2.5 text-white/50">{t.g}</td>
                    <td className="px-2.5 py-2.5">{t.w}-{t.t}-{t.l}</td>
                    <td className="px-2.5 py-2.5 text-emerald-400">{t.win_pct?.toFixed(3) ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-white/70">{t.gb === 0 ? "—" : t.gb}</td>
                    <td className="px-2.5 py-2.5 text-white/60">{t.streak ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-white/50">{t.home_record ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-white/50">{t.away_record ?? "—"}</td>
                    <td className="px-2.5 py-2.5 text-white/50">{t.last10 ?? "—"}</td>
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

      {items.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-1 text-lg font-semibold">對戰成績</h2>
          <p className="mb-3 text-[11px] text-white/30">每列為該隊對各對手的 勝-和-敗（{SEGS.find((s) => s.v === segCode)?.label}）。</p>
          <div className="overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-left text-white/50">
                <tr>
                  <th className="whitespace-nowrap px-2.5 py-3 font-medium">球隊＼對手</th>
                  {items.map((c) => (
                    <th key={c.team_code} className="px-2.5 py-3 text-center font-medium">{ABBR[c.team_code] ?? c.team_name}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {items.map((row) => (
                  <tr key={row.team_code} className="border-t border-white/5 hover:bg-white/5">
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-sans">{row.team_name}</td>
                    {items.map((col) => (
                      <td key={col.team_code} className="px-2.5 py-2.5 text-center text-white/70">
                        {col.team_code === row.team_code ? (
                          <span className="text-white/15">—</span>
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
