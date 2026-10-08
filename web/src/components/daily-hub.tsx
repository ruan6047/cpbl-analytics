"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { EmptyState, StatusBadge, TeamLogo } from "@/components/ui";
import { Scoreline, SectionTitle, Serial } from "@/components/postmark";
import { TodayGameCard, orderedTodayGames } from "@/components/today-slate";
import { clientGet } from "@/lib/client";
import { methodologyHref } from "@/lib/methodology-anchors";
import type { CalendarGame } from "@/lib/api";
import { previousGameDay, type ResultGame } from "@/lib/home-results";
import {
  dailySummaryQuery,
  homePregameNotice,
  liveSourceSignal,
  refreshCopy,
  refreshAtText,
  shortDate,
  slateDistanceText,
  todayCardKind,
  todayPollDelayMs,
  gameHref,
  latestGameStatus,
  latestGameDateNote,
  latestDayPendingCount,
  LATEST_STATUS_COPY,
  TODAY_COPY,
  type DailySummary,
  type TodayGame,
} from "@/lib/daily-summary";

// 首頁每日入口 hub（UX-GAME-HOME1 → UX-HOME-LIVE-STRIP1 → #220 郵戳 7:3）。所有語意由
// API 推導，不寫死「昨天／今天」，未完成場次不以 0–0 假裝賽果。
//
// 版面（#218 核可 7:3）：左＝今天全部場次（含已完賽）的票券；今天沒有賽程時改列下一批賽事。
// 右＝**嚴格早於今天**、最近一個有完賽紀錄的比賽日（`lib/home-results.ts`）。舊版「今日／
// 最近比賽日二擇一」保證的是「同一場不在兩個區塊出現兩次」；新版以日期切開達成同一保證
// （右欄的日期一定早於左欄），所以兩欄可以同時在。
//
// 為什麼這裡是 client island 而不是 server component：票券要在使用者不重新整理的情況下
// 自己翻態（賽前 → 賽中 → 賽後）。島只持有「目前這一份 summary」與「現在幾點」，
// 畫面全部委給無 hook 的展示元件（`today-slate.tsx`）。
//
// **輪詢打的是首屏那一支端點**（`/api/v1/daily/summary`，查詢字串由同一份 response 的
// scope 推導）。這條不是效能取捨而是正確性：這份 response 同時承載賽況數字、賽前點機率
// 與產生那些機率的 serving 版本；一旦分成兩個來源，就會再次出現「快取的舊機率＋即時的
// 正常狀態」那個競態（ML-OUTCOME-SIMPLE-LEAK2 iteration 3）。右欄另讀的 calendar 只在 SSR
// 取一次，只用來回答「今天以前」的事（前一比賽日與其 MVP），不碰任何今天會變的數字。

const WEEKDAY = ["日", "一", "二", "三", "四", "五", "六"];
/** `YYYY-MM-DD` → 「（四）」。純字串／UTC 算術，不碰執行環境時區。 */
function weekday(ymd: string): string {
  const ms = Date.parse(`${ymd}T00:00:00Z`);
  return Number.isFinite(ms) ? `（${WEEKDAY[new Date(ms).getUTCDay()]}）` : "";
}

/** 標題日期：寬體 MM/DD＋小字星期。 */
function TitleDate({ ymd }: { ymd: string }) {
  return <>{shortDate(ymd)}<small>{weekday(ymd)}</small></>;
}

/** 右欄：前一比賽日的單場。有賽果＝比分元件兩層式（每隊印記＋隊名一組、比分在中軸）＋
 *  場次・球場說明＋MVP（calendar 有值才顯示）；沒有賽果＝狀態章＋原定日（不給連結，
 *  見 `LATEST_FOOTER_COPY.pending`），不畫比分、不回填 0。 */
function ResultRow({ g }: { g: ResultGame }) {
  const status = latestGameStatus(g);
  if (status !== "final") {
    const copy = LATEST_STATUS_COPY[status];
    const dateNote = latestGameDateNote(g);
    return (
      <li data-testid="latest-pending-game" data-status={status}
        className="grid content-center gap-1.5 rounded-md bg-surface-2 px-3.5 py-2.5">
        <div className="flex items-center justify-between gap-2 text-[13px]">
          <span className="inline-flex min-w-0 items-center gap-1.5">
            <TeamLogo code={g.away_team_code} name={g.away_team_name} size={18} decorative />
            <span className="truncate">{g.away_team_name}</span>
          </span>
          <span className="text-faint">對</span>
          <span className="inline-flex min-w-0 items-center gap-1.5">
            <span className="truncate">{g.home_team_name}</span>
            <TeamLogo code={g.home_team_code} name={g.home_team_name} size={18} decorative />
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1">
          <StatusBadge tone={copy.tone}>{copy.label}</StatusBadge>
          <Serial items={[{ text: `No.${g.game_sno}` }, g.venue ? { text: g.venue } : null, dateNote ? { text: dateNote } : null]} />
        </div>
      </li>
    );
  }
  const winner = (g.away_score ?? 0) > (g.home_score ?? 0) ? g.away_team_name
    : (g.home_score ?? 0) > (g.away_score ?? 0) ? g.home_team_name : null;
  return (
    <li className="grid">
      <Link href={gameHref(g)}
        aria-label={`No.${g.game_sno}${g.venue ? ` ${g.venue}` : ""}，終場：${g.away_team_name}（客）${g.away_score} 比 ${g.home_score} ${g.home_team_name}（主），${winner ? `${winner}勝` : "和局"}${g.mvp ? `，單場 MVP ${g.mvp}` : ""}。開啟賽後復盤`}
        className="grid content-center gap-1.5 rounded-md bg-surface px-3.5 py-2.5 text-inherit no-underline transition-colors hover:bg-surface-2">
        <Scoreline stack away={{ code: g.away_team_code, name: g.away_team_name, score: g.away_score }}
          home={{ code: g.home_team_code, name: g.home_team_name, score: g.home_score }} />
        <span aria-hidden="true" className="flex flex-wrap justify-center gap-x-3 text-[11.5px] text-muted">
          <span className="font-mono">No.{g.game_sno}{g.venue ? ` · ${g.venue}` : ""}</span>
          {g.mvp && <span><b className="font-bold text-ink">MVP</b> {g.mvp}</span>}
        </span>
      </Link>
    </li>
  );
}

/** 下次向自家 API 拉取的倒數環。
 *
 *  **形狀由事實決定**：輪詢是整批一次請求（一支 dailySummary、三場一起回來），所以倒數
 *  是**全域一個**，不是每張卡一個。它與卡上「最後更新 HH:mm」是兩種語意，不可互相取代：
 *  卡上那個是 worker 抓到官方資料的時刻（逐場不同、逐場降級），這裡是前端下一次拉取。
 *
 *  **它不宣稱資料新不新**。請求失敗時倒數照樣重來——那是「下一次拉取」的計時，不是
 *  「剛剛更新成功」的宣告；失敗看得出來是靠既有的兩階降級（卡片會隨 `fetched_at` 老化
 *  標示更新中斷），不另造一套失敗訊號。
 *
 *  **每秒 tick 關在這個元件裡**：狀態不放在 DailyHub，否則整個 hub（含三張卡）會每秒
 *  重繪一次。父層只給「這一輪何時開始」與「一輪多長」，兩者都只在輪詢發生時才變。 */
function PollCountdown({ cycleMs, startedAt }: { cycleMs: number; startedAt: number }) {
  const [remainingMs, setRemainingMs] = useState(cycleMs);

  useEffect(() => {
    const compute = () =>
      setRemainingMs(Math.max(0, Math.min(cycleMs, cycleMs - (Date.now() - startedAt))));
    compute();
    let timer: ReturnType<typeof setInterval> | null = null;
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };
    const start = () => {
      if (!timer) timer = setInterval(compute, 1000);
    };
    // 背景分頁：**凍住**而不是繼續空轉。回到前景看到一個「早就該更新了卻沒更新」的
    // 倒數是騙人的——那段時間根本沒有排任何請求。刻意不在轉回前景時立刻 compute：
    // 島會立即抓一次並更新 `startedAt`，讓 effect 帶著新的起點重跑。
    const onVisibility = () => (document.visibilityState === "visible" ? start() : stop());
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [cycleMs, startedAt]);

  const seconds = Math.ceil(remainingMs / 1000);
  const radius = 7;
  const circumference = 2 * Math.PI * radius;
  return (
    <span
      tabIndex={0}
      // 靜態說明；**不掛 aria-live**——每秒播報一次倒數是災難。
      title="距離下次更新"
      aria-label="距離下次更新"
      className="group inline-flex items-center gap-1 rounded text-[11px] text-muted"
    >
      <svg width={18} height={18} viewBox="0 0 18 18" aria-hidden="true">
        <circle cx={9} cy={9} r={radius} fill="none" stroke="var(--color-line)" strokeWidth={2} />
        <circle
          cx={9} cy={9} r={radius} fill="none" stroke="var(--color-accent)" strokeWidth={2}
          strokeLinecap="round" transform="rotate(-90 9 9)"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - remainingMs / cycleMs)}
        />
      </svg>
      {/* 數字只在滑過／聚焦時出現：常駐一個每秒跳動的秒數會把注意力從比分上拉走。 */}
      <span className="w-0 overflow-hidden tabular-nums opacity-0 transition-[width,opacity] group-hover:w-7 group-hover:opacity-100 group-focus:w-7 group-focus:opacity-100">
        {seconds} 秒
      </span>
    </span>
  );
}

/** 賽前機率的降級告示。**只收一份 summary**——告示描述的就是本頁顯示的那些機率，
 *  兩者必須來自同一個 response。開一個外部注入的 prop 就等於再開一次「兩個來源、
 *  不同新鮮度」的洞。 */
function PregameNotice({ text }: { text: string }) {
  return (
    <p
      data-testid="pregame-serving-notice"
      className="rounded-md bg-surface-2 px-3 py-2 text-xs text-muted"
    >
      {text}{" "}
      <Link href={methodologyHref("pregame")} className="text-accent hover:underline">
        模型方法
      </Link>
    </p>
  );
}

export default function DailyHub({ summary: initial, calendar, postseason = null }: {
  summary: DailySummary;
  /** SSR 取一次的本季 calendar（A＋季後 E／C）；失敗時為 null，右欄退回 summary 能給的。 */
  calendar: CalendarGame[] | null;
  /** 季後公告仍有未完成場次時的指引（#237，SSR 由共用旅程模型推導）。有值時左欄沒有場次
   *  也不得稱「本季賽程已全部結束」——資料庫還沒有季後列不代表季後賽不打。 */
  postseason?: { text: string; href: string } | null;
}) {
  const [summary, setSummary] = useState<DailySummary>(initial);
  // 首次渲染刻意不帶時鐘（見 `liveInterrupt` 的 null 分支）；掛載後由 effect 補上，
  // 之後每次輪詢（成功或失敗）都往前推——輪詢打不出去時資料仍必須繼續老化。
  const [nowMs, setNowMs] = useState<number | null>(null);
  const latest = useRef(initial);
  const query = dailySummaryQuery(initial.scope);
  // 郵戳落章：只在「這一輪輪詢才轉為終場」的那場落一次；首屏已是終場的不動（不做進場動畫）。
  const kinds = useRef<Map<string, string> | null>(null);
  const [revealed, setRevealed] = useState<ReadonlySet<string>>(() => new Set());

  useEffect(() => {
    setSummary(initial);
    latest.current = initial;
  }, [initial]);

  useEffect(() => {
    const next = new Map((summary.today?.games ?? []).map((g) => [gameKey(g), todayCardKind(g)] as const));
    const prev = kinds.current;
    kinds.current = next;
    if (!prev) return;
    const turned = [...next].filter(([k, kind]) => kind === "final" && prev.has(k) && prev.get(k) !== "final").map(([k]) => k);
    if (turned.length) setRevealed((cur) => new Set([...cur, ...turned]));
  }, [summary]);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const clear = () => {
      if (timer) clearTimeout(timer);
      timer = null;
    };
    const visible = () => document.visibilityState === "visible";
    // 背景分頁**完全停止**（不是降頻）：不排下一次，也不留任何 timer。
    const schedule = () => {
      clear();
      if (disposed || !visible()) return;
      const delay = todayPollDelayMs(latest.current.today);
      if (delay !== null) timer = setTimeout(() => void refresh(), delay);
    };
    const refresh = async () => {
      clear();
      if (disposed || !visible()) return;
      try {
        const next = await clientGet<DailySummary>(`/api/v1/daily/summary${query}`);
        if (disposed) return;
        latest.current = next;
        setSummary(next);
      } catch {
        // 取不到就保留手上這一份，讓它依 `fetched_at` 自然老化到兩階降級；
        // 不清空、不顯示錯誤——訪客要的是「還在打」而不是一個紅色警告。
      } finally {
        if (!disposed) {
          setNowMs(Date.now());
          schedule();
        }
      }
    };
    const onVisibility = () => {
      clear();
      // 重新取得焦點：立即抓一次，不等下一個週期。
      if (visible()) void refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);
    setNowMs(Date.now());
    schedule();
    return () => {
      disposed = true;
      clear();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [query]);

  const { today, next_slate, freshness, availability } = summary;
  const trainedThrough = availability.pregame_model.trained_through;
  // serving 沿用上一版時，卡片上的機率其實不是最新回測那個模型算的——必須在賽事卡上方
  // 明講，不能只寫進後端 log 或只在方法頁揭露（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）。
  const notice = homePregameNotice(summary);
  const refresh = refreshCopy(freshness.last_refresh.status);
  const refreshedAt = refreshAtText(freshness.last_refresh.at, freshness.as_of);
  const liveSource = liveSourceSignal(today);
  // 倒數的週期直接取輪詢實際用的那個值（live 20 秒／未定案無 live 60 秒），不另寫死常數；
  // null＝今天不輪詢，此時**不渲染**倒數環——一個永遠不動的假倒數比沒有更糟。
  const pollCycleMs = todayPollDelayMs(today);

  // 左欄：今天有排賽就列今天全部場次（賽前也列，票券自帶賽前勝率）；今天沒有排賽就列下一批。
  const hasToday = !!today && today.games.length > 0;
  const leftGames: TodayGame[] = hasToday
    ? orderedTodayGames(today!.games)
    : (next_slate?.games ?? []).map((g) => ({ ...g, live: null }));
  const leftHasPregame = leftGames.some((g) => todayCardKind(g) === "pregame");
  // 右欄：嚴格早於今天的最近完賽日（日界取 summary 的台北日期）。
  const prevDay = previousGameDay(summary, calendar);
  const prevGames = prevDay?.games ?? [];
  const pendingCount = latestDayPendingCount(prevGames);
  const rows = Math.max(1, leftGames.length, prevGames.length);

  return (
    <section className="space-y-6">
      <div className="pm-split" style={{ "--n": rows } as React.CSSProperties}>
        <div className="pm-split-hl space-y-2">
          <SectionTitle as="h1"
            date={hasToday ? <TitleDate ymd={today!.game_date} /> : next_slate ? <TitleDate ymd={next_slate.game_date} /> : undefined}
            cue={hasToday
              ? <span className="text-sm font-bold text-ink">{today!.games.length} 場</span>
              : next_slate ? slateDistanceText(next_slate.days_from_as_of) : undefined}
            meta={
              <span className="inline-flex items-center gap-2">
                {pollCycleMs !== null && nowMs !== null && (
                  <PollCountdown cycleMs={pollCycleMs} startedAt={nowMs} />
                )}
                {/* 觸控目標 ≥44px（藍圖 §8.3）：負外距讓命中區長高但不改變標題列的視覺高度。 */}
                <Link href="/games" className="-my-3 inline-flex min-h-11 items-center text-accent no-underline hover:underline">
                  完整賽況 →
                </Link>
              </span>
            }>
            {hasToday ? TODAY_COPY.title : "下一批賽事"}
          </SectionTitle>
          {/* 資料新鮮度（維護者 fail-fast 安全網；各 status 文案分立）＝全頁唯一一個資料時間。
              即時來源訊號併在這一條（藍圖 §8.1）：**恆常渲染**（含「今日無賽程」這個正常態），
              只描述觀察到的事實，不診斷即時管道的成因。 */}
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-muted">
            <span className={`pm-fresh ${refresh.tone === "warn" ? "pm-fresh--stale" : ""}`}>
              資料更新至 <b className="font-bold text-ink">{shortDate(freshness.last_completed_game_date)}</b>
            </span>
            <span className={refresh.tone === "warn" ? "font-bold text-down" : undefined}>{refresh.label}</span>
            {refreshedAt && <span>{refreshedAt}</span>}
            {liveSource.display === "symbol" ? (
              <span role="img" aria-label={liveSource.label} title={liveSource.label} className="font-bold text-accent">
                {liveSource.symbol}
              </span>
            ) : (
              <StatusBadge tone={liveSource.tone}>{liveSource.label}</StatusBadge>
            )}
          </p>
          {notice && leftHasPregame && <PregameNotice text={notice} />}
        </div>

        <section className="pm-split-l" aria-label={hasToday ? "今日場次，每張票上客下主" : "下一批賽事，每張票上客下主"}>
          {leftGames.length > 0 ? (
            <div className="pm-rows">
              {leftGames.map((g) => (
                <TodayGameCard key={gameKey(g)} g={g} trainedThrough={trainedThrough} nowMs={nowMs}
                  reveal={revealed.has(gameKey(g))} />
              ))}
            </div>
          ) : (
            <div className="pm-rows">
              {postseason ? (
                <p data-testid="postseason-pointer" className="rounded-md bg-surface px-4 py-6 text-center text-sm text-ink">
                  {postseason.text}
                  <Link href={postseason.href} className="ml-2 inline-flex min-h-11 items-center text-accent hover:underline">
                    季後賽程與系列 →
                  </Link>
                </p>
              ) : (
                <EmptyState className="rounded-md bg-surface py-6">
                  {availability.schedule.status === "season_complete"
                    ? "本季賽程已全部結束"
                    : availability.schedule.status === "source_missing"
                      ? "查無賽程資料"
                      : "目前沒有已排定的下一批賽事"}
                </EmptyState>
              )}
            </div>
          )}
        </section>

        <div className="pm-split-hr">
          <SectionTitle as="h2" date={prevDay ? <TitleDate ymd={prevDay.game_date} /> : undefined} cue="終場・左客右主">
            賽果
          </SectionTitle>
          {/* 混合日的**區塊層**提示：逐列的狀態章解釋單場，這一句解釋整天。全部完成時不渲染。 */}
          {pendingCount > 0 && prevDay && (
            <p data-testid="latest-pending-note" className="-mt-1 text-[12.5px] text-muted">
              這一天共 {prevGames.length} 場，其中 {pendingCount} 場尚無賽果
            </p>
          )}
        </div>
        <section className="pm-split-r" aria-label={prevDay ? `${shortDate(prevDay.game_date)} 賽果，左客右主` : "最近賽果"}>
          <ol className="pm-rows">
            {prevGames.length > 0 ? prevGames.map((g) => <ResultRow key={gameKey(g)} g={g} />) : (
              <li>
                <EmptyState className="rounded-md bg-surface py-6">
                  {availability.results.status === "not_started"
                    ? "本季尚未有完成的比賽"
                    : availability.results.status === "source_missing"
                      ? "查無賽程資料"
                      : "目前沒有可顯示的最近賽果"}
                </EmptyState>
              </li>
            )}
          </ol>
        </section>
      </div>
    </section>
  );
}

function gameKey(g: { kind_code: string; game_sno: number; season: number }): string {
  return `${g.season}-${g.kind_code}-${g.game_sno}`;
}
