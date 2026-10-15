import type { ReactNode } from "react";

import type { ComparisonBarVM } from "@/lib/playoffs-comparison";

/**
 * 兩色比例條（共用呈現元件；#287 D1 自單場頁 `game-board.tsx` 的勝率條抽出）。
 *
 * 只負責呈現：左右兩段寬度、隊色與三格標籤。**語意不住這裡**——
 * 勝率的 [1%, 99%] 夾層與「目前預期勝率（推算）」文案留在單場頁呼叫端（`WpBar`）；
 * 隊伍比較的共享尺度與方向換算在 `lib/playoffs-comparison.ts`（`comparisonBarVM`）。
 * ⚠️ 單場頁回歸（E14）：同一輸入的 DOM 必須與抽離前逐字相同，`split-bar.test.tsx` 以抽離前
 * 擷取的 golden markup 釘住，改動結構前先看那份測試。
 */
export function SplitBar({ leftPct, leftColor, rightColor, left, center, right, children }: {
  /** 左段寬度百分比（0–100）；右段＝100 − 左段。 */
  leftPct: number;
  leftColor: string;
  rightColor: string;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  /** 條下方的補充列（樣本、方向等）；未提供時不輸出任何節點。 */
  children?: ReactNode;
}) {
  return (
    <div className="rounded-md bg-surface px-3 py-2">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold tabular-nums" style={{ color: leftColor }}>{left}</span>
        <span className="text-[11px] text-muted">{center}</span>
        <span className="font-semibold tabular-nums" style={{ color: rightColor }}>{right}</span>
      </div>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        <div style={{ width: `${leftPct}%`, background: leftColor }} />
        <div style={{ width: `${100 - leftPct}%`, background: rightColor }} />
      </div>
      {children}
    </div>
  );
}

/**
 * 隊伍比較條（共享尺度＋方向）：兩隊值同一軸域、同時呈現數值、單位、樣本與方向。
 * 缺值顯示「—」與原因，**不畫成 0 長度**（改成不畫比例條）。
 */
export function ComparisonBar({ vm, leftColor, rightColor }: {
  vm: ComparisonBarVM; leftColor: string; rightColor: string;
}) {
  const sample = (
    <div className="mt-1 flex items-center justify-between text-[11px] text-faint">
      <span className="tabular-nums">{vm.leftSample}</span>
      <span>{vm.direction}</span>
      <span className="tabular-nums">{vm.rightSample}</span>
    </div>
  );
  if (vm.leftPct == null) {
    return (
      <div className="rounded-md bg-surface px-3 py-2" data-comparison-missing={vm.metric}>
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="font-semibold tabular-nums" style={{ color: leftColor }}>{vm.leftText}</span>
          <span className="text-[11px] text-muted">{vm.label}</span>
          <span className="font-semibold tabular-nums" style={{ color: rightColor }}>{vm.rightText}</span>
        </div>
        <p className="text-[11px] text-muted">{vm.missingNote}</p>
        {sample}
      </div>
    );
  }
  return (
    <SplitBar leftPct={vm.leftPct} leftColor={leftColor} rightColor={rightColor}
      left={vm.leftText} center={vm.label} right={vm.rightText}>
      {sample}
    </SplitBar>
  );
}
