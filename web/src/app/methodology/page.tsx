import { api, type OutcomeBenchmarkResponse, type PregameBacktestResponse } from "@/lib/api";
import { METHODOLOGY_SECTIONS } from "@/lib/methodology-anchors";
import {
  BENCHMARK_NOTE,
  ENTRY_FIELD_LABELS,
  METHODOLOGY_CONTENT,
  METRIC_GLOSSARY,
  NOT_ON_SITE,
  SECTION_IDS,
  type MethodologyEntry,
} from "@/lib/methodology-content";
import { Card, Eyebrow } from "@/components/ui";

export const metadata = { title: "方法與模型透明度 | CPBL 分析" };

/**
 * `/methodology`（PRODUCT_UX_BLUEPRINT v0.2 §5.14；UX-MODEL-METHOD1）。
 *
 * 段落 id 由 METHODOLOGY_SECTIONS 契約固定，模型旁的「模型方法」badge deep-link
 * 至此。內容六欄（回答的問題／資料期間／baseline／validation／限制／版本）取自
 * 已核可模型報告（methodology-content.ts）；賽前勝率段另抓正式回測紀錄即時對照，
 * artifact 缺席時退回報告快照並明示——頁面在任何 fetch 失敗下都必須可讀。
 */

// 模型狀態 chip 色調：passed＝綠（通過閘門）／descriptive＝中性／gated＝amber 警示。
const STATUS_CLS = {
  passed: "bg-up/15 text-up",
  descriptive: "bg-surface-2 text-muted",
  gated: "bg-amber/15 text-amber",
} as const;

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

// 回測模型列名 → 中文（後端 cv_metrics 的內部名不直接見人）。
const BACKTEST_MODEL_LABELS: Record<string, string> = {
  fixed_semantic: "固定語意群（上線模型）",
  home_baseline: "全押主場（baseline）",
  full_logistic: "全特徵邏輯回歸（對照）",
  lightgbm: "全特徵 LightGBM（對照）",
};

function MetricsTable({
  rows,
  highlight,
}: {
  rows: { name: string; accuracy: number; brier: number; log_loss: number }[];
  highlight?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[26rem] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-faint">
            <th className="py-1.5 pr-3 font-medium">模型</th>
            <th className="py-1.5 pr-3 font-medium">準確率</th>
            <th className="py-1.5 pr-3 font-medium">Brier</th>
            <th className="py-1.5 font-medium">LogLoss</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const emphasized = row.name === highlight;
            return (
              <tr key={row.name} className="border-b border-line/50 last:border-0">
                <td className={`py-1.5 pr-3 ${emphasized ? "font-semibold text-ink" : "text-muted"}`}>
                  {BACKTEST_MODEL_LABELS[row.name] ?? row.name}
                </td>
                <td className={`py-1.5 pr-3 tabular-nums ${emphasized ? "font-semibold text-ink" : "text-muted"}`}>
                  {pct(row.accuracy)}
                </td>
                <td className={`py-1.5 pr-3 tabular-nums ${emphasized ? "font-semibold text-ink" : "text-muted"}`}>
                  {row.brier.toFixed(4)}
                </td>
                <td className={`py-1.5 tabular-nums ${emphasized ? "font-semibold text-ink" : "text-muted"}`}>
                  {row.log_loss.toFixed(4)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 賽前勝率段的即時回測面板；紀錄缺席時明示退回報告快照，不空白、不拋錯。 */
function PregameLivePanel({ backtest }: { backtest: PregameBacktestResponse | null }) {
  if (!backtest?.available || !backtest.models?.length) {
    return (
      <p className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted">
        目前無法取得線上回測紀錄（模型 artifact 或資料庫紀錄缺席）；上方 validation
        數字為報告快照，仍為最近一次通過查核的結果。
      </p>
    );
  }
  const gate = backtest.gate;
  const gatePassed = gate ? Object.values(gate.checks).filter(Boolean).length : 0;
  const gateTotal = gate ? Object.keys(gate.checks).length : 0;
  return (
    <div className="mt-2">
      <p className="mb-1.5 text-xs text-faint">
        線上回測紀錄（版本 {backtest.version}
        {backtest.test_years?.length
          ? `・測試 ${backtest.test_years[0]}–${backtest.test_years[backtest.test_years.length - 1]} 季`
          : ""}
        {backtest.n_test ? `・${backtest.n_test.toLocaleString()} 場` : ""}）
      </p>
      <MetricsTable rows={backtest.models} highlight="fixed_semantic" />
      {gate && (
        <p className="mt-1.5 text-xs text-muted">
          部署閘門：{gatePassed}/{gateTotal} 項通過・
          {gate.deployable ? "可部署" : "未達可部署標準（頁面仍如實展示）"}
          {backtest.seasons_beating_baseline != null && backtest.test_years?.length
            ? `・${backtest.seasons_beating_baseline}/${backtest.test_years.length} 個測試季勝過全押主場`
            : ""}
        </p>
      )}
    </div>
  );
}

/** 舊全特徵模型 benchmark 對照（§6：只作比較組，不驅動公開互動 UI）。 */
function BenchmarkPanel({ benchmark }: { benchmark: OutcomeBenchmarkResponse | null }) {
  return (
    <div className="mt-4 border-t border-line pt-3">
      <h3 className="text-sm font-semibold text-ink">benchmark：舊全特徵模型對照</h3>
      <p className="mt-1 text-xs text-muted">{BENCHMARK_NOTE}</p>
      {benchmark?.available && benchmark.models?.length ? (
        <div className="mt-2">
          <p className="mb-1.5 text-xs text-faint">
            走查回測（版本 {benchmark.version}
            {benchmark.test_seasons?.length
              ? `・測試 ${benchmark.test_seasons[0]}–${benchmark.test_seasons[benchmark.test_seasons.length - 1]} 季`
              : ""}
            {benchmark.n_test ? `・${benchmark.n_test.toLocaleString()} 場` : ""}）
          </p>
          <MetricsTable rows={benchmark.models} />
        </div>
      ) : (
        <p className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted">
          目前無法取得 benchmark 回測紀錄；報告快照（測試 2022–2026 季、1,496 場）：全特徵邏輯回歸準確率
          62.8%、全特徵 LightGBM 61.3%，對全押主場 52.9%。
        </p>
      )}
    </div>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[7.5rem_1fr] sm:gap-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-faint sm:pt-0.5">{label}</dt>
      <dd className="text-sm leading-relaxed text-muted">{children}</dd>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item} className="flex gap-2">
          <span aria-hidden className="mt-[0.55rem] h-1 w-1 shrink-0 rounded-full bg-line" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function ModelSection({
  id,
  label,
  entry,
  children,
}: {
  id: string;
  label: string;
  entry: MethodologyEntry;
  children?: React.ReactNode;
}) {
  return (
    <Card>
      <section aria-labelledby={`${id}-heading`}>
        {/* scroll-mt 讓 badge deep-link 錨點不被 sticky header 蓋住 */}
        <div id={id} className="scroll-mt-24">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={`${id}-heading`} className="text-lg font-bold text-ink">
              {label}
            </h2>
            <span className="rounded bg-ink px-1.5 py-0.5 text-[10px] font-semibold text-paper">
              {entry.kindBadge}
            </span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATUS_CLS[entry.status.tone]}`}>
              {entry.status.label}
            </span>
          </div>
        </div>
        <dl className="mt-3 space-y-3">
          <FieldRow label={ENTRY_FIELD_LABELS.question}>{entry.question}</FieldRow>
          <FieldRow label="方法">
            <div className="space-y-2">
              {entry.method.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>
          </FieldRow>
          <FieldRow label={ENTRY_FIELD_LABELS.period}>{entry.period}</FieldRow>
          <FieldRow label={ENTRY_FIELD_LABELS.baseline}>{entry.baseline}</FieldRow>
          <FieldRow label={ENTRY_FIELD_LABELS.validation}>
            <List items={entry.validation} />
          </FieldRow>
          <FieldRow label={ENTRY_FIELD_LABELS.limits}>
            <List items={entry.limits} />
          </FieldRow>
          <FieldRow label={ENTRY_FIELD_LABELS.version}>{entry.version}</FieldRow>
        </dl>
        {children}
      </section>
    </Card>
  );
}

async function safeFetch<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch {
    // /methodology 必須在 API 不可達時仍可讀：任何 fetch 失敗都退回報告快照。
    return null;
  }
}

export default async function MethodologyPage() {
  const [pregameBacktest, benchmark] = await Promise.all([
    safeFetch(api.pregameBacktest()),
    safeFetch(api.outcomeBenchmark()),
  ]);

  return (
    <div>
      <header className="mb-6">
        <Eyebrow className="mb-2">方法與模型透明度</Eyebrow>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">
          這個數字怎麼來、可信到哪裡？
        </h1>
        <p className="mt-1.5 max-w-3xl text-sm text-muted">
          本頁逐一交代站上每個模型數字：它回答什麼問題、用哪段資料、跟什麼 baseline
          比、通過了什麼驗證、在哪裡會失準。站上模型旁的「模型方法」標籤會直接連到對應段落。
        </p>
      </header>

      <Card className="mb-4">
        <h2 className="text-sm font-bold text-ink">怎麼讀本頁</h2>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          每個模型固定交代六件事：{Object.values(ENTRY_FIELD_LABELS).join("、")}
          。指標白話對照如下；模型沒贏過 baseline 就不會上線，是本站的紅線。
        </p>
        <dl className="mt-3 space-y-1.5">
          {METRIC_GLOSSARY.map(({ term, desc }) => (
            <div key={term} className="grid gap-1 text-sm sm:grid-cols-[7.5rem_1fr] sm:gap-3">
              <dt className="font-semibold text-ink">{term}</dt>
              <dd className="text-muted">{desc}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <nav aria-label="模型段落" className="mb-6 flex flex-wrap gap-2">
        {SECTION_IDS.map((id) => (
          <a
            key={id}
            href={`#${id}`}
            className="inline-flex min-h-11 items-center rounded-lg border border-line bg-surface px-3 text-sm font-medium text-ink hover:bg-surface-2"
          >
            {METHODOLOGY_SECTIONS[id]}
          </a>
        ))}
        <a
          href="#not-on-site"
          className="inline-flex min-h-11 items-center rounded-lg border border-line bg-surface px-3 text-sm font-medium text-muted hover:bg-surface-2"
        >
          站上沒有的模型
        </a>
      </nav>

      <div className="space-y-4">
        {SECTION_IDS.map((id) => (
          <ModelSection key={id} id={id} label={METHODOLOGY_SECTIONS[id]} entry={METHODOLOGY_CONTENT[id]}>
            {id === "pregame" && (
              <div className="mt-4 border-t border-line pt-3">
                <h3 className="text-sm font-semibold text-ink">線上回測對照</h3>
                <PregameLivePanel backtest={pregameBacktest} />
                <BenchmarkPanel benchmark={benchmark} />
              </div>
            )}
          </ModelSection>
        ))}

        <Card>
          <section aria-labelledby="not-on-site-heading">
            <h2 id="not-on-site" className="scroll-mt-24 text-lg font-bold text-ink">
              站上沒有的模型
            </h2>
            <p className="mt-1.5 text-sm text-muted">
              沒通過驗證閘門的模型不會出現在站上，也不會在本頁取得方法段落——缺席本身就是結論。
            </p>
            <dl className="mt-3 space-y-3">
              {NOT_ON_SITE.map(({ title, body }) => (
                <div key={title}>
                  <dt className="text-sm font-semibold text-ink">{title}</dt>
                  <dd className="mt-0.5 text-sm leading-relaxed text-muted">{body}</dd>
                </div>
              ))}
            </dl>
          </section>
        </Card>
      </div>
    </div>
  );
}
