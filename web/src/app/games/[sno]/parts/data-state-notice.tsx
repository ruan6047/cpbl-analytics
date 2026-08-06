"use client";

// 資料狀態揭露列（設計稿 §1 區位 D）。
//
// freshness／availability 的**語意不得共用同一空態文案**（UI_UX_SYSTEM §3.3 的 blueprint
// 例外）：暫定、對帳未過、等待官方資料、延賽是四件不同的事，各給各的文字。

import Link from "next/link";
import { Notice } from "@/components/ui";
import { methodologyHref } from "@/lib/methodology-anchors";
import type { RenderState } from "@/lib/game-facts";

const REASON_TEXT: Record<string, string> = {
  phase_not_final: "官方尚未宣告比賽結束",
  missing_ball_strike_flags: "即時來源缺少好壞球旗標",
  score_mismatch: "即時來源的比分與逐打席推導不一致",
  half_inning_out_violation: "逐打席的半局出局數不合規則",
  empty_livelog: "即時來源沒有逐打席資料",
  pa_build_reconciliation_required: "官方資料有修正，打席正在對帳",
};

export function ProvisionalBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-muted">
      當晚即時計算
      <Link href={methodologyHref("winprob-validation")}
        className="underline decoration-line underline-offset-2 hover:text-accent">
        說明
      </Link>
    </span>
  );
}

export function DataStateNotice({ state, reason }: { state: RenderState; reason: string | null }) {
  // live＝賽事進行中，事實流照供逐打席使用，但不進賽後態、也不需要警示
  if (state === "authoritative" || state === "provisional" || state === "live") return null;
  const detail = reason ? REASON_TEXT[reason] : null;
  if (state === "provisional_simple" || state === "reconciling") {
    return (
      <Notice className="mb-4" icon="⚠">
        關鍵打席暫不呈現：{detail ?? "打席資料一致性檢查未通過"}。
        比分與得分過程照常顯示，官方資料入庫後會自動補上。
      </Notice>
    );
  }
  if (state === "stale_live") {
    return (
      <Notice className="mb-4" icon="⏳">
        官方尚未宣告比賽結束，賽後戰報待官方資料到位後顯示；畫面維持賽況檢視。
      </Notice>
    );
  }
  if (state === "pending") {
    return (
      <Notice className="mb-4" icon="⏳">
        等待官方逐打席資料入庫，賽後戰報稍後顯示。
      </Notice>
    );
  }
  return null;
}
