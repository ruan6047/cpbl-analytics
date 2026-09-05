"use client";

// 單場賽況頁的**殼**（UX-GAME-RECAP1 重構）：只負責「取數 + 輪詢 + 三態路由 + 頁籤狀態」。
//
// 三態設計原則＝**恆定骨架 ＋ 主區塊置換**（設計稿 `docs/design/GAME-PAGE-THREE-STATES.md`）：
//   * 賽前：既有先發打線 + 賽前勝率卡（Wave 2 再做對戰卡主區塊）
//   * 賽中：ESPN 板（`GameBoard`）——**不動**，僅逐打席分組換底到打席事實流
//   * 賽後：`<RecapMain>` recap 五塊
//
// 焦點／決勝／賽事資訊的**純計算**已抽到 `game-summary.ts`（原本內嵌在本檔 721 行內）。
//
// 完賽觸發雙層（brief §端到端檢視補充，把 `canShowPostgameConclusions` 形式化）：
//   * 頁面層＝`snapshot.phase === "final"`（當晚即可切賽後態）
//   * 資料層＝後端 `is_completed_game`（證據感知；隔日權威源）
// 兩層皆不成立時**停在賽中態**，嚴禁以時間推斷硬切完賽。

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { detail } from "@/lib/client";
import GameBoard, { type Live } from "@/components/game-board";
import { Card, Notice, Skeleton, ErrorState, EmptyState, PlayerLink, ENTITY_LINK } from "@/components/ui";
import BoxTabs, { type BoxTab } from "./box-tabs";
import { WinProbChart, type WpPoint } from "@/components/win-prob-chart";
import { PregameCard } from "@/components/pregame-card";
import { teamColor, teamShort } from "@/lib/teams";
import { resolvePregameCard, type PregameCardModel } from "@/lib/pregame-card";
import { GameOverview } from "./overview";
import { methodologyHref } from "@/lib/methodology-anchors";
import { StartingLineups } from "@/components/starting-lineups";
import { LiveGameLineups } from "@/components/live-game-lineups";
import { MainTabs } from "@/components/hierarchical-tabs";
import { StickyNavBar } from "@/components/sticky-nav-bar";
import { ProvisionalBadge } from "./parts/data-state-notice";
import { RecapMain } from "./states/recap-main";
import {
  buildDecisions, buildHighlights, buildMilestoneChips, delayNoteOf, num, summaryLine,
} from "./game-summary";
import { isProvisional, isRecapReady, type GameFacts } from "@/lib/game-facts";
import {
  applyLiveSnapshot,
  canShowPostgameConclusions,
  nextPollDelay,
  phaseLabel,
  resolveStatusSnapshot,
  shouldFetchLivePayload,
  type LiveSnapshot,
} from "@/lib/live-game";

type PageTab = "overview" | "pbp" | BoxTab;

export default function GameLivePage() {
  const { sno } = useParams<{ sno: string }>();
  const sp = useSearchParams();
  const kind = sp.get("kind") || "A";
  const year = sp.get("year") ? Number(sp.get("year")) : undefined;
  const [data, setData] = useState<Live | null>(null);
  const [err, setErr] = useState(false);
  const [refreshIssue, setRefreshIssue] = useState<"network" | "source" | null>(null);
  const snapshotRef = useRef<LiveSnapshot | null>(null);
  const [idx, setIdx] = useState(0);
  // 頁面預設「比賽總覽」；逐打席為進階操作視圖
  const [view, setView] = useState<PageTab>("overview");
  const [wp, setWp] = useState<WpPoint[] | null>(null);
  const [pregame, setPregame] = useState<PregameCardModel | null>(null);
  const [milestones, setMilestones] = useState<{ player: string; text: string }[]>([]);
  const [facts, setFacts] = useState<GameFacts | null>(null);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let hasData = false;

    const clearTimer = () => {
      if (timer) clearTimeout(timer);
      timer = null;
    };

    const loadFull = async () => {
      const raw = await detail.gameLive(Number(sno), kind, year);
      if (disposed) return;
      const next = applyLiveSnapshot(raw);
      const dd = next as unknown as Live;
      const nextSnapshot = next.live_snapshot;
      snapshotRef.current = nextSnapshot;
      setRefreshIssue(nextSnapshot?.source_status === "error" ? "source" : null);
      setData((previous) => {
        const previousLength = previous?.livelog.length ?? 0;
        setIdx((current) => previous === null || current >= Math.max(0, previousLength - 1)
          ? Math.max(0, dd.livelog.length - 1)
          : current);
        return dd;
      });
      hasData = true;

      // 未開賽（無逐打席）→ 固定語意的賽前勝率，不再使用可選特徵對戰 API。
      if (!dd.livelog.length && dd.game) {
        const game = dd.game;
        detail.pregame()
          .then((response) => setPregame(resolvePregameCard({
            response,
            game: {
              season: Number(game.year),
              game_sno: Number(game.game_sno),
              kind_code: String(game.kind_code),
            },
          })))
          .catch(() => setPregame(resolvePregameCard({
            response: null,
            fetchFailed: true,
            game: {
              season: Number(game.year),
              game_sno: Number(game.game_sno),
              kind_code: String(game.kind_code),
            },
          })));
      }
    };

    const schedule = () => {
      clearTimer();
      const delay = nextPollDelay(snapshotRef.current, document.visibilityState === "visible");
      if (delay !== null) timer = setTimeout(() => void refresh(false), delay);
    };

    const refresh = async (initial: boolean) => {
      clearTimer();
      if (document.visibilityState !== "visible") return;
      try {
        if (initial) {
          await loadFull();
        } else {
          const status = await detail.gameStatus(Number(sno), kind, year);
          if (disposed) return;
          const previous = snapshotRef.current;
          const resolved = resolveStatusSnapshot(previous, status.live_snapshot);
          setRefreshIssue(resolved.interrupted ? "source" : null);
          if (!resolved.accepted) return;
          snapshotRef.current = resolved.snapshot;
          if (shouldFetchLivePayload(previous, resolved.snapshot)) {
            await loadFull();
            void loadFacts();
          } else {
            setData((current) => current ? ({ ...current, live_snapshot: resolved.snapshot } as Live) : current);
          }
        }
      } catch {
        if (!disposed) {
          if (hasData) setRefreshIssue("network");
          else setErr(true);
        }
      } finally {
        if (!disposed) schedule();
      }
    };

    // 打席事實流：recap 五塊、linescore 展開、逐打席換底三個消費者共用。
    // 失敗不阻塞賽況（三態骨架與 box 都不依賴它）——降級為「無事實流」。
    const loadFacts = async () => {
      try {
        const payload = await detail.gameFacts(Number(sno), kind, year);
        if (!disposed) setFacts(payload);
      } catch {
        if (!disposed) setFacts(null);
      }
    };

    const onVisibilityChange = () => {
      clearTimer();
      if (document.visibilityState === "visible") void refresh(false);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    void refresh(true);
    void loadFacts();

    detail.winprob(Number(sno), kind, year).then((d) => setWp(d.items)).catch(() => setWp([]));
    detail.milestones(Number(sno), kind, year).then((d) => setMilestones(d.items)).catch(() => setMilestones([]));
    return () => {
      disposed = true;
      clearTimer();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [sno, kind, year]);

  if (err) return <ErrorState>載入賽況失敗。</ErrorState>;
  // 載入骨架：對齊記分條(rounded-2xl)＋linescore＋總覽雙卡的量體，避免 CLS
  if (!data) return (
    <div className="mt-2 space-y-4">
      <Skeleton className="h-28 rounded-2xl" />
      <Skeleton className="h-24 rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-40 rounded-xl" /><Skeleton className="h-40 rounded-xl" />
      </div>
    </div>
  );
  if (!data.game) return <EmptyState>查無此場比賽。</EmptyState>;

  const g = data.game;
  const liveSnapshot = (data as Live & { live_snapshot?: LiveSnapshot | null }).live_snapshot ?? null;
  const liveInterrupted = refreshIssue !== null || liveSnapshot?.freshness === "stale";
  const hs = num(g.home_score);
  const aw = num(g.away_score);
  // 頁面層完賽觸發（既有語意，形式化進 spec）；資料層由後端 facts 的 render_state 表達。
  const completed = canShowPostgameConclusions(liveSnapshot, hs + aw, g.game_date);
  // 賽後主區塊只在事實流可用時置換；否則沿用既有總覽（不留白、不硬切）
  const showRecap = completed && isRecapReady(facts);
  // 導航模型（2026-08-06 需求方人工審定案）：
  //   * 逐打席是**獨立頁籤**（賽中／賽後皆然）——逐球等操作資訊不混進賽後戰報總覽。
  //   * 賽後戰報總覽裡的記分板是**純顯示**（不標選中局），但**可點**：一次點擊即跳到逐打席
  //     頁籤並定位該半局（保住「進頁籤還要再點一次」的解法）。
  //   * 逐打席頁籤內部的記分板保留選中標示——那裡它是導航器，標示有功能意義。
  const plainLinescore = completed && view === "overview";

  // 關鍵打席／得分事實鏈／勝率曲線 → 切到逐打席頁籤並捲到該打席（與點記分板同語意）。
  const jumpToPa = (evt: string) => {
    const i = data.livelog.findIndex((e) => String(e.main_event_no) === evt);
    if (i < 0) return;
    setIdx(i);
    setView("pbp");
    requestAnimationFrame(() =>
      document.getElementById("pbp-section")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const highlights = buildHighlights(data, completed);
  const { items: decisionItems, mvp } = buildDecisions(data, completed);
  const milestoneItems = buildMilestoneChips(data, milestones);
  const visibleHighlights = completed ? highlights : [];

  // 賽事資訊（渲染於總覽右卡／recap 兩隊表現行）：天氣/觀眾/時長併一列，裁判獨立一列
  const info: [string, React.ReactNode][] = [];
  const overview = summaryLine(data.detail);
  if (overview) info.push(["概況", overview]);
  if (data.detail) {
    const d = data.detail;
    const umps = [["主審", d.head_umpire], ["一壘", d.first_umpire], ["二壘", d.second_umpire],
      ["三壘", d.third_umpire], ["左審", d.left_umpire], ["右審", d.right_umpire]]
      .filter(([, v]) => v) as [string, string][];
    if (umps.length) {
      info.push([
        "裁判",
        <span key="umps" className="flex flex-wrap gap-x-1.5 gap-y-0.5">
          {umps.map(([l, v], idx2) => (
            <span key={l}>
              {idx2 > 0 && "、"}
              <span className="text-muted">{l}</span>{" "}
              <Link href={`/people/umpire/${encodeURIComponent(v)}`} className={ENTITY_LINK}>
                {v}
              </Link>
            </span>
          ))}
        </span>
      ]);
    }
  }
  // 延賽/保留說明：放進賽事資訊卡（裁判下方）；歷史無總覽場走頁面下方 Notice fallback
  const delayNote = delayNoteOf(g);
  if (delayNote) info.push([String(g.delay_kind), `☔ ${delayNote}`]);

  const boxTab: BoxTab | null = view === "away" || view === "home" || view === "ana" || view === "umpire" ? view : null;
  const pageTabs: { value: PageTab; label: string }[] = [
    { value: "overview", label: completed ? "賽後戰報" : "比賽總覽" },
    { value: "pbp", label: "逐打席" },
  ];
  if (data.batting.length > 0) {
    pageTabs.push(
      { value: "away", label: teamShort(String(g.away_team_code ?? "")) },
      { value: "home", label: teamShort(String(g.home_team_code ?? "")) },
      { value: "ana", label: "分析" },
    );
    if (data.detail?.head_umpire) pageTabs.push({ value: "umpire", label: "主審判決" });
  }

  return (
    <div>
      {liveInterrupted && (
        <Notice className="mt-2" icon="⚠">
          即時更新暫時中斷；畫面保留最後一次成功賽況，恢復連線後會自動續接。
        </Notice>
      )}

      {data.livelog.length > 0 ? (
        <section className="mb-8 mt-2 space-y-4">
          <GameBoard data={data} idx={idx} setIdx={setIdx} view={view === "pbp" ? "pbp" : "overview"} wp={wp ?? undefined} gameSno={sno}
            onNavigate={() => setView("pbp")}
            facts={facts?.plate_appearances ?? null}
            highlightSelection={!plainLinescore}
            tabs={<StickyNavBar label="賽況檢視" flush>
              <div className="flex min-w-0 items-center overflow-x-auto overscroll-x-contain">
                <MainTabs label="賽況檢視" value={view} onChange={setView} items={pageTabs} />
              </div>
            </StickyNavBar>} />
          {view === "overview" && (
            <>
              {isProvisional(facts) && showRecap && (
                <div className="flex justify-end px-1"><ProvisionalBadge /></div>
              )}
              {showRecap ? (
                <RecapMain facts={facts} decisions={decisionItems} mvp={mvp}
                  highlights={visibleHighlights} milestones={milestoneItems} info={info}
                  onJump={jumpToPa} onPlayByPlay={() => setView("pbp")} />
              ) : (
                <GameOverview wp={wp ?? []} log={data.livelog}
                  homeName={String(g.home_team_name)} awayName={String(g.away_team_name)}
                  homeColor={teamColor(String(g.home_team_code ?? ""))}
                  awayColor={teamColor(String(g.away_team_code ?? ""))}
                  onJump={jumpToPa} highlights={visibleHighlights} milestones={milestoneItems} info={info}
                  mvp={completed ? mvp : null} decisions={decisionItems} />
              )}
              {liveSnapshot
                ? <LiveGameLineups snapshot={liveSnapshot} />
                : <StartingLineups game={g} log={data.livelog} pitching={data.pitching} />}
              <WinProbChart items={wp ?? []}
                homeName={String(g.home_team_name)} awayName={String(g.away_team_name)}
                homeColor={teamColor(String(g.home_team_code ?? ""))} onSelect={jumpToPa} />
              {/* WP 曲線誠實註記（UX-WP-DISCLOSURE1）：文案事實基準凍結於卡面，
                  數字出自 GAME-RECAP-WP-VAL1/CAL1 時間外驗證；連結至方法頁對應節。 */}
              {(wp?.length ?? 0) >= 4 && (
                <p className="-mt-2 px-1 text-xs leading-relaxed text-muted">
                  局面勝率：僅依比分・壘位・出局數與歷史主場優勢推算，未含兩隊戰力與先發投手；
                  領先／落後方極端區間有已知 ±4–6 個百分點偏差。
                  <Link href={methodologyHref("winprob-validation")}
                    className="ml-1 whitespace-nowrap underline decoration-line underline-offset-2 hover:text-accent">
                    驗證與已知限制 →
                  </Link>
                </p>
              )}
            </>
          )}
          {boxTab && (
            <BoxTabs data={data} tab={boxTab} onTabChange={setView} showTabs={false} />
          )}
        </section>
      ) : completed ? (
        /* 已完賽但無逐打席（歷史場）：沿用比分標題 */
        <header className="mb-6 mt-2">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">
            {String(g.away_team_name)} <span className="font-mono">{aw}</span>
            <span className="mx-2 text-faint">@</span>
            {String(g.home_team_name)} <span className="font-mono">{hs}</span>
          </h1>
          <p className="mt-1.5 text-sm text-muted">{String(g.game_date ?? "")}　賽事編號 {sno}　{String(g.venue ?? "")}</p>
        </header>
      ) : (
        /* 未開賽：固定語意的賽前勝率 */
        <div className="mb-8 mt-2 space-y-4">
          <header className="mb-6">
            <h1 className="text-2xl font-extrabold tracking-tight text-ink">
              {String(g.away_team_name)} <span className="mx-2 text-faint">@</span>
              {String(g.home_team_name)}
            </h1>
            <p className="mt-1.5 text-sm text-muted">
              {String(g.game_date ?? "")}　賽事編號 {sno}　{String(g.venue ?? "")}　
              {liveSnapshot ? phaseLabel(liveSnapshot.phase) : "尚未開賽"}
            </p>
          </header>
          {liveSnapshot && <LiveGameLineups snapshot={liveSnapshot} />}
          {pregame && <PregameCard model={pregame} homeName={String(g.home_team_name)} />}
        </div>
      )}

      {/* 延賽/保留：有總覽場已併入賽事資訊卡（裁判下方）；歷史無總覽場在此 fallback */}
      {g.delay_kind && delayNote && data.livelog.length === 0 && (
        <Notice className="mb-6" icon="☔">因雨{String(g.delay_kind)}　{delayNote}</Notice>
      )}

      {/* 決勝資訊已併入總覽焦點卡；僅歷史無逐打席場次（無總覽）時在此顯示 */}
      {completed && data.livelog.length === 0 && (decisionItems.length > 0 || mvp) && (
        <Card padding="px-4 py-3" className="mb-6 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
          {decisionItems.map((d) => (
            <span key={d.label}><span className="text-muted">{d.label}</span>{" "}
              <span className="font-medium text-ink">{d.pid ? <PlayerLink pid={d.pid} name={d.value} /> : d.value}</span>
              {d.note ? <span className="ml-1 text-xs text-muted">{d.note}</span> : null}</span>
          ))}
          {data.people[String(g.mvp_id)] && (
            <span><span className="text-muted">MVP</span>{" "}
              <span className="font-medium text-ink"><PlayerLink pid={String(g.mvp_id ?? "")} name={String(data.people[String(g.mvp_id)])} /></span>
              {data.decision_counts?.mvp ? <span className="ml-1 text-xs text-muted">本季第 {data.decision_counts.mvp} 次</span> : null}</span>
          )}
        </Card>
      )}
    </div>
  );
}
