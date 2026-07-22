"use client";

import { useEffect, useState } from "react";

// 圖表色票 API。recharts 的顏色走 JS props（stroke/fill 是 SVG *屬性*，不解析 CSS var()），
// 因此無法像一般元件靠 Tailwind 工具類自動換色。此 hook 於執行期讀 globals.css 的
// 設計 token（單一事實來源），並在 data-theme 變動時重讀 → 圖表隨深淺主題即時換色。
//
// raw SVG（自繪 <svg>）不需要本 hook：直接用 fill-/stroke- 工具類或 style{{fill:'var(--…)'}}
// 讓 CSS 處理即可。本 hook 專供 recharts 這類「顏色必須是具體字串」的場景。

export interface ChartTheme {
  theme: "light" | "dark";
  // 結構
  ink: string;
  muted: string;
  faint: string;
  line: string;
  lineStrong: string;
  surface: string;
  surface2: string;
  // 語意
  up: string;
  down: string;
  accent: string;
  cpbl: string;
  // 圖表分類序列（chart-1..6；索引 0-5）。含球種調色盤，見 pitchColor()。
  series: string[];
  zone: { heart: string; shadow: string; chase: string; waste: string };
  status: { import: string; loree: string; nagata: string };
}

// 淺色預設值＝globals.css 淺色 token 的鏡像，僅供 SSR / 首繪前（讀不到 computed style）
// 退場用；一旦掛載即以 getComputedStyle 覆蓋為當前主題真值。globals.css 才是 canonical。
const LIGHT_FALLBACK: ChartTheme = {
  theme: "light",
  ink: "#0a2540",
  muted: "#5b6b7a",
  faint: "#94a3b8",
  line: "#e2e8f0",
  lineStrong: "#cbd5e1",
  surface: "#ffffff",
  surface2: "#eef2f7",
  up: "#1d6fb8",
  down: "#d62839",
  accent: "#d62839",
  cpbl: "#1b4da1",
  series: ["#1d6fb8", "#0ea5a4", "#f59e0b", "#8b5cf6", "#16a34a", "#94a3b8", "#db2777", "#a16207"],
  zone: { heart: "#b91c1c", shadow: "#ea580c", chase: "#eab308", waste: "#9ca3af" },
  status: { import: "#2563eb", loree: "#0f766e", nagata: "#7c3aed" },
};

function readTheme(): ChartTheme {
  const root = document.documentElement;
  const cs = getComputedStyle(root);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  const f = LIGHT_FALLBACK;
  return {
    theme: root.getAttribute("data-theme") === "dark" ? "dark" : "light",
    ink: v("--color-ink", f.ink),
    muted: v("--color-muted", f.muted),
    faint: v("--color-faint", f.faint),
    line: v("--color-line", f.line),
    lineStrong: v("--color-line-strong", f.lineStrong),
    surface: v("--color-surface", f.surface),
    surface2: v("--color-surface-2", f.surface2),
    up: v("--color-up", f.up),
    down: v("--color-down", f.down),
    accent: v("--color-accent", f.accent),
    cpbl: v("--color-cpbl", f.cpbl),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--chart-${i}`, f.series[i - 1])),
    zone: {
      heart: v("--zone-heart", f.zone.heart),
      shadow: v("--zone-shadow", f.zone.shadow),
      chase: v("--zone-chase", f.zone.chase),
      waste: v("--zone-waste", f.zone.waste),
    },
    status: {
      import: v("--status-import", f.status.import),
      loree: v("--status-loree", f.status.loree),
      nagata: v("--status-nagata", f.status.nagata),
    },
  };
}

// recharts 消費端一律用此 hook 取色；data-theme 一變（切換鈕/系統）即重讀重繪。
export function useChartTheme(): ChartTheme {
  const [ct, setCt] = useState<ChartTheme>(LIGHT_FALLBACK);
  useEffect(() => {
    const update = () => setCt(readTheme());
    update();
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return ct;
}

// 球種 → 分類色（原 players/[id]/lib.ts 的 PT_COLOR 表；改由色票 API 統一供給，隨主題換色）。
// v2 細分球種（ML-PT2）：色槽依 top1 段（複合名取 '/' 前段）；
// v1 遺留名（fallback 投手/二軍）：速球→四縫槽、變化球→faint、其餘複合名同樣取 top1。
const PITCH_ORDER = ["四縫", "伸卡", "卡特", "滑球", "橫掃", "曲球", "變速", "指叉"] as const;
const PITCH_ALIAS: Record<string, string> = { 速球: "四縫", 指叉變速: "指叉", 滑曲球: "曲球" };
export function pitchColor(ct: ChartTheme, pitch: string): string {
  let seg = pitch.split("/")[0];
  seg = PITCH_ALIAS[seg] ?? seg;
  const idx = PITCH_ORDER.indexOf(seg as (typeof PITCH_ORDER)[number]);
  return idx >= 0 ? ct.series[idx] : ct.faint;
}
export const PITCH_KEYS = PITCH_ORDER;

// recharts 座標軸樣式（隨主題換色）。原散落各檔的 `const axis = {...}` 統一由此出。
export function chartAxis(ct: ChartTheme, fontSize = 11) {
  return { tick: { fill: ct.muted, fontSize }, stroke: ct.lineStrong } as const;
}
// recharts Tooltip 容器樣式（隨主題換色）。
export function chartTooltip(ct: ChartTheme) {
  return { background: ct.surface, border: `1px solid ${ct.line}`, borderRadius: 8, fontSize: 12, color: ct.ink };
}

// —— 圖表語意調色盤（單一事實來源；飽和色、深淺皆可讀，故用固定常數而非隨主題重讀）——
// tsx/元件內禁止再硬編這些 hex，一律 import 本模組。
// 打擊結果（spray-chart / zone-scatter 共用）
export const BATTED_OUTCOME: Record<string, string> = {
  hr: "#d62839", "3b": "#f59e0b", "2b": "#16a34a", "1b": "#1d6fb8", out: "#94a3b8",
};
// 好球帶揮打結果（zone-scatter）
export const ZONE_OUTCOME: Record<string, string> = {
  hit: "#16a34a", out: "#1d6fb8", foul: "#f59e0b", whiff: "#d62839", take: "#94a3b8",
};
// 逐球判定（game-board：壞球/擊出/界外）
export const PITCH_CALL = { ball: "#16a34a", inplay: "#2563eb", foul: "#eab308" } as const;
// 打席結果語意色（安打=綠/保送=藍；出局走中性 surface-2）。比照 PITCH_CALL，供 game-board 今日 chip。
export const PA_KIND = { hit: "#16a34a", walk: "#2563eb" } as const;
// 能力評級 S..G（ability-card）
export const GRADE_COLORS: Record<string, string> = {
  S: "#e6b422", A: "#d23a3a", B: "#e8842b", C: "#e0c53a",
  D: "#4caf50", E: "#3b82c4", F: "#7c8696", G: "#9aa3af",
};
export const gradeColor = (grade?: string | null) => (grade && GRADE_COLORS[grade]) || GRADE_COLORS.G;
// 獎牌（hero 生涯獎項：金/銀/銅）
export const MEDAL_COLORS: Record<string, string> = { 金: "#e6b422", 銀: "#9aa3af", 銅: "#b0703c" };
// 洋將身分徽章（原 lib.ts IMPORT_BADGE 的色；hint 文案仍留 lib.ts）
export const STATUS_COLORS: Record<string, string> = {
  import: "#2563eb", loree: "#0f766e", nagata: "#7c3aed",
};
// 甜甜圈/圓餅預設分類色（parts.tsx CompositionPie）——取分類序列前 4 色。
export const PIE_COLORS = ["#1b4da1", "#3b82c4", "#e8842b", "#9aa3af"];
