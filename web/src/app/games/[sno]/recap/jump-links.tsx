"use client";

// recap ⑤跳入點：往逐打席／逐球的入口。
//
// 逐打席是**獨立頁籤**（2026-08-06 需求方人工審定案：逐球等操作資訊不混進賽後戰報總覽），
// 所以本區塊給的是「切到該頁籤」的入口；另一條等價路徑是直接點總覽記分板的任一局——
// 那會一次點擊就切到逐打席頁籤並定位該半局。
//
// #79 全打席探索器屬 Wave 3——**本 wave 不放占位**（需求方裁決 Q2：避免死連結）。
// WP 曲線維持在頁面下方既有位置且**預設收合**（裁決 Q4）；recap 區塊內不重複內嵌。

export function JumpLinks({ onPlayByPlay }: { onPlayByPlay: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1 text-sm">
      <button type="button" onClick={onPlayByPlay}
        className="text-accent transition-colors hover:underline">
        看逐打席與逐球 →
      </button>
      <span className="text-xs text-faint">
        或直接點上方記分板的任一局，跳到該半局的逐打席
      </span>
    </div>
  );
}
