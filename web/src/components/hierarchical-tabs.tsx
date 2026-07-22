"use client";

import { type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";

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
    <div className="flex min-w-0 flex-col gap-2 md:flex-row md:items-center md:justify-between">
      <div role="group" aria-label={label}
        className="flex min-w-0 items-center gap-1 overflow-x-auto overscroll-x-contain pb-0.5 md:pb-0">
        {groups.map((group, index) => {
          const active = group.value === activeGroup;
          return (
            <div key={group.value} className="contents">
              {index > 0 && <span aria-hidden className="mx-1 h-6 w-px shrink-0 bg-line" />}
              <div className={`flex shrink-0 items-center gap-1 rounded-xl p-1 ${active
                ? "border border-line-strong bg-surface-2"
                : ""}`}>
                <button type="button" aria-pressed={active}
                  ref={(element) => { groupRefs.current[index] = element; }}
                  onClick={() => onGroupChange(group.value)} onKeyDown={(event) => moveGroup(event, index)}
                  className={`min-h-11 shrink-0 whitespace-nowrap rounded-lg px-3 text-sm font-bold transition ${active
                    ? "bg-ink text-paper shadow-sm"
                    : "border-2 border-line-strong bg-surface text-ink shadow-sm hover:bg-surface-2"}`}>
                  {group.label}
                </button>
                {active && (
                  <>
                    <span aria-hidden className="mx-0.5 h-6 w-px shrink-0 bg-line" />
                    <TabItems label={`${group.label}內容`} items={group.items} value={activeItem}
                      onChange={onItemChange} />
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {controls && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-line/70 pt-2 md:border-l md:border-t-0 md:pl-3 md:pt-0">
          {controls}
        </div>
      )}
    </div>
  );
}

type ContextSwitcherProps<Value extends string> = {
  label: string;
  values: readonly Value[];
  value: Value;
  render: (value: Value) => string;
  onChange: (value: Value) => void;
};

/** 緊湊型情境切換器，適合放在階層導覽右側，不與內容 tab 混用語意。 */
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
      <div role="group" aria-label={label} onKeyDown={onKeyDown}
        className="flex rounded-full bg-surface-2 p-1">
        {values.map((item, itemIndex) => (
          <button key={item} type="button" aria-pressed={value === item}
            ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item)}
            className={`min-h-9 whitespace-nowrap rounded-full px-3 text-xs font-medium transition ${value === item
              ? "bg-paper text-ink shadow-sm ring-1 ring-line"
              : "text-muted hover:text-ink"}`}>
            {render(item)}
          </button>
        ))}
      </div>
    </div>
  );
}

function TabItems<ItemValue extends string>({ label, items, value, onChange }: {
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
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex shrink-0 gap-1">
      {items.map((item, itemIndex) => (
        <button key={item.value} type="button" role="tab" aria-selected={value === item.value}
          tabIndex={value === item.value ? 0 : -1}
          ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item.value)}
          className={`min-h-11 whitespace-nowrap rounded-full px-3 text-sm transition ${value === item.value
            ? "bg-accent font-semibold text-white"
            : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
          {item.label}
        </button>
      ))}
    </div>
  );
}
