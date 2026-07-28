import { Card, EmptyState, PlayerLink } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import type { TeamRecordsFranchise, TeamRecordsMilestone, TeamRecordsStreak, TeamUpcomingRecordsResponse } from "@/lib/api";

// 近日焦點・即將挑戰的紀錄（UX-TEAM-RECORDS1）：
//   1. 生涯里程碑——生涯口徑走後端 canonical 生涯路徑（與球員頁一致，見
//      cpbl.api.team_records docstring），依「差距／階梯」比值排序（API 已排好）。
//   2. 進行中連續安打——複用 UX-TEAM-FOCUS2 的 streak 計算。
//   3. 隊史紀錄逼近——僅計數型；連續型隊史紀錄（含「近年最佳」等變體）不得出現，
//      這是需求方 2026-07-28 裁定的紅線，本元件不接受、也不應該收到這類欄位。
//
// 三個陣列各自可能為空；三者皆空時顯示統一退化文案，不留白區塊（驗收條件明定）。

const ROLE_LABEL: Record<"batting" | "pitching", string> = { batting: "打", pitching: "投" };

function MilestonesTable({ items }: { items: TeamRecordsMilestone[] }) {
  const columns: Column<TeamRecordsMilestone>[] = [
    { header: "球員", cell: (m) => <PlayerLink pid={m.player_id} name={m.name} />, className: "font-sans", nowrap: true },
    { header: "項目", cell: (m) => `${ROLE_LABEL[m.role]}／${m.label}`, className: "font-sans text-muted", nowrap: true },
    { header: "目前", cell: (m) => m.current, align: "right" },
    { header: "里程碑", cell: (m) => m.milestone, align: "right", className: "text-ink" },
    { header: "還差", cell: (m) => m.remaining, align: "right", className: "text-accent" },
  ];
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold text-muted">生涯里程碑</div>
      {items.length === 0 ? (
        <EmptyState className="py-2 text-left">目前無接近生涯里程碑的一軍球員。</EmptyState>
      ) : (
        <DataTable columns={columns} rows={items} rowKey={(m, i) => `${m.player_id}-${m.stat}-${i}`} dense bare />
      )}
    </div>
  );
}

function StreaksTable({ items }: { items: TeamRecordsStreak[] }) {
  const columns: Column<TeamRecordsStreak>[] = [
    { header: "球員", cell: (s) => <PlayerLink pid={s.player_id} name={s.name} />, className: "font-sans", nowrap: true },
    { header: "現行連續安打", cell: (s) => `${s.streak} 場`, align: "right", className: "text-accent" },
  ];
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold text-muted">進行中連續安打</div>
      {items.length === 0 ? (
        <EmptyState className="py-2 text-left">目前無連續安打達 5 場以上的一軍球員。</EmptyState>
      ) : (
        <DataTable columns={columns} rows={items} rowKey={(s) => s.player_id} dense bare />
      )}
    </div>
  );
}

function FranchiseTable({ items }: { items: TeamRecordsFranchise[] }) {
  const columns: Column<TeamRecordsFranchise>[] = [
    { header: "球員", cell: (r) => <PlayerLink pid={r.player_id} name={r.name} />, className: "font-sans", nowrap: true },
    { header: "項目", cell: (r) => `${ROLE_LABEL[r.role]}／${r.label}`, className: "font-sans text-muted", nowrap: true },
    { header: "目前", cell: (r) => r.current, align: "right" },
    { header: "隊史紀錄", cell: (r) => `${r.record}（${r.holder}）`, align: "right", className: "font-sans text-ink", nowrap: true },
    { header: "還差", cell: (r) => r.remaining, align: "right", className: "text-accent" },
  ];
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold text-muted">隊史紀錄逼近</div>
      <p className="mb-1.5 text-[11px] text-faint">
        僅計數型；資料以年度成績表計，本季貢獻須待球季結束入庫後才會反映，非即時。
      </p>
      {items.length === 0 ? (
        <EmptyState className="py-2 text-left">目前無逼近隊史紀錄的一軍球員。</EmptyState>
      ) : (
        <DataTable columns={columns} rows={items} rowKey={(r, i) => `${r.player_id}-${r.stat}-${i}`} dense bare />
      )}
    </div>
  );
}

export function TeamRecordsSection({ data }: { data: TeamUpcomingRecordsResponse | null }) {
  if (!data) return null;
  const isEmpty = data.milestones.length === 0 && data.streaks.length === 0 && data.franchise_records.length === 0;

  return (
    <Card padding="p-4">
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
        <span className="text-sm font-bold text-ink">即將挑戰的紀錄</span>
      </div>
      {isEmpty ? (
        <EmptyState className="py-3">目前無接近中的紀錄。</EmptyState>
      ) : (
        <div className="space-y-4">
          <MilestonesTable items={data.milestones} />
          <StreaksTable items={data.streaks} />
          <FranchiseTable items={data.franchise_records} />
        </div>
      )}
    </Card>
  );
}
