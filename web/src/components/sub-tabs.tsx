"use client";

import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

export type SubTabItem<Value extends string> = { value: Value; label: string; content: ReactNode };

/**
 * 卡片內容切換用小頁籤（UX-TEAM-HOTZONE1）：視覺借
 * `hierarchical-tabs.tsx` `ContextSwitcher` 的 pill 軌道＋滑塊語彙
 * （`h-8`、`rounded-full`、`bg-surface-2` 軌道、active＝`bg-surface text-ink
 * shadow-sm`），但**語意不同不能直接複用該元件**：`ContextSwitcher` 是
 * `aria-pressed` 的「同一份內容換範圍」（如全年/上下半季），這裡是「換內容
 * 面板」，故用真正的 tab 語意——`role="tablist"`/`role="tab"`/
 * `aria-selected`/`aria-controls` 指向 `role="tabpanel"`，方向鍵 roving
 * tabindex（沿用 `hierarchical-tabs.tsx` 現有 tablist 的 keydown pattern）。
 *
 * 觸控熱區同樣沿用 `ContextSwitcher` 的手法：視覺高度不變（pill 本身
 * `px-2.5 py-1`），按鈕本體 `min-h-11`（44px）垂直外溢撐開熱區，不放大圖示
 * 本身。**不要改動 `ContextSwitcher` 本身**——球隊頁半季範圍切換在用它。
 *
 * 每個分頁的內容一律掛載在 DOM 中（用 `hidden` 屬性切換顯示），不是
 * 條件式卸載/重新掛載：`aria-controls` 指向的 tabpanel 必須存在，且切換
 * 分頁不該把資料重新渲染一次（雖然這裡的內容本身是靜態 server-rendered
 * ReactNode，代價可忽略，但保持與其他 tablist 實作一致的心智模型）。
 */
export function SubTabs<Value extends string>({ label, items, defaultValue }: {
  label: string;
  items: readonly SubTabItem<Value>[];
  /** 固定順序的預設分類（不要用「筆數最多」——切隊時版面才不會跳，見卡面決策）。 */
  defaultValue: Value;
}) {
  const [value, setValue] = useState<Value>(defaultValue);
  const index = Math.max(0, items.findIndex((item) => item.value === value));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const keyboardMoved = useRef(false);
  const id = useId();
  const tabId = (v: Value) => `${id}-tab-${v}`;
  const panelId = (v: Value) => `${id}-panel-${v}`;

  const onKeyDown = (event: KeyboardEvent) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    keyboardMoved.current = true;
    setValue(items[(index + delta + items.length) % items.length].value);
  };
  useEffect(() => {
    if (keyboardMoved.current) refs.current[index]?.focus({ preventScroll: true });
  }, [index]);

  if (items.length === 0) return null;

  return (
    <div>
      {/* UX-TEAM-HOTZONE1「隊史紀錄」拆兩個小頁籤後，卡面預估的「4 個約 384px
          裝得進 512px 容器」只在桌機成立——375px 手機版卡片內距後可用寬度僅
          ~293px，實測 384px＋間距會讓整條 tablist 溢出頁面（`w-fit` 不受父層
          寬度限制，`scrollWidth` 撐到 429px）。卡面明訂「不要自行縮短需求方
          指定的頁籤名稱」，故不是靠改字，而是沿用本專案既有的同類解法——
          `hierarchical-tabs.tsx` 的父層導覽列面對同一種「多個 pill 頁籤在窄
          寬度放不下」問題，已用 `overflow-x-auto overscroll-x-contain` +
          子項 `shrink-0`（不擠壓、改橫向捲動）解決，此處原樣沿用同一組
          class，不另創新樣式。`max-w-full` 讓 `w-fit` 的「隨內容寬度」行為
          在裝得下時不受影響（3 個分類、桌機 4 個分類皆維持原本的貼合寬度），
          只在裝不下時封頂於父層寬度並改為可橫向捲動。 */}
      <div role="tablist" aria-label={label} onKeyDown={onKeyDown}
        className="mb-2 flex h-8 w-fit max-w-full items-center overflow-x-auto overscroll-x-contain rounded-full bg-surface-2 px-0.5">
        {items.map((item, i) => {
          const active = item.value === value;
          return (
            <button key={item.value} type="button" role="tab" id={tabId(item.value)}
              aria-selected={active} aria-controls={panelId(item.value)}
              tabIndex={active ? 0 : -1}
              ref={(element) => { refs.current[i] = element; }}
              onClick={() => setValue(item.value)}
              className="min-h-11 shrink-0 touch-manipulation whitespace-nowrap px-0.5 text-xs font-medium transition">
              <span className={`inline-flex items-center rounded-full px-2.5 py-1 transition ${active
                ? "bg-surface text-ink shadow-sm"
                : "text-muted hover:text-ink"}`}>
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
      {items.map((item) => (
        <div key={item.value} role="tabpanel" id={panelId(item.value)} aria-labelledby={tabId(item.value)}
          hidden={item.value !== value}>
          {item.content}
        </div>
      ))}
    </div>
  );
}
