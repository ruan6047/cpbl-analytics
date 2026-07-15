"use client";

// 個人冠軍次數榜（client island）：專案 Tooltip 用 React.Children.only，server component
// 傳含 server 子元件的 children 跨 RSC 邊界會炸，故整表在 client 端渲染。
import { DataTable, type Column } from "@/components/table";
import { Tooltip } from "@/components/tooltip";
import { ActivePill, Pill, PlayerLink, TeamBadge } from "@/components/ui";

export type ChampTeam = { code: string; name: string; years: number[] };
export type ChampRow = {
  key: string;
  titles: number;
  players: { pid: string; name: string }[];
  teams: ChampTeam[];
  active: boolean;
  isManager: boolean;
};

const columns: Column<ChampRow>[] = [
  { header: "冠軍次數", cell: (r) => r.titles, sticky: true, align: "right", nowrap: true, className: "font-bold text-accent" },
  {
    header: "球員",
    cell: (r) => (
      <span className="inline-flex flex-wrap items-center gap-x-1 gap-y-0.5">
        {r.players.map((p, i) => (
          <span key={p.pid} className="whitespace-nowrap">
            <PlayerLink pid={p.pid} name={p.name} />{i < r.players.length - 1 ? "、" : ""}
          </span>
        ))}
      </span>
    ),
    className: "font-sans",
  },
  {
    header: "球隊",
    cell: (r) => (
      <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
        {r.teams.map((t) => (
          <Tooltip key={t.code} content={`${t.name}：${t.years.join("、")} 奪冠`} suppressUnderline>
            <span className="inline-flex cursor-help"><TeamBadge code={t.code} name={t.name} size={16} /></span>
          </Tooltip>
        ))}
      </span>
    ),
    nowrap: true,
    className: "font-sans",
  },
  {
    // 現役／退役／教練：三選一互斥的單一標籤（統一 Pill 格式，色別區分）。曾以教練奪冠者
    // 一律顯示「教練」（皆已非現役球員），否則依球員現役/退役。
    header: "現況",
    cell: (r) =>
      r.isManager ? <Pill tone="muted" className="!bg-accent/15 !text-accent">教練</Pill>
        : r.active ? <ActivePill />
          : <Pill tone="muted">退役</Pill>,
    align: "center",
    nowrap: true,
    className: "font-sans",
  },
];

export function ChampionsPlayerTable({ rows }: { rows: ChampRow[] }) {
  return <DataTable columns={columns} rows={rows} rowKey={(r) => r.key} dense />;
}
