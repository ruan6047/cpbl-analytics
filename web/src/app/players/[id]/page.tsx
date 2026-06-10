import Link from "next/link";
import { notFound } from "next/navigation";
import { OpsChart } from "@/components/ops-chart";
import { api } from "@/lib/api";

export default async function PlayerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await api.player(id);
  if (!data.player) notFound();

  const { player, seasons } = data;
  const chart = seasons.map((s) => ({ year: s.year, avg: s.avg }));

  return (
    <div>
      <Link href="/" className="text-sm text-white/40 hover:text-emerald-400">
        ← 回排行
      </Link>

      <header className="mt-4 mb-6 flex items-baseline gap-3">
        <h1 className="text-2xl font-bold">{player.name}</h1>
        <span className="text-sm text-white/40">
          {player.bats ?? ""} {player.throws ?? ""}
        </span>
      </header>

      <section className="mb-8 rounded-xl border border-white/10 p-4">
        <h2 className="mb-3 text-sm font-medium text-white/50">逐年打擊率 AVG</h2>
        <OpsChart data={chart} />
      </section>

      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-left text-white/50">
            <tr>
              {["年", "G", "PA", "AB", "H", "HR", "RBI", "BB", "SO", "AVG"].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {seasons.map((s) => (
              <tr key={s.year} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-3 py-2">{s.year}</td>
                <td className="px-3 py-2">{s.g}</td>
                <td className="px-3 py-2">{s.pa}</td>
                <td className="px-3 py-2">{s.ab}</td>
                <td className="px-3 py-2">{s.h}</td>
                <td className="px-3 py-2">{s.hr}</td>
                <td className="px-3 py-2">{s.rbi}</td>
                <td className="px-3 py-2">{s.bb}</td>
                <td className="px-3 py-2">{s.so}</td>
                <td className="px-3 py-2 text-emerald-400">{s.avg?.toFixed(3) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
