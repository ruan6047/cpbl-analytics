"use client";

import { type CSSProperties, type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";

// Radio-pill 單選群（games/matchups 導覽欄；需求方 2026-07-24 指定
// uiverse.io/nhfiz/old-lion-54（MIT，Abu Shafiyya）風格改作）：
// 未選＝radio 圓圈＋文字、選中＝圓圈收合、整項變實色膠囊；
// 改作差異：去掉原作 hover 光暈、色彩全改站內 token（不硬編 hex）。

/** 單一選項的視覺面（dot＋內容）；供 button（RadioPills）與 Link（games 隊伍 chips）共用。 */
export function RadioPillFace({ active, activeClass = "bg-ink text-paper", activeStyle, children }: {
  active: boolean;
  /** 選中時的膠囊配色 class；隊色等 inline 色改用 activeStyle 並傳空字串。 */
  activeClass?: string;
  activeStyle?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <span style={active ? activeStyle : undefined}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all duration-200 ${active
        ? activeClass
        : "text-muted group-hover:text-ink"}`}>
      <span aria-hidden className={`box-border shrink-0 rounded-full border-2 transition-all duration-200 ${active
        ? "-ml-1.5 h-0 w-0 border-transparent opacity-0"
        : "h-3 w-3 border-line-strong"}`} />
      {children}
    </span>
  );
}

/** button 版單選群（matchups 視角）；鍵盤 ←→ 巡覽與 aria-pressed 比照 ContextSwitcher。 */
export function RadioPills<Value extends string>({ label, values, value, render, onChange }: {
  label: string;
  values: readonly Value[];
  value: Value;
  render: (value: Value) => string;
  onChange: (value: Value) => void;
}) {
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
      <div role="group" aria-label={label} onKeyDown={onKeyDown} className="flex items-center gap-1">
        {values.map((item, itemIndex) => (
          <button key={item} type="button" aria-pressed={value === item}
            ref={(element) => { refs.current[itemIndex] = element; }} onClick={() => onChange(item)}
            className="group min-h-11 touch-manipulation whitespace-nowrap transition">
            <RadioPillFace active={value === item}>{render(item)}</RadioPillFace>
          </button>
        ))}
      </div>
    </div>
  );
}
