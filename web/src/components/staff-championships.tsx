// 教練團奪冠紀錄（#470）：球員頁與教練個人頁共用。
// 刻意與「總冠軍 ×N」（球員身分＋總教練身分，championship_members）分開：教練團身分
// 不計入個人冠軍次數（需求方 #470 第 4 題）。資料為一次性人工產生的維基名單，不保證完整，
// 一律在段落附註寫明資料截至年份與來源；只有單一來源的列逐列標示。
import Link from "next/link";
import type { ReactNode } from "react";
import { DataTable, type Column } from "@/components/table";
import { ENTITY_LINK_TEXT, TeamLogo } from "@/components/ui";

export type StaffChampionshipItem = {
  year: number;
  team_code: string;
  team_name: string | null;
  level: string;
  title: string | null;
  single_source: boolean;
  sources: { site: string; label: string; url: string }[];
  note: string | null;
};

export type StaffChampionships = {
  through_year: number;
  items: StaffChampionshipItem[];
  missing_years: number[];
  note: string | null;
};

/** 不重複的奪冠年份（同年同隊只算一次）。 */
export function staffChampionshipYears(d: StaffChampionships | null | undefined): number[] {
  return [...new Set((d?.items ?? []).map((i) => i.year))].sort((a, b) => a - b);
}

/** Hero 榮譽列的身分標籤：「教練團冠軍 ×N」，與「總冠軍 ×N」並列但分開。 */
export function StaffChampionshipTag({ data }: { data: StaffChampionships | null | undefined }) {
  const years = staffChampionshipYears(data);
  if (!years.length) return null;
  return (
    <span title={`教練團身分奪冠年份：${years.join("、")}（不計入總冠軍次數）`}
      className="pm-tag !text-ink">
      教練團冠軍 ×{years.length}
    </span>
  );
}

const CHIP = "rounded bg-surface-2 px-1 py-0.5 text-[10px] font-semibold text-faint";

export function StaffChampionshipsSection({ data, heading }: {
  data: StaffChampionships | null | undefined;
  heading: ReactNode;
}) {
  if (!data || !data.items.length) return null;
  const cols: Column<StaffChampionshipItem>[] = [
    { header: "年度", cell: (r) => String(r.year), nowrap: true },
    {
      header: "球隊",
      cell: (r) => (
        <Link href={`/teams/${r.team_code}`} className="group inline-flex items-center gap-1.5">
          <TeamLogo code={r.team_code} size={16} decorative />
          <span className={ENTITY_LINK_TEXT}>{r.team_name ?? r.team_code}</span>
        </Link>
      ),
      nowrap: true,
      className: "font-sans",
    },
    { header: "層級", cell: (r) => r.level, nowrap: true, className: "font-sans" },
    { header: "職稱", cell: (r) => r.title ?? "—", nowrap: true, className: "font-sans text-ink" },
    {
      header: "來源",
      cell: (r) => (
        <span className="flex flex-wrap items-center gap-1.5">
          {r.sources.map((s) => (
            <a key={`${s.site}-${s.url}`} href={s.url} target="_blank" rel="noopener noreferrer"
              className="text-accent hover:underline">{s.label}</a>
          ))}
          {r.single_source && (
            <span title="只有一個來源列出此人" className={CHIP}>單一來源</span>
          )}
        </span>
      ),
      nowrap: true,
      className: "font-sans text-xs",
    },
    {
      header: "附註",
      cell: (r) => r.note ? <span className="text-xs text-muted">{r.note}</span> : "—",
      className: "font-sans min-w-[14rem]",
      headClassName: "whitespace-nowrap",
    },
  ];
  return (
    <section className="mb-6">
      {heading}
      <DataTable columns={cols} rows={data.items} rowKey={(r, i) => `${r.year}-${r.team_code}-${i}`} dense />
      <p className="mt-2 text-xs text-faint">
        教練團身分，不計入總冠軍次數。教練團奪冠資料截至 {data.through_year} 年；
        來源：台灣棒球維基館、中文維基百科，名單不保證完整。
        {data.missing_years.length > 0 && ` 以下冠軍隊年來源沒有教練團名單：${data.missing_years.join("、")}。`}
      </p>
    </section>
  );
}
