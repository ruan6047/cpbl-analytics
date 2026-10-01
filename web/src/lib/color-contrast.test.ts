import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

/**
 * 設計 token 的可及性守衛。
 *
 * 涵蓋：不透明的一般文字語意色（accent/down/up）在 paper、surface、
 * surface-2 三層文字底色的深淺模式組合，門檻為本專案採用的 4.60:1。
 * （#220：amber 拆為延賽・保留＝down 紅字狀態章、二軍・獎項＝身分標籤；cpbl 品牌藍退役。
 *  band 只承載 muted 表頭字與 ink 選中字，不放語意色文字，故不列入。）
 *
 * 不涵蓋：faint（設計系統明定僅限輔助資訊）、圖表／隊色／status 色、帶 alpha 的
 * 背景與元件巢狀實際組合；那些需要個別元件的瀏覽器回歸驗證。
 */
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const MIN_TEXT_CONTRAST = 4.6;
const FOREGROUNDS = ["accent", "down", "up"] as const;
const BACKGROUNDS = ["paper", "surface", "surface-2"] as const;

function token(name: string, mode: "light" | "dark"): string {
  const source = mode === "light" ? css : css.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1];
  assert.ok(source, `${mode} mode token block is missing`);
  const match = source.match(new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})`));
  assert.ok(match, `${mode} mode is missing --color-${name}`);
  return match[1].toLowerCase();
}

function luminance(hex: string): number {
  const channels = hex.slice(1).match(/.{2}/g)?.map((part) => Number.parseInt(part, 16) / 255);
  assert.equal(channels?.length, 3, `invalid hex color: ${hex}`);
  const [red, green, blue] = channels.map((channel) => (
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  ));
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(foreground: string, background: string): number {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

test("一般文字語意 token 在三層底色的深淺模式皆保有 4.60:1 對比", () => {
  for (const mode of ["light", "dark"] as const) {
    for (const foreground of FOREGROUNDS) {
      for (const background of BACKGROUNDS) {
        const ratio = contrast(token(foreground, mode), token(background, mode));
        assert.ok(
          ratio >= MIN_TEXT_CONTRAST,
          `${mode} ${foreground} on ${background} is ${ratio.toFixed(2)}:1; expected >= ${MIN_TEXT_CONTRAST}:1`,
        );
      }
    }
  }
});

// #218 核可：accent＝石油藍（互動／焦點），down＝紅（數據差、延賽・保留）。兩者分屬不同語意，
// 不可再合併成同一色——否則行動連結會被讀成負向訊號。
test("accent 與 down 分屬兩色，互動不被讀成負向訊號", () => {
  for (const mode of ["light", "dark"] as const) {
    assert.notEqual(token("accent", mode), token("down", mode), `${mode} accent/down collapsed`);
  }
});
