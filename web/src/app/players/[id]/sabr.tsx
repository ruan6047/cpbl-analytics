"use client";

// 進階指標（sabr 推算）：打者 RE24/wSB、投手 RE24、捕手 RA9+阻殺。
// 全部自算（livelog + RE 矩陣 + 官方計數），非官方數據 → 區塊標「推算」。
import { useEffect, useState } from "react";
import { detail } from "@/lib/client";
import { DataTable, type Column } from "@/components/table";
import { StatAbbr } from "@/components/ui";
import type { Role } from "./lib";

type SabrYear = {
  year: number; pa?: number | null; bf?: number | null; re24: string | null;
  rnk: number | null; n: number | null; sb?: number | null; cs?: number | null; wsb?: string | null;
};
type CatcherYear = {
  year: number; runs: number; games: number; outs: number; ra9: string | null;
  cs: number | null; sba: number | null; cs_pct: number | null;
};

const num = (v: string | number | null | undefined) => (v == null ? null : Number(v));
const signed = (v: number) => (v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1));
// 出局數 → 棒球記法局數（.1=⅓）
const ipTxt = (outs: number) => `${Math.floor(outs / 3)}${outs % 3 ? `.${outs % 3}` : ""}`;

export function SabrSection({ id, role }: { id: string; role: Role }) {
  const [d, setD] = useState<{ years: SabrYear[]; catcher?: CatcherYear[] } | null>(null);
  useEffect(() => {
    setD(null);
    detail.sabr(id, role).then(setD).catch(() => setD(null));
  }, [id, role]);

  const years = (d?.years ?? []).filter((y) => y.re24 != null || num(y.wsb));
  const catcher = d?.catcher ?? [];
  if (!years.length && !catcher.length) return null;

  // RE24 正=創造得分價值：打者越高越好、投手越低（壓制）越好
  const good = (v: number) => (role === "batting" ? v > 0 : v < 0);
  const reCell = (v: number | null) => v == null ? <span className="text-faint">—</span> : (
    <span className={good(v) ? "font-semibold text-accent" : ""}>{signed(v)}</span>
  );

  const reColumns: Column<SabrYear>[] = [
    { header: "年度", cell: (y) => y.year, sticky: true, nowrap: true },
    { header: role === "batting" ? <StatAbbr abbr="PA" customDesc="打席數 (Plate Appearances)。" /> : <StatAbbr abbr="BF" customDesc="投手面對打席數 (Batters Faced)。" />, cell: (y) => y.pa ?? y.bf ?? "—", align: "right" },
    { header: <StatAbbr abbr="RE24" customDesc="期望得分值：以24種壘包出局狀態期望值，計算該打席創造的真實得分價值（投手為壓制值，負數代表表現佳）。" />, cell: (y) => reCell(num(y.re24)), align: "right" },
    { header: "年度名次", cell: (y) => (y.rnk ? `${y.rnk}/${y.n}` : "—"), align: "right", className: "text-muted" },
    ...(role === "batting"
      ? [
          { header: <StatAbbr abbr="wSB" customDesc="加權盜壘值：衡量該球員盜壘成功與失敗，相較於聯盟平均創造的得分價值。" />, cell: (y: SabrYear) => (num(y.wsb) != null ? signed(num(y.wsb)!) : "—"), align: "right" as const },
          { header: "盜壘 SB-CS", cell: (y: SabrYear) => (y.sb != null ? `${y.sb}-${y.cs ?? 0}` : "—"), align: "right" as const, className: "text-muted" },
        ]
      : []),
  ];
  const catColumns: Column<CatcherYear>[] = [
    { header: "捕手守備", cell: (y) => y.year, sticky: true, nowrap: true },
    { header: "接捕局數", cell: (y) => ipTxt(y.outs), align: "right" },
    { header: <StatAbbr abbr="RA/9" customDesc="接捕失分率：捕手蹲捕時，每 9 局球隊被得到的所有分數（含自責與非自責分）。" />, cell: (y) => y.ra9 ?? "—", align: "right" },
    { header: <StatAbbr abbr="阻殺率" customDesc="阻殺成功率 = 阻殺次數 ÷ (阻殺次數 + 被盜壘成功次數)。" />, cell: (y) => (y.cs_pct != null ? `${y.cs_pct}%` : "—"), align: "right" },
    { header: "CS-被盜", cell: (y) => (y.cs != null ? `${y.cs}-${y.sba ?? 0}` : "—"), align: "right", className: "text-muted" },
  ];

  return (
    <section className="mb-8">
      <h2 className="mb-1 text-lg font-semibold">
        進階指標 <span className="text-xs font-normal text-faint">（RE24／wSB 推算・一軍例行）</span>
      </h2>
      <p className="mb-3 text-xs text-faint">
        RE24＝打席前後得分期望變化的累計（跑者盜壘等異動不計入打者）；wSB＝盜壘淨得分價值。
        皆以自建 CPBL 得分期望矩陣（2018–25）推算，{role === "batting" ? "正值" : "負值"}越大越好。
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        <DataTable columns={reColumns} rows={years.slice(0, 9)} rowKey={(y) => y.year} dense />
        {role === "batting" && catcher.length > 0 && (
          <DataTable columns={catColumns} rows={catcher.slice(0, 9)} rowKey={(y) => y.year} dense />
        )}
      </div>
    </section>
  );
}
