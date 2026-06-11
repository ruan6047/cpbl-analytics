import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const SORTS = [
  { key: "tc", label: "守備機會" },
  { key: "po", label: "刺殺" },
  { key: "a", label: "助殺" },
  { key: "dp", label: "雙殺" },
  { key: "e", label: "失誤" },
  { key: "fpct", label: "守備率" },
];

export default async function FieldingPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string; pos?: string }>;
}) {
  const { sort = "tc", pos } = await searchParams;
  const { season, positions, items } = await api.fielding(sort, pos);

  const chip = (active: boolean) =>
    `rounded-full px-3 py-1 text-sm transition ${
      active ? "bg-emerald-500 text-black" : "bg-white/5 text-white/60 hover:bg-white/10"
    }`;
  const q = (p?: string) => `/fielding?sort=${sort}${p ? `&pos=${encodeURIComponent(p)}` : ""}`;

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 守備數據</h1>
        <p className="mt-2 text-sm text-white/50">逐守備位置統計。守備率 = (刺殺+助殺) ÷ 守備機會。</p>
      </header>

      <nav className="mb-3 flex flex-wrap gap-2">
        <Link href={q(undefined)} className={chip(!pos)}>全部</Link>
        {positions.map((p) => (
          <Link key={p} href={q(p)} className={chip(pos === p)}>
            {p}
          </Link>
        ))}
      </nav>

      <nav className="mb-4 flex flex-wrap gap-2">
        {SORTS.map((s) => (
          <Link
            key={s.key}
            href={`/fielding?sort=${s.key}${pos ? `&pos=${encodeURIComponent(pos)}` : ""}`}
            className={`rounded px-2.5 py-1 text-xs transition ${
              sort === s.key ? "bg-white/15 text-white" : "bg-white/5 text-white/50 hover:bg-white/10"
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
              {["#", "球員", "隊", "守位", "G", "守備機會", "刺殺", "助殺", "失誤", "雙殺", "守備率"].map(
                (h) => (
                  <th key={h} className="whitespace-nowrap px-2.5 py-3 font-medium">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {items.map((f, i) => (
              <tr key={`${f.player_id}-${f.pos}`} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-2.5 py-2.5 text-white/40">{i + 1}</td>
                <td className="whitespace-nowrap px-2.5 py-2.5 font-sans">{f.name ?? "—"}</td>
                <td className="whitespace-nowrap px-2.5 py-2.5 font-sans text-white/50">{f.team ?? "—"}</td>
                <td className="whitespace-nowrap px-2.5 py-2.5 font-sans text-white/60">{f.pos}</td>
                <td className="px-2.5 py-2.5 text-white/50">{f.g ?? "—"}</td>
                <td className="px-2.5 py-2.5">{f.tc ?? "—"}</td>
                <td className="px-2.5 py-2.5">{f.po ?? "—"}</td>
                <td className="px-2.5 py-2.5">{f.a ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-rose-400/80">{f.e ?? "—"}</td>
                <td className="px-2.5 py-2.5">{f.dp ?? "—"}</td>
                <td className="px-2.5 py-2.5 text-emerald-400">{f.fpct?.toFixed(3) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
