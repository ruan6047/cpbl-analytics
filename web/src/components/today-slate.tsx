import type { ReactNode } from "react";
import Link from "next/link";
import { StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";
import { DependencyMark, GameSituation, Postmark, Serial } from "@/components/postmark";
import { PregameCard } from "@/components/pregame-card";
import { isTopHalf } from "@/lib/live-game";
import { teamShort } from "@/lib/teams";
import {
  gameHref,
  latestGameDateNote,
  liveInterrupt,
  phaseTone,
  resolvePregameFromDaily,
  sortTodayGames,
  taipeiTime,
  todayCardKind,
  todayInningLabel,
  todayStatusCopy,
  todayStatusText,
  TODAY_COPY,
  type LiveInterrupt,
  type TodayGame,
  type TodayLive,
} from "@/lib/daily-summary";

// 首頁「今日賽事」票券（UX-HOME-LIVE-STRIP1 → #220 郵戳票券）。純展示元件，**不含 hook、不抓資料**：
// 輪詢與狀態住在 `daily-hub.tsx` 那一個島，這裡只把一場畫出來（UI_UX_SYSTEM §10.2）。
//
// 每張票自己有賽前／賽中／賽後三態，判準與單場頁同一組 phase（`lib/live-game.ts`），
// 不另立一套「有沒有比分」的土法——DB 的 0–0 正是首頁整天失準的來源。三態**同一結構**
// （#218）：票根＝序號列＋狀態章＋郵戳（日期＋球場）；本體＝兩隊（上客下主）＋固定寬右格，
// 比分位置與基線不隨狀態移動。
//
//   賽前 → 右格＝賽前勝率（PregameCard aside 版）。已開打場次的後端 payload 沒有 `pregame`。
//   賽中 → 右格＝局數＋局況（壘包＋出局）。**球數不在 daily summary**（`daily.py` 刻意排除），
//          唯一帶球數的逐場 `/live` 每次約 440–500 KB，不適合首頁輪詢（#220 執行前提確認），
//          故 B／S 兩列不畫、標「球數需資料支援」——不造值。不顯示逐球、Recent Plays、WP。
//   賽後 → 右格＝勝投＋MVP（snapshot `decisions`，官方直接給的）；兩者皆缺寫「官方紀錄確認中」。

const PHASE_ENTRY = { pregame: "賽事詳情 →", live: "進入賽況 →", final: "賽後復盤 →" } as const;

function TeamRow({ code, name, score, hide, tone }: {
  code: string; name: string; score: number | null; hide: boolean;
  /** w＝勝方（只加粗）；l＝敗方（淡）；live＝比分仍會變；plain＝無比分。 */
  tone: "w" | "l" | "live" | "plain";
}) {
  return (
    <div className={`pm-ticket-team ${tone === "plain" ? "" : `pm-${tone}`}`}>
      <TeamLogo code={code} name={name} size={22} decorative />
      <span className="pm-nm">{name}</span>
      <span className="pm-n">{hide || score == null ? "—" : score}</span>
    </div>
  );
}

/** 三態共用的票券殼。骨架一致，態切換（賽前 → 賽中 → 賽後）不產生版面跳動。 */
function Ticket({ g, status, tone, aside, extra, meta, entry, showScore, live, reveal = false }: {
  g: TodayGame;
  status: string | null;
  tone: StatusTone;
  /** 右格（固定寬）：賽前勝率／局況／勝投 MVP／保留附註。 */
  aside?: ReactNode;
  /** 本體下方整列（只放必須讀到的附註，例如螢幕閱讀器播報）。 */
  extra?: ReactNode;
  /** 票根上的小字（賽中「最後更新」）。 */
  meta?: ReactNode;
  entry: string;
  showScore: boolean;
  /** 顯示用的比分來源；二階降級時呼叫端傳 null 以收掉會變的數字。 */
  live: TodayLive | null;
  /** 轉為終場的那一次輪詢：郵戳落章一次。 */
  reveal?: boolean;
}) {
  const kind = todayCardKind(g);
  const settled = kind === "final";
  const awayScore = live?.away_score ?? g.away_score;
  const homeScore = live?.home_score ?? g.home_score;
  const known = showScore && awayScore != null && homeScore != null;
  const homeWin = settled && known && (homeScore as number) > (awayScore as number);
  const awayWin = settled && known && (awayScore as number) > (homeScore as number);
  const toneOf = (win: boolean, lose: boolean): "w" | "l" | "live" | "plain" =>
    !known ? "plain" : win ? "w" : lose ? "l" : kind === "live" ? "live" : "plain";
  const start = taipeiTime(g.live?.starts_at ?? null);
  const dateNote = latestGameDateNote({ completed: false, orig_date: g.orig_date, game_date: g.game_date });

  return (
    <div className="pm-ticket">
      <div className="pm-ticket-stub">
        <Serial items={[{ text: `No.${g.game_sno}`, kind: "lead" }, start ? { text: start, kind: "time" } : null]} />
        {status && <StatusBadge tone={tone}>{status}</StatusBadge>}
        {dateNote && <span className="pm-ticket-note">{dateNote}</span>}
        {meta}
        <Link href={gameHref(g)} className="pm-ticket-link"
          aria-label={`No.${g.game_sno} ${g.away_team_name} 對 ${g.home_team_name}，${entry.replace(" →", "")}`}>
          {entry}
        </Link>
        {/* 日期已由區塊標題（今日／下一批賽事＋日期）說過，替代文字只補每張票的球場。 */}
        <Postmark date={g.game_date} venue={g.venue} size="lg" placed="absolute" reveal={reveal} announce="venue" />
      </div>
      <div className="pm-ticket-body">
        <div className="pm-ticket-teams">
          <TeamRow code={g.away_team_code} name={g.away_team_name} score={awayScore} hide={!showScore}
            tone={toneOf(awayWin, homeWin)} />
          <TeamRow code={g.home_team_code} name={g.home_team_name} score={homeScore} hide={!showScore}
            tone={toneOf(homeWin, awayWin)} />
        </div>
        <div className="pm-ticket-aside">{aside}</div>
        {extra && <div className="pm-ticket-extra">{extra}</div>}
      </div>
    </div>
  );
}

function LiveTicket({ g, live, interrupt }: { g: TodayGame; live: TodayLive; interrupt: LiveInterrupt }) {
  const status = todayStatusText(live, interrupt);
  const inningText = todayInningLabel(live, "text");

  // 二階降級：收掉**所有會變的數字**（比分／局況／壘包／出局數），只留
  // 「A vs B・比賽進行中・即時資料中斷」＋ 入口。一階仍照顯數字，另加標示。
  if (interrupt === "blackout") {
    return (
      <Ticket g={g} status={status} tone="warn" entry={PHASE_ENTRY.live} showScore={false} live={null}
        extra={
          <p className="sr-only" aria-live="polite" aria-atomic="true">
            {g.away_team_name} 對 {g.home_team_name}，{TODAY_COPY.inProgress}，{TODAY_COPY.blackout}
          </p>
        }
      />
    );
  }

  // 「最後更新」**逐場**顯示，不收攏成全域單一值：三場的 `fetched_at` 可以不同，
  // 取最新的會遮蔽落單卡住的那一場，而兩階降級本來就是逐場判斷的。
  // 時刻走釘死台北時區的 `taipeiTime`，SSR 與 hydration 必然一致（不必等掛載）。
  const updated = taipeiTime(live.fetched_at);
  const inning = live.inning == null ? null : `${live.inning} 局${isTopHalf(live.half) ? "上" : "下"}`;
  return (
    <Ticket
      g={g}
      status={status}
      tone={interrupt === "degraded" ? "warn" : "live"}
      showScore
      live={live}
      entry={PHASE_ENTRY.live}
      meta={updated && (
        <time className="text-[11.5px] text-muted" dateTime={live.fetched_at ?? undefined}>
          最後更新 {updated}
        </time>
      )}
      aside={
        <div className="grid justify-items-center gap-1 justify-self-center">
          <span className="text-[15px] font-extrabold leading-none text-ink">{inning ?? "等待賽況"}</span>
          {live.bases && <GameSituation bases={live.bases} outs={live.outs} small />}
          <DependencyMark>球數需資料支援</DependencyMark>
        </div>
      }
      extra={
        <p className="sr-only" aria-live="polite" aria-atomic="true">
          {g.away_team_name} {live.away_score ?? 0} 比 {live.home_score ?? 0} {g.home_team_name}
          {inningText ? `，${inningText}` : ""}
          {interrupt === "degraded" ? `，${TODAY_COPY.interrupted}` : ""}
        </p>
      }
    />
  );
}

function FinalTicket({ g, reveal }: { g: TodayGame; reveal: boolean }) {
  const decisions = g.live?.phase === "final" ? g.live.decisions : null;
  const win = decisions?.winning_pitcher?.name ?? null;
  const mvp = decisions?.mvp?.name ?? null;
  return (
    <Ticket
      g={g}
      status={g.live ? todayStatusText(g.live, "none") : "比賽結束"}
      tone="done"
      showScore
      live={g.live}
      entry={PHASE_ENTRY.final}
      reveal={reveal}
      aside={g.live?.phase === "final" ? (
        win || mvp ? (
          <dl className="grid w-full grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-2 gap-y-0.5">
            {win && <><dt className="text-[11.5px] text-muted">勝投</dt><dd className="m-0 text-right text-[13.5px] font-bold leading-snug [word-break:keep-all]">{win}</dd></>}
            {mvp && <><dt className="text-[11.5px] text-muted">MVP</dt><dd className="m-0 text-right text-[13.5px] font-bold leading-snug [word-break:keep-all]">{mvp}</dd></>}
          </dl>
        ) : <span className="text-xs text-muted">{TODAY_COPY.officialPending}</span>
      ) : undefined}
    />
  );
}

/** 單場票券的三態分派。`nowMs` 一律由呼叫端注入（島持有的 tick），元件內不叫
 *  `Date.now()`——同一份 props 必須畫出同一個畫面，SSR 與 client 首次渲染才會一致。 */
export function TodayGameCard({ g, trainedThrough, nowMs, reveal = false }: {
  g: TodayGame; trainedThrough: number | null; nowMs: number | null;
  /** 這一輪剛轉為終場：郵戳落章一次。 */
  reveal?: boolean;
}) {
  const kind = todayCardKind(g);
  // 狀態章文案與最近比賽日共用同一張表（`todayStatusCopy` → `LATEST_STATUS_COPY`），
  // 不用 `phaseLabel`：canonical 的「延期」在 2026-08-16 Design Gate 被需求方推翻，
  // 官方原文「延賽」勝出，而同一場比賽在首頁兩個區塊不得是兩個詞。
  const statusCopy = todayStatusCopy(g);

  if (kind === "live" && g.live) {
    return <LiveTicket g={g} live={g.live} interrupt={liveInterrupt(g.live, nowMs)} />;
  }
  if (kind === "final") return <FinalTicket g={g} reveal={reveal} />;
  // 延賽：根本沒開打，沒有比分可顯示。**不要求有 live snapshot**：worker 只在開賽時段供
  // snapshot，官方 `delay_kind` 早就在 DB 裡（2026-08-19 A#274 的漏洞，`todayCardKind` 已補 DB 後備）。
  if (kind === "postponed" && statusCopy) {
    return (
      <Ticket g={g} status={statusCopy.label} tone={statusCopy.tone}
        showScore={false} live={null} entry={PHASE_ENTRY.pregame} />
    );
  }
  // 保留賽：**已開賽後中止，場上是有比分的**（GLOSSARY〈保留賽〉：官方 GameResult=2）。
  // 藏起來比顯示更失真，故照顯中斷時比分（不判勝方）；「保留・擇期續賽」負責防止它被讀成終場。
  // 沒有 snapshot 時退回 DB 的 `g.*_score`，兩邊都沒有就照顯破折號——不回填 0。
  if (kind === "reserved" && statusCopy) {
    return (
      <Ticket g={g} status={statusCopy.label} tone={statusCopy.tone}
        showScore live={g.live} entry={PHASE_ENTRY.pregame}
        aside={<span className="text-right text-[12.5px] text-ink">{TODAY_COPY.reservedNote}</span>} />
    );
  }
  // 賽前態：後端只在未開打的一軍場次帶 `pregame`；缺席時 resolver 回不支援的單行附註，
  // 不會冒出 50% 假數字。沒有 snapshot 時不貼狀態章（不宣稱「未開打」，郵戳已承載日期）。
  return (
    <Ticket
      g={g}
      status={g.live ? todayStatusText(g.live, "none") : null}
      tone={g.live ? phaseTone(g.live.phase) : "scheduled"}
      showScore={false}
      live={null}
      entry={PHASE_ENTRY.pregame}
      aside={
        <PregameCard model={resolvePregameFromDaily(g.pregame, trainedThrough)}
          homeName={teamShort(g.home_team_code) || g.home_team_name} variant="aside" />
      }
    />
  );
}

/** 依顯示順序排好的今日場次（開賽時間 → 場次）。 */
export const orderedTodayGames = sortTodayGames;
