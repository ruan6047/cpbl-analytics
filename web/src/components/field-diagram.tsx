// 守備位置圖（共用元件，UI-FIELD-DIAGRAM1）。
//
// 轉播記分板式的制式格位，**不是**真實球場座標——這是身分圖，不宣稱空間精確度，
// 也不以顏色編碼好壞。呼叫端只給「守位 → 顯示內容」，元件不假設資料來源：
// 球員頁餵守備局數／出賽數，賽況頁未來可餵先發球員名與守備異動。
//
// 佈局與截斷邏輯在 field-diagram-layout.ts（可單測）；本檔只負責畫。
import {
  type FieldCells, MAIN_BASELINE, MAIN_BASELINE_ALONE, MAIN_FONT, SUB_BASELINE, SUB_FONT,
  VIEW_H, VIEW_W, describeCells, layoutCells,
} from "./field-diagram-layout";

export type { FieldCellContent, FieldCells, FieldPosition } from "./field-diagram-layout";
export { POSITION_LABEL } from "./field-diagram-layout";

export function FieldDiagram({ cells, caption = "守備位置", ariaLabel, className }: {
  /** 守位 → 顯示內容。未列出的守位以「無資料」樣式呈現，不會消失。 */
  cells: FieldCells;
  /** 用於 aria-label 開頭的情境描述（例：「守位分布」「先發守備位置」）。 */
  caption?: string;
  /** 覆寫整段 aria-label；預設由 cells 自動敘述。 */
  ariaLabel?: string;
  className?: string;
}) {
  const laid = layoutCells(cells);
  const label = ariaLabel ?? describeCells(cells, caption);

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      className={className ?? "w-full max-w-[340px]"}
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      <desc>守位以制式格位排列（外野一列、內野一列、投手、捕手），非真實球場座標。</desc>
      {laid.map((c) => (
        <g key={c.code}>
          <rect
            x={c.x} y={c.y} width={c.w} height={c.h} rx={6}
            className={c.used ? "fill-surface stroke-line-strong" : "fill-surface-2 stroke-line"}
            strokeWidth={1}
            strokeDasharray={c.used ? undefined : "3 3"}
          />
          <text
            x={c.cx} y={c.y + (c.sub ? MAIN_BASELINE : MAIN_BASELINE_ALONE)}
            textAnchor="middle" fontSize={MAIN_FONT}
            className={c.used ? "fill-ink" : "fill-faint"}
          >
            {c.main}
          </text>
          {c.sub && (
            <text
              x={c.cx} y={c.y + SUB_BASELINE}
              textAnchor="middle" fontSize={SUB_FONT}
              className="fill-muted font-mono"
            >
              {c.sub}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}
