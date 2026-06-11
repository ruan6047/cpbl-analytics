import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const SORTS = [
  { key: "era", label: "防禦率" },
  { key: "whip", label: "WHIP" },
  { key: "w", label: "勝場" },
  { key: "sv", label: "救援" },
  { key: "hld", label: "中繼" },
  { key: "k9", label: "K9" },
  { key: "ip", label: "投球局數" },
];

export default async function PitchersPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort = "era" } = await searchParams;
  const { season, items } = await api.pitchingLeaders(sort);

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 投手排行</h1>
        <p className="mt-2 text-sm text-white/50">全隊投手名單（最低 20 局）。K9 = 三振 × 9 ÷ 投球局數。</p>
      </header>

      <nav className="mb-4 flex flex-wrap gap-2">
        {SORTS.map((s) => (
          <Link
            key={s.key}
            href={`/pitchers?sort=${s.key}`}
            className={`rounded-full px-3 py-1 text-sm transition ${
              sort === s.key ? "bg-emerald-500 text-black" : "bg-white/5 text-white/60 hover:bg-white/10"
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
              {["#", "球員", "隊", "G", "先發", "勝", "敗", "救援", "中繼", "局數", "防禦率", "WHIP", "K9"].map(
                (h) => (
                  <th key={h} className="whitespace-nowrap px-2.5 py-3 font-medium">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {items.map((p, i) => (
              <tr key={p.player_id} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-2.5 py-2.5 text-white/40">{i + 1}</td>
                <td className="whitespace-nowrap px-2.5 py-2.5 font-sans">{p.name ?? "—"}</td>
                <td className="whitespace-nowrap px-2.5 py-2.5 font-sans text-white/50">{p.team ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{p.g ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{p.gs ?? "—"}</td>
                <td className="px-2.5 py-2.5">{p.w ?? "—"}</td>
                <td className="px-2.5 py-2.5">{p.l ?? "—"}</td>
                <td className="px-2.5 py-2.5">{p.sv ?? "—"}</td>
                <td className="px-2.5 py-2.5">{p.hld ?? "—"}</td>
                <td className="px-2.5 py-2.5">{p.ip?.toFixed(1) ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-emerald-400">{p.era?.toFixed(2) ?? "—"}</td>
                <td className="px-2.5 py-2.5">{p.whip?.toFixed(2) ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-white/50">{p.k9?.toFixed(2) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
