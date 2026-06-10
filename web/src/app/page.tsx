import Link from "next/link";
import { api } from "@/lib/api";

const STATS = [
  { key: "ops", label: "OPS" },
  { key: "obp", label: "上壘率 OBP" },
  { key: "slg", label: "長打率 SLG" },
  { key: "avg", label: "打擊率 AVG" },
];

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ stat?: string }>;
}) {
  const { stat = "ops" } = await searchParams;
  const data = await api.battingProjections(stat, 25);

  return (
    <div>
      <section className="mb-8">
        <h1 className="text-2xl font-bold">
          {data.target_year ?? ""} 球季成績預測排行
        </h1>
        <p className="mt-2 text-sm text-white/50">
          以 Marcel 為 baseline,LightGBM 在時間切分回測上勝出後採用。
          模型版本 <code className="text-emerald-400">{data.model_version ?? "—"}</code>。
        </p>
      </section>

      <nav className="mb-4 flex gap-2">
        {STATS.map((s) => (
          <Link
            key={s.key}
            href={`/?stat=${s.key}`}
            className={`rounded-full px-3 py-1 text-sm transition ${
              stat === s.key
                ? "bg-emerald-500 text-black"
                : "bg-white/5 text-white/60 hover:bg-white/10"
            }`}
          >
            {s.label}
          </Link>
        ))}
      </nav>

      <div className="overflow-hidden rounded-xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-left text-white/50">
            <tr>
              <th className="px-4 py-3 font-medium">#</th>
              <th className="px-4 py-3 font-medium">球員</th>
              <th className="px-4 py-3 text-right font-medium">預測 {stat.toUpperCase()}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((p, i) => (
              <tr key={p.player_id} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-4 py-3 text-white/40">{i + 1}</td>
                <td className="px-4 py-3">
                  <Link href={`/players/${p.player_id}`} className="hover:text-emerald-400">
                    {p.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right font-mono tabular-nums">
                  {p.predicted.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
