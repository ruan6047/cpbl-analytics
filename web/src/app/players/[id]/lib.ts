// 球員頁共用：格式化工具、指標/進階/分項常數、型別。純資料與函式（無 JSX）。
import { type StatRow, type detail } from "@/lib/client";
import { fmtIPParts } from "@/lib/format";

export type Role = "batting" | "pitching";
export type CareerStats = Awaited<ReturnType<typeof detail.careerStats>>;
export type Ability = Awaited<ReturnType<typeof detail.abilityCard>>;
export type Disc = {
  summary: Record<string, number | null>;
  quality: Record<string, number | null>;
  quality_by_pt: Record<string, Record<string, number | null>>;
  points: { x: number; y: number; sw: boolean; wh: boolean; result: string; ev: number | null; la: number | null; pt: string | null }[];
  spray: { dir: number; dist: number; ev: number | null; la: number | null; result: string; pt: string | null }[];
  batted: { la: number; ev: number; result: string }[];
};

export const numOf = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === "" ? null : Number(v);

// 洋將身分徽章樣式（local 不顯示）
export const IMPORT_BADGE: Record<string, { color: string; hint: string }> = {
  import: { color: "#2563EB", hint: "外籍洋將，占球隊洋將登錄名額" },
  loree: { color: "#0F766E", hint: "羅力條款：在台累積球季並申請，視為本土洋將，不占洋將名額" },
  nagata: { color: "#7C3AED", hint: "永田條款：循台灣學生棒球體系選秀進入職棒，視同本土選手" },
};

// hero 內「教練／行政」所屬隊伍列型別（依隊聚合年份、職稱進 tooltip）
export type Tenure = { team: string; role: string | null; from: number | null; to: number | null };

export const n0 = (v: number | string | null | undefined) => (v === null || v === undefined ? "—" : String(v));
export const f3 = (v: number | string | null | undefined) => {
  const x = numOf(v);
  return x === null ? "—" : x.toFixed(3).replace(/^0\./, ".");
};
export const ipOf = (r: StatRow) => {
  const c = numOf(r.inning_pitched_cnt);
  return c === null ? null : c + (numOf(r.inning_pitched_div3) ?? 0) / 3;
};
export const eraOf = (r: StatRow) => {
  const ip = ipOf(r), er = numOf(r.earned_runs);
  return ip && ip > 0 && er !== null ? (er * 9) / ip : null;
};
export const ipText = (r: StatRow) =>
  fmtIPParts(r.inning_pitched_cnt as number | null, r.inning_pitched_div3 as number | null);

// 官方進階 + PR
export type Adv = { key: string; pr: string; bl: string; pl: string; def: string; kind: "kmh" | "pct" | "rate3" | "cnt" };
export const ADV: Adv[] = [
  { key: "ev", pr: "ev_pr", bl: "擊球初速", pl: "被擊球初速", def: "平均擊球初速 km/h", kind: "kmh" },
  { key: "max_ev", pr: "max_ev_pr", bl: "最高初速", pl: "被最高初速", def: "單季最高擊球初速 km/h", kind: "kmh" },
  { key: "brlp", pr: "brlp_pr", bl: "Barrel%", pl: "被Barrel%", def: "出色擊球率", kind: "pct" },
  { key: "brl", pr: "brl_pr", bl: "Barrel數", pl: "被Barrel數", def: "出色擊球次數", kind: "cnt" },
  { key: "hardhitp", pr: "hardhitp_pr", bl: "強擊球%", pl: "被強擊球%", def: "強勁擊球占比", kind: "pct" },
  { key: "woba", pr: "woba_pr", bl: "wOBA", pl: "被wOBA", def: "加權上壘率（官方）", kind: "rate3" },
  { key: "ba", pr: "ba_pr", bl: "打擊率", pl: "被打擊率", def: "BA", kind: "rate3" },
  { key: "iso", pr: "iso_pr", bl: "ISO", pl: "被ISO", def: "純長打率", kind: "rate3" },
  { key: "slg", pr: "slg_pr", bl: "長打率", pl: "被長打率", def: "SLG", kind: "rate3" },
  { key: "obp", pr: "obp_pr", bl: "上壘率", pl: "被上壘率", def: "OBP", kind: "rate3" },
  { key: "chasep", pr: "chasep_pr", bl: "追打%", pl: "誘追打%", def: "好球帶外揮棒率", kind: "pct" },
  { key: "whiffp", pr: "whiffp_pr", bl: "揮空%", pl: "誘揮空%", def: "揮棒落空率", kind: "pct" },
  { key: "kp", pr: "kp_pr", bl: "K%", pl: "奪三振%", def: "三振率", kind: "pct" },
  { key: "bbp", pr: "bbp_pr", bl: "BB%", pl: "被保送%", def: "保送率", kind: "pct" },
];
export const fmtAdv = (v: number, k: Adv["kind"]) =>
  k === "kmh" ? v.toFixed(1) : k === "cnt" ? String(Math.round(v))
    : k === "pct" ? `${(v * 100).toFixed(1)}%` : v.toFixed(3).replace(/^0\./, ".");

// 擊球品質與彈道（讀 advanced.metrics jsonb；官方 /rankings 全套）
const _pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const _kmh = (v: number) => v.toFixed(1);
const _m = (v: number) => `${v.toFixed(1)}m`;
const _deg = (v: number) => `${v.toFixed(1)}°`;
const _cnt = (v: number) => String(Math.round(v));
export const QUALITY_GROUPS: { title: string; pie?: boolean; items: { k: string; label: string; fmt: (v: number) => string }[] }[] = [
  { title: "擊球品質", items: [
    { k: "evAvg", label: "平均初速", fmt: _kmh }, { k: "ev90Th", label: "EV90", fmt: _kmh },
    { k: "evMax", label: "最大初速", fmt: _kmh }, { k: "laAvg", label: "平均仰角", fmt: _deg },
    { k: "distanceAvgHr", label: "全壘打均距", fmt: _m }, { k: "distanceMax", label: "最遠擊球", fmt: _m },
  ] },
  { title: "彈道分布", pie: true, items: [
    { k: "gbp", label: "滾地球", fmt: _pct }, { k: "ldp", label: "平飛球", fmt: _pct },
    { k: "fbp", label: "高飛球", fmt: _pct }, { k: "pup", label: "內野飛球", fmt: _pct },
  ] },
  { title: "拉打方向", pie: true, items: [
    { k: "pullp", label: "拉打", fmt: _pct }, { k: "straightp", label: "中間", fmt: _pct },
    { k: "oppop", label: "推打", fmt: _pct },
  ] },
  { title: "強擊 / Barrel", items: [
    { k: "hardHitp", label: "強擊球%", fmt: _pct }, { k: "barrels", label: "Barrel 數", fmt: _cnt },
    { k: "brlsPAp", label: "Barrel/PA", fmt: _pct },
  ] },
];

// roll=近15場滾動(rate/adjusted，看冷熱手)；無 roll=累積配速線(計數型)。ref=基準參考線。
export type Metric = { key: string; label: string; dp: number; get: (r: StatRow) => number | null; roll?: boolean; ref?: number };
export const BAT_METRICS: Metric[] = [
  { key: "ops_plus", label: "OPS+", dp: 0, get: (r) => numOf(r.ops_plus), roll: true, ref: 100 },
  { key: "ops", label: "OPS", dp: 3, get: (r) => numOf(r.ops), roll: true },
  { key: "avg", label: "打擊率", dp: 3, get: (r) => numOf(r.avg), roll: true },
  { key: "obp", label: "上壘率", dp: 3, get: (r) => numOf(r.obp), roll: true },
  { key: "slg", label: "長打率", dp: 3, get: (r) => numOf(r.slg), roll: true },
  // 逐場趨勢用 hits/home_runs、生涯逐年用 h/hr → 兩者皆容
  { key: "hits", label: "安打", dp: 0, get: (r) => numOf(r.hits ?? r.h) },
  { key: "home_runs", label: "全壘打", dp: 0, get: (r) => numOf(r.home_runs ?? r.hr) },
  { key: "rbi", label: "打點", dp: 0, get: (r) => numOf(r.rbi) },
];
export const PIT_METRICS: Metric[] = [
  { key: "era_plus", label: "ERA+", dp: 0, get: (r) => numOf(r.era_plus), roll: true, ref: 100 },
  { key: "era", label: "ERA", dp: 2, get: (r) => (r.era != null ? numOf(r.era) : eraOf(r)), roll: true },
  { key: "whip", label: "WHIP", dp: 2, get: (r) => numOf(r.whip), roll: true },
  { key: "so", label: "三振", dp: 0, get: (r) => numOf(r.so) },
  { key: "hits", label: "被安打", dp: 0, get: (r) => numOf(r.hits) },
  { key: "bb", label: "四壞", dp: 0, get: (r) => numOf(r.bb) },
];
export const axis = { tick: { fill: "#5b6b7a", fontSize: 12 }, stroke: "#cbd5e1" };

// 推算球種（pitch_type_pred；缺退 tagged 二元）：統一名稱→色→順序，逐球各視圖共用。
// 順序＝快→慢/常見度；色為分類配色（賽況卡與此處一致）。
export const PITCH_META: { key: string; color: string }[] = [
  { key: "速球", color: "#1d6fb8" },
  { key: "卡特/滑球", color: "#0ea5a4" },
  { key: "指叉/變速", color: "#f59e0b" },
  { key: "滑球/橫掃", color: "#8b5cf6" },
  { key: "曲球", color: "#16a34a" },
  { key: "變化球", color: "#94a3b8" },
];
export const PT_ORDER: string[] = PITCH_META.map((m) => m.key);
const PT_COLOR: Record<string, string> = Object.fromEntries(PITCH_META.map((m) => [m.key, m.color]));
export const ptColor = (pt: string): string => PT_COLOR[pt] ?? "#94a3b8";
// 球種鏡頭：state 為 "all" 或某推算球種中文名。可選球種由該球員實際投/面對的資料決定（避免空按鈕）。
export type PitchType = string;
export const ptTypesFrom = (pts: (string | null)[]): string[] => {
  const present = new Set(pts.filter((p): p is string => !!p));
  return PT_ORDER.filter((t) => present.has(t));
};

// 分項類別：官網 item_group_code 在打/投間不一致，改用 item_name 內容判斷（穩健、跨角色）。
export const SPLIT_CATS: { key: string; label: string; test: (n: string) => boolean }[] = [
  { key: "ha", label: "主客場", test: (n) => n === "主場" || n === "客場" },
  { key: "order", label: "棒次", test: (n) => /第.+棒/.test(n) },
  { key: "hand", label: "左右投打", test: (n) => /右投|左投|右打|左打/.test(n) },
  { key: "natfor", label: "本土／外籍", test: (n) => n.includes("本土") || n.includes("外籍") },
  { key: "role", label: "先發／中繼／後援", test: (n) => /先發|中繼|救援|後援|最後一任/.test(n) },
  { key: "base", label: "壘上狀況", test: (n) => n.includes("跑者") || n.includes("滿壘") },
  { key: "out", label: "出局數", test: (n) => n.includes("出局") },
  { key: "inning", label: "局數", test: (n) => /第.+局/.test(n) },
  { key: "score", label: "比分", test: (n) => n.includes("比分") },
  { key: "month", label: "月份", test: (n) => /月$/.test(n) },
  { key: "venue", label: "球場", test: (n) => n.includes("球場") || n.includes("中心") || n.includes("巨蛋") },
];
export const splitCat = (name: string) => SPLIT_CATS.find((c) => c.test(name))?.key ?? "other";
