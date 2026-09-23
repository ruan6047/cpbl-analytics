import type { Metadata } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:4001";

async function readEntity<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_URL}${path}`, { next: { revalidate: 300 } });
    return response.ok ? response.json() as Promise<T> : null;
  } catch {
    return null;
  }
}

export async function playerMetadata(id: string): Promise<Metadata> {
  const data = await readEntity<{ player: { name?: string | null } | null }>(`/api/v1/players/${id}/profile`);
  return { title: data?.player?.name ? `${data.player.name}｜球員` : "球員資料" };
}

export type GameMetadataScope = { kind?: string; year?: string };

function gameEntityPath(sno: string, resource: "live" | "status", { kind = "A", year }: GameMetadataScope = {}): string {
  const query = new URLSearchParams({ kind_code: kind });
  if (year && /^\d{4}$/.test(year)) query.set("season", year);
  return `/api/v1/games/${encodeURIComponent(sno)}/${resource}?${query}`;
}

export const gameMetadataPath = (sno: string, scope?: GameMetadataScope) => gameEntityPath(sno, "live", scope);
export const gameStatusPath = (sno: string, scope?: GameMetadataScope) => gameEntityPath(sno, "status", scope);

export type GameTitleStatus = {
  official_game_status?: { status?: string | null } | null;
  live_snapshot?: { phase?: string | null } | null;
} | null;

const UNFINISHED_OFFICIAL = new Set(["scheduled", "postponed", "reserved"]);

/** 標題比分只在「能由現有狀態可靠辨識為未完成」時隱藏（#186）：延賽／未開賽的比分欄是 0:0
 *  佔位，不是賽果。刻意**不是**完賽白名單——沒有排程紀錄的歷史場（official=unknown）與
 *  狀態讀取失敗（null）維持原顯示，否則大批歷史標題會失去比分；讀取失敗時短暫露出 0:0 是
 *  需求方已接受的取捨。 */
function hidesTitleScore(status: GameTitleStatus): boolean {
  const snapshot = status?.live_snapshot;
  return UNFINISHED_OFFICIAL.has(status?.official_game_status?.status ?? "")
    || (snapshot != null && snapshot.phase !== "final");
}

export async function gameMetadata(sno: string, scope?: GameMetadataScope): Promise<Metadata> {
  const [data, status] = await Promise.all([
    readEntity<{ game: { away_team_name?: string; home_team_name?: string; away_score?: number | null; home_score?: number | null } | null }>(gameMetadataPath(sno, scope)),
    readEntity<GameTitleStatus>(gameStatusPath(sno, scope)),
  ]);
  const game = data?.game;
  if (!game?.away_team_name || !game.home_team_name) return { title: "賽事詳情" };
  const score = game.away_score != null && game.home_score != null && !hidesTitleScore(status)
    ? ` ${game.away_score}：${game.home_score}` : "";
  return { title: `${game.away_team_name} vs ${game.home_team_name}${score}` };
}
