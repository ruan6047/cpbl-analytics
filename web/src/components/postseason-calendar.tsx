import Link from "next/link";
import type { ReactNode } from "react";
import { StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";
import { slotGameLabel } from "@/components/postseason-series";
import {
  POSTSEASON_COPY, journeyAsOfText, slotAllUnknown, slotVenueText, type JourneySlot, type PostseasonJourney,
} from "@/lib/postseason-journey";

// 日曆上的季後公告格（#237）：資料庫還沒有正式場次的公告安排。虛線框，與正式場次分開。
// 原則上不給連結；唯一例外是 E 場次經單場狀態身分比對的單場賽況入口（slot.liveEntry），
// 整格連到既有單場頁，狀態徽章仍是資料庫判準（不轉述單場的即時狀態）。
// 「公告安排」由月曆上方的說明一次交代，格內只標例外狀態（賽果待更新、依條件不需進行）與「如有必要」。

const SERIES_LABEL: Record<JourneySlot["kind"], string> = { E: "季後挑戰賽", C: "台灣大賽" };
const SLOT_TONE: Record<JourneySlot["status"], StatusTone> = {
  final: "done", scheduled: "scheduled", announced: "scheduled", result_pending: "warn", not_needed: "done",
};
const open = (s: JourneySlot) => s.status !== "final" && s.status !== "not_needed";
/** 窄格只放得下短字；完整說明見 title 與下方說明區。 */
const shortVenue = (s: JourneySlot) => s.venue ?? (s.venueNote?.startsWith("依挑戰賽") ? "球場依晉級隊" : "球場未取得");

/** `decorative`：旁邊已有隊名文字時不再朗讀（避免報讀器把「挑戰賽勝隊」念兩次）。 */
function SlotTeam({ code, label, size, decorative = false }: { code: string | null; label: string; size: number; decorative?: boolean }) {
  return code ? (
    <TeamLogo code={code} name={label} size={size} decorative={decorative} />
  ) : (
    <span className="inline-flex shrink-0 items-center justify-center rounded-full border border-dashed border-line-strong text-xs text-muted"
      style={{ width: size, height: size }} title={decorative ? undefined : label} aria-hidden={decorative || undefined}>
      <span aria-hidden="true">待</span>{!decorative && <span className="sr-only">{label}</span>}
    </span>
  );
}

/** 有單場賽況入口時整格成為連結（與正式場次格同一種 hover）；沒有時原樣。 */
function EntryLink({ s, children }: { s: JourneySlot; children: ReactNode }) {
  return s.liveEntry && s.href ? (
    <Link href={s.href} className="block transition-colors [&>div]:hover:bg-band">{children}</Link>
  ) : children;
}

/** 月曆上方的季後說明（#237 驗收 3、5）。`announced`＝本月實際畫出的虛線公告格（呼叫端已套月份與隊伍篩選）。
 *  #268 N13：「虛線框…本站尚無正式場次，不提供單場連結」只在本月真的有虛線格時才說。正式場次是實線格、
 *  連到真 (year, kind, sno) 單場頁；舊版不論有沒有虛線格都印這句，台灣大賽 G1–G7 入庫後就與畫面矛盾。 */
export function PostseasonCalendarLegend({ journey, announced }: { journey: PostseasonJourney; announced: JourneySlot[] }) {
  return (
    <p className="mb-3 text-xs leading-relaxed text-muted">
      <b className="font-bold text-ink">季後賽</b>：
      {announced.length > 0 && (
        <>
          虛線框為官方公告安排（本站尚無正式場次，
          {announced.some((s) => s.liveEntry) ? "標「單場賽況」者可點入查看單場賽況，整體賽果待更新" : "不提供單場連結"}）・
        </>
      )}
      點線框為{POSTSEASON_COPY.reserveDay}・「{POSTSEASON_COPY.conditional}」＝{POSTSEASON_COPY.conditionalNote}・{journeyAsOfText(journey)}。
      <Link href="/standings?seg=3" className="ml-1 inline-flex min-h-11 items-center text-accent hover:underline">系列進度與晉級條件 →</Link>
    </p>
  );
}

/** 桌面月曆格。 */
export function AnnouncedCompact({ s }: { s: JourneySlot }) {
  const entry = s.liveEntry && s.href;
  return (
    <EntryLink s={s}>
    <div data-announced="true" title={`${POSTSEASON_COPY.status[s.status]}：${s.awayLabel}（客）對 ${s.homeLabel}（主）・${slotVenueText(s)}${entry ? `・${POSTSEASON_COPY.liveEntryPending}` : ""}`}
      className="block rounded-sm border border-dashed border-line-strong px-1.5 py-1">
      <div className="mb-0.5 text-center text-xs font-bold leading-none text-ink">{SERIES_LABEL[s.kind]} {slotGameLabel(s)}</div>
      <div className="flex items-center justify-between gap-1 leading-none">
        <SlotTeam code={s.awayCode} label={s.awayLabel} size={20} />
        <span className="text-center text-xs leading-tight">
          {s.status !== "announced" && <StatusBadge tone={SLOT_TONE[s.status]} variant="bare">{POSTSEASON_COPY.status[s.status]}</StatusBadge>}
          {s.conditional && open(s) && <span className="block font-bold text-ink">{POSTSEASON_COPY.conditional}</span>}
          {entry && <span className="block text-accent">{POSTSEASON_COPY.liveEntryLink}</span>}
        </span>
        <SlotTeam code={s.homeCode} label={s.homeLabel} size={20} />
      </div>
      <div className="mt-1 truncate text-center text-xs leading-none text-muted">
        {[s.start, shortVenue(s)].filter(Boolean).join("・")}
      </div>
    </div>
    </EntryLink>
  );
}

/** 手機直列：一場一張精簡卡（系列＋場序、開打時刻、主客一行、球場一行）。 */
export function AnnouncedMobile({ s, asOf }: { s: JourneySlot; asOf: string | null }) {
  const unknown = slotAllUnknown(s);
  const entry = s.liveEntry && s.href;
  return (
    <EntryLink s={s}>
    <div data-announced="true" className="rounded-sm border border-dashed border-line-strong px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-bold text-ink">{SERIES_LABEL[s.kind]} {slotGameLabel(s)}</span>
          {s.status !== "announced" && <StatusBadge tone={SLOT_TONE[s.status]}>{POSTSEASON_COPY.status[s.status]}</StatusBadge>}
          {s.conditional && open(s) && <span className="pm-tag !text-ink">{POSTSEASON_COPY.conditional}</span>}
        </span>
        {s.start && <span className="shrink-0 text-sm tabular-nums text-ink">{s.start} 開打</span>}
      </div>
      {unknown ? (
        <p className="mt-1 text-xs text-muted">主客、球場：{POSTSEASON_COPY.unknownVenue}</p>
      ) : (
        <>
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[13px] text-ink">
            <SlotTeam code={s.awayCode} label={s.awayLabel} size={16} decorative />
            <span>{s.awayLabel}（客）</span>
            <span className="text-faint">對</span>
            <SlotTeam code={s.homeCode} label={s.homeLabel} size={16} decorative />
            <span>{s.homeLabel}（主）</span>
          </p>
          <p className="mt-0.5 text-xs text-muted">{slotVenueText(s)}</p>
        </>
      )}
      {s.status === "result_pending" && !entry && (
        <p className="mt-1 text-xs text-down">已過預定開賽時間・本站尚無賽果紀錄{asOf ? `（本站賽果紀錄至 ${asOf.slice(5).replace("-", "/")}）` : ""}</p>
      )}
      {s.status === "result_pending" && entry && <p className="mt-1 text-xs text-down">{POSTSEASON_COPY.liveEntryPending}</p>}
      {s.status === "not_needed" && <p className="mt-1 text-xs text-muted">{POSTSEASON_COPY.notNeededNote}</p>}
      {s.changeNote && <p className="mt-1 text-xs text-down">{s.changeNote}</p>}
      {entry && <p className="mt-1 text-sm text-accent">{POSTSEASON_COPY.liveEntryLink}</p>}
    </div>
    </EntryLink>
  );
}
