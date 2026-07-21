// 守備位置圖（共用元件，UI-FIELD-DIAGRAM1）。
//
// 轉播式近似守位座標——保留棒球站位語意，但不宣稱實際守備範圍或公尺級精確度，
// 也不以顏色編碼好壞。呼叫端只給「守位 → 顯示內容」，元件不假設資料來源：
// 球員頁餵守備局數／出賽數，賽況頁未來可餵先發球員名與守備異動。
//
// 佈局與截斷邏輯在 field-diagram-layout.ts（可單測）；本檔只負責畫。
import Link from "next/link";
import {
  BADGE_W, META_W, type FieldCellContent, type FieldCells, MAIN_BASELINE, MAIN_BASELINE_ALONE, MAIN_FONT,
  SUB_BASELINE, SUB_FONT, VIEW_H, VIEW_W, describeCells, layoutCells, layoutDesignatedHitter,
} from "./field-diagram-layout";

export type { FieldCellContent, FieldCells, FieldPosition } from "./field-diagram-layout";
export { POSITION_LABEL } from "./field-diagram-layout";

export function FieldDiagram({ cells, designatedHitter, caption = "守備位置", ariaLabel, className }: {
  /** 守位 → 顯示內容。未列出的守位以「無資料」樣式呈現，不會消失。 */
  cells: FieldCells;
  /** 指定打擊不屬於守備位置；提供時另列於捕手旁。 */
  designatedHitter?: FieldCellContent | null;
  /** 用於 aria-label 開頭的情境描述（例：「守位分布」「先發守備位置」）。 */
  caption?: string;
  /** 覆寫整段 aria-label；預設由 cells 自動敘述。 */
  ariaLabel?: string;
  className?: string;
}) {
  const laid = layoutCells(cells);
  const allCells = designatedHitter ? [...laid, layoutDesignatedHitter(designatedHitter)] : laid;
  const dhLabel = designatedHitter
    ? `；指定打擊：${designatedHitter.main ?? "指定打擊"}${designatedHitter.meta ? ` 第${designatedHitter.meta}棒` : ""}`
    : "";
  const label = ariaLabel ?? `${describeCells(cells, caption)}${dhLabel}`;
  const links = allCells.filter((c) => c.href);

  return (
    <div className={`relative ${className ?? "w-full max-w-[340px]"}`}>
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      className="block w-full"
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      <desc>守位依轉播常見的棒球場空間排列；位置為近似示意，不代表守備範圍。</desc>
      <g aria-hidden="true">
        {/* 扇形外野＋界外線 */}
        <path d="M180 286 14 130 Q43 28 180 8 Q317 28 346 130Z"
          className="fill-surface-2 stroke-line" strokeWidth={1.25} />
        <path d="M180 286 14 130M180 286 346 130" className="stroke-line-strong" fill="none" strokeWidth={1} />
        {/* 內野土區與草區；捕手視角的一壘在右、三壘在左。 */}
        <path d="M180 104 280 184 180 284 80 184Z" className="fill-line/35 stroke-line" strokeWidth={1} />
        <path d="M180 128 250 184 180 252 110 184Z" className="fill-surface stroke-line" strokeWidth={1} />
        <circle cx="180" cy="199" r="11" className="fill-line/50" />
        {[{ x: 180, y: 128 }, { x: 250, y: 184 }, { x: 110, y: 184 }, { x: 180, y: 252 }].map((base) => (
          <rect key={`${base.x}-${base.y}`} x={base.x - 4} y={base.y - 4} width={8} height={8}
            transform={`rotate(45 ${base.x} ${base.y})`} className="fill-surface stroke-line-strong" strokeWidth={1} />
        ))}
      </g>
      {allCells.map((c) => {
        const body = (
          <>
            <rect
              x={c.x} y={c.y} width={c.w} height={c.h} rx={6}
              className={c.used ? "fill-surface stroke-line-strong" : "fill-surface-2 stroke-line"}
              strokeWidth={1}
              strokeDasharray={c.used ? undefined : "3 3"}
            />
            <path d={`M${c.x + BADGE_W} ${c.y}V${c.y + c.h}`} className="stroke-line" strokeWidth={1} />
            <text x={c.x + BADGE_W / 2} y={c.y + 23} textAnchor="middle" fontSize={9}
              className={c.used ? "fill-muted font-mono font-semibold" : "fill-faint font-mono"}>
              {c.code}
            </text>
            {c.meta && (
              <>
                <path d={`M${c.x + c.w - META_W} ${c.y}V${c.y + c.h}`} className="stroke-line" strokeWidth={1} />
                <text x={c.x + c.w - META_W / 2} y={c.y + 22.5} textAnchor="middle" fontSize={9}
                  className="fill-ink font-mono font-semibold">{c.meta}</text>
              </>
            )}
            <text
              x={c.contentCx} y={c.y + (c.sub ? MAIN_BASELINE : MAIN_BASELINE_ALONE)}
              textAnchor="middle" fontSize={MAIN_FONT}
              className={c.used ? "fill-ink" : "fill-faint"}
            >
              {c.main}
            </text>
            {c.sub && (
              <text
                x={c.contentCx} y={c.y + SUB_BASELINE}
                textAnchor="middle" fontSize={SUB_FONT}
                className="fill-muted font-mono"
              >
                {c.sub}
              </text>
            )}
          </>
        );
        return <g key={c.code}>{body}</g>;
      })}
    </svg>
    {/* 可點格位：以 HTML 連結覆蓋於 SVG 之上（SVG <a> 不穩、且不進無障礙樹），
        座標由 viewBox 換算百分比，與 svg 同框對齊。 */}
    {links.map((c) => (
      <Link key={c.code} href={c.href!} aria-label={c.main}
        className="absolute rounded-md transition hover:bg-accent/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent"
        style={{
          left: `${(c.x / VIEW_W) * 100}%`, top: `${(c.y / VIEW_H) * 100}%`,
          width: `${(c.w / VIEW_W) * 100}%`, height: `${(c.h / VIEW_H) * 100}%`,
        }} />
    ))}
    </div>
  );
}
