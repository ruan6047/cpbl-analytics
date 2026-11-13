"use client";

// PitchMind 概念展演頁（#452 修正三）：完全靜態、不呼叫 API，是未來功能的畫面預覽。
// 版型＝頂部情境與戰術選擇 → 比較區間（示意指標：參考線＋動態值）→ 三欄
// （情蒐資料／對戰紀錄｜情蒐指標｜動態指標）→ 我方投手量測對照 → 可展開的逐球與說明。
// 主畫面唯一可操作的業務選項是「查看戰術」；「展演控制」只推進事先寫好的合成劇本。

import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { DependencyMark, GameSituation } from "@/components/postmark";
import { ContextSwitcher } from "@/components/hierarchical-tabs";
import { ZoneScatter, type ZonePoint } from "@/components/zone-scatter";
import { Grid3x3 } from "@/components/perf-heatmap";
import {
  COUNT_TAGS, baselineCell, baselineEntry, batterPaResults, completedPaSummary, countTag, currentPaPitches,
  indicatorAt, lastPitchContext, pitcherMeasure, reactionCount, situationAt,
  type Cell, type PaPitch, type Status, type Tally,
} from "./accumulate.ts";
import {
  DEMO_BASELINES, DEMO_EVENTS, DEMO_LONG_POINTS, DEMO_MATCHUP, DEMO_MIN_N, DEMO_PITCHER_REF_SPEED,
  DEMO_REFERENCE, REPLAY_START,
} from "./demo-data.ts";
import {
  ALL_TAGS, DEMO_RULES, H_ZH, REACTIONS, REACTION_ORDER, SOURCES, TACTICS, V_ZH, type Tactic,
} from "./tactics.config.ts";
import type { GameEvent, Outcome } from "./model.ts";

const LAST = DEMO_EVENTS.length - 1;
const TACTIC_IDS = TACTICS.map((t) => t.id);
const pct = (r: number) => `${Math.round(r * 100)}%`;
const half = (h: "top" | "bottom") => (h === "top" ? "上" : "下");
const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");
const STATUS_TEXT: Record<Status, string> = { far: "距離尚遠", near: "接近區內", over: "已超過" };

/** 反應名稱；結果文字與名稱相同時不重複。 */
const reactionText = (o: Outcome, resultText: string) =>
  (REACTIONS[o].label === resultText ? resultText : `${REACTIONS[o].label}（${resultText}）`);

function cutoffText(e: GameEvent): string {
  const s = e.after;
  if (e.kind === "pa_start") return `${e.label}（尚無本打席投球）`;
  return `${e.label}：${e.resultText}（${s.inning} 局${half(s.half)}）`;
}

// ───────── 不可操作的狀態標籤：無 button 語意、無 tabindex、無 hover／focus 樣式 ─────────
function StateTag({ active, round = false, children }: { active: boolean; round?: boolean; children: string }) {
  return (
    <li className={`inline-flex cursor-default select-none items-center gap-1 px-2.5 py-1 text-xs ${round ? "rounded-full" : "rounded-sm"} ${active
      ? "font-bold text-ink ring-2 ring-ink"
      : "text-faint ring-1 ring-line"}`}>
      {active && <span aria-hidden="true" className="inline-block h-1.5 w-1.5 rounded-full bg-ink" />}
      {children}
      {active && <span className="sr-only">（目前）</span>}
    </li>
  );
}

// ───────── 狀態形狀：距離尚遠＝空心圓、接近區內＝三角、已超過＝實心方塊（不只靠顏色）─────────
function StatusShape({ status, x = 0, y = 0, size = 14 }: { status: Status; x?: number; y?: number; size?: number }) {
  const h = size / 2;
  if (status === "far") return <circle cx={x} cy={y} r={h - 1} className="fill-surface stroke-ink" strokeWidth={2.5} />;
  if (status === "near") return <polygon points={`${x},${y - h} ${x + h},${y + h - 1} ${x - h},${y + h - 1}`} className="fill-ink stroke-surface" strokeWidth={1.5} />;
  return <rect x={x - h + 1} y={y - h + 1} width={size - 2} height={size - 2} className="fill-ink stroke-surface" strokeWidth={1.5} />;
}

// ───────── 比較區間：同一示意尺度上的參考線、接近區、超過區與動態值 ─────────
function Gauge({ value, reference, status, prevValue, prevReference }: {
  value: number; reference: number; status: Status; prevValue: number | null; prevReference: number | null;
}) {
  const W = 640, L = 14, R = 14, trackY = 44, trackH = 24;
  const sx = (v: number) => L + ((v - DEMO_RULES.min) / (DEMO_RULES.max - DEMO_RULES.min)) * (W - L - R);
  const nearFrom = Math.max(DEMO_RULES.min, reference - DEMO_RULES.nearBand);
  const labelX = (v: number, pad: number) => Math.min(sx(100) - pad, Math.max(sx(0) + pad, sx(v)));
  return (
    <svg viewBox={`0 0 ${W} 112`} className="w-full" role="img"
      aria-label={`示意指標比較區間（0 到 100）：情蒐參考 ${reference}，本場動態 ${value}，${STATUS_TEXT[status]}`}>
      <defs>
        <pattern id="pm-near-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" className="stroke-line-strong" strokeWidth="2" />
        </pattern>
      </defs>
      <rect x={sx(0)} y={trackY} width={sx(100) - sx(0)} height={trackH} rx={3} className="fill-surface-2" />
      {/* 接近區（斜線）與超過區（實色） */}
      <rect x={sx(nearFrom)} y={trackY} width={sx(reference) - sx(nearFrom)} height={trackH} fill="url(#pm-near-hatch)" />
      <rect x={sx(reference)} y={trackY} width={sx(100) - sx(reference)} height={trackH} className="fill-band" />
      <text x={(sx(nearFrom) + sx(reference)) / 2} y={trackY + trackH + 13} textAnchor="middle" className="fill-faint" fontSize={10}>接近區</text>
      <text x={(sx(reference) + sx(100)) / 2} y={trackY + trackH + 13} textAnchor="middle" className="fill-faint" fontSize={10}>超過區</text>
      {/* 動態值 */}
      <rect x={sx(0)} y={trackY + 6} width={Math.max(0, sx(value) - sx(0))} height={trackH - 12} rx={2} className="fill-ink" />
      {prevValue != null && prevValue !== value && (
        <line x1={sx(prevValue)} x2={sx(prevValue)} y1={trackY - 2} y2={trackY + trackH + 2} className="stroke-muted" strokeWidth={2} strokeDasharray="2 2" />
      )}
      {/* 參考線（變動時以虛線留下原位置） */}
      {prevReference != null && prevReference !== reference && (
        <line x1={sx(prevReference)} x2={sx(prevReference)} y1={trackY - 12} y2={trackY + trackH + 2} className="stroke-muted" strokeWidth={2} strokeDasharray="4 3" />
      )}
      <line x1={sx(reference)} x2={sx(reference)} y1={trackY - 14} y2={trackY + trackH + 3} className="stroke-ink" strokeWidth={3} />
      <text x={labelX(reference, 44)} y={18} textAnchor="middle" className="fill-ink" fontSize={15} fontWeight={700}>情蒐參考 {reference}</text>
      <StatusShape status={status} x={sx(value)} y={trackY + trackH / 2} size={18} />
      <text x={labelX(value, 44)} y={trackY + trackH + 36} textAnchor="middle" className="fill-ink" fontSize={17} fontWeight={800}>本場動態 {value}</text>
      {[0, 50, 100].map((t) => (
        <text key={t} x={sx(t)} y={trackY - 4} textAnchor={t === 0 ? "start" : t === 100 ? "end" : "middle"} className="fill-faint" fontSize={10}>{t}</text>
      ))}
    </svg>
  );
}

// ───────── 基準格（精簡版）：四態互斥，各自不同文字 ─────────
function CellView({ cell }: { cell: Cell }) {
  if (cell.state === "missing") return <div><DependencyMark>缺值</DependencyMark></div>;
  if (cell.state === "insufficient") {
    return <div><span className="pm-st pm-st--sample pm-st--sm">樣本不足</span>
      <div className="mt-0.5 text-[11px] text-faint">n={cell.n}</div></div>;
  }
  return <div>
    <span className="font-mono text-base font-bold tabular-nums text-ink">{cell.state === "zero" ? "0 次" : pct(cell.rate)}</span>
    <div className="mt-0.5 font-mono text-[11px] tabular-nums text-faint">{cell.k} / {cell.n}</div>
  </div>;
}
const cellInline = (c: Cell) =>
  c.state === "ok" ? `${pct(c.rate)}（${c.k}/${c.n}）` : c.state === "zero" ? `0 次（0/${c.n}）` : c.state === "insufficient" ? `樣本不足（n=${c.n}）` : "缺值";

// ───────── 目標區域示意（與進壘點圖同座標：捕手視角）─────────
function TargetZone({ tactic }: { tactic: Tactic }) {
  const W = 120, H = 124, pad = 8;
  const xMin = -0.5, xMax = 0.5, yMin = 0.15, yMax = 1.35;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin)) * (H - 2 * pad);
  const hx: Record<string, [number, number]> = { inside: [-0.35, -0.07], middle: [-0.07, 0.07], outside: [0.07, 0.35] };
  const vy: Record<string, [number, number]> = { high: [0.83, 1.15], mid: [0.67, 0.83], low: [0.3, 0.67] };
  const x0 = Math.min(...tactic.condition.h.map((h) => hx[h][0])), x1 = Math.max(...tactic.condition.h.map((h) => hx[h][1]));
  const y0 = Math.min(...tactic.condition.v.map((v) => vy[v][0])), y1 = Math.max(...tactic.condition.v.map((v) => vy[v][1]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-28" role="img" aria-label={`目標區域示意：${tactic.condition.text}`}>
      <rect x={sx(-0.21)} y={sy(1.0)} width={sx(0.21) - sx(-0.21)} height={sy(0.5) - sy(1.0)}
        className="fill-surface-2 stroke-faint" strokeWidth={1} />
      <rect x={sx(x0)} y={sy(y1)} width={sx(x1) - sx(x0)} height={sy(y0) - sy(y1)}
        className="fill-accent/25 stroke-accent" strokeWidth={1.4} strokeDasharray="3 2" />
      <text x={W / 2} y={H - 1} textAnchor="middle" className="fill-faint" fontSize={8}>捕手視角・右打外角在右</text>
    </svg>
  );
}

// ───────── 逐球表（本打席／剛結束打席共用）─────────
function PaTable({ list, tactic }: { list: PaPitch[]; tactic: Tactic }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-xs">
        <thead className="bg-band text-muted">
          <tr>{["球序", "投出前球數", "球種", "位置", "球速", "與前一球差", "反應", `對「${tactic.name}」`].map((h) =>
            <th key={h} scope="col" className="px-2 py-1.5 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {list.map((p) => (
            <tr key={p.event.id} className="border-b border-line">
              <td className="px-2 py-1.5 font-mono tabular-nums">{p.event.seq}</td>
              <td className="px-2 py-1.5 font-mono tabular-nums">{p.pre.balls}-{p.pre.strikes}</td>
              <td className="px-2 py-1.5">{p.event.pitch}</td>
              <td className="px-2 py-1.5">{H_ZH[p.event.h]}{V_ZH[p.event.v]}</td>
              <td className="px-2 py-1.5 font-mono tabular-nums">{p.event.speed} km/h</td>
              <td className="px-2 py-1.5 font-mono tabular-nums">{p.speedDiff == null ? "—（首球）" : `${p.speedDiff > 0 ? "+" : ""}${p.speedDiff}`}</td>
              <td className="px-2 py-1.5">{reactionText(p.event.outcome, p.event.resultText)}</td>
              <td className="px-2 py-1.5">{p.inclusion.included
                ? <b className="text-ink">納入（{signed(tactic.points[p.event.outcome])}）</b>
                : <span className="text-faint">未納入：{p.inclusion.reasons.join("、")}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PitchMindDemo() {
  const [tacticId, setTacticId] = useState<string>(TACTICS[0].id);
  const [idx, setIdx] = useState(REPLAY_START);
  const [playing, setPlaying] = useState(false);
  // 剛到達的事件索引：只用來讓改變的數值短暫突出，約 2 秒後自動清除（不影響任何數字）。
  const [flash, setFlash] = useState<number | null>(null);
  const tactic = TACTICS.find((t) => t.id === tacticId) ?? TACTICS[0];
  const others = REACTION_ORDER.filter((r) => !tactic.focus.includes(r));

  const go = (next: number) => { setIdx(next); setFlash(next); };
  // 播放到最後一個事件自動停；計時器只推進索引，所有數字仍由索引推導。
  const isPlaying = playing && idx < LAST;
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setTimeout(() => {
      const next = Math.min(LAST, idx + 1);
      setIdx(next);
      setFlash(next);
      if (next >= LAST) setPlaying(false);
    }, 2600);
    return () => clearTimeout(timer);
  }, [isPlaying, idx]);
  useEffect(() => {
    if (flash == null) return;
    const timer = setTimeout(() => setFlash(null), 2000);
    return () => clearTimeout(timer);
  }, [flash]);

  const { situation: s, cutoff } = situationAt(DEMO_EVENTS, idx);
  const tag = countTag(s.balls, s.strikes);
  const ind = indicatorAt(DEMO_EVENTS, idx, tactic, DEMO_REFERENCE);
  const dyn = ind.dyn;
  const ck = ind.count;
  const ctx = lastPitchContext(DEMO_EVENTS, idx);
  const paDone = completedPaSummary(DEMO_EVENTS, idx, tactic);
  const pa = currentPaPitches(DEMO_EVENTS, idx, tactic);
  const priorPas = batterPaResults(DEMO_EVENTS, idx, s.batter);
  const measure = pitcherMeasure(DEMO_EVENTS, idx, tactic);
  const matchup = DEMO_MATCHUP[s.batter];
  const mu = matchup?.byTactic[tactic.id] ?? null;
  const longPts = (DEMO_LONG_POINTS[s.batter] ?? []).filter((p) => p.pitch === tactic.condition.pitch);
  const measurePoints: ZonePoint[] = measure.points.map((p) => ({ x: p.x, y: p.y, sw: p.outcome !== "take", wh: p.outcome === "whiff", result: p.zoneResult }));
  const replayPos = idx - REPLAY_START + 1, replayTotal = LAST - REPLAY_START + 1;

  const lastObs = dyn.last.kind === "included" ? dyn.last.observation : null;
  const justChanged = flash === idx && lastObs != null;
  const prevReference = ind.refChange?.kind === "count" ? ind.refChange.fromRef : null;
  const distanceText = ind.distance == null ? "" : ind.distance < 0 ? `高於參考線 ${-ind.distance}`
    : ind.distance === 0 ? "剛好到參考線" : `距參考線還有 ${ind.distance}`;
  const moveText = lastObs ? `${lastObs.delta > 0 ? "↑" : lastObs.delta < 0 ? "↓" : "→"} 本次 ${signed(lastObs.delta)}`
    : dyn.last.kind === "excluded" ? "本球未納入" : dyn.last.kind === "other_batter" ? "剛換打者" : "尚無本打席投球";
  const reasonText = lastObs
    ? `第 ${lastObs.seq} 球${tactic.name}：${reactionText(lastObs.outcome, lastObs.resultText)}`
    : dyn.last.kind === "excluded" ? dyn.last.text
    : dyn.last.kind === "other_batter" ? `上一球屬於${dyn.last.batter} 的打席，不計入${s.batter}。`
    : "打者剛上場，本打席尚無投球。";
  const refNote = ind.refChange?.kind === "count"
    ? `球數 ${ind.refChange.from} → ${ind.refChange.to}：參考線 ${ind.refChange.fromRef ?? "—"} → ${ind.reference ?? "—"}，是情境不同，不是打者反應改變。`
    : ind.refChange?.kind === "batter" ? `換為${s.batter}：參考線改用${s.batter} 自己的值。` : null;
  const focusList = (tally: Tally) => tactic.focus.map((r) => `${REACTIONS[r].label} ${tally[r]}`).join("、");

  return (
    <main className="mx-auto max-w-[1280px] space-y-4 px-4 py-5">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-xl font-bold tracking-[0.04em] text-ink">PitchMind 情蒐展演</h1>
          <span className="pm-st pm-st--hold">示意資料</span>
          <span className="text-xs text-muted">未來功能的畫面預覽・合成劇本・匿名球員</span>
        </div>
        {/* 展演控制（與正式操作分開） */}
        <section aria-label="展演控制" className="max-w-full rounded-md border-2 border-dashed border-line-strong px-3 py-2 lg:max-w-[680px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <div className="text-sm font-bold text-ink">展演控制</div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => { setPlaying(false); go(REPLAY_START); }} disabled={idx === REPLAY_START}
                className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">重播</button>
              <button type="button" onClick={() => { setPlaying(false); go(Math.max(REPLAY_START, idx - 1)); }} disabled={idx === REPLAY_START}
                className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">上一事件</button>
              <button type="button" onClick={() => setPlaying((p) => !p)} disabled={idx >= LAST} aria-pressed={isPlaying}
                className="min-h-11 rounded-md bg-ink px-4 text-sm font-bold text-paper disabled:opacity-40">{isPlaying ? "暫停" : "播放"}</button>
              <button type="button" onClick={() => { setPlaying(false); go(Math.min(LAST, idx + 1)); }} disabled={idx >= LAST}
                className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">下一事件</button>
            </div>
            <span className="font-mono text-xs tabular-nums text-muted" data-testid="replay-pos">事件 {replayPos} / {replayTotal}</span>
          </div>
          <p className="mt-1 text-xs text-muted" data-testid="script">劇本（外角高速球主線）：{cutoff.script ?? "—"}</p>
        </section>
      </div>

      {/* 頂部情境（系統帶入，不可點選） */}
      <Card className="space-y-3" padding="px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div>
            <div className="text-xs text-muted">目前打者</div>
            <div className="text-2xl font-black text-ink" data-testid="batter">{s.batter}
              <span className="ml-1.5 text-sm font-medium text-muted">{s.batterHand === "R" ? "右打" : "左打"}</span></div>
          </div>
          <div>
            <div className="text-xs text-muted">我方投手</div>
            <div className="text-lg font-bold text-ink">{s.pitcher}<span className="ml-1.5 text-sm font-medium text-muted">右投</span></div>
          </div>
          <div>
            <div className="text-xs text-muted">局數</div>
            <div className="text-lg font-bold text-ink">{s.inning} 局{half(s.half)}</div>
          </div>
          <div>
            <div className="text-xs text-muted">球數（壞-好）</div>
            <div className="font-mono text-2xl font-black tabular-nums text-ink" data-testid="count">{s.balls}-{s.strikes}</div>
          </div>
          <div className="rounded-md bg-surface-2 px-3 py-1.5">
            <GameSituation bases={s.bases} outs={s.outs} balls={s.balls} strikes={s.strikes} />
          </div>
          <div className="min-w-0 basis-full text-xs text-muted md:ml-auto md:basis-auto md:text-right">
            <div>資料截至</div>
            <div className="font-medium text-ink" data-testid="cutoff">{cutoffText(cutoff)}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">情境（系統判定・投手觀點）</span>
          <ul className="flex flex-wrap gap-1.5" aria-label="情境標籤">
            {COUNT_TAGS.map((t) => <StateTag key={t} active={t === tag}>{t}</StateTag>)}
          </ul>
        </div>
      </Card>

      {/* 戰術選擇（唯一可切換的業務選項）＋唯讀說明標籤 */}
      <Card padding="px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <ContextSwitcher label="查看戰術" values={TACTIC_IDS} value={tacticId}
            render={(id) => TACTICS.find((t) => t.id === id)?.name ?? id} onChange={setTacticId} />
          <div className="text-xs text-muted">目的：<span className="font-medium text-ink">{tactic.purpose}</span></div>
          <div className="text-xs text-muted" data-testid="focus">關注反應：<span className="font-medium text-ink">{tactic.focus.map((r) => REACTIONS[r].label).join("・")}</span></div>
          <ul className="flex flex-wrap gap-1.5 md:ml-auto" aria-label="戰術說明標籤（隨戰術帶出）">
            {ALL_TAGS.map((t) => <StateTag key={t} round active={tactic.tags.includes(t)}>{t}</StateTag>)}
          </ul>
        </div>
        <p className="mt-1.5 text-[11px] text-faint">條件：{tactic.condition.text}。切換只改變查看的戰術，不代表教練已採用。</p>
      </Card>

      {/* 比較區間（快讀主體）：示意指標上的參考線與動態值 */}
      <Card padding="px-5 py-4" className={`ring-2 ${justChanged ? "ring-ink" : "ring-transparent"}`}>
        <div className="grid items-center gap-x-8 gap-y-3 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]" data-testid="strip" data-flash={justChanged ? "1" : "0"}>
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="pm-st pm-st--sample pm-st--sm">示意指標</span>
              <span>比較區間・{s.batter}・{tactic.name}</span>
            </div>
            {ind.status ? (
              <div className="mt-1.5 flex items-center gap-2.5" data-testid="status">
                <svg width={28} height={28} viewBox="-14 -14 28 28" aria-hidden="true"><StatusShape status={ind.status} size={24} /></svg>
                <span className="text-3xl font-black leading-none text-ink">{STATUS_TEXT[ind.status]}</span>
              </div>
            ) : <div className="mt-1.5"><DependencyMark>此打者沒有參考線資料</DependencyMark></div>}
            <div className="mt-2 text-base font-bold text-ink" data-testid="distance">{distanceText}</div>
            <div className="font-mono text-sm font-bold tabular-nums text-ink" data-testid="move">{moveText}</div>
          </div>
          {ind.reference != null && ind.status && (
            <Gauge value={ind.value} reference={ind.reference} status={ind.status} prevValue={ind.prevValue} prevReference={prevReference} />
          )}
        </div>
        {refNote && <p className="mt-2 text-xs text-ink" data-testid="strip-ref-note">{refNote}</p>}
        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs">
          <span className="text-ink" data-testid="reason">{reasonText}</span>
          <span className={ind.status === "far" || !ind.status ? "text-faint" : "font-bold text-ink"} data-testid="hint">
            {ind.status === "near" || ind.status === "over" ? "提示：可提醒教練留意這個戰術；是否調整由教練決定。" : "尚無提示"}
          </span>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* 欄一：情蒐資料／對戰紀錄 */}
        <Card className="space-y-4">
          <h2 className="text-base font-bold text-ink" data-testid="left-title">情蒐資料・對戰紀錄<span className="ml-2 text-xs font-normal text-muted">{s.batter}</span></h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs">
              <div className="mb-1 font-medium text-ink">{s.batter} 對 {s.pitcher}・過往</div>
              {matchup ? (
                <>
                  <div className="text-muted">{matchup.period}</div>
                  <div className="mt-1 font-mono tabular-nums text-ink">{matchup.pa} 打席・{matchup.hits} 安打・{matchup.so} 三振・{matchup.bb} 保送</div>
                  {mu && <div className="mt-1 text-muted">「{tactic.name}」來球 <b className="text-ink">{mu[0]}</b> 球：
                    {tactic.focus.map((r) => `${REACTIONS[r].label} ${reactionCount(mu, r)}`).join("、")}</div>}
                </>
              ) : <DependencyMark>缺值／待補</DependencyMark>}
            </div>
            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs">
              <div className="mb-1 font-medium text-ink">{s.batter}・本場已結束打席</div>
              {priorPas.length ? (
                <ul className="space-y-0.5 text-ink">{priorPas.map((p, i) => <li key={i}>{p.inning} 局：{p.text}</li>)}</ul>
              ) : <span className="text-faint">本場尚無已結束打席（0 個）</span>}
            </div>
          </div>
          <div>
            <h3 className="mb-1 text-sm font-medium text-muted">來球位置・{tactic.condition.pitch}（{s.batter} 長期，{longPts.length} 球）</h3>
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
              <div className="mx-auto w-full max-w-[300px]"><ZoneScatter points={longPts} staticLegend /></div>
              <div className="flex flex-col items-center gap-1 pt-2">
                <TargetZone tactic={tactic} />
                <div className="text-center text-[11px] text-muted">目標區域<br />{tactic.name}</div>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-[minmax(0,180px)_minmax(0,1fr)] items-center gap-3">
            <Grid3x3 points={longPts} metric={tactic.heatMetric.metric} title={`${tactic.heatMetric.title}・${tactic.condition.pitch}`} />
            <p className="text-[11px] leading-relaxed text-faint">白＝此打者此球種均值；每格樣本少於 3 顯「—」。</p>
          </div>
        </Card>

        <div className="grid gap-4 md:grid-cols-2">
          {/* 欄二：情蒐指標（上：參考線的值；下：各來源在此條件的反應） */}
          <Card className="space-y-3">
            <h2 className="text-base font-bold text-ink">情蒐指標</h2>
            <div className="rounded-md bg-surface-2 px-3 py-2.5" data-testid="scout-quick">
              <div className="text-xs font-medium text-muted">情蒐參考<span className="ml-1 text-faint">示意指標・比較區間的參考線</span></div>
              <div className="mt-0.5 flex items-baseline gap-2">
                <span className="font-mono text-3xl font-black tabular-nums leading-none text-ink">{ind.reference ?? "—"}</span>
                <span className="text-xs text-muted">{s.batter}・球數 <b className="text-ink">{ck}</b></span>
              </div>
            </div>
            <div className="space-y-2" data-testid="scout-rows">
              {tactic.scoutingSources.map((src) => {
                const meta = SOURCES[src];
                const entry = baselineEntry(DEMO_BASELINES, tactic.id, src, s.batter, ck);
                return (
                  <div key={src} className="rounded-md bg-surface-2 px-3 py-2">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                      <span className="text-sm font-medium text-ink">{meta.label}{meta.scope === "batter" && <span className="ml-1 text-xs font-normal text-muted">{s.batter}</span>}</span>
                      <span className="text-[11px] text-faint">{meta.period}</span>
                    </div>
                    <div className="mt-1.5 grid grid-cols-4 gap-1.5">
                      {tactic.focus.map((r) => (
                        <div key={r}>
                          <div className="text-[11px] text-muted">{REACTIONS[r].label}</div>
                          <CellView cell={baselineCell(entry, r, DEMO_MIN_N)} />
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <details className="rounded-md bg-surface-2 px-3 py-2 text-xs">
              <summary className="cursor-pointer font-medium text-ink">其他反應（{others.map((r) => REACTIONS[r].label).join("、")}）</summary>
              <div className="mt-2 space-y-1.5" data-testid="scout-others">
                {tactic.scoutingSources.map((src) => {
                  const entry = baselineEntry(DEMO_BASELINES, tactic.id, src, s.batter, ck);
                  return (
                    <div key={src}>
                      <div className="font-medium text-ink">{SOURCES[src].label}</div>
                      <div className="text-muted">{others.map((r) => `${REACTIONS[r].label} ${cellInline(baselineCell(entry, r, DEMO_MIN_N))}`).join("・")}</div>
                    </div>
                  );
                })}
              </div>
            </details>
            <p className="text-[11px] text-faint">各格為此條件（{tactic.name}・球數 {ck}）的比例，下方是次數／來球數。</p>
          </Card>

          {/* 欄三：動態指標（上：目前示意值與本次增減；下：本場相關觀察） */}
          <Card className="space-y-3">
            <h2 className="text-base font-bold text-ink">動態指標</h2>
            <div data-testid="dyn-quick" data-flash={justChanged ? "1" : "0"}
              className={`rounded-md bg-surface-2 px-3 py-2.5 ring-2 ${justChanged ? "ring-ink" : "ring-transparent"}`}>
              <div className="text-xs font-medium text-muted">本場動態<span className="ml-1 text-faint">示意指標・比較區間的動態值</span></div>
              <div className="mt-0.5 flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-3xl font-black tabular-nums leading-none text-ink" data-testid="dyn-value">{ind.value}</span>
                {lastObs && (
                  <span className="inline-flex items-center rounded-sm bg-ink px-1.5 py-0.5 font-mono text-xs font-bold tabular-nums text-paper">
                    本次 {lastObs.delta > 0 ? "↑" : lastObs.delta < 0 ? "↓" : "→"} {signed(lastObs.delta)}
                  </span>
                )}
                <span className="text-xs text-muted">{s.batter}</span>
              </div>
              <p className="mt-1.5 text-xs text-ink" data-testid="dyn-last">{reasonText}</p>
            </div>

            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs" data-testid="dyn-obs">
              <div className="text-sm font-medium text-ink">{s.batter}・本場相關觀察</div>
              <div className="mt-1 text-ink">符合條件來球 <b className="font-mono tabular-nums">{dyn.tally.opp}</b> 球
                （本打席 {dyn.currentPaOpp}{dyn.priorInnings.length > 0 && `、先前打席 ${dyn.tally.opp - dyn.currentPaOpp}`}）</div>
              <div className="mt-1.5 grid grid-cols-4 gap-1.5">
                {tactic.focus.map((r) => (
                  <div key={r}>
                    <div className="text-[11px] text-muted">{REACTIONS[r].label}</div>
                    <div className="font-mono text-base font-bold tabular-nums text-ink">{dyn.tally[r]}<span className="text-[11px] font-normal text-faint"> / {dyn.tally.opp}</span></div>
                  </div>
                ))}
              </div>
              <div className="mt-1 text-[11px] text-muted">其他：{others.map((r) => `${REACTIONS[r].label} ${dyn.tally[r]}`).join("、")}</div>
              {dyn.priorInnings.length > 0 && (
                <div className="mt-1 text-[11px] text-faint">含{s.batter} 本場 {dyn.priorInnings.join("、")} 局的打席，只算他自己的球。</div>
              )}
            </div>

            {ctx && ctx.sameBatter && (
              <div className="rounded-md bg-surface-2 px-3 py-2 text-xs text-ink" data-testid="ctx-box">
                <div>上一球：第 {ctx.event.seq} 球，投出前 <b className="font-mono">{ctx.pre.balls}-{ctx.pre.strikes}</b>
                  {lastObs ? `（觀察記在 ${ctx.pre.balls}-${ctx.pre.strikes}）` : "（未納入）"}</div>
                <div>目前情境：<b className="font-mono">{ck}</b>（參考線用 {ck} 的值）</div>
              </div>
            )}

            {paDone && (
              <div className="rounded-md bg-surface-2 px-3 py-2 text-xs" data-testid="pa-done">
                <div className="text-sm font-medium text-ink">剛結束打席摘要・{paDone.batter}</div>
                <div className="mt-1 text-ink">{paDone.inning} 局・{paDone.pitches} 球・{paDone.resultText}</div>
                <div className="text-ink">{tactic.name} {paDone.includedCount} 球；本場動態 {paDone.valueBefore} → {paDone.valueAfter}</div>
                <div className="mt-0.5 text-[11px] text-faint">供轉達用；屬於{paDone.batter}，不計入{s.batter}。</div>
              </div>
            )}

            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs" data-testid="teammates">
              <div className="text-sm font-medium text-ink">隊友共同反應<span className="ml-1 text-[11px] font-normal text-faint">獨立欄位</span></div>
              <div className="mt-1 text-ink">{dyn.teammates.batters.join("、") || "其他打者"}：
                <b className="font-mono tabular-nums">{dyn.teammates.opp}</b> 球符合條件；{focusList(dyn.teammates)}</div>
              <div className="mt-0.5 text-[11px] text-faint">原始次數，不計入{s.batter} 的示意指標。</div>
            </div>
          </Card>
        </div>
      </div>

      {/* 我方投手量測對照（只描述球速與位置） */}
      <Card className="space-y-3">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="text-base font-bold text-ink">我方投手量測對照</h2>
          <span className="text-xs text-muted" data-testid="measure-scope">{s.pitcher}・本場{measure.pitch}・截至上方事件</span>
        </div>
        {measure.count === 0 ? <p className="text-xs text-faint">本場尚未投出{measure.pitch}（0 球）</p> : (
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_240px]">
            <div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="measure">
                {[
                  ["本場球數", `${measure.count}`, "球"],
                  ["本場均速", measure.avgSpeed == null ? "—" : measure.avgSpeed.toFixed(1), "km/h"],
                  ["賽前參考均速", DEMO_PITCHER_REF_SPEED[measure.pitch]?.toFixed(1) ?? "—", "km/h"],
                  ["最近一顆", measure.lastSpeed == null ? "—" : `${measure.lastSpeed}`, "km/h"],
                ].map(([l, v, u]) => (
                  <div key={l} className="rounded-md bg-surface-2 px-3 py-2">
                    <div className="text-[11px] text-muted">{l}</div>
                    <div className="mt-0.5 font-mono text-base tabular-nums text-ink">{v}<span className="ml-0.5 text-[10px] text-faint">{u}</span></div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs text-ink">實際進壘位置：{tactic.condition.h.map((h) => H_ZH[h]).join("／")}{tactic.condition.v.map((v) => V_ZH[v]).join("／")}
                {" "}<b className="font-mono tabular-nums">{measure.inTargetZone}</b> 球、其他位置 <b className="font-mono tabular-nums">{measure.count - measure.inTargetZone}</b> 球</p>
              <p className="mt-1 text-[11px] text-faint">只描述量測到的球速與位置；沒有捕手原定目標，無法判斷是否投到預定位置。</p>
            </div>
            <div>
              <h3 className="mb-1 text-sm font-medium text-muted">本場{measure.pitch}進壘點（{measure.count} 球）</h3>
              <div className="mx-auto w-full max-w-[240px]"><ZoneScatter points={measurePoints} staticLegend /></div>
            </div>
          </div>
        )}
      </Card>

      {/* 可展開：本打席逐球 */}
      <details className="card px-4 py-3">
        <summary className="cursor-pointer text-sm font-bold text-ink" data-testid="pa-summary">
          {pa.length > 0 ? `本打席逐球・${s.batter}（${pa.length} 球）`
            : paDone ? `剛結束打席逐球・${paDone.batter}（${paDone.pitches} 球）` : `本打席逐球・${s.batter}（0 球）`}
        </summary>
        <div className="mt-3">
          {pa.length > 0 ? <PaTable list={pa} tactic={tactic} />
            : paDone ? <PaTable list={paDone.list} tactic={tactic} />
            : <p className="text-xs text-faint">本打席尚無投球（0 球）</p>}
        </div>
      </details>

      {/* 可展開：示意指標逐事件（取代曲線） */}
      <details className="card px-4 py-3">
        <summary className="cursor-pointer text-sm font-bold text-ink">本場動態逐事件・{s.batter}・{tactic.name}（{dyn.observations.length} 筆）</summary>
        <p className="mt-2 text-xs text-muted">
          觀察對象：{s.batter}。對應戰術：{tactic.name}。每列是一顆符合條件的來球與它讓示意指標增減多少；數值是示意點數，不是機率，也不是選手近況。
        </p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-xs" data-testid="obs-table">
            <thead className="bg-band text-muted">
              <tr>{["局", "球序", "投出前球數", "反應", "本次增減", "本場動態"].map((h) =>
                <th key={h} scope="col" className="px-2 py-1.5 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {dyn.observations.map((o) => (
                <tr key={o.eventId} className="border-b border-line">
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.inning}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.seq}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.count}</td>
                  <td className="px-2 py-1.5">{reactionText(o.outcome, o.resultText)}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{signed(o.delta)}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {/* 可展開：展演說明 */}
      <details className="card px-4 py-3">
        <summary className="cursor-pointer text-sm font-bold text-ink">展演說明與示意規則</summary>
        <div className="mt-2 space-y-2 text-xs leading-relaxed text-muted">
          <p><b className="text-ink">示意資料：</b>本頁是未來功能的畫面預覽。比賽流程、球員（匿名）、參考線、各來源數字都是直接寫好的模擬值，不代表真實球員或比賽，也不是模型算出來的結果。只討論壘上無人。</p>
          <p><b className="text-ink">比較區間（示意指標）：</b>參考線代表賽前情蒐對這個戰術、這位打者、這個球數的參考位置；動態值代表本場到目前為止，打者的反應與戰術目的不一致的程度。兩者放在同一把 0–100 的示意尺上。正式指標、刻度、權重與門檻都待研究。接近或超過參考線不代表戰術失效，也不是已校準的警戒線；只是提示可以留意，是否調整由教練決定。</p>
          <div>
            <b className="text-ink">示意規則（都不是已驗證方法）：</b>
            <ol className="mt-1 list-decimal space-y-0.5 pl-5">
              <li>一球要球種、區域都符合所選戰術且壘上無人才納入；否則顯示未納入的原因。實投符合條件不等於已知投捕意圖。</li>
              <li>只算目前打者自己的球，可含他本場先前打席；其他打者只出現在隊友共同反應欄位。換打者不帶走前一位的累積。</li>
              <li>每納入一球，動態值依反應增減（{tactic.name}）：{(Object.keys(tactic.points) as Outcome[]).map((o) => `${REACTIONS[o].label} ${signed(tactic.points[o])}`).join("、")}；限制在 0–100。</li>
              <li>與參考線差距在 {DEMO_RULES.nearBand} 以內＝接近區內；達到或高於參考線＝已超過；其餘＝距離尚遠。</li>
              <li>觀察記在投出前的球數；參考線依目前球數取值（滿球數另給一個值）。球數改變造成的參考線變動來自情境，不是打者。跨情境如何共享累積尚未定案。</li>
            </ol>
          </div>
          <div>
            <b className="text-ink">反應種類（示意定義；分母都是符合條件的來球數）：</b>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {REACTION_ORDER.map((r) => <li key={r}><b className="text-ink">{REACTIONS[r].label}</b>：{REACTIONS[r].def}</li>)}
            </ul>
            <p className="mt-1">{TACTICS.map((t) => `${t.name}關注：${t.focus.map((r) => REACTIONS[r].label).join("、")}`).join("；")}。</p>
          </div>
          <p><b className="text-ink">說明標籤（{tactic.name}）：</b>{tactic.tags.map((t) => `${t}＝${tactic.tagNotes[t]}`).join("；")}。標籤隨戰術帶出，不代表已量測效果。</p>
          <p><b className="text-ink">投手量測：</b>只描述球速與實際進壘位置；沒有捕手原定目標，不判斷是否投到預定位置。</p>
          <p><b className="text-ink">尚未完成：</b>1–2 秒快讀是設計目標，還沒有實際試讀結果。</p>
        </div>
      </details>
    </main>
  );
}
