import { Card, PlayerLink } from "@/components/ui";

// 本季「年度獎項」競逐：各類別當季前五名（用現有排行資料即算，非歷史得獎次數）。
// rate 類（打擊率/防禦率…）套規定門檻（qualKey ≥ qualMin），避免少打席洗榜。
export type Cat = {
  key: string;
  label: string;
  fmt?: "i" | "f2" | "f3";
  dir?: "asc" | "desc"; // 預設 desc；防禦率/WHIP 等越低越好用 asc
  qual?: boolean; // 是否套規定門檻
};

type Row = Record<string, number | string | null>;

const fmtVal = (v: number, fmt?: Cat["fmt"]) =>
  fmt === "f3" ? v.toFixed(3).replace(/^0\./, ".") : fmt === "f2" ? v.toFixed(2) : String(v);

function top5(rows: Row[], cat: Cat, qualKey: string, qualMin: number): { id: string; name: string; val: number }[] {
  const dir = cat.dir ?? "desc";
  return rows
    .filter((r) => {
      const v = r[cat.key];
      if (v == null || v === "") return false;
      return cat.qual ? Number(r[qualKey] ?? 0) >= qualMin : true;
    })
    .map((r) => ({ id: String(r.player_id ?? ""), name: String(r.name ?? "—"), val: Number(r[cat.key]) }))
    .sort((a, b) => (dir === "asc" ? a.val - b.val : b.val - a.val))
    .slice(0, 5);
}

export function AwardRaces({
  rows, cats, qualKey, qualMin, note,
}: {
  rows: Row[];
  cats: Cat[];
  qualKey: string;
  qualMin: number;
  note?: string;
}) {
  return (
    <section className="mb-6">
      <h2 className="mb-1 text-lg font-semibold">本季獎項競逐 · 前五</h2>
      <p className="mb-3 text-[11px] text-faint">本季各獎項類別當前領先者（即時排名，非歷史得獎次數）。{note}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cats.map((cat) => {
          const list = top5(rows, cat, qualKey, qualMin);
          if (!list.length) return null;
          return (
            <Card key={cat.key} padding="p-3">
              <div className="mb-1.5 text-xs font-semibold text-muted">{cat.label}</div>
              <ol className="space-y-1 text-sm">
                {list.map((p, i) => (
                  <li key={`${p.id}-${i}`} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate">
                      <span className={`mr-1.5 inline-block w-3 text-right font-mono text-[11px] ${i === 0 ? "text-accent" : "text-faint"}`}>{i + 1}</span>
                      <PlayerLink pid={p.id} name={p.name} className={i === 0 ? "font-medium text-accent hover:underline" : "hover:underline"} />
                    </span>
                    <span className={`shrink-0 font-mono tabular-nums ${i === 0 ? "font-semibold text-ink" : "text-muted"}`}>{fmtVal(p.val, cat.fmt)}</span>
                  </li>
                ))}
              </ol>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
