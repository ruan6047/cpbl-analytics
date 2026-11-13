"use client";

// PitchMind 概念展演頁（#452）：完全靜態、不呼叫 API。
// 主畫面唯一可操作的業務選項是「戰術」；局面、情境標籤、戰術說明標籤都是系統顯示。
// 「展演重播控制」是展演用的事件推進，與正式操作分開標示。

import { useEffect, useState } from "react";
import { Card, Notice } from "@/components/ui";
import { DependencyMark, GameSituation } from "@/components/postmark";
import { ContextSwitcher } from "@/components/hierarchical-tabs";
import { ZoneScatter, type ZonePoint } from "@/components/zone-scatter";
import { Grid3x3 } from "@/components/perf-heatmap";
import {
  COUNT_TAGS, accumulateAt, baselineCell, batterPaResults, countKey, countTag, currentPaPitches, situationAt,
  type Cell,
} from "./accumulate.ts";
import {
  DEMO_BASELINES, DEMO_BATTER_WITH_BASELINE, DEMO_EVENTS, DEMO_LONG_POINTS, DEMO_MATCHUP, DEMO_MIN_N, REPLAY_START,
} from "./demo-data.ts";
import { ALL_TAGS, FAMILY_ZH, H_ZH, REACTIONS, SOURCES, TACTICS, V_ZH, type Tactic } from "./tactics.config.ts";
import type { GameEvent, ReactionKey } from "./model.ts";

const LAST = DEMO_EVENTS.length - 1;
const TACTIC_IDS = TACTICS.map((t) => t.id);
const pct = (r: number) => `${Math.round(r * 100)}%`;
const half = (h: "top" | "bottom") => (h === "top" ? "上" : "下");

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
function CellView({ cell, reaction }: { cell: Cell | { state: "missing"; why: string }; reaction: ReactionKey }) {
  const denLabel = REACTIONS[reaction].denLabel;
  if (cell.state === "missing") {
    return <div><DependencyMark>缺值／待補</DependencyMark>
      {"why" in cell && <div className="mt-0.5 text-[11px] text-faint">{cell.why}</div>}</div>;
  }
  if (cell.state === "insufficient") {
    return <div><span className="pm-st pm-st--sample pm-st--sm">樣本不足</span>
      <div className="mt-0.5 text-[11px] text-faint">{denLabel} n={cell.n}（未達示意門檻 {DEMO_MIN_N}）</div></div>;
  }
  if (cell.state === "zero") {
    return <div><span className="font-mono text-sm font-bold tabular-nums text-ink">觀察到 0 次</span>
      <div className="mt-0.5 text-[11px] text-faint">0 / {cell.n} {denLabel}</div></div>;
  }
  return <div><span className="font-mono text-base font-bold tabular-nums text-ink">{pct(cell.rate)}</span>
    <div className="mt-0.5 text-[11px] text-faint">{cell.k} / {cell.n} {denLabel}</div></div>;
}

// ───────── 目標區域示意（與進壘點圖同座標：捕手視角）─────────
function TargetZone({ tactic }: { tactic: Tactic }) {
  const W = 120, H = 124, pad = 8;
  const xMin = -0.5, xMax = 0.5, yMin = 0.15, yMax = 1.35;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin)) * (H - 2 * pad);
  const hx: Record<string, [number, number]> = { inside: [-0.35, -0.07], middle: [-0.07, 0.07], outside: [0.07, 0.35] };
  const vy: Record<string, [number, number]> = { high: [0.83, 1.15], mid: [0.67, 0.83], low: [0.3, 0.67] };
  const [x0, x1] = [Math.min(...tactic.condition.h.map((h) => hx[h][0])), Math.max(...tactic.condition.h.map((h) => hx[h][1]))];
  const [y0, y1] = [Math.min(...tactic.condition.v.map((v) => vy[v][0])), Math.max(...tactic.condition.v.map((v) => vy[v][1]))];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-28" role="img"
      aria-label={`目標區域示意：${tactic.condition.text}`}>
      <rect x={sx(-0.21)} y={sy(1.0)} width={sx(0.21) - sx(-0.21)} height={sy(0.5) - sy(1.0)}
        className="fill-surface-2 stroke-faint" strokeWidth={1} />
      <rect x={sx(x0)} y={sy(y1)} width={sx(x1) - sx(x0)} height={sy(y0) - sy(y1)}
        className="fill-accent/25 stroke-accent" strokeWidth={1.4} strokeDasharray="3 2" />
      <text x={W / 2} y={H - 1} textAnchor="middle" className="fill-faint" fontSize={8}>捕手視角・右打外角在右</text>
    </svg>
  );
}

export function PitchMindDemo() {
  const [tacticId, setTacticId] = useState<string>(TACTICS[0].id);
  const [idx, setIdx] = useState(REPLAY_START);
  const [playing, setPlaying] = useState(false);
  const tactic = TACTICS.find((t) => t.id === tacticId) ?? TACTICS[0];

  // 播放到最後一個事件自動停；計時器只推進索引，累積仍由索引推導。
  const isPlaying = playing && idx < LAST;
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setTimeout(() => {
      setIdx((i) => Math.min(LAST, i + 1));
      if (idx + 1 >= LAST) setPlaying(false);
    }, 2200);
    return () => clearTimeout(timer);
  }, [isPlaying, idx]);

  const { situation: s, cutoff } = situationAt(DEMO_EVENTS, idx);
  const tag = countTag(s.balls, s.strikes);
  const ck = countKey(s.balls, s.strikes);
  const hasBatterBaseline = s.batter === DEMO_BATTER_WITH_BASELINE;
  const acc = accumulateAt(DEMO_EVENTS, idx, tactic, DEMO_BASELINES, DEMO_MIN_N);
  const pa = currentPaPitches(DEMO_EVENTS, idx, tactic);
  const priorPas = batterPaResults(DEMO_EVENTS, idx, s.batter);
  const longPts = DEMO_LONG_POINTS.filter((p) => p.family === tactic.condition.family);
  const mu = DEMO_MATCHUP.byTactic[tactic.id];
  // 打席剛結束、下一位打者尚未投球時，對照區顯示剛結束的那個打席並標明已結束。
  const paBatter = pa[0]?.pre.batter ?? s.batter;
  const paEnded = paBatter !== s.batter;
  const paPoints: ZonePoint[] = pa.map((p) => ({ x: p.event.x, y: p.event.y, sw: p.event.swing, wh: p.event.whiff, result: p.event.zoneResult }));
  const replayPos = idx - REPLAY_START + 1, replayTotal = LAST - REPLAY_START + 1;

  return (
    <main className="mx-auto max-w-[1280px] space-y-4 px-4 py-5">
      {/* 頁首 + 示意聲明 */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold tracking-[0.04em] text-ink">PitchMind 情蒐展演</h1>
        <span className="pm-st pm-st--hold">示意資料</span>
        <span className="text-xs text-muted">概念展演・非正式頁面</span>
      </div>
      <Notice label="示意資料">
        本頁全部為虛構示意：球員匿名（打者 A、投手 B…），數字為手編示意值，不代表任何真實球員、比賽，
        也不代表 PitchMind 已有驗證過的戰術評估。本頁不顯示戰術有效率或被識破機率，門檻一律「待研究」。
      </Notice>

      {/* 展演重播控制（與正式操作分開） */}
      <section aria-label="展演重播控制" className="rounded-md border-2 border-dashed border-line-strong px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="text-sm font-bold text-ink">展演重播控制
            <span className="ml-2 text-xs font-normal text-muted">僅供展演推進事件；正式賽中由資料自動更新</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => { setPlaying(false); setIdx(REPLAY_START); }} disabled={idx === REPLAY_START}
              className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">回到起點</button>
            <button type="button" onClick={() => { setPlaying(false); setIdx((i) => Math.max(REPLAY_START, i - 1)); }} disabled={idx === REPLAY_START}
              className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">上一球</button>
            <button type="button" onClick={() => setPlaying((p) => !p)} disabled={idx >= LAST} aria-pressed={isPlaying}
              className="min-h-11 rounded-md bg-ink px-4 text-sm font-bold text-paper disabled:opacity-40">{isPlaying ? "暫停" : "播放"}</button>
            <button type="button" onClick={() => { setPlaying(false); setIdx((i) => Math.min(LAST, i + 1)); }} disabled={idx >= LAST}
              className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">下一球</button>
          </div>
          <span className="font-mono text-xs tabular-nums text-muted" data-testid="replay-pos">事件 {replayPos} / {replayTotal}</span>
        </div>
      </section>

      {/* 頂部情境（系統顯示，不可點選） */}
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
          <div className="min-w-0 basis-full text-xs text-muted md:basis-auto md:ml-auto md:text-right">
            <div>資料截至</div>
            <div className="font-medium text-ink" data-testid="cutoff">{cutoffText(cutoff)}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">情境（系統判定・投手觀點）</span>
          <ul className="flex flex-wrap gap-1.5" aria-label="情境標籤">
            {COUNT_TAGS.map((t) => <StateTag key={t} active={t === tag}>{t}</StateTag>)}
          </ul>
          {tag == null && <span className="text-xs text-faint">{ck} 為平球數，四類皆不適用</span>}
        </div>
      </Card>

      {/* 戰術選擇（唯一可切換的業務選項）＋說明標籤 */}
      <Card padding="px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <ContextSwitcher label="戰術" values={TACTIC_IDS} value={tacticId}
            render={(id) => TACTICS.find((t) => t.id === id)?.name ?? id} onChange={setTacticId} />
          <div className="text-xs text-muted">來球條件：<span className="font-medium text-ink">{tactic.condition.text}</span></div>
          <ul className="flex flex-wrap gap-1.5 md:ml-auto" aria-label="戰術說明標籤（隨戰術自動帶出）">
            {ALL_TAGS.map((t) => <StateTag key={t} round active={tactic.tags.includes(t)}>{t}</StateTag>)}
          </ul>
        </div>
        <ul className="mt-2 space-y-0.5 text-xs text-muted">
          {tactic.tags.map((t) => <li key={t}><b className="text-ink">{t}</b>：{tactic.tagNotes[t]}</li>)}
        </ul>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* 左：情蒐資料、對戰紀錄、既有來球圖表 */}
        <Card className="space-y-4">
          <h2 className="text-base font-bold text-ink">情蒐資料・對戰紀錄</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs">
              <div className="mb-1 font-medium text-ink">{s.batter} 對 {s.pitcher}・過往</div>
              {hasBatterBaseline ? (
                <>
                  <div className="text-muted">{DEMO_MATCHUP.period}</div>
                  <div className="mt-1 font-mono tabular-nums text-ink">{DEMO_MATCHUP.pa} 打席・{DEMO_MATCHUP.hits} 安打・{DEMO_MATCHUP.so} 三振・{DEMO_MATCHUP.bb} 保送</div>
                  {mu && <div className="mt-1 text-muted">其中「{tactic.name}」條件來球 <b className="text-ink">{mu.pitches}</b> 球：
                    {tactic.reactions.map((r) => `${REACTIONS[r].label} ${r === "swing" ? mu.swing : mu[r]}`).join("、")}
                    <span className="text-faint">（原始次數，未換算比例）</span></div>}
                </>
              ) : <DependencyMark>缺值／待補：示意資料未建 {s.batter} 對戰紀錄</DependencyMark>}
            </div>
            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs">
              <div className="mb-1 font-medium text-ink">{s.batter}・本場已結束打席</div>
              {priorPas.length ? (
                <ul className="space-y-0.5 text-ink">{priorPas.map((p, i) => <li key={i}>{p.inning} 局：{p.text}</li>)}</ul>
              ) : <span className="text-faint">本場尚無已結束打席（0 個）</span>}
            </div>
          </div>
          <div>
            <h3 className="mb-1 text-sm font-medium text-muted">來球位置・{FAMILY_ZH[tactic.condition.family]}族群（{s.batter === DEMO_BATTER_WITH_BASELINE ? `${DEMO_BATTER_WITH_BASELINE} 長期` : "示意打者 A 長期"}，{longPts.length} 球）</h3>
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
              <div className="mx-auto w-full max-w-[300px]"><ZoneScatter points={longPts} staticLegend /></div>
              <div className="flex flex-col items-center gap-1 pt-2">
                <TargetZone tactic={tactic} />
                <div className="text-center text-[11px] text-muted">目標區域<br />{tactic.name}</div>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-[minmax(0,180px)_minmax(0,1fr)] items-center gap-3">
            <Grid3x3 points={longPts} metric={tactic.heatMetric.metric} title={`${tactic.heatMetric.title}・${FAMILY_ZH[tactic.condition.family]}`} />
            <p className="text-[11px] leading-relaxed text-faint">
              既有好球帶熱區元件，套用示意來球點；白＝此打者此族群均值，每格樣本不足 3 顯「—」。
              圖中的色差只描述分布，不代表戰術成敗。
            </p>
          </div>
        </Card>

        {/* 右：情蒐依據 ｜ 動態累積（並列） */}
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="space-y-3">
            <div>
              <h2 className="text-base font-bold text-ink">情蒐依據</h2>
              <p className="mt-0.5 text-xs text-muted">相似條件的長期與近期反應。比較條件：
                <span className="font-medium text-ink" data-testid="scout-cond">{tactic.condition.text}・球數 {ck}・對右投</span></p>
            </div>
            <div className="space-y-2" data-testid="scout-rows">
              {tactic.scoutingSources.map((src) => {
                const meta = SOURCES[src];
                const entry = DEMO_BASELINES[tactic.id]?.[src]?.[ck] ?? null;
                const noBatter = meta.scope === "batter" && !hasBatterBaseline;
                return (
                  <div key={src} className="rounded-md bg-surface-2 px-3 py-2">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                      <span className="text-sm font-medium text-ink">{meta.label}</span>
                      <span className="text-[11px] text-faint">{meta.period}</span>
                    </div>
                    <div className="mt-1.5 grid grid-cols-2 gap-2">
                      {tactic.reactions.map((r) => (
                        <div key={r}>
                          <div className="text-[11px] text-muted">{REACTIONS[r].label}</div>
                          <CellView reaction={r} cell={noBatter
                            ? { state: "missing", why: `示意資料未建 ${s.batter}` }
                            : entry == null && src === "pitcher"
                              ? { state: "missing", why: "投手此分項尚未接入" }
                              : baselineCell(entry, r, DEMO_MIN_N)} />
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="text-[11px] leading-relaxed text-faint">
              每格附分母與條件；未達門檻顯示「樣本不足」，不以其他球數或舊值補上。樣本門檻 {DEMO_MIN_N} 為示意設定，實際門檻待研究。
              指標各自獨立，不加總、不排序。
            </p>
          </Card>

          <Card className="space-y-3">
            <div>
              <h2 className="text-base font-bold text-ink">動態累積</h2>
              <p className="mt-0.5 text-xs text-muted">本場符合「{tactic.name}」條件的實際來球與反應（截至上方事件）</p>
            </div>
            <div className="rounded-md bg-surface-2 px-3 py-2" data-testid="dyn-batter">
              <div className="text-sm font-medium text-ink">{s.batter}・本場</div>
              {acc.batter.opp === 0 ? (
                <div className="mt-1 text-xs text-ink">符合條件機會：<b>0 次</b><span className="ml-1 text-faint">（本場尚未遇到這類來球，非缺值）</span></div>
              ) : (
                <div className="mt-1 space-y-0.5 text-xs text-ink">
                  <div>符合條件機會：<b className="font-mono tabular-nums">{acc.batter.opp}</b> 次</div>
                  {tactic.reactions.map((r) => {
                    const x = acc.batter.reactions[r];
                    return <div key={r}>{REACTIONS[r].label}：<b className="font-mono tabular-nums">{x.k}</b> / {x.den} {REACTIONS[r].denLabel}
                      {x.den === 0 && <span className="ml-1 text-faint">（分母 0，無法計算比例）</span>}</div>;
                  })}
                </div>
              )}
            </div>
            <div className="rounded-md bg-surface-2 px-3 py-2">
              <div className="text-sm font-medium text-ink">相對預期變化</div>
              <div className="text-[11px] text-faint">預期＝逐次機會依該球精確球數的打者長期基準加總</div>
              {!hasBatterBaseline ? (
                <div className="mt-1"><DependencyMark>缺值／待補：示意資料未建 {s.batter} 長期基準</DependencyMark></div>
              ) : acc.batter.opp === 0 ? (
                <div className="mt-1 text-xs text-faint">尚無機會可比較</div>
              ) : (
                <ul className="mt-1 space-y-1 text-xs text-ink" data-testid="dyn-expected">
                  {tactic.reactions.map((r) => {
                    const x = acc.expected[r];
                    return (
                      <li key={r}>{REACTIONS[r].label}：觀察 <b className="font-mono tabular-nums">{x.observed}</b> 次｜
                        {x.used ? <>預期 <b className="font-mono tabular-nums">{x.expected.toFixed(1)}</b> 次（{x.used} 次機會有基準）</> : "無可用基準"}
                        {x.skipped > 0 && <div className="text-[11px] text-faint">另 {x.skipped} 次機會的基準樣本不足，未納入預期</div>}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <div className="rounded-md bg-surface-2 px-3 py-2 text-xs">
              <div className="text-sm font-medium text-ink">隊友共同反應</div>
              <div className="mt-1 text-ink">同場其他打者對{s.pitcher}：機會 <b className="font-mono tabular-nums">{acc.teammates.opp}</b> 次、
                出棒 <b className="font-mono tabular-nums">{acc.teammates.reactions.swing.k}</b> 次</div>
              <div className="mt-0.5 text-[11px] text-faint">原始次數；多位打者同向不代表隊伍戰術</div>
            </div>
            <ul className="space-y-0.5 text-[11px] text-muted">
              <li>提示門檻：<b className="text-ink">待研究</b>（本頁不判定是否偏離）</li>
              <li>資料截至上方事件；尚未到達的事件為未知，不推定為最新</li>
            </ul>
          </Card>
        </div>
      </div>

      {/* 我方投手實際來球對照 */}
      <Card className="space-y-3">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="text-base font-bold text-ink">我方投手實際來球對照</h2>
          <span className="text-xs text-muted" data-testid="pa-scope">{s.pitcher} 對 {paBatter}・{paEnded ? "上一打席（已結束）" : "本打席"}・依目前戰術「{tactic.name}」條件比對</span>
        </div>
        {pa.length === 0 ? (
          <p className="text-xs text-faint">本打席尚無投球（0 球）</p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
            <div className="overflow-x-auto">
              <p className="mb-2 text-xs text-ink" data-testid="pa-summary">{paEnded ? "該打席" : "本打席"} {pa.length} 球中 <b>{pa.filter((p) => p.matched).length}</b> 球符合條件</p>
              <table className="w-full min-w-[560px] text-left text-xs">
                <thead className="bg-band text-muted">
                  <tr>{["球序", "投出前球數", "球種族群", "位置", "球速", "與前一球差", "符合條件", "打者反應"].map((h) =>
                    <th key={h} scope="col" className="px-2 py-1.5 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {pa.map((p) => (
                    <tr key={p.event.id} className="border-b border-line">
                      <td className="px-2 py-1.5 font-mono tabular-nums">{p.event.seq}</td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">{p.pre.balls}-{p.pre.strikes}</td>
                      <td className="px-2 py-1.5">{FAMILY_ZH[p.event.family]}</td>
                      <td className="px-2 py-1.5">{H_ZH[p.event.h]}{V_ZH[p.event.v]}</td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">{p.event.speed} km/h</td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">{p.speedDiff == null ? "—（首球）" : `${p.speedDiff > 0 ? "+" : ""}${p.speedDiff}`}</td>
                      <td className="px-2 py-1.5">{p.matched ? <b className="text-ink">符合</b> : <span className="text-faint">不符合</span>}</td>
                      <td className="px-2 py-1.5">{p.event.resultText}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-[11px] text-faint">實投符合條件不等於已知投捕當時意圖；球速差為示意實測欄位，差異是否帶來效果另需驗證。</p>
            </div>
            <div>
              <h3 className="mb-1 text-sm font-medium text-muted">{paEnded ? "該打席" : "本打席"}進壘點（{pa.length} 球）</h3>
              <div className="mx-auto w-full max-w-[260px]"><ZoneScatter points={paPoints} staticLegend /></div>
            </div>
          </div>
        )}
      </Card>

      {/* 資料說明 */}
      <Card className="text-xs text-muted">
        <h2 className="mb-1 text-sm font-bold text-ink">資料說明</h2>
        <ul className="list-disc space-y-0.5 pl-5">
          <li>實測：無。本頁未接任何正式資料來源或研究檔。</li>
          <li>示意（手編）：事件序列、情蒐基準、對戰紀錄、長期來球點（固定種子產生）、球速。</li>
          <li>待補：共軌所需的逐球軌跡、投手內角低變化球分項、打者 A 以外的打者基準、正式樣本門檻與提示門檻（待研究）。</li>
          <li>狀態用語：「缺值／待補」＝資料未接入；「觀察到 0 次」＝有足夠樣本但未發生；「樣本不足」＝分母未達門檻，不顯示比例。</li>
        </ul>
      </Card>
    </main>
  );
}
