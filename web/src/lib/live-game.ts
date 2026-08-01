export type StatRow = Record<string, number | string | boolean | null | undefined>;
export type CanonicalPhase =
  | "scheduled" | "probable_announced" | "lineup_announced" | "live" | "final"
  | "postponed" | "reserved" | "unknown";
export type Availability = "not_announced" | "partial" | "announced" | "source_error" | "stale";

export type CanonicalLineup = {
  availability: Availability;
  items: { batting_order: number; player_id: string; name: string; position: string }[];
  first_observed_at?: string | null;
};

export type LivePerson = { player_id: string; name: string; yearly_count?: number | null };

export type LiveSide = {
  team: { code: string; name: string };
  score: number;
  // 隊伍層級 H/E。null = 官方未供（與「值為零」不同），舊 snapshot 也可能整個缺欄位。
  hits?: number | null;
  errors?: number | null;
  record?: { w: number | null; l: number | null; t: number | null } | null;
  inning_score: Record<string, unknown>[];
  lineup: CanonicalLineup;
  hitters: Record<string, unknown>[];
  pitchers: Record<string, unknown>[];
  probable_pitcher: { availability: "not_announced" };
};

export type LiveDecisions = {
  winning_pitcher: LivePerson | null;
  losing_pitcher: LivePerson | null;
  closer: LivePerson | null;
  mvp: LivePerson | null;
};

export type LiveSnapshot = {
  game_id: string;
  game_sno: number;
  kind_code: string;
  phase: CanonicalPhase;
  raw_status: string | null;
  starts_at?: string | null;
  inning: number | null;
  half: string | number | null;
  event_count: number;
  tracking_count: number;
  tracking_availability: "not_announced" | "pending" | "available" | "unknown";
  poll_after_seconds: number | null;
  freshness: "fresh" | "stale" | "final";
  source_status: "ok" | "error";
  stale_after_seconds: number | null;
  source: { fetched_at: string | null; version?: string | null; last_error_at?: string | null };
  away: LiveSide;
  home: LiveSide;
  livelog: Record<string, unknown>[];
  // 以下為 LIVE-SNAPSHOT-FIELDS1 additive 欄位；舊 snapshot 可能整個缺，故全為 optional。
  decisions?: LiveDecisions | null;
  venue?: string | null;
  umpires?: { job: string; name: string }[];
  // 官方權威旗標：true = 該球場不配置 TrackMan。undefined = 舊 snapshot 未帶。
  skip_trackman?: boolean | null;
};

export type LiveApiResponse = {
  game: StatRow | null;
  scoreboard: StatRow[];
  livelog: StatRow[];
  batting: StatRow[];
  pitching: StatRow[];
  people: Record<string, string>;
  records: Record<string, { w: number; l: number; form: string }>;
  batter_avg: Record<string, number>;
  detail: StatRow | null;
  decisions?: Record<string, "W" | "L" | "SV" | "HLD">;
  decision_counts?: unknown;
  has_tracking: boolean;
  tracking: unknown[];
  spray?: unknown[];
  live_snapshot: LiveSnapshot | null;
};

export type GameStatusResponse = {
  canonical_phase: CanonicalPhase;
  live_snapshot: LiveSnapshot | null;
};

const PHASE_LABEL: Record<CanonicalPhase, string> = {
  scheduled: "未開賽",
  probable_announced: "賽前資訊已更新",
  lineup_announced: "先發名單已公布",
  live: "比賽進行中",
  final: "比賽結束",
  postponed: "延期",
  reserved: "保留比賽",
  unknown: "狀態確認中",
};

export const phaseLabel = (phase: CanonicalPhase) => PHASE_LABEL[phase];

export const isTopHalf = (half: LiveSnapshot["half"]): boolean => half === "top" || String(half) === "1";

export const canShowPostgameConclusions = (
  snapshot: LiveSnapshot | null,
  scoreTotal: number,
): boolean => scoreTotal > 0 && (snapshot === null || snapshot.phase === "final");

/** 局數是否為真值。worker 對未開打場次仍回 `inning=1／half=1` 佔位（生產實測
 *  SCHEDULED 場 inning=1、event_count=0；FINISHED 場 inning=9、half=2 為真值），
 *  故不可只判 `inning` truthy，否則未開賽會顯示「▲ 1 局」。判準＝比賽確實打過：
 *  live／final 一律成立，其餘 phase（保留賽等可能已打數局）改以 event_count 認定。 */
export const hasStartedPlay = (snapshot: LiveSnapshot): boolean =>
  snapshot.phase === "live" || snapshot.phase === "final" || snapshot.event_count > 0;

/** 狀態列與 aria-live 共用的局數文案；未開打回 null 讓呼叫端顯示「等待賽況」。 */
export const inningLabel = (
  snapshot: LiveSnapshot,
  style: "glyph" | "text",
): string | null => {
  if (!hasStartedPlay(snapshot) || !snapshot.inning) return null;
  const top = isTopHalf(snapshot.half);
  return style === "glyph"
    ? `${top ? "▲" : "▼"} ${snapshot.inning} 局`
    : `${top ? "上" : "下"}${snapshot.inning}局`;
};

export function resolveStatusSnapshot(previous: LiveSnapshot | null, incoming: LiveSnapshot | null) {
  if (!incoming) return { accepted: false, interrupted: true, snapshot: previous };
  return {
    accepted: true,
    interrupted: incoming.source_status === "error" || incoming.freshness === "stale",
    snapshot: incoming,
  };
}

/** 逐球追蹤缺資料的文案。實測 TrackMan 是賽後才發布（2026-A-234 完賽當下 0/260，
 *  約四小時後 249/260），故賽中缺資料是常態、不是球場沒設備。只有官方 `skip_trackman`
 *  明確為 true 時才可說該場地不提供；未知一律用中性文案。 */
export const trackingPendingMessage = (snapshot: LiveSnapshot | null): string => {
  if (trackmanAvailability(snapshot) === "unavailable") {
    return "本場地未配置逐球追蹤設備，無進壘點、球種與球速。";
  }
  return snapshot && snapshot.phase !== "final"
    ? "賽中逐球追蹤尚在整理；目前以文字賽況為準，完賽資料補齊後再顯示。"
    : "本場尚無可顯示的逐球追蹤資料。";
};

export function lineupMessage(
  availability: Availability,
  freshness: LiveSnapshot["freshness"],
  sourceStatus: LiveSnapshot["source_status"],
): string {
  if (sourceStatus === "error") return "來源中斷（保留最近名單）";
  if (freshness === "stale") return "資料可能已過期（保留最近名單）";
  if (availability === "announced") return "已公布";
  if (availability === "partial") return "部分公布";
  if (availability === "source_error") return "來源中斷";
  if (availability === "stale") return "資料可能已過期";
  return "尚未公布";
}

export function nextPollDelay(snapshot: LiveSnapshot | null, visible: boolean): number | null {
  if (!visible || snapshot?.phase === "final") return null;
  if (snapshot?.phase === "live") return Math.max(10, snapshot.poll_after_seconds ?? 12) * 1_000;
  return 60_000;
}

export function shouldFetchLivePayload(current: LiveSnapshot | null, next: LiveSnapshot | null): boolean {
  if (!next) return false;
  if (!current) return true;
  return next.event_count !== current.event_count
    || next.tracking_count !== current.tracking_count
    || next.phase !== current.phase
    || next.source.version !== current.source.version;
}

const snake = (key: string) => key
  .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
  .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
  .toLowerCase();

const bool = (value: unknown) => value === true || value === 1 || value === "1" || value === "true";

function normalized(row: Record<string, unknown>): StatRow {
  const result: StatRow = {};
  for (const [key, value] of Object.entries(row)) {
    const normalizedKey = snake(key);
    result[normalizedKey] = key.startsWith("Is") ? bool(value) : value as StatRow[string];
  }
  return result;
}

// key 必須等於 snake() 對官方欄位的實際輸出。曾把 RunBattedINCnt 手寫成
// run_batted_incnt（少一個底線），使打點／觸身／盜壘整欄空白且測試靜默通過；
// tests/test_live_game_backend.py 以真實 payload 的 key 集合守住這件事。
//
// 註：滿貫（GrandSlamHomerunCnt）、致勝打點（GameWinningRbiCnt）、背號
// （HitterUniformNo）、個人失誤、IsMvp、RoleType 是主站 box/getlive 專有，
// stats 站永遠不供，故賽中算不出來——不列 alias，由呼叫端 fail-closed。
const BATTER_ALIASES: Record<string, string> = {
  hit_cnt: "at_bats", hitting_cnt: "hits", run_batted_in_cnt: "rbi", score_cnt: "runs",
  one_base_hit_cnt: "singles", two_base_hit_cnt: "doubles", three_base_hit_cnt: "triples",
  home_run_cnt: "home_runs", double_play_bat_cnt: "gidp",
  sacrifice_hit_cnt: "sac_hit", sacrifice_fly_cnt: "sac_fly", bases_on_balls_cnt: "bb",
  intentional_bases_on_balls_cnt: "ibb", hit_by_pitch_cnt: "hbp", strike_out_cnt: "so",
  steal_base_ok_cnt: "sb", steal_base_fail_cnt: "cs",
};

// 投手側同理：GameResult／IsCompleteGame／IsShoutOut／GameHigherSpeedPitch 主站專有，
// 故完投、完封、最速球賽中不可得（保留 alias 供 DB 路徑沿用同一組正規化）。
const PITCHER_ALIASES: Record<string, string> = {
  inning_pitched_div3_cnt: "inning_pitched_div3", hitting_cnt: "hits", home_run_cnt: "home_runs",
  sacrifice_hit_cnt: "sac_hit", sacrifice_fly_cnt: "sac_fly", bases_on_balls_cnt: "bb",
  intentional_bases_on_balls_cnt: "ibb", hit_by_pitch_cnt: "hbp", strike_out_cnt: "so",
  wild_pitch_cnt: "wild_pitch", balk_cnt: "balk", run_cnt: "runs", earned_run_cnt: "earned_runs",
  relief_point_cnt: "relief_point", game_higher_speed_pitch: "max_speed",
  pitcher_uniform_no: "uniform_no", is_shout_out: "is_shutout",
};

function aliases(row: StatRow, mapping: Record<string, string>): StatRow {
  const result = { ...row };
  for (const [from, to] of Object.entries(mapping)) if (from in row) result[to] = row[from];
  return result;
}

function boxRows(side: "1" | "2", rows: Record<string, unknown>[], kind: "batter" | "pitcher"): StatRow[] {
  const mapping = kind === "batter" ? BATTER_ALIASES : PITCHER_ALIASES;
  return rows.map((row) => ({ ...aliases(normalized(row), mapping), visiting_home_type: side } as StatRow));
}

function lineupPositions(snapshot: LiveSnapshot) {
  return new Map([
    ...snapshot.away.lineup.items.map((item) => [item.player_id, item.position] as const),
    ...snapshot.home.lineup.items.map((item) => [item.player_id, item.position] as const),
  ]);
}

function liveLog(snapshot: LiveSnapshot): StatRow[] {
  const positions = lineupPositions(snapshot);
  let away = 0;
  let home = 0;
  return snapshot.livelog.map((raw) => {
    const row = normalized(raw);
    const nextAway = Number(row.visiting_score ?? away);
    const nextHome = Number(row.home_score ?? home);
    const scored = nextAway > away || nextHome > home || bool(row.is_score_cnt);
    away = nextAway;
    home = nextHome;
    const content = String(row.content ?? "");
    return {
      ...row,
      defend_station_code: row.defend_station_code
        ?? positions.get(String(row.hitter_acnt ?? "")) ?? null,
      is_score: scored,
      is_ball: bool(row.is_ball) || /壞球/.test(content),
      is_strike: bool(row.is_strike) || /好球|揮空|界外/.test(content),
    };
  });
}

/** 記分板 R/H/E 的 H、E。
 *
 *  官方在隊伍層級就給 `HittingCnt`／`ErrorCnt`，直接採用。舊做法從 hitters 加總，
 *  但 stats 站的打者列**沒有** error 欄位（個人失誤是主站 box 專有），故 E 恆為 0——
 *  實測 2026-A-234 統一官方 ErrorCnt=1、畫面卻印 0。缺值回 null 讓呈現端顯示「—」，
 *  不可回退成 0，否則「未知」會被寫成「沒有失誤」。 */
function teamTotals(side: LiveSide, hitters: StatRow[]) {
  const summedHits = hitters.reduce((sum, row) => sum + Number(row.hits ?? 0), 0);
  return {
    hits: side.hits ?? (hitters.length ? summedHits : null),
    errors: side.errors ?? null,
  };
}

function scoreRows(side: "1" | "2", rows: Record<string, unknown>[]): StatRow[] {
  return rows.map((raw) => {
    const row = normalized(raw);
    return {
      visiting_home_type: side,
      inning_seq: Number(row.seq ?? 0),
      score_cnt: Number(row.score ?? 0),
      // canonical snapshot 只有全場 box totals，沒有逐局 H/E；unknown 不可偽造成第一局數值。
      hitting_cnt: null,
      error_cnt: null,
    };
  });
}

/** 將 Redis canonical snapshot 疊到既有 DB payload；沒有 snapshot 時保持完全向後相容。 */
export function applyLiveSnapshot(response: LiveApiResponse): LiveApiResponse {
  const snapshot = response.live_snapshot;
  if (!snapshot) return response;

  const awayBatting = boxRows("1", snapshot.away.hitters, "batter");
  const homeBatting = boxRows("2", snapshot.home.hitters, "batter");
  const batting = [...awayBatting, ...homeBatting];
  const awayTotals = teamTotals(snapshot.away, awayBatting);
  const homeTotals = teamTotals(snapshot.home, homeBatting);
  // DB 尚未補資料時，決勝改由 snapshot 供；DB 有值一律以 DB 為準（不倒退）。
  const fromDb = Object.keys(response.decisions ?? {}).length > 0;
  const decisions = fromDb ? response.decisions : snapshotDecisions(snapshot);
  // 決勝資訊列讀的是 game.*_pitcher_id + people，與上面的 acnt→代碼 map 是兩條路徑，
  // 兩邊都要接，否則賽後頁面「勝投／敗投／救援／MVP」整列空白。
  const decisionIds = fromDb ? {} : snapshotDecisionIds(snapshot);
  const decisionPeople = fromDb ? {} : snapshotPeople(snapshot);
  // MVP 卡沿用既有的 is_mvp 掃描（box 旗標是主站專有，stats 站不供），這裡以 snapshot
  // 的 MVP acnt 在 box 列上補旗標，讓成績行與本季次數不必另寫一套呈現路徑。
  const mvpId = fromDb ? null : snapshot.decisions?.mvp?.player_id ?? null;
  const markMvp = (rows: StatRow[], key: "hitter_acnt" | "pitcher_acnt") =>
    mvpId ? rows.map((row) => (String(row[key]) === mvpId ? { ...row, is_mvp: true } : row)) : rows;
  const pitching = [
    ...boxRows("1", snapshot.away.pitchers, "pitcher"),
    ...boxRows("2", snapshot.home.pitchers, "pitcher"),
  ];
  const batterAvg = Object.fromEntries(batting.flatMap((row) => {
    const id = String(row.hitter_acnt ?? "");
    return id && row.avg != null ? [[id, Number(row.avg)]] : [];
  }));

  return {
    ...response,
    game: {
      ...(response.game ?? {}),
      year: Number(snapshot.game_id.slice(0, 4)),
      kind_code: snapshot.kind_code,
      game_sno: snapshot.game_sno,
      away_team_code: snapshot.away.team.code,
      away_team_name: snapshot.away.team.name,
      away_score: snapshot.away.score,
      away_hits: awayTotals.hits,
      away_errors: awayTotals.errors,
      home_team_code: snapshot.home.team.code,
      home_team_name: snapshot.home.team.name,
      home_score: snapshot.home.score,
      home_hits: homeTotals.hits,
      home_errors: homeTotals.errors,
      ...decisionIds,
    },
    livelog: liveLog(snapshot),
    batting: markMvp(batting, "hitter_acnt"),
    pitching: markMvp(pitching, "pitcher_acnt"),
    // 官方 MVP.YearlyCount＝本季第 N 次；DB 未補資料時沿用它顯示「本季第 N 次」。
    decision_counts: fromDb || snapshot.decisions?.mvp?.yearly_count == null
      ? response.decision_counts
      : { ...(response.decision_counts as object ?? {}), mvp: snapshot.decisions.mvp.yearly_count },
    scoreboard: [
      ...scoreRows("1", snapshot.away.inning_score),
      ...scoreRows("2", snapshot.home.inning_score),
    ],
    batter_avg: { ...response.batter_avg, ...batterAvg },
    people: { ...response.people, ...decisionPeople },
    decisions,
    // live snapshot 只有 availability/count，沒有逐球座標；不可渲染空好球帶。
    has_tracking: snapshot.phase === "final" ? response.has_tracking : false,
  };
}

/** snapshot 的決勝 → 既有 `decisions` 形狀（acnt → W/L/SV）。無資料回 `{}`。
 *
 *  DB 每日爬蟲補齊前，賽後頁面的決勝一度全空，使「問天」把勝投寫成「無關勝負」。
 *  官方頂層本來就給 WinningPitcher／LoserPitcher／Closer，接上即可。 */
function snapshotDecisions(snapshot: LiveSnapshot): Record<string, "W" | "L" | "SV" | "HLD"> {
  const out: Record<string, "W" | "L" | "SV" | "HLD"> = {};
  const map = [
    ["winning_pitcher", "W"], ["losing_pitcher", "L"], ["closer", "SV"],
  ] as const;
  for (const [key, code] of map) {
    const person = snapshot.decisions?.[key];
    if (person?.player_id) out[person.player_id] = code;
  }
  return out;
}

/** snapshot 決勝 → `game.*_id` 欄位（決勝資訊列與 MVP 卡讀這組）。 */
function snapshotDecisionIds(snapshot: LiveSnapshot): StatRow {
  const d = snapshot.decisions;
  if (!d) return {};
  const out: StatRow = {};
  if (d.winning_pitcher) out.winning_pitcher_id = d.winning_pitcher.player_id;
  if (d.losing_pitcher) out.losing_pitcher_id = d.losing_pitcher.player_id;
  if (d.closer) out.closer_id = d.closer.player_id;
  if (d.mvp) out.mvp_id = d.mvp.player_id;
  return out;
}

/** snapshot 決勝 → `people`（id → 姓名）；決勝資訊列以此顯示姓名。 */
function snapshotPeople(snapshot: LiveSnapshot): Record<string, string> {
  const out: Record<string, string> = {};
  for (const person of Object.values(snapshot.decisions ?? {})) {
    if (person?.player_id && person.name) out[person.player_id] = person.name;
  }
  return out;
}

/** 該場是否可能有逐球追蹤。官方 `skip_trackman` 是權威旗標；未帶（舊 snapshot）回 null
 *  表示未知——未知不得被說成「球場沒有設備」。 */
export const trackmanAvailability = (
  snapshot: LiveSnapshot | null,
): "unavailable" | "expected" | "unknown" => {
  if (!snapshot || snapshot.skip_trackman == null) return "unknown";
  return snapshot.skip_trackman ? "unavailable" : "expected";
};
