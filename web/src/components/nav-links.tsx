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

  // 面板 portal 到 body：header 的 backdrop-blur 會為 fixed 子元素建立 containing block，
  // 面板若留在 header 內會被夾成 header 的高度（實測 49px）而無法點擊。
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
        className={
          active
            ? "border-b-2 border-accent pb-0.5 font-semibold text-ink"
            : "border-b-2 border-transparent pb-0.5 transition-colors hover:text-ink"
        }
      >
        {n.label}
      </Link>
    );
  };

  const moreActive = isMoreActive(pathname);

  return (
    <>
      {/* ==================== 桌機版導覽列 ==================== */}
      <nav aria-label="主導覽" className="hidden md:flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] lg:text-sm text-muted">
        {PRIMARY_NAV.map(desktopLink)}

        <span aria-hidden className="h-4 w-px bg-line" />

        {/* 「更多」收納紀錄室／球場／賽事預測（§4.1；紀錄室桌機位置依需求方 §12-2 決策維持於此） */}
        <div ref={moreRef} className="relative">
          <button
            ref={moreButtonRef}
            type="button"
            onClick={() => setIsMoreOpen((v) => !v)}
            aria-expanded={isMoreOpen}
            aria-haspopup="menu"
            aria-controls="more-menu"
            className={`flex items-center gap-1 border-b-2 pb-0.5 transition-colors ${
              moreActive ? "border-accent font-semibold text-ink" : "border-transparent hover:text-ink"
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
              className="absolute right-0 z-40 mt-2 w-36 rounded-xl border border-line bg-surface p-1 shadow-lg"
            >
              {MORE_NAV.map((n) => {
                const active = isNavActive(n, pathname);
                return (
                  <Link
                    key={n.href}
                    href={n.href}
                    role="menuitem"
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-lg px-3 py-2 text-sm transition ${
                      active ? "bg-surface-2 font-semibold text-ink" : "text-muted hover:bg-surface-2 hover:text-ink"
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
      <div className="md:hidden flex items-center">
        <button
          ref={buttonRef}
          onClick={() => setIsOpen(!isOpen)}
          aria-expanded={isOpen}
          aria-haspopup="dialog"
          aria-controls="mobile-menu"
          aria-label={isOpen ? "關閉選單" : "開啟選單"}
          className="relative z-50 flex h-11 w-11 items-center justify-center rounded-lg border border-line bg-surface text-ink transition-colors hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent"
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
          className="md:hidden fixed inset-x-0 bottom-0 z-40 flex flex-col bg-paper/95 px-6 py-6 backdrop-blur-lg border-t border-line animate-fade-in overflow-y-auto outline-none"
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
                <div className="text-[11px] font-bold uppercase tracking-wider text-faint px-1">{name}</div>
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
                            ? "flex items-center justify-center h-11 px-3 rounded-xl bg-accent/10 border border-accent/20 text-sm font-bold text-accent transition-all active:scale-[0.98]"
                            : "flex items-center justify-center h-11 px-3 rounded-xl bg-surface border border-line text-sm font-medium text-ink transition-all hover:bg-surface-2 active:scale-[0.98] active:bg-surface-2"
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
