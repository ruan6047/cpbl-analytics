import Link from "next/link";
import { SectionTitle } from "@/components/postmark";

// 404（#220 W5：沿用 #218 共用語言——區塊標題、狀態章、卡面色塊；不另起插圖或裝飾）。
export const metadata = { title: "找不到頁面" };

export default function NotFound() {
  return (
    <div className="mx-auto max-w-2xl py-6">
      <span className="pm-st pm-st--sample">404</span>
      <SectionTitle as="h1" className="mt-3">找不到這一頁</SectionTitle>
      <p className="-mt-1 text-sm text-muted">網址可能已變更，或這場比賽、球員、球隊在資料中不存在。可以從下面的入口繼續：</p>
      <nav aria-label="常用入口" className="mt-5 flex flex-wrap gap-2">
        {[["/", "今日賽事"], ["/games", "賽程與賽況"], ["/standings", "戰績"], ["/batters", "打者排行"]].map(([href, label]) => (
          <Link key={href} href={href}
            className="inline-flex min-h-11 items-center rounded-md bg-surface px-4 text-sm font-medium text-ink no-underline transition-colors hover:bg-surface-2">
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
