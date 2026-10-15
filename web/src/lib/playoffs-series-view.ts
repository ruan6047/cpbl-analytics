// `/playoffs` 第 1 區（系列賽表現）的檢視模型（#285 S04）：純函式，只把 `playoffs-overview/v1` 原值排成字。
//
// 紅線：
// - ⛔ 重算勝場、完賽、勝隊、目標場——全讀 overview（S02 原值）。
// - 系列一句（需求方 D3）只用 S02 的 `sides[].total_wins／initial_wins`、`winner`、`ties`；規則勝分開寫，
//   不寫成「N 勝 M 敗」（對手的規則勝不是實際敗場）。
// - 預告不含先發投手（需求方 D7）；MVP 缺值寫「本站尚未取得」，⛔ 寫「未公布」。
// - 每張完賽卡比分＋官方 MVP＋單場連結；未完賽卡沒有比分（S02 恆 null）。

import { teamName3 } from "./teams.ts";
import type { OverviewGameCard, OverviewSeriesBlock, PlayoffsOverview, PlayoffsSeriesCode } from "./playoffs-types.ts";

export const SERIES_NAME: Record<PlayoffsSeriesCode, string> = { E: "季後挑戰賽", C: "台灣大賽" };

export const SERIES_COPY = {
  mvpNotIngested: "官方 MVP：本站尚未取得",
  mvpNameMissing: "官方 MVP：姓名本站尚未取得",
  noNextGame: "下一場賽程本站尚未取得",
  overviewFailed: "季後賽資料暫時無法讀取",
  empty: "本站尚無這一年的季後賽場次",
  noGames: "場次本站尚未取得",
  pendingUpdate: "最新完賽結果更新中，比分以本站已同步的為準",
  coverageUnknown: "本站資料完整度未知，比分以本站已同步的為準",
  pollFailed: "最新資料暫時無法取得，畫面維持上一次取得的內容",
  conditional: "如有必要",
  unknownTeam: "待定",
} as const;

export function teamLabel(code: string | null | undefined): string {
  return (code && teamName3(code)) || code || SERIES_COPY.unknownTeam;
}

function md(ymd: string | null): string {
  const m = ymd ? /^\d{4}-(\d{2})-(\d{2})/.exec(ymd) : null;
  return m ? `${Number(m[1])}/${Number(m[2])}` : "日期待定";
}

/** 「10/17（六）」；無日期時「日期待定」。 */
export function dateText(ymd: string | null): string {
  if (!ymd) return md(null);
  const ms = Date.parse(`${ymd}T00:00:00Z`);
  const wd = Number.isFinite(ms) ? `（${"日一二三四五六"[new Date(ms).getUTCDay()]}）` : "";
  return `${md(ymd)}${wd}`;
}

export function gameTitle(card: Pick<OverviewGameCard, "game_key" | "series_game_no">): string {
  return `${SERIES_NAME[card.game_key.kind_code]} G${card.series_game_no}`;
}

export function gameHref(card: Pick<OverviewGameCard, "game_key">): string {
  const k = card.game_key;
  return `/games/${k.game_sno}?kind=${k.kind_code}&year=${k.year}`;
}

export type CardStatus = { text: string; tone: "done" | "warn" | "live" | "scheduled" };

/** 場次狀態章：完賽／進行中／延賽／賽果待更新／賽前，皆有文字（不只靠顏色）。 */
export function cardStatus(card: OverviewGameCard): CardStatus {
  if (card.completed) return { text: "終場", tone: "done" };
  if (card.target_status === "live") return { text: "進行中", tone: "live" };
  if (card.target_status === "suspended") return { text: "暫停", tone: "warn" };
  if (card.official_status === "postponed" || card.target_status === "postponed") return { text: "延賽", tone: "warn" };
  if (card.official_status === "reserved") return { text: "保留", tone: "warn" };
  if (card.display_status === "result_pending") return { text: "賽果待更新", tone: "warn" };
  return { text: "賽前", tone: "scheduled" };
}

export function mvpText(card: OverviewGameCard): string | null {
  if (!card.completed) return null;
  if (card.mvp?.name) return `官方 MVP：${card.mvp.name}`;
  return card.mvp_missing_reason === "player_name_unavailable" ? SERIES_COPY.mvpNameMissing : SERIES_COPY.mvpNotIngested;
}

/** 卡上要顯示的場次：依 S02 的「不需進行」隱藏旗標過濾，順序沿系列場序。 */
export function visibleCards(block: OverviewSeriesBlock): OverviewGameCard[] {
  return block.games.filter((g) => !g.hidden_not_needed);
}

function ruleNote(block: OverviewSeriesBlock): string {
  const rule = block.sides.filter((s) => (s.initial_wins ?? 0) > 0).map((s) => `${teamLabel(s.team_code)}含規則勝 ${s.initial_wins}`);
  const ties = block.ties > 0 ? [`和局 ${block.ties}`] : [];
  const parts = [...rule, ...ties];
  return parts.length ? `（${parts.join("、")}）` : "";
}

function formatText(block: OverviewSeriesBlock): string {
  return block.best_of && block.wins_needed ? `${block.best_of} 戰 ${block.wins_needed} 勝制` : "賽制本站尚未取得";
}

/** 需求方 D3「系列一句」。 */
export function seriesSentence(block: OverviewSeriesBlock): string {
  const name = SERIES_NAME[block.kind_code];
  const [a, b] = block.sides;
  if (block.series_status === "unknown" || block.conflict_reason || !a || !b) return `${name}系列狀態待確認`;
  if (block.series_status === "decided" && block.winner) {
    const w = block.sides.find((s) => s.team_code === block.winner)!;
    const l = block.sides.find((s) => s.team_code !== block.winner)!;
    const outcome = block.kind_code === "E" ? "晉級台灣大賽" : "奪得總冠軍";
    return `${teamLabel(w.team_code)}以 ${w.total_wins}：${l.total_wins} ${outcome}${ruleNote(block)}`;
  }
  const score = `${teamLabel(a.team_code)} ${a.total_wins ?? "?"}：${teamLabel(b.team_code)} ${b.total_wins ?? "?"}`;
  if (block.series_status === "pending") {
    return `${name} ${formatText(block)}，尚未開打・${score}${ruleNote(block)}`;
  }
  const need = block.sides.filter((s) => s.team_code && s.remaining != null)
    .map((s) => `${teamLabel(s.team_code)}還差 ${s.remaining} 勝`);
  return `${score}${ruleNote(block)}${need.length ? `・${need.join("、")}` : ""}`;
}

/** 完賽卡比分列（客左主右）；未完賽回 null。 */
export function scoreLine(card: OverviewGameCard): { away: string; home: string; awayScore: number; homeScore: number } | null {
  if (!card.completed || card.away_score == null || card.home_score == null) return null;
  return { away: teamLabel(card.away_team_code), home: teamLabel(card.home_team_code), awayScore: card.away_score, homeScore: card.home_score };
}

/** 開賽時刻＋來源（公告常數）。 */
export function startText(card: OverviewGameCard, overview: Pick<PlayoffsOverview, "schedule_source">): string {
  if (!card.start) return "開賽時間本站尚未取得";
  const src = overview.schedule_source;
  return src ? `${card.start} 開賽（官方 ${md(src.published_on)} 公告）` : `${card.start} 開賽`;
}

export function nextGameMissingText(o: PlayoffsOverview): string | null {
  const r = o.series_section.next_game_missing_reason;
  if (!r || r === "series_decided") return null;
  return SERIES_COPY.noNextGame;
}

/** 頁首資料時點：本站最近一次整鏈更新（台北時間）＋覆蓋狀態。 */
export function asOfText(o: Pick<PlayoffsOverview, "as_of">): string {
  const at = o.as_of.last_refresh_at;
  const m = at ? /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(taipeiIso(at)) : null;
  return m ? `本站資料更新於 ${Number(m[1])}/${Number(m[2])} ${m[3]}:${m[4]}` : "本站資料更新時間未取得";
}

function taipeiIso(iso: string): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms + 8 * 3_600_000).toISOString();
}

/** 第 1 區的區塊缺值說明（逐區缺資料原因）。 */
export function seriesNotices(o: PlayoffsOverview): string[] {
  const out: string[] = [];
  if (o.coverage === "pending_update") out.push(SERIES_COPY.pendingUpdate);
  else if (o.coverage === "unknown") out.push(SERIES_COPY.coverageUnknown);
  return out;
}
