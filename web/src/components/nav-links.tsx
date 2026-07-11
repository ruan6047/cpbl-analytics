"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  group?: string;
};

export function NavLinks({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  // 當路徑改變時，自動關閉行動端選單
  useEffect(() => {
    setIsOpen(false);
  }, [pathname]);

  // 行動端選單打開時防止底層頁面滾動
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // 將選單項目依 group 分組，用於行動端面板的語意呈現
  const groupedItems = items.reduce((acc, item) => {
    const groupName = item.group || "其他";
    if (!acc[groupName]) acc[groupName] = [];
    acc[groupName].push(item);
    return acc;
  }, {} as Record<string, NavItem[]>);

  return (
    <>
      {/* ==================== 桌機版導覽列 ==================== */}
      <nav aria-label="主導覽" className="hidden md:flex items-center gap-x-4 text-sm text-muted">
        {items.map((n, i) => {
          const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
          const newGroup = i > 0 && n.group !== items[i - 1].group;
          return (
            <span key={n.href} className="flex items-center gap-x-4">
              {newGroup && <span aria-hidden className="h-4 w-px bg-line" />}
              <Link
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "border-b-2 border-accent pb-0.5 font-semibold text-ink"
                    : "border-b-2 border-transparent pb-0.5 transition-colors hover:text-ink"
                }
              >
                {n.label}
              </Link>
            </span>
          );
        })}
      </nav>

      {/* ==================== 行動端選單按鈕 ==================== */}
      <div className="md:hidden flex items-center">
        <button
          onClick={() => setIsOpen(!isOpen)}
          aria-expanded={isOpen}
          aria-haspopup="true"
          aria-controls="mobile-menu"
          aria-label={isOpen ? "關閉選單" : "開啟選單"}
          className="relative z-50 flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-ink transition-colors hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent"
        >
          <svg
            className="h-5 w-5 transition-transform duration-200"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2"
          >
            {isOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {/* ==================== 行動端滑出選單面板 ==================== */}
      {isOpen && (
        <div
          id="mobile-menu"
          role="dialog"
          aria-modal="true"
          aria-label="行動端選單"
          className="fixed inset-x-0 bottom-0 top-[57px] z-40 flex flex-col bg-paper/95 px-6 py-6 backdrop-blur-lg border-t border-line animate-[fadeIn_0.15s_ease-out] overflow-y-auto"
        >
          <nav className="flex-1 space-y-6 pb-8">
            {Object.entries(groupedItems).map(([groupName, groupList]) => (
              <div key={groupName} className="space-y-2">
                {/* 分組眉標 */}
                <div className="text-[11px] font-bold uppercase tracking-wider text-faint px-1">
                  {groupName}
                </div>
                {/* 雙欄按鈕佈局，利於大拇指單手操作 */}
                <div className="grid grid-cols-2 gap-2.5">
                  {groupList.map((n) => {
                    const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
                    return (
                      <Link
                        key={n.href}
                        href={n.href}
                        onClick={() => setIsOpen(false)}
                        aria-current={active ? "page" : undefined}
                        className={
                          active
                            ? "flex items-center justify-center h-11 px-3 rounded-xl bg-cpbl/10 border border-cpbl/20 text-sm font-bold text-cpbl transition-all active:scale-[0.98]"
                            : "flex items-center justify-center h-11 px-3 rounded-xl bg-surface border border-line text-sm font-medium text-ink transition-all hover:bg-surface-2 active:scale-[0.98] active:bg-surface-3"
                        }
                      >
                        {n.label}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>
        </div>
      )}
    </>
  );
}
