import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "CPBL 分析 | Ruan Dev",
  description: "中華職棒本季戰績與單場賽果預測 — 透明變因、可調權重。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body className="min-h-screen antialiased">
        <header className="border-b border-white/10">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-bold tracking-tight">
              CPBL <span className="text-emerald-400">分析</span>
            </Link>
            <nav className="flex gap-4 text-sm text-white/50">
              <Link href="/" className="hover:text-emerald-400">本季戰績</Link>
              <Link href="/batters" className="hover:text-emerald-400">打者</Link>
              <Link href="/pitchers" className="hover:text-emerald-400">投手</Link>
              <Link href="/fielding" className="hover:text-emerald-400">守備</Link>
              <Link href="/matchups" className="hover:text-emerald-400">投打對決</Link>
              <Link href="/predict" className="hover:text-emerald-400">賽果預測</Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-5xl px-6 py-10 text-xs text-white/30">
          資料來源:cpbl-opendata (MIT) + cpbl.com.tw。僅供學習與作品集用途。
        </footer>
      </body>
    </html>
  );
}
