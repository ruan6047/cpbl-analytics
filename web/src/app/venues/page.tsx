import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata = { title: "球場 | CPBL 分析" };

const num = (v: number | null) => (v == null ? "—" : Number(v).toLocaleString());

function DistBar({ label, ft, max = 410 }: { label: string; ft: number | null; max?: number }) {
  if (ft == null) return null;
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-8 text-faint">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line/60">
        <div className="h-full rounded-full bg-accent/70" style={{ width: `${(ft / max) * 100}%` }} />
      </div>
      <span className="w-10 text-right font-mono tabular-nums text-muted">{ft} 呎</span>
    </div>
  );
}

export default async function VenuesPage() {
  const data = await api.venues();
  const active = data.items.filter((v) => (v.games_played ?? 0) > 0);
  const historic = data.items.filter((v) => !v.games_played && v.first_year != null);

  const card = (v: (typeof data.items)[number]) => (
    <div key={v.venue} className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-base font-bold text-ink">{v.full_name ?? v.venue}</h3>
        <span className="shrink-0 text-xs text-faint">{v.city}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
        {v.indoor && <span className="rounded-full bg-cpbl/10 px-2 py-0.5 font-medium text-cpbl">室內</span>}
        {v.turf && (
          <span className="rounded-full bg-line/60 px-2 py-0.5 text-muted">
            {v.turf === "artificial" ? "人工草皮" : "天然草皮"}
          </span>
        )}
        {v.big_screen && <span className="rounded-full bg-line/60 px-2 py-0.5 text-muted">大螢幕</span>}
        {v.home_teams && <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">{v.home_teams} 主場</span>}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="font-mono text-lg font-bold tabular-nums text-ink">{num(v.capacity)}</div>
          <div className="text-[11px] text-faint">容量</div>
        </div>
        <div>
          <div className="font-mono text-lg font-bold tabular-nums text-ink">{v.games_played ?? "—"}</div>
          <div className="text-[11px] text-faint">{data.season} 場次</div>
        </div>
        <div>
          <div className="font-mono text-lg font-bold tabular-nums text-ink">{num(v.avg_attendance)}</div>
          <div className="text-[11px] text-faint">場均觀眾</div>
        </div>
      </div>
      {(v.lf_dist || v.cf_dist || v.rf_dist) && (
        <div className="mt-3 space-y-1">
          <DistBar label="左外野" ft={v.lf_dist} />
          <DistBar label="中外野" ft={v.cf_dist} />
          <DistBar label="右外野" ft={v.rf_dist} />
        </div>
      )}
      <div className="mt-3 flex items-center justify-between text-[11px] text-faint">
        <span>{v.first_year != null && `一軍使用 ${v.first_year}–${v.last_year}`}</span>
        {v.infield_seats != null && <span>內 {num(v.infield_seats)}／外 {num(v.outfield_seats)}</span>}
      </div>
      {v.address && <div className="mt-1 truncate text-[11px] text-faint" title={v.address}>{v.address}</div>}
    </div>
  );

  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold tracking-tight">球場</h1>
      <p className="mb-6 text-sm text-muted">
        規格來自官網球場介紹（外野距離單位：呎）；場次與觀眾為 {data.season} 一軍例行賽統計。
      </p>
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">本季使用中（{active.length}）</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{active.map(card)}</div>
      </section>
      {historic.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">歷史球場（{historic.length}）</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{historic.map(card)}</div>
        </section>
      )}
    </div>
  );
}
