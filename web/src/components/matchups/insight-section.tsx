"use client";

// 隊伍對戰洞察區（UX-MATCHUP1）：ML-MATCHUP1 輸出的呈現層。
// fail-closed 四狀態是常態版面（藍圖 §5.9），各有獨立結構與文案；
// 統計判定全由 API 完成，此處只讀 API 明示欄位（T4 紅線）。
import { useId } from "react";
import { Card, Eyebrow, TeamLogo } from "@/components/ui";
import type { InsightItem, InsightsResponse, Role } from "./api";
import {
  INSIGHT_COPY,
  INSIGHT_LABELS,
  deriveInsightState,
  fmtDelta,
  subjectDelta,
} from "./insight-state";

const fmt3 = (v: number | null | undefined) =>
  v == null ? "—" : v.toFixed(3).replace(/^0\./, ".");

/** 覆蓋率量尺：以 API 回傳的 ratio/gate 畫刻度，不自創閾值。 */
function CoverageMeter({ ratio, gate, passed }: { ratio: number; gate: number; passed: boolean }) {
  const pct = Math.round(Math.min(ratio, 1) * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="relative h-2 w-36 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <div
          className={`h-full rounded-full ${passed ? "bg-ink/60" : "bg-amber"}`}
          style={{ width: `${pct}%` }}
        />
        <div
          className="absolute top-0 h-full w-px bg-ink/70"
          style={{ left: `${Math.round(gate * 100)}%` }}
        />
      </div>
      <span className="font-mono tabular-nums text-muted">
        {pct}%<span className="text-faint">／門檻 {Math.round(gate * 100)}%</span>
      </span>
    </div>
  );
}

function OpportunityLabel({ role }: { role: Role }) {
  return <>{role === "batting" ? "打席" : "面對打席"}</>;
}

function CandidateCard({
  item,
  role,
  tone,
  onPick,
}: {
  item: InsightItem;
  role: Role;
  tone: "adv" | "dis";
  onPick: (id: string, name: string | null) => void;
}) {
  const delta = subjectDelta(role, item.delta_shrunk);
  return (
    <li>
      <Card padding="p-3" className="h-full">
        <div className="flex items-center gap-2">
          <TeamLogo code={item.opp_franchise ?? item.opp_team_code} size={20} decorative />
          <button
            type="button"
            onClick={() => onPick(item.opp_id, item.opp_name)}
            className="font-semibold text-ink hover:underline"
          >
            {item.opp_name ?? item.opp_id}
          </button>
          <span
            className={`ml-auto font-mono text-sm tabular-nums ${
              tone === "adv" ? "text-up" : "text-down"
            }`}
            title="經驗貝氏收縮後的 wOBA 差（主角視角，正＝有利主角）"
          >
            {fmtDelta(role, item.delta_shrunk)}
          </span>
        </div>
        <dl className="mt-2 grid grid-cols-3 gap-1.5 text-center text-xs">
          <div className="rounded bg-surface-2 px-1 py-1.5">
            <dt className="text-[10px] text-muted">
              <OpportunityLabel role={role} />
            </dt>
            <dd className="font-mono tabular-nums text-ink">{item.plate_appearances ?? item.opportunities}</dd>
          </div>
          <div className="rounded bg-surface-2 px-1 py-1.5">
            <dt className="text-[10px] text-muted">{role === "batting" ? "AVG／OPS" : "被打 AVG／OPS"}</dt>
            <dd className="font-mono tabular-nums text-ink">
              {fmt3(item.avg)}／{fmt3(item.ops)}
            </dd>
          </div>
          <div className="rounded bg-surface-2 px-1 py-1.5">
            <dt className="text-[10px] text-muted">可信度</dt>
            <dd className="font-mono tabular-nums text-ink">{Math.round(item.credibility * 100)}%</dd>
          </div>
        </dl>
        <p className="mt-1.5 text-[11px] leading-4 text-faint">
          觀察 wOBA {fmt3(item.observed_woba)}，期望 {fmt3(item.expected_woba)}（收縮後差{" "}
          {delta >= 0 ? "+" : "−"}
          {Math.abs(delta).toFixed(3)}）
        </p>
      </Card>
    </li>
  );
}

/** fail-closed 共用外殼：獨立標題＋說明＋各狀態專屬的事實列。 */
function FailClosed({
  title,
  body,
  note,
  children,
}: {
  title: string;
  body: string;
  note?: string;
  children?: React.ReactNode;
}) {
  return (
    <Card padding="p-4">
      <p className="font-semibold text-ink">{title}</p>
      <p className="mt-1 text-sm leading-6 text-muted">{body}</p>
      {children}
      {note ? <p className="mt-2 text-xs text-faint">API 註記：{note}</p> : null}
    </Card>
  );
}

export default function InsightSection({
  data,
  role,
  teamFilterName,
  onPickOpponent,
  compact = false,
}: {
  data: InsightsResponse;
  role: Role;
  teamFilterName: string | null;
  onPickOpponent: (id: string, name: string | null) => void;
  /** 球員頁用：非 ok 態收合為一行可展開提示（洞察在球員頁是次要加值層）。 */
  compact?: boolean;
}) {
  const state = deriveInsightState(data);
  // 球員頁雙棲時本區會同時掛兩份（打擊／投球），標題 id 需唯一
  const headingId = useId();
  const body = (
    <>
      <p className="mb-3 text-xs leading-5 text-faint">{data.disclaimer}</p>

      {state.kind === "no_baseline" && (
        <FailClosed
          title={INSIGHT_COPY.no_baseline.title}
          body={INSIGHT_COPY.no_baseline.body}
          note={state.note}
        />
      )}

      {state.kind === "no_data" && (
        <FailClosed
          title={INSIGHT_COPY.no_data.title}
          body={INSIGHT_COPY.no_data.body}
          note={state.note}
        />
      )}

      {state.kind === "low_coverage" && (
        <FailClosed
          title={INSIGHT_COPY.low_coverage.title}
          body={INSIGHT_COPY.low_coverage.body}
          note={state.note}
        >
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <span className="text-xs text-muted">樣本覆蓋率（佔官方生涯、全對手範圍）</span>
            <CoverageMeter ratio={state.ratio} gate={state.gate} passed={false} />
          </div>
          {data.coverage && (
            <p className="mt-1.5 text-xs text-faint">
              可觀察 {data.coverage.sampled_opportunities.toLocaleString()}／官方{" "}
              {data.coverage.official_opportunities.toLocaleString()}{" "}
              <OpportunityLabel role={role} />
            </p>
          )}
        </FailClosed>
      )}

      {state.kind === "no_prior" && (
        <FailClosed
          title={INSIGHT_COPY.no_prior.title}
          body={INSIGHT_COPY.no_prior.body}
          note={state.note}
        >
          <p className="mt-3 text-xs text-muted">
            此範圍可用於估計先驗的配對數：
            <span className="font-mono tabular-nums text-ink">
              {data.method.pairs_used ?? 0}
            </span>
            （不足以估計 tau²；覆蓋率
            {data.coverage ? `${Math.round(data.coverage.ratio * 100)}%` : "—"} 已過門檻，
            但收縮基準缺席時不輸出任何排行）
          </p>
        </FailClosed>
      )}

      {state.kind === "gated" && (
        <FailClosed
          title={INSIGHT_COPY.gated.title}
          body={INSIGHT_COPY.gated.body}
          note={state.note}
        >
          <p className="mt-3 text-xs text-muted">
            候選對手{" "}
            <span className="font-mono tabular-nums text-ink">
              {state.eligible + state.gatedOut}
            </span>{" "}
            位，通過可信度閘門（{Math.round(data.method.credibility_gate * 100)}%）者{" "}
            <span className="font-mono tabular-nums text-ink">{state.eligible}</span> 位——
            全部不足以形成方向性排行。上方基礎實績即為完整對戰紀錄。
          </p>
        </FailClosed>
      )}

      {state.kind === "ok" && (
        <>
          {teamFilterName && (
            <p className="mb-2 text-xs text-muted">
              候選已限縮為 {teamFilterName} 所屬投打（本次查詢樣本：
              {data.query_sample.opponents} 位對手、
              {data.query_sample.sampled_opportunities.toLocaleString()}{" "}
              <OpportunityLabel role={role} />；覆蓋率仍以全對手評估）。
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-down">
                {INSIGHT_LABELS.disadvantages}
              </h3>
              {data.disadvantages.length === 0 ? (
                <p className="rounded-lg border border-line bg-surface px-3 py-4 text-center text-xs text-faint">
                  此方向沒有通過閘門的候選
                </p>
              ) : (
                <ul className="grid gap-2">
                  {data.disadvantages.map((c) => (
                    <CandidateCard key={c.opp_id} item={c} role={role} tone="dis" onPick={onPickOpponent} />
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-up">
                {INSIGHT_LABELS.advantages}
              </h3>
              {data.advantages.length === 0 ? (
                <p className="rounded-lg border border-line bg-surface px-3 py-4 text-center text-xs text-faint">
                  此方向沒有通過閘門的候選
                </p>
              ) : (
                <ul className="grid gap-2">
                  {data.advantages.map((c) => (
                    <CandidateCard key={c.opp_id} item={c} role={role} tone="adv" onPick={onPickOpponent} />
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted">
            {data.baseline?.woba != null && (
              <span>
                主角官方 baseline wOBA{" "}
                <span className="font-mono tabular-nums text-ink">{fmt3(data.baseline.woba)}</span>
              </span>
            )}
            {data.league && (
              <span>
                聯盟{" "}
                <span className="font-mono tabular-nums text-ink">{fmt3(data.league.woba)}</span>
              </span>
            )}
            {data.coverage && (
              <span className="flex items-center gap-2">
                樣本覆蓋率
                <CoverageMeter
                  ratio={data.coverage.ratio}
                  gate={data.coverage.gate}
                  passed={data.coverage.passed}
                />
              </span>
            )}
            {data.sensitivity && !data.sensitivity.stable && (
              <span className="rounded bg-amber/15 px-1.5 py-0.5 font-medium text-amber">
                名單對參數選擇敏感
              </span>
            )}
          </div>
          {state.note && <p className="mt-1.5 text-xs text-faint">API 註記：{state.note}</p>}
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer select-none text-faint hover:text-muted">
              方法摘要（{data.method.metric}）
            </summary>
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 leading-5">
              <li>baseline 來源：{data.method.baseline_source ?? "—"}</li>
              <li>對戰觀察來源：{data.method.observed_source ?? "—"}</li>
              <li>期望值：{data.method.expected ?? "—"}</li>
              <li>
                先驗：tau²={data.method.tau2 ?? "—"}、估計配對 {data.method.pairs_used ?? "—"}、
                可信度閘門 {Math.round(data.method.credibility_gate * 100)}%
              </li>
            </ul>
          </details>
        </>
      )}
    </>
  );

  // 球員頁（compact）：非 ok 態收合為一行可展開提示——洞察在此是次要加值層，
  // 且六隊制下同對手對戰量結構性偏低，多數球員此區恆空；ok 態（真有天敵／優勢，
  // 罕見但有價值）照常展開。狀態判定與四態內容仍是同一份（不複製、不另造空態）。
  if (compact && state.kind !== "ok") {
    return (
      <section aria-label="對戰洞察" className="mt-8">
        <details className="overflow-hidden rounded-xl border border-line bg-surface">
          <summary className="cursor-pointer select-none px-4 py-2.5 text-sm text-muted hover:text-ink">
            <span className="font-semibold text-ink">對戰洞察</span>
            <span className="ml-2 text-xs text-faint">
              此範圍樣本不足以產生天敵／優勢排行——點開看原因
            </span>
          </summary>
          <div className="border-t border-line p-4">{body}</div>
        </details>
      </section>
    );
  }

  return (
    <section aria-labelledby={headingId} className="mt-8">
      <Eyebrow className="mb-1">加值層・描述性統計</Eyebrow>
      <h2 id={headingId} className="mb-1 text-lg font-bold text-ink">
        對戰洞察
      </h2>
      {body}
    </section>
  );
}
