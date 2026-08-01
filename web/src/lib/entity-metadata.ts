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

export async function gameMetadata(sno: string): Promise<Metadata> {
  const data = await readEntity<{ game: { away_team_name?: string; home_team_name?: string; away_score?: number | null; home_score?: number | null } | null }>(`/api/v1/games/${sno}/live?kind_code=A`);
  const game = data?.game;
  if (!game?.away_team_name || !game.home_team_name) return { title: "賽事詳情" };
  const score = game.away_score != null && game.home_score != null ? ` ${game.away_score}：${game.home_score}` : "";
  return { title: `${game.away_team_name} vs ${game.home_team_name}${score}` };
}
