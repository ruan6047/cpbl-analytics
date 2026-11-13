"use client";

// PitchMind 概念展演頁（#452 修正二）：完全靜態、不呼叫 API。
// 版型＝頂部情境與戰術選擇 → 三欄（情蒐資料／對戰紀錄｜情蒐指標｜動態指標）→ 我方投手量測對照
// → 可展開的逐球與詳細證據。情蒐指標與動態指標兩欄上方各有一塊快讀摘要。
// 主畫面唯一可操作的業務選項是「查看戰術」；「展演控制」只推進事先寫好的合成劇本。

import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { DependencyMark, GameSituation } from "@/components/postmark";
import { ContextSwitcher } from "@/components/hierarchical-tabs";
import { ZoneScatter, type ZonePoint } from "@/components/zone-scatter";
import { Grid3x3 } from "@/components/perf-heatmap";
import {
  COUNT_TAGS, baselineCell, baselineEntry, batterPaResults, completedPaSummary, countKey, countTag,
  currentPaPitches, dynamicAt, lastPitchContext, pitcherMeasure, situationAt,
  type Cell, type PaPitch,
} from "./accumulate.ts";
import {
  DEMO_BASELINES, DEMO_EVENTS, DEMO_LONG_POINTS, DEMO_MATCHUP, DEMO_MIN_N, DEMO_PITCHER_REF_SPEED, REPLAY_START,
} from "./demo-data.ts";
import { ALL_TAGS, H_ZH, REACTIONS, SOURCES, TACTICS, V_ZH, type Tactic } from "./tactics.config.ts";
import type { GameEvent, ReactionKey } from "./model.ts";

const LAST = DEMO_EVENTS.length - 1;
const TACTIC_IDS = TACTICS.map((t) => t.id);
const pct = (r: number) => `${Math.round(r * 100)}%`;
const half = (h: "top" | "bottom") => (h === "top" ? "上" : "下");
/** 帶正負號、一位小數；不輸出 −0.0。 */
function signed1(v: number): string {
  const r = Math.round(v * 10) / 10;
  return r > 0 ? `+${r.toFixed(1)}` : r < 0 ? `−${Math.abs(r).toFixed(1)}` : "0.0";
}

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

// ───────── 基準格：四態互斥，各自不同文字 ─────────
function CellView({ cell, reaction }: { cell: Cell; reaction: ReactionKey }) {
  const denLabel = REACTIONS[reaction].denLabel;
  if (cell.state === "missing") return <div><DependencyMark>缺值／待補</DependencyMark></div>;
  if (cell.state === "insufficient") {
    return <div><span className="pm-st pm-st--sample pm-st--sm">樣本不足</span>
      <div className="mt-0.5 text-[11px] text-faint">{denLabel} n={cell.n}</div></div>;
  }
  if (cell.state === "zero") {
    return <div><span className="font-mono text-sm font-bold tabular-nums text-ink">觀察到 0 次</span>
      <div className="mt-0.5 text-[11px] text-faint">0 / {cell.n}</div></div>;
  }
  return <div><span className="font-mono text-base font-bold tabular-nums text-ink">{pct(cell.rate)}</span>
    <div className="mt-0.5 text-[11px] text-faint">{cell.k} / {cell.n}</div></div>;
}
const cellShort = (c: Cell) =>
  c.state === "ok" ? pct(c.rate) : c.state === "zero" ? "0%" : c.state === "insufficient" ? "樣本不足" : "缺值";

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
      <table className="w-full min-w-[620px] text-left text-xs">
        <thead className="bg-band text-muted">
          <tr>{["球序", "投出前球數", "球種", "位置", "球速", "與前一球差", "結果", `對「${tactic.name}」`].map((h) =>
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
              <td className="px-2 py-1.5">{p.event.resultText}</td>
              <td className="px-2 py-1.5">{p.inclusion.included
                ? <b className="text-ink">納入</b>
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
  const primary = tactic.reactions[0];

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
  const ck = countKey(s.balls, s.strikes);
  const dyn = dynamicAt(DEMO_EVENTS, idx, tactic, DEMO_BASELINES, DEMO_MIN_N);
  const ctx = lastPitchContext(DEMO_EVENTS, idx);
  const paDone = completedPaSummary(DEMO_EVENTS, idx, tactic, DEMO_BASELINES, DEMO_MIN_N);
  const pa = currentPaPitches(DEMO_EVENTS, idx, tactic);
  const priorPas = batterPaResults(DEMO_EVENTS, idx, s.batter);
  const measure = pitcherMeasure(DEMO_EVENTS, idx, tactic);
  const matchup = DEMO_MATCHUP[s.batter];
  const mu = matchup?.byTactic[tactic.id];
  const longPts = (DEMO_LONG_POINTS[s.batter] ?? []).filter((p) => p.pitch === tactic.condition.pitch);
  const measurePoints: ZonePoint[] = measure.points.map((p) => ({ x: p.x, y: p.y, sw: p.swing, wh: p.whiff, result: p.zoneResult }));
  const replayPos = idx - REPLAY_START + 1, replayTotal = LAST - REPLAY_START + 1;

  // 情蒐參考（快讀）：打者長期在「所選戰術＋目前精確球數」的首要關注反應
  const refCell = baselineCell(baselineEntry(DEMO_BASELINES, tactic.id, "long", s.batter, ck), primary, DEMO_MIN_N);
  const prevCk = ctx ? countKey(ctx.pre.balls, ctx.pre.strikes) : null;
  const prevRefCell = ctx && ctx.sameBatter && prevCk && prevCk !== ck
    ? baselineCell(baselineEntry(DEMO_BASELINES, tactic.id, "long", s.batter, prevCk), primary, DEMO_MIN_N) : null;

  const justChanged = flash === idx && dyn.last.kind === "included";
  const lastObs = dyn.last.kind === "included" ? dyn.last.observation : null;
  const reactionLabel = REACTIONS[primary].label;

  return (
    <main className="mx-auto max-w-[1280px] space-y-4 px-4 py-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold tracking-[0.04em] text-ink">PitchMind 情蒐展演</h1>
        <span className="pm-st pm-st--hold">示意資料</span>
        <span className="text-xs text-muted">合成劇本・匿名球員・壘上無人</span>
      </div>

      {/* 展演控制（與正式操作分開） */}
      <section aria-label="展演控制" className="rounded-md border-2 border-dashed border-line-strong px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="text-sm font-bold text-ink">展演控制
            <span className="ml-2 text-xs font-normal text-muted">推進合成劇本；正式賽中由資料自動更新</span>
          </div>
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
        <p className="mt-1.5 text-xs text-muted" data-testid="script">劇本步驟（以外角高速球為主線）：{cutoff.script ?? "—"}</p>
      </section>

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
          <div className="text-xs text-muted">條件：<span className="font-medium text-ink">{tactic.condition.text}</span></div>
          <div className="text-xs text-muted">目的：<span className="font-medium text-ink">{tactic.purpose}</span></div>
          <ul className="flex flex-wrap gap-1.5 md:ml-auto" aria-label="戰術說明標籤（隨戰術帶出）">
            {ALL_TAGS.map((t) => <StateTag key={t} round active={tactic.tags.includes(t)}>{t}</StateTag>)}
          </ul>
        </div>
        <p className="mt-1.5 text-[11px] text-faint">切換只改變三欄查看的戰術，不代表教練已採用；戰術與標籤對應為示意。</p>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* 欄一：情蒐資料／對戰紀錄（原有圖表與資料） */}
        <Card className="space-y-4">
          <h2 className="text-base font-bold text-ink" data-testid="left-title">情蒐資料・對戰紀錄<span className="ml-2 text-xs font-normal text-muted">{s.batter}</span></h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs">
              <div className="mb-1 font-medium text-ink">{s.batter} 對 {s.pitcher}・過往</div>
              {matchup ? (
                <>
                  <div className="text-muted">{matchup.period}</div>
                  <div className="mt-1 font-mono tabular-nums text-ink">{matchup.pa} 打席・{matchup.hits} 安打・{matchup.so} 三振・{matchup.bb} 保送</div>
                  {mu && <div className="mt-1 text-muted">其中「{tactic.name}」條件來球 <b className="text-ink">{mu.pitches}</b> 球：
                    {tactic.reactions.map((r) => `${REACTIONS[r].label} ${mu[r]}`).join("、")}</div>}
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
            <p className="text-[11px] leading-relaxed text-faint">白＝此打者此球種均值；每格樣本少於 3 顯「—」。色差只描述分布。</p>
          </div>
        </Card>

        <div className="grid gap-4 md:grid-cols-2">
          {/* 欄二：情蒐指標（上：快讀摘要；下：歷史與近況依據） */}
          <Card className="space-y-3">
            <h2 className="text-base font-bold text-ink">情蒐指標</h2>
            <div className="rounded-md bg-surface-2 px-3 py-3" data-testid="scout-quick">
              <div className="text-xs font-medium text-muted">情蒐參考・{s.batter} 長期</div>
              <div className="mt-0.5 flex items-baseline gap-2">
                <span className="text-sm font-bold text-ink">{reactionLabel}</span>
                <span className="font-mono text-4xl font-black tabular-nums leading-none text-ink">{cellShort(refCell)}</span>
              </div>
              <div className="mt-1 text-xs text-muted">
                {refCell.state === "missing" ? "此條件沒有資料" : `${refCell.k} / ${refCell.n} 球・`}{tactic.name}・球數 <b className="text-ink">{ck}</b>
              </div>
              {prevRefCell && prevCk && (
                <p className="mt-1.5 text-[11px] leading-snug text-ink" data-testid="ctx-note">
                  球數 {prevCk} → {ck}：參考由 {cellShort(prevRefCell)} 改為 {cellShort(refCell)}，是情境不同，不是打者反應改變。
                </p>
              )}
              {ctx && !ctx.sameBatter && (
                <p className="mt-1.5 text-[11px] leading-snug text-ink" data-testid="ctx-note">
                  打者由{ctx.pre.batter} 換為{s.batter}：參考改用{s.batter} 自己的資料，不沿用前一位。
                </p>
              )}
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
                    <div className="mt-1.5 grid grid-cols-2 gap-2">
                      {tactic.reactions.map((r) => (
                        <div key={r}>
                          <div className="text-[11px] text-muted">{REACTIONS[r].label}</div>
                          <CellView reaction={r} cell={baselineCell(entry, r, DEMO_MIN_N)} />
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="text-[11px] text-faint">分母＝此條件（戰術＋球數 {ck}）的來球數。</p>
          </Card>

          {/* 欄三：動態指標（上：目前示意值與本次增減；下：本場相關觀察） */}
          <Card className="space-y-3">
            <h2 className="text-base font-bold text-ink">動態指標</h2>
            <div data-testid="dyn-quick" data-flash={justChanged ? "1" : "0"}
              className={`rounded-md bg-surface-2 px-3 py-3 ring-2 ${justChanged ? "ring-ink" : "ring-transparent"}`}>
              <div className="text-xs font-medium text-muted">本場變化・{s.batter}・相對情蒐預期</div>
              {dyn.opp === 0 ? (
                <div className="mt-1 text-sm text-ink">本場尚無符合條件的來球（0 次）</div>
              ) : (
                <>
                  <div className="mt-0.5 flex items-baseline gap-2">
                    <span className="text-sm font-bold text-ink">{reactionLabel}</span>
                    <span className="font-mono text-4xl font-black tabular-nums leading-none text-ink" data-testid="dyn-value">{signed1(dyn.value)}</span>
                    <span className="text-sm text-muted">次</span>
                  </div>
                  <div className="mt-1 text-xs text-muted">
                    觀察 <b className="text-ink">{dyn.observed}</b> 次・預期 <b className="text-ink">{dyn.expected.toFixed(1)}</b> 次・{dyn.used} 球符合條件
                  </div>
                </>
              )}
              <div className="mt-2 text-xs" data-testid="dyn-last">
                {dyn.last.kind === "included" && lastObs && (
                  <>
                    <span className="mr-2 inline-flex items-center rounded-sm bg-ink px-1.5 py-0.5 font-mono font-bold tabular-nums text-paper">
                      本次 {lastObs.delta == null ? "無基準" : `${lastObs.delta > 0 ? "↑" : "↓"} ${signed1(lastObs.delta)}`}
                    </span>
                    <span className="text-ink">
                      第 {lastObs.seq} 球{tactic.name}，{lastObs.reacted ? `打者${reactionLabel}` : `打者未${reactionLabel}`}（{lastObs.resultText}）；
                      {lastObs.count} 時長期{reactionLabel} {lastObs.expectedRate == null ? "無基準" : pct(lastObs.expectedRate)}。
                    </span>
                  </>
                )}
                {dyn.last.kind === "excluded" && <span className="font-medium text-ink">{dyn.last.text}</span>}
                {dyn.last.kind === "other_batter" && <span className="text-ink">上一球屬於{dyn.last.batter} 的打席，不計入{s.batter}。</span>}
                {dyn.last.kind === "none" && <span className="text-faint">打者剛上場，本打席尚無投球。</span>}
              </div>
            </div>

            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs" data-testid="dyn-obs">
              <div className="text-sm font-medium text-ink">{s.batter}・本場相關觀察</div>
              <div className="mt-1 space-y-0.5 text-ink">
                <div>符合條件來球：<b className="font-mono tabular-nums">{dyn.opp}</b> 球
                  （本打席 {dyn.currentPaOpp}{dyn.priorInnings.length > 0 && `、先前打席 ${dyn.opp - dyn.currentPaOpp}`}）</div>
                {tactic.reactions.map((r) => (
                  <div key={r}>{REACTIONS[r].label}：<b className="font-mono tabular-nums">{dyn.tally[r]}</b> / {dyn.opp}</div>
                ))}
              </div>
              {dyn.priorInnings.length > 0 && (
                <div className="mt-1 text-[11px] text-faint">來源：含{s.batter} 本場 {dyn.priorInnings.join("、")} 局的打席，只算他自己的球。</div>
              )}
            </div>

            {ctx && ctx.sameBatter && (
              <div className="rounded-md bg-surface-2 px-3 py-2 text-xs text-ink" data-testid="ctx-box">
                <div>上一球：第 {ctx.event.seq} 球，投出前 <b className="font-mono">{ctx.pre.balls}-{ctx.pre.strikes}</b>
                  {dyn.last.kind === "included" ? `（觀察記在 ${ctx.pre.balls}-${ctx.pre.strikes}）` : "（未納入）"}</div>
                <div>目前情境：<b className="font-mono">{ck}</b>（情蒐參考用 {ck} 的資料）</div>
              </div>
            )}

            {paDone && (
              <div className="rounded-md bg-surface-2 px-3 py-2 text-xs" data-testid="pa-done">
                <div className="text-sm font-medium text-ink">剛結束打席摘要・{paDone.batter}</div>
                <div className="mt-1 text-ink">{paDone.inning} 局・{paDone.pitches} 球・{paDone.resultText}</div>
                <div className="text-ink">{tactic.name} {paDone.includedCount} 球，{reactionLabel} {paDone.reactedCount} 次；
                  本場變化 {signed1(paDone.valueBefore)} → {signed1(paDone.valueAfter)}</div>
                <div className="mt-0.5 text-[11px] text-faint">供轉達用；屬於{paDone.batter}，不計入{s.batter}。</div>
              </div>
            )}

            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs" data-testid="teammates">
              <div className="text-sm font-medium text-ink">隊友共同反應<span className="ml-1 text-[11px] font-normal text-faint">獨立欄位</span></div>
              <div className="mt-1 text-ink">{dyn.teammates.batters.join("、") || "其他打者"}：
                <b className="font-mono tabular-nums">{dyn.teammates.opp}</b> 球符合條件、{reactionLabel} <b className="font-mono tabular-nums">{dyn.teammates[primary]}</b> 次</div>
              <div className="mt-0.5 text-[11px] text-faint">原始次數，不計入{s.batter} 的數字。</div>
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

      {/* 可展開：本場相關觀察逐事件（取代曲線） */}
      <details className="card px-4 py-3">
        <summary className="cursor-pointer text-sm font-bold text-ink">本場相關觀察逐事件・{s.batter}・{tactic.name}（{dyn.observations.length} 筆）</summary>
        <p className="mt-2 text-xs text-muted">
          觀察對象：{s.batter}。對應戰術：{tactic.name}。每列是一顆符合條件的來球。
          數值意義：{reactionLabel}次數相對情蒐預期的差（示意），不是選手近況，也不是機率。
        </p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className="bg-band text-muted">
              <tr>{["局", "球序", "投出前球數", "反應", "該球數長期比例", "本次增減", "累計"].map((h) =>
                <th key={h} scope="col" className="px-2 py-1.5 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {dyn.observations.map((o) => (
                <tr key={o.eventId} className="border-b border-line">
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.inning}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.seq}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.count}</td>
                  <td className="px-2 py-1.5">{o.reacted ? reactionLabel : `未${reactionLabel}`}（{o.resultText}）</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.expectedRate == null ? "無基準" : pct(o.expectedRate)}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{o.delta == null ? "—" : signed1(o.delta)}</td>
                  <td className="px-2 py-1.5 font-mono tabular-nums">{signed1(o.cumulative)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {/* 可展開：展演說明（長篇方法與劇本規則集中在這裡） */}
      <details className="card px-4 py-3">
        <summary className="cursor-pointer text-sm font-bold text-ink">展演說明與示意規則</summary>
        <div className="mt-2 space-y-2 text-xs leading-relaxed text-muted">
          <p><b className="text-ink">示意資料：</b>全頁是完整合成的比賽流程劇本，球員匿名（打者 A、投手 B…），不代表真實球員或比賽，也不代表 PitchMind 已有驗證過的模型。只討論壘上無人。</p>
          <p><b className="text-ink">兩側快讀：</b>「情蒐參考」是打者長期在所選戰術與目前精確球數下的{reactionLabel}比例；「本場變化」是本場{reactionLabel}次數減去預期次數。兩者單位不同（比例與次數），並排只是比較方式的示意，不具統計可比性；兩者差多少都不代表戰術失效，也不是有效率、被識破機率或警戒線。是否調整由教練決定。</p>
          <div>
            <b className="text-ink">示意用的簡化（都不是已驗證方法；模型、刻度、權重、門檻未定案）：</b>
            <ol className="mt-1 list-decimal space-y-0.5 pl-5">
              <li>一球要球種、區域都符合所選戰術且壘上無人才納入；否則顯示未納入的原因。實投符合條件不等於已知投捕意圖。</li>
              <li>觀察只算目前打者自己的球，可含他本場先前打席並標明來源；其他打者只出現在隊友共同反應欄位。</li>
              <li>每筆觀察記在投出前的精確球數；之後球數改變不搬動它。球數改變時情蒐參考改用新球數的資料，這個變化來自情境，不是打者。</li>
              <li>本場變化＝各筆觀察（有反應 1、沒有 0）減去該球數的長期比例後相加。跨球數直接相加是簡化；跨情境如何共享累積尚未定案。</li>
              <li>增減由劇本安排的事件決定，包含讓數值回落的事件；不是已驗證公式。</li>
            </ol>
          </div>
          <p><b className="text-ink">劇本步驟：</b>A 打者上場；B 切換查看戰術（隨時可操作）；C 符合條件的新一球；D 不符合條件的新一球；E 2-2 變 3-2；F 打席結束換下一位打者；G 與預期方向相反的偏離縮小（回落）。展演控制區會標出目前事件對應哪一步（以外角高速球為主線）。</p>
          <p><b className="text-ink">說明標籤（{tactic.name}）：</b>{tactic.tags.map((t) => `${t}＝${tactic.tagNotes[t]}`).join("；")}。標籤隨戰術帶出，不代表已量測效果。</p>
          <p><b className="text-ink">投手量測：</b>只描述球速與實際進壘位置；沒有捕手原定目標，不判斷失投或是否投到預定位置。</p>
          <p><b className="text-ink">尚未完成：</b>1–2 秒快讀是設計目標，還沒有實際試讀結果。樣本多少才夠、共軌所需的軌跡資料、壘上有人時的處理都待研究。</p>
        </div>
      </details>
    </main>
  );
}
