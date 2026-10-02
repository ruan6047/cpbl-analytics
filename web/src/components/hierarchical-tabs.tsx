"use client";

import { Fragment, type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";

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
 * 階層導覽：父層、作用中父層的子頁籤與右側情境 controls **同一列**（正式版既有排列，
 * 需求方 #220 裁定 issuecomment-5945865835）：`A a1 a2 ┊ B ……… controls` → 切到 B 為 `A ┊ B b1 b2 ……… controls`。
 * 父層位置固定、子項緊接作用中父層；整列是 #218 色塊帶，選中子頁籤（卡面色＋粗體＋上緣石油藍）
 * 直接接呼叫端的 `TabPanel`。層級靠字級／字重／位置區分：父層 14px 粗體（作用中＝墨色頁籤），
 * 子頁籤 13px，未作用父層為純文字並以細線分隔。
 * ⛔ 不要再把父層或 controls 拆成帶上方另一列（#220 第三輪曾如此，需求方指為退化）；
 * 窄螢幕（<768）由 `.pm-navrow` 把 controls 移到帶上方另列，帶仍是最後一列以接面板。
 *
 * 父層仍是獨立的狀態控制（aria-pressed），子層才使用 tab 語意。
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
    <div className="pm-navrow">
      <div role="group" aria-label={label}
        className="pm-navrow-main flex items-end gap-0.5 overflow-x-auto overscroll-x-contain rounded-t-md bg-band px-[3px] pt-[3px]">
        {groups.map((group, index) => {
          const active = group.value === activeGroup;
          return (
            <Fragment key={group.value}>
              {index > 0 && <span aria-hidden className="mx-1 mb-3 h-5 w-px shrink-0 bg-line-strong" />}
              <button type="button" aria-pressed={active}
                ref={(element) => { groupRefs.current[index] = element; }}
                onClick={() => onGroupChange(group.value)} onKeyDown={(event) => moveGroup(event, index)}
                className={`min-h-11 shrink-0 touch-manipulation whitespace-nowrap rounded-t-md px-4 text-sm transition-colors ${active
                  ? "bg-ink font-bold text-paper"
                  : "font-semibold text-muted hover:text-ink"}`}>
                {group.label}
              </button>
              {active && group.items.length > 0 && (
                <MainTabs embedded label={`${group.label}內容`} items={group.items} value={activeItem}
                  onChange={onItemChange} />
              )}
            </Fragment>
          );
        })}
      </div>
      {controls && <div className="pm-navrow-ctl">{controls}</div>}
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
export function MainTabs<ItemValue extends string>({ label, items, value, onChange, panelId, embedded = false }: {
  label: string;
  items: readonly { value: ItemValue; label: string }[];
  value: ItemValue;
  onChange: (value: ItemValue) => void;
  /** 有值＝頁面提供一個 `role=tabpanel`（id＝panelId）：各 tab 帶 id／aria-controls，
   *  面板以 `mainTabId(panelId, value)` 回指選中 tab（#218 賽況頁補 tabpanel）。 */
  panelId?: string;
  /** HierarchicalTabs 子層專用：嵌在父層的色塊帶內（不自帶帶底／捲動），字級小父層一級（13px）。 */
  embedded?: boolean;
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
      className={embedded
        ? "flex shrink-0 items-end gap-0.5"
        : "flex w-full min-w-0 items-end gap-0.5 overflow-x-auto overscroll-x-contain rounded-t-md bg-band px-[3px] pt-[3px]"}>
      {items.map((item, itemIndex) => (
        <button key={item.value} type="button" role="tab" aria-selected={value === item.value}
          id={panelId ? mainTabId(panelId, item.value) : undefined}
          aria-controls={panelId}
          tabIndex={value === item.value ? 0 : -1}
          ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item.value)}
          className={`min-h-11 shrink-0 touch-manipulation whitespace-nowrap rounded-t-md ${embedded ? "px-3 text-[13px]" : "px-4 text-sm"} transition-colors ${value === item.value
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
