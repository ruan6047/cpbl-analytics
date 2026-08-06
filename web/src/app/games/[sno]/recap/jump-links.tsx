"use client";

// recap ⑤跳入點：往逐打席／逐球好球帶的入口。
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
        點記分板的任一局，可直接展開該半局的打席
      </span>
    </div>
  );
}
