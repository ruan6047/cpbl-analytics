// 六隊品牌色、簡稱、字母徽章（避免官方 logo 版權，以隊色＋字母代表）。
// 字母取隊伍英文代表字：W=味全(Wei Chuan)、B=兄弟(Brothers)、L=獅(Lions)、
// G=悍將(Guardians)、M=猿(Monkeys)、H=鷹(Hawks)。key = team_code（ClubNo+011）。
export type TeamMeta = { short: string; color: string; letter: string };

export const TEAMS: Record<string, TeamMeta> = {
  AAA011: { short: "味全", color: "#C8102E", letter: "W" }, // 味全龍
  ACN011: { short: "兄弟", color: "#D8A400", letter: "B" }, // 中信兄弟
  ADD011: { short: "統一", color: "#EA5413", letter: "L" }, // 統一7-ELEVEn獅
  AEO011: { short: "富邦", color: "#1D3C8B", letter: "G" }, // 富邦悍將
  AJL011: { short: "樂天", color: "#9B1B30", letter: "M" }, // 樂天桃猿
  AKP011: { short: "台鋼", color: "#00843D", letter: "H" }, // 台鋼雄鷹
};

export const teamColor = (code?: string | null) => (code && TEAMS[code]?.color) || "#0A2540";
export const teamShort = (code?: string | null) => (code && TEAMS[code]?.short) || "";
export const teamLetter = (code?: string | null) => (code && TEAMS[code]?.letter) || "?";

// 依背景色亮度回傳對比文字色（黃色系用深色字）
export function contrastText(hex: string): string {
  const n = hex.replace("#", "");
  const r = parseInt(n.slice(0, 2), 16), g = parseInt(n.slice(2, 4), 16), b = parseInt(n.slice(4, 6), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? "#0A2540" : "#FFFFFF";
}

// 依隊名反查（資料常只有中文隊名）
const NAME_CODE: Record<string, string> = {
  味全龍: "AAA011", 中信兄弟: "ACN011", "統一7-ELEVEn獅": "ADD011",
  富邦悍將: "AEO011", 樂天桃猿: "AJL011", 台鋼雄鷹: "AKP011",
};
export const codeFromName = (name?: string | null) => (name && NAME_CODE[name]) || null;
export const colorFromName = (name?: string | null) => teamColor(codeFromName(name));
