import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { NavLinks } from "@/components/nav-links";
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

// group 變化處插入視覺分隔：賽事｜數據｜預測
const NAV = [
  { href: "/", label: "戰績", group: "賽事" },
  { href: "/games", label: "賽況", group: "賽事" },
  { href: "/matchups", label: "投打對決", group: "賽事" },
  { href: "/batters", label: "打者", group: "數據" },
  { href: "/pitchers", label: "投手", group: "數據" },
  { href: "/records", label: "紀錄室", group: "數據" },
  { href: "/venues", label: "球場", group: "數據" },
  { href: "/umpires", label: "裁判報告", group: "數據" },
  { href: "/projections", label: "成績預測", group: "預測" },
  { href: "/predict", label: "賽事預測", group: "預測" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className={outfit.variable}>
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
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <NavLinks items={NAV} />
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
