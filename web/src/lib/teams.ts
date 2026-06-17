// 六隊品牌色與簡稱（hero/badge/隊色條用）。key = team_code（ClubNo+011）。
export type TeamMeta = { short: string; color: string };

export const TEAMS: Record<string, TeamMeta> = {
  AAA011: { short: "味全", color: "#C8102E" }, // 味全龍
  ACN011: { short: "兄弟", color: "#D8A400" }, // 中信兄弟
  ADD011: { short: "統一", color: "#EA5413" }, // 統一7-ELEVEn獅
  AEO011: { short: "富邦", color: "#1D3C8B" }, // 富邦悍將
  AJL011: { short: "樂天", color: "#9B1B30" }, // 樂天桃猿
  AKP011: { short: "台鋼", color: "#00843D" }, // 台鋼雄鷹
};

export const teamColor = (code?: string | null) => (code && TEAMS[code]?.color) || "#0A2540";
export const teamShort = (code?: string | null) => (code && TEAMS[code]?.short) || "";

// 依隊名反查（資料常只有中文隊名）
const NAME_CODE: Record<string, string> = {
  味全龍: "AAA011", 中信兄弟: "ACN011", "統一7-ELEVEn獅": "ADD011",
  富邦悍將: "AEO011", 樂天桃猿: "AJL011", 台鋼雄鷹: "AKP011",
};
export const codeFromName = (name?: string | null) => (name && NAME_CODE[name]) || null;
export const colorFromName = (name?: string | null) => teamColor(codeFromName(name));
