import Link from "next/link";
import { PlayerLink } from "@/components/ui";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata = { title: "成績預測 | CPBL 分析" };

const STATS = [
  { key: "ops", label: "OPS" },
  { key: "avg", label: "打擊率" },
  { key: "obp", label: "上壘率" },
  { key: "slg", label: "長打率" },
] as const;

const f3 = (v: number | null) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));

export default async function ProjectionsPage({ searchParams }: { searchParams: Promise<{ stat?: string }> }) {
  const sp = await searchParams;
  const stat = STATS.some((s) => s.key === sp.stat) ? (sp.stat as string) : "ops";
  const data = await api.projections(stat);

  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold tracking-tight">成績預測</h1>
      <p className="mb-4 text-sm text-muted">
        LightGBM 打擊率能力投影（以逐年成績 lag 1–3 季 + 年齡 + 聯盟均值訓練，時間切分回測須勝過
        Marcel baseline 才採用）。目標季 {data.target_year ?? "—"}・模型 {data.model_version ?? "—"}。
        單場勝負預測見 <Link href="/predict" className="text-accent hover:underline">賽事預測</Link>。
      </p>
      <div className="mb-4 flex gap-2">
        {STATS.map((s) => (
          <Link key={s.key} href={`/projections?stat=${s.key}`}
            className={s.key === stat
              ? "rounded-full bg-cpbl px-3 py-1 text-sm font-semibold text-white"
              : "rounded-full border border-line bg-surface px-3 py-1 text-sm text-muted hover:text-ink"}>
            {s.label}
          </Link>
        ))}
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-3 py-2 text-right">#</th>
              <th className="px-3 py-2">球員</th>
              <th className="px-3 py-2 text-right">投影 {stat.toUpperCase()}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r, i) => (
              <tr key={r.player_id} className="border-b border-line/50 last:border-0">
                <td className="px-3 py-1.5 text-right font-mono text-faint">{i + 1}</td>
                <td className="px-3 py-1.5"><PlayerLink pid={r.player_id} name={r.name ?? r.player_id} /></td>
                <td className="px-3 py-1.5 text-right font-mono font-semibold tabular-nums">{f3(r.predicted)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-faint">
        投影為賽季開始前的能力估計（非當下狀態）；rate stat 限定，計數型（HR/RBI 總數）需上場時間模型故不提供。
      </p>
    </div>
  );
}
