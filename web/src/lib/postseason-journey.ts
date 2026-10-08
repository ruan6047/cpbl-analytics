// 季後追賽旅程的共用檢視模型（#237）：把官方公告（postseason-announcement.ts）與資料庫
// 已有的正式場次歸併成**同一份**場次清單與系列進度。首頁、季後總覽、日曆三個入口都只吃
// `buildPostseasonJourney` 的輸出，同樣輸入得到同樣的安排，三處才不會互相矛盾。
//
// 純函式：不抓資料、不讀時鐘（現在時刻由呼叫端注入）、不碰執行環境時區。
//
// 紅線：
// 1. 規則讓勝固定歸公告指定的球隊（2026＝兄弟），與實際場勝分開計算；不從戰況反推。
//    「獅贏前兩場」必須是獅 2、兄弟 1、系列未分勝負。
// 2. 單場連結只給資料庫裡真的有的場次，且一定帶 kind 與 year；公告場序不能變成場號，
//    A（例行賽）列一律不參與歸併。
// 3. 沒有完賽紀錄就沒有比分；已過預定開賽時間仍沒有賽果時明說「賽果待更新」，不猜結果。

import { announcementFor, type AnnouncedSlot, type PostseasonAnnouncement, type TeamSlot } from "./postseason-announcement.ts";
import { teamName3, teamShort } from "./teams.ts";

// —— 輸入 ——

/** 資料庫的季後場次列（calendar 端點的子集；未完賽時比分為 0）。 */
export type JourneyRow = {
  year: number;
  kind_code: string;
  game_sno: number;
  game_date: string;
  venue: string | null;
  away_team_code: string;
  home_team_code: string;
  away_score: number;
  home_score: number;
};

/** postseason-summary 的逐場（只含完賽場，沿用後端 `_DONE` 判準）。 */
export type SeriesGame = {
  game_no: number;
  game_sno?: number;
  date: string | null;
  home_code: string;
  home_score: number;
  away_code: string;
  away_score: number;
};

export type SummarySeries = {
  kind_code: string;
  team1_code: string;
  team2_code: string;
  games?: SeriesGame[];
};

export type JourneyInput = {
  announcement: PostseasonAnnouncement;
  /** postseason-summary 的系列；取不到時 null。 */
  summary: SummarySeries[] | null;
  /** calendar 的場次（任何賽別皆可，這裡只取 E／C）；取不到時 null。 */
  rows: JourneyRow[] | null;
  nowMs: number;
  /** 本站最近一筆完賽紀錄的日期（YYYY-MM-DD）；未知時 null。 */
  dataAsOf: string | null;
};

// —— 系列計算 ——

export type SideTally = {
  code: string | null;
  /** 規則勝（讓勝），不是實際比賽。 */
  ruleWins: number;
  /** 實際比賽勝場。 */
  gameWins: number;
  total: number;
  /** 還差幾勝晉級／封王；已分勝負後為 0。 */
  remaining: number;
};

export type SeriesTally = {
  a: SideTally;
  b: SideTally;
  decided: boolean;
  winner: string | null;
  /** 比分相同的完賽場數（挑戰賽沒有和局，出現即為異常；不算任何一方勝場）。 */
  ties: number;
};

export function gameWinner(g: Pick<SeriesGame, "home_code" | "home_score" | "away_code" | "away_score">): string | null {
  return g.home_score > g.away_score ? g.home_code : g.away_score > g.home_score ? g.away_code : null;
}

/** 系列大比分：實際勝場＋規則勝。系列卡與旅程模型共用這一份算法。
 *  沒有任何完賽場時不判勝負（沿用既有系列卡行為）。 */
export function tallySeries(
  a: { code: string | null; handicap: boolean },
  b: { code: string | null; handicap: boolean },
  games: SeriesGame[],
  needed: number,
): SeriesTally {
  const side = (s: { code: string | null; handicap: boolean }) => {
    const gameWins = s.code ? games.filter((g) => gameWinner(g) === s.code).length : 0;
    const ruleWins = s.handicap ? 1 : 0;
    return { code: s.code, ruleWins, gameWins, total: gameWins + ruleWins };
  };
  const sa = side(a);
  const sb = side(b);
  const decided = games.length > 0 && Math.max(sa.total, sb.total) >= needed;
  const winner = decided ? (sa.total >= sb.total ? sa.code : sb.code) : null;
  const remaining = (t: number) => (decided ? 0 : Math.max(0, needed - t));
  return {
    a: { ...sa, remaining: remaining(sa.total) },
    b: { ...sb, remaining: remaining(sb.total) },
    decided,
    winner,
    ties: games.filter((g) => gameWinner(g) === null).length,
  };
}

export type SeriesStatus = "not_started" | "in_progress" | "decided";

export type JourneySeries = {
  kind: "E" | "C";
  name: string;
  bestOf: number;
  winsNeeded: number;
  tally: SeriesTally;
  status: SeriesStatus;
  /** 完賽場（依日期序），供系列卡逐場欄與單場連結。 */
  games: SeriesGame[];
};

function seriesGames(summary: SummarySeries[] | null, kind: string, teams: (string | null)[]): SeriesGame[] {
  const known = teams.filter((t): t is string => !!t);
  const games = (summary ?? [])
    .filter((s) => s.kind_code === kind)
    .flatMap((s) => s.games ?? [])
    // 對手未定（C 的挑戰賽勝隊）時只要求種子隊在場；兩隊已知時兩隊都要在場。
    .filter((g) => known.every((t) => g.home_code === t || g.away_code === t));
  return [...games].sort((x, y) => (x.date ?? "").localeCompare(y.date ?? "") || (x.game_sno ?? 0) - (y.game_sno ?? 0));
}

function statusOf(t: SeriesTally, games: SeriesGame[]): SeriesStatus {
  return t.decided ? "decided" : games.length > 0 ? "in_progress" : "not_started";
}

// —— 場次歸併 ——

export type SlotStatus =
  | "final"          // 資料庫列已完賽
  | "scheduled"      // 有資料庫列、未完賽、未過開賽時間
  | "announced"      // 沒有資料庫列、未過開賽時間（公告安排）
  | "result_pending" // 已過預定開賽時間、沒有完賽紀錄
  | "not_needed";    // 條件場，系列已由實際資料分出勝負

export type JourneySlot = {
  key: string;
  kind: "E" | "C";
  seq: number;
  /** 顯示日期：有資料庫列時以資料庫為準。 */
  date: string;
  /** 公告開賽時刻（資料庫沒有開賽時刻欄位）。 */
  start: string | null;
  awayCode: string | null;
  homeCode: string | null;
  /** 隊伍未定或未取得時的說明，例如「挑戰賽勝隊」。 */
  awayLabel: string;
  homeLabel: string;
  venue: string | null;
  /** 球場未定或未取得時的說明。 */
  venueNote: string | null;
  conditional: boolean;
  status: SlotStatus;
  /** 公告與資料庫不一致時的註記（以資料庫為準）。 */
  changeNote: string | null;
  score: { away: number; home: number } | null;
  /** 只有資料庫列才有連結。 */
  href: string | null;
  /** 是否已對到資料庫列（日曆用來決定公告格要不要另畫）。 */
  row: JourneyRow | null;
};

export type PostseasonJourney = {
  year: number;
  announcement: PostseasonAnnouncement;
  series: { E: JourneySeries; C: JourneySeries };
  slots: JourneySlot[];
  /** 下一個還沒有賽果、也不是「不需進行」的場次。 */
  next: JourneySlot | null;
  /** 公告還有未完成的季後場次（＝不得稱全季結束）。 */
  remaining: boolean;
  /** 本站已有的季後完賽紀錄場數。 */
  recordedGames: number;
  dataAsOf: string | null;
  reserveDays: PostseasonAnnouncement["reserveDays"];
};

export const POSTSEASON_COPY = {
  eWinner: "挑戰賽勝隊",
  unknownTeam: "本站未取得",
  unknownVenue: "本站未取得，以官方公告為準",
  status: {
    final: "終場",
    scheduled: "已排定",
    announced: "公告安排",
    result_pending: "賽果待更新",
    not_needed: "依條件不需進行",
  } satisfies Record<SlotStatus, string>,
  conditional: "如有必要",
  conditionalNote: "系列尚未分出勝負才進行",
  notNeededNote: "系列已分勝負，依公告條件不需進行",
  changed: "公告原定，已異動，以官方賽程為準",
  reserveDay: "移動補賽日（遇延賽才使用，不是比賽）",
  noLink: "本站尚無官方台灣大賽場次編號，暫不提供單場連結",
} as const;

export function gameLink(kind: string, sno: number, year: number): string {
  return `/games/${sno}?kind=${kind}&year=${year}`;
}

/** `YYYY-MM-DD`＋`HH:mm`（台北）→ epoch ms。沒有開賽時刻時取當天 24:00 才算「已過」。 */
export function slotStartMs(date: string, start: string | null): number {
  return start ? Date.parse(`${date}T${start}:00+08:00`) : Date.parse(`${date}T00:00:00+08:00`) + 86_400_000;
}

function md(ymd: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(ymd);
  return m ? `${m[1]}/${m[2]}` : ymd;
}

function teamOf(slot: TeamSlot | null, eWinner: string | null): { code: string | null; label: string } {
  if (!slot) return { code: null, label: POSTSEASON_COPY.unknownTeam };
  if ("code" in slot) return { code: slot.code, label: teamName3(slot.code) || slot.code };
  return eWinner
    ? { code: eWinner, label: teamName3(eWinner) || eWinner }
    : { code: null, label: POSTSEASON_COPY.eWinner };
}

const VENUE_BY_WINNER = "依挑戰賽勝隊而定：";

function venueOf(slot: AnnouncedSlot, eWinner: string | null): { venue: string | null; note: string | null } {
  const v = slot.venue;
  if ("name" in v) return { venue: v.name, note: null };
  if ("unknown" in v) return { venue: null, note: POSTSEASON_COPY.unknownVenue };
  if (eWinner && v.byWinner[eWinner]) return { venue: v.byWinner[eWinner], note: null };
  const branches = Object.entries(v.byWinner).map(([code, name]) => `${teamShortName(code)}晉級→${name}`).join("／");
  return { venue: null, note: `${VENUE_BY_WINNER}${branches}` };
}

/** 二字隊慣稱（統一／兄弟／味全）；不認得的隊碼原樣回傳。 */
export function teamShortName(code: string): string {
  return teamShort(code) || code;
}

/** 歸併公告與資料庫。純函式；同樣輸入必得同樣輸出。 */
export function buildPostseasonJourney(input: JourneyInput): PostseasonJourney {
  const { announcement: ann, summary, nowMs, dataAsOf } = input;
  const year = ann.year;

  // E 系列：讓勝固定歸公告指定隊。
  const [eA, eB] = ann.series.E.teams;
  const eGames = seriesGames(summary, "E", [eA, eB]);
  const eTally = tallySeries(
    { code: eA, handicap: eA === ann.series.E.handicapTeam },
    { code: eB, handicap: eB === ann.series.E.handicapTeam },
    eGames,
    ann.series.E.winsNeeded,
  );
  const eWinner = eTally.winner;

  // C 系列：對手只在 E 由實際資料分出勝負後才填入。
  const cSeed = ann.series.C.seededTeam;
  const cGames = seriesGames(summary, "C", [cSeed, eWinner]);
  const cTally = tallySeries({ code: cSeed, handicap: false }, { code: eWinner, handicap: false }, cGames, ann.series.C.winsNeeded);

  const series = {
    E: { kind: "E" as const, name: ann.series.E.name, bestOf: ann.series.E.bestOf, winsNeeded: ann.series.E.winsNeeded, tally: eTally, status: statusOf(eTally, eGames), games: eGames },
    C: { kind: "C" as const, name: ann.series.C.name, bestOf: ann.series.C.bestOf, winsNeeded: ann.series.C.winsNeeded, tally: cTally, status: statusOf(cTally, cGames), games: cGames },
  };

  // 資料庫列：calendar 的 E／C ∪ summary 的完賽場（summary 帶 game_sno 時本身就是資料庫列）。
  // A 列一律不參與。
  const rowsByKey = new Map<string, JourneyRow>();
  for (const r of input.rows ?? []) {
    if (r.year === year && (r.kind_code === "E" || r.kind_code === "C")) rowsByKey.set(`${r.kind_code}-${r.game_sno}`, r);
  }
  const finals = new Map<string, SeriesGame>();
  // 舊版 API 沒有 game_sno：只能以「日期＋主客」認出完賽，給狀態與比分、不給連結。
  const finalsNoSno = new Map<string, SeriesGame>();
  for (const [kind, games] of [["E", eGames], ["C", cGames]] as const) {
    for (const g of games) {
      if (g.game_sno == null) {
        finalsNoSno.set(`${kind}|${g.date}|${g.away_code}|${g.home_code}`, g);
        continue;
      }
      const k = `${kind}-${g.game_sno}`;
      finals.set(k, g);
      if (!rowsByKey.has(k) && g.date) {
        rowsByKey.set(k, {
          year, kind_code: kind, game_sno: g.game_sno, game_date: g.date, venue: null,
          away_team_code: g.away_code, home_team_code: g.home_code, away_score: g.away_score, home_score: g.home_score,
        });
      }
    }
  }
  const rows = [...rowsByKey.values()];
  const cRows = rows.filter((r) => r.kind_code === "C");
  const announcedCDates = new Set(ann.slots.filter((s) => s.kind === "C").map((s) => s.date));
  // C 有資料庫列落在公告沒有的日期 → 公告已有異動的證據。
  const cMoved = cRows.some((r) => !announcedCDates.has(r.game_date));

  const slots: JourneySlot[] = ann.slots.map((slot) => {
    const decided = slot.kind === "E" ? eTally.decided : cTally.decided;
    let row: JourneyRow | null = null;
    let changeNote: string | null = null;
    if (slot.kind === "E" && slot.officialSno != null) {
      const cand = rowsByKey.get(`E-${slot.officialSno}`) ?? null;
      const away = slot.away && "code" in slot.away ? slot.away.code : null;
      const home = slot.home && "code" in slot.home ? slot.home.code : null;
      if (cand && cand.away_team_code === away && cand.home_team_code === home) {
        row = cand;
        if (cand.game_date !== slot.date) changeNote = `公告原定 ${md(slot.date)}`;
      } else if (cand) {
        changeNote = POSTSEASON_COPY.changed;
      }
    } else if (slot.kind === "C") {
      const sameDay = cRows.filter((r) => r.game_date === slot.date);
      if (sameDay.length === 1) row = sameDay[0];
      else if (sameDay.length > 1 || cMoved) changeNote = POSTSEASON_COPY.changed;
    }

    const away = row ? { code: row.away_team_code, label: teamName3(row.away_team_code) || row.away_team_code } : teamOf(slot.away, eWinner);
    const home = row ? { code: row.home_team_code, label: teamName3(row.home_team_code) || row.home_team_code } : teamOf(slot.home, eWinner);
    const v = row?.venue ? { venue: row.venue, note: null } : venueOf(slot, eWinner);
    const date = row?.game_date ?? slot.date;
    const fin = row
      ? finals.get(`${row.kind_code}-${row.game_sno}`)
      : finalsNoSno.get(`${slot.kind}|${date}|${away.code}|${home.code}`);
    const past = nowMs >= slotStartMs(date, slot.start);

    let status: SlotStatus;
    if (fin) status = "final";
    else if (!row && slot.conditional && decided) status = "not_needed";
    else if (past) status = "result_pending";
    else status = row ? "scheduled" : "announced";

    return {
      key: slot.key,
      kind: slot.kind,
      seq: slot.seq,
      date,
      start: slot.start,
      awayCode: away.code,
      homeCode: home.code,
      awayLabel: away.label,
      homeLabel: home.label,
      venue: v.venue,
      venueNote: v.note,
      conditional: slot.conditional,
      status,
      changeNote,
      score: fin ? { away: fin.away_score, home: fin.home_score } : null,
      href: row ? gameLink(row.kind_code, row.game_sno, year) : null,
      row,
    };
  });

  const open = (s: JourneySlot) => s.status !== "final" && s.status !== "not_needed";
  const ordered = [...slots].sort((x, y) => slotStartMs(x.date, x.start) - slotStartMs(y.date, y.start));
  // 「下一場」先找還沒到開賽時間的；全部都過了才退回最早一場待更新的。
  const next = ordered.find((s) => open(s) && s.status !== "result_pending")
    ?? ordered.find(open)
    ?? null;
  return {
    year,
    announcement: ann,
    series,
    slots,
    next,
    remaining: !cTally.decided && slots.some(open),
    recordedGames: eGames.length + cGames.length,
    dataAsOf,
    reserveDays: ann.reserveDays,
  };
}

/** 三入口的唯一進入點：該年度有官方公告才建模型，否則回 null（呼叫端走原路徑）。
 *  `rows` 用 calendar 的場次；資料截至取其中最近一筆完賽紀錄。 */
export function postseasonJourneyFor(
  year: number,
  summary: SummarySeries[] | null,
  rows: JourneyRow[] | null,
  nowMs: number,
): PostseasonJourney | null {
  const announcement = announcementFor(year);
  if (!announcement) return null;
  return buildPostseasonJourney({ announcement, summary, rows, nowMs, dataAsOf: latestResultDate(rows) });
}

/** 某隊可能出現在這個場次（日曆篩隊用）：未定席位以可能的參賽隊判斷。 */
export function slotMayInvolve(j: PostseasonJourney, s: JourneySlot, team: string): boolean {
  if (s.awayCode === team || s.homeCode === team) return true;
  if (s.awayCode && s.homeCode) return false;
  const e = j.announcement.series.E.teams;
  const cand = s.kind === "C"
    ? [j.announcement.series.C.seededTeam, ...(j.series.E.tally.winner ? [j.series.E.tally.winner] : e)]
    : e;
  return cand.includes(team);
}

// —— 文案 helper（三入口共用，避免各頁各寫一套） ——

export function shortDay(ymd: string): string {
  return md(ymd);
}

/** 「10/09（五）17:05」——純字串／UTC 算術，不吃執行環境時區。 */
export function slotWhen(s: Pick<JourneySlot, "date" | "start">): string {
  const ms = Date.parse(`${s.date}T00:00:00Z`);
  const wd = Number.isFinite(ms) ? `（${"日一二三四五六"[new Date(ms).getUTCDay()]}）` : "";
  return `${md(s.date)}${wd}${s.start ? ` ${s.start}` : ""}`;
}

/** 場次列上的球場短句：依晉級隊而定時只留分支（「球場依晉級隊：兄弟晉級→大巨蛋／統一晉級→亞太主」）。 */
export function slotVenueText(s: Pick<JourneySlot, "venue" | "venueNote">): string {
  if (s.venue) return s.venue;
  const branch = s.venueNote?.startsWith(VENUE_BY_WINNER) ? s.venueNote.slice(VENUE_BY_WINNER.length) : null;
  return branch ? `球場依晉級隊：${branch}` : (s.venueNote ?? "");
}

/** 公告沒寫主客也沒寫球場（本站未取得）：列上合併成一句，不逐欄重複「本站未取得」。 */
export function slotAllUnknown(s: Pick<JourneySlot, "awayCode" | "homeCode" | "awayLabel" | "homeLabel" | "venue" | "venueNote">): boolean {
  return !s.awayCode && !s.homeCode && !s.venue
    && s.awayLabel === POSTSEASON_COPY.unknownTeam && s.homeLabel === POSTSEASON_COPY.unknownTeam
    && s.venueNote === POSTSEASON_COPY.unknownVenue;
}

/** 有規則勝的一方把實際場勝與規則勝分列：「實際勝 2＋規則勝 1」。沒有規則勝時合計就是實際勝場，不另列。 */
export function tallyBreakdownText(t: Pick<SideTally, "gameWins" | "ruleWins">): string | null {
  return t.ruleWins > 0 ? `實際勝 ${t.gameWins}＋規則勝 ${t.ruleWins}` : null;
}

/** 「獅 2：兄弟 1（兄弟實際勝 0＋規則勝 1）・獅還差 1 勝、兄弟還差 2 勝」。 */
export function seriesProgressText(s: JourneySeries): string {
  const { a, b } = s.tally;
  const name = (t: SideTally, fallback: string) => (t.code ? teamShortName(t.code) : fallback);
  const an = name(a, POSTSEASON_COPY.eWinner);
  const bn = name(b, POSTSEASON_COPY.eWinner);
  const rule = [a, b].filter((t) => t.ruleWins > 0).map((t) => `${name(t, "")}${tallyBreakdownText(t)}`);
  const score = `${an} ${a.total}：${bn} ${b.total}${rule.length ? `（${rule.join("、")}）` : ""}`;
  if (s.status === "decided") {
    const w = s.tally.winner === a.code ? an : bn;
    return `${score}・${w}${s.kind === "E" ? "晉級台灣大賽" : "奪得總冠軍"}`;
  }
  const need = [a, b].filter((t) => t.code).map((t) => `${name(t, "")}還差 ${t.remaining} 勝`);
  return `${score}${need.length ? `・${need.join("、")}` : ""}`;
}

/** 本站季後資料狀態一句話：讀者據以分辨公告安排與已更新賽果。 */
export function journeyAsOfText(j: Pick<PostseasonJourney, "recordedGames" | "dataAsOf">): string {
  const asOf = j.dataAsOf ? `，本站賽果紀錄至 ${md(j.dataAsOf)}` : "";
  return j.recordedGames > 0
    ? `本站季後賽果紀錄 ${j.recordedGames} 場${asOf}`
    : `本站尚無季後賽果紀錄${asOf}`;
}

/** 公告來源一句話（含取得與核對）。 */
export function announcementSourceText(ann: PostseasonAnnouncement): string {
  const cap = ann.source.capturedAt;
  const capText = `${md(cap.slice(0, 10))} ${cap.slice(11, 16)}`;
  const okA = ann.source.checks.find((c) => c.scope === "announcement" && c.ok);
  const okE = ann.source.checks.find((c) => c.scope === "E" && c.ok);
  return `CPBL 官方 ${md(ann.source.publishedOn)} 公告，本站 ${capText} 取得` +
    (okA ? `，${md(okA.on)} 重新核對官網公告` : "") +
    (okE ? `；挑戰賽賽程 ${md(okE.on)} 已與官方賽程核對一致` : "");
}

/** 最近一筆完賽紀錄日期（比分總和 > 0，沿用日曆判準；任何賽別）。 */
export function latestResultDate(rows: Pick<JourneyRow, "game_date" | "away_score" | "home_score">[] | null): string | null {
  let best: string | null = null;
  for (const r of rows ?? []) {
    if (r.away_score + r.home_score > 0 && (!best || r.game_date > best)) best = r.game_date;
  }
  return best;
}
