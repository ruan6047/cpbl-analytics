"use client";

// 球員頁「分項與對戰」的投打對決區（UX-MATCHUP2）。
// 只整合共用 MatchupExplorer：主角固定為當前球員（無主角選擇器），查詢狀態
// 收在本區 local state（球員頁 URL 只留 ?sec= 導覽，雙棲兩份面板互不干擾）；
// 「在投打對決頁開啟」以 matchupsHref 帶當前查詢回 /matchups 跨球員入口。
// EB 判斷、fail-closed 與空／錯誤狀態全在共用面板內，本檔不得另造。
import Link from "next/link";
import { useState } from "react";
import {
  DEFAULT_CONTROLS,
  matchupsHref,
  type ControlsPatch,
  type MatchupControls,
} from "@/components/matchups/controls";
import MatchupExplorer from "@/components/matchups/explorer";
import type { Role } from "@/components/matchups/api";

export function PlayerMatchupsSection({ id, role, name, isRetired }: {
  id: string;
  role: Role;
  name: string | null;
  /** 退役／教練本季必無對戰列，預設改查生涯（與分項明細一致）。 */
  isRetired: boolean;
}) {
  const [controls, setControls] = useState<MatchupControls>({
    ...DEFAULT_CONTROLS,
    scope: isRetired ? "career" : "season",
  });
  const patch = (p: ControlsPatch) => setControls((c) => ({ ...c, ...p }));

  return (
    <section className="mb-6">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold text-ink">投打對決</h2>
        <span className="text-xs text-muted">
          對特定球隊／{role === "batting" ? "投手" : "打者"}的歷史對戰紀錄——描述性統計，非未來預測。
        </span>
        <Link
          href={matchupsHref(id, role, controls)}
          className="ml-auto text-sm text-accent hover:underline"
        >
          在投打對決頁開啟 →
        </Link>
      </div>
      <MatchupExplorer pid={id} role={role} subjectName={name} controls={controls} onPatch={patch} />
    </section>
  );
}
