// #467：行動瀏覽器頂欄 theme-color 跟「頁面實際套用的主題」（<html data-theme>），不跟系統偏好。
//
// 作法：Next 的 viewport.themeColor 固定給淺色（＝預設主題，無 JS 時也成立）；深色時由首繪 inline script 與
// ThemeToggle 在 <head> **最前面**插一個帶 data-theme-override 的深色 meta，切回淺色就移除。
// HTML 規格取第一個符合的 theme-color meta，覆寫排第一就生效。
// ⛔ 不改 Next 產生的那個 meta 的 content：React 依 content 認領 head 內的 meta，Next client 換頁也會以伺服器值
//    重建 viewport meta（remount 後 append 到後面），改它的值會被寫回或多出重複節點。覆寫是另一個節點，不受影響。
// 值＝頂欄卡面色（globals.css --color-surface 淺／深；theme-color.test.ts 防 drift）。

export const THEME_COLOR = { light: "#f7f5f0", dark: "#1a2229" } as const;

export type AppliedTheme = "light" | "dark";

const OVERRIDE_SELECTOR = 'meta[name="theme-color"][data-theme-override]';

/** 依實際主題增刪深色覆寫 meta（ThemeToggle 用；首繪由 THEME_COLOR_SCRIPT 做同一件事）。 */
export function applyThemeColor(theme: AppliedTheme, doc: Document = document): void {
  doc.head.querySelectorAll(OVERRIDE_SELECTOR).forEach((m) => m.remove());
  if (theme !== "dark") return;
  const meta = doc.createElement("meta");
  meta.setAttribute("name", "theme-color");
  meta.setAttribute("content", THEME_COLOR.dark);
  meta.setAttribute("data-theme-override", "");
  doc.head.insertBefore(meta, doc.head.firstChild);
}

/**
 * 首繪前（阻塞）決定主題的 inline script：**預設淺色（一般模式）**，只有使用者曾手動切成深色才用深色；
 * 不跟隨系統偏好（避免深色系統使用者被迫進深色）。深色時同步插入 theme-color 覆寫（語意同 applyThemeColor）。
 * inline script 無法 import，故以樣板字串帶入常數。
 */
export const THEME_COLOR_SCRIPT =
  `(function(){try{var t=localStorage.getItem('theme')==='dark'?'dark':'light';` +
  `document.documentElement.setAttribute('data-theme',t);` +
  `var h=document.head;h.querySelectorAll(${JSON.stringify(OVERRIDE_SELECTOR)}).forEach(function(m){m.remove();});` +
  `if(t==='dark'){var m=document.createElement('meta');m.setAttribute('name','theme-color');` +
  `m.setAttribute('content',${JSON.stringify(THEME_COLOR.dark)});m.setAttribute('data-theme-override','');` +
  `h.insertBefore(m,h.firstChild);}}catch(e){}})();`;
