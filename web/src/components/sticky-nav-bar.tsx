"use client";

import { type ReactNode, useEffect, useState } from "react";

/**
 * 一體式多軸導覽欄的 sticky 殼（UI_UX_SYSTEM §4.3 D2）：由球員頁 PlayerNavigation
 * 抽出。量測全站 header 高度作為 sticky top（header 高度會隨視窗寬度變化），
 * 使導覽欄捲動時貼齊站頂欄下緣；各頁把主軸 tab 與右側 controls 放進 children。
 */
export function StickyNavBar({ label, children }: { label: string; children: ReactNode }) {
  const [stickyTop, setStickyTop] = useState(0);
  useEffect(() => {
    const header = document.querySelector("header");
    if (!header) return;
    const update = () => setStickyTop(header.getBoundingClientRect().height);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(header);
    return () => ro.disconnect();
  }, []);

  return (
    <nav aria-label={label} style={{ top: stickyTop }}
      className="sticky z-20 -mx-1 mb-6 border-b border-line bg-paper/95 px-1 py-1.5 backdrop-blur">
      {children}
    </nav>
  );
}

/**
 * 導覽欄單列版面：左側主內容軸（tablist／chip 群，捲動容器由呼叫端決定）＋
 * 右側 controls 插槽（`md:border-l` 分隔）；窄螢幕改垂直堆疊（§4.3 B1）。
 * 與 HierarchicalTabs 內部版面同源，供單層 tablist 頁（standings/games）重用。
 */
export function NavBarRow({ main, controls }: { main: ReactNode; controls?: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:justify-between">
      {main}
      {controls && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 pt-0.5 md:border-l md:border-line md:pl-3 md:pt-0">
          {controls}
        </div>
      )}
    </div>
  );
}
