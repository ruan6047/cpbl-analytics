"use client";

// 守備表：本季 fielding_current / 生涯 1990– 彙總；退役無本季 → 自動切生涯。fieldScope 內化。
import { useState } from "react";
import { type StatRow } from "@/lib/client";
import { DataTable, type Column } from "@/components/table";
import { n0, numOf } from "./lib";

export function FieldingSection({ fielding, fieldingCareer, fieldFromYear }: {
  fielding: StatRow[] | null;
  fieldingCareer: StatRow[] | null;
  fieldFromYear: number | null;
}) {
  const [fieldScope, setFieldScope] = useState<"season" | "career">("season");
  if ((fielding?.length ?? 0) === 0 && (fieldingCareer?.length ?? 0) === 0) return null;
  const effField: "season" | "career" =
    fieldScope === "season" && (fielding?.length ?? 0) === 0 && (fieldingCareer?.length ?? 0) > 0
      ? "career" : fieldScope;
  const fld = (effField === "career" ? fieldingCareer : fielding) ?? [];
  if (fld.length === 0) return null;
  const hasC = fld.some((r) => String(r.pos).includes("捕") || numOf(r.cs) || numOf(r.pb) || numOf(r.sba));
  const cols: { key: string; label: string; tip: string; tone?: string; catcher?: boolean }[] = [
    { key: "g", label: "出賽", tip: "該守位出賽場數 G", tone: "text-muted" },
    { key: "tc", label: "守備機會", tip: "TC＝刺殺＋助殺＋失誤" },
    { key: "po", label: "刺殺", tip: "PO：直接使打者/跑者出局" },
    { key: "a", label: "助殺", tip: "A：傳球協助使對方出局" },
    { key: "e", label: "失誤", tip: "E", tone: "text-accent" },
    { key: "dp", label: "雙殺", tip: "參與的雙殺次數" },
    { key: "tp", label: "三殺", tip: "參與的三殺次數" },
    { key: "pb", label: "捕逸", tip: "PB：捕手漏接致跑者進壘", catcher: true },
    { key: "cs", label: "盜壘阻殺", tip: "阻殺：捕手傳殺盜壘跑者", catcher: true },
    { key: "sba", label: "被盜成功", tip: "被盜壘成功數", catcher: true },
  ].filter((c) => !c.catcher || hasC);
  const columns: Column<StatRow>[] = [
    { header: "守位", cell: (r) => String(r.pos), sticky: true, nowrap: true, className: "font-sans text-ink" },
    ...cols.map((c): Column<StatRow> => ({
      header: <span title={c.tip} className="cursor-help">{c.label}</span>,
      cell: (r) => n0(r[c.key]),
      align: "right",
      className: c.tone,
    })),
    {
      header: <span title="(刺殺＋助殺) ÷ 守備機會" className="cursor-help">守備率</span>,
      cell: (r) => (r.fpct == null ? "—" : Number(r.fpct).toFixed(3).replace(/^0\./, ".")),
      align: "right",
      className: "text-ink",
    },
  ];
  return (
    <section className="mb-6">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-ink">守備</h2>
        {(fielding?.length ?? 0) > 0 && (fieldingCareer?.length ?? 0) > 0 && (
          <div className="inline-flex overflow-hidden rounded-full border border-line text-[11px]">
            {(["season", "career"] as const).map((s) => (
              <button key={s} onClick={() => setFieldScope(s)}
                className={`px-2.5 py-0.5 transition ${effField === s ? "bg-ink text-paper" : "bg-surface text-muted hover:text-ink"}`}>
                {s === "season" ? "本季" : "生涯"}
              </button>
            ))}
          </div>
        )}
        {effField === "career" && fieldFromYear && (
          <span className="text-[11px] text-faint">生涯累計（{fieldFromYear} 起）</span>
        )}
      </div>
      <DataTable columns={columns} rows={fld} rowKey={(r) => String(r.pos)} dense />
    </section>
  );
}
