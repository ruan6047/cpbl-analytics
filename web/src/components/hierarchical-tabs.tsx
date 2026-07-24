"use client";

import { type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";
import { NavBarRow } from "@/components/sticky-nav-bar";

export type HierarchicalTabGroup<GroupValue extends string, ItemValue extends string> = {
  value: GroupValue;
  label: string;
  items: readonly { value: ItemValue; label: string }[];
};

type HierarchicalTabsProps<GroupValue extends string, ItemValue extends string> = {
  label: string;
  groups: readonly HierarchicalTabGroup<GroupValue, ItemValue>[];
  activeGroup: GroupValue;
  activeItem: ItemValue;
  onGroupChange: (value: GroupValue) => void;
  onItemChange: (value: ItemValue) => void;
  controls?: ReactNode;
};

/**
 * 將父層與作用中父層的子標籤合併為一條導覽列：
 * `A a1 a2 | B` → 切換後為 `A | B b1 b2`。
 *
 * 父層仍是獨立的狀態控制，子層才使用 tab 語意；視覺合併不會犧牲
 * 輔助科技可辨識的資訊架構。右側 controls 可放情境切換器。
 */
export function HierarchicalTabs<GroupValue extends string, ItemValue extends string>({
  label, groups, activeGroup, activeItem, onGroupChange, onItemChange, controls,
}: HierarchicalTabsProps<GroupValue, ItemValue>) {
  const groupIndex = Math.max(0, groups.findIndex((group) => group.value === activeGroup));
  const groupRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const keyboardMovedGroup = useRef(false);

  const moveGroup = (event: KeyboardEvent, index: number) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    keyboardMovedGroup.current = true;
    const next = (index + delta + groups.length) % groups.length;
    onGroupChange(groups[next].value);
  };

  useEffect(() => {
    if (keyboardMovedGroup.current) groupRefs.current[groupIndex]?.focus({ preventScroll: true });
  }, [groupIndex]);

  return (
    <NavBarRow
      align="end"
      main={<div role="group" aria-label={label}
        className="flex min-w-0 items-center gap-1.5 overflow-x-auto overscroll-x-contain">
        {groups.map((group, index) => {
          const active = group.value === activeGroup;
          return (
            <div key={group.value} className="contents">
              {/* 主頁籤 vs 子頁籤的視覺分層（需求方 2026-07-24 UI 審）：
                  頁籤造型＝上圓角、下方角、下緣貼分隔線（經典分頁感）；
                  active 主頁籤＝實心 ink 全高頁籤，其子頁籤住在**較矮（h-8）的灰色托盤**
                  （階梯式從屬，子頁籤框不與主頁籤同高）；未選取主頁籤＝描邊頁籤。
                  子頁籤按鈕仍為 min-h-11 觸控熱區，向上外溢於托盤外（不可見）。 */}
              <div className="flex shrink-0 items-end">
                <button type="button" aria-pressed={active}
                  ref={(element) => { groupRefs.current[index] = element; }}
                  onClick={() => onGroupChange(group.value)} onKeyDown={(event) => moveGroup(event, index)}
                  className={`min-h-11 shrink-0 touch-manipulation whitespace-nowrap rounded-t-md px-2.5 text-sm font-semibold transition ${active
                    ? "bg-ink text-paper"
                    : "border border-line bg-surface text-muted hover:border-line-strong hover:text-ink"}`}>
                  {group.label}
                </button>
                {active && (
                  <div className="flex h-8 items-end rounded-tr-lg bg-surface-2 px-1">
                    <TabItems label={`${group.label}內容`} items={group.items} value={activeItem}
                      onChange={onItemChange} />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>}
      controls={controls}
    />
  );
}

type ContextSwitcherProps<Value extends string> = {
  label: string;
  values: readonly Value[];
  value: Value;
  render: (value: Value) => string;
  onChange: (value: Value) => void;
};

/** 緊湊型情境切換器（switch 造型：圓形軌道＋滑塊），適合放在階層導覽右側，不與內容 tab 混用語意。 */
export function ContextSwitcher<Value extends string>({
  label, values, value, render, onChange,
}: ContextSwitcherProps<Value>) {
  const index = Math.max(0, values.indexOf(value));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const keyboardMoved = useRef(false);
  const onKeyDown = (event: KeyboardEvent) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    keyboardMoved.current = true;
    onChange(values[(index + delta + values.length) % values.length]);
  };
  useEffect(() => {
    if (keyboardMoved.current) refs.current[index]?.focus({ preventScroll: true });
  }, [index]);

  return (
    <div className="flex items-center gap-1.5">
      <span className="whitespace-nowrap text-[11px] text-muted">{label}</span>
      {/* switch 瘦身：軌道視覺高 32px（h-8）、滑塊為內層 span；按鈕本體維持 min-h-11
          的 44px 觸控熱區（垂直外溢、不可見），不犧牲 a11y。 */}
      <div role="group" aria-label={label} onKeyDown={onKeyDown}
        className="flex h-8 items-center rounded-full bg-surface-2 px-0.5">
        {values.map((item, itemIndex) => (
          <button key={item} type="button" aria-pressed={value === item}
            ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item)}
            className={`min-h-11 touch-manipulation whitespace-nowrap px-0.5 text-xs font-medium transition`}>
            <span className={`inline-flex items-center rounded-full px-2.5 py-1 transition ${value === item
              ? "bg-surface text-ink shadow-sm"
              : "text-muted hover:text-ink"}`}>
              {render(item)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** 單層 tablist（underline 語彙）：階層導覽的子層，亦供單層主分頁頁（standings seg）重用（§4.3 D2）。 */
export function TabItems<ItemValue extends string>({ label, items, value, onChange }: {
  label: string;
  items: readonly { value: ItemValue; label: string }[];
  value: ItemValue;
  onChange: (value: ItemValue) => void;
}) {
  const index = Math.max(0, items.findIndex((item) => item.value === value));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const keyboardMoved = useRef(false);
  const onKeyDown = (event: KeyboardEvent) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    keyboardMoved.current = true;
    onChange(items[(index + delta + items.length) % items.length].value);
  };
  useEffect(() => {
    if (keyboardMoved.current) refs.current[index]?.focus({ preventScroll: true });
  }, [index]);

  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex shrink-0">
      {/* 子頁籤比主頁籤「矮」：文字下沉錨定（items-end＋pb-1）＋字級略小，
          底線貼齊導覽欄分隔線；觸控熱區仍為 min-h-11（44px）。 */}
      {items.map((item, itemIndex) => (
        <button key={item.value} type="button" role="tab" aria-selected={value === item.value}
          tabIndex={value === item.value ? 0 : -1}
          ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item.value)}
          className={`min-h-11 flex touch-manipulation items-end whitespace-nowrap border-b-2 px-2 pb-1 text-xs transition ${value === item.value
            ? "border-ink font-semibold text-ink"
            : "border-transparent text-muted hover:border-line-strong hover:text-ink"}`}>
          {item.label}
        </button>
      ))}
    </div>
  );
}
