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

/** 顯示用時區固定為台北。
 *
 *  **不吃執行環境時區**：本專案的容器沒有設 TZ（`python:3.12-slim-bookworm` 與 node 皆
 *  預設 UTC），瀏覽器則是台北，用預設時區格式化會讓 SSR 與 hydration 印出不同字串。
 *  釘死時區後兩邊必然一致，時刻也才是台灣讀者看得懂的那一個。 */
const TAIPEI = "Asia/Taipei";

/** ISO 時刻 → 台北的 `YYYY-MM-DD` 與 `HH:mm`；無法解析回 null。 */
export function taipeiParts(iso: string | null): { date: string; time: string } | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  const at = new Date(ms);
  return {
    // en-CA 產出 `YYYY-MM-DD`，可直接與 API 的日期字串比對，不必自己拼。
    date: new Intl.DateTimeFormat("en-CA", { timeZone: TAIPEI, year: "numeric",
                                             month: "2-digit", day: "2-digit" }).format(at),
    time: new Intl.DateTimeFormat("en-GB", { timeZone: TAIPEI, hour: "2-digit",
                                             minute: "2-digit", hour12: false }).format(at),
  };
}

/** 台北時刻 `HH:mm`（賽中卡的「最後更新」共用）。 */
export const taipeiTime = (iso: string | null): string | null => taipeiParts(iso)?.time ?? null;

/** `YYYY-MM-DD` 的前一天。純字串／UTC 算術，不碰執行環境時區。 */
function previousDay(ymd: string): string | null {
  const ms = Date.parse(`${ymd}T00:00:00Z`);
  return Number.isFinite(ms) ? new Date(ms - 86_400_000).toISOString().slice(0, 10) : null;
}

/** 最近一次刷新 → 「今日 10:12 刷新」／「昨日 10:12 刷新」／「08/05 10:12 刷新」。
 *
 *  **刻意不用「N 小時前」**：排程是每日 10:10 一班，所以隔天清晨顯示「20 小時前」是完全
 *  正常的狀態，卻與旁邊「資料為最新」的徽章讀起來互相矛盾；而那個數字幾乎永遠很大，
 *  大到多少都不代表任何事。維護者要回答的是「今天那班跑了沒」——是非題，不是時數。
 *
 *  落後與否仍由 `refreshCopy` 的 status 徽章承載（後端 `STALE_AFTER_HOURS = 24`），
 *  這一句永遠是中性灰字，只陳述時刻。
 *
 *  今日／昨日以 `freshness.as_of` 為基準（同一份 response 裡的日期），不用瀏覽器時鐘：
 *  一來 SSR 與 hydration 必然一致，二來與頁面其他地方的日期推導同源。 */
export function refreshAtText(at: string | null, asOf: string): string | null {
  const parts = taipeiParts(at);
  if (!parts) return null;
  if (parts.date === asOf) return `今日 ${parts.time} 刷新`;
  if (parts.date === previousDay(asOf)) return `昨日 ${parts.time} 刷新`;
  return `${shortDate(parts.date)} ${parts.time} 刷新`;
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

// —— 最近比賽日的混合日呈現（DAILY-MIXED-DAY-UX1，需求方 Design Gate 2026-08-16 全數裁定）——
//
// 痛點：`latest_game_day` 是「最近**有**完成場的那一天的**全部**場次」，不是「完成場清單」
// ——後端 `latest_day` 取 `max(game_date) WHERE completed`，接著把那一天的場次整批送出。
// 同一天同時有完賽與延賽時（2026-08-09 A#253 完賽＋A#254／255 延賽，本機 DB 實查），
// 未完成場帶著 `completed=false`、`home_score=null` 進到賽後卡，於是畫面上出現一張沒有
// 比分卻寫著「賽後復盤」的空卡。
//
// 紅線（卡面第 2 條）：**不得把未證實的原因說成事實**。可用的證據只有官方 `delay_kind`
// 兩個值（`延賽`／`保留`，對應官網 GameResult 1／2，見 GLOSSARY〈保留賽／delay_kind〉）
// 與 `orig_date`。**全庫沒有任何欄位記載延賽的原因**——本機實查 `cpbl` schema 下
// 所有 reason／note／weather 類欄位，唯一相關的 `game_detail.weather_desc` 是該場的天氣
// 描述而非停賽理由，且延賽場根本沒有 `game_detail` 列。故文案一律只講狀態，不講成因；
// 「因雨延賽」這種寫法沒有證據支撐，不得出現。
//
// **為什麼只有兩種未完成態，不是三種**：混合日的未完成場拆桶（2026-08-16 本機全庫實測，
// 同日同 kind_code 定義混合日）＝無註記且無取證 62 筆（1993-08-29～2025-09-24）、0:0 但
// 有官方 box 取證 4 筆、官方註記延賽 3 筆，合計 69。第三桶那 4 筆在後端改用
// `is_completed_game` 之後直接變成完成場離開這個集合（Design Gate 第 8 項），剩下正好是
// 「官方給了狀態」與「官方什麼都沒給」兩桶。所以兩種徽章是資料形狀決定的，不是版面偏好。

/** 最近比賽日單場的呈現態。`final` 以外皆為「這一天排了但沒有結果」。 */
export type LatestGameStatus = "final" | "postponed" | "reserved" | "unrecorded";

/** 官方 `delay_kind` 的兩個值（本機全庫實查：僅 `延賽` 59 筆、`保留` 8 筆，無第三種）。 */
const DELAY_POSTPONED = "延賽";
const DELAY_RESERVED = "保留";

/** 單場 → 呈現態。
 *
 *  **`completed` 必須先判，不可只看 `delay_kind`**：`delay_kind` 是排程歷程的**歷史標記**，
 *  補賽打完後仍留在該列——本機實查全庫 41 場**已完成**場次帶著 `delay_kind`（例：2026-06-27
 *  A#15 由 04-04 延到 06-27，最終 2:9 打完，`delay_kind` 仍是 `延賽`）。先看 `delay_kind`
 *  會把 41 場有比分的終場誤標成延賽。
 *
 *  `unrecorded`＝這一天排了這場、日期已過、我們手上沒有賽果，**且官方也沒有給狀態註記**。
 *  它是混合日未完成場的**多數**而非邊角：本機實查混合日的未完成場 69 筆中 62 筆無註記
 *  且無取證（1993–2025，以二軍為主），有 `延賽` 註記的只有 3 筆；另 4 筆是 0:0 真和局，
 *  在後端改判準之後已經是 `completed`，不再進到這個函式的未完成分支。 */
export function latestGameStatus(g: Pick<DailyGame, "completed" | "delay_kind">): LatestGameStatus {
  if (g.completed) return "final";
  const kind = g.delay_kind?.trim();
  if (kind === DELAY_POSTPONED) return "postponed";
  if (kind === DELAY_RESERVED) return "reserved";
  return "unrecorded";
}

/** 未完成場的狀態徽章文案。**改文案只需要動這一張表**。
 *  三句話由需求方 Design Gate（2026-08-16）逐條裁定，`daily-summary.test.ts` 釘住字面。
 *
 *  三句話都只描述**狀態**或**我們的紀錄**，沒有一句宣稱成因：
 *  - `postponed`／`reserved` 是官方直接給的狀態，照搬不加工；
 *  - `unrecorded` 講的是「我們的紀錄裡沒有賽果」，這是可證的；講「未開打」則不可證
 *    ——沒有註記的場次我們分不出它是沒打、打了沒爬到、還是官網自己沒更新。 */
export const LATEST_STATUS_COPY: Record<
  Exclude<LatestGameStatus, "final">,
  { label: string; tone: FreshnessTone }
> = {
  // 官方與球迷都用「延賽」，`delay_kind` 的原字也是它（`聯盟規章.txt` 出現 19 次，本機
  // 實測）。與 `lib/live-game.ts` 的 canonical `phaseLabel` 用詞不同一事由對照表維持，
  // 不靠把兩邊改成同一個詞來解決——那會讓官方詞彙遷就內部字彙。
  postponed: { label: "延賽", tone: "warn" },
  // 「保留比賽」是**規則書用詞**，不是自創解釋：本機實測 `docs/reference/棒球規則.txt`
  // 20 次、`聯盟規章.txt` 9 次、`裁判執法手冊規則補述.txt` 9 次。曾提過的「保留・擇期
  // 續賽」把規則詞加上自撰註解，被需求方否決——官方詞彙優先。
  reserved: { label: "保留比賽", tone: "warn" },
  // 刻意**不用** canonical 的「狀態確認中」：那句話隱含「有人正在確認」，而這 62 筆最早
  // 回到 1993 年，沒有任何確認程序在跑。改成陳述我們的紀錄狀態，不暗示任何進行中的動作。
  unrecorded: { label: "無賽果紀錄", tone: "scheduled" },
};

/** 未完成場的補充事實：這一場原定在別的日子（Design Gate 第 6 項：留）。
 *
 *  只在 `orig_date` 與 `game_date` **不同**時才出現，因為相同代表「延賽且尚未排定補賽日」
 *  （本機實查：A#254／255 兩筆 `orig_date === game_date`），此時講任何日期都是無中生有。
 *  刻意**不寫**「補賽日期未定」——我們能證明的只有「我們的資料裡沒有新日期」，不是
 *  「官方尚未公布」。這個保守作法在 Design Gate 上被明確採納。 */
export function latestGameDateNote(
  g: Pick<DailyGame, "completed" | "orig_date" | "game_date">,
): string | null {
  if (g.completed || !g.orig_date || g.orig_date === g.game_date) return null;
  return `原定 ${shortDate(g.orig_date)}`;
}

/** 卡片右下角的入口文案。已完成場一字不動（驗收條件：賽後入口不得退化）。 */
export const LATEST_FOOTER_COPY = {
  final: "賽後復盤 →",
  /** 未完成場**不給連結**（Design Gate 第 4 項）：`/games/254` 目前的 SSR 內容是空的，且
   *  document title 直接寫「味全龍 vs 樂天桃猿 0：0」——把使用者送過去等於把「空白賽後卡」
   *  換成「宣稱 0：0 的空白頁」，痛點沒有解決只是換了位置。
   *
   *  **不連結只是治標，而治本不在本卡射程**：title 的根因是 `lib/entity-metadata.ts` 用
   *  `score != null` 而不是「這場打完了」判定要不要印比分，延賽場在 DB 是 0/0 不是 NULL。
   *  賽況月曆一樣會連過去、搜尋引擎一樣索引得到。修法是「metadata 端點回傳 `completed`、
   *  TS 消費它」而**不是**在 TypeScript 裡再抄一次完成場判準（那會是第三份副本）——
   *  已另開 `UX-GAME-META-COMPLETED1`（#148）承接。 */
  pending: null,
} as const;

/** 這一天有幾場沒有賽果。0＝全部完成（今日的常態），等於總場數＝一場都沒有結果。 */
export function latestDayPendingCount(games: DailyGame[]): number {
  return games.filter((g) => !g.completed).length;
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
  liveSourceNoGames: "今日無賽程",
  liveSourceOk: "即時賽況正常",
  /** 保留賽＝已開賽後中止，比分照顯示；這一句負責防止它被讀成終場。 */
  reservedNote: "保留・擇期續賽",
} as const;

export type TodayCardKind = "pregame" | "live" | "final" | "postponed" | "reserved";

/** 場次卡要渲染哪一態。
 *
 *  **延賽與保留賽是兩件事，不可併成一態**（需求方 2026-08-07 人工審裁定 1）：
 *  依 `docs/reference/GLOSSARY.md`〈保留賽／`delay_kind`〉，官網 `GameResult=1` 是延賽
 *  （根本沒開打），`GameResult=2` 是**保留**——已開賽後中止，場上是有比分的。把保留賽
 *  的比分藏起來比顯示出來更失真；狀態文字負責防止它被讀成終場。
 *
 *  判定順序＝**snapshot phase 優先於 DB 比分**。保留賽在 `cpbl.games` 裡帶著比分，而
 *  `_serialize` 的完成場判準（有比分且日期不在未來）會把當天的保留賽算成 completed；
 *  若先看 `g.completed`，一場中止的比賽會被畫成終場。DB 比分只在**沒有 snapshot 時**
 *  當後備（隔日爬蟲補完、worker 早已不供該場的情形）。 */
export function todayCardKind(g: TodayGame): TodayCardKind {
  const phase = g.live?.phase;
  if (phase === "postponed") return "postponed";
  if (phase === "reserved") return "reserved";
  if (phase === "live") return "live";
  if (phase === "final" || g.completed) return "final";
  // 沒有 snapshot、也沒有賽果時，官方 `delay_kind` 是手上唯一還在的事實。2026-08-19 的
  // A#274 正是這一格（`live` 為 null、`completed` 為 false、`delay_kind` 為「延賽」）：
  // 舊版直接落到 `pregame`，於是一場官方已宣布延賽的比賽被畫成「還沒開打」，而畫面上
  // 唯一的說明文字是賽前卡的「模型尚未建置」——等於拿模型狀態充當缺分的原因。
  //
  // **必須排在 `completed` 之後**：`delay_kind` 是排程歷程的歷史標記，補賽打完後仍留在
  // 該列（`latestGameStatus` 的 docstring 記錄本機實查 41 場**已完成**場次帶著它）。先看
  // 它會把補賽日當天已經打完的那一場誤標成延賽。
  //
  // 徽章一律只用 `delay_kind` 原文，**不解釋成因**：`delay_kind` 由同 `game_sno` 的排程
  // 歷程推得（`ingest/cpbl_site.py`），官方給的是代碼不是理由；`cpbl.games` 上沒有任何
  // reason／note 欄位，延賽場連 `game_detail` 列都沒有。寫「因雨」是無中生有。
  const delay = g.delay_kind?.trim();
  if (delay === DELAY_POSTPONED) return "postponed";
  if (delay === DELAY_RESERVED) return "reserved";
  return "pregame";
}

/** 今日賽事卡的狀態徽章文案；`null`＝這一態不由徽章表承載（賽前／賽中／賽後各有自己的）。
 *
 *  **與最近比賽日共用同一張 `LATEST_STATUS_COPY`**：同一場延賽在首頁的兩個區塊裡不得
 *  是兩個詞。刻意**不走** `lib/live-game.ts` 的 canonical `phaseLabel`——它對 `postponed`
 *  回的是「延期」，而需求方在 2026-08-16 Design Gate 明確裁定用官方原文「延賽」
 *  （`delay_kind` 的原字、官方與球迷都這樣講）。canonical 詞彙遷就官方詞彙，不是反過來。
 *
 *  **詞不隨來源改變**：不管這一態是 worker snapshot 給的還是 DB `delay_kind` 推的，
 *  讀者看到的都是同一個字。徽章只講狀態，一律**不講成因**（沒有任何欄位存得下理由）。 */
export function todayStatusCopy(g: TodayGame): { label: string; tone: FreshnessTone } | null {
  const kind = todayCardKind(g);
  if (kind === "postponed") return LATEST_STATUS_COPY.postponed;
  if (kind === "reserved") return LATEST_STATUS_COPY.reserved;
  return null;
}

/** 該場今天還會不會變。全部不會變時輪詢應完全停止。
 *
 *  保留賽算 settled：依 GLOSSARY，保留賽的補賽掛在**另一個日期**（`orig_date` 記原開賽
 *  日、`game_date` 指向未來的補賽時段），故同一天不會續打完。延賽同理。 */
export function todayGameSettled(g: TodayGame): boolean {
  const kind = todayCardKind(g);
  return kind === "final" || kind === "postponed" || kind === "reserved";
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
 *
 *  **四態各有自己的文案，且一定會渲染其中一格**——這是需求方 2026-08-07 裁決 B 的要求。
 *  原本只在異常時顯示一句話，於是「今天沒有比賽」（正常，沒有人需要做事）與「今日即時
 *  來源不可用」（要人去看即時管道）在畫面上都是**一片空白**，維護者分不出來；而 Redis
 *  全斷時訪客面本來就會靜默退回純日期版面，兩者長得一模一樣。用「沒有訊號」表達「一切
 *  正常」在這裡行不通，所以正常態也明講。
 *
 *  文案只描述**觀察到的事實**（今天有幾場、其中幾場拿得到即時資料），不診斷成因——
 *  API 這一側分不出「即時管道不通」「上游沒跑」「不在抓取窗口」，講死任何一個都超出
 *  證據，而且訪客也看得到這一條。 */
export type LiveSourceSignalKind = "no_games" | "ok" | "partial" | "down" | "settled";

export type LiveSourceSignal = {
  kind: LiveSourceSignalKind;
  /** 完整語意；`display="symbol"` 時它只出現在 `aria-label`／`title`，不佔版面。 */
  label: string;
  tone: FreshnessTone;
  /** `badge`＝完整文字徽章；`symbol`＝時間戳旁的小字符號（僅「一切正常」那一態）。 */
  display: "badge" | "symbol";
  /** `display="symbol"` 時要畫的字元。 */
  symbol?: string;
};

/** 今天還有幾場**畫面上真的在等即時資料**。
 *
 *  已有賽果（`final`）、或官方已給終止狀態（`postponed`／`reserved`）的場次不算：那些
 *  卡片不因即時來源斷線而少掉任何一塊內容，即時管道此刻對它們沒有影響。
 *
 *  這個分母就是 2026-08-19 那句假敘述的修法（需求方當晚裁定「footer 那句要改掉」）。
 *  當晚 freshness 條寫著「今日 3 場無法取得即時賽況」，而同一排卡片裡有兩張明白標著
 *  「比賽結束」並顯示終局比分——那句話**就印在推翻它的證據旁邊**。成因是舊版拿
 *  `live_source.games`（今天排了幾場）當分母，但那個數字回答的是「今天有幾場比賽」，
 *  不是「畫面上缺了幾場」；而每天傍晚場次打完、live worker 收工之後，兩者必然分岔。 */
function awaitingLiveCount(today: TodaySlate): number {
  return today.games.filter((g) => !todayGameSettled(g) && !g.live).length;
}

export function liveSourceSignal(today: TodaySlate | null): LiveSourceSignal {
  if (!today || today.games.length === 0) {
    // 正常狀態，不需要任何人做事——但**維持完整文字**：它同時解釋了版面為什麼是舊雙塊
    // （需求方 2026-08-07 人工審裁定 4），這是讀者需要的資訊，不只是健康訊號。
    return { kind: "no_games", label: TODAY_COPY.liveSourceNoGames, tone: "scheduled",
             display: "badge" };
  }
  const { status, games } = today.live_source;
  const awaiting = awaitingLiveCount(today);
  // 一場都不缺 → 這一格**不得喊警示**。此時即時管道接不接得上對畫面沒有差別，而場次
  // 全部打完之後這是每天的常態；照舊喊警示等於天天對維護者狼來了一次。
  // 文案只講得出來的那件事：每一場**都拿得到官方狀態**（終局比分，或官方的延賽／保留
  // 註記）。刻意**不寫**「皆已完賽」——延賽場並沒有完賽，那會是另一句假敘述。
  if (awaiting === 0 && status !== "ok") {
    return { kind: "settled", label: `今日 ${games} 場皆已有官方狀態`, tone: "done",
             display: "badge" };
  }
  // 文案是「無法取得」而非「無」：開賽前本來就沒有比賽在進行，「無」會被讀成那個意思；
  // 實際狀況是**取不到資料**（裁定 2）。數字一律是 `awaiting` 而非總場數——見上。
  if (status === "unavailable" || status === "disabled") {
    return { kind: "down", label: `今日 ${awaiting} 場無法取得即時賽況`, tone: "warn",
             display: "badge" };
  }
  if (status === "partial") {
    return { kind: "partial",
             label: `今日 ${games} 場中 ${awaiting} 場無法取得即時賽況`,
             tone: "warn", display: "badge" };
  }
  // 一切正常：完整文字在每個比賽日都掛著太吵，壓縮成時間戳旁的符號。語意不縮水——
  // 完整句子改由 aria-label／title 承載，螢幕閱讀器與滑鼠使用者都拿得到。
  // **只有這一態壓縮**：被省下的是「不需要行動」那一格，兩個異常態維持完整文字＋警示色。
  return { kind: "ok", label: TODAY_COPY.liveSourceOk, tone: "done",
           display: "symbol", symbol: "✓" };
}
