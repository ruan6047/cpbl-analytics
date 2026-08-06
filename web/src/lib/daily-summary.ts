// 首頁每日入口 view-model（UX-GAME-HOME1；PRODUCT_UX_BLUEPRINT v0.2 §5.1、GAME_RECAP §6.1）。
// 消費 GET /api/v1/daily/summary（API-DAILY-SUMMARY1 契約）：最近比賽日、下一批賽事、
// freshness 與三軸 availability。本模組只做純轉換（型別鏡射 + 退化文案 + PregameCard
// adapter），不抓資料、不含 JSX。
//
// 紅線：
// 1. 不寫死「昨天／今天」——日期一律來自 API 推導（最近有結果的比賽日／下一批未開打）。
// 2. 未完成場次比分為 null，不以 0–0 假裝賽果（API 已清洗，前端亦不得回填 0）。
// 3. v1 不依賴 WPA；賽前卡只顯示點機率＋1 主訊號，區間不進首頁。
// 4. freshness 各 status 文案分立（§8.1），且作為維護者 fail-fast 安全網。

import {
  formatProbability,
  pickPrimarySignal,
  pregameServingNotice,
  PREGAME_COPY,
  type PregameCardModel,
  type PregameItemSignal,
  type PregameServingMeta,
} from "./pregame-card.ts";
import { methodologyHref } from "./methodology-anchors.ts";
import { isTopHalf, phaseLabel, type CanonicalPhase, type LiveDecisions } from "./live-game.ts";
import type { StatusTone } from "@/components/ui";

// —— API 契約鏡射（欄位與後端一致故 snake_case）——

export type DailyGamePregame = {
  status: "available" | "artifact_missing" | "unsupported" | "no_features" | "error";
  home_win_probability: number | null;
  signals: Record<string, PregameItemSignal> | null;
};

export type DailyGame = {
  season: number;
  kind_code: string;
  game_sno: number;
  game_date: string;
  venue: string | null;
  away_team_code: string;
  away_team_name: string;
  away_score: number | null;
  home_team_code: string;
  home_team_name: string;
  home_score: number | null;
  completed: boolean;
  delay_kind: string | null;
  orig_date: string | null;
  /** 只有 next_slate 的場次帶賽前預測；latest_game_day 的場次不帶。 */
  pregame?: DailyGamePregame;
};

export type AxisStatus = { status: string; reason: string | null };

export type RefreshStatus = "fresh" | "stale" | "failed" | "unknown" | "source_error";

export type LastRefresh = {
  at: string | null;
  ok: boolean | null;
  scope: string | null;
  hours_ago: number | null;
  status: RefreshStatus;
  reason: string | null;
};

/** 今日場次疊上的 canonical live snapshot 視圖（後端 `daily.live_view`）。
 *  刻意不含逐球、球數與任何 WP 欄位——本區塊只攤事實。 */
export type TodayLive = {
  phase: CanonicalPhase;
  raw_status: string | null;
  /** 官方預定開賽時間。`cpbl.games` 沒有這一欄，排序第一鍵只能來自 snapshot。 */
  starts_at: string | null;
  inning: number | null;
  half: string | number | null;
  outs: number | null;
  bases: { first: boolean; second: boolean; third: boolean } | null;
  away_score: number | null;
  home_score: number | null;
  event_count: number;
  freshness: "fresh" | "stale" | "final" | null;
  stale_after_seconds: number | null;
  source_status: "ok" | "error" | null;
  fetched_at: string | null;
  /** 後端以伺服器時鐘算的中斷分級；首屏吃這一格（見 `liveInterrupt`）。 */
  interrupt: LiveInterrupt | null;
  decisions: LiveDecisions | null;
};

export type TodayGame = DailyGame & { live: TodayLive | null };

export type LiveSourceStatus = "ok" | "partial" | "unavailable" | "disabled";

export type TodaySlate = {
  game_date: string;
  /** 日界線：當天任一場走到打線公布或更後。主區塊據此擇一渲染。 */
  started: boolean;
  live_source: {
    status: LiveSourceStatus;
    reason: string | null;
    snapshots: number;
    games: number;
  };
  games: TodayGame[];
};

export type DailySummary = {
  scope: { season: number | null; kind_code: string; kinds: string[]; as_of: string };
  /** 今天的排定場次；今天沒有任何場次時為 null（不是空陣列，見驗收條件「零空容器」）。 */
  today: TodaySlate | null;
  latest_game_day: { game_date: string; games: DailyGame[] } | null;
  next_slate: { game_date: string; days_from_as_of: number; games: DailyGame[] } | null;
  freshness: {
    as_of: string;
    last_completed_game_date: string | null;
    last_refresh: LastRefresh;
    unresolved_games: (DailyGame & { status: string })[];
  };
  availability: {
    schedule: AxisStatus;
    results: AxisStatus;
    pregame_model: PregameModelAxis;
  };
};

export {
  pregameServingNotice,
  type PregameDegradation,
  type PregameServingMeta,
} from "./pregame-card.ts";

/** daily summary 的賽前模型軸：serving 契約 ＋ 本聚合特有的欄位。 */
export type PregameModelAxis = AxisStatus & PregameServingMeta & {
  trained_through: number | null;
  signals: Record<string, string> | null;
};

/** 首頁的降級告示。**只收 DailySummary**——簽章本身就是那條不變式：
 *  告示描述的是本頁正在顯示的那些點機率，因此只能由產生那些機率的同一份 response 推導。
 *
 *  iteration 3 的競態就是繞過這一點：首頁顯示 dailySummary（當時快取 120 秒）的舊機率，
 *  卻用另外即時取得的 serving 狀態決定要不要顯示告示。refresh 完成後那一刻，
 *  舊機率配上「一切正常」＝完全沒有提示的舊模型機率。
 *  現在 dailySummary 走 no-store，且此函式無從接收第二個來源。
 */
export function homePregameNotice(summary: DailySummary): string | null {
  return pregameServingNotice(summary.availability.pregame_model);
}

// —— 賽前卡 adapter ——
// daily summary 每場內嵌的 pregame（status + 點機率 + signals）→ PregameCardModel，
// 直接餵 UX-OUTCOME-HOME 的 <PregameCard/>。複用 pregame-card.ts 匯出的 helper，
// 不改動該檔；避免為首頁再打一支 /api/v1/outcome/pregame。

const PREGAME_HREF = methodologyHref("pregame");

function trainedThroughText(trainedThrough: number | null): string | null {
  return trainedThrough != null
    ? `${PREGAME_COPY.trainedThroughPrefix} ${trainedThrough} ${PREGAME_COPY.trainedThroughSuffix}`
    : null;
}

/** 永不 throw、永不造 50%；缺場次 pregame（如二軍或 latest 場次）視為不支援。 */
export function resolvePregameFromDaily(
  pregame: DailyGamePregame | undefined | null,
  trainedThrough: number | null,
): PregameCardModel {
  if (!pregame) {
    return { status: "unsupported", message: PREGAME_COPY.unsupported, methodologyHref: PREGAME_HREF };
  }
  switch (pregame.status) {
    case "available": {
      const p = pregame.home_win_probability;
      if (p == null || !Number.isFinite(p)) {
        return { status: "pending", message: PREGAME_COPY.pending, methodologyHref: PREGAME_HREF };
      }
      return {
        status: "available",
        homeWinProbability: p,
        probabilityText: formatProbability(p),
        primarySignal: pickPrimarySignal(pregame.signals ?? {}),
        trainedThroughText: trainedThroughText(trainedThrough),
        // 首頁一次列多場，告示由 DailyHub 在列表上方顯示一次（homePregameNotice，
        // 同樣出自這份 summary），不在每張卡重複同一句話。
        servingNotice: null,
        methodologyHref: PREGAME_HREF,
      };
    }
    case "artifact_missing":
      return { status: "missing_artifact", message: PREGAME_COPY.missingArtifact, methodologyHref: PREGAME_HREF };
    case "no_features":
      return { status: "pending", message: PREGAME_COPY.pending, methodologyHref: PREGAME_HREF };
    case "unsupported":
      return { status: "unsupported", message: PREGAME_COPY.unsupported, methodologyHref: PREGAME_HREF };
    case "error":
    default:
      return { status: "error", message: PREGAME_COPY.error, methodologyHref: PREGAME_HREF };
  }
}

// —— freshness 文案（各 status 分立；tone 對映 StatusBadge）——

export type FreshnessTone = "done" | "warn" | "scheduled";

export const REFRESH_COPY: Record<RefreshStatus, { label: string; tone: FreshnessTone }> = {
  fresh: { label: "資料為最新", tone: "done" },
  stale: { label: "資料可能落後排程", tone: "warn" },
  failed: { label: "最近一次刷新失敗", tone: "warn" },
  unknown: { label: "尚無刷新紀錄", tone: "scheduled" },
  source_error: { label: "刷新來源異常", tone: "warn" },
};

export function refreshCopy(status: RefreshStatus): { label: string; tone: FreshnessTone } {
  return REFRESH_COPY[status] ?? REFRESH_COPY.unknown;
}

/** hours_ago → 白話相對時間（維護者辨識排程是否落後用）。 */
export function refreshAgeText(hoursAgo: number | null): string | null {
  if (hoursAgo == null) return null;
  if (hoursAgo < 1) return "1 小時內";
  if (hoursAgo < 24) return `${Math.round(hoursAgo)} 小時前`;
  return `${Math.floor(hoursAgo / 24)} 天前`;
}

// —— 一般顯示 helper ——

/** ISO date（YYYY-MM-DD）→ MM/DD；非法輸入原樣回傳。 */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[2]}/${m[3]}` : iso;
}

/** 下一批賽事相對日期文案；不用「今天／明天」寫死，改以資料推導的天數距離表達。 */
export function slateDistanceText(daysFromAsOf: number): string {
  if (daysFromAsOf <= 0) return "即將開打";
  if (daysFromAsOf === 1) return "隔日賽事";
  return `${daysFromAsOf} 天後`;
}

/** 每場 → 賽況／復盤連結（對齊 /games 既有查詢字串）。 */
export function gameHref(g: Pick<DailyGame, "game_sno" | "kind_code" | "season">): string {
  return `/games/${g.game_sno}?kind=${g.kind_code}&year=${g.season}`;
}

// —— 今日賽事三態（UX-HOME-LIVE-STRIP1）——
//
// 首頁在比賽日整天失準的根因是**缺乏 phase 意識**：`cpbl.games` 沒有開賽時間欄、live
// worker 只寫 Redis 不寫 DB，所以 DB 只能回答「這場有沒有比分」。本段把單場頁已經在
// 用的那組判斷搬到首頁，全部是純函式，所有時間相關的判定都吃外部傳入的 `nowMs`
// （不在模組內叫 Date.now()），行為才測得出來。
//
// 紅線：
// 1. 只攤事實——局數／比分／壘包／出局數／官方決勝。不做「關鍵局面」判斷，不引入
//    任何 WP／WPA／leverage（那是另一張卡，本卡不得依賴、不得預告、不留 TODO 掛鉤）。
// 2. 已開打（live／final／DB 已有比分）的場次不得顯示賽前機率。後端已讓 `pregame`
//    欄整個缺席，這裡的 `todayCardKind` 是第二道，不是唯一那道。
// 3. 即時中斷分兩階：一階留數字並標示，二階收掉所有會變的數字。單一門檻＋小字標籤
//    保護不了決策（本專案已有「告警響兩個半月無人讀」的前例）。

/** 進行中場次超過此秒數未更新即進入二階降級：收掉所有會變的數字。
 *  年齡是從 `fetched_at` 算的**總年齡**（Design Gate 第 5 項：45 秒～約 3 分鐘為一階）。 */
export const LIVE_BLACKOUT_AFTER_SECONDS = 180;
/** live snapshot 沒帶門檻時的保底值（後端 `live_game_stale_after_seconds` 現值）。 */
export const LIVE_STALE_FALLBACK_SECONDS = 45;
/** 前景輪詢：有進行中場次 20 秒（worker 12 秒＋前端 20 秒＝最壞約 32 秒，仍在 45 秒門檻內）。 */
export const TODAY_POLL_LIVE_MS = 20_000;
/** 尚未開打但今天還有場次：沿用站上既有的非 live 節奏（`lib/live-game.ts` 的 60 秒）。
 *  這一段存在的理由是日界線本身要能在使用者不重新整理時翻頁——打線公布是首頁把主位
 *  移到今天的觸發條件，不輪詢就永遠等不到它。 */
export const TODAY_POLL_PREGAME_MS = 60_000;

export const TODAY_COPY = {
  title: "今日賽事",
  interrupted: "即時資料更新中斷",
  blackout: "即時資料中斷",
  inProgress: "比賽進行中",
  officialPending: "官方紀錄確認中",
  liveSourceDown: "今日即時賽況來源無資料",
  liveSourcePartial: "部分今日場次無即時賽況",
} as const;

export type TodayCardKind = "pregame" | "live" | "final" | "suspended";

/** 場次卡要渲染哪一態。DB 已有比分（隔日爬蟲補完）與 snapshot `final` 都算賽後。 */
export function todayCardKind(g: TodayGame): TodayCardKind {
  const phase = g.live?.phase;
  if (phase === "final" || g.completed) return "final";
  if (phase === "live") return "live";
  // 延賽／保留：既不是賽前也不是賽中，不掛賽前機率（那場今天不會照原樣打）。
  if (phase === "postponed" || phase === "reserved") return "suspended";
  return "pregame";
}

/** 該場今天還會不會變。全部不會變時輪詢應完全停止。 */
export function todayGameSettled(g: TodayGame): boolean {
  const kind = todayCardKind(g);
  return kind === "final" || kind === "suspended";
}

/** 主區塊要不要換成「今日賽事」。今天沒有場次（`today` 為 null）時一律退回舊雙塊。 */
export function showTodaySlate(summary: DailySummary): boolean {
  return summary.today !== null && summary.today.games.length > 0 && summary.today.started;
}

/** 排序 deterministic：開賽時間 → `game_sno`。開賽時間只在 snapshot 有，缺的排在後面
 *  （缺值不得混進時間序中間，否則同一份資料在 worker 補上 snapshot 前後順序會跳動）。 */
export function sortTodayGames(games: TodayGame[]): TodayGame[] {
  return [...games].sort((a, b) => {
    const sa = a.live?.starts_at ?? "";
    const sb = b.live?.starts_at ?? "";
    if (Boolean(sa) !== Boolean(sb)) return sa ? -1 : 1;
    if (sa !== sb) return sa < sb ? -1 : 1;
    return a.game_sno - b.game_sno;
  });
}

/** snapshot 取得至今的秒數。`fetched_at` 缺席或無法解析回 null。
 *
 *  年齡刻意在**瀏覽器端**算，不吃後端算好的數字：輪詢打不出去（斷網、API 掛）時
 *  頁面上的資料仍必須繼續老化，否則二階降級永遠不會發生——而那正是最需要它的時候。 */
export function liveAgeSeconds(live: TodayLive, nowMs: number): number | null {
  if (!live.fetched_at) return null;
  const at = Date.parse(live.fetched_at);
  if (!Number.isFinite(at)) return null;
  return Math.max(0, (nowMs - at) / 1000);
}

export type LiveInterrupt = "none" | "degraded" | "blackout";

const INTERRUPT_SEVERITY: Record<LiveInterrupt, number> = { none: 0, degraded: 1, blackout: 2 };

/** 即時中斷兩階降級。
 *
 *  - `none`：正常顯示。
 *  - `degraded`（一階）：保留比分／局況／壘包，加上「更新中斷」標示。
 *  - `blackout`（二階）：收掉所有會變的數字，只留對戰、比賽進行中與入口。
 *
 *  兩份判定**取較嚴重者**：後端那一份用伺服器時鐘（首屏唯一能用的來源，`nowMs` 為
 *  null 時就只有它），這一份用瀏覽器時鐘。取 max 是 fail closed——輪詢打不出去時後端
 *  那一格會凍在最後一次成功的值，只有瀏覽器時鐘會繼續走；反過來若瀏覽器時鐘被調慢，
 *  後端那一格仍會把卡收掉。
 *
 *  只對 `live` 場次分兩階：`final` 是不可變快照（不因時間經過變舊），而賽前場次的
 *  後端門檻是 20 分鐘，套 3 分鐘的黑幕會把一張本來就沒有變動數字的卡誤標成中斷。 */
export function liveInterrupt(live: TodayLive, nowMs: number | null): LiveInterrupt {
  if (live.phase === "final") return "none";
  const fromServer: LiveInterrupt = live.interrupt ?? "none";
  if (nowMs === null || live.phase !== "live") return fromServer;

  const age = liveAgeSeconds(live, nowMs);
  // 沒有 `fetched_at` 就無從證明這份數字是新的 → fail closed 收掉數字。
  const fromClient: LiveInterrupt =
    age === null || age > LIVE_BLACKOUT_AFTER_SECONDS ? "blackout"
      : age > (live.stale_after_seconds ?? LIVE_STALE_FALLBACK_SECONDS)
        || live.freshness === "stale" || live.source_status === "error" ? "degraded"
        : "none";
  return INTERRUPT_SEVERITY[fromClient] >= INTERRUPT_SEVERITY[fromServer] ? fromClient : fromServer;
}

/** 瀏覽器輪詢用的查詢字串。**由 SSR 那一份 response 的 scope 推導**，不是各自寫死：
 *  首屏與輪詢因此結構上打同一支端點、同一組參數，不可能變成「兩個來源、不同新鮮度」。 */
export function dailySummaryQuery(scope: DailySummary["scope"]): string {
  const season = scope.season != null ? `&season=${scope.season}` : "";
  return `?kind_code=${encodeURIComponent(scope.kind_code)}${season}`;
}

/** 前景輪詢間隔；null＝完全不輪詢（今天沒比賽、或今天的比賽都不會再變）。 */
export function todayPollDelayMs(today: TodaySlate | null): number | null {
  if (!today || today.games.length === 0) return null;
  if (today.games.some((g) => todayCardKind(g) === "live")) return TODAY_POLL_LIVE_MS;
  if (today.games.every(todayGameSettled)) return null;
  return TODAY_POLL_PREGAME_MS;
}

/** 局數文案。上／下半局的判準沿用 `lib/live-game.ts` 的 `isTopHalf`，不另立一套。
 *  `inning` 為 null＝還沒真的打過（worker 對未開打場次回 1 佔位），回 null。 */
export function todayInningLabel(live: TodayLive, style: "glyph" | "text"): string | null {
  if (live.inning == null) return null;
  const top = isTopHalf(live.half);
  return style === "glyph"
    ? `${top ? "▲" : "▼"} ${live.inning} 局`
    : `${top ? "上" : "下"}${live.inning}局`;
}

/** 場次狀態徽章色調。`StatusBadge` 是全站唯一場次狀態語彙（UI_UX_SYSTEM §3.2）。 */
export function phaseTone(phase: CanonicalPhase): StatusTone {
  if (phase === "live") return "live";
  if (phase === "final") return "done";
  if (phase === "postponed" || phase === "reserved" || phase === "unknown") return "warn";
  return "scheduled";
}

/** 賽後卡的一行官方事實：**只吃 snapshot `decisions`**（官方直接給的），零模型衍生。
 *  兩者皆缺時回「官方紀錄確認中」——不留空、不猜（單場頁三態規格 §5.2 同一立場）。 */
export function officialFactLine(live: TodayLive | null): string | null {
  if (!live || live.phase !== "final") return null;
  const parts: string[] = [];
  const mvp = live.decisions?.mvp;
  const win = live.decisions?.winning_pitcher;
  if (mvp?.name) parts.push(`單場 MVP ${mvp.name}`);
  if (win?.name) parts.push(`勝投 ${win.name}`);
  return parts.length > 0 ? parts.join("・") : TODAY_COPY.officialPending;
}

/** 卡片上的狀態文字（含中斷標示）。phase 文案沿用 `lib/live-game.ts` 的 `phaseLabel`。 */
export function todayStatusText(live: TodayLive | null, interrupt: LiveInterrupt): string | null {
  if (!live) return null;
  const base = phaseLabel(live.phase);
  if (interrupt === "blackout") return `${base}・${TODAY_COPY.blackout}`;
  if (interrupt === "degraded") return `${base}・${TODAY_COPY.interrupted}`;
  return base;
}

/** freshness 條的即時來源訊號（維護者 fail-fast；藍圖 §8.1）。
 *  訪客面的降級是靜默的——這一句只描述觀察到的事實，不診斷 Redis 或 worker。 */
export function liveSourceNotice(today: TodaySlate | null): string | null {
  if (!today || today.games.length === 0) return null;
  if (today.live_source.status === "unavailable" || today.live_source.status === "disabled") {
    return TODAY_COPY.liveSourceDown;
  }
  if (today.live_source.status === "partial") return TODAY_COPY.liveSourcePartial;
  return null;
}
