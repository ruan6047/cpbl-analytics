"use client";

// 單組打者×投手對決卡：首屏只放核心結果，進階計數與比例主動展開。
// 資料為官網逐年彙總（本季年度列＋生涯彙總列），非逐打席事件流。
import Link from "next/link";
import { Card, EmptyState, StatGrid, TeamLogo } from "@/components/ui";
import { KIND_LABEL } from "@/lib/client";
import type { Kind, PairDetail, PairRow, Role, YearCoverage } from "./api";

const fmt3 = (v: number | null) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));
const fmtPct = (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`);
const KIND_ORDER: Kind[] = ["A", "E", "C"];

function coverageText(c: YearCoverage): string {
  const parts: string[] = [];
  if (c.career) parts.push("生涯彙總");
  if (c.annual_years.length) parts.push(`年度：${c.annual_years.join("、")}`);
  return parts.length ? parts.join("；") : "無";
}

function KindSection({ row, role }: { row: PairRow; role: Role }) {
  const batterView = role === "batting";
  return (
    <section aria-label={KIND_LABEL[row.kind_code]} className="border-t border-line pt-3 first:border-t-0 first:pt-0">
      <h3 className="mb-2 text-sm font-semibold text-ink">{KIND_LABEL[row.kind_code]}</h3>
      <StatGrid
        cols={4}
        items={[
          { label: "打席", value: row.plate_appearances },
          { label: "打數", value: row.at_bats },
          { label: batterView ? "AVG" : "被打 AVG", value: fmt3(row.avg) },
          { label: batterView ? "OPS" : "被 OPS", value: fmt3(row.ops) },
          { label: batterView ? "上壘率" : "被上壘率", value: fmt3(row.obp) },
          { label: batterView ? "長打率" : "被長打率", value: fmt3(row.slg) },
          { label: "三振", value: row.so },
          { label: batterView ? "全壘打" : "被全壘打", value: row.home_runs },
        ]}
      />
      <details className="mt-2">
        <summary className="cursor-pointer select-none text-xs text-faint hover:text-muted">
          進階（計數與比例）
        </summary>
        <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
          {(
            [
              ["安打", row.hits],
              ["一安／二安／三安", `${row.singles}／${row.doubles}／${row.triples}`],
              ["壘打數", row.total_bases],
              ["打點", row.rbi],
              ["四壞（故四）", `${row.bb}（${row.ibb}）`],
              ["觸身", row.hbp],
              ["犧短／犧飛", `${row.sac_hit}／${row.sac_fly}`],
              ["滾地出局／飛球出局", `${row.ground_out}／${row.fly_out}`],
              ["滾飛比", row.goao == null ? "—" : row.goao.toFixed(2)],
              ["好球率", fmtPct(row.strike_pct)],
              ["揮棒率", fmtPct(row.swing_pct)],
              ["揮空率", fmtPct(row.whiff_pct)],
              ["首球揮棒率", fmtPct(row.first_pitch_swing_pct)],
              ["滾地／平飛／飛球比例", row.gb_pct == null ? "—" : `${fmtPct(row.gb_pct)}／${fmtPct(row.ld_pct)}／${fmtPct(row.fb_pct)}`],
            ] as [string, React.ReactNode][]
          ).map(([label, value]) => (
            <div key={label} className="flex justify-between gap-2 border-b border-line/60 py-1">
              <span className="text-muted">{label}</span>
              <span className="font-mono tabular-nums text-ink">{value}</span>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

export default function PairCard({
  data,
  role,
  scopeLabel,
}: {
  data: PairDetail;
  role: Role;
  scopeLabel: string;
}) {
  const rows = KIND_ORDER.map((k) => data.items.find((r) => r.kind_code === k)).filter(
    (r): r is PairRow => !!r,
  );
  const any = rows[0] ?? data.items[0];
  return (
    <Card padding="p-4">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="inline-flex items-center gap-1.5 text-base font-bold text-ink">
          <TeamLogo code={any?.hitter_franchise ?? any?.hitter_team_code} size={20} decorative />
          <Link href={`/players/${data.hitter}`} className="hover:underline">
            {any?.hitter_name ?? data.hitter}
          </Link>
          <span className="text-xs font-normal text-muted">打者</span>
        </span>
        <span className="text-faint">vs</span>
        <span className="inline-flex items-center gap-1.5 text-base font-bold text-ink">
          <TeamLogo code={any?.pitcher_franchise ?? any?.pitcher_team_code} size={20} decorative />
          <Link href={`/players/${data.pitcher}`} className="hover:underline">
            {any?.pitcher_name ?? data.pitcher}
          </Link>
          <span className="text-xs font-normal text-muted">投手</span>
        </span>
        <span className="ml-auto rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted">
          {scopeLabel}
        </span>
      </div>
      <p className="mt-1 text-xs text-faint">
        數值{role === "batting" ? "以打者成績呈現" : "以打者成績呈現（主角為投手，讀作被打成績）"}；
        來源為官網逐年彙總，非逐打席事件流。此組對戰資料涵蓋：{coverageText(data.coverage)}。
      </p>

      {rows.length === 0 ? (
        <EmptyState>
          此範圍（{scopeLabel}）查無這組對決的資料。
          {data.coverage.career || data.coverage.annual_years.length
            ? "可改查上列涵蓋範圍。"
            : "兩人可能不曾交手（同隊不對戰）。"}
        </EmptyState>
      ) : (
        <div className="mt-4 space-y-4">
          {rows.map((r) => (
            <KindSection key={r.kind_code} row={r} role={role} />
          ))}
        </div>
      )}
    </Card>
  );
}
