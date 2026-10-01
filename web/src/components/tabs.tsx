"use client";

import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

// 頁籤 client island：伺服器端把各分頁內容（server-rendered ReactNode）以 items 傳入，
// 客端只掛載當前分頁。資料已在 props 內、切換不再打 API。
// #218 一級頁籤：色塊帶（選中＝卡面色塊＋粗體＋上緣石油藍），下接同色 tabpanel；左右方向鍵切換。
export function Tabs({ items }: { items: { label: string; content: ReactNode }[] }) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const moved = useRef(false);
  const id = useId();
  const cur = Math.min(active, Math.max(0, items.length - 1));
  useEffect(() => {
    if (moved.current) refs.current[cur]?.focus({ preventScroll: true });
  }, [cur]);
  if (items.length === 0) return null;
  const onKeyDown = (event: KeyboardEvent) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    moved.current = true;
    setActive((cur + delta + items.length) % items.length);
  };
  return (
    <div>
      <div role="tablist" className="pm-tabs" onKeyDown={onKeyDown}>
        {items.map((it, i) => (
          <button
            key={it.label}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role="tab"
            id={`${id}-t${i}`}
            aria-controls={`${id}-p${i}`}
            aria-selected={i === cur}
            tabIndex={i === cur ? 0 : -1}
            onClick={() => setActive(i)}
          >
            {it.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-p${cur}`} aria-labelledby={`${id}-t${cur}`} tabIndex={0} className="pm-panel">
        {items[cur]?.content}
      </div>
    </div>
  );
}
