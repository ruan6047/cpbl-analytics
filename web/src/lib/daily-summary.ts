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
  PREGAME_COPY,
  type PregameCardModel,
  type PregameItemSignal,
} from "./pregame-card.ts";
import { methodologyHref } from "./methodology-anchors.ts";

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

export type DailySummary = {
  scope: { season: number | null; kind_code: string; kinds: string[]; as_of: string };
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
    pregame_model: AxisStatus & { trained_through: number | null; signals: Record<string, string> | null };
  };
};

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
