"use client";

// PitchMind 概念展演頁（#452，2026-11-13 方向修正版）：完全靜態、不呼叫 API。
// 快讀區只回答四件事：所選戰術、情蒐參考值、動態累積值、離界線多遠與方向。
// 主畫面唯一可操作的業務選項是「戰術」；局面、情境與說明標籤都是系統顯示。
// 「展演控制」只推進事先設計的模擬序列，與正式操作分開標示。

import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { GameSituation } from "@/components/postmark";
import { ContextSwitcher } from "@/components/hierarchical-tabs";
import { ZoneScatter, type ZonePoint } from "@/components/zone-scatter";
import { pitchColor, useChartTheme } from "@/lib/chart-theme";
import {
  COUNT_TAGS, countTag, currentPaPitches, dynamicSeries, quickRead, situationAt, type Status,
} from "./accumulate.ts";
import { DEMO_EVENTS, REPLAY_START, SCRIPTED_ADVERSE_EVENT_ID } from "./demo-data.ts";
import { ALL_TAGS, DEMO_RULES, H_ZH, REACTION_ZH, TACTICS, V_ZH } from "./tactics.config.ts";
import type { GameEvent } from "./model.ts";

const LAST = DEMO_EVENTS.length - 1;
const TACTIC_IDS = TACTICS.map((t) => t.id);
const half = (h: "top" | "bottom") => (h === "top" ? "上" : "下");
const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");

const STATUS_TEXT: Record<Status, string> = { far: "距離尚遠", near: "正在接近", over: "已超過" };
const STATUS_TONE: Record<Status, { text: string; fill: string }> = {
  far: { text: "text-muted", fill: "fill-muted" },
  near: { text: "text-ink", fill: "fill-ink" },
  over: { text: "text-down", fill: "fill-down" },
};

function cutoffText(e: GameEvent): string {
  const s = e.after;
  if (e.kind === "pa_start") return `${e.label}（尚無本打席投球）`;
  return `${e.label}：${e.resultText}（${s.inning} 局${half(s.half)}）`;
}

// ───────── 狀態形狀：距離尚遠＝空心圓、正在接近＝三角、已超過＝實心方塊（不只靠顏色）─────────
function StatusShape({ status, x = 0, y = 0, size = 14, className = "" }: {
  status: Status; x?: number; y?: number; size?: number; className?: string;
}) {
  const h = size / 2;
  if (status === "far") return <circle cx={x} cy={y} r={h - 1} className={`fill-none stroke-current ${className}`} strokeWidth={2} />;
  if (status === "near") return <polygon points={`${x},${y - h} ${x + h},${y + h - 1} ${x - h},${y + h - 1}`} className={`fill-current ${className}`} />;
  return <rect x={x - h + 1} y={y - h + 1} width={size - 2} height={size - 2} className={`fill-current ${className}`} />;
}
function StatusIcon({ status, size = 22 }: { status: Status; size?: number }) {
  return (
    <svg width={size} height={size} viewBox={`${-size / 2} ${-size / 2} ${size} ${size}`} aria-hidden="true">
      <StatusShape status={status} size={size - 4} />
    </svg>
  );
}

// ───────── 不可操作的狀態標籤：無 button 語意、無 tabindex、無 hover／focus 樣式 ─────────
function StateTag({ active, round = false, children }: { active: boolean; round?: boolean; children: string }) {
  return (
    <li className={`inline-flex cursor-default select-none items-center gap-1 px-2 py-0.5 text-xs ${round ? "rounded-full" : "rounded-sm"} ${active
      ? "font-bold text-ink ring-2 ring-ink"
      : "text-faint ring-1 ring-line"}`}>
      {active && <span aria-hidden="true" className="inline-block h-1.5 w-1.5 rounded-full bg-ink" />}
      {children}
      {active && <span className="sr-only">（目前）</span>}
    </li>
  );
}

// ───────── 同尺度對照條：0–100 示意點數；參考線＋接近區＋動態值，兩個數字直接標在圖上 ─────────
function Gauge({ value, reference, prev, status }: { value: number; reference: number; prev: number | null; status: Status }) {
  const W = 640, L = 16, R = 16, trackY = 62, trackH = 22;
  const sx = (v: number) => L + ((v - DEMO_RULES.min) / (DEMO_RULES.max - DEMO_RULES.min)) * (W - L - R);
  const nearFrom = Math.max(DEMO_RULES.min, reference - DEMO_RULES.nearBand);
  const tone = STATUS_TONE[status];
  return (
    <svg viewBox={`0 0 ${W} 150`} className="w-full" role="img"
      aria-label={`同一示意尺度 0 到 100：情蒐參考值 ${reference}，動態累積值 ${value}，${STATUS_TEXT[status]}`}>
      <defs>
        <pattern id="pm-near-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" className="stroke-line-strong" strokeWidth="2" />
        </pattern>
      </defs>
      {/* 底軌 */}
      <rect x={sx(0)} y={trackY} width={sx(100) - sx(0)} height={trackH} rx={3} className="fill-surface-2" />
      {/* 接近區（斜線）與超過區 */}
      <rect x={sx(nearFrom)} y={trackY} width={sx(reference) - sx(nearFrom)} height={trackH} fill="url(#pm-near-hatch)" />
      <rect x={sx(reference)} y={trackY} width={sx(100) - sx(reference)} height={trackH} className="fill-down/10" />
      <text x={(sx(nearFrom) + sx(reference)) / 2} y={trackY + trackH + 14} textAnchor="middle" className="fill-faint" fontSize={11}>接近區</text>
      <text x={(sx(reference) + sx(100)) / 2} y={trackY + trackH + 14} textAnchor="middle" className="fill-faint" fontSize={11}>超過區</text>
      {/* 動態累積值 */}
      <rect x={sx(0)} y={trackY + 5} width={Math.max(0, sx(value) - sx(0))} height={trackH - 10} rx={2} className={tone.fill} />
      {prev != null && prev !== value && (
        <line x1={sx(prev)} x2={sx(prev)} y1={trackY - 2} y2={trackY + trackH + 2} className="stroke-faint" strokeWidth={2} strokeDasharray="2 2" />
      )}
      {/* 參考線（上方標數字） */}
      <line x1={sx(reference)} x2={sx(reference)} y1={22} y2={trackY + trackH + 4} className="stroke-ink" strokeWidth={3} />
      <text x={sx(reference)} y={16} textAnchor="middle" className="fill-ink" fontSize={14} fontWeight={700}>情蒐參考 {reference}</text>
      {/* 動態值標記（形狀＝狀態），下方標數字 */}
      <g className={tone.text}><StatusShape status={status} x={sx(value)} y={trackY + trackH / 2} size={16} className="stroke-surface" /></g>
      <text x={Math.min(sx(100) - 40, Math.max(sx(0) + 40, sx(value)))} y={trackY + trackH + 40} textAnchor="middle"
        className={status === "over" ? "fill-down" : "fill-ink"} fontSize={18} fontWeight={800}>動態累積 {value}</text>
      {/* 刻度 */}
      {[0, 50, 100].map((t) => (
        <text key={t} x={sx(t)} y={trackY - 6} textAnchor={t === 0 ? "start" : t === 100 ? "end" : "middle"} className="fill-faint" fontSize={10}>{t}</text>
      ))}
    </svg>
  );
}

// ───────── 走勢：每次符合條件的來球更新一點；參考線為階梯（隨球數改變）─────────
function Trend({ points, adverseIdx }: { points: { value: number; reference: number; eventIdx: number }[]; adverseIdx: number }) {
  const W = 640, H = 120, L = 28, R = 12, T = 10, B = 18;
  const n = Math.max(points.length, 2);
  const sx = (i: number) => L + (i / (n - 1)) * (W - L - R);
  const sy = (v: number) => T + (1 - v / 100) * (H - T - B);
  if (points.length === 0) return <p className="text-xs text-faint">此戰術尚無符合條件的來球（0 次更新）</p>;
  const refPath = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(i)},${sy(p.reference)}${i < points.length - 1 ? ` L${sx(i + 1)},${sy(p.reference)}` : ""}`).join(" ");
  const valPath = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(i)},${sy(p.value)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
      aria-label={`動態累積走勢，共 ${points.length} 次更新，最新 ${points[points.length - 1].value}`}>
      {[0, 50, 100].map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="stroke-line" strokeWidth={1} />
          <text x={L - 6} y={sy(t)} textAnchor="end" dominantBaseline="central" className="fill-faint" fontSize={10}>{t}</text>
        </g>
      ))}
      <path d={refPath} className="fill-none stroke-ink" strokeWidth={2} strokeDasharray="6 4" />
      <path d={valPath} className="fill-none stroke-accent" strokeWidth={2} />
      {points.map((p, i) => (
        <g key={p.eventIdx}>
          <circle cx={sx(i)} cy={sy(p.value)} r={i === points.length - 1 ? 5 : 3} className="fill-accent stroke-surface" strokeWidth={1.5} />
          {p.eventIdx === adverseIdx && (
            <text x={sx(i)} y={sy(p.value) - 9} textAnchor="middle" className="fill-down" fontSize={10} fontWeight={700}>安排的不利結果</text>
          )}
        </g>
      ))}
      <text x={W - R} y={H - 3} textAnchor="end" className="fill-faint" fontSize={10}>虛線＝情蒐參考 · 實線＝動態累積（模擬）</text>
    </svg>
  );
}

export function PitchMindDemo() {
  const ct = useChartTheme();
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
    }, 2000);
    return () => clearTimeout(timer);
  }, [isPlaying, idx]);

  const { situation: s, cutoff } = situationAt(DEMO_EVENTS, idx);
  const tag = countTag(s.balls, s.strikes);
  const q = quickRead(DEMO_EVENTS, idx, tactic);
  const series = dynamicSeries(DEMO_EVENTS, idx, tactic);
  const prev = series.length >= 2 ? series[series.length - 2].value : null;
  const lastEv = q.lastEventIdx != null ? DEMO_EVENTS[q.lastEventIdx] : null;
  const pa = currentPaPitches(DEMO_EVENTS, idx, tactic);
  const paBatter = pa[0]?.pre.batter ?? s.batter;
  const paEnded = paBatter !== s.batter;
  const paPoints: ZonePoint[] = pa.map((p) => ({ x: p.event.x, y: p.event.y, sw: p.event.zoneResult !== "take", wh: p.event.zoneResult === "whiff", result: p.event.zoneResult }));
  const replayPos = idx - REPLAY_START + 1, replayTotal = LAST - REPLAY_START + 1;
  const adverseIdx = DEMO_EVENTS.findIndex((e) => e.id === SCRIPTED_ADVERSE_EVENT_ID);
  const tone = STATUS_TONE[q.status];
  const distanceText = q.status === "over"
    ? (q.distance === 0 ? "已達參考界線" : `高於參考界線 ${-q.distance}`)
    : `距參考界線還有 ${q.distance}`;
  const directionText = q.direction === "up" ? `↑ 上升 ${signed(q.delta)}`
    : q.direction === "down" ? `↓ 下降 ${signed(q.delta)}`
    : q.direction === "flat" ? "→ 持平" : "尚無觀察";

  return (
    <main className="mx-auto max-w-[1180px] space-y-3 px-4 py-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-xl font-bold tracking-[0.04em] text-ink">PitchMind 情蒐展演</h1>
        <span className="pm-st pm-st--hold">示意資料</span>
        <div className="ml-auto">
          <ContextSwitcher label="戰術（示意）" values={TACTIC_IDS} value={tacticId}
            render={(id) => TACTICS.find((t) => t.id === id)?.name ?? id} onChange={setTacticId} />
        </div>
      </div>

      {/* ── 快讀區：戰術、兩數值、距離、方向 ── */}
      <Card padding="px-5 py-4" className="space-y-2">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          <div>
            <div className="text-xs text-muted">所選戰術</div>
            <div className="flex items-center gap-2 text-3xl font-black text-ink" data-testid="tactic-name">
              <span aria-hidden="true" className="inline-block h-3.5 w-3.5 rounded-full" style={{ background: pitchColor(ct, tactic.condition.pitch) }} />
              {tactic.name}
            </div>
          </div>
          <div className={`flex items-center gap-3 ${tone.text}`} data-testid="status">
            <StatusIcon status={q.status} size={30} />
            <div>
              <div className="text-2xl font-black leading-tight">{STATUS_TEXT[q.status]}</div>
              <div className="text-sm font-bold text-ink">
                <span data-testid="distance">{distanceText}</span>
                <span className="mx-2 text-faint">·</span>
                <span data-testid="direction">{directionText}</span>
              </div>
            </div>
          </div>
        </div>
        <Gauge value={q.value} reference={q.reference} prev={prev} status={q.status} />
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className={q.status === "far" ? "text-faint" : "font-bold text-ink"} data-testid="hint">
            {q.status === "far" ? "尚無提示" : "提示：可請教練留意這個戰術；是否調整由教練決定"}
          </span>
          <span className="text-faint">
            {lastEv && lastEv.kind === "pitch"
              ? `最近一次更新：${lastEv.label}・${REACTION_ZH[lastEv.reaction]}（${signed(q.delta)}）`
              : "此戰術尚無更新"}
          </span>
        </div>
        <Trend points={series} adverseIdx={adverseIdx} />
      </Card>

      {/* ── 次要：情境（系統帶入，不可操作）── */}
      <Card padding="px-4 py-3" className="space-y-2 text-sm">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <span><span className="text-xs text-muted">打者 </span><b className="text-ink" data-testid="batter">{s.batter}</b><span className="text-xs text-muted"> 右打</span></span>
          <span><span className="text-xs text-muted">投手 </span><b className="text-ink">{s.pitcher}</b><span className="text-xs text-muted"> 右投</span></span>
          <span><span className="text-xs text-muted">局數 </span><b className="text-ink">{s.inning} 局{half(s.half)}</b></span>
          <span><span className="text-xs text-muted">球數 </span><b className="font-mono tabular-nums text-ink" data-testid="count">{s.balls}-{s.strikes}</b></span>
          <GameSituation bases={s.bases} outs={s.outs} balls={s.balls} strikes={s.strikes} small />
          <span className="text-xs text-muted md:ml-auto">資料截至 <b className="text-ink" data-testid="cutoff">{cutoffText(cutoff)}</b></span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ul className="flex flex-wrap gap-1.5" aria-label="情境標籤">
            {COUNT_TAGS.map((t) => <StateTag key={t} active={t === tag}>{t}</StateTag>)}
          </ul>
          <ul className="flex flex-wrap gap-1.5" aria-label="戰術說明標籤（隨戰術顯示）">
            {ALL_TAGS.map((t) => <StateTag key={t} round active={tactic.tags.includes(t)}>{t}</StateTag>)}
          </ul>
          <span className="text-xs text-muted">條件：{tactic.condition.pitch}・{tactic.condition.h.map((h) => H_ZH[h]).join("／")}{tactic.condition.v.map((v) => V_ZH[v]).join("／")}・壘上無人</span>
        </div>
      </Card>

      {/* ── 展演控制（與正式操作分開）── */}
      <section aria-label="展演控制" className="rounded-md border-2 border-dashed border-line-strong px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="text-sm font-bold text-ink">展演控制<span className="ml-2 text-xs font-normal text-muted">推進事先設計的模擬序列</span></div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => { setPlaying(false); setIdx(REPLAY_START); }} disabled={idx === REPLAY_START}
              className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">回到起點</button>
            <button type="button" onClick={() => { setPlaying(false); setIdx((i) => Math.max(REPLAY_START, i - 1)); }} disabled={idx === REPLAY_START}
              className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">上一事件</button>
            <button type="button" onClick={() => setPlaying((p) => !p)} disabled={idx >= LAST} aria-pressed={isPlaying}
              className="min-h-11 rounded-md bg-ink px-4 text-sm font-bold text-paper disabled:opacity-40">{isPlaying ? "暫停" : "播放"}</button>
            <button type="button" onClick={() => { setPlaying(false); setIdx((i) => Math.min(LAST, i + 1)); }} disabled={idx >= LAST}
              className="min-h-11 rounded-md bg-surface-2 px-3 text-sm text-ink disabled:opacity-40">下一事件</button>
          </div>
          <span className="font-mono text-xs tabular-nums text-muted" data-testid="replay-pos">事件 {replayPos} / {replayTotal}</span>
        </div>
        <p className="mt-1.5 text-xs text-muted" data-testid="script">劇本（主線：外角高速球）：{cutoff.script ?? "—"}</p>
      </section>

      {/* ── 展演說明（完整說明集中在這裡）── */}
      <Card className="space-y-2 text-xs leading-relaxed text-muted">
        <h2 className="text-sm font-bold text-ink">展演說明</h2>
        <p><b className="text-ink">示意資料：</b>全頁為事先設計的模擬序列，球員匿名（打者 A、投手 B…），數字手編，不代表真實球員、比賽或已驗證的 PitchMind 結果。</p>
        <p><b className="text-ink">兩個值：</b>情蒐參考值＝依歷史情蒐為所選戰術與情境設定的參考界線；動態累積值＝本場對該戰術不利的反應證據累積到的程度。兩者在同一個 0–100 示意尺度上，單位是示意點數，<b className="text-ink">不是</b>有效率、被識破率或成功機率，也不是百分比。</p>
        <div>
          <b className="text-ink">示意規則（非已驗證方法）：</b>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5">
            <li>只有符合戰術條件（球種＋區域＋壘上無人）的實際來球會更新該戰術的動態值；每個戰術各自累積，切換戰術只換查看對象，不重置也不重複計入。</li>
            <li>每次更新依打者反應加減示意點數：{(Object.keys(REACTION_ZH) as (keyof typeof REACTION_ZH)[]).map((r) => `${REACTION_ZH[r]} ${signed(tactic.points[r])}`).join("、")}；結果限制在 0–100。</li>
            <li>球數改變、換打者都不重置累積；參考界線依目前球數切換：兩好球時用兩好球界線（{tactic.name}：{tactic.reference.twoStrike}），其餘用一般界線（{tactic.reference.preTwoStrike}）。</li>
            <li>動態值達到或高於參考值＝已超過；差距在 {DEMO_RULES.nearBand} 以內＝正在接近；其餘＝距離尚遠。狀態同時以文字、標記形狀（○／△／■）與條上位置呈現。</li>
            <li>方向＝最近一次更新相對前一次的增減。</li>
          </ol>
        </div>
        <p><b className="text-ink">劇本聲明：</b>外角高速球的提示（接近、超過）刻意排在第 {DEMO_EVENTS.findIndex((e) => e.id === SCRIPTED_ADVERSE_EVENT_ID) - REPLAY_START + 1} 事件安排的明顯不利結果（全壘打）之前，之後安排追打揮空讓動態值回落。這是設計好的示意，不是提前預警成效證明。</p>
        <p><b className="text-ink">待研究／待補：</b>參考值的建立方法與門檻、接近區寬度、反應點數、反應分類所需的逐球資料、共軌所需的軌跡資料、壘上有人時的處理。共軌／速差／引誘只是隨戰術顯示的說明標籤，不代表已量測效果。資料缺值時不當成零。</p>
      </Card>

      {/* ── 延伸資料（不在快讀區，預設收合）── */}
      <details className="card px-4 py-3">
        <summary className="cursor-pointer text-sm font-bold text-ink">延伸資料：{paEnded ? `${paBatter} 上一打席（已結束）` : `${paBatter} 本打席`}逐球（{pa.length} 球）</summary>
        {pa.length === 0 ? <p className="mt-2 text-xs text-faint">本打席尚無投球（0 球）</p> : (
          <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-xs">
                <thead className="bg-band text-muted">
                  <tr>{["球序", "投出前球數", "球種", "位置", "球速", "反應", "符合「" + tactic.name + "」", "結果"].map((h) =>
                    <th key={h} scope="col" className="px-2 py-1.5 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {pa.map((p) => (
                    <tr key={p.event.id} className="border-b border-line">
                      <td className="px-2 py-1.5 font-mono tabular-nums">{p.event.seq}</td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">{p.pre.balls}-{p.pre.strikes}</td>
                      <td className="px-2 py-1.5">{p.event.pitch}</td>
                      <td className="px-2 py-1.5">{H_ZH[p.event.h]}{V_ZH[p.event.v]}</td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">{p.event.speed} km/h</td>
                      <td className="px-2 py-1.5">{REACTION_ZH[p.event.reaction]}</td>
                      <td className="px-2 py-1.5">{p.matched ? <b className="text-ink">符合</b> : <span className="text-faint">不符合</span>}</td>
                      <td className="px-2 py-1.5">{p.event.resultText}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-[11px] text-faint">實投符合條件不等於已知投捕當時意圖。</p>
            </div>
            <div className="mx-auto w-full max-w-[220px]"><ZoneScatter points={paPoints} staticLegend /></div>
          </div>
        )}
      </details>
    </main>
  );
}
