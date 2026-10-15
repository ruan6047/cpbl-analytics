"use client";

import { useState } from "react";

import { ComparisonBar } from "@/components/split-bar";
import {
  COMPARISON_COPY,
  T5_COPY,
  comparisonBarVM,
  defaultScope,
  formatMetric,
  scopeHasTeams,
  scopeStatusNote,
  streakVM,
  styleTagsVM,
  type ComparisonMetricDef,
  type ComparisonPayload,
  type ComparisonScopeKey,
  type ComparisonTeamView,
} from "@/lib/playoffs-comparison";
import { teamShortName } from "@/lib/postseason-journey";
import { teamColor } from "@/lib/teams";

// #287 S06 WP6b：季後賽第 2 區「隊伍表現」——全年 A／兩隊 A 對戰／本系列三範圍比較。
//
// 掛點（#285 掛點契約 r3 §2）：
// - S04 外框提供 `#teams` 錨點、client 取數與 30 秒輪詢（本區 `every_round`）；本元件⛔ 不設 `id="teams"`、⛔ 不取數。
// - `data == null` ⇒ 第 2 區錯誤態；不影響其他區。
// - 輪詢只換 `data` props：範圍切換是元件內 state（初值見 `defaultScope`），資料更新不重置；清單以 metric key／
//   team code／axis key 為 key，不 remount。
// - 說明性注意事項⛔ 不在區內就地顯示：資料來源、樣本限制、方向圖例、具體缺值原因都在 `comparisonNotes(data)`
//   交 S04 頁尾；格內只留「—」「待更新」與數值（含樣本數值，F1）。
// - 數字、尺度、方向、排名都由後端 payload 給，元件只排字（PRD 前後端責任）；比較條換算在 `comparisonBarVM`。

const SCOPES: ComparisonScopeKey[] = ["season_a", "head_to_head_a", "series"];

export function ComparisonSection({ data }: { data: ComparisonPayload | null }) {
  return (
    <section aria-labelledby="teams-heading" className="min-w-0 space-y-4">
      <h2 id="teams-heading" className="text-lg font-bold text-ink">{COMPARISON_COPY.heading}</h2>
      {data == null ? (
        <p role="status" className="rounded border border-line bg-surface p-3 text-sm text-muted">
          {COMPARISON_COPY.loadFailed}
        </p>
      ) : (
        <ComparisonBody data={data} />
      )}
    </section>
  );
}

/** 持有範圍切換 state；固定位置、不給 key——輪詢換 `data` 時保留使用者所選範圍。 */
function ComparisonBody({ data }: { data: ComparisonPayload }) {
  const [scope, setScope] = useState<ComparisonScopeKey>(() => defaultScope(data));
  return <ComparisonView data={data} scope={scope} onScope={setScope} />;
}

/** 純呈現（無 hooks，測試可直接以任一範圍渲染）。 */
export function ComparisonView({ data, scope, onScope }: {
  data: ComparisonPayload; scope: ComparisonScopeKey; onScope?: (s: ComparisonScopeKey) => void;
}) {
  const [left, right] = data.series_id.teams;
  const current = data.scopes[scope];
  const status = scopeStatusNote(current);
  const lView = left ? current.teams[left] : undefined;
  const rView = right ? current.teams[right] : undefined;
  const lColor = teamColor(left);
  const rColor = teamColor(right);
  const h2hGames = data.scopes.head_to_head_a.games;

  return (
    <div className="min-w-0 space-y-4" data-scope={scope} data-area-status={data.status}>
      <div role="group" aria-label={COMPARISON_COPY.scopeTabsLabel} className="flex flex-wrap gap-2">
        {SCOPES.map((k) => (
          <button key={k} type="button" aria-pressed={scope === k} onClick={() => onScope?.(k)}
            className={`rounded-full px-3 py-1 text-sm font-semibold ${scope === k
              ? "bg-ink text-paper" : "bg-surface-2 text-muted hover:text-ink"}`}>
            {COMPARISON_COPY.scopeLabel[k]}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between gap-3 text-sm font-bold">
        <span style={{ color: lColor }}>{left ? teamShortName(left) : COMPARISON_COPY.missingValue}</span>
        <span className="flex items-center gap-2 text-xs font-semibold text-muted">
          {scope === "head_to_head_a" && h2hGames != null
            ? <span className="tabular-nums">{COMPARISON_COPY.sample.games(h2hGames)}</span> : null}
          {status ? <span role="status" data-scope-status={current.status}
            className="rounded bg-surface-2 px-2 py-0.5 text-ink">{status}</span> : null}
        </span>
        <span style={{ color: rColor }}>{right ? teamShortName(right) : COMPARISON_COPY.missingValue}</span>
      </div>

      {scopeHasTeams(current) ? (
        <>
          <div className="space-y-2">
            <h3 className="text-sm font-bold text-muted">{COMPARISON_COPY.metricsHeading}</h3>
            {data.metric_defs.map((def) => (
              <ComparisonBar key={def.key} vm={comparisonBarVM(def, lView, rView, current.scales[def.key])}
                leftColor={lColor} rightColor={rColor} />
            ))}
          </div>

          <div className="space-y-1">
            <h3 className="text-sm font-bold text-muted">{COMPARISON_COPY.streakHeading}</h3>
            <div className="grid grid-cols-2 gap-3 text-sm text-ink">
              <p data-streak-team={left ?? ""}>{streakVM(scope, lView)}</p>
              <p data-streak-team={right ?? ""} className="text-right">{streakVM(scope, rView)}</p>
            </div>
          </div>

          <div className="space-y-1">
            <h3 className="text-sm font-bold text-muted">{COMPARISON_COPY.styleHeading}</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {[left, right].map((code, i) => (
                <StyleBlock key={code ?? `none-${i}`} scope={scope} view={code ? current.teams[code] : undefined}
                  axes={data.style_axes} />
              ))}
            </div>
          </div>

          {scope === "series" && scopeHasTeams(data.scopes.season_a) ? (
            <T5Table data={data} left={left} right={right} />
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function StyleBlock({ scope, view, axes }: {
  scope: ComparisonScopeKey; view: ComparisonTeamView | undefined; axes: ComparisonPayload["style_axes"];
}) {
  if (!view) return <p className="text-sm text-muted">{COMPARISON_COPY.missingValue}</p>;
  const tags = styleTagsVM(scope, view, axes);
  if (scope === "season_a") {
    return (
      <div aria-label={COMPARISON_COPY.topTraitsLabel} className="flex flex-wrap gap-2">
        {tags.length ? tags.map((t) => (
          <span key={t.axis} className="rounded bg-band px-2 py-1 text-xs font-bold text-ink">
            {t.text}{t.badge ? <span className="ml-1 font-normal text-muted">{t.badge}</span> : null}
          </span>
        )) : <span className="text-xs text-muted">{COMPARISON_COPY.missingValue}</span>}
      </div>
    );
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
      {tags.map((t) => (
        <div key={t.axis} className="contents">
          <dt className="text-muted">{t.label}</dt>
          <dd className="tabular-nums text-ink">{t.text}</dd>
        </div>
      ))}
    </dl>
  );
}

function T5Table({ data, left, right }: { data: ComparisonPayload; left: string | null; right: string | null }) {
  const pick = (code: string | null, scope: "season_a" | "series", def: ComparisonMetricDef) =>
    formatMetric(def, code ? data.scopes[scope].teams[code]?.metrics[def.key] : null);
  const name = (code: string | null) => (code ? teamShortName(code) : COMPARISON_COPY.missingValue);
  return (
    <div className="space-y-1" data-t5="">
      <h3 className="text-sm font-bold text-muted">{T5_COPY.heading}</h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[18rem] text-xs tabular-nums">
          <thead>
            <tr className="text-muted">
              <th className="py-1 text-left font-semibold" />
              <th className="py-1 text-right font-semibold" colSpan={2}>{name(left)}</th>
              <th className="py-1 text-right font-semibold" colSpan={2}>{name(right)}</th>
            </tr>
            <tr className="text-faint">
              <th />
              <th className="text-right font-normal">{T5_COPY.seasonColumn}</th>
              <th className="text-right font-normal">{T5_COPY.seriesColumn}</th>
              <th className="text-right font-normal">{T5_COPY.seasonColumn}</th>
              <th className="text-right font-normal">{T5_COPY.seriesColumn}</th>
            </tr>
          </thead>
          <tbody>
            {data.metric_defs.map((def) => (
              <tr key={def.key} className="border-t border-line">
                <th className="py-1 text-left font-semibold text-ink">{def.label}</th>
                <td className="py-1 text-right text-muted">{pick(left, "season_a", def)}</td>
                <td className="py-1 text-right text-ink">{pick(left, "series", def)}</td>
                <td className="py-1 text-right text-muted">{pick(right, "season_a", def)}</td>
                <td className="py-1 text-right text-ink">{pick(right, "series", def)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default ComparisonSection;
