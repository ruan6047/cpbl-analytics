import Link from "next/link";
import { PlayerLink } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata = { title: "成績預測 | CPBL 分析" };

const BAT_STATS = [
  { key: "ops", label: "OPS" },
  { key: "avg", label: "打擊率" },
  { key: "obp", label: "上壘率" },
  { key: "slg", label: "長打率" },
] as const;
const PIT_STATS = [
  { key: "era", label: "ERA" },
  { key: "whip", label: "WHIP" },
  { key: "k9", label: "K/9" },
  { key: "bb9", label: "BB/9" },
] as const;

const f3 = (v: number | null) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));
const f2 = (v: number | null) => (v == null ? "—" : Number(v).toFixed(2));

export default async function ProjectionsPage({
  searchParams,
}: { searchParams: Promise<{ stat?: string; role?: string }> }) {
  const sp = await searchParams;
  const role = sp.role === "pitching" ? "pitching" : "batting";
  const STATS = role === "pitching" ? PIT_STATS : BAT_STATS;
  const stat = STATS.some((s) => s.key === sp.stat) ? (sp.stat as string) : STATS[0].key;
  const data = role === "pitching"
    ? await api.pitchingProjections(stat)
    : await api.projections(stat);
  const fmt = role === "pitching" ? f2 : f3;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold tracking-tight">成績預測</h1>
      <p className="mb-4 text-sm text-muted">
        {role === "pitching" ? (
          <>Marcel 投手能力投影（加權前 3 季 + 回歸均值 + 年齡曲線；LightGBM 挑戰者於時間切分回測
          3/4 項落敗故不採用——打不贏 baseline 的模型不上線）。</>
        ) : (
          <>LightGBM 打擊率能力投影（以逐年成績 lag 1–3 季 + 年齡 + 聯盟均值訓練，時間切分回測須勝過
          Marcel baseline 才採用）。</>
        )}
        目標季 {data.target_year ?? "—"}・模型 {data.model_version ?? "—"}。
        單場勝負預測見 <Link href="/predict" className="text-accent hover:underline">賽事預測</Link>。
      </p>
      <div className="mb-3 flex gap-2">
        {([["batting", "打者"], ["pitching", "投手"]] as const).map(([r, label]) => (
          <Link key={r} href={`/projections?role=${r}`}
            className={r === role
              ? "rounded-lg bg-ink px-3 py-1 text-sm font-bold text-surface"
              : "rounded-lg border border-line bg-surface px-3 py-1 text-sm text-muted hover:text-ink"}>
            {label}
          </Link>
        ))}
      </div>
      <div className="mb-4 flex gap-2">
        {STATS.map((s) => (
          <Link key={s.key} href={`/projections?role=${role}&stat=${s.key}`}
            className={s.key === stat
              ? "rounded-full bg-cpbl px-3 py-1 text-sm font-semibold text-white"
              : "rounded-full border border-line bg-surface px-3 py-1 text-sm text-muted hover:text-ink"}>
            {s.label}
          </Link>
        ))}
      </div>
      <DataTable
        columns={[
          { header: "#", cell: (_r, i) => i + 1, align: "right", className: "text-faint", width: "3rem" },
          { header: "球員", cell: (r) => <PlayerLink pid={r.player_id} name={r.name ?? r.player_id} />, className: "font-sans" },
          { header: `投影 ${stat.toUpperCase()}`, cell: (r) => fmt(r.predicted), align: "right", className: "font-semibold" },
        ] satisfies Column<(typeof data.items)[number]>[]}
        rows={data.items}
        rowKey={(r) => r.player_id}
        dense
      />
      <p className="mt-3 text-xs text-faint">
        投影為賽季開始前的能力估計（非當下狀態）；rate stat 限定，計數型（HR/RBI、勝場/三振總數）需上場時間模型故不提供。
        {role === "pitching" && " ERA/WHIP/BB/9 低為佳（升冪）、K/9 高為佳（降冪）。"}
      </p>
    </div>
  );
}
