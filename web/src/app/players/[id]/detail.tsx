"use client";

// 明細區。IA 分層（UX-PLAYER-IA1）後拆為兩塊：
// SplitsSection→L3 分項與對戰（分項資料自抓，scope/kinds 只影響本區）、CareerYearlySection→L4 生涯。
import { useEffect, useRef, useState } from "react";
import { type StatRow, detail } from "@/lib/client";
import { EmptyState, TableSkeleton } from "@/components/ui";
import { type Role, SPLIT_CATS, splitCat } from "./lib";
import { CareerTable, SplitsTable, Tabs } from "./parts";

export function SplitsSection({ id, role, seasonKind, isRetired }: {
  id: string;
  role: Role;
  seasonKind: "A" | "D";
  isRetired: boolean;
}) {
  // 退役/教練（本季無登錄層級）分項預設生涯
  const [scope, setScope] = useState<"season" | "career">(isRetired ? "career" : "season");
  const [kinds, setKinds] = useState<string[]>(["A"]);
  const [splits, setSplits] = useState<StatRow[] | null>(null);
  // 重抓（切 role／scope／鏡頭）時本區會退回骨架，高度大幅縮水會改變文件高度、
  // 讓瀏覽器把捲動位置往回夾（REVIEW-005 P1）。記住上次實際高度，載入中沿用為下限。
  const bodyRef = useRef<HTMLDivElement>(null);
  const lastHeight = useRef(0);
  useEffect(() => {
    if (splits && bodyRef.current) lastHeight.current = bodyRef.current.offsetHeight;
  }, [splits]);

  useEffect(() => {
    const year = scope === "season" ? 2026 : 9999;
    // 本季分項依一/二軍鏡頭(seasonKind)；生涯分項用 kind 頁籤(A/C/E)
    const k = scope === "season" ? seasonKind : (kinds.length ? kinds.join(",") : "A");
    let cancelled = false;
    setSplits(null);
    detail.splits(id, role, year, k)
      .then((d) => { if (!cancelled) setSplits(d.items); })
      .catch(() => { if (!cancelled) setSplits([]); });
    return () => { cancelled = true; };
  }, [id, role, scope, kinds, seasonKind]);

  return (
    <section className="mb-6">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-ink">分項明細</h2>
        {/* 退役/教練本季無分項 → 只留生涯切換 */}
        <Tabs opts={isRetired
          ? [{ v: "career", label: "生涯" }]
          : [{ v: "season", label: "本季" }, { v: "career", label: "生涯" }]} v={scope} set={setScope} />
        {scope === "career" && (
          <div className="inline-flex flex-wrap gap-2">
            {([["A", "例行賽"], ["C", "總冠軍"], ["E", "季後賽"]] as const).map(([k, label]) => {
              const on = kinds.includes(k);
              return (
                <button key={k} onClick={() => setKinds(on ? (kinds.length > 1 ? kinds.filter((x) => x !== k) : kinds) : [...kinds, k])}
                  className={`rounded-full px-3 py-1 text-xs transition ${on ? "bg-accent text-white" : "bg-surface-2 text-muted hover:text-ink"}`}>
                  {label}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div ref={bodyRef} style={!splits && lastHeight.current ? { minHeight: lastHeight.current } : undefined}>
      {!splits ? <TableSkeleton rows={4} cols={role === "batting" ? 10 : 9} />
        : splits.length === 0 ? (
          <EmptyState>
            {scope === "season" ? "本季此範圍無分項資料（未出賽或該層級無樣本）。" : "生涯此範圍無分項資料。"}
          </EmptyState>
        ) : (() => {
          const groups = [...SPLIT_CATS, { key: "other", label: "其他" }]
            .map((cat) => ({ cat, rows: (splits ?? []).filter((r) => splitCat(String(r.item_name)) === cat.key) }))
            .filter((g) => g.rows.length > 0);
          return (
            <div className="space-y-2">
              {groups.map((g, gi) => (
                <details key={g.cat.key} open={gi === 0} className="overflow-hidden rounded-xl border border-line bg-surface">
                  <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface-2">
                    {g.cat.label}<span className="ml-2 text-xs font-normal text-faint">{g.rows.length}</span>
                  </summary>
                  <div className="border-t border-line"><SplitsTable rows={g.rows} role={role} /></div>
                </details>
              ))}
            </div>
          );
        })()}
      </div>
    </section>
  );
}

export function CareerYearlySection({ career, role }: { career: StatRow[] | null; role: Role }) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-lg font-semibold text-ink">生涯逐年</h2>
      {career === null ? <TableSkeleton rows={5} cols={role === "batting" ? 10 : 9} />
        : career.length === 0 ? <EmptyState>無生涯逐年紀錄（來源 cpbl-opendata 不含當季）。</EmptyState>
        : <CareerTable seasons={career} role={role} />}
    </section>
  );
}
