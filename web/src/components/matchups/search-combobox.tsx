"use client";

// 通用球員搜尋 combobox（UX-MATCHUP1）：debounce 後端搜尋、ARIA combobox 鍵盤
// 操作（↑↓ Enter Esc）、選定後以 chip 呈現可清除。主角搜尋與「找特定對手」共用。
import { useEffect, useId, useRef, useState } from "react";
import { TeamLogo } from "@/components/ui";

export type ComboHit = {
  id: string;
  name: string;
  team: string | null;
  hint: string | null; // 次要說明（如「有對戰紀錄・82 PA」）
};

export default function SearchCombobox({
  label,
  placeholder,
  fetcher,
  selected,
  onSelect,
  onClear,
  autoFocus = false,
}: {
  label: string;
  placeholder: string;
  fetcher: (q: string) => Promise<ComboHit[]>;
  selected: { id: string; name: string } | null;
  onSelect: (hit: ComboHit) => void;
  onClear: () => void;
  autoFocus?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ComboHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  // fetch 競態守衛：只採納最後一次輸入的結果
  const seqRef = useRef(0);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setHits([]);
      setStatus("idle");
      return;
    }
    setStatus("loading");
    const seq = ++seqRef.current;
    const t = setTimeout(() => {
      fetcher(q)
        .then((items) => {
          if (seqRef.current !== seq) return;
          setHits(items);
          setActive(0);
          setStatus("ready");
        })
        .catch(() => {
          if (seqRef.current !== seq) return;
          setHits([]);
          setStatus("error");
        });
    }, 250);
    return () => clearTimeout(t);
  }, [query, fetcher]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const pick = (hit: ComboHit) => {
    onSelect(hit);
    setQuery("");
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setOpen(false);
      if (query) setQuery("");
      return;
    }
    if (!open || hits.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(hits[active]);
    }
  };

  if (selected) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface-2 py-1 pl-3 pr-1.5 text-sm">
        <span className="font-semibold text-ink">{selected.name}</span>
        <button
          type="button"
          onClick={() => {
            onClear();
            // 清除後把焦點還給輸入框，鍵盤流程不中斷
            setTimeout(() => inputRef.current?.focus(), 0);
          }}
          aria-label={`清除${label}`}
          className="rounded-md px-1.5 py-0.5 text-muted transition hover:bg-line hover:text-ink"
        >
          ✕
        </button>
      </div>
    );
  }

  const showList = open && query.trim().length > 0;

  return (
    <div ref={rootRef} className="relative min-w-0 flex-1 sm:max-w-64">
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-label={label}
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && hits[active] ? `${listId}-${active}` : undefined}
        aria-autocomplete="list"
        autoFocus={autoFocus}
        value={query}
        placeholder={placeholder}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none placeholder:text-faint focus:border-ink"
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label={`${label}結果`}
          className="absolute left-0 right-0 top-full z-20 mt-1 max-h-72 overflow-auto rounded-lg border border-line bg-surface py-1 shadow-lg"
        >
          {status === "loading" && <li className="px-3 py-2 text-sm text-faint">搜尋中…</li>}
          {status === "error" && <li className="px-3 py-2 text-sm text-accent">搜尋失敗，請重試</li>}
          {status === "ready" && hits.length === 0 && (
            <li className="px-3 py-2 text-sm text-faint">無符合的球員</li>
          )}
          {hits.map((h, i) => (
            <li
              key={h.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              data-active={i === active || undefined}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(h);
              }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-2 text-sm ${
                i === active ? "bg-surface-2 text-ink" : "text-ink"
              }`}
            >
              <TeamLogo name={h.team} size={18} decorative />
              <span className="font-medium">{h.name}</span>
              {h.team && <span className="text-xs text-muted">{h.team}</span>}
              {h.hint && <span className="ml-auto text-[11px] text-faint">{h.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
