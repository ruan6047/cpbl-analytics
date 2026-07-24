"use client";

import { type ReactNode, useState } from "react";
import { TabItems } from "@/components/hierarchical-tabs";
import { NavBarRow, StickyNavBar } from "@/components/sticky-nav-bar";

// 紀錄室分區頁籤（UI 審 r7）：長頁直落改單層 tablist（比照 standings seg 的
// TabItems 視覺＋StickyNavBar flush 貼線）。各區內容由 server 一次備妥（props 傳入
// ReactNode），客端只切換掛載，不重打 API——同 teams 頁「資料已在 props」模式。
export function SectionTabs({ label, items }: {
  label: string;
  items: { label: string; content: ReactNode }[];
}) {
  const [active, setActive] = useState(items[0]?.label ?? "");
  const cur = items.find((item) => item.label === active) ?? items[0];
  if (!cur) return null;
  return (
    <div>
      <StickyNavBar label={label} flush>
        <NavBarRow
          align="end"
          main={
            <div className="flex min-w-0 items-center overflow-x-auto overscroll-x-contain">
              <TabItems label={label} value={cur.label} onChange={setActive}
                items={items.map((item) => ({ value: item.label, label: item.label }))} />
            </div>
          }
        />
      </StickyNavBar>
      <div role="tabpanel" aria-label={cur.label}>{cur.content}</div>
    </div>
  );
}
