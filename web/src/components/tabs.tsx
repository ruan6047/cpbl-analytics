"use client";

import { useState, type ReactNode } from "react";

// 頁籤 client island：伺服器端把各分頁內容（server-rendered ReactNode）以 items 傳入，
// 客端只掛載當前分頁。資料已在 props 內、切換不再打 API。樣式沿用全站分段控制。
export function Tabs({ items }: { items: { label: string; content: ReactNode }[] }) {
  const [active, setActive] = useState(0);
  if (items.length === 0) return null;
  const cur = Math.min(active, items.length - 1);
  return (
    <div>
      <div role="tablist" className="mb-3 inline-flex flex-wrap items-center gap-1 rounded-full border border-line bg-surface p-1">
        {items.map((it, i) => (
          <button
            key={it.label}
            type="button"
            role="tab"
            aria-selected={i === cur}
            onClick={() => setActive(i)}
            className={`rounded-full px-3 py-1 text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              i === cur ? "bg-ink text-paper" : "text-muted hover:bg-surface-2"
            }`}
          >
            {it.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">{items[cur]?.content}</div>
    </div>
  );
}
