import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "CPBL 成績預測 | Ruan Dev",
  description: "中華職棒球員成績預測 — Marcel baseline + LightGBM,公開回測準確率。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body className="min-h-screen antialiased">
        <header className="border-b border-white/10">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-bold tracking-tight">
              CPBL <span className="text-emerald-400">成績預測</span>
            </Link>
            <span className="text-xs text-white/40">Marcel + LightGBM</span>
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
