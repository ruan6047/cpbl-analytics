import type { ReactNode } from "react";
import Link from "next/link";
import { BasesOuts, Card, StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";
import { PregameCard } from "@/components/pregame-card";
import {
  gameHref,
  liveInterrupt,
  officialFactLine,
  phaseTone,
  resolvePregameFromDaily,
  shortDate,
  sortTodayGames,
  todayCardKind,
  todayInningLabel,
  taipeiTime,
  todayStatusText,
  TODAY_COPY,
  type LiveInterrupt,
  type TodayGame,
  type TodayLive,
  type TodaySlate as TodaySlateData,
} from "@/lib/daily-summary";

// 首頁「今日賽事」區塊（UX-HOME-LIVE-STRIP1）。純展示元件，**不含 hook、不抓資料**：
// 輪詢與狀態住在 `daily-hub.tsx` 那一個島，這裡只把一份 slate 畫出來（UI_UX_SYSTEM §10.2）。
//
// 每張卡自己有賽前／賽中／賽後三態，判準與單場頁同一組 phase（`lib/live-game.ts`），
// 不另立一套「有沒有比分」的土法——DB 的 0–0 正是首頁整天失準的來源。三態分工：
//
//   賽前 → 現行 `PregameCard`（點機率＋1 主訊號）。已開打場次的後端 payload 連
//          `pregame` 欄位都沒有，所以畫不出來，不是靠這裡的 if 擋住。
//   賽中 → 雙隊／比分／局況／壘包／出局數／最後更新／進入單場。**不做**「關鍵局面」
//          之類的判斷標示，不顯示逐球、球數、Recent Plays，不引入任何 WP 欄位。
//   賽後 → 比分（勝方強調）＋一行官方事實（MVP／勝投，取自 snapshot `decisions`）＋
//          復盤入口。零模型衍生；今晚結束的場次當晚即可見，不等隔日爬蟲。

function TeamLine({ code, name, score, win, hide }: {
  code: string; name: string; score: number | null; win: boolean; hide: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <TeamLogo code={code} name={name} size={22} decorative />
      <span className={`truncate text-sm ${win ? "font-semibold text-ink" : "text-muted"}`}>{name}</span>
      <span className="ml-auto min-w-6 shrink-0 text-right font-mono text-lg tabular-nums">
        {hide || score == null
          ? <span className="text-faint">—</span>
          : <span className={win ? "font-bold text-ink" : "text-muted"}>{score}</span>}
      </span>
    </div>
  );
}

/** 三態共用的卡殼：狀態列 → 兩隊（＋右側槽）→ 下方槽 → 入口。骨架一致，態切換
 *  （賽前 → 賽中 → 賽後）不產生版面跳動（UI_UX_SYSTEM §3.3 感知效能三態）。 */
function GameCard({ g, status, tone, aside, meta, below, footer, showScore, live }: {
  g: TodayGame;
  status: string | null;
  tone: StatusTone;
  /** 兩隊右側（賽中的局數與壘包）。 */
  aside?: ReactNode;
  /** 狀態列右端（最後更新時刻）。 */
  meta?: ReactNode;
  /** 兩隊下方（賽前卡、賽後官方事實、螢幕閱讀器播報）。 */
  below?: ReactNode;
  footer: string;
  showScore: boolean;
  /** 顯示用的比分來源；二階降級時呼叫端傳 null 以收掉會變的數字。 */
  live: TodayLive | null;
}) {
  const settled = todayCardKind(g) === "final";
  const awayScore = live?.away_score ?? g.away_score;
  const homeScore = live?.home_score ?? g.home_score;
  const homeWin = settled && showScore && (homeScore ?? 0) > (awayScore ?? 0);
  const awayWin = settled && showScore && (awayScore ?? 0) > (homeScore ?? 0);

  return (
    <Card padding="p-3" className="flex flex-col gap-2">
      <div className="flex min-h-6 items-center justify-between gap-2">
        {status
          ? <StatusBadge tone={tone}>{status}</StatusBadge>
          : <span className="text-[11px] text-faint">{shortDate(g.game_date)}</span>}
        {meta}
      </div>
      <div className="flex items-center gap-3">
        <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5">
          <TeamLine code={g.away_team_code} name={g.away_team_name}
            score={awayScore} win={awayWin} hide={!showScore} />
          <TeamLine code={g.home_team_code} name={g.home_team_name}
            score={homeScore} win={homeWin} hide={!showScore} />
        </div>
        {aside}
      </div>
      {below}
      <Link
        href={gameHref(g)}
        className="-mx-1 mt-auto flex min-h-11 items-center justify-between rounded-lg px-1 text-[11px] transition hover:bg-surface-2"
      >
        <span className="truncate text-faint">{g.venue ?? "—"}</span>
        <span className="shrink-0 text-accent">{footer}</span>
      </Link>
    </Card>
  );
}

function LiveCard({ g, live, interrupt }: {
  g: TodayGame; live: TodayLive; interrupt: LiveInterrupt;
}) {
  const status = todayStatusText(live, interrupt);
  const inningText = todayInningLabel(live, "text");

  // 二階降級：收掉**所有會變的數字**（比分／局況／壘包／出局數），只留
  // 「A vs B・比賽進行中・即時資料中斷」＋ 入口。一階仍照顯數字，另加標示。
  if (interrupt === "blackout") {
    return (
      <GameCard g={g} status={status} tone="warn" footer="進入賽況 →" showScore={false} live={null}
        below={
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
  return (
    <GameCard
      g={g}
      status={status}
      tone={interrupt === "degraded" ? "warn" : "live"}
      showScore
      live={live}
      footer="進入賽況 →"
      meta={updated && (
        <time className="shrink-0 text-[11px] text-faint" dateTime={live.fetched_at ?? undefined}>
          最後更新 {updated}
        </time>
      )}
      aside={
        <div className="flex shrink-0 flex-col items-center gap-0.5">
          <span className="text-[11px] font-semibold text-accent">
            {todayInningLabel(live, "glyph") ?? "等待賽況"}
          </span>
          {live.bases && <BasesOuts bases={live.bases} outs={live.outs} size={38} />}
        </div>
      }
      below={
        <p className="sr-only" aria-live="polite" aria-atomic="true">
          {g.away_team_name} {live.away_score ?? 0} 比 {live.home_score ?? 0} {g.home_team_name}
          {inningText ? `，${inningText}` : ""}
          {interrupt === "degraded" ? `，${TODAY_COPY.interrupted}` : ""}
        </p>
      }
    />
  );
}

function FinalCard({ g }: { g: TodayGame }) {
  const fact = officialFactLine(g.live);
  return (
    <GameCard
      g={g}
      status={g.live ? todayStatusText(g.live, "none") : "比賽結束"}
      tone="done"
      showScore
      live={g.live}
      footer="賽後復盤 →"
      below={fact ? <p className="truncate text-[11px] text-muted">{fact}</p> : undefined}
    />
  );
}

/** 單場卡的三態分派。`nowMs` 一律由呼叫端注入（島持有的 tick），元件內不叫
 *  `Date.now()`——同一份 props 必須畫出同一個畫面，SSR 與 client 首次渲染才會一致。 */
export function TodayGameCard({ g, trainedThrough, nowMs }: {
  g: TodayGame; trainedThrough: number | null; nowMs: number | null;
}) {
  const kind = todayCardKind(g);

  if (kind === "live" && g.live) {
    return <LiveCard g={g} live={g.live} interrupt={liveInterrupt(g.live, nowMs)} />;
  }
  if (kind === "final") return <FinalCard g={g} />;
  // 延賽：根本沒開打，沒有比分可顯示。
  if (kind === "postponed" && g.live) {
    return (
      <GameCard g={g} status={todayStatusText(g.live, "none")} tone="warn"
        showScore={false} live={null} footer="賽事詳情 →" />
    );
  }
  // 保留賽：**已開賽後中止，場上是有比分的**（GLOSSARY〈保留賽〉：官方 GameResult=2）。
  // 藏起來比顯示更失真，故照顯中斷時比分；「保留・擇期續賽」那一行負責防止它被讀成
  // 終場，也說明了為什麼這個比分不會再變。
  if (kind === "reserved" && g.live) {
    return (
      <GameCard g={g} status={todayStatusText(g.live, "none")} tone="warn"
        showScore live={g.live} footer="賽事詳情 →"
        below={<p className="text-[11px] text-muted">{TODAY_COPY.reservedNote}</p>} />
    );
  }
  // 賽前態：維持現行 PregameCard。後端只在未開打的一軍場次帶 `pregame`；缺席時
  // resolver 回不支援的單行附註，不會冒出 50% 假數字。
  return (
    <GameCard
      g={g}
      status={g.live ? todayStatusText(g.live, "none") : null}
      tone={g.live ? phaseTone(g.live.phase) : "scheduled"}
      showScore={false}
      live={null}
      footer="賽事詳情 →"
      below={
        <PregameCard model={resolvePregameFromDaily(g.pregame, trainedThrough)}
          homeName={g.home_team_name} />
      }
    />
  );
}

export default function TodaySlate({ slate, trainedThrough, nowMs }: {
  slate: TodaySlateData;
  trainedThrough: number | null;
  nowMs: number | null;
}) {
  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
      {sortTodayGames(slate.games).map((g) => (
        <TodayGameCard key={`${g.kind_code}-${g.game_sno}`} g={g}
          trainedThrough={trainedThrough} nowMs={nowMs} />
      ))}
    </div>
  );
}
