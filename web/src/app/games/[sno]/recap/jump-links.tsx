"use client";

// recap ⑤跳入點：往逐打席／逐球的入口。
//
// 賽後態的導航**統一在記分板**（2026-08-06 需求方人工審）：點逐局格子即就地展開該半局的
// 打席摘要，逐打席與逐球操作區跟著同一個選擇顯示。故本區塊不再自備「切到逐打席頁籤」的
// 按鈕——那正是被指出冗餘的那一步（點了頁籤還是得回記分板選局）；改為把讀者送回記分板。
//
// #79 全打席探索器屬 Wave 3——**本 wave 不放占位**（需求方裁決 Q2：避免死連結）。
// WP 曲線維持在頁面下方既有位置且**預設收合**（裁決 Q4）；recap 區塊內不重複內嵌。

export function JumpLinks({ onPickInning }: { onPickInning: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1 text-sm">
      <button type="button" onClick={onPickInning}
        className="text-accent transition-colors hover:underline">
        回記分板選局 ↑
      </button>
      <span className="text-xs text-faint">
        點記分板的任一局，就地展開該半局的打席與逐球
      </span>
    </div>
  );
}
