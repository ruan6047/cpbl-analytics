import type { FieldCells } from "../components/field-diagram";
import { posCode } from "../app/players/[id]/fielding-metrics.ts";
import type { Report, ReportPlayer } from "./report-types.ts";

/** 同份報告已有投手守位身分時可開投手面板；有打者列則優先野手。 */
export function reportFieldPlayer(report: Report, team: string, pid: string): ReportPlayer | null {
  const matches = (report.players ?? []).filter(p => p.team_code === team && p.player_id === pid);
  return matches.find(p => p.role === "batting") ?? matches[0] ?? null;
}

/** 只消費已驗證的公告；棒次／守位從未用 box 或年度守備倒填。 */
export function reportField(report: Report, team: string): { cells: FieldCells; dh: { main: string; href?: string; meta?: string } | null; announced: boolean } {
  const person = (pid: string) => reportFieldPlayer(report, team, pid)?.name ?? pid;
  const lineup = report.announcements?.lineup;
  const items = lineup?.items.filter(i => i.team_code === team) ?? [];
  const observed = Date.parse(lineup?.observed_at ?? "");
  const fetched = Date.parse(lineup?.pregame_evidence?.fetched_at ?? "");
  const started = lineup?.pregame_evidence?.first_started_at;
  const positions = new Set(items.map(i => i.pos));
  const reliable = lineup?.status === "announced" && !!lineup.source_version && !!lineup.observed_at
    && lineup.pregame_evidence?.is_play_ball === "N" && items.length === 9
    && Number.isFinite(observed) && observed === fetched && (!started || observed < Date.parse(started))
    && new Set(items.map(i => i.player_id)).size === 9 && new Set(items.map(i => i.order)).size === 9
    && positions.size === 9 && ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"].every(p => positions.has(p))
    && (positions.has("DH") || positions.has("P"))
    && items.every(i => i.player_id && i.pos && i.order >= 1 && i.order <= 9);
  const cell = (pid: string, order?: number) => ({ main: person(pid), href: `#report-player-${pid}`, meta: order == null ? undefined : String(order) });
  if (reliable) return {
    cells: Object.fromEntries(items.filter(i => i.pos !== "DH").map(i => [i.pos,cell(i.player_id,i.order)])) as FieldCells,
    dh: items.find(i => i.pos === "DH") ? cell(items.find(i => i.pos === "DH")!.player_id,items.find(i => i.pos === "DH")!.order) : null,
    announced: true,
  };
  const candidates = report.field_candidates?.[team] ?? {};
  const dh = candidates["指定打擊"] ?? candidates.DH;
  return {
    cells: Object.fromEntries(Object.entries(candidates).flatMap(([pos,c]) => {
      const code = posCode(pos);
      return code ? [[code,{
      main:c.player_ids.map(person).join("／"),sub:`${c.g} 場${c.status === "tied" ? " · 並列" : ""}`,
      href:c.player_ids.length === 1 ? `#report-player-${c.player_ids[0]}` : undefined,
      }]] : [];
    })) as FieldCells,
    dh:dh ? {main:dh.player_ids.map(person).join("／")} : null,
    announced:false,
  };
}
