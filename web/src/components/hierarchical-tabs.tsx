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
 * 階層導覽（#218 頁籤語言；核可稿 player.html「範圍列 → 頁籤 → tabpanel」）：
 *   第一列＝範圍列（紙色底，不在卡面上）：左＝父層分段切換（#218 二級＝分段，如本季／生涯），右＝情境 controls；
 *   第二列＝作用中父層的子項目＝一級頁籤帶（選中＝卡面色塊＋粗體＋上緣石油藍），
 *   呼叫端以 `TabPanel` 直接接在帶下（帶 → 內容同一張卡面）。
 * 子母因此由兩種不同元件區分（分段 vs 頁籤帶），切換內容的頁籤直接連著它控制的內容。
 * ⛔ 不要把子項目再放回「帶下另一列分段」：那是 #220 第二輪的局部調整，需求方質疑後依核可稿改回。
 *
 * 父層仍是獨立的狀態控制（aria-pressed），子層才使用 tab 語意。
 * 作用中父層沒有子項目時不畫頁籤帶（現有呼叫端皆有子項目）。
 */
export function HierarchicalTabs<GroupValue extends string, ItemValue extends string>({
  label, groups, activeGroup, activeItem, onGroupChange, onItemChange, controls,
}: HierarchicalTabsProps<GroupValue, ItemValue>) {
  const groupIndex = Math.max(0, groups.findIndex((group) => group.value === activeGroup));
  const current = groups[groupIndex];
  const hasItems = !!current && current.items.length > 0;
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
    <div className="min-w-0">
      <div className="pm-scope">
        {/* 父層分段：視覺比情境 controls 大一級（核可稿 .scope .seg：14px）；按鈕本體 min-h-11 觸控熱區，
            視覺高度由內層 span 決定（同 ContextSwitcher 手法）。 */}
        <div role="group" aria-label={label} className="flex h-9 items-center rounded-md bg-band px-0.5">
          {groups.map((group, index) => {
            const active = group.value === activeGroup;
            return (
              <button key={group.value} type="button" aria-pressed={active}
                ref={(element) => { groupRefs.current[index] = element; }}
                onClick={() => onGroupChange(group.value)} onKeyDown={(event) => moveGroup(event, index)}
                className={`min-h-11 touch-manipulation whitespace-nowrap px-0.5 text-sm transition`}>
                <span className={`inline-flex items-center rounded-sm px-4 py-1 transition-colors ${active
                  ? "bg-ink font-bold text-paper"
                  : "text-muted hover:text-ink"}`}>
                  {group.label}
                </span>
              </button>
            );
          })}
        </div>
        {controls && <div className="pm-scope-ctl">{controls}</div>}
      </div>
      {hasItems && (
        <MainTabs label={`${current.label}內容`} items={current.items} value={activeItem} onChange={onItemChange} />
      )}
    </div>
  );
}

/** 頁籤帶下方的同色卡面（#218 components.html「下接同色 tabpanel」）。
 *  `labelledBy`／`label` 其一＝真正的 tabpanel；兩者皆無＝父層只是狀態切換（aria-pressed），
 *  只承接卡面樣式、不宣稱 tabpanel 語意。 */
export function TabPanel({ id, labelledBy, label, className = "", children }: {
  id?: string;
  /** 選中 tab 的 id（MainTabs 用 `mainTabId(panelId, value)`）。 */
  labelledBy?: string;
  /** 子頁籤沒有 id 時改用文字標名。 */
  label?: string;
  className?: string;
  children: ReactNode;
}) {
  const isTabPanel = !!(labelledBy || label);
  return (
    <div role={isTabPanel ? "tabpanel" : undefined} id={id} aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : label} className={`pm-panel ${className}`}>
      {children}
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
      <span className="whitespace-nowrap text-xs text-muted">{label}</span>
      {/* switch 瘦身：軌道視覺高 32px（h-8）、滑塊為內層 span；按鈕本體維持 min-h-11
          的 44px 觸控熱區（垂直外溢、不可見），不犧牲 a11y。 */}
      <div role="group" aria-label={label} onKeyDown={onKeyDown}
        className="flex h-8 items-center rounded-md bg-band px-0.5">
        {values.map((item, itemIndex) => (
          <button key={item} type="button" aria-pressed={value === item}
            ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item)}
            className={`min-h-11 touch-manipulation whitespace-nowrap px-0.5 text-xs font-medium transition`}>
            <span className={`inline-flex items-center rounded-sm px-2.5 py-1 transition-colors ${value === item
              ? "bg-ink font-bold text-paper"
              : "text-muted hover:text-ink"}`}>
              {render(item)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** 單層主頁籤 tablist（UI 審 r8）：無主/次階層的頁（standings seg、records 分區）
    一律採主頁籤造型呈現——#218 一級頁籤：band 色塊帶（佔滿內容寬），選中＝卡面色塊＋粗體＋上緣石油藍，
    下方以 `TabPanel` 接同色內容面板。 */
export function MainTabs<ItemValue extends string>({ label, items, value, onChange, panelId }: {
  label: string;
  items: readonly { value: ItemValue; label: string }[];
  value: ItemValue;
  onChange: (value: ItemValue) => void;
  /** 有值＝頁面提供一個 `role=tabpanel`（id＝panelId）：各 tab 帶 id／aria-controls，
   *  面板以 `mainTabId(panelId, value)` 回指選中 tab（#218 賽況頁補 tabpanel）。 */
  panelId?: string;
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
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown}
      className="flex w-full min-w-0 items-end gap-0.5 overflow-x-auto overscroll-x-contain rounded-t-md bg-band px-[3px] pt-[3px]">
      {items.map((item, itemIndex) => (
        <button key={item.value} type="button" role="tab" aria-selected={value === item.value}
          id={panelId ? mainTabId(panelId, item.value) : undefined}
          aria-controls={panelId}
          tabIndex={value === item.value ? 0 : -1}
          ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item.value)}
          className={`min-h-11 shrink-0 touch-manipulation whitespace-nowrap rounded-t-md px-4 text-sm transition-colors ${value === item.value
            ? "bg-surface font-bold text-ink shadow-[inset_0_3px_0_var(--color-accent)]"
            : "text-muted hover:text-ink"}`}>
          {item.label}
        </button>
      ))}
    </div>
  );
}

/** MainTabs 的 tab id（tabpanel 的 aria-labelledby 用）。值可能含中文，編碼成安全字元。 */
export function mainTabId(panelId: string, value: string): string {
  return `${panelId}-tab-${Array.from(value).map((c) => c.codePointAt(0)!.toString(36)).join("")}`;
}
