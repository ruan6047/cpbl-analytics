"use client";

// 「如果現在對決」單一打席結果分布面板（UX-PA-SIM-MATCHUP1）。
//
// 產品定位（PRODUCT_UX_BLUEPRINT §5.9／§6）：ML-SIM1 模式 B 的價值是「結果分布 ×
// 情境拆解」，首版只出現在 /matchups 選定打者×投手後的第二 tab，與歷史實績分離。
// 紅線：不得包裝為整場勝負預測提升、區間不得稱信賴區間、任何退化態不得產生替代
// 機率。所有統計由 API 完成，本檔只做取用、狀態分流與呈現（判定見 pa-sim-state.ts）。
import { useEffect, useId, useMemo, useState } from "react";
import { Card, EmptyState, ErrorState, Eyebrow, Skeleton, StatGrid } from "@/components/ui";
import { matchupApi, type Kind, type PaOutcomeKey, type PaSimOk, type PaSimResponse, type PaState } from "./api";
import {
  BASES_OPTIONS,
  DEFAULT_PA_STATE,
  OUT_KEYS,
  PA_OUTCOME_HINT,
  PA_OUTCOME_LABEL,
  PA_SIM_COPY,
  PA_SIM_DISCLOSURE,
  REACH_KEYS,
  batterSide,
  batterSideDelta,
  batterSideWinProbability,
  derivePaSimState,
  fmtDeltaPoints,
  fmtProbability,
  stateSummary,
  type PaSimState,
} from "./pa-sim-state";

const INNINGS = Array.from({ length: 12 }, (_, index) => index + 1);
const SCORES = Array.from({ length: 11 }, (_, index) => index);
const OUTS = [0, 1, 2];

// §4.2 選擇族原生 select：control 圓角 rounded-lg，觸控熱區 44px（min-h-11）。
const selectCls =
  "min-h-11 rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-ink";

/** 上壘價值遞增的單色相序列（§6.2.4）；出局組走中性灰，色彩不承載好壞。 */
const BAR_TONE: Record<PaOutcomeKey, string> = {
  K: "bg-faint",
  BIP_OUT: "bg-faint",
  OTHER_REACH: "bg-up/30",
  BB_HBP: "bg-up/45",
  "1B": "bg-up/60",
  XBH: "bg-up/75",
  HR: "bg-up",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      {label}
      {children}
    </label>
  );
}

/** 單一結果列：標籤＋機率＋機率條＋（區間／勝率影響／轉移樣本）。 */
function OutcomeRow({
  outcomeKey,
  data,
  max,
  half,
}: {
  outcomeKey: PaOutcomeKey;
  data: PaSimOk;
  max: number;
  half: PaState["half"];
}) {
  const outcome = data.outcomes[outcomeKey];
  const [low, high] = outcome.probability_interval_90;
  const delta = batterSideDelta(half, outcome.delta_wp);
  const width = max > 0 ? Math.max(1, (outcome.probability / max) * 100) : 0;
  return (
    <div className="border-t border-line/60 py-2 first:border-t-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-ink" title={PA_OUTCOME_HINT[outcomeKey]}>
          {PA_OUTCOME_LABEL[outcomeKey]}
        </span>
        <span className="font-mono text-sm font-semibold tabular-nums text-ink">
          {fmtProbability(outcome.probability)}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className={`h-full rounded-full ${BAR_TONE[outcomeKey]}`} style={{ width: `${width}%` }} />
      </div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[11px] text-muted">
        <span className="font-mono tabular-nums">
          區間 {fmtProbability(low)}–{fmtProbability(high)}
        </span>
        <span>
          打者方勝率{" "}
          <span
            className={`font-mono tabular-nums ${delta >= 0 ? "text-up" : "text-down"}`}
          >
            {fmtDeltaPoints(delta)} pt
          </span>
        </span>
        <span className="font-mono tabular-nums">轉移樣本 {outcome.transition_samples}</span>
      </div>
    </div>
  );
}

function OutcomeGroup({
  title,
  keys,
  data,
  max,
  half,
}: {
  title: string;
  keys: readonly PaOutcomeKey[];
  data: PaSimOk;
  max: number;
  half: PaState["half"];
}) {
  const total = keys.reduce((sum, key) => sum + data.outcomes[key].probability, 0);
  return (
    <section className="rounded-lg bg-surface-2/40 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold text-muted">{title}</h4>
        <span className="font-mono text-xs tabular-nums text-muted">{fmtProbability(total)}</span>
      </div>
      <div className="mt-1">
        {keys.map((key) => (
          <OutcomeRow key={key} outcomeKey={key} data={data} max={max} half={half} />
        ))}
      </div>
    </section>
  );
}

/** 退化態版面：四種退化＋兩種 fail-closed 各自獨立標題／說明，不顯示任何機率。 */
function DegradedState({ state }: { state: Exclude<PaSimState, { kind: "ok" }> }) {
  const copy = PA_SIM_COPY[state.kind];
  const reason = "reason" in state ? state.reason : null;
  const detail =
    state.kind === "league_fallback"
      ? `缺少樣本的一方：${
          state.side === "hitter" ? "打者" : state.side === "pitcher" ? "投手" : "打者與投手"
        }。`
      : state.kind === "invariant_failed"
        ? state.missing.length
          ? `缺少結果項：${state.missing.join("、")}。`
          : state.sum !== null
            ? `回應機率總和為 ${state.sum.toFixed(4)}。`
            : null
        : reason
          ? `服務回報原因：${reason}。`
          : null;

  // EmptyState／ErrorState 本體是 <p>，內部只能放 inline 元素（塞 div/p 會造成
  // hydration error）；用 span + block 取得段落排版而不破壞 HTML 結構。
  const body = (
    <span className="mx-auto block max-w-prose text-left">
      <span className="block text-sm font-semibold text-ink">{copy.title}</span>
      <span className="mt-1 block text-xs leading-relaxed text-muted">{copy.body}</span>
      {detail && <span className="mt-1 block text-xs text-muted">{detail}</span>}
    </span>
  );

  return state.kind === "api_error" ? <ErrorState>{body}</ErrorState> : <EmptyState>{body}</EmptyState>;
}

export default function PaSimPanel({
  hitterId,
  pitcherId,
  hitterName,
  pitcherName,
  kind,
}: {
  hitterId: string;
  pitcherId: string;
  hitterName: string | null;
  pitcherName: string | null;
  /** 上方查詢的賽事類型；非 A 時模擬母體不存在（unsupported）。 */
  kind: Kind;
}) {
  const [state, setState] = useState<PaState>(DEFAULT_PA_STATE);
  const [response, setResponse] = useState<PaSimResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const headingId = useId();

  const supported = kind === "A";

  useEffect(() => {
    if (!supported || !hitterId || !pitcherId) {
      setResponse(null);
      return;
    }
    let stale = false;
    setLoading(true);
    setFailed(false);
    matchupApi
      .plateAppearance(hitterId, pitcherId, state)
      .then((data) => {
        if (!stale) setResponse(data);
      })
      .catch(() => {
        if (!stale) {
          setResponse(null);
          setFailed(true);
        }
      })
      .finally(() => {
        if (!stale) setLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [supported, hitterId, pitcherId, state]);

  // 尚未取得任何回應（且母體受支援、請求未失敗）＝首次載入，不得當成退化態。
  const pending = supported && !failed && response === null;
  const derived = useMemo(
    () => derivePaSimState(kind, response, failed),
    [kind, response, failed],
  );
  const max = useMemo(() => {
    if (derived.kind !== "ok") return 0;
    return Math.max(
      ...Object.values(derived.data.outcomes).map((outcome) => outcome.probability),
    );
  }, [derived]);

  const patch = (next: Partial<PaState>) => setState((prev) => ({ ...prev, ...next }));
  const hitter = hitterName ?? hitterId;
  const pitcher = pitcherName ?? pitcherId;

  return (
    <Card padding="p-4">
      <section aria-labelledby={headingId}>
        <Eyebrow>打席結果分布・模型機率</Eyebrow>
        <h3 id={headingId} className="mt-0.5 text-base font-bold text-ink">
          {hitter} 對 {pitcher}：這一個打席會怎麼結束
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          {PA_SIM_DISCLOSURE.scopeNote}
          {PA_SIM_DISCLOSURE.shrinkageNote}
        </p>

        {/* 情境輸入：只影響「若該結果發生，戰局怎麼變」，不改變結果機率。
            退化態不顯示——沒有結果可拆解時，可操作的情境控制會誤導使用者以為
            「調一調就會有數字」。 */}
        {(pending || derived.kind === "ok") && (
        <div className="mt-3 rounded-lg border border-line bg-surface-2/40 p-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="text-[11px] font-semibold text-muted">假設情境</span>
            <Field label="局數">
              <select
                className={selectCls}
                value={state.inning}
                onChange={(event) => patch({ inning: Number(event.target.value) })}
              >
                {INNINGS.map((inning) => (
                  <option key={inning} value={inning}>{inning}</option>
                ))}
              </select>
            </Field>
            <Field label="打者所屬">
              <select
                className={selectCls}
                value={state.half}
                onChange={(event) => patch({ half: event.target.value as PaState["half"] })}
              >
                <option value="1">客隊（上半）</option>
                <option value="2">主隊（下半）</option>
              </select>
            </Field>
            <Field label="出局">
              <select
                className={selectCls}
                value={state.outs}
                onChange={(event) => patch({ outs: Number(event.target.value) })}
              >
                {OUTS.map((outs) => (
                  <option key={outs} value={outs}>{outs}</option>
                ))}
              </select>
            </Field>
            <Field label="壘上">
              <select
                className={selectCls}
                value={state.bases}
                onChange={(event) => patch({ bases: event.target.value })}
              >
                {BASES_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </Field>
            <Field label="客隊分">
              <select
                className={selectCls}
                value={state.away_score}
                onChange={(event) => patch({ away_score: Number(event.target.value) })}
              >
                {SCORES.map((score) => (
                  <option key={score} value={score}>{score}</option>
                ))}
              </select>
            </Field>
            <Field label="主隊分">
              <select
                className={selectCls}
                value={state.home_score}
                onChange={(event) => patch({ home_score: Number(event.target.value) })}
              >
                {SCORES.map((score) => (
                  <option key={score} value={score}>{score}</option>
                ))}
              </select>
            </Field>
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
            {stateSummary(state)}；打者此時屬{batterSide(state.half) === "home" ? "主隊" : "客隊"}。
            {PA_SIM_DISCLOSURE.situationNote}
          </p>
        </div>
        )}

        {/* 首次尚無回應＝載入態；已有回應時改情境不清空版面（避免骨架閃爍與
            「無法模擬」誤閃），只以 aria-busy＋淡化標示更新中。 */}
        {pending && (
          <div className="mt-4 space-y-2" aria-busy="true">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}

        {!pending && derived.kind !== "ok" && (
          <div className="mt-2">
            <DegradedState state={derived} />
          </div>
        )}

        {!pending && derived.kind === "ok" && (
          <div aria-busy={loading} className={loading ? "opacity-60 transition-opacity" : undefined}>
            <PaSimResult data={derived.data} half={state.half} max={max} />
          </div>
        )}
      </section>
    </Card>
  );
}

function PaSimResult({
  data,
  half,
  max,
}: {
  data: PaSimOk;
  half: PaState["half"];
  max: number;
}) {
  const { sample } = data;
  const currentBatterView = batterSideWinProbability(half, data.current_win_probability);
  const outsTotal = OUT_KEYS.reduce((sum, key) => sum + data.outcomes[key].probability, 0);

  return (
    <div className="mt-4">
      {/* 出局組只有兩項，寬螢幕併排會在左欄留下大片空白；把「此情境勝率」放進左欄
          下方既補齊視覺，也讓最相關的情境結果留在結果分布的視線內。 */}
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-3">
          <OutcomeGroup title="出局" keys={OUT_KEYS} data={data} max={max} half={half} />
          <section className="rounded-lg border border-line bg-surface-2/40 p-3">
            <h4 className="text-xs font-semibold text-muted">此情境的起點</h4>
            <p className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-xl font-bold tabular-nums text-ink">
                {fmtProbability(currentBatterView)}
              </span>
              <span className="text-xs text-muted">
                打者方（{batterSide(half) === "home" ? "主隊" : "客隊"}）目前勝率
              </span>
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              {"上表「打者方勝率」是各結果發生後相對這個起點的變化量；" +
                "打席還沒發生，分布本身不隨情境改變。"}
            </p>
          </section>
        </div>
        <OutcomeGroup title="上壘" keys={REACH_KEYS} data={data} max={max} half={half} />
      </div>

      {/* 圖表文字替代（§6.3）：條圖之外，同一組數字以純文字列表重述。 */}
      <details className="mt-2">
        <summary className="cursor-pointer select-none text-xs text-muted hover:text-ink">
          結果分布的文字列表
        </summary>
        <ul className="mt-1.5 space-y-0.5 text-xs text-muted">
          {[...OUT_KEYS, ...REACH_KEYS].map((key) => {
            const outcome = data.outcomes[key];
            return (
              <li key={key} className="font-mono tabular-nums">
                {PA_OUTCOME_LABEL[key]}：{fmtProbability(outcome.probability)}（區間{" "}
                {fmtProbability(outcome.probability_interval_90[0])}–
                {fmtProbability(outcome.probability_interval_90[1])}；打者方勝率{" "}
                {fmtDeltaPoints(batterSideDelta(half, outcome.delta_wp))} pt；轉移樣本{" "}
                {outcome.transition_samples}）
              </li>
            );
          })}
          <li className="text-muted">
            出局合計 {fmtProbability(outsTotal)}、上壘合計 {fmtProbability(1 - outsTotal)}。
          </li>
        </ul>
      </details>

      <section className="mt-4 border-t border-line pt-3">
        <Eyebrow>樣本與模型版本</Eyebrow>
        <StatGrid
          cols={3}
          items={[
            { label: "打者可用打席", value: sample.hitter_pa },
            { label: "投手可用打席", value: sample.pitcher_pa },
            { label: "兩人直接對戰", value: sample.direct_pa },
          ]}
        />
        <ul className="mt-2 space-y-1 text-[11px] leading-relaxed text-muted">
          <li>
            收縮權重：打者 {(sample.shrinkage_weight.hitter * 100).toFixed(0)}%、投手{" "}
            {(sample.shrinkage_weight.pitcher * 100).toFixed(0)}%、直接對戰{" "}
            {(sample.shrinkage_weight.direct * 100).toFixed(0)}%
            {sample.low_sample && "（直接對戰屬小樣本，估計以雙方各自表現為主）"}
          </li>
          <li>模型訓練截止：{data.trained_through} 季；勝率期望使用 {data.wp_span} 逐打席分布。</li>
          <li>{PA_SIM_DISCLOSURE.intervalNote}</li>
          {/* 「等效」不只宣稱，直接把兩個數字並排讓讀者自行核對（blueprint §7.2 精神：
              不得只給結論數字而隱藏對照組）。 */}
          <li>
            {PA_SIM_DISCLOSURE.weightedNote}此情境主隊視角：現行{" "}
            <span className="font-mono tabular-nums">
              {fmtProbability(data.current_win_probability)}
            </span>{" "}
            對加權{" "}
            <span className="font-mono tabular-nums">
              {fmtProbability(data.weighted_win_probability)}
            </span>
            。
          </li>
          <li>
            {"情境影響由歷史轉移樣本估計，樣本少的結果（如滿壘全壘打）可能出現不符" +
              "直覺的排序，屬估計雜訊而非規則；每列已附轉移樣本數供判讀。"}
          </li>
        </ul>
      </section>
    </div>
  );
}
