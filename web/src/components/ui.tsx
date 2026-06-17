import { teamColor } from "@/lib/teams";

export function Card({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={`card p-4 ${className}`}>{children}</div>;
}

export function StatTile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="card px-3 py-2.5 text-center">
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`mt-0.5 font-mono text-lg tabular-nums ${accent ? "text-accent" : "text-ink"}`}>{value}</div>
    </div>
  );
}

export function TeamBadge({ code, name }: { code?: string | null; name?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-3.5 w-1 rounded-sm" style={{ background: teamColor(code) }} />
      <span>{name}</span>
    </span>
  );
}

// 百分位發散色階：0=藍 50=灰 100=紅（Baseball Savant 式）
export function prColor(pr: number): string {
  const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
  const hex = (r: number, g: number, b: number) => `rgb(${r},${g},${b})`;
  if (pr <= 50) {
    const t = pr / 50; // #1E5BB8 → #E8E8E8
    return hex(lerp(30, 232, t), lerp(91, 232, t), lerp(184, 232, t));
  }
  const t = (pr - 50) / 50; // #E8E8E8 → #C4122F
  return hex(lerp(232, 196, t), lerp(232, 18, t), lerp(232, 47, t));
}

export function PercentileBar({ name, value, pr, def }: { name: string; value: string; pr: number; def?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-sm">
      <span title={def} className={`w-20 shrink-0 text-muted ${def ? "cursor-help" : ""}`}>{name}</span>
      <div className="relative h-4 flex-1 overflow-hidden rounded bg-surface-2">
        <div className="h-full rounded" style={{ width: `${pr}%`, background: prColor(pr) }} />
      </div>
      <span className="w-12 shrink-0 text-right font-mono tabular-nums text-ink">{value}</span>
      <span className="w-9 shrink-0 text-right font-mono text-xs text-faint">{pr}</span>
    </div>
  );
}
