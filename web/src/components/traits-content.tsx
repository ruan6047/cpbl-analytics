import type { ReactNode } from "react";
export type TraitsData = { traits: Record<string, number | string | null> | null; league: { p_pa: number | null; go_fo: number | null; two_strike_k_pct: number | null } };
/** 共用已取得的年度資料 renderer；本元件不抓取最新值。 */
export function TraitsContent({ data, role }: { data: TraitsData | null; role: "batting" | "pitching" }) {
  const tr = data?.traits;
  const pa = Number(tr?.[role === "batting" ? "pa" : "bf"] ?? 0);
  if (!tr || pa < 50) return null;
  const lg = data!.league;
  const chip = (label: string, val: string, cmp?: string) => (
    <span key={label} className="inline-flex items-baseline gap-1.5 rounded-md bg-surface-2 px-3 py-1.5 text-[13px]">
      <span>{label}</span>
      <span className="font-mono font-bold tabular-nums text-ink">{val}</span>
      {cmp && <span className="text-xs text-muted">聯盟 {cmp}</span>}
    </span>
  );
  const items: ReactNode[] = [];
  if (tr.p_pa != null) items.push(chip("打席耗球 P/PA", String(tr.p_pa), lg.p_pa != null ? String(lg.p_pa) : undefined));
  if (tr.go != null && Number(tr.fo) > 0) {
    items.push(chip("滾飛比 GO/FO", (Number(tr.go) / Number(tr.fo)).toFixed(2), lg.go_fo != null ? String(lg.go_fo) : undefined));
  }
  if (tr.two_strike_k_pct != null) {
    items.push(chip(role === "batting" ? "兩好球後被三振" : "兩好球後解決率",
      `${tr.two_strike_k_pct}%`, lg.two_strike_k_pct != null ? `${lg.two_strike_k_pct}%` : undefined));
  }
  if (role === "batting") {
    const l = Number(tr.dir_left ?? 0), c = Number(tr.dir_center ?? 0), r = Number(tr.dir_right ?? 0);
    const tot = l + c + r;
    if (tot >= 30) items.push(chip("擊球方向 左/中/右", `${Math.round(100 * l / tot)}/${Math.round(100 * c / tot)}/${Math.round(100 * r / tot)}%`));
  }
  if (!items.length) return null;
  return (
    <div className="mt-4">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3"><h2 className="text-base font-bold tracking-[0.04em] text-ink">選手特性</h2><span className="text-[12.5px] text-muted">逐打席推算・本季一軍</span></div>
      <div className="flex flex-wrap gap-1.5">{items}</div>
    </div>
  );
}
