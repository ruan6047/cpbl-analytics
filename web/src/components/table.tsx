import type { CSSProperties, ReactNode } from "react";
import { EmptyState } from "@/components/ui";

// 靜態資料表（presentational，無 hook → 可直接用於 server component，勿為它翻 "use client"）。
// 收斂全站散寫的 <table>：寬表容器（橫向捲動保護）+ 卡殼 + sticky 首欄 + 一致表頭/字級。
// 互動型（排序/篩選）用 components/leaderboard.tsx（已是 client island），非本元件職責。
//
// Column<T>：
//   header      表頭內容
//   cell        (row, i) => 儲存格內容（render prop；可回連結/徽章/發散色格等任意 JSX）
//   align       對齊（預設 left；數據欄用 right）
//   sticky      首欄固定（行動端寬表捲動時鎖住；套 globals 的 .sticky-col）
//   nowrap      不換行（隊名/日期等）
//   className   額外 td class（如 text-ink 強調、font-sans 覆寫等寬）
//   cellStyle   (row,i) => td inline style（發散色格 divBg 用；一般欄不需）
//   headClassName 額外 th class
//   width       欄寬（如 "3rem"）
export type Column<T> = {
  header: ReactNode;
  cell: (row: T, index: number) => ReactNode;
  align?: "left" | "right" | "center";
  sticky?: boolean;
  nowrap?: boolean;
  className?: string;
  cellStyle?: (row: T, index: number) => CSSProperties | undefined;
  headClassName?: string;
  width?: string;
};

const alignCls = (a?: Column<unknown>["align"]) =>
  a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  dense = false,
  className = "",
  bodyClassName = "font-mono tabular-nums",
  emptyText = "無資料",
  maxHeight,
  bare = false,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string | number;
  dense?: boolean;
  className?: string;
  /** tbody 額外 class；預設等寬數字。純文字表可傳 "" 覆寫。 */
  bodyClassName?: string;
  emptyText?: ReactNode;
  /** 設定則垂直捲動 + 表頭 sticky（長列表用，如對戰各隊）。CSS 長度字串。 */
  maxHeight?: string;
  /** 已在 Card 內時傳 true：只留捲動容器，不畫卡殼邊框/底，避免雙層邊框。 */
  bare?: boolean;
}) {
  if (!rows.length) return <EmptyState>{emptyText}</EmptyState>;
  const pad = dense ? "px-2.5 py-1.5" : "px-3 py-2.5";
  const shell = bare ? "" : "rounded-xl border border-line bg-surface";
  const th = (c: Column<T>, i: number) => (
    <th
      key={i}
      scope="col"
      style={c.width ? { width: c.width } : undefined}
      className={`${pad} font-medium ${alignCls(c.align)} ${c.nowrap ? "whitespace-nowrap" : ""} ${c.sticky ? "sticky-col" : ""} ${c.headClassName ?? ""}`}
    >
      {c.header}
    </th>
  );
  return (
    <div
      style={maxHeight ? { maxHeight } : undefined}
      className={`overflow-x-auto ${shell} ${maxHeight ? "overflow-y-auto" : ""} ${className}`}
    >
      <table className="w-full text-sm">
        <thead className={`bg-surface-2 text-left text-muted ${maxHeight ? "sticky top-0 z-10" : ""}`}>
          <tr>{columns.map(th)}</tr>
        </thead>
        <tbody className={bodyClassName}>
          {rows.map((row, ri) => (
            <tr key={rowKey(row, ri)} className="border-t border-line hover:bg-surface-2">
              {columns.map((c, ci) => (
                <td
                  key={ci}
                  style={c.cellStyle?.(row, ri)}
                  className={`${pad} ${alignCls(c.align)} ${c.nowrap ? "whitespace-nowrap" : ""} ${c.sticky ? "sticky-col" : ""} ${c.className ?? ""}`}
                >
                  {c.cell(row, ri)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
