// 六隊品牌色、簡稱、字母徽章（避免官方 logo 版權，以隊色＋字母代表）。
// 字母取隊伍英文代表字：W=味全(Wei Chuan)、B=兄弟(Brothers)、L=獅(Lions)、
// G=悍將(Guardians)、M=猿(Monkeys)、H=鷹(Hawks)。key = team_code（ClubNo+011）。
export type TeamMeta = { short: string; color: string; letter: string };

// 字母與配色對齊官方字母標：W味全 B兄弟 L統一(LL) G富邦 R樂天(Rakuten) T台鋼(TSG)
export const TEAMS: Record<string, TeamMeta> = {
  AAA011: { short: "味全", color: "#C8102E", letter: "W" }, // 味全龍 紅
  ACN011: { short: "兄弟", color: "#C8A24A", letter: "B" }, // 中信兄弟 金
  ADD011: { short: "統一", color: "#E35A13", letter: "L" }, // 統一7-ELEVEn獅 橘
  AEO011: { short: "富邦", color: "#2A4B9B", letter: "G" }, // 富邦悍將 藍
  AJL011: { short: "樂天", color: "#8E1537", letter: "R" }, // 樂天桃猿 暗紅
  AKP011: { short: "台鋼", color: "#15543C", letter: "T" }, // 台鋼雄鷹 深綠
};

// CPBL 品牌色（CPBL TV：藍 + 紅）
export const CPBL_BLUE = "#1B4DA1";

// 改名/轉賣視為同一支球隊：歷史隊代碼 → 現役 franchise 代碼（依 games 年份範圍實證）
const FRANCHISE: Record<string, string> = {
  ACC011: "ACN011",                                   // 兄弟象 → 中信兄弟
  AEE011: "AEO011", AEG011: "AEO011", AEM011: "AEO011", // 俊國→興農→義大→富邦悍將
  AJJ011: "AJL011", AJK011: "AJL011",                 // 第一金剛→La New/Lamigo→樂天桃猿
};
// 現役 franchise 代碼（一軍 011 / 二軍 022 共用 org 前綴；歷史隊映射到現役）
export const franchiseOf = (code?: string | null): string | undefined => {
  if (!code) return undefined;
  if (TEAMS[code]) return code;
  if (FRANCHISE[code]) return FRANCHISE[code];
  const org = code.slice(0, 3);
  return Object.keys(TEAMS).find((k) => k.slice(0, 3) === org);  // 二軍 022 → 現役
};
const _meta = (code?: string | null): TeamMeta | undefined => {
  const fc = franchiseOf(code);
  return fc ? TEAMS[fc] : undefined;  // 找不到現役 franchise → 已解散隊（灰）
};
export const teamColor = (code?: string | null) => _meta(code)?.color || "#94a3b8";
export const teamShort = (code?: string | null) => _meta(code)?.short || "";
export const teamLetter = (code?: string | null) => _meta(code)?.letter || "?";
// 有對應現役 franchise 才連球隊頁（含歷史隊→現役頁）；已解散隊不連
export const isCurrentTeam = (code?: string | null) => !!franchiseOf(code);
export const teamPageCode = (code?: string | null) => franchiseOf(code);

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
