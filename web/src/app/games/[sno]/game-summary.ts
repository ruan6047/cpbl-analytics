// UX-GAME-RECAP1 重構：把原本內嵌在 `game-live-page.tsx`（721 行）的**純計算**抽出。
//
// 本檔零 JSX、零 hook、零請求——只吃 `Live` payload 回傳資料結構，故可單元測試，
// 也讓頁面殼回到「載入 + 三態路由」的職責。行為與抽出前**逐項等價**（只是搬家）。
//
// 產出三組：
//   * `buildHighlights`：本場焦點（賽事級 → 稀有成就 → 常見；含已量化的球迷用語）
//   * `buildDecisions`：決勝資訊（先發／勝敗投／中繼／救援／致勝打點）與 MVP 成績行
//   * `buildGameInfo`：賽事資訊（天氣／觀眾／時長／延賽備註）——裁判列含連結，留在頁面層
//
// ⚠️ 球迷用語（魯閣／中計／煮粥／問天／劇場…）**只用於賽況頁焦點區**，其觸發條件早已
// 量化；recap 的正式文案（結論行事實句）**禁用暱稱**，由後端 `pa_facts` 負責。

import type { Live } from "@/components/game-board";
import type { StatRow } from "@/lib/client";
import { fanNick, teamShort } from "@/lib/teams";
import { num, type Highlight } from "@/lib/game-highlights";

// 本場焦點（buildHighlights）與共用小工具已搬到 `@/lib/game-highlights`（#288 WP-K3，逐字搬移）；
// 這裡 re-export，既有 import 路徑（game-live-page.tsx、recap/*）不變。
export { buildHighlights, num, type Highlight } from "@/lib/game-highlights";

export type DecItem = { label: string; value: string; note?: string; pid?: string };
export type MvpLine = { name: string; line: string; count?: number | null; pid?: string };

const ipTxt = (r: StatRow) => {
  const whole = num(r.inning_pitched_cnt);
  const third = num(r.inning_pitched_div3);
  return third ? `${whole}.${third}` : String(whole);
};

/** 決勝資訊 ＋ MVP 成績行（box score 慣例「本季第 N 勝/敗/救援/中繼/次 MVP」，含本場）。 */
export function buildDecisions(data: Live, completed: boolean): {
  items: DecItem[]; mvp: MvpLine | null;
} {
  const g = data.game;
  if (!g) return { items: [], mvp: null };
  const dc = data.decision_counts;
  const ppl = data.people;

  // MVP 的 box 成績行：優先用 `is_mvp` 旗標；旗標缺席時退回以 `game.mvp_id` 對位。
  //
  // 為什麼需要退路：`is_mvp` 是主站 box 專有旗標，而 `applyLiveSnapshot` 在有 live
  // snapshot 時會把 box 陣列換成 stats 站的列，且**只在 DB 尚無決勝資料時**才回補旗標
  // （`fromDb` 分支）。於是「DB 已有決勝 ＋ snapshot 仍在 48h TTL 內」的窗口裡，旗標
  // 兩邊都沒有，MVP 的成績行與本季次數會整塊消失。以 mvp_id 對位可涵蓋兩條路徑。
  const mvpId = String(g.mvp_id ?? "");
  const mvpBat = data.batting.find((r) => r.is_mvp)
    ?? (mvpId ? data.batting.find((r) => String(r.hitter_acnt) === mvpId) : undefined);
  const mvpPit = data.pitching.find((r) => r.is_mvp)
    ?? (mvpId ? data.pitching.find((r) => String(r.pitcher_acnt) === mvpId) : undefined);
  let mvp: MvpLine | null = null;
  if (mvpBat) {
    const parts = [`${num(mvpBat.at_bats)} 打數 ${num(mvpBat.hits)} 安`];
    if (num(mvpBat.home_runs)) parts.push(`${mvpBat.home_runs} 轟`);
    if (num(mvpBat.rbi)) parts.push(`${mvpBat.rbi} 打點`);
    if (num(mvpBat.runs)) parts.push(`${mvpBat.runs} 得分`);
    if (num(mvpBat.sb)) parts.push(`${mvpBat.sb} 盜`);
    mvp = { name: String(mvpBat.hitter_name ?? ""), line: parts.join("・"),
            count: dc?.mvp, pid: String(mvpBat.hitter_acnt ?? "") };
  } else if (mvpPit) {
    const parts = [`${ipTxt(mvpPit)} 局`, `${num(mvpPit.so)}K`, `失 ${num(mvpPit.runs)} 分`];
    if (num(mvpPit.bb) === 0) parts.push("無保送");
    mvp = { name: String(mvpPit.pitcher_name ?? ""), line: parts.join("・"),
            count: dc?.mvp, pid: String(mvpPit.pitcher_acnt ?? "") };
  }

  const holdAcnts = Object.entries(data.decisions ?? {})
    .filter(([, v]) => v === "HLD").map(([acnt]) => acnt);
  const holdNames = holdAcnts
    .map((acnt) => data.pitching.find((r) => String(r.pitcher_acnt) === acnt)?.pitcher_name)
    .filter(Boolean).join("、");
  // 中繼次數：單一中繼投手才在其後標「第 N 中繼」；多人時名字已擠，省略避免爆格
  const holdNote = holdAcnts.length === 1 && dc?.hold?.[holdAcnts[0]]
    ? `第${dc.hold[holdAcnts[0]]}中繼` : undefined;
  // 致勝打點（官方 box gw_rbi 旗標；每場勝方通常一人，罕見多人以「、」併列）
  const gwRbiNames = data.batting
    .filter((r) => num(r.gw_rbi) > 0)
    .map((r) => String(r.hitter_name ?? ""))
    .filter(Boolean).join("、");

  const starterItems: DecItem[] = ([
    { label: "先發(客)", value: ppl[String(g.away_starter_id)], pid: String(g.away_starter_id ?? "") },
    { label: "先發(主)", value: ppl[String(g.home_starter_id)], pid: String(g.home_starter_id ?? "") },
  ] as DecItem[]).filter((d) => d.value);
  const resultItems: DecItem[] = ([
    { label: "勝投", value: ppl[String(g.winning_pitcher_id)], note: dc?.win ? `第${dc.win}勝` : undefined, pid: String(g.winning_pitcher_id ?? "") },
    { label: "敗投", value: ppl[String(g.losing_pitcher_id)], note: dc?.loss ? `第${dc.loss}敗` : undefined, pid: String(g.losing_pitcher_id ?? "") },
    { label: "救援", value: ppl[String(g.closer_id)], note: dc?.save ? `第${dc.save}救援` : undefined, pid: String(g.closer_id ?? "") },
    { label: "中繼", value: holdNames || undefined, note: holdNote },   // HLD 為官方 relief_point（中繼點）
    { label: "致勝打點", value: gwRbiNames || undefined },
  ] as DecItem[]).filter((d) => d.value);

  return {
    items: completed ? [...starterItems, ...resultItems] : starterItems,
    mvp: completed ? mvp : null,
  };
}

/** 延賽／保留說明文字；無延賽回空字串。 */
export function delayNoteOf(g: StatRow): string {
  if (!g.delay_kind) return "";
  const md = (s: unknown) => { const p = String(s ?? "").slice(5).split("-"); return p.length === 2 ? `${+p[0]}/${+p[1]}` : ""; };
  const orig = md(g.orig_date), played = md(g.game_date);
  const done = num(g.present_status) === 1 && (num(g.home_score) + num(g.away_score)) > 0;
  return g.delay_kind === "保留"
    ? `原 ${orig} 開賽${done ? `，${played} 續賽完成` : "，擇期續賽"}`
    : `原定 ${orig}${done && played !== orig ? `，${played} 補賽` : "，擇期補賽"}`;
}

/** 賽事資訊的「概況」列（天氣／觀眾／時長）；無資料回 null。 */
export function summaryLine(detail: StatRow | null): string | null {
  if (!detail) return null;
  const parts: string[] = [];
  const wx = String(detail.weather_desc ?? "");
  if (wx) {
    const cond = wx.split("。")[0] ?? "";
    const temp = wx.match(/攝氏(\d+)至(\d+)度/);
    // #218 emoji 處置：天氣改純文字（官方描述原句＋溫度），不配圖示。
    parts.push(`${cond}${temp ? ` ${temp[1]}–${temp[2]}°C` : ""}`);
  }
  if (detail.attendance) parts.push(`觀眾 ${Number(detail.attendance).toLocaleString()} 人`);
  if (detail.game_time) parts.push(`時長 ${String(detail.game_time)}`);
  return parts.length ? parts.join("・") : null;
}

/** 生涯里程碑 → 帶隊色的 chip 清單（球員名 → visiting_home_type → 隊碼）。 */
export function buildMilestoneChips(
  data: Live, milestones: { player: string; text: string }[],
): Highlight[] {
  const g = data.game;
  const nameTeam = new Map<string, string>();
  const teamOf = (vht: unknown) =>
    String(vht) === "1" ? String(g?.away_team_code ?? "") : String(g?.home_team_code ?? "");
  for (const r of data.pitching) {
    const nm = String(r.pitcher_name ?? "");
    if (nm) nameTeam.set(nm, teamOf(r.visiting_home_type));
  }
  for (const r of data.batting) {
    const nm = String(r.hitter_name ?? "");
    if (nm) nameTeam.set(nm, teamOf(r.visiting_home_type));
  }
  return milestones.map((m) => ({
    text: `${m.player} ${m.text}`,
    team: nameTeam.get(m.player) ?? null,
  }));
}
