import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const SORTS = [
  { key: "ops", label: "OPS" },
  { key: "avg", label: "打擊率" },
  { key: "obp", label: "上壘率" },
  { key: "slg", label: "長打率" },
  { key: "hr", label: "全壘打" },
  { key: "rbi", label: "打點" },
  { key: "h", label: "安打" },
  { key: "r", label: "得分" },
  { key: "sb", label: "盜壘" },
];

const fmt3 = (v: number | null) => (v === null ? "—" : v.toFixed(3));

export default async function BattersPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort = "ops" } = await searchParams;
  const { season, items } = await api.battingLeaders(sort);

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 打者進階排行</h1>
        <p className="mt-2 text-sm text-white/50">
          僅列達規定打席之合格打者(本季進行中,人數隨賽季增加)。OPS+ 100 為聯盟平均。
        </p>
      </header>

      <nav className="mb-4 flex flex-wrap gap-2">
        {SORTS.map((s) => (
          <Link
            key={s.key}
            href={`/batters?sort=${s.key}`}
            className={`rounded-full px-3 py-1 text-sm transition ${
              sort === s.key
                ? "bg-emerald-500 text-black"
                : "bg-white/5 text-white/60 hover:bg-white/10"
            }`}
          >
            {s.label}
          </Link>
        ))}
      </nav>

      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-left text-white/50">
            <tr>
              {["#", "球員", "隊", "G", "PA", "AB", "R", "H", "2B", "3B", "HR", "RBI", "BB", "SO", "SB", "CS", "打擊率", "上壘率", "長打率", "OPS"].map(
                (h) => (
                  <th key={h} className="whitespace-nowrap px-2.5 py-3 font-medium">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {items.map((b, i) => (
              <tr key={b.player_id} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-2.5 py-2.5 text-white/40">{i + 1}</td>
                <td className="whitespace-nowrap px-2.5 py-2.5 font-sans">{b.name ?? "—"}</td>
                <td className="whitespace-nowrap px-2.5 py-2.5 font-sans text-white/50">{b.team ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{b.g ?? "—"}</td>
                <td className="px-2.5 py-2.5">{b.pa ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{b.ab ?? "—"}</td>
                <td className="px-2.5 py-2.5">{b.r ?? "—"}</td>
                <td className="px-2.5 py-2.5">{b.h ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{b.b2 ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{b.b3 ?? "—"}</td>
                <td className="px-2.5 py-2.5">{b.hr ?? "—"}</td>
                <td className="px-2.5 py-2.5">{b.rbi ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{b.bb ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{b.so ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-emerald-400/80">{b.sb ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{b.cs ?? "—"}</td>
                <td className="px-2.5 py-2.5">{fmt3(b.avg)}</td>
                <td className="px-2.5 py-2.5">{fmt3(b.obp)}</td>
                <td className="px-2.5 py-2.5">{fmt3(b.slg)}</td>
                <td className="px-2.5 py-2.5 text-emerald-400">{fmt3(b.ops)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
