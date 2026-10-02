"use client";

import { type ReactNode, useState } from "react";
import { MainTabs, TabPanel, mainTabId } from "@/components/hierarchical-tabs";
import { StickyNavBar } from "@/components/sticky-nav-bar";

// 紀錄室分區頁籤（UI 審 r7）：長頁直落改單層 tablist（StickyNavBar flush＋#218 一級頁籤帶，
// 下接同色 TabPanel）。各區內容由 server 一次備妥（props 傳入 ReactNode），客端只切換掛載，
// 不重打 API——同 teams 頁「資料已在 props」模式。
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
        <MainTabs label={label} value={cur.label} onChange={setActive} panelId="records-panel"
          items={items.map((item) => ({ value: item.label, label: item.label }))} />
      </StickyNavBar>
      <TabPanel id="records-panel" labelledBy={mainTabId("records-panel", cur.label)}>{cur.content}</TabPanel>
    </div>
  );
}
