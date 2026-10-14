import Link from "next/link";
import { PostseasonRefreshHint } from "@/components/postseason-refresh-hint";
import type { PostseasonPointer } from "@/components/daily-hub";
import { nextPreviewLink } from "@/lib/between-games";
import {
  POSTSEASON_COPY,
  slotVenueText,
  slotWhen,
  teamShortName,
  type JourneySlot,
  type PostseasonJourney,
} from "@/lib/postseason-journey";

// 首頁戰績右側的季後入口卡（#237）。只吃共用旅程模型：一行系列概況＋一個直達季後總覽的入口。
// 單場與日曆入口只在季後總覽呈現。概況不轉述比分（規則勝會被讀成已打的勝場），資料缺漏照實說。
//
// #268：首頁「下一批賽事」在資料庫還沒有下一場正式列時（例：挑戰賽打完、台灣大賽 C 列尚未入庫），
// 由 `postseasonPointer` 在左欄直接呈現共用旅程模型的下一場（「台灣大賽 G1」、日期時刻、主客、
// 球場），標「公告安排・正式場次待更新」且不給單場連結——不造場號。正式列入庫後下一批賽事
// 本來就會列出它（daily summary 的 next_slate），票券再以 `postseasonGameLabels` 標系列與場序。

export const POSTSEASON_HUB_HREF = "/standings?seg=3";

/** 下一場只有公告、資料庫尚無正式場次時的狀態文案。 */
export const NEXT_ANNOUNCED_STATUS = "公告安排・正式場次待更新";

export function postseasonCalendarHref(j: PostseasonJourney): string {
  return `/games?month=${(j.next?.date ?? j.slots[0]?.date ?? `${j.year}-10-01`).slice(0, 7)}`;
}

function slotTitle(j: PostseasonJourney, s: Pick<JourneySlot, "kind" | "seq">): string {
  return `${j.series[s.kind].name} G${s.seq}`;
}

/** DailyHub 左欄沒有場次時的季後指引；公告已無未完成場次時回 null（沿用原文案）。
 *  `next` 是共用旅程模型的下一場：與季後總覽、日曆同一份歸併結果，三處才不會互相矛盾。
 *  只有已對到資料庫正式列（`row`）時才給單場連結；公告安排一律沒有連結。 */
export function postseasonPointer(j: PostseasonJourney | null): PostseasonPointer | null {
  if (!j || !j.remaining) return null;
  const s = j.next;
  const next = s && s.status !== "not_needed" ? {
    title: slotTitle(j, s),
    when: slotWhen(s),
    away: s.awayLabel,
    home: s.homeLabel,
    venue: slotVenueText(s),
    status: s.status === "result_pending" ? POSTSEASON_COPY.status.result_pending
      : s.row ? POSTSEASON_COPY.status.scheduled : NEXT_ANNOUNCED_STATUS,
    gameHref: s.row ? s.href : null,
  } : null;
  return { text: "例行賽已結束，季後賽仍在進行", href: POSTSEASON_HUB_HREF, next };
}

/** 正式場次 → 系列標籤（`${year}-${kind}-${sno}` → 「台灣大賽 G1」）。只收已對到資料庫列的
 *  場次；場序取自公告歸併，⛔ 不從場號推場序。 */
export function postseasonGameLabels(j: PostseasonJourney | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const s of j?.slots ?? []) {
    if (s.row) out[`${s.row.year}-${s.row.kind_code}-${s.row.game_sno}`] = slotTitle(j!, s);
  }
  return out;
}

/** 下一場（旅程 next）已有正式列時的觀戰報告入口（`${year}-${kind}-${sno}` → 網址；#273 N03）。
 *  只給下一場：其他場的觀戰報告不成立。網址本身由觀戰報告頁再核對一次，這裡不重複判斷。 */
export function postseasonPreviewLinks(j: PostseasonJourney | null): Record<string, string> {
  const row = j?.next?.row;
  const href = nextPreviewLink(row);
  return row && href ? { [`${row.year}-${row.kind_code}-${row.game_sno}`]: href } : {};
}

/** 首頁賽果卡的季後標籤（#273 N10）：「季後挑戰賽 G4」，分出系列勝負的那一場另說誰晉級／封王。 */
export function postseasonResultLabels(j: PostseasonJourney | null): Record<string, string> {
  const out = postseasonGameLabels(j);
  for (const s of j ? [j.series.E, j.series.C] : []) {
    const last = s.games.at(-1);
    const key = last?.game_sno != null ? `${j!.year}-${s.kind}-${last.game_sno}` : null;
    if (s.status === "decided" && s.tally.winner && key && out[key]) {
      out[key] = `${out[key]}・${teamShortName(s.tally.winner)}${s.kind === "E" ? "晉級台灣大賽" : "奪得總冠軍"}`;
    }
  }
  return out;
}

/** 一行系列概況：挑戰賽已決時先說誰晉級（#268 驗收），再說進行中的系列是什麼狀態。
 *  #273 N11：不再寫「本站季後賽果 N 場」——讀者會把它讀成台灣大賽已有 N 場結果；改說「尚未開打／系列進行中」。
 *  日期時刻刻意不寫（#237：下一場細節只在季後總覽）；已過開賽時間仍無賽果時不說「尚未開打」。 */
function seriesBrief(j: PostseasonJourney): string {
  const eDone = j.series.E.status === "decided";
  const s = eDone ? j.series.C : j.series.E;
  const eWinner = eDone ? j.series.E.tally.winner : null;
  const pending = j.slots.some((x) => x.status === "result_pending");
  return [
    eWinner && s.status !== "decided" ? `挑戰賽已決：${teamShortName(eWinner)}晉級` : null,
    `${s.name}${s.status === "not_started" && !pending ? "尚未開打" : s.status === "in_progress" ? "系列進行中" : ""}`,
    s.status === "decided" ? "系列已分勝負" : null,
    pending ? "部分場次賽果待更新" : null,
  ].filter(Boolean).join("・");
}

export function PostseasonNextCard({ journey }: { journey: PostseasonJourney }) {
  return (
    <section aria-labelledby="ps-next-h" className="rounded-md bg-surface p-4">
      <h2 id="ps-next-h" className="mb-1 text-base font-bold text-ink">季後賽</h2>
      <PostseasonRefreshHint journey={journey} />
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
