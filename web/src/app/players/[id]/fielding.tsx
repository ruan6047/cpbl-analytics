"use client";

// 守備表：本季 fielding_current / 生涯 1990– 彙總。
// 本區整段屬「生涯」層，故不再提供本季/生涯切換（IA 遷移 map #16：本季守備併同表首列）；
// 有本季資料就直接疊在生涯表之上，兩段一眼全見，退役者自然只剩生涯段。
import { type StatRow } from "@/lib/client";
import { DataTable, type Column } from "@/components/table";
import { n0, numOf } from "./lib";
import {
  POS_COORD, type PosGroup, innings, isMultiPosition, isQualified, per9,
  posGroup, posLabel, primaryPos, valueMetrics,
} from "./fielding-metrics";

export type FieldLeague = Record<string, {
  n: number; a9: number | null; dp9: number | null; tc9: number | null; fpct: number | null;
}>;

// ---- 元件 C：守位身分圖（回答「他是什麼樣的守備者」，不宣稱守備好壞）----

/** 球場示意圖：沿用 spray-chart 的扇形幾何與極座標慣例（0°＝中外野、負角＝左半場）。 */
function FieldPositionMap({ rows, primary }: { rows: StatRow[]; primary: string | null }) {
  const W = 300, H = 232, cx = W / 2, baseY = H - 6;
  const maxDist = 142, scale = (baseY - 8) / maxDist;
  const centerR = 122, cornerR = 100;
  const pt = (deg: number, dist: number) => {
    const r = (deg * Math.PI) / 180;
    return [cx + dist * scale * Math.sin(r), baseY - dist * scale * Math.cos(r)] as const;
  };
  const fenceR = (deg: number) => cornerR + (centerR - cornerR) * Math.cos((Math.abs(deg) / 45) * (Math.PI / 2));
  let field = `M ${cx} ${baseY} `;
  for (let d = -45; d <= 45; d += 3) {
    const [x, y] = pt(d, fenceR(d));
    field += `L ${x.toFixed(1)} ${y.toFixed(1)} `;
  }
  field += "Z";
  const played = rows.filter((r) => (numOf(r.g) ?? 0) > 0 && POS_COORD[String(r.pos)]);
  const label = played.map((r) => {
    const pos = String(r.pos);
    const c = POS_COORD[pos];
    const [x, y] = pt(c.deg, c.dist);
    return { pos, x, y, text: posLabel(numOf(r.outs), numOf(r.g)), isPrimary: pos === primary };
  });
  const aria = label.length
    ? `守位分布：${label.map((l) => `${l.pos} ${l.text}`).join("、")}${label.length > 1 ? "，多守位" : ""}`
    : "無守備紀錄";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-[320px]" role="img" aria-label={aria}>
      <path d={field} className="fill-surface-2 stroke-line" strokeWidth={1} />
      {label.map((l) => (
        <g key={l.pos}>
          {/* 圓點大小固定：這是身分圖，尺寸與顏色都不編碼守備好壞 */}
          <circle cx={l.x} cy={l.y} r={l.isPrimary ? 6 : 5}
            className={l.isPrimary ? "fill-accent" : "fill-muted"} opacity={l.isPrimary ? 1 : 0.65} />
          <text x={l.x} y={l.y - 9} textAnchor="middle" className="fill-ink text-[9px] font-medium">
            {l.pos.replace("手", "")}
          </text>
          <text x={l.x} y={l.y + 15} textAnchor="middle" className="fill-faint text-[8px]">{l.text}</text>
        </g>
      ))}
    </svg>
  );
}

// ---- 元件 A：守備價值卡（依守位群分流，內容各不相同）----

const METRIC_META: Record<string, { label: string; tip: string; dp: number; of?: string }> = {
  a9: { label: "助殺 / 9局", tip: "A：傳球協助使對方出局，換算每 9 局", dp: 2 },
  dp9: { label: "雙殺參與 / 9局", tip: "參與雙殺次數，換算每 9 局", dp: 2 },
  tc9: { label: "守備機會 / 9局", tip: "TC＝刺殺＋助殺＋失誤，換算每 9 局", dp: 2 },
  fpct: { label: "守備率", tip: "(刺殺＋助殺) ÷ 守備機會", dp: 3 },
};

function ValueRow({ metric, value, league, dp }: {
  metric: string; value: number | null; league: number | null; dp: number;
}) {
  const meta = METRIC_META[metric];
  const diff = value != null && league != null ? value - league : null;
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/60 py-1.5 last:border-0">
      <span title={meta.tip} className="cursor-help text-xs text-muted">{meta.label}</span>
      <span className="flex items-baseline gap-2 font-mono text-sm text-ink">
        {value != null ? value.toFixed(dp) : "—"}
        {league != null && (
          <span className="text-[11px] font-sans text-faint">
            聯盟 {league.toFixed(dp)}
            {diff != null && (
              <span className={diff >= 0 ? "ml-1.5 text-up" : "ml-1.5 text-down"}>
                {diff >= 0 ? "+" : ""}{diff.toFixed(dp)}
              </span>
            )}
          </span>
        )}
      </span>
    </div>
  );
}

function FieldingValueCard({ row, league, qualifyOuts }: {
  row: StatRow; league: FieldLeague | undefined; qualifyOuts: number;
}) {
  const pos = String(row.pos);
  const group: PosGroup = posGroup(pos);
  const metrics = valueMetrics(group);
  const outs = numOf(row.outs);
  const ip = innings(outs);
  const qualified = isQualified(outs, qualifyOuts);
  const lg = league?.[pos];

  // 一壘與投手不做價值宣稱——坦白略過優於硬湊（Brief §1 元件 A）
  if (metrics.length === 0) {
    return (
      <p className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs text-muted">
        {group === "first"
          ? "一壘守備的價值難以由官方計數量化，本頁不對一壘守備下評價；上方表格為原始數據。"
          : "投手守備樣本過少，不作評價；上方表格為原始數據。"}
      </p>
    );
  }
  const val = (m: string): number | null =>
    m === "fpct" ? numOf(row.fpct)
    : per9(numOf(m === "a9" ? row.a : m === "dp9" ? row.dp : row.tc), outs);

  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-medium text-ink">{pos}・守備指標</h4>
        <span className="text-[11px] text-faint">
          {ip != null ? `${ip.toFixed(0)} 局` : "無局數資料"}
          {lg && qualified && `・聯盟合格 ${lg.n} 人`}
        </span>
      </div>
      {ip == null ? (
        <p className="text-xs text-muted">2018 年以前無守備局數資料，無法計算每 9 局率，僅呈現上方累計數據。</p>
      ) : (
        <>
          {metrics.map((m) => (
            <ValueRow key={m} metric={m} value={val(m)}
              league={qualified && lg ? (lg[m] as number | null) : null} dp={METRIC_META[m].dp} />
          ))}
          {!qualified && (
            <p className="mt-2 text-[11px] text-faint">
              守備局數未達 {qualifyOuts / 3} 局，樣本不足以與聯盟對照，僅顯示本人數值。
            </p>
          )}
          {/* 阻嚇悖論：會直接導致誤讀，依 Brief §3 置於指標旁而非頁尾 */}
          {group === "outfield" && (
            <p className="mt-2 rounded bg-surface-2 px-2 py-1.5 text-[11px] leading-relaxed text-muted">
              助殺少不等於臂力差——跑者可能因為忌憚傳球而不敢進壘，這種阻嚇效果不會出現在助殺數上。
            </p>
          )}
        </>
      )}
    </div>
  );
}

export function FieldingSection({ fielding, fieldingCareer, fieldFromYear, league, qualifyOuts }: {
  fielding: StatRow[] | null;
  fieldingCareer: StatRow[] | null;
  fieldFromYear: number | null;
  league?: FieldLeague;
  qualifyOuts?: number;
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
  // 身分圖與價值卡以本季為準（有本季才有局數與聯盟對照）；退役／2018 前退回生涯列做身分描述。
  const mapRows = seasonRows.length > 0 ? seasonRows : careerRows;
  const primary = primaryPos(mapRows.map((r) => ({ pos: String(r.pos), g: numOf(r.g) })));
  const multi = isMultiPosition(mapRows.map((r) => ({ pos: String(r.pos), g: numOf(r.g) })));
  const primaryRow = seasonRows.find((r) => String(r.pos) === primary) ?? null;

  return (
    <section className="mb-6">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-ink">守備</h2>
        {multi && (
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted">多守位</span>
        )}
      </div>
      <div className="mb-4 grid items-start gap-4 sm:grid-cols-[auto_1fr]">
        <FieldPositionMap rows={mapRows} primary={primary} />
        {primaryRow && (
          <FieldingValueCard row={primaryRow} league={league} qualifyOuts={qualifyOuts ?? 300} />
        )}
      </div>
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
