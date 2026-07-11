"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

// 深淺主題切換。初值由 layout 的 no-flash inline script 在首繪前寫入 <html data-theme>；
// 本元件掛載後才讀該屬性同步 UI，避免 SSR/CSR 標記不一致（hydration mismatch）。
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const current = (document.documentElement.getAttribute("data-theme") as Theme) || "light";
    setTheme(current);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* 無痕/封鎖 localStorage 時忽略：主題僅本次 session 生效 */
    }
    setTheme(next);
  };

  // 掛載前保留等寬佔位，避免切換鈕造成版位跳動（CLS）
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "切換為淺色模式" : "切換為深色模式"}
      title={isDark ? "淺色模式" : "深色模式"}
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-ink"
    >
      {theme === null ? (
        <span className="h-4 w-4" />
      ) : isDark ? (
        // 太陽（點擊回淺色）
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="h-4 w-4">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        // 月亮（點擊進深色）
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}
