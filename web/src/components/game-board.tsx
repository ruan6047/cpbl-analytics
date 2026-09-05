"use client";

import { Fragment, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import Link from "next/link";
import type { StatRow } from "@/lib/client";
import { BasesOuts, ENTITY_LINK, ENTITY_LINK_TEXT, TeamLogo } from "@/components/ui";
import { isCurrentTeam, teamColor, teamPageCode } from "@/lib/teams";
import { PITCH_CALL, PA_KIND } from "@/lib/chart-theme";
import type { WpPoint } from "@/components/win-prob-chart";
import { buildPaGroups, wpSwingLabel, type PaFact } from "@/lib/game-facts";
import { PlayCard, type PlayCardTeams } from "@/components/play-card";
import { buildPaCardVM, paCardHitterName, paCardLabel, paScoreLineOf, type PaCardEvent } from "@/lib/pa-card";
import { indexWpCurve, joinPaSwing } from "@/lib/pa-wp-join";
import { displayWpPctInt } from "@/lib/win-prob-display";
import { PaScoreLine } from "@/components/pa-score-line";
import {
  canShowPostgameConclusions, delayKindLabel, inningLabel, liveScorebarScores, phaseLabel, plateAppearancePitchCountLabel, trackingEmptyMessage,
  type LiveSnapshot,
} from "@/lib/live-game";

type Rec = { w: number; l: number; form: string };
export type TrackRow = {
  main_event_no?: string; main_event_nos?: string[]; pitcher_acnt: string; hitter_acnt: string; inning_seq: number; pitch_cnt: number;
  ball_cnt: number; strike_cnt: number;
  pitch_type_pred: string | null; tagged_pitch_type: string | null;
  rel_speed: number | null; plate_loc_side: number | null; plate_loc_height: number | null;
  pitch_call: string | null;
  exit_speed?: number | null; launch_angle?: number | null; hit_spin_rate?: number | null;
  hit_distance?: number | null; hit_hang_time?: number | null;
};
export type Live = {
  game: StatRow | null;
  scoreboard: StatRow[];
  livelog: StatRow[];
  batting: StatRow[];
  pitching: StatRow[];
  people: Record<string, string>;
  records: Record<string, Rec>;
  batter_avg: Record<string, number>;
  detail: StatRow | null;
  decisions?: Record<string, "W" | "L" | "SV" | "HLD">;
  decision_counts?: {
    win: number | null; loss: number | null; save: number | null; mvp: number | null;
    hold: Record<string, number>;
  } | null;
  has_tracking: boolean;
  tracking: TrackRow[];
  spray?: { hitter_acnt: string; dir: number; dist: number; ev: number | null; la: number | null; result: string }[];
  live_snapshot?: LiveSnapshot | null;
};

const occupied = (v: StatRow[string]) => v !== null && v !== undefined && String(v) !== "";
const num = (v: StatRow[string]) => Number(v) || 0;
const avg3 = (v: number) => v.toFixed(3).replace(/^0/, ""); // .278

// 打席結果 → 2 字標籤 + 分類（hit 安打綠／walk 保送藍／out 出局灰）。優先取 batting_action_name
// （官方 2 字碼 一安/二安/游滾/中飛…），缺值才從 action_name 歸納，避免冗長字串。
type PaKind = "hit" | "walk" | "out";
function todayLabel(r: StatRow): { label: string; kind: PaKind } {
  const kindOf = (label: string): PaKind =>
    /死球|四壞|敬遠/.test(label) ? "walk"
    : (/安|打$/.test(label) && label !== "犧飛" && label !== "雙殺") ? "hit" : "out";
  const ba = String(r.batting_action_name ?? "").trim();
  if (ba) return { label: ba, kind: kindOf(ba) };
  const a = String(r.action_name ?? "");
  const m: [RegExp, string][] = [
    [/全壘打/, "全打"], [/三壘安打/, "三安"], [/二壘安打/, "二安"], [/安打/, "一安"],
    [/三振/, "三振"], [/雙殺/, "雙殺"], [/四壞|故意四壞|裁定四壞/, "四壞"], [/觸身/, "死球"],
    [/犧牲飛|犧牲界外飛/, "犧飛"], [/犧牲短/, "犧觸"], [/失誤/, "失誤"],
    [/野手選擇|野選/, "野選"], [/妨礙打擊/, "妨打"], [/突破僵局/, "上壘"],
    [/飛球接殺|高飛/, "飛球"], [/刺殺|觸殺|踩壘|三呎|妨礙守備/, "滾地"],
  ];
  for (const [re, label] of m) if (re.test(a)) return { label, kind: kindOf(label) };
  const label = a.slice(0, 2);
  return { label, kind: kindOf(label) };
}
const paRbi = (r: StatRow): number => Number(String(r.content ?? "").match(/(\d+)分打點/)?.[1] ?? 0);

// ───────────────────────── 球數燈 ─────────────────────────
function Dots({ n, total, color }: { n: number; total: number; color: string }) {
  return (
    <div className="flex gap-1">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className="h-2.5 w-2.5 rounded-full border"
          style={{ borderColor: i < n ? color : "var(--color-line)", background: i < n ? color : "transparent" }}
        />
      ))}
    </div>
  );
}

// ───────────────────────── 壘包＋出局（緊湊版：菱形品字群 + 出局點）─────────────────────────
// ───────────────────────── 頂部記分條 ─────────────────────────
function ScoreBar({ game, e, records, snapshot, gameSno, plain, interruptionLabel }: {
  game: StatRow; e: StatRow; records: Record<string, Rec>; snapshot: LiveSnapshot | null; gameSno: string;
  /** true＝完賽態總覽：中央格只寫「終場」，不畫 ▲/▼ N 局、壘包與球數（設計定稿 §1.1.1）。 */
  plain: boolean;
  /** 未完成但帶中止比分的保留／延賽場，中央格必須說明比分不是即時或終場。 */
  interruptionLabel: string | null;
}) {
  const ac = String(game.away_team_code ?? "");
  const hc = String(game.home_team_code ?? "");
  const half = String(e.visiting_home_type);
  const ar = records[ac];
  const hr = records[hc];
  const score = liveScorebarScores(game, e);

  // 隊名連結（UX-ENTITY-LINKS3 A 層；§9.3）：gating 只連現役 franchise，歷史／已解散隊
  // 退化純文字。可點範圍與底線的取捨沿用 UX-ENTITY-LINKS2 的結論——**整塊（徽章＋隊名＋
  // 戰績）可點，底線只跟隊名文字**，故外層 `<Link>` 帶 `group`、內層文字套
  // `ENTITY_LINK_TEXT`（該常數本身不自建 `<a>`，不會產生 nested anchor）。
  const side = (code: string, name: StatRow[string], rec: Rec | undefined, alignRight: boolean) => {
    const label = String(name ?? "");
    const box = `flex items-center gap-3 ${alignRight ? "flex-row-reverse text-right" : ""}`;
    // `decorative`：旁邊已有隊名，徽章即裝飾（§9.3；與 `TeamBadge` 的 `decorative={!!name}`
    // 一致）。兩個分支都設，否則同一個視覺會因球隊是否現役而有不同的無障礙行為，
    // 且連結態會唸成「X隊徽 X」。
    const inner = (linked: boolean) => (
      <>
        <TeamLogo code={code} name={label} size={40} decorative />
        <div>
          <div className={`text-base font-bold leading-tight ${linked ? ENTITY_LINK_TEXT : ""}`}>{label}</div>
          <div className="font-mono text-xs text-faint">{rec ? `${rec.w}-${rec.l}` : ""}</div>
        </div>
      </>
    );
    return isCurrentTeam(code) ? (
      <Link href={`/teams/${teamPageCode(code)}`} className={`group ${box}`}>{inner(true)}</Link>
    ) : (
      <div className={box}>{inner(false)}</div>
    );
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-sm">
      <div className="flex h-1.5">
        <div className="flex-1" style={{ background: teamColor(ac) }} />
        <div className="flex-1" style={{ background: teamColor(hc) }} />
      </div>
      <div className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-5 py-2 text-xs">
        {snapshot && <>
          <span className={`font-semibold ${snapshot.phase === "live" ? "text-accent" : "text-ink"}`}>
            {snapshot.phase === "live" && <span className="mr-1 inline-block h-2 w-2 rounded-full bg-accent" aria-hidden="true" />}
            {phaseLabel(snapshot.phase)}
          </span>
          <span className="text-muted">{inningLabel(snapshot, "glyph") ?? "等待賽況"}</span>
        </>}
        <span className="text-faint">{String(game.game_date ?? "")}　賽事編號 {gameSno}　{String(game.venue ?? "")}</span>
        {snapshot && <time className="ml-auto text-faint" dateTime={snapshot.source.fetched_at ?? undefined}>
          最後更新 {snapshot.source.fetched_at
            ? new Date(snapshot.source.fetched_at).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
            : "—"}
        </time>}
        {snapshot && <p className="sr-only" aria-live="polite" aria-atomic="true">
          {phaseLabel(snapshot.phase)}，{String(game.away_team_name)} {score.away} 比 {score.home} {String(game.home_team_name)}
          {inningLabel(snapshot, "text") ? `，${inningLabel(snapshot, "text")}` : ""}
        </p>}
      </div>
      <div className="grid grid-cols-[1fr_auto_auto_auto_1fr] items-center gap-4 px-5 py-4">
        {side(ac, game.away_team_name, ar, false)}
        <div className="font-mono text-4xl font-bold tabular-nums">{score.away}</div>
        {/* 完賽態不掛 px-2：那 16 px 是留給壘包圖與球數燈的呼吸空間，「終場」兩個字
            不需要，而 375 px 下的欄寬已經緊到會把隊名壓成每行一字。 */}
        <div className={`flex flex-col items-center gap-0.5${plain ? "" : " px-2"}`}>
          {plain ? (
            // 完賽態總覽（§1.1.1）：比賽結束後這格若照舊吃當前事件，畫面會陳述一件假的事——
            // `out_cnt` 是**打席前**計數，所以印出來的是「最後一個出局發生之前」的局面，且
            // `<BasesOuts>` 的 aria-label 會被螢幕閱讀器照著念。
            // ⚠️ 不留白：歷史存檔場沒有 snapshot，上方狀態列的「比賽結束」整段不渲染，
            //    留白會讓兩側那兩個大數字看起來像即時比分。
            // ⚠️ 用 text-muted 不用 text-accent：accent 在本記分條是「進行中」的訊號色
            //    （狀態列 phase === "live" 就是 text-accent ＋脈動圓點）。
            <div className="whitespace-nowrap text-xs font-semibold tracking-wide text-muted">終場</div>
          ) : interruptionLabel ? (
            <div className="whitespace-nowrap text-xs font-semibold tracking-wide text-muted">{interruptionLabel}</div>
          ) : (
            <>
              <div className="text-xs font-semibold tracking-wide text-accent">
                {half === "1" ? "▲ TOP" : "▼ BOT"} {num(e.inning_seq)}
              </div>
              {/* 壘包與出局數：canonical 幾何已上抽至 ui.tsx（首頁今日賽事卡共用同一份）。 */}
              <BasesOuts
                bases={{ first: occupied(e.first_base), second: occupied(e.second_base),
                         third: occupied(e.third_base) }}
                outs={num(e.out_cnt)} />
              {/* 球數與出局同處（全站唯一顯示點） */}
              <div className="flex items-center gap-2.5">
                <span className="flex items-center gap-1"><span className="font-mono text-[10px] font-semibold text-muted">B</span>
                  <Dots n={num(e.ball_cnt)} total={3} color={PITCH_CALL.ball} /></span>
                <span className="flex items-center gap-1"><span className="font-mono text-[10px] font-semibold text-muted">S</span>
                  <Dots n={num(e.strike_cnt)} total={2} color={PITCH_CALL.foul} /></span>
              </div>
            </>
          )}
        </div>
        <div className="font-mono text-4xl font-bold tabular-nums">{score.home}</div>
        {side(hc, game.home_team_name, hr, true)}
      </div>
    </div>
  );
}

// ───────────────────────── 目前預期勝率（當前打席，推算）─────────────────────────
function WpBar({ homeWp, homeName, awayName, homeColor, awayColor }: {
  homeWp: number; homeName: string; awayName: string; homeColor: string; awayColor: string;
}) {
  // 顯示夾層：本條顯示的一律是「當前打席開始時」的勝率——依定義不是終場點，故一律夾到
  // [1%, 99%]，比賽終結前不顯示 100%／0%（`lib/win-prob-display.ts`）。
  const h = displayWpPctInt(homeWp);
  const a = 100 - h;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold tabular-nums" style={{ color: awayColor }}>{awayName} {a}%</span>
        <span className="text-[10px] text-faint">目前預期勝率（推算）</span>
        <span className="font-semibold tabular-nums" style={{ color: homeColor }}>{homeName} {h}%</span>
      </div>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        <div style={{ width: `${a}%`, background: awayColor }} />
        <div style={{ width: `${h}%`, background: homeColor }} />
      </div>
    </div>
  );
}

// ───────────────────────── 當前對戰（球數/出局統一在記分條，此處放投打累計）─────────────────────────
type PitcherLive = { outs: number; k: number; h: number };
type TodayPA = { label: string; kind: PaKind; rbi: number; idx: number };

// 打者該場守位字母碼 → 2 字中文（既有 defend_station_code，逐事件精準、全史已填；含換守位/代打）
export const DEFEND_ZH: Record<string, string> = {
  P: "投手", C: "捕手", "1B": "一壘", "2B": "二壘", "3B": "三壘", SS: "游擊",
  LF: "左外", CF: "中外", RF: "右外", DH: "指打", PH: "代打",
};

// 廣播式選手卡（參考轉播下方橫幅）：隊色 logo 方塊 + 背號 + 名 + 右側守位/棒次/數據；
// 打者卡再帶「今日」chip 列（沿用既有配色：安打綠/保送藍/出局灰）。
function Matchup({ e, game, batterAvg, uniforms, pcount, pstats, batterToday, onJump }: {
  e: StatRow; game: StatRow; batterAvg: Record<string, number>;
  uniforms: { bat: Record<string, string>; pit: Record<string, string> };
  pcount: number; pstats: PitcherLive; batterToday: TodayPA[]; onJump: (idx: number) => void;
}) {
  const batAway = String(e.visiting_home_type) === "1";     // 上半＝客隊打擊
  const batCode = String((batAway ? game.away_team_code : game.home_team_code) ?? "");
  const batTeam = String((batAway ? game.away_team_name : game.home_team_name) ?? "");
  const pitCode = String((batAway ? game.home_team_code : game.away_team_code) ?? "");
  const pitTeam = String((batAway ? game.home_team_name : game.away_team_name) ?? "");
  const batNo = uniforms.bat[String(e.hitter_acnt ?? "")];
  const pitNo = uniforms.pit[String(e.pitcher_acnt ?? "")];
  const pos = DEFEND_ZH[String(e.defend_station_code ?? "")];
  const ba = batterAvg[String(e.hitter_acnt ?? "")];
  const ip = `${Math.floor(pstats.outs / 3)}${pstats.outs % 3 ? `.${pstats.outs % 3}` : ""}`;
  return (
    <div className="space-y-2">
      {/* 投手橫幅 */}
      <div className="flex items-center gap-2 rounded-xl border border-line bg-surface px-2.5 py-1.5">
        <TeamLogo code={pitCode} name={pitTeam} size={30} />
        <span className="text-[10px] font-semibold text-muted">投</span>
        {pitNo && <span className="font-mono text-sm font-bold tabular-nums text-ink">{pitNo}</span>}
        <span className="truncate text-base font-bold text-ink">{String(e.pitcher_name ?? "—")}</span>
        <span className="ml-auto shrink-0 font-mono text-[11px] tabular-nums text-faint">{ip}局・{pstats.k}K・被安{pstats.h}・{pcount}球</span>
      </div>
      {/* 打者卡（頭條 + 今日 chip 列）*/}
      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <div className="flex items-center gap-2 px-2.5 py-1.5">
          <TeamLogo code={batCode} name={batTeam} size={30} />
          {batNo && <span className="font-mono text-sm font-bold tabular-nums text-ink">{batNo}</span>}
          <span className="truncate text-base font-bold text-ink">{String(e.hitter_name ?? "—")}</span>
          <span className="ml-auto flex shrink-0 items-center gap-1.5 tabular-nums">
            {pos && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] font-medium text-muted">{pos}</span>}
            <span className="font-mono text-[11px] font-semibold text-ink">AVG {ba !== undefined ? avg3(ba) : "—"}</span>
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1 border-t border-line px-2.5 py-1.5">
          <span className="mr-0.5 text-[10px] font-semibold tracking-wider text-muted">今日</span>
          {batterToday.length ? batterToday.map((pa, i) => {
            const c = pa.kind === "hit" ? PA_KIND.hit : pa.kind === "walk" ? PA_KIND.walk : null;
            return (
              <button key={i} onClick={() => onJump(pa.idx)} title="看該打席"
                className={`rounded px-1.5 py-0.5 text-[11px] font-medium tabular-nums transition-colors hover:brightness-95 ${c ? "" : "bg-surface-2 text-muted"}`}
                style={c ? { background: `color-mix(in srgb, ${c} 12%, transparent)`, color: c } : undefined}>
                {pa.label}{pa.rbi ? `(${pa.rbi})` : ""}
              </button>
            );
          }) : <span className="text-[11px] text-faint">首打席</span>}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────── 局數側欄 ─────────────────────────
type Half = { inning: number; half: string; firstIdx: number };

function buildHalves(log: StatRow[]): Half[] {
  const seen = new Map<string, Half>();
  log.forEach((e, i) => {
    const k = `${e.inning_seq}|${e.visiting_home_type}`;
    if (!seen.has(k)) seen.set(k, { inning: num(e.inning_seq), half: String(e.visiting_home_type), firstIdx: i });
  });
  return [...seen.values()];
}

// 逐局比分 = 局數導覽：每局格子可點（客列=上半、主列=下半）→ 跳到該半局的逐打席。
//
// `highlightSelection=false`＝**純顯示**：仍可點（一次點擊跳到逐打席並定位該半局），但不標
// 示選中局。賽後戰報總覽用這個模式——那裡的記分板是戰報的一部分，標一個選中局會讓讀者
// 以為總覽內容跟著它變；逐打席頁籤裡的記分板才是導航器，標示在那裡才有功能意義
// （2026-08-06 需求方人工審定案）。
function ScoreLine({ sb, game, snapshot, halves, curKey, onSelect, highlightSelection = true }: {
  sb: StatRow[]; game: StatRow; snapshot: LiveSnapshot | null;
  halves: Half[]; curKey: string; onSelect: (h: Half) => void;
  highlightSelection?: boolean;
}) {
  const away = sb.filter((r) => String(r.visiting_home_type) === "1");
  const home = sb.filter((r) => String(r.visiting_home_type) === "2");
  const innings = [...new Set(sb.map((r) => num(r.inning_seq)))].sort((a, b) => a - b);
  const halfBy = new Map(halves.map((h) => [`${h.inning}|${h.half}`, h]));
  const cellScore = (rows: StatRow[], inn: number) => rows.find((r) => num(r.inning_seq) === inn)?.score_cnt ?? "";
  const tot = (rows: StatRow[], key: string) => rows.reduce((s, r) => s + (num(r[key]) || 0), 0);
  // 主隊末局 Ｘ：主隊獲勝時，末局若未打（領先免打）標「Ｘ」，若打了（再見得分）標「{分}Ｘ」。僅主列(half 2)末局。
  // 「有無打末局」以 livelog 半局為準——scoreboard 對未打局仍有 phantom 0 列，不可信；無 livelog(歷史場)則不套用。
  const maxInn = innings.length ? innings[innings.length - 1] : 0;
  const homeWon = canShowPostgameConclusions(
    snapshot, num(game.home_score) + num(game.away_score), game.game_date,
  )
    && num(game.home_score) > num(game.away_score);
  const homeBattedFinal = halfBy.has(`${maxInn}|2`);
  const cellNode = (rows: StatRow[], inn: number, half: string) => {
    const base = String(cellScore(rows, inn));
    if (half === "2" && inn === maxInn && homeWon && halves.length > 0)
      return homeBattedFinal ? <>{base}<span className="text-faint">Ｘ</span></> : <span className="text-faint">Ｘ</span>;
    return base;
  };

  // 隊伍欄的隊名連結（UX-ENTITY-LINKS3 A 層）：此處**沒有**外層 `<Link>`（同列其餘格子是
  // 局數導覽 `<button>`），故文字自建錨點、用 `ENTITY_LINK`；gating 同 §9.3。
  const teamCell = (label: StatRow[string], code: string) => {
    const text = String(label ?? "");
    return isCurrentTeam(code)
      ? <Link href={`/teams/${teamPageCode(code)}`} className={ENTITY_LINK}>{text}</Link>
      : text;
  };

  const row = (label: StatRow[string], code: string, rows: StatRow[], half: string, score: number) => {
    const prefix = half === "1" ? "away" : "home";
    // snapshot 路徑用官方隊伍層級真值；null＝官方未供，顯示「—」而非 0
    // （未知不可寫成「沒有失誤」）。DB 路徑仍由逐局加總。
    const teamTotal = (key: string) => {
      const v = game[`${prefix}_${key}`];
      return v === null || v === undefined ? <span className="text-faint">—</span> : num(v);
    };
    const hits = snapshot ? teamTotal("hits") : tot(rows, "hitting_cnt");
    const errors = snapshot ? teamTotal("errors") : tot(rows, "error_cnt");
    return (
    <tr className="border-t border-line">
      <td className="whitespace-nowrap px-3 py-2 font-sans font-medium">{teamCell(label, code)}</td>
      {innings.map((inn) => {
        const k = `${inn}|${half}`;
        const h = halfBy.get(k);
        const active = highlightSelection && k === curKey;
        return (
          <td key={inn} className="p-0 text-center">
            {h ? (
              <button onClick={() => onSelect(h)}
                title={`看 ${inn} 局${half === "1" ? "上" : "下"}的逐打席`}
                // hover 變體的特異性高於基底 class：選中格若同時掛 `hover:bg-surface-2`，
                // 滑鼠停留時底色會被換成淺灰而文字仍是白色（對比度不足）。故 hover 樣式
                // 只給未選中的格子。
                className={`h-9 w-full px-2.5 transition-colors ${active
                  ? "bg-accent font-semibold text-white"
                  : "text-muted hover:bg-surface-2"}`}>
                {cellNode(rows, inn, half)}
              </button>
            ) : (
              <span className="block px-2.5 py-1.5 text-muted">{cellNode(rows, inn, half)}</span>
            )}
          </td>
        );
      })}
      <td className="px-2.5 py-1.5 text-center font-semibold text-accent">{score}</td>
      <td className="px-2.5 py-1.5 text-center text-muted">{hits}</td>
      <td className="px-2.5 py-1.5 text-center text-muted">{errors}</td>
    </tr>
    );
  };

  return (
    <div id="linescore" className="scroll-mt-16 overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm font-mono tabular-nums">
        <thead className="bg-surface-2 text-muted">
          <tr>
            <th className="px-3 py-2 text-left font-medium">隊伍</th>
            {innings.map((inn) => <th key={inn} className="px-2.5 py-1.5 font-medium">{inn}</th>)}
            <th className="px-2.5 py-1.5 font-medium">R</th>
            <th className="px-2.5 py-1.5 font-medium">H</th>
            <th className="px-2.5 py-1.5 font-medium">E</th>
          </tr>
        </thead>
        <tbody>
          {row(game.away_team_name, String(game.away_team_code ?? ""), away, "1", num(game.away_score))}
          {row(game.home_team_name, String(game.home_team_code ?? ""), home, "2", num(game.home_score))}
        </tbody>
      </table>
    </div>
  );
}

// ───────────────────────── 逐打席賽況（選定半局）─────────────────────────
// UX-GAME-PA1：逐打席改用**與關鍵打席同一個卡片元件**（`components/play-card.tsx`）。
// 需求方上線首日回饋：「逐打席有辦法用類似關鍵打席的 UI 嗎…關鍵打席有一個逐打席缺少的
// 狀態，就是該打席的壘包狀態跟即時勝率。（雖然右側也有即時勝率但跟打席位置有點遠，
// 尤其是手機版上根本沒辦法一眼了解狀況。）」→ 每張卡自帶壘包＋出局＋分差＋該打席的
// 勝率變化與勝率條，手機上不必再對照右側面板。
//
// 折疊：一次只展開一個打席（沿用原本「當前打席自動展開」的語意），**展開才渲染逐球列**
// ——收合的打席不產生任何 DOM，長半局在手機上不需要虛擬化即可流暢。
function PlayByPlay({ log, events, halfKey, idx, setIdx, userAction, facts, wp, teams }: {
  log: StatRow[]; events: number[]; idx: number; setIdx: (i: number) => void;
  /** 目前半局（`{局}|{上下}`）；折疊狀態只在**換半局**時重置。 */
  halfKey: string;
  userAction: MutableRefObject<boolean>;
  /** canonical 打席（打席事實流）；缺席時分組與局面脈絡退回既有近似切法，行為完全不變。 */
  facts?: PaFact[] | null;
  /** 逐打席勝率曲線（與同頁曲線同一份 response）；缺席時卡片不顯示勝率。 */
  wp?: WpPoint[];
  teams: PlayCardTeams;
}) {
  const activeRef = useRef<HTMLLIElement | null>(null);
  // 只在使用者切半局／點打席時才把當前打席捲入視野。
  // 載入時 page 會 setIdx(終局)，但那不是使用者操作（userAction=false），
  // 不可捲動整頁——否則會把頂部記分條捲出視野、linescore 表頭卡進 sticky nav 下。
  // 用 userAction ref 判定而非「跳過首次掛載」：後者會被 StrictMode 雙呼叫 effect 打敗。
  useEffect(() => {
    if (!userAction.current) return;
    userAction.current = false;
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [idx, userAction]);

  // 折疊狀態：null＝依當前 idx 推導（沿用舊行為，含外部跳轉進來的打席）；
  // ""＝使用者手動全收合；其他＝該打席展開。**只在換半局時**回到推導模式。
  //
  // ⚠️ 重置條件不可用 `events` 陣列的識別：live 場每次輪詢都會產生新的 livelog 陣列，
  // 依識別重置會讓使用者手動展開的打席每隔幾秒自己收合（實測撞到過）。半局字串是值比較，
  // 輪詢不會改變它。
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { setOpen(null); }, [halfKey]);

  // 將本半局事件切成打席群組（**換底不換臉**：有 canonical 打席就用它，沒有就逐位元
  // 退回原本的「連續同打者」近似切法，`pa-groups.test.ts` 釘住兩者相同）。
  const groups = buildPaGroups(log as unknown as Parameters<typeof buildPaGroups>[0], events, facts);

  // 逐列的「該事件進帳分數 ＋ 事件後比分」。livelog 的比分欄是**事件後**快照且可能為
  // null（沿用前值），故必須全場前掃一次，不能只讀單列。
  const runningScore = useMemo(() => {
    const out: { runs: number; away: number; home: number }[] = [];
    let away = 0, home = 0;
    for (const ev of log) {
      const preAway = away, preHome = home;
      if (ev.visiting_score != null) away = num(ev.visiting_score);
      if (ev.home_score != null) home = num(ev.home_score);
      const runs = String(ev.visiting_home_type) === "1" ? away - preAway : home - preHome;
      out.push({ runs, away, home });
    }
    return out;
  }, [log]);

  // 曲線索引：整場算一次，逐打席 join（避免每張卡重掃整條曲線）。
  const wpIndex = useMemo(() => indexWpCurve(wp), [wp]);

  const lineBtn = (gi: number, inCard = false) => {
    const ev = log[gi];
    const content = String(ev.content ?? "").split(/[\r\n]/)[0];
    const isScore = Boolean(ev.is_score);
    const isPitch = content.length <= 8;
    const active = gi === idx;
    // 得分事件的敘述文字走**一般字級**（與其他結果行相同）——重要性由清單級的 PaScoreLine 承載。
    // 字級與色調分開算：選中態要能蓋掉色調而不動字級，否則 Tailwind 同屬性衝突的勝負
    // 取決於 CSS 順序而非字串順序（會時靈時不靈）。
    // 選中態＝中性 `ink/10` 淡底，**不用 accent 紅底也不加框線**（需求方回饋）；紅色系在
    // 本站是 down／得分語意，當選取態會語意錯位。淡底而非 `bg-ink` 實底的理由：本列可能
    // 帶得分 chip（accent 色），實底會讓 chip 對比不足。
    const size = isPitch ? "text-xs" : "text-sm";
    const tone = active ? "bg-ink/10 font-medium text-ink"
      : isScore ? "text-accent" : isPitch ? "text-faint" : "text-ink";
    return (
      <button key={gi} onClick={() => setIdx(gi)}
        className={`block w-full scroll-mt-16 rounded px-2 py-0.5 text-left transition-colors hover:bg-surface-2 ${
          inCard ? "pl-3" : "pl-5"} ${size} ${tone}`}>
        {content}
      </button>
    );
  };

  return (
    <div className="order-1 rounded-xl border border-line bg-surface p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-semibold">逐打席</span>
        <span className="text-[10px] text-faint">點打席展開逐球</span>
      </div>
      {/* 內容過長時只捲動本區塊（不動整頁）*/}
      <ul className="max-h-[65vh] space-y-1 overflow-y-auto pr-1">
        {groups.map((g, gk) => {
          if (g.kind === "sub") {
            return <li key={gk} className="pt-0.5">{lineBtn(g.gi)}</li>;
          }
          const key = `pa-${gk}`;
          const firstIdx = g.idxs[0];
          const outcomeIdx = g.idxs[g.idxs.length - 1];
          const active = g.idxs.includes(idx);
          const expanded = open === null ? active : open === key;
          // 該打席的進帳分數與最後一次得分後的比分（打席可能多次得分）
          const scoringIdxs = g.idxs.filter((gi) => log[gi].is_score && runningScore[gi]?.runs > 0);
          const runs = scoringIdxs.reduce((sum, gi) => sum + (runningScore[gi]?.runs ?? 0), 0);
          const paScore = scoringIdxs.length
            ? runningScore[scoringIdxs[scoringIdxs.length - 1]] : null;
          const vm = buildPaCardVM(
            g.fact, log[firstIdx] as PaCardEvent, log[outcomeIdx] as PaCardEvent,
            firstIdx > 0 ? runningScore[firstIdx - 1] : null,
            paScore ? { away: paScore.away, home: paScore.home } : null, runs || null);
          // 突破僵局的跑者佈局列是**非打席**（canonical `non_pa`）：它確實會推動勝率，
          // 但那不是任何打者造成的，掛上勝率標示等於把佈局規則的效果歸因給該打席。
          // 與 `/recap-wp` 對 non_pa 的處理一致（`non_pa_context`，WP 欄不可用）。
          const isNonPa = g.fact?.state === "non_pa";
          const swing = isNonPa ? null
            : joinPaSwing(wpIndex, log[firstIdx]?.main_event_no as string,
              log[outcomeIdx]?.main_event_no as string);
          const swingLabel = wpSwingLabel(swing?.delta, teams.homeName, teams.awayName);
          const label = paCardLabel(vm, paCardHitterName(g.fact, g.name),
            swingLabel ? `，勝率推向${swingLabel.team} ${swingLabel.pt} 個百分點` : "");
          // 得分打席的比分列：清單級（與「更換選手」列同層級），排在該打席卡之後。
          const scoreLine = paScoreLineOf(vm);
          return (
            <Fragment key={key}>
              <li ref={active ? activeRef : undefined}>
                <PlayCard
                  variant="pbp"
                  inning={vm.inning} half={vm.half}
                  outsBefore={vm.outsBefore} basesBefore={vm.basesBefore}
                  margin={vm.margin} garbageTime={vm.garbageTime}
                  hitterId={g.fact?.hitter?.player_id ?? g.hitter}
                  hitterName={paCardHitterName(g.fact, g.name)}
                  pitcherName={g.pitcher} resultAction={vm.resultAction}
                  pitchCountLabel={g.idxs.length > 1
                    ? plateAppearancePitchCountLabel(g.idxs.length) : null}
                  deltaRe24={vm.deltaRe24}
                  wp={swing}
                  teams={teams}
                  ariaLabel={label}
                  active={active}
                  expanded={expanded}
                  onActivate={() => {
                    if (expanded) { setOpen(""); return; }
                    setOpen(key);
                    setIdx(outcomeIdx);
                  }}
                >
                  <div className="space-y-0.5">
                    {g.idxs.map((gi) => lineBtn(gi, true))}
                  </div>
                </PlayCard>
              </li>
              {scoreLine && (
                <li className="pt-0.5">
                  <PaScoreLine {...scoreLine}
                    awayName={teams.awayName} homeName={teams.homeName} className="ml-3" />
                </li>
              )}
            </Fragment>
          );
        })}
      </ul>
    </div>
  );
}

// ───────────────────────── 好球帶（逐球進壘）─────────────────────────
// tagged_pitch_type 是官網分類；只有整個 canonical PA 都具模型結果，才可顯示推算球種。
const TAGGED_ZH: Record<string, string> = { fastball: "速球", breakingball: "變化球", offspeed: "變速" };
const pitchZh = (pitch: TrackRow, useModel: boolean) =>
  (useModel ? pitch.pitch_type_pred : null) || (pitch.tagged_pitch_type && TAGGED_ZH[pitch.tagged_pitch_type]) || "—";
// 進壘判定 → 顏色（紅=好球/出局 綠=壞球 藍=擊出）
function callStyle(call: string | null): { color: string; label: string } {
  const c = call || "";
  if (c === "BallCalled") return { color: PITCH_CALL.ball, label: "壞球" };
  if (c === "InPlay") return { color: PITCH_CALL.inplay, label: "擊出" };
  if (c.startsWith("Foul")) return { color: PITCH_CALL.foul, label: "界外" };
  if (c.startsWith("Strike")) return { color: "var(--color-accent)", label: c === "StrikeSwinging" ? "揮空" : "好球" };
  return { color: "var(--color-faint)", label: c || "—" };
}
// 真實座標(公尺) → SVG。視窗 side∈[-0.6,0.6]、height∈[0.2,1.5]
const SX = (s: number) => ((s + 0.6) / 1.2) * 200;
const SY = (h: number) => 200 - ((h - 0.2) / 1.3) * 200;
const ZONE = { l: -0.23, r: 0.23, b: 0.46, t: 1.05 }; // 名義好球帶

function StrikeZone({ pitches }: { pitches: TrackRow[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  // PA 來源鎖定：任一球沒有模型結果就整個 PA 降階官網分類，禁止混用兩種來源。
  const useModel = pitches.length > 0 && pitches.every((pitch) => Boolean(pitch.pitch_type_pred));
  const hasLocations = pitches.some((pitch) => pitch.plate_loc_side != null && pitch.plate_loc_height != null);
  const zl = SX(ZONE.l), zr = SX(ZONE.r), zt = SY(ZONE.t), zb = SY(ZONE.b);
  const gx1 = zl + (zr - zl) / 3, gx2 = zl + (2 * (zr - zl)) / 3;
  const gy1 = zt + (zb - zt) / 3, gy2 = zt + (2 * (zb - zt)) / 3;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2.5">
      <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
        <span className="font-semibold">本打席逐球追蹤</span>
        <span className="text-muted">球種：{useModel ? "推算" : "官網分類"}</span>
      </div>
      <div className="flex gap-3">
        {hasLocations && <svg viewBox="0 0 200 200" className="h-36 w-36 shrink-0" aria-label="本打席好球帶">
          <rect x={zl} y={zt} width={zr - zl} height={zb - zt} fill="var(--color-surface-2)" stroke="var(--color-faint)" strokeWidth={1.5} />
          <line x1={gx1} y1={zt} x2={gx1} y2={zb} stroke="var(--color-line)" />
          <line x1={gx2} y1={zt} x2={gx2} y2={zb} stroke="var(--color-line)" />
          <line x1={zl} y1={gy1} x2={zr} y2={gy1} stroke="var(--color-line)" />
          <line x1={zl} y1={gy2} x2={zr} y2={gy2} stroke="var(--color-line)" />
          {/* 本壘板示意 */}
          <polygon points={`${SX(-0.22)},196 ${SX(0.22)},196 ${SX(0.22)},191 ${SX(0)},186 ${SX(-0.22)},191`} fill="var(--color-faint)" opacity={0.5} />
          {pitches.map((p, i) => {
            if (p.plate_loc_side == null || p.plate_loc_height == null) return null;
            const { color } = callStyle(p.pitch_call);
            return (
              <g key={i}>
                <circle cx={SX(p.plate_loc_side)} cy={SY(p.plate_loc_height)} r={9} fill={color} opacity={0.9} />
                <text x={SX(p.plate_loc_side)} y={SY(p.plate_loc_height) + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} className="fill-white">{i + 1}</text>
              </g>
            );
          })}
        </svg>}
        <ol className="min-w-0 flex-1 space-y-0.5 text-xs">
          {pitches.map((p, i) => {
            const { color, label } = callStyle(p.pitch_call);
            return (
              <li key={i} className="font-mono tabular-nums">
              <div className="flex items-center gap-1.5 whitespace-nowrap">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded text-[10px] font-bold text-white" style={{ background: color }}>{i + 1}</span>
                <span className="w-8 shrink-0 font-sans text-muted">{label}</span>
                <span className="font-sans text-ink">{pitchZh(p, useModel)}</span>
                {p.rel_speed != null && <span className="text-faint">{Math.round(p.rel_speed)} km/h</span>}
                {label === "擊出" && <button type="button" className="ml-auto inline-flex min-h-11 min-w-11 items-center justify-center text-accent underline" onClick={() => setExpanded(expanded === i ? null : i)} aria-expanded={expanded === i} aria-controls={`hit-data-${i}`} aria-label={`${i + 1} 號擊出球數據`}>數據</button>}
              </div>
              {expanded === i && <div id={`hit-data-${i}`} className="grid grid-cols-2 gap-x-2 py-1 text-faint">
                {p.exit_speed != null && <span>初速 {Math.round(p.exit_speed)} km/h</span>}{p.launch_angle != null && <span>仰角 {Math.round(p.launch_angle)}°</span>}
                {p.hit_distance != null && <span>距離 {Math.round(p.hit_distance)} m</span>}{p.hit_hang_time != null && <span>滯空 {p.hit_hang_time.toFixed(1)} s</span>}
                {p.hit_spin_rate != null && <span>轉速 {Math.round(p.hit_spin_rate)} rpm</span>}
              </div>}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

// ───────────────────────── 主板 ─────────────────────────
export default function GameBoard({ data, idx, setIdx, view = "pbp", onNavigate, wp, gameSno, tabs,
                                    facts, highlightSelection }: {
  data: Live;
  idx: number; setIdx: (i: number) => void;
  wp?: WpPoint[];                // 逐打席勝率（顯示當前打席的目前預期勝率）
  view?: "overview" | "pbp";     // overview=總覽（隱藏逐打席操作區）；pbp=逐打席
  onNavigate?: () => void;       // 使用者選打席/選局時通知父層（總覽→切逐打席）
  gameSno: string;
  /** 頁面唯一主頁籤：必須位於 Hero 記分條之後。 */
  tabs?: ReactNode;
  /** canonical 打席（打席事實流）；缺席時逐打席分組退回既有近似切法。 */
  facts?: PaFact[] | null;
  /** false＝記分板純顯示（不標選中局）；點擊仍會跳到該半局的逐打席。 */
  highlightSelection?: boolean;
}) {
  const log = data.livelog;
  const game = data.game!;
  const total = log.length;

  // 使用者主動切換（點打席/選半局）時才允許把當前打席捲入視野；
  // 區分 page 載入時程式化的 setIdx(終局)——後者不得捲動整頁。
  const userAction = useRef(false);
  const selectIdx = (i: number) => { userAction.current = true; setIdx(i); onNavigate?.(); };

  const e = log[idx] ?? log[total - 1];
  const halves = useMemo(() => buildHalves(log), [log]);

  // 完賽態頁首記分條只呈現終場比分（設計定稿 §1.1.1；#160）。條件與頁面層
  // `game-live-page.tsx:212` 的 `plainLinescore` 逐字相同，刻意不另立第二套完賽語意。
  // ⚠️ 不可簡化成 `data.live_snapshot?.phase === "final"`：`canShowPostgameConclusions` 的
  //    定義是 `scoreTotal > 0 && (snapshot === null || phase === "final")`，歷史存檔場
  //    snapshot 為 null 時**兩者分歧**（前者 true、後者 false）。生產實測 2024 A/100 與
  //    A/200 皆無 snapshot 卻有真實比分，整個歷史存檔都走那一支——寫成 phase 判定等於
  //    對絕大多數場次完全失效。
  // ⚠️ `view === "overview"` 不可省：ScoreBar 渲染於主頁籤（`tabs` prop）之前，賽後戰報
  //    與逐打席**共用同一個元素**，而逐打席要的正是選中打席的局面。
  // ⚠️ 本註解刻意不寫出 tabs 的 JSX 字面：`lib/live-game.test.ts:111` 以
  //    `indexOf("<ScoreBar") < indexOf(...)` 的**原始碼字串**位置守 Hero 在頁籤上方，
  //    在此處提早出現該字面會讓那條守衛誤判。
  const plainScorebar = view === "overview"
    && canShowPostgameConclusions(data.live_snapshot ?? null,
                                  num(game.away_score) + num(game.home_score), game.game_date);
  const interruptionLabel = plainScorebar ? null : delayKindLabel(game.delay_kind);

  // 目前選定的半局（由所選事件決定）+ 該半局事件索引
  const curKey = e ? `${num(e.inning_seq)}|${String(e.visiting_home_type)}` : "";
  const curEvents = useMemo(() => {
    const out: number[] = [];
    log.forEach((r, i) => { if (`${num(r.inning_seq)}|${String(r.visiting_home_type)}` === curKey) out.push(i); });
    return out;
  }, [log, curKey]);

  // 投手本場累積投球數（至目前指標）
  const pcount = useMemo(() => {
    if (!e) return 0;
    let c = 0;
    for (let k = 0; k <= idx && k < total; k++) {
      const r = log[k];
      if (r.pitcher_acnt === e.pitcher_acnt && (r.is_ball || r.is_strike)) c++;
    }
    return c;
  }, [log, idx, total, e]);

  // 投打即時累計（至 idx，排除進行中打席）：
  // 投手局數用「出局宣告歸屬法」——content『N人出局』為半局內累計，宣告出現在造成出局
  // 的那一列、該列 pitcher_acnt 即當時投手，換投中途歸屬亦正確（與後端 sabr 同構）。
  // K/被安打以打席末事件的 action_name（打席層級傳播值）計。
  const liveStats = useMemo(() => {
    const outsBy: Record<string, number> = {};
    const kBy: Record<string, number> = {};
    const hBy: Record<string, number> = {};
    const paResults: { hitter: string; label: string; kind: PaKind; rbi: number; idx: number }[] = [];
    let curHalf = "", prevAnn = 0;
    let paFinal: StatRow | null = null, paFinalIdx = -1;
    const flush = () => {
      if (!paFinal) return;
      const p = String(paFinal.pitcher_acnt ?? "");
      const a = String(paFinal.action_name ?? "").trim();
      if (a.includes("三振")) kBy[p] = (kBy[p] ?? 0) + 1;
      if (/安打|全壘打/.test(a)) hBy[p] = (hBy[p] ?? 0) + 1;
      if (a) {
        const { label, kind } = todayLabel(paFinal);
        paResults.push({ hitter: String(paFinal.hitter_acnt), label, kind, rbi: paRbi(paFinal), idx: paFinalIdx });
      }
      paFinal = null;
    };
    for (let i = 0; i <= idx && i < total; i++) {
      const r = log[i];
      const hk = `${r.inning_seq}|${r.visiting_home_type}`;
      if (hk !== curHalf) { flush(); curHalf = hk; prevAnn = 0; }
      if (r.is_change_player || !r.hitter_acnt) continue;
      if (paFinal && String((paFinal as StatRow).hitter_acnt) !== String(r.hitter_acnt)) flush();
      paFinal = r; paFinalIdx = i;
      for (const m of String(r.content ?? "").matchAll(/(\d)人出局/g)) {
        const ann = Number(m[1]);
        if (ann > prevAnn) {
          const p = String(r.pitcher_acnt ?? "");
          outsBy[p] = (outsBy[p] ?? 0) + (ann - prevAnn);
          prevAnn = ann;
        }
      }
    }
    // 進行中打席不 flush（「今日之前」與投手累計都不含未完成打席）
    return { outsBy, kBy, hBy, paResults };
  }, [log, idx, total]);

  const pstats = useMemo(() => {
    const p = String(e?.pitcher_acnt ?? "");
    return { outs: liveStats.outsBy[p] ?? 0, k: liveStats.kBy[p] ?? 0, h: liveStats.hBy[p] ?? 0 };
  }, [liveStats, e]);
  const batterToday = useMemo(() => {
    const h = String(e?.hitter_acnt ?? "");
    return liveStats.paResults.filter((r) => r.hitter === h);
  }, [liveStats, e]);
  // 背號 map（自 box）：acnt → 背號
  const uniforms = useMemo(() => ({
    bat: Object.fromEntries(data.batting.map((r) => [String(r.hitter_acnt), String(r.uniform_no ?? "")])),
    pit: Object.fromEntries(data.pitching.map((r) => [String(r.pitcher_acnt), String(r.uniform_no ?? "")])),
  }), [data.batting, data.pitching]);

  // 當前打席的目前預期勝率：wp 為每打席一點（evt=打席首事件號），取 evt ≤ 當前事件號
  // 的最後一點＝當前打席進場時的 WP（主隊視角）。
  const curHomeWp = useMemo(() => {
    if (!e || !wp?.length) return null;
    const cur = Number(e.main_event_no);
    let best: number | null = null, bestEvt = -1;
    for (const p of wp) {
      if (p.evt == null) continue;
      const ne = Number(p.evt);
      if (ne <= cur && ne > bestEvt) { bestEvt = ne; best = p.wp; }
    }
    return best;
  }, [wp, e]);

  // live 與賽後都只以官方事件鍵／canonical PA mapping 比對；不得退回同局投打三鍵猜測。
  const paPitches = useMemo(() => {
    if (!e || !e.pitcher_acnt || !e.hitter_acnt) return [];
    const eventNo = String(e.main_event_no ?? "");
    return data.tracking
      .filter((p) => p.main_event_nos?.includes(eventNo) ?? p.main_event_no === eventNo)
      .sort((a, b) => a.pitch_cnt - b.pitch_cnt);
  }, [data.tracking, e]);

  // 隊名與隊色：逐打席卡與勝率條共用（隊色＝身分，走 lib/teams.ts）
  const boardTeams: PlayCardTeams = {
    homeName: String(game.home_team_name ?? ""), awayName: String(game.away_team_name ?? ""),
    homeColor: teamColor(String(game.home_team_code ?? "")),
    awayColor: teamColor(String(game.away_team_code ?? "")),
  };

  if (!e) return <p className="text-sm text-faint">無賽況資料。</p>;

  return (
    <div className="space-y-4">
      <ScoreBar game={game} e={e} records={data.records} snapshot={data.live_snapshot ?? null} gameSno={gameSno}
        plain={plainScorebar} interruptionLabel={interruptionLabel} />

      {tabs}

      <ScoreLine sb={data.scoreboard} game={game} snapshot={data.live_snapshot ?? null}
        halves={halves} curKey={curKey} onSelect={(h) => selectIdx(h.firstIdx)}
        highlightSelection={highlightSelection} />

      {view === "pbp" && (
      <div id="pbp-section" className="grid scroll-mt-16 gap-4 lg:grid-cols-[1fr_360px]">
        {/* 左：逐打席賽況（選定半局）*/}
        <PlayByPlay log={log} events={curEvents} halfKey={curKey} idx={idx} setIdx={selectIdx}
          userAction={userAction} facts={facts} wp={wp} teams={boardTeams} />

        {/* 右：當前對戰 + 好球帶（sticky）。
            窄螢幕原本排到清單**上方**（order-1），理由是「避免長局把當前打席/WP/好球帶
            擠到超長清單下方看不到」——UX-GAME-PA1 後這個理由消失了：每張打席卡自帶壘包、
            出局、分差與該打席的勝率變化＋勝率條，清單本身即可一眼判讀，不必再上滑對照。
            需求方原話「手機版上根本沒辦法一眼了解狀況」指的正是這段距離，故窄螢幕改為
            清單優先（order-2），桌面維持右側不變（lg:order-2）。 */}
        <div className="order-2 space-y-2 lg:sticky lg:top-3 lg:self-start">
          {curHomeWp != null && (
            <WpBar homeWp={curHomeWp}
              homeName={String(game.home_team_name ?? "")} awayName={String(game.away_team_name ?? "")}
              homeColor={teamColor(String(game.home_team_code ?? ""))}
              awayColor={teamColor(String(game.away_team_code ?? ""))} />
          )}
          <Matchup e={e} game={game} batterAvg={data.batter_avg} uniforms={uniforms} pcount={pcount}
            pstats={pstats} batterToday={batterToday} onJump={selectIdx} />
          {data.has_tracking ? (
            paPitches.length > 0 ? (
              <StrikeZone pitches={paPitches} />
            ) : (
              <div className="rounded-xl border border-dashed border-line bg-surface-2/50 px-4 py-3 text-xs text-muted">
                此事件無對應逐球進壘資料（換人/局間或來源未收錄該打席）。
              </div>
            )
          ) : (
            <div className="rounded-xl border border-dashed border-line bg-surface-2/50 px-4 py-3 text-xs text-muted">
              {trackingEmptyMessage(data.live_snapshot ?? null, "暫不呈現好球帶、球種與球速")}
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
