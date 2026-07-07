"use client";

// 比賽總覽：關鍵時刻（|ΔWP| 大轉折）+ 得分時刻 timeline。
// 素材全來自既有資料：winprob 逐打席序列 × livelog 事件文，零新請求。
import type { StatRow } from "@/lib/client";
import type { WpPoint } from "@/components/win-prob-chart";

const num = (v: StatRow[string]) => Number(v) || 0;

type Moment = {
  evt: string; inning: number; half: string; hitter: string; pitcher: string;
  desc: string; before: number; after: number; delta: number; isScore: boolean;
};

/** 每打席 ΔWP（後點 − 前點，主隊視角）+ 該打席結果文（PA 末筆非更換事件的首行）。 */
export function buildMoments(wp: WpPoint[], log: StatRow[]): Moment[] {
  if (wp.length < 2) return [];
  // evt(打席首事件) → 該打席結果：從首事件掃到下一打席前，取最後一筆同打者事件
  const idxByEvt = new Map<string, number>(log.map((e, i) => [String(e.main_event_no), i]));
  const out: Moment[] = [];
  for (let i = 0; i < wp.length - 1; i++) {
    const p = wp[i];
    if (!p.evt) continue;
    const start = idxByEvt.get(p.evt);
    if (start === undefined) continue;
    const hitter = log[start].hitter_acnt;
    let last = start, isScore = false;
    for (let j = start; j < log.length; j++) {
      const e = log[j];
      if (e.is_change_player) continue;
      if (String(e.hitter_acnt) !== String(hitter)) break;
      last = j;
      if (e.is_score) isScore = true;
    }
    const fin = log[last];
    out.push({
      evt: p.evt, inning: p.inning ?? 0, half: p.half ?? "1",
      hitter: String(fin.hitter_name ?? ""), pitcher: String(fin.pitcher_name ?? ""),
      desc: String(fin.content ?? "").split(/[\r\n]/)[0],
      before: p.wp, after: wp[i + 1].wp, delta: wp[i + 1].wp - p.wp, isScore,
    });
  }
  return out;
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

function MomentRow({ m, homeName, awayName, onJump }: {
  m: Moment; homeName: string; awayName: string; onJump: (evt: string) => void;
}) {
  const gain = m.delta > 0;                    // 主隊受益
  const team = gain ? homeName : awayName;
  return (
    <button onClick={() => onJump(m.evt)}
      className="block w-full rounded-lg px-3 py-2 text-left transition-colors hover:bg-surface-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-muted">
          {m.inning}{m.half === "1" ? "上" : "下"}　{m.hitter}
          <span className="ml-1 text-faint">vs {m.pitcher}</span>
        </span>
        <span className={`shrink-0 font-mono text-xs font-semibold tabular-nums ${gain ? "text-accent" : "text-sky-700"}`}>
          {team} +{Math.abs(Math.round(m.delta * 100))}%
        </span>
      </div>
      <div className="mt-0.5 truncate text-sm text-ink">{m.desc}</div>
      <div className="mt-1 flex items-center gap-1.5">
        {/* WP 前→後 迷你條（主隊視角） */}
        <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-line">
          <div className="absolute inset-y-0 left-0 rounded-full bg-accent/30" style={{ width: pct(m.before) }} />
          <div className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: pct(m.after) }} />
        </div>
        <span className="font-mono text-[10px] tabular-nums text-faint">{pct(m.before)}→{pct(m.after)}</span>
      </div>
    </button>
  );
}

export function GameOverview({ wp, log, homeName, awayName, onJump, highlights, info, mvp, decisions }: {
  wp: WpPoint[]; log: StatRow[]; homeName: string; awayName: string;
  onJump: (evt: string) => void;
  highlights: string[]; info: [string, string][];
  mvp: { name: string; line: string } | null;
  decisions: [string, string][];
}) {
  const moments = buildMoments(wp, log);
  const key = [...moments].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .filter((m) => Math.abs(m.delta) >= 0.04).slice(0, 5)
    .sort((a, b) => (a.inning - b.inning) || a.evt.localeCompare(b.evt));

  if (!key.length && !highlights.length && !info.length && !mvp && !decisions.length) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {key.length > 0 && (
        <div className="rounded-xl border border-line bg-surface p-3">
          <div className="mb-1.5 px-3 pt-1 text-sm font-semibold">
            關鍵時刻 <span className="text-xs font-normal text-faint">（勝率大轉折・點擊看該打席）</span>
          </div>
          <div className="space-y-0.5">
            {key.map((m) => (
              <MomentRow key={m.evt} m={m} homeName={homeName} awayName={awayName} onJump={onJump} />
            ))}
          </div>
        </div>
      )}
      {(highlights.length > 0 || info.length > 0 || mvp || decisions.length > 0) && (
        <div className="rounded-xl border border-line bg-surface p-4">
          {mvp && (
            <div className="mb-3 flex items-center gap-3 rounded-lg bg-accent/5 px-3 py-2.5">
              <span className="rounded-md bg-accent px-2 py-0.5 text-xs font-bold text-white">MVP</span>
              <div>
                <span className="text-base font-bold text-ink">{mvp.name}</span>
                <span className="ml-2 font-mono text-xs tabular-nums text-muted">{mvp.line}</span>
              </div>
            </div>
          )}
          {highlights.length > 0 && (
            <>
              <div className="mb-2 text-sm font-semibold">本場焦點</div>
              <div className="mb-3 flex flex-wrap gap-1.5">
                {highlights.map((t, i) => (
                  <span key={i} className="rounded-md bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent">{t}</span>
                ))}
              </div>
            </>
          )}
          {decisions.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-2.5 text-xs">
              {decisions.map(([l, v]) => (
                <span key={l}><span className="text-muted">{l}</span> <span className="font-medium text-ink">{v}</span></span>
              ))}
            </div>
          )}
          {info.length > 0 && (
            <>
              <div className="mb-1.5 text-sm font-semibold">賽事資訊</div>
              <dl className="space-y-1 text-sm">
                {info.map(([l, v]) => (
                  <div key={l} className="flex gap-3">
                    <dt className="w-10 shrink-0 text-muted">{l}</dt>
                    <dd className="min-w-0 text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ───────────────────────── 未開賽：賽前展望 ─────────────────────────
export type PregameMatchup = {
  game_date: string; home_win_prob: number;
  home: PregameSide; away: PregameSide;
};
export type PregameSide = {
  code: string; name: string; win_pct: number | null; record: string | null; form: string | null;
  starter?: { name: string; era: number | null; whip: number | null; k9: number | null } | null;
};

export function Pregame({ m }: { m: PregameMatchup }) {
  const p = Math.round(m.home_win_prob * 100);
  const side = (s: PregameSide, right: boolean) => (
    <div className={right ? "text-right" : ""}>
      <div className="text-base font-bold">{s.name}</div>
      <div className="font-mono text-xs text-muted">{s.record ?? "—"}　近10 {s.form ?? "—"}</div>
      {s.starter && (
        <div className="mt-2 text-sm">
          <span className="text-muted">預告先發</span> <span className="font-medium">{s.starter.name}</span>
          <div className="font-mono text-xs text-faint">
            ERA {s.starter.era ?? "—"}・WHIP {s.starter.whip ?? "—"}・K9 {s.starter.k9 ?? "—"}
          </div>
        </div>
      )}
    </div>
  );
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-3 text-sm font-semibold">
        賽前展望 <span className="text-xs font-normal text-faint">（模型參考勝率・詳見賽事預測頁）</span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {side(m.away, false)}
        {side(m.home, true)}
      </div>
      {/* 勝率對比條（主隊右側） */}
      <div className="mt-4">
        <div className="flex h-6 overflow-hidden rounded-md font-mono text-[11px] font-semibold text-white">
          <div className="flex items-center bg-sky-700 pl-2" style={{ width: `${100 - p}%` }}>{100 - p}%</div>
          <div className="flex items-center justify-end bg-accent pr-2" style={{ width: `${p}%` }}>{p}%</div>
        </div>
        <div className="mt-1.5 text-[10px] text-faint">
          全特徵邏輯回歸即時擬合（回測 ~62%，全押主場 ~53%）；單場勝負可預測性有限，供參考與教育用途。
        </div>
      </div>
    </div>
  );
}
