"use client";

// 明細區：生涯逐年 / 分項明細 分頁。分項資料自抓（scope/kinds 只影響本區）。
import { useEffect, useState } from "react";
import { type StatRow, detail } from "@/lib/client";
import { type Role, SPLIT_CATS, splitCat } from "./lib";
import { CareerTable, SplitsTable, Tabs } from "./parts";

export function DetailSection({ id, role, seasonKind, isRetired, career }: {
  id: string;
  role: Role;
  seasonKind: "A" | "D";
  isRetired: boolean;
  career: StatRow[] | null;
}) {
  // 退役/教練（本季無登錄層級）分項預設生涯
  const [scope, setScope] = useState<"season" | "career">(isRetired ? "career" : "season");
  const [kinds, setKinds] = useState<string[]>(["A"]);
  const [detailTab, setDetailTab] = useState<"yearly" | "splits">("yearly");
  const [splits, setSplits] = useState<StatRow[] | null>(null);

  useEffect(() => {
    const year = scope === "season" ? 2026 : 9999;
    // 本季分項依一/二軍鏡頭(seasonKind)；生涯分項用 kind 頁籤(A/C/E)
    const k = scope === "season" ? seasonKind : (kinds.length ? kinds.join(",") : "A");
    detail.splits(id, role, year, k).then((d) => setSplits(d.items)).catch(() => setSplits([]));
  }, [id, role, scope, kinds, seasonKind]);

  return (
    <>
      {/* 明細：生涯逐年 / 分項 分頁切換 */}
      <div className="mb-3"><Tabs opts={[
        ...(career && career.length > 0 ? [{ v: "yearly" as const, label: "生涯逐年" }] : []),
        { v: "splits" as const, label: "分項明細" },
      ]} v={detailTab} set={setDetailTab} /></div>

      {/* 生涯逐年 */}
      {detailTab === "yearly" && career && career.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-3 text-lg font-semibold text-ink">生涯逐年</h2>
          <CareerTable seasons={career} role={role} />
        </section>
      )}

      {/* 分項明細 */}
      {(detailTab === "splits" || !(career && career.length > 0)) && (
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
        {!splits ? <p className="text-sm text-muted">載入中…</p>
          : splits.length === 0 ? <p className="text-sm text-muted">此範圍無分項資料。</p> : (() => {
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
                    <div className="overflow-x-auto border-t border-line"><SplitsTable rows={g.rows} role={role} /></div>
                  </details>
                ))}
              </div>
            );
          })()}
      </section>
      )}
    </>
  );
}
