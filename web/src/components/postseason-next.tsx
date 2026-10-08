import Link from "next/link";
import { StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";
import type { PostseasonJourney, SlotStatus } from "@/lib/postseason-journey";
import {
  POSTSEASON_COPY,
  announcementSourceText,
  journeyAsOfText,
  seriesProgressText,
  slotWhen,
} from "@/lib/postseason-journey";

// 首頁的季後下一場卡（#237）。只吃共用旅程模型，與季後總覽、日曆同一份安排。
// 公告場次沒有官方場號 → 不給單場連結；入口一律指向季後總覽與日曆。

const TONE: Record<SlotStatus, StatusTone> = {
  final: "done", scheduled: "scheduled", announced: "scheduled", result_pending: "warn", not_needed: "done",
};

export const POSTSEASON_HUB_HREF = "/standings?seg=3";

export function postseasonCalendarHref(j: PostseasonJourney): string {
  return `/games?month=${(j.next?.date ?? j.slots[0]?.date ?? `${j.year}-10-01`).slice(0, 7)}`;
}

/** DailyHub 左欄沒有場次時的季後指引；公告已無未完成場次時回 null（沿用原文案）。 */
export function postseasonPointer(j: PostseasonJourney | null): { text: string; href: string } | null {
  if (!j || !j.remaining) return null;
  const n = j.next;
  const series = n ? (n.kind === "E" ? j.announcement.series.E.name : j.announcement.series.C.name) : "季後賽";
  return {
    text: n
      ? `例行賽已結束，季後賽仍在進行：下一場 ${series} ${slotWhen(n)}（${POSTSEASON_COPY.status[n.status]}）`
      : "例行賽已結束，季後賽仍在進行",
    href: POSTSEASON_HUB_HREF,
  };
}

export function PostseasonNextCard({ journey }: { journey: PostseasonJourney }) {
  const n = journey.next;
  const ann = journey.announcement;
  const s = journey.series.E.status === "decided" ? journey.series.C : journey.series.E;
  // 已過開賽時間仍無賽果的其他場次：下一場前進後仍要明說，避免把系列進度讀成最新賽況。
  const pending = journey.slots.filter((x) => x.status === "result_pending" && x !== n);
  return (
    <section aria-labelledby="ps-next-h" className="rounded-md bg-surface p-4">
      <h2 id="ps-next-h" className="mb-2 text-base font-bold text-ink">季後賽・下一場</h2>
      {n ? (
        <div className="space-y-1.5">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-bold">{n.kind === "E" ? ann.series.E.name : ann.series.C.name} G{n.seq}</span>
            <StatusBadge tone={TONE[n.status]}>{POSTSEASON_COPY.status[n.status]}</StatusBadge>
            {n.conditional && <span className="pm-tag">{POSTSEASON_COPY.conditional}</span>}
          </p>
          <p className="text-[15px] font-bold tabular-nums text-ink">{slotWhen(n)}</p>
          <p className="flex flex-wrap items-center gap-1.5 text-sm text-ink">
            {n.awayCode && <TeamLogo code={n.awayCode} name={n.awayLabel} size={18} decorative />}
            <span>{n.awayLabel}（客）</span>
            <span className="text-faint">對</span>
            {n.homeCode && <TeamLogo code={n.homeCode} name={n.homeLabel} size={18} decorative />}
            <span>{n.homeLabel}（主）</span>
          </p>
          <p className="text-[13px] text-muted">{n.venue ?? n.venueNote}</p>
          {n.status === "result_pending" && (
            <p className="text-xs text-down">已過預定開賽時間・本站尚無賽果紀錄</p>
          )}
          {n.changeNote && <p className="text-xs text-down">{n.changeNote}</p>}
        </div>
      ) : (
        <p className="text-sm text-muted">本站紀錄中已無未完成的季後場次。</p>
      )}
      {pending.length > 0 && (
        <p className="mt-3 text-xs text-down">
          {pending[0].kind === "E" ? ann.series.E.name : ann.series.C.name} G{pending[0].seq} {slotWhen(pending[0])}
          {pending.length > 1 ? ` 等 ${pending.length} 場` : ""}：{POSTSEASON_COPY.status.result_pending}（已過預定開賽時間・本站尚無賽果紀錄）
        </p>
      )}
      <p className="mt-3 text-[13px] font-medium text-ink">{s.name}：{seriesProgressText(s)}</p>
      <div className="mt-2 flex flex-wrap gap-x-4">
        {n?.href && (
          <Link href={n.href} className="inline-flex min-h-11 items-center text-sm text-accent hover:underline">單場頁 →</Link>
        )}
        <Link href={POSTSEASON_HUB_HREF} className="inline-flex min-h-11 items-center text-sm text-accent hover:underline">
          系列與晉級條件 →
        </Link>
        <Link href={postseasonCalendarHref(journey)} className="inline-flex min-h-11 items-center text-sm text-accent hover:underline">
          季後賽程日曆 →
        </Link>
      </div>
      <p className="mt-2 text-[11.5px] leading-relaxed text-muted">
        {n && !n.href ? "公告安排，尚無官方場次編號。" : ""}
        {journeyAsOfText(journey)}。公告來源：{announcementSourceText(ann)}。
      </p>
    </section>
  );
}
