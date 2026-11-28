import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { THEME_COLOR, THEME_COLOR_SCRIPT, applyThemeColor } from "./theme-color.ts";

// #467：行動瀏覽器頂欄 theme-color 跟「頁面實際套用的主題」，不跟系統偏好（預設淺色不跟系統，UI_UX_SYSTEM §2.2）。
// Next 的 viewport.themeColor 固定給淺色；深色時在 <head> 最前面插一個覆寫 meta（規格取第一個符合者）。

const globals = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");

test("THEME_COLOR 鏡像 globals.css --color-surface 淺／深（頂欄卡面色；防 drift）", () => {
  const all = [...globals.matchAll(/--color-surface:\s*(#[0-9a-fA-F]{6})/g)].map((m) => m[1].toLowerCase());
  assert.equal(all.length, 2, "globals.css 應恰有淺色 @theme 與 [data-theme=dark] 兩處 --color-surface");
  assert.equal(THEME_COLOR.light, all[0]);
  assert.equal(THEME_COLOR.dark, all[1]);
});

test("layout：viewport.themeColor 改由 THEME_COLOR 給，不再依 prefers-color-scheme", () => {
  assert.doesNotMatch(layout, /prefers-color-scheme/);
  assert.match(layout, /themeColor:\s*THEME_COLOR\.light/);
  assert.match(layout, /THEME_COLOR_SCRIPT/);
});

// ---- 最小假 DOM：只實作覆寫邏輯會碰到的介面 ----
type FakeEl = { tag: string; attrs: Record<string, string>; parent: FakeHead | null; setAttribute(k: string, v: string): void; getAttribute(k: string): string | null; hasAttribute(k: string): boolean; remove(): void };
type FakeHead = { children: FakeEl[]; firstChild: FakeEl | null; insertBefore(n: FakeEl, ref: FakeEl | null): void; appendChild(n: FakeEl): void; querySelectorAll(sel: string): FakeEl[] };

function fakeDoc(initial: { content: string }[] = []) {
  const head: FakeHead = {
    children: [],
    get firstChild() { return this.children[0] ?? null; },
    insertBefore(n, ref) { n.parent = head; const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(n); else this.children.splice(i, 0, n); },
    appendChild(n) { n.parent = head; this.children.push(n); },
    querySelectorAll(sel) {
      assert.equal(sel, 'meta[name="theme-color"][data-theme-override]', `未預期的 selector：${sel}`);
      return this.children.filter((c) => c.tag === "meta" && c.attrs.name === "theme-color" && "data-theme-override" in c.attrs);
    },
  };
  const make = (tag: string): FakeEl => ({
    tag, attrs: {}, parent: null,
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k] ?? null; },
    hasAttribute(k) { return k in this.attrs; },
    remove() { if (this.parent) { this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; } },
  });
  for (const m of initial) { const el = make("meta"); el.setAttribute("name", "theme-color"); el.setAttribute("content", m.content); head.appendChild(el); }
  const doc = { head, createElement: make };
  // 依 HTML 規格：取第一個 name=theme-color 的 meta（本卡不帶 media）。
  const effective = () => head.children.find((c) => c.tag === "meta" && c.attrs.name === "theme-color")?.attrs.content ?? null;
  const overrides = () => head.querySelectorAll('meta[name="theme-color"][data-theme-override]').length;
  return { doc, head, effective, overrides };
}

test("applyThemeColor：深色插到 head 最前面且只有一個；淺色移除覆寫；Next 之後重建的 meta 排在後面不影響", () => {
  const f = fakeDoc([{ content: THEME_COLOR.light }]);
  assert.equal(f.effective(), THEME_COLOR.light);
  applyThemeColor("dark", f.doc as unknown as Document);
  assert.equal(f.effective(), THEME_COLOR.dark);
  applyThemeColor("dark", f.doc as unknown as Document);
  assert.equal(f.overrides(), 1, "重複套用不得疊出多個覆寫");
  // 模擬 Next client 換頁：viewport meta 被移除後 append 回 head 末端。
  const next = f.head.children.find((c) => !c.hasAttribute("data-theme-override"))!;
  next.remove();
  f.head.appendChild(next);
  assert.equal(f.effective(), THEME_COLOR.dark);
  applyThemeColor("light", f.doc as unknown as Document);
  assert.equal(f.overrides(), 0);
  assert.equal(f.effective(), THEME_COLOR.light);
});

test("THEME_COLOR_SCRIPT（首繪 inline script）：與 applyThemeColor 同語意；data-theme 規則不變（只有 localStorage=dark 才深色）", () => {
  for (const [stored, theme, color] of [["dark", "dark", THEME_COLOR.dark], ["light", "light", THEME_COLOR.light], [null, "light", THEME_COLOR.light]] as const) {
    const f = fakeDoc([{ content: THEME_COLOR.light }]);
    const attrs: Record<string, string> = {};
    const document = { ...f.doc, documentElement: { setAttribute: (k: string, v: string) => { attrs[k] = v; } } };
    const localStorage = { getItem: (k: string) => (k === "theme" ? stored : null) };
    new Function("document", "localStorage", THEME_COLOR_SCRIPT)(document, localStorage);
    assert.equal(attrs["data-theme"], theme, `localStorage=${stored}`);
    assert.equal(f.effective(), color, `localStorage=${stored}`);
    assert.ok(f.overrides() <= 1);
  }
});
