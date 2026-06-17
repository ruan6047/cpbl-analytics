import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "CPBL 分析 | Ruan Dev",
  description: "中華職棒戰績、進階數據與賽果預測 — TrackMan/Statcast 視覺化。",
};

const NAV = [
  { href: "/", label: "戰績" },
  { href: "/batters", label: "打者" },
  { href: "/pitchers", label: "投手" },
  { href: "/games", label: "賽況" },
  { href: "/matchups", label: "投打對決" },
  { href: "/predict", label: "賽果預測" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body className="min-h-screen antialiased">
        <header className="sticky top-0 z-40 border-b border-line bg-surface/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
            <Link href="/" className="text-lg font-extrabold tracking-tight">
              <span className="text-cpbl">CPBL</span> <span className="text-accent">分析</span>
            </Link>
            <nav className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="hover:text-ink">{n.label}</Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 py-10 text-xs text-faint">
          資料來源：cpbl-opendata (MIT) + cpbl.com.tw + stats.cpbl.com.tw。僅供學習與作品集用途。
        </footer>
      </body>
    </html>
  );
}
