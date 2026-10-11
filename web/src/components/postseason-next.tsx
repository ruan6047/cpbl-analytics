import Link from "next/link";
import type { PostseasonJourney } from "@/lib/postseason-journey";

// 首頁戰績右側的季後入口卡（#237）。只吃共用旅程模型：一行系列概況＋一個直達季後總覽的入口。
// 下一場時間、主客、球場、待更新細節、單場與日曆入口都只在季後總覽呈現，首頁不重複 DailyHub。
// 概況不轉述比分（規則勝會被讀成已打的勝場），資料缺漏照實說。

export const POSTSEASON_HUB_HREF = "/standings?seg=3";

export function postseasonCalendarHref(j: PostseasonJourney): string {
  return `/games?month=${(j.next?.date ?? j.slots[0]?.date ?? `${j.year}-10-01`).slice(0, 7)}`;
}

/** DailyHub 左欄沒有場次時的季後指引；公告已無未完成場次時回 null（沿用原文案）。
 *  下一場的日期、對戰與球場只由同頁的季後卡呈現，這裡只取代「全季結束」並導向季後總覽。 */
export function postseasonPointer(j: PostseasonJourney | null): { text: string; href: string } | null {
  if (!j || !j.remaining) return null;
  return { text: "例行賽已結束，季後賽仍在進行", href: POSTSEASON_HUB_HREF };
}

/** 一行系列概況：系列名、是否已分勝負、本站季後賽果場數、是否有場次賽果待更新。 */
function seriesBrief(j: PostseasonJourney): string {
  const s = j.series.E.status === "decided" ? j.series.C : j.series.E;
  return [
    s.name,
    s.status === "decided" ? "系列已分勝負" : null,
    j.recordedGames > 0 ? `本站季後賽果 ${j.recordedGames} 場` : "本站尚無季後賽果紀錄",
    j.slots.some((x) => x.status === "result_pending") ? "部分場次賽果待更新" : null,
  ].filter(Boolean).join("・");
}

export function PostseasonNextCard({ journey }: { journey: PostseasonJourney }) {
  return (
    <section aria-labelledby="ps-next-h" className="rounded-md bg-surface p-4">
      <h2 id="ps-next-h" className="mb-1 text-base font-bold text-ink">季後賽</h2>
      <p className="break-words text-[13px] text-muted">{seriesBrief(journey)}</p>
      <Link
        href={POSTSEASON_HUB_HREF}
        className="mt-2 inline-flex min-h-11 items-center rounded-sm text-sm font-medium text-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        季後賽總覽 →
      </Link>
    </section>
  );
}
