import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { NavLinks } from "@/components/nav-links";
import PlayerSearch from "@/components/player-search";
import { ThemeToggle } from "@/components/theme-toggle";
import { Outfit } from "next/font/google";
import "./globals.css";

export const metadata: Metadata = {
  title: "CPBL 分析 | Ruan Dev",
  description: "中華職棒戰績、進階數據與賽事預測 — TrackMan/Statcast 視覺化。",
};

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

// 行動瀏覽器頂欄配色跟隨系統深淺（data-theme 覆寫時 UI 內底色仍由 CSS token 處理）
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7fa" },
    { media: "(prefers-color-scheme: dark)", color: "#0a1626" },
  ],
};

// 首繪前（阻塞）決定主題：**預設淺色（一般模式）**，只有使用者曾手動切成深色才用深色。
// 不跟隨系統偏好（避免深色系統使用者被迫進深色）。掛在 <head> 確保早於 <body> 繪製、無 FOUC。
const NO_FLASH = `(function(){try{var t=localStorage.getItem('theme');document.documentElement.setAttribute('data-theme',t==='dark'?'dark':'light');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className={outfit.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body className="min-h-screen antialiased">
        <a href="#main" className="skip-link">跳至主內容</a>
        <header className="sticky top-0 z-40 border-b border-line bg-surface/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
            <Link href="/" className="text-lg font-extrabold tracking-tight">
              <span className="text-cpbl">CPBL</span> <span className="text-accent">分析</span>
            </Link>
            {/* 全域球員搜尋（§5.5）：桌機常駐頂欄；行動端置於選單面板內 */}
            <div className="hidden md:block flex-1 max-w-xs">
              <PlayerSearch variant="header" />
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <NavLinks />
            </div>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl border-t border-line/75 px-6 py-8 mt-12 text-xs text-faint flex flex-col md:flex-row items-center justify-between gap-4">
          <div>
            資料來源：cpbl-opendata (MIT) + cpbl.com.tw + stats.cpbl.com.tw。僅供學習與作品集用途。
          </div>
          <div>
            © {new Date().getFullYear()} CPBL Analytics.
          </div>
        </footer>
      </body>
    </html>
  );
}
