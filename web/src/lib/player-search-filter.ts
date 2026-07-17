// 全域球員搜尋的純邏輯（PRODUCT_UX_BLUEPRINT v0.2 §5.5）：把 roster 轉為搜尋項並過濾。
// 與 React 分離，讓行為可用 node:test 驗證。

export type PlayerRole = "batter" | "pitcher";

/** 結構上相容 client.ts 的 Roster；此處不 import，讓本模組可獨立於 API 型別測試。 */
type RosterEntry = { id: string; name: string | null; team: string | null };
type RosterInput = { batters: RosterEntry[]; pitchers: RosterEntry[] };

export type PlayerSearchItem = {
  id: string;
  name: string;
  team: string;
  /** 二刀流球員同時出現在 roster 的 batters 與 pitchers，合併為單一項。 */
  roles: PlayerRole[];
};

/** roster 的兩份名單合併為以 player_id 為主鍵的搜尋項；無姓名者無法被搜尋故略過。 */
export function toSearchItems(roster: RosterInput): PlayerSearchItem[] {
  const byId = new Map<string, PlayerSearchItem>();
  const add = (list: RosterEntry[], role: PlayerRole) => {
    for (const p of list ?? []) {
      const name = p.name?.trim();
      if (!p.id || !name) continue;
      const existing = byId.get(p.id);
      if (existing) {
        if (!existing.roles.includes(role)) existing.roles.push(role);
        continue;
      }
      byId.set(p.id, { id: p.id, name, team: p.team ?? "", roles: [role] });
    }
  };
  add(roster.batters, "batter");
  add(roster.pitchers, "pitcher");
  return [...byId.values()];
}

/** 空白 query 不回結果：搜尋的任務是導航到指定球員，列出任意球員只是雜訊。 */
export function filterPlayers(
  items: PlayerSearchItem[],
  query: string,
  limit = 8
): PlayerSearchItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return items
    .filter((p) => p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))
    .slice(0, limit);
}

export function roleLabel(roles: PlayerRole[]): string {
  return roles.map((r) => (r === "batter" ? "打者" : "投手")).join("／");
}
