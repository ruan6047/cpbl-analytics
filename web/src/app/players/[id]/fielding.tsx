"use client";

// 守備表：本季 fielding_current / 生涯 1990– 彙總。
// 本區整段屬「生涯」層，故不再提供本季/生涯切換（IA 遷移 map #16：本季守備併同表首列）；
// 有本季資料就直接疊在生涯表之上，兩段一眼全見，退役者自然只剩生涯段。
import { type StatRow } from "@/lib/client";
import { DataTable, type Column } from "@/components/table";
import { n0, numOf } from "./lib";

export function FieldingSection({ fielding, fieldingCareer, fieldFromYear }: {
  fielding: StatRow[] | null;
  fieldingCareer: StatRow[] | null;
  fieldFromYear: number | null;
}) {
  const seasonRows = fielding ?? [];
  const careerRows = fieldingCareer ?? [];
  if (seasonRows.length === 0 && careerRows.length === 0) return null;
  // 捕手欄位只要任一段用得到就整區顯示，避免兩張表欄數不一致而難以對照。
  const fld = [...seasonRows, ...careerRows];
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
      <h2 className="mb-3 text-lg font-semibold text-ink">守備</h2>
      {seasonRows.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-medium text-muted">本季</h3>
          <DataTable columns={columns} rows={seasonRows} rowKey={(r) => `s-${r.pos}`} dense />
        </div>
      )}
      {careerRows.length > 0 && (
        <div>
          <h3 className="mb-2 flex flex-wrap items-baseline gap-2 text-sm font-medium text-muted">
            生涯累計
            {fieldFromYear && <span className="text-[11px] font-normal text-faint">{fieldFromYear} 起</span>}
          </h3>
          <DataTable columns={columns} rows={careerRows} rowKey={(r) => `c-${r.pos}`} dense />
        </div>
      )}
    </section>
  );
}
