"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import PlayerSearch from "@/components/player-search";
import { MORE_NAV, PRIMARY_NAV, isMoreActive, isNavActive, type NavItem } from "@/lib/nav";

export function NavLinks() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [isMoreOpen, setIsMoreOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const isMounted = useRef(false);
  const [menuTop, setMenuTop] = useState(0);
  const [canPortal, setCanPortal] = useState(false);

  // 面板 portal 到 body：不受 sticky header 的層疊與日後可能出現的 containing block
  // （backdrop-filter／transform 等）影響；曾因 header 的 backdrop-blur 被夾成 49px 高而無法點擊。
  useEffect(() => {
    setCanPortal(true);
  }, []);

  // 依實際 header 底緣定位，避免寫死高度與真實版面漂移（觸控目標改 44px 後高度已變）。
  useEffect(() => {
    if (!isOpen) return;
    const header = buttonRef.current?.closest("header");
    if (!header) return;
    const measure = () => setMenuTop(header.getBoundingClientRect().bottom);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [isOpen]);

  // 當路徑改變時，自動關閉行動端選單與「更多」
  useEffect(() => {
    setIsOpen(false);
    setIsMoreOpen(false);
  }, [pathname]);

  // 行動端選單打開時防止底層頁面滾動、處理 Escape 關閉
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          setIsOpen(false);
        }
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => {
        document.body.style.overflow = "";
        window.removeEventListener("keydown", handleKeyDown);
      };
    } else {
      document.body.style.overflow = "";
    }
  }, [isOpen]);

  // 「更多」展開時：點外部或 Escape 關閉，Escape 後焦點回按鈕
  useEffect(() => {
    if (!isMoreOpen) return;
    const onPointerDown = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setIsMoreOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsMoreOpen(false);
        moreButtonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isMoreOpen]);

  // 行動選單開關時的焦點管理
  useEffect(() => {
    if (!isMounted.current) {
      isMounted.current = true;
      return;
    }
    if (isOpen) {
      if (menuRef.current) {
        menuRef.current.focus();
      }
    } else {
      if (buttonRef.current) {
        buttonRef.current.focus();
      }
    }
  }, [isOpen]);

  // 焦點陷阱 (Focus Trap)
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab") return;
    if (!menuRef.current) return;
    const focusables = menuRef.current.querySelectorAll<HTMLElement>(
      'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first) {
        last.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    }
  };

  const desktopLink = (n: NavItem) => {
    const active = isNavActive(n, pathname);
    return (
      <Link
        key={n.href}
        href={n.href}
        aria-current={active ? "page" : undefined}
        // 選中＝底緣 3px 石油藍（#218 頂欄）；hover 換石油藍字。
        className={`pb-[15px] pt-[18px] text-ink transition-colors hover:text-accent ${
          active ? "shadow-[inset_0_-3px_0_var(--color-accent)]" : ""
        }`}
      >
        {n.label}
      </Link>
    );
  };

  const moreActive = isMoreActive(pathname);

  return (
    <>
      {/* ==================== 桌機版導覽列 ==================== */}
      <nav aria-label="主導覽" className="order-1 ml-3 hidden items-center gap-x-5 text-sm font-bold md:flex">
        {PRIMARY_NAV.map(desktopLink)}

        {/* 「更多」收納紀錄室／球場／賽事預測（§4.1；紀錄室桌機位置依需求方 §12-2 決策維持於此） */}
        <div ref={moreRef} className="relative">
          <button
            ref={moreButtonRef}
            type="button"
            onClick={() => setIsMoreOpen((v) => !v)}
            aria-expanded={isMoreOpen}
            aria-haspopup="menu"
            aria-controls="more-menu"
            className={`flex items-center gap-1 pb-[15px] pt-[18px] font-bold text-ink transition-colors hover:text-accent ${
              moreActive ? "shadow-[inset_0_-3px_0_var(--color-accent)]" : ""
            }`}
          >
            更多
            <svg aria-hidden className={`h-3 w-3 transition-transform ${isMoreOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {isMoreOpen && (
            <div
              id="more-menu"
              role="menu"
              aria-label="更多"
              className="absolute right-0 z-40 mt-1 w-36 rounded-md border border-line bg-surface p-1 font-medium shadow-[0_6px_18px_-6px_rgb(0_0_0/0.25)]"
            >
              {MORE_NAV.map((n) => {
                const active = isNavActive(n, pathname);
                return (
                  <Link
                    key={n.href}
                    href={n.href}
                    role="menuitem"
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-sm px-3 py-2 text-sm transition-colors ${
                      active ? "bg-ink font-bold text-paper" : "text-ink hover:bg-surface-2"
                    }`}
                  >
                    {n.label}
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </nav>

      {/* ==================== 行動端選單按鈕 ==================== */}
      <div className="order-4 flex items-center md:hidden">
        <button
          ref={buttonRef}
          onClick={() => setIsOpen(!isOpen)}
          aria-expanded={isOpen}
          aria-haspopup="dialog"
          aria-controls="mobile-menu"
          aria-label={isOpen ? "關閉選單" : "開啟選單"}
          className="relative z-50 flex h-11 w-11 items-center justify-center rounded-md border border-line-strong bg-transparent text-ink transition-colors hover:bg-surface-2"
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
      {isOpen && canPortal && createPortal(
        <div
          ref={menuRef}
          id="mobile-menu"
          role="dialog"
          aria-modal="true"
          aria-label="行動端選單"
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          style={{ top: menuTop }}
          className="md:hidden fixed inset-x-0 bottom-0 z-40 flex flex-col overflow-y-auto bg-paper px-4 py-5 outline-none animate-fade-in"
        >
          {/* 行動端頂欄沒有空間放搜尋，改置於面板首位（§5.5 全域球員搜尋於 375px 仍可達） */}
          <div className="mb-6">
            <PlayerSearch />
          </div>
          <nav aria-label="主導覽" className="flex-1 space-y-6 pb-8">
            {[
              { name: "主要", items: PRIMARY_NAV },
              { name: "更多", items: MORE_NAV },
            ].map(({ name, items }) => (
              <div key={name} className="space-y-2">
                <div className="px-1 text-xs font-bold text-muted">{name}</div>
                {/* 雙欄按鈕佈局，利於大拇指單手操作 */}
                <div className="grid grid-cols-2 gap-2.5">
                  {items.map((n) => {
                    const active = isNavActive(n, pathname);
                    return (
                      <Link
                        key={n.href}
                        href={n.href}
                        onClick={() => setIsOpen(false)}
                        aria-current={active ? "page" : undefined}
                        className={
                          active
                            ? "flex h-11 items-center justify-center rounded-md bg-ink px-3 text-sm font-bold text-paper"
                            : "flex h-11 items-center justify-center rounded-md bg-surface px-3 text-sm font-medium text-ink transition-colors hover:bg-surface-2 active:bg-surface-2"
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
        </div>,
        document.body
      )}
    </>
  );
}
