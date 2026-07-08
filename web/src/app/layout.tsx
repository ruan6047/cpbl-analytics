import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { NavLinks } from "@/components/nav-links";
import { Outfit } from "next/font/google";
import "./globals.css";

export const metadata: Metadata = {
  title: "CPBL 分析 | Ruan Dev",
  description: "中華職棒戰績、進階數據與賽事預測 — TrackMan/Statcast 視覺化。",
};

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

// 行動瀏覽器頂欄配色跟隨頁面底色（--color-paper）
export const viewport: Viewport = { themeColor: "#f5f7fa" };

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
      <body className="min-h-screen antialiased">
        <a href="#main" className="skip-link">跳至主內容</a>
        <header className="sticky top-0 z-40 border-b border-line bg-surface/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
            <Link href="/" className="text-lg font-extrabold tracking-tight">
              <span className="text-cpbl">CPBL</span> <span className="text-accent">分析</span>
            </Link>
            <NavLinks items={NAV} />
          </div>
        </header>
        <main id="main" className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 py-10 text-xs text-faint">
          資料來源：cpbl-opendata (MIT) + cpbl.com.tw + stats.cpbl.com.tw。僅供學習與作品集用途。
        </footer>
      </body>
    </html>
  );
}
