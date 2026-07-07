"use client";

import { useEffect, useMemo, useRef, type MutableRefObject } from "react";
import type { StatRow } from "@/lib/client";
import { TeamLogo } from "@/components/ui";
import { teamColor } from "@/lib/teams";

type Rec = { w: number; l: number; form: string };
export type TrackRow = {
  pitcher_acnt: string; hitter_acnt: string; inning_seq: number; pitch_cnt: number;
  ball_cnt: number; strike_cnt: number; auto_pitch_type: string | null;
  rel_speed: number | null; plate_loc_side: number | null; plate_loc_height: number | null;
  pitch_call: string | null;
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
  has_tracking: boolean;
  tracking: TrackRow[];
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
function BasesOuts({ b1, b2, b3, outs, size = 52 }: {
  b1: boolean; b2: boolean; b3: boolean; outs: number; size?: number;
}) {
  // 品字排列：二壘上中、三壘左下、一壘右下，菱形緊靠；下方兩顆出局圓點
  const base = (cx: number, cy: number, on: boolean) => (
    <rect
      x={cx - 15} y={cy - 15} width={30} height={30}
      transform={`rotate(45 ${cx} ${cy})`} rx={4}
      fill={on ? "var(--color-accent)" : "var(--color-line)"}
      stroke="var(--color-surface)" strokeWidth={3}
    />
  );
  const o = Math.min(outs, 2);
  return (
    <svg viewBox="0 0 120 116" width={size} height={size * 116 / 120} aria-label={`壘上${[b1 && "一壘", b2 && "二壘", b3 && "三壘"].filter(Boolean).join("、") || "無人"}，${o} 出局`}>
      {base(60, 26, b2)}
      {base(36, 50, b3)}
      {base(84, 50, b1)}
      <circle cx={48} cy={92} r={9} fill={o >= 1 ? "var(--color-accent)" : "var(--color-line)"} />
      <circle cx={72} cy={92} r={9} fill={o >= 2 ? "var(--color-accent)" : "var(--color-line)"} />
    </svg>
  );
}

// ───────────────────────── 頂部記分條 ─────────────────────────
function ScoreBar({ game, e, records }: { game: StatRow; e: StatRow; records: Record<string, Rec> }) {
  const ac = String(game.away_team_code ?? "");
  const hc = String(game.home_team_code ?? "");
  const half = String(e.visiting_home_type);
  const ar = records[ac];
  const hr = records[hc];

  const side = (code: string, name: StatRow[string], rec: Rec | undefined, alignRight: boolean) => (
    <div className={`flex items-center gap-3 ${alignRight ? "flex-row-reverse text-right" : ""}`}>
      <TeamLogo code={code} name={String(name ?? "")} size={40} />
      <div>
        <div className="text-base font-bold leading-tight">{String(name ?? "")}</div>
        <div className="font-mono text-xs text-faint">{rec ? `${rec.w}-${rec.l}` : ""}</div>
      </div>
    </div>
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-sm">
      <div className="flex h-1.5">
        <div className="flex-1" style={{ background: teamColor(ac) }} />
        <div className="flex-1" style={{ background: teamColor(hc) }} />
      </div>
      <div className="grid grid-cols-[1fr_auto_auto_auto_1fr] items-center gap-4 px-5 py-4">
        {side(ac, game.away_team_name, ar, false)}
        <div className="font-mono text-4xl font-bold tabular-nums">{num(e.visiting_score)}</div>
        <div className="flex flex-col items-center gap-0.5 px-2">
          <div className="text-xs font-semibold tracking-wide text-accent">
            {half === "1" ? "▲ TOP" : "▼ BOT"} {num(e.inning_seq)}
          </div>
          <BasesOuts b1={occupied(e.first_base)} b2={occupied(e.second_base)}
            b3={occupied(e.third_base)} outs={num(e.out_cnt)} />
          {/* 球數與出局同處（全站唯一顯示點） */}
          <div className="flex items-center gap-2.5">
            <span className="flex items-center gap-1"><span className="font-mono text-[10px] font-semibold text-muted">B</span>
              <Dots n={num(e.ball_cnt)} total={3} color="#16a34a" /></span>
            <span className="flex items-center gap-1"><span className="font-mono text-[10px] font-semibold text-muted">S</span>
              <Dots n={num(e.strike_cnt)} total={2} color="#eab308" /></span>
          </div>
        </div>
        <div className="font-mono text-4xl font-bold tabular-nums">{num(e.home_score)}</div>
        {side(hc, game.home_team_name, hr, true)}
      </div>
      <div className="border-t border-line px-5 py-1.5 text-center text-xs text-faint">
        {String(game.game_date ?? "")}　{String(game.venue ?? "")}
      </div>
    </div>
  );
}

// ───────────────────────── 當前對戰（球數/出局統一在記分條，此處放投打累計）─────────────────────────
type PitcherLive = { outs: number; k: number; h: number };
type TodayPA = { label: string; kind: PaKind; rbi: number; idx: number };

function Matchup({ e, batterAvg, pcount, pstats, batterToday, onJump }: {
  e: StatRow; batterAvg: Record<string, number>; pcount: number;
  pstats: PitcherLive; batterToday: TodayPA[]; onJump: (idx: number) => void;
}) {
  const ba = batterAvg[String(e.hitter_acnt ?? "")];
  const ip = `${Math.floor(pstats.outs / 3)}${pstats.outs % 3 ? `.${pstats.outs % 3}` : ""}`;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-muted">投手</div>
          <div className="text-lg font-semibold text-ink">{String(e.pitcher_name ?? "—")}</div>
          <div className="font-mono text-xs text-faint">至此 {ip} 局・{pstats.k}K・被安 {pstats.h}</div>
          <div className="font-mono text-xs text-faint">本場第 {pcount} 球</div>
        </div>
        <div>
          <div className="text-xs text-muted">打者{e.batting_order ? `　第 ${num(e.batting_order)} 棒` : ""}</div>
          <div className="text-lg font-semibold text-ink">{String(e.hitter_name ?? "—")}</div>
          <div className="font-mono text-xs text-faint">本季打擊率 {ba !== undefined ? avg3(ba) : "—"}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            <span className="text-xs text-faint">今日</span>
            {batterToday.length ? batterToday.map((pa, i) => (
              <button key={i} onClick={() => onJump(pa.idx)} title="看該打席"
                className={`rounded px-1.5 py-0.5 text-xs font-medium tabular-nums transition-colors hover:brightness-95 ${
                  pa.kind === "hit" ? "bg-emerald-500/10 text-emerald-700"
                  : pa.kind === "walk" ? "bg-sky-500/10 text-sky-700"
                  : "bg-surface-2 text-muted"}`}>
                {pa.label}{pa.rbi ? `(${pa.rbi})` : ""}
              </button>
            )) : <span className="text-xs text-faint">首打席</span>}
          </div>
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

// 逐局比分 = 局數導覽：每局格子可點（客列=上半、主列=下半）
function ScoreLine({ sb, game, halves, curKey, onSelect }: {
  sb: StatRow[]; game: StatRow; halves: Half[]; curKey: string; onSelect: (h: Half) => void;
}) {
  const away = sb.filter((r) => String(r.visiting_home_type) === "1");
  const home = sb.filter((r) => String(r.visiting_home_type) === "2");
  const innings = [...new Set(sb.map((r) => num(r.inning_seq)))].sort((a, b) => a - b);
  const halfBy = new Map(halves.map((h) => [`${h.inning}|${h.half}`, h]));
  const cellScore = (rows: StatRow[], inn: number) => rows.find((r) => num(r.inning_seq) === inn)?.score_cnt ?? "";
  const tot = (rows: StatRow[], key: string) => rows.reduce((s, r) => s + (num(r[key]) || 0), 0);

  const row = (label: StatRow[string], rows: StatRow[], half: string, score: number) => (
    <tr className="border-t border-line">
      <td className="whitespace-nowrap px-3 py-2 font-sans font-medium">{String(label ?? "")}</td>
      {innings.map((inn) => {
        const k = `${inn}|${half}`;
        const h = halfBy.get(k);
        const active = k === curKey;
        return (
          <td key={inn} className="p-0 text-center">
            {h ? (
              <button onClick={() => onSelect(h)}
                className={`h-9 w-full px-2.5 transition-colors hover:bg-surface-2 ${active ? "bg-accent font-semibold text-white" : "text-muted"}`}>
                {String(cellScore(rows, inn))}
              </button>
            ) : (
              <span className="block px-2.5 py-2 text-muted">{String(cellScore(rows, inn))}</span>
            )}
          </td>
        );
      })}
      <td className="px-2.5 py-2 text-center font-semibold text-accent">{score}</td>
      <td className="px-2.5 py-2 text-center text-muted">{tot(rows, "hitting_cnt")}</td>
      <td className="px-2.5 py-2 text-center text-muted">{tot(rows, "error_cnt")}</td>
    </tr>
  );

  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm font-mono tabular-nums">
        <thead className="bg-surface-2 text-muted">
          <tr>
            <th className="px-3 py-2 text-left font-medium">隊伍</th>
            {innings.map((inn) => <th key={inn} className="px-2.5 py-2 font-medium">{inn}</th>)}
            <th className="px-2.5 py-2 font-medium">R</th>
            <th className="px-2.5 py-2 font-medium">H</th>
            <th className="px-2.5 py-2 font-medium">E</th>
          </tr>
        </thead>
        <tbody>
          {row(game.away_team_name, away, "1", num(game.away_score))}
          {row(game.home_team_name, home, "2", num(game.home_score))}
        </tbody>
      </table>
    </div>
  );
}

// ───────────────────────── 逐打席賽況（選定半局）─────────────────────────
function PlayByPlay({ log, events, idx, setIdx, userAction }: {
  log: StatRow[]; events: number[]; idx: number; setIdx: (i: number) => void;
  userAction: MutableRefObject<boolean>;
}) {
  const activeRef = useRef<HTMLButtonElement | null>(null);
  // 只在使用者切半局／點打席時才把當前打席捲入視野。
  // 載入時 page 會 setIdx(終局)，但那不是使用者操作（userAction=false），
  // 不可捲動整頁——否則會把頂部記分條捲出視野、linescore 表頭卡進 sticky nav 下。
  // 用 userAction ref 判定而非「跳過首次掛載」：後者會被 StrictMode 雙呼叫 effect 打敗。
  useEffect(() => {
    if (!userAction.current) return;
    userAction.current = false;
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [idx, userAction]);

  return (
    <div className="flex-1 rounded-xl border border-line bg-surface p-4">
      <div className="space-y-0.5">
        {events.map((gi, k) => {
          const e = log[gi];
          const prev = k > 0 ? log[events[k - 1]] : undefined;
          const newBatter = !prev || prev.hitter_acnt !== e.hitter_acnt || prev.is_change_player !== e.is_change_player;
          const isScore = Boolean(e.is_score);
          const content = String(e.content ?? "").split(/[\r\n]/)[0];
          const isPitch = content.length <= 8;
          const active = gi === idx;
          return (
            <div key={gi}>
              {newBatter && e.hitter_name && !e.is_change_player && (
                <div className="mt-2.5 text-sm font-medium text-ink">
                  ⚾ {String(e.hitter_name)}
                  <span className="ml-2 text-xs text-faint">投：{String(e.pitcher_name ?? "")}</span>
                </div>
              )}
              <button ref={active ? activeRef : undefined} onClick={() => setIdx(gi)}
                className={`block w-full scroll-mt-16 rounded px-2 py-0.5 pl-5 text-left transition-colors hover:bg-surface-2 ${
                  active ? "bg-accent/10 ring-1 ring-accent/30" : ""} ${
                  isScore ? "text-accent" : isPitch ? "text-xs text-faint" : "text-sm text-ink"}`}>
                {content}
                {isScore && <span className="ml-2 font-mono text-xs">({num(e.visiting_score)}-{num(e.home_score)})</span>}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ───────────────────────── 好球帶（逐球進壘）─────────────────────────
const PITCH_ZH: Record<string, string> = { fastball: "速球", breakingball: "變化球", offspeed: "變速", other: "其他" };
const pitchZh = (t: string | null) => (t && PITCH_ZH[t]) || t || "—";
// 進壘判定 → 顏色（紅=好球/出局 綠=壞球 藍=擊出）
function callStyle(call: string | null): { color: string; label: string } {
  const c = call || "";
  if (c === "BallCalled") return { color: "#16a34a", label: "壞球" };
  if (c === "InPlay") return { color: "#2563eb", label: "擊出" };
  if (c.startsWith("Foul")) return { color: "#eab308", label: "界外" };
  if (c.startsWith("Strike")) return { color: "var(--color-accent)", label: c === "StrikeSwinging" ? "揮空" : "好球" };
  return { color: "var(--color-faint)", label: c || "—" };
}
// 真實座標(公尺) → SVG。視窗 side∈[-0.6,0.6]、height∈[0.2,1.5]
const SX = (s: number) => ((s + 0.6) / 1.2) * 200;
const SY = (h: number) => 200 - ((h - 0.2) / 1.3) * 200;
const ZONE = { l: -0.23, r: 0.23, b: 0.46, t: 1.05 }; // 名義好球帶

function StrikeZone({ pitches }: { pitches: TrackRow[] }) {
  const zl = SX(ZONE.l), zr = SX(ZONE.r), zt = SY(ZONE.t), zb = SY(ZONE.b);
  const gx1 = zl + (zr - zl) / 3, gx2 = zl + (2 * (zr - zl)) / 3;
  const gy1 = zt + (zb - zt) / 3, gy2 = zt + (2 * (zb - zt)) / 3;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-2 text-sm font-semibold">本打席進壘（逐球追蹤）</div>
      <div className="flex gap-4">
        <svg viewBox="0 0 200 200" className="h-44 w-44 shrink-0">
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
                <text x={SX(p.plate_loc_side)} y={SY(p.plate_loc_height) + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} fill="#fff">{i + 1}</text>
              </g>
            );
          })}
        </svg>
        <ol className="flex-1 space-y-1 text-sm">
          {pitches.map((p, i) => {
            const { color, label } = callStyle(p.pitch_call);
            return (
              <li key={i} className="flex items-center gap-2 font-mono tabular-nums">
                <span className="flex h-5 w-5 items-center justify-center rounded text-xs font-bold text-white" style={{ background: color }}>{i + 1}</span>
                <span className="w-12 font-sans text-muted">{label}</span>
                <span className="font-sans text-ink">{pitchZh(p.auto_pitch_type)}</span>
                {p.rel_speed != null && <span className="text-faint">{Math.round(p.rel_speed)} km/h</span>}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

// ───────────────────────── 主板 ─────────────────────────
export default function GameBoard({ data, idx, setIdx, view = "pbp", toolbar, onNavigate }: {
  data: Live;
  idx: number; setIdx: (i: number) => void;
  view?: "overview" | "pbp";     // overview=總覽（隱藏逐打席操作區）；pbp=逐打席
  toolbar?: React.ReactNode;     // 視圖切換列（渲染在逐局比分與內容之間）
  onNavigate?: () => void;       // 使用者選打席/選局時通知父層（總覽→切逐打席）
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

  // 當前打席逐球（以 投手×打者×局 三鍵精準比對 tracking）
  const paPitches = useMemo(() => {
    if (!e || !e.pitcher_acnt || !e.hitter_acnt) return [];
    return data.tracking
      .filter((p) => p.pitcher_acnt === e.pitcher_acnt && p.hitter_acnt === e.hitter_acnt && p.inning_seq === Number(e.inning_seq))
      .sort((a, b) => a.pitch_cnt - b.pitch_cnt);
  }, [data.tracking, e]);

  if (!e) return <p className="text-sm text-faint">無賽況資料。</p>;
  const isScore = Boolean(e.is_score);

  return (
    <div className="space-y-4">
      <ScoreBar game={game} e={e} records={data.records} />

      <ScoreLine sb={data.scoreboard} game={game}
        halves={halves} curKey={curKey} onSelect={(h) => selectIdx(h.firstIdx)} />

      {toolbar}

      {view === "pbp" && (
      <div id="pbp-section" className="grid scroll-mt-16 gap-4 lg:grid-cols-[1fr_360px]">
        {/* 左：逐打席賽況（選定半局）*/}
        <PlayByPlay log={log} events={curEvents} idx={idx} setIdx={selectIdx} userAction={userAction} />

        {/* 右：當前對戰 + 好球帶（sticky） */}
        <div className="space-y-4 lg:sticky lg:top-3 lg:self-start">
          <Matchup e={e} batterAvg={data.batter_avg} pcount={pcount}
            pstats={pstats} batterToday={batterToday} onJump={selectIdx} />
          <p className={`rounded-xl border px-4 py-3 text-sm ${isScore ? "border-accent/30 bg-accent/10 font-medium text-accent" : "border-line bg-surface text-ink"}`}>
            {String(e.content ?? "")}
          </p>
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
              本場未提供逐球追蹤資料（該球場未設置 TrackMan 設備），因此無進壘點、球種與球速。
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
