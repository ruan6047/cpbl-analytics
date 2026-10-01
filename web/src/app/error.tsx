"use client";

import Link from "next/link";
import { SectionTitle } from "@/components/postmark";

// 頁面錯誤邊界（#220 W5：共用語言的錯誤態）。不顯示技術細節；提供重試與回首頁。
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mx-auto max-w-2xl py-6" role="alert">
      <span className="pm-st pm-st--hold">載入失敗</span>
      <SectionTitle as="h1" className="mt-3">這一頁暫時無法顯示</SectionTitle>
      <p className="-mt-1 text-sm text-muted">資料來源可能暫時沒有回應。可以重試一次，或先回到今日賽事。</p>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" onClick={() => reset()}
          className="inline-flex min-h-11 items-center rounded-md bg-ink px-4 text-sm font-bold text-paper transition-opacity hover:opacity-90">
          重試
        </button>
        <Link href="/"
          className="inline-flex min-h-11 items-center rounded-md bg-surface px-4 text-sm font-medium text-ink no-underline transition-colors hover:bg-surface-2">
          回今日賽事
        </Link>
      </div>
    </div>
  );
}
