"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Card, Eyebrow, TeamLogo, EmptyState, StatusBadge } from "@/components/ui";
import { PregameCard } from "@/components/pregame-card";
import TodaySlate from "@/components/today-slate";
import { clientGet } from "@/lib/client";
import { methodologyHref } from "@/lib/methodology-anchors";
import {
  dailySummaryQuery,
  resolvePregameFromDaily,
  homePregameNotice,
  liveSourceNotice,
  refreshCopy,
  refreshAgeText,
  shortDate,
  showTodaySlate,
  slateDistanceText,
  todayCardKind,
  todayPollDelayMs,
  gameHref,
  TODAY_COPY,
  type DailySummary,
  type DailyGame,
} from "@/lib/daily-summary";

// 首頁每日入口 hub（UX-GAME-HOME1 → UX-HOME-LIVE-STRIP1）。所有語意由 API 推導，
// 不寫死「昨天／今天」，未完成場次不以 0–0 假裝賽果。
//
// 為什麼這裡是 client island 而不是 server component：主區塊要在使用者不重新整理的
// 情況下自己翻頁（打線公布 → 今日賽事；開打 → 賽中；終場 → 賽後），而那個決定跨越
// 整個 hub——不是某一張卡的局部狀態。島只持有「目前這一份 summary」與「現在幾點」，
// 畫面全部委給無 hook 的展示元件（`today-slate.tsx` 與既有卡片）。
//
// **輪詢打的是首屏那一支端點**（`/api/v1/daily/summary`，查詢字串由同一份 response 的
// scope 推導）。這條不是效能取捨而是正確性：這份 response 同時承載賽況數字、賽前點機率
// 與產生那些機率的 serving 版本；一旦分成兩個來源，就會再次出現「快取的舊機率＋即時的
// 正常狀態」那個競態（ML-OUTCOME-SIMPLE-LEAK2 iteration 3）。

function TeamRow({
  code,
  name,
  score,
  win,
  align = "left",
}: {
  code: string;
  name: string;
  score: number | null;
  win: boolean;
  align?: "left" | "right";
}) {
  const logo = <TeamLogo code={code} name={name} size={20} decorative />;
  return (
    <div className={`flex items-center gap-2 ${align === "right" ? "flex-row-reverse" : ""}`}>
      {logo}
      <span className={`text-sm ${win ? "font-semibold text-ink" : "text-muted"}`}>{name}</span>
      {score != null && (
        <span className={`ml-auto font-mono text-base tabular-nums ${win ? "font-bold text-ink" : "text-muted"} ${align === "right" ? "ml-0 mr-auto" : ""}`}>
          {score}
        </span>
      )}
    </div>
  );
}

// 完賽場次：比分 + 勝方強調 + 進入復盤。未完成場次比分為 null 時只顯示對戰與狀態文字。
function CompletedGame({ g }: { g: DailyGame }) {
  const homeWin = g.completed && (g.home_score ?? 0) > (g.away_score ?? 0);
  const awayWin = g.completed && (g.away_score ?? 0) > (g.home_score ?? 0);
  return (
    <Link
      href={gameHref(g)}
      className="block rounded-lg border border-line bg-surface px-3 py-2.5 transition hover:bg-surface-2"
    >
      <div className="grid grid-cols-1 gap-1">
        <TeamRow code={g.away_team_code} name={g.away_team_name} score={g.away_score} win={awayWin} />
        <TeamRow code={g.home_team_code} name={g.home_team_name} score={g.home_score} win={homeWin} />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[11px] text-faint">
        <span className="truncate">{g.venue ?? "—"}</span>
        <span className="shrink-0 text-accent">賽後復盤 →</span>
      </div>
    </Link>
  );
}

// 下一批賽事：對戰 + 賽前卡（點機率＋1 主訊號），可進入賽事頁。
function NextGame({ g, trainedThrough }: { g: DailyGame; trainedThrough: number | null }) {
  const model = resolvePregameFromDaily(g.pregame, trainedThrough);
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2.5">
      <Link href={gameHref(g)} className="block transition hover:opacity-80">
        <div className="grid grid-cols-1 gap-1">
          <TeamRow code={g.away_team_code} name={g.away_team_name} score={null} win={false} />
          <TeamRow code={g.home_team_code} name={g.home_team_name} score={null} win={false} />
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-faint">
          <span className="truncate">{g.venue ?? "—"}</span>
          <span className="shrink-0 text-accent">賽事詳情 →</span>
        </div>
      </Link>
      <div className="mt-2">
        <PregameCard model={model} homeName={g.home_team_name} />
      </div>
    </div>
  );
}

/** 賽前機率的降級告示。**只收一份 summary**——告示描述的就是本頁顯示的那些機率，
 *  兩者必須來自同一個 response。開一個外部注入的 prop 就等於再開一次「兩個來源、
 *  不同新鮮度」的洞。 */
function PregameNotice({ text }: { text: string }) {
  return (
    <p
      data-testid="pregame-serving-notice"
      className="mb-3 rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted"
    >
      {text}{" "}
      <Link href={methodologyHref("pregame")} className="text-accent hover:underline">
        模型方法
      </Link>
    </p>
  );
}

export default function DailyHub({ summary: initial }: { summary: DailySummary }) {
  const [summary, setSummary] = useState<DailySummary>(initial);
  // 首次渲染刻意不帶時鐘（見 `liveInterrupt` 的 null 分支）；掛載後由 effect 補上，
  // 之後每次輪詢（成功或失敗）都往前推——輪詢打不出去時資料仍必須繼續老化。
  const [nowMs, setNowMs] = useState<number | null>(null);
  const latest = useRef(initial);
  const query = dailySummaryQuery(initial.scope);

  useEffect(() => {
    setSummary(initial);
    latest.current = initial;
  }, [initial]);

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

  const { today, latest_game_day, next_slate, freshness, availability } = summary;
  const trainedThrough = availability.pregame_model.trained_through;
  // serving 沿用上一版時，卡片上的機率其實不是最新回測那個模型算的——必須在賽事卡上方
  // 明講，不能只寫進後端 log 或只在方法頁揭露（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）。
  const notice = homePregameNotice(summary);
  const refresh = refreshCopy(freshness.last_refresh.status);
  const ageText = refreshAgeText(freshness.last_refresh.hours_ago);
  const liveNotice = liveSourceNotice(today);

  // 日界線：今天任一場走到打線公布或更後 → 主區塊整個換成「今日賽事」，舊的兩塊
  // 不再渲染。兩者擇一是「同一場比賽不得同時出現在兩個區塊」的結構性保證，
  // 不是靠逐場去重（今天的場次同時也是 next_slate 的場次）。
  const showToday = showTodaySlate(summary);
  const todayHasPregame = today?.games.some((g) => todayCardKind(g) === "pregame") ?? false;

  return (
    <section className="space-y-4">
      {showToday && today ? (
        /* 1a. 今日賽事（每場卡自己有三態） */
        <Card padding="p-4">
          <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
            <Eyebrow className="text-xs font-bold text-ink">
              {TODAY_COPY.title} · {shortDate(today.game_date)}
            </Eyebrow>
            {/* 觸控目標 ≥44px（藍圖 §8.3）：負外距讓命中區長高但不改變標題列的視覺高度。 */}
            <Link href="/games"
              className="-my-3 inline-flex min-h-11 items-center text-xs text-accent hover:underline">
              完整賽況 →
            </Link>
          </div>
          {notice && todayHasPregame && <PregameNotice text={notice} />}
          <TodaySlate slate={today} trainedThrough={trainedThrough} nowMs={nowMs} />
        </Card>
      ) : (
        /* 1b. 最近比賽日（今天沒有場次、或今天還沒有任何新內容時的主位） */
        <Card padding="p-4">
          <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
            <Eyebrow className="text-xs font-bold text-ink">
              最近比賽日{latest_game_day ? ` · ${shortDate(latest_game_day.game_date)}` : ""}
            </Eyebrow>
            {/* 觸控目標 ≥44px（藍圖 §8.3）：負外距讓命中區長高但不改變標題列的視覺高度。 */}
            <Link href="/games"
              className="-my-3 inline-flex min-h-11 items-center text-xs text-accent hover:underline">
              完整賽況 →
            </Link>
          </div>
          {latest_game_day && latest_game_day.games.length > 0 ? (
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {latest_game_day.games.map((g) => (
                <CompletedGame key={`${g.kind_code}-${g.game_sno}`} g={g} />
              ))}
            </div>
          ) : (
            <EmptyState className="py-5">
              {availability.results.status === "not_started"
                ? "本季尚未有完成的比賽"
                : availability.results.status === "source_missing"
                  ? "查無賽程資料"
                  : "目前沒有可顯示的最近賽果"}
            </EmptyState>
          )}
        </Card>
      )}

      {/* 2. 資料 freshness（維護者 fail-fast 安全網；各 status 文案分立）。
          即時來源訊號併在這一條（藍圖 §8.1 模式）：訪客面已靜默降級，這裡只讓維護者
          fail fast，且只描述觀察到的事實，不診斷 Redis 或 worker。 */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-surface-2 px-3 py-2 text-xs">
        <span className="text-muted">
          資料更新至{" "}
          <span className="font-medium text-ink">{shortDate(freshness.last_completed_game_date)}</span>
        </span>
        <StatusBadge tone={refresh.tone}>{refresh.label}</StatusBadge>
        {ageText && <span className="text-faint">刷新於 {ageText}</span>}
        {liveNotice && <StatusBadge tone="warn">{liveNotice}</StatusBadge>}
      </div>

      {/* 3. 下一批賽事。今日賽事區塊在位時整塊不渲染——今天的場次同時就是 next_slate，
          兩塊並存等於同一場比賽出現兩次。 */}
      {!showToday && (
        <Card padding="p-4">
          <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
            <Eyebrow className="text-xs font-bold text-ink">
              下一批賽事
              {next_slate ? ` · ${shortDate(next_slate.game_date)}` : ""}
            </Eyebrow>
            {next_slate && (
              <span className="text-xs text-muted">{slateDistanceText(next_slate.days_from_as_of)}</span>
            )}
          </div>
          {notice && <PregameNotice text={notice} />}
          {next_slate && next_slate.games.length > 0 ? (
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {next_slate.games.map((g) => (
                <NextGame key={`${g.kind_code}-${g.game_sno}`} g={g} trainedThrough={trainedThrough} />
              ))}
            </div>
          ) : (
            <EmptyState className="py-5">
              {availability.schedule.status === "season_complete"
                ? "本季賽程已全部結束"
                : availability.schedule.status === "source_missing"
                  ? "查無賽程資料"
                  : "目前沒有已排定的下一批賽事"}
            </EmptyState>
          )}
        </Card>
      )}
    </section>
  );
}
