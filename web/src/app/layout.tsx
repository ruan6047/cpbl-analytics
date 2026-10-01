import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { NavLinks } from "@/components/nav-links";
import PlayerSearch from "@/components/player-search";
import { ThemeToggle } from "@/components/theme-toggle";
import { BrandMark } from "@/components/brand-mark";
import { Archivo, LXGW_WenKai_TC, Noto_Sans_TC } from "next/font/google";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://cpbl.ruan-ruan.com"),
  title: { default: "Ruan's CPBL Lab", template: "%s | Ruan's CPBL Lab" },
  // 「數據實驗室」須與站名一致（原用詞與站名不同，屬命名收斂漏網）。
  // 註解刻意不複述舊用詞，讓 grep 守衛維持可用。
  // 已知並接受「數據」在本句重複兩次——「進階數據」是對應官方進階數據的既定術語，
  // 不為修辭而動既定術語，品牌一致性優先。
  description: "中華職棒戰績、進階數據與賽事預測的非官方數據實驗室。",
  openGraph: { type: "website", locale: "zh_TW", siteName: "Ruan's CPBL Lab" },
  twitter: { card: "summary_large_image" },
};

// #218 核可字體：Archivo（寬體數字與字標，用 wdth 軸壓縮）、Noto Sans TC（內文）、
// 霞鶩文楷 TC（手札註記，每區最多一句）。兩套中文字型不 preload：Google 依 unicode-range
// 切片，瀏覽器只下載畫面實際用到的字；文楷只在 .pm-hand 出現時才會被請求。
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });
const notoTC = Noto_Sans_TC({ subsets: ["latin"], variable: "--font-noto-tc", display: "swap", preload: false });
const wenkaiTC = LXGW_WenKai_TC({ weight: "400", subsets: ["latin"], variable: "--font-wenkai-tc", display: "swap", preload: false });

// 行動瀏覽器頂欄配色跟隨系統深淺（data-theme 覆寫時 UI 內底色仍由 CSS token 處理）；
// 值＝頂欄卡面色（globals.css --color-surface 淺／深）。
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f5f0" },
    { media: "(prefers-color-scheme: dark)", color: "#1a2229" },
  ],
};

// 首繪前（阻塞）決定主題：**預設淺色（一般模式）**，只有使用者曾手動切成深色才用深色。
// 不跟隨系統偏好（避免深色系統使用者被迫進深色）。掛在 <head> 確保早於 <body> 繪製、無 FOUC。
const NO_FLASH = `(function(){try{var t=localStorage.getItem('theme');document.documentElement.setAttribute('data-theme',t==='dark'?'dark':'light');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className={`${archivo.variable} ${notoTC.variable} ${wenkaiTC.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body className="min-h-screen antialiased">
        <a href="#main" className="skip-link">跳至主內容</a>
        {/* 頂欄（#218）：卡面底＋墨色底線；字標＝打孔標誌＋壓縮體。實心底不做毛玻璃。
            子元素以 order 排序：字標 → 桌機導覽 → 搜尋（推到右側）→ 主題 → 行動選單鈕；
            NavLinks 回傳的桌機導覽與行動選單鈕是兩個直接子元素，各自帶 order。 */}
        <header className="pm-site sticky top-0 z-40">
          <div className="mx-auto flex h-[54px] max-w-6xl items-center gap-2.5 px-3.5 md:h-[60px] md:gap-5 md:px-6">
            <Link href="/" aria-label="Ruan's CPBL Lab 首頁" className="order-0 flex shrink-0 items-center gap-2.5 no-underline">
              <span className="pm-punch"><BrandMark className="h-[21px] w-[21px]" /></span>
              <span className="pm-word">Ruan&apos;s CPBL Lab<small>中職數據實驗室</small></span>
            </Link>
            <NavLinks />
            {/* 全域球員搜尋（§5.5）：桌機常駐頂欄；行動端置於選單面板內 */}
            <div className="order-2 ml-auto hidden w-56 md:block">
              <PlayerSearch variant="header" />
            </div>
            <div className="order-3 ml-auto md:ml-0">
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-6xl px-3.5 py-6 md:px-6 md:py-8">{children}</main>
        <footer className="mt-12 bg-surface-2 text-[12.5px] text-muted">
          <div className="mx-auto flex max-w-6xl flex-col justify-between gap-3 px-3.5 pb-8 pt-6 md:flex-row md:px-6">
            <div className="max-w-2xl">
              非官方獨立專案，與中華職棒大聯盟無隸屬關係。資料來源：cpbl-opendata (MIT)、cpbl.com.tw、stats.cpbl.com.tw。
            </div>
            <div className="md:text-right">
              <div>作者 Ruan Ruan · <a className="underline decoration-accent underline-offset-2 hover:text-ink" href="https://ruan-ruan.com">ruan-ruan.com</a> · <a className="underline decoration-accent underline-offset-2 hover:text-ink" href="https://github.com/ruan6047/cpbl-analytics">GitHub</a></div>
              <div className="mt-1">© {new Date().getFullYear()} Ruan&apos;s CPBL Lab.</div>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
