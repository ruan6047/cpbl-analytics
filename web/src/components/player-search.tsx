"use client";

import { useState, useEffect, useRef, useId } from "react";
import { useRouter } from "next/navigation";
import { TeamLogo, Skeleton } from "@/components/ui";
import { detail } from "@/lib/client";
import {
  filterPlayers,
  roleLabel,
  toSearchItems,
  type PlayerSearchItem,
} from "@/lib/player-search-filter";

type Status = "idle" | "loading" | "ready" | "error";

/**
 * 全域球員搜尋（§5.5）：選定結果直接進 /players/[id]，不經 landing。
 * header 版本置於頂欄，hero 版本供首頁大搜尋框沿用同一份行為。
 */
export default function PlayerSearch({ variant = "hero" }: { variant?: "hero" | "header" }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [players, setPlayers] = useState<PlayerSearchItem[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listboxId = useId();

  const isHeader = variant === "header";
  const results = filterPlayers(players, query);
  const showList = isOpen && query.trim().length > 0;

  // 點擊外部關閉下拉選單
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 結果變動時把高亮拉回第一筆，避免指到已消失的項目
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  // 鍵盤移動時讓高亮項保持在可視範圍
  useEffect(() => {
    if (!showList) return;
    listRef.current?.querySelector<HTMLElement>('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, showList]);

  const loadRoster = async () => {
    if (status === "loading" || status === "ready") return;
    setStatus("loading");
    try {
      const data = await detail.roster();
      setPlayers(toSearchItems(data));
      setStatus("ready");
    } catch (e) {
      console.error("Failed to load player roster for search", e);
      setStatus("error");
    }
  };

  const go = (player: PlayerSearchItem) => {
    setIsOpen(false);
    setQuery("");
    router.push(`/players/${player.id}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      if (query) setQuery("");
      setIsOpen(false);
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!showList || results.length === 0) return;
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((i) => (i + step + results.length) % results.length);
      return;
    }
    if (e.key === "Enter") {
      const target = results[activeIndex];
      if (showList && target) {
        e.preventDefault();
        go(target);
      }
    }
  };

  return (
    <div
      ref={containerRef}
      className={isHeader ? "relative w-full max-w-[13rem] lg:max-w-xs" : "relative z-20 mx-auto w-full max-w-md"}
    >
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={showList && results[activeIndex] ? `${listboxId}-${activeIndex}` : undefined}
          aria-label="搜尋球員"
          placeholder={isHeader ? "搜尋球員…" : "搜尋球員姓名或球隊 (例如: 林立、兄弟)..."}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
            void loadRoster();
          }}
          onFocus={() => {
            setIsOpen(true);
            void loadRoster();
          }}
          onKeyDown={handleKeyDown}
          className={
            isHeader
              ? "w-full rounded-full border border-line bg-surface-2 py-1.5 pl-8 pr-3 text-[13px] text-ink outline-none transition focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent/15"
              : "w-full rounded-full border border-line bg-surface-2 px-5 py-3 pl-11 text-sm text-ink outline-none transition focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent/15"
          }
        />
        <svg
          aria-hidden
          className={
            isHeader
              ? "pointer-events-none absolute left-3 top-2 h-4 w-4 text-faint"
              : "pointer-events-none absolute left-4 top-3.5 h-4.5 w-4.5 text-faint"
          }
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        {query && !isHeader && (
          <button
            type="button"
            aria-label="清除搜尋"
            onClick={() => {
              setQuery("");
              inputRef.current?.focus();
            }}
            className="absolute right-4 top-3.5 text-xs text-faint transition hover:text-ink"
          >
            清除
          </button>
        )}
      </div>

      {showList && (
        <div className="absolute z-30 mt-2 max-h-72 w-full min-w-[16rem] overflow-y-auto rounded-xl border border-line bg-surface p-1 shadow-lg">
          {status === "loading" ? (
            <div className="space-y-2 p-3" aria-live="polite">
              <span className="sr-only">載入球員名單中</span>
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
            </div>
          ) : status === "error" ? (
            <div className="p-3 text-center text-xs text-down" role="alert">
              名單載入失敗
              <button
                type="button"
                onClick={() => {
                  setStatus("idle");
                  void loadRoster();
                }}
                className="ml-2 font-semibold text-accent underline"
              >
                重試
              </button>
            </div>
          ) : results.length === 0 ? (
            <div className="p-3 text-center text-xs text-faint" role="status">
              找不到符合的球員
            </div>
          ) : (
            <ul ref={listRef} id={listboxId} role="listbox" aria-label="球員搜尋結果">
              {results.map((p, i) => (
                <li key={p.id} id={`${listboxId}-${i}`} role="option" aria-selected={i === activeIndex} data-active={i === activeIndex}>
                  <button
                    type="button"
                    tabIndex={-1}
                    onMouseEnter={() => setActiveIndex(i)}
                    onClick={() => go(p)}
                    className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink transition ${
                      i === activeIndex ? "bg-surface-2" : ""
                    }`}
                  >
                    <TeamLogo code={null} name={p.team} size={20} decorative />
                    <span className="font-semibold">{p.name}</span>
                    <span className="text-xs text-muted">{p.team}</span>
                    <span className="ml-auto rounded border border-line px-1.5 py-0.5 text-[10px] font-semibold text-faint">
                      {roleLabel(p.roles)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
