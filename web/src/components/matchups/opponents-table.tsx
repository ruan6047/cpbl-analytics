"use client";

// 對手清單（基礎實績 hero）：緊湊欄位、server-side 排序（截斷時客端排序會誤導
// top-N，故排序一律重新查詢）、點列進單組對決。取代舊版 14 欄寬表。
import { TeamLogo } from "@/components/ui";
import type { MatchupRow, Role, SortKey } from "./api";

const fmt3 = (v: number | null) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));

const COLS: { key: SortKey; label: (role: Role) => string }[] = [
  { key: "plate_appearances", label: (r) => (r === "batting" ? "打席" : "面對打席") },
  { key: "avg", label: (r) => (r === "batting" ? "AVG" : "被打 AVG") },
  { key: "ops", label: (r) => (r === "batting" ? "OPS" : "被 OPS") },
  { key: "home_runs", label: (r) => (r === "batting" ? "全壘打" : "被全壘打") },
  { key: "so", label: () => "三振" },
];

export default function OpponentsTable({
  rows,
  role,
  sort,
  order,
  onSort,
  onPick,
}: {
  rows: MatchupRow[];
  role: Role;
  sort: SortKey;
  order: "asc" | "desc";
  onSort: (key: SortKey) => void;
  onPick: (row: MatchupRow) => void;
}) {
  const oppLabel = role === "batting" ? "投手" : "打者";
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[560px] text-sm">
        <caption className="sr-only">對戰{oppLabel}清單，點欄位標題排序、點對手看單組對決</caption>
        <thead>
          <tr className="bg-surface-2 text-left text-xs text-muted">
            <th scope="col" className="px-3 py-2.5 font-medium">
              對手{oppLabel}
            </th>
            {COLS.map((c) => (
              <th key={c.key} scope="col" className="px-2 py-1.5 text-right font-medium">
                <button
                  type="button"
                  onClick={() => onSort(c.key)}
                  aria-sort={sort === c.key ? (order === "desc" ? "descending" : "ascending") : undefined}
                  className={`rounded px-1 py-1 transition hover:text-ink ${
                    sort === c.key ? "font-semibold text-ink" : ""
                  }`}
                >
                  {c.label(role)}
                  {sort === c.key ? (order === "desc" ? " ↓" : " ↑") : ""}
                </button>
              </th>
            ))}
            <th scope="col" className="px-2 py-2.5 text-right font-medium">
              {role === "batting" ? "安打" : "被安打"}
            </th>
            <th scope="col" className="w-8 px-2 py-2.5" aria-hidden />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.opp_id} className="border-t border-line transition hover:bg-surface-2">
              <td className="px-3 py-2">
                <button
                  type="button"
                  onClick={() => onPick(r)}
                  className="flex items-center gap-2 text-left font-medium text-ink hover:underline"
                >
                  <TeamLogo code={r.opp_franchise ?? r.opp_team_code} size={18} decorative />
                  {r.opp_name ?? r.opp_id}
                </button>
              </td>
              <td className="px-2 py-2 text-right font-mono tabular-nums">{r.plate_appearances}</td>
              <td className="px-2 py-2 text-right font-mono tabular-nums">{fmt3(r.avg)}</td>
              <td className="px-2 py-2 text-right font-mono tabular-nums">{fmt3(r.ops)}</td>
              <td className="px-2 py-2 text-right font-mono tabular-nums">{r.home_runs}</td>
              <td className="px-2 py-2 text-right font-mono tabular-nums">{r.so}</td>
              <td className="px-2 py-2 text-right font-mono tabular-nums">{r.hits}</td>
              <td className="px-2 py-2 text-right text-faint" aria-hidden>
                ›
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
