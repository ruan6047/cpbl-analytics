// ΔRE24 的**唯一呈現形式**（UI_UX_SYSTEM §10.4 registry 精神：同一概念一個 owner）。
//
// 需求方 2026-08-06 人工審：「逐打席的 RE24 可以跟打席訊息合併嗎，不要分開」——ΔRE24
// 不另立欄位／不獨立成行，而是**併進該打席資訊的同一視覺單元**，做成緊貼結果敘述的
// inline chip。一列＝一個打席的完整資訊（局面＋打者＋結果＋ΔRE24），掃讀時不必左右對照。
//
// 逐打席頁籤、關鍵打席、得分過程三處逐列呈現全部走本元件，形式一致。
//
// 色彩走語意 token（`up` 藍＝對打擊方有利、`down` 紅＝不利），深色模式自動適配；
// 缺值顯示 `—` 而非 0——**沒有值和「沒有影響」是兩件事**。

import { signedDelta } from "@/lib/game-facts";

export function Re24Badge({ value, className = "" }: {
  value: number | null | undefined;
  className?: string;
}) {
  const delta = value ?? null;
  const tone = delta === null ? "text-faint"
    : delta > 0 ? "text-up"
    : delta < 0 ? "text-down"
    : "text-muted";
  return (
    <span
      title="ΔRE24：該打席造成的得分期望值變化（打者觀點，正＝對打擊方有利）"
      className={`ml-1.5 inline-block whitespace-nowrap rounded bg-surface-2 px-1.5 py-px align-middle font-mono text-[11px] font-semibold tabular-nums ${tone} ${className}`}
    >
      ΔRE24 {signedDelta(delta)}
    </span>
  );
}
