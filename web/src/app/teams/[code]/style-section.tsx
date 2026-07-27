"use client";

import { useState } from "react";
import {
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartAxis, chartTooltip, useChartTheme } from "@/lib/chart-theme";
import {
  SEMANTICS_BADGE,
  TEAM_STYLE_COPY,
  TEAM_STYLE_SECTION as S,
  clampZ,
  formatZ,
  managerMarkers,
  type TeamStyleAxisKey,
  type TeamStyleResponse,
} from "@/lib/team-style";

/**
 * 球隊頁「球風」獨立頁籤（UX-TEAM-STYLE1；需求方 2026-07-27 裁定由賽季內區塊改獨立頁籤）。
 *
 * - 口徑固定**全年**（設計約束 7）：本群組無半季子頁籤（結構上不接 ContextSwitcher），
 *   頁面內仍明示「全年」。季切換在頁內 client 端做——API 一次回全部季，切換即時不重抓。
 * - 雷達＝所選季七軸季內 z（顯示截 ±2）；軸明細＝原始數值＋聯盟排名＋軸級語意標注
 *   （semantics 判定在後端，本層只映射 `SEMANTICS_BADGE`／`TEAM_STYLE_COPY` 文案）。
 * - 歷史逐季＝單軸 z 折線（約束 2：分段維持逐季）；教練名僅時間標記（換帥年虛線＋
 *   「名 年–」清單）；進行中賽季空心點＋標注（約束 8）。
 * - 全部使用者可見字串出自 `@/lib/team-style`（文案單點，測試掃描設計約束）。
 * - active 樣式沿設計系統：`bg-ink text-paper`（嚴禁 text-white）。
 */
export function TeamStyleSection({ data, defaultYear }: {
  data: TeamStyleResponse;
  defaultYear: number;
}) {
  const ct = useChartTheme();
  const years = data.seasons.map((s) => s.year);
  const [year, setYear] = useState<number>(
    years.includes(defaultYear) ? defaultYear : (years[years.length - 1] ?? defaultYear));
  const [historyAxis, setHistoryAxis] = useState<TeamStyleAxisKey>("discipline");

  const season = data.seasons.find((s) => s.year === year);
  const color = ct.series[0];

  const radarData = season
    ? data.axes.map((a) => ({ axis: a.label, z: clampZ(season.axes[a.key].z) }))
    : [];

  const markers = managerMarkers(data.seasons);
  const inProgressYears = data.seasons.filter((s) => s.in_progress).map((s) => s.year);
  const historyData = data.seasons.map((s) => ({
    year: s.year,
    z: s.axes[historyAxis].z,
    in_progress: s.in_progress,
  }));
  const historyMeta = data.axes.find((a) => a.key === historyAxis);

  const chip = (active: boolean) =>
    `rounded-full px-2.5 py-1 text-xs transition ${
      active ? "bg-ink font-medium text-paper" : "border border-line bg-surface text-muted hover:bg-surface-2"
    }`;

  return (
    <section>
      <h2 className="mb-1 flex flex-wrap items-center gap-2 text-lg font-semibold">
        {S.title}
        <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-muted">{S.scopeBadge}</span>
        {season?.in_progress && (
          <span className="rounded bg-amber/10 px-1.5 py-0.5 text-[10px] font-medium text-amber">{S.inProgressBadge}</span>
        )}
      </h2>
      <p className="mb-3 text-[11px] text-faint">{S.subtitle}</p>

      {/* 季選擇（client 端切換；資料已全量在手，不重抓） */}
      {years.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label={S.yearSelectorLabel}>
          {[...years].reverse().map((y) => (
            <button key={y} type="button" onClick={() => setYear(y)} aria-pressed={year === y}
              className={`${chip(year === y)} font-mono tabular-nums`}>
              {y}
            </button>
          ))}
        </div>
      )}

      {!season ? (
        <div className="rounded-lg border border-line bg-surface p-4 text-sm text-muted">{S.emptyState}</div>
      ) : (
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
            {/* 雷達：七軸季內 z */}
            <div className="rounded-lg border border-line bg-surface p-3 lg:col-span-2">
              <div className="h-72 sm:h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData} outerRadius="74%">
                    <PolarGrid stroke={ct.line} />
                    <PolarAngleAxis dataKey="axis" tick={{ fontSize: 11, fill: ct.muted }} />
                    {/* 半徑軸釘死 ±2：z 是季內標準化值，截 ±2 顯示（研究消費建議） */}
                    <PolarRadiusAxis domain={[-2, 2]} tick={false} axisLine={false} />
                    <Radar dataKey="z" stroke={color} fill={color} fillOpacity={0.3} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-center text-[10px] text-faint">{S.radarCaption}</p>
            </div>

            {/* 軸明細：raw＋聯盟排名＋語意標注 */}
            <div className="rounded-lg border border-line bg-surface p-4 lg:col-span-3">
              <div className="mb-1 flex items-baseline gap-2">
                <h3 className="text-sm font-semibold text-ink">{S.detailHeading}</h3>
                <span className="text-[10px] text-faint">{S.detailCaption}</span>
              </div>
              <ul className="divide-y divide-line">
                {data.axes.map((a) => {
                  const v = season.axes[a.key];
                  const copy = TEAM_STYLE_COPY[a.key];
                  const badge = SEMANTICS_BADGE[a.semantics];
                  return (
                    <li key={a.key} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2">
                      <span className="w-20 shrink-0 text-sm font-medium text-ink">{a.label}</span>
                      {badge && (
                        <span className="rounded bg-surface-2 px-1 py-px text-[10px] text-muted">{badge}</span>
                      )}
                      <span className="text-xs text-muted tabular-nums">{copy.detail(v)}</span>
                      <span className="ml-auto flex items-baseline gap-2">
                        <span className="text-xs text-muted tabular-nums">{S.rankLabel(v.rank, season.n_teams)}</span>
                        <span className="w-12 text-right font-mono text-sm tabular-nums text-ink">{formatZ(v.z)}</span>
                      </span>
                      {(copy.desc || copy.note) && (
                        <span className="w-full text-[10px] text-faint">
                          {copy.desc}
                          {copy.desc && copy.note ? "・" : ""}
                          {copy.note}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

          {/* 歷史逐季：單軸 z 折線＋教練時間標記（約束 2：分段維持逐季） */}
          <div className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <h3 className="text-sm font-semibold text-ink">{S.historyHeading}</h3>
              <span className="text-[10px] text-faint">{S.historyCaption}</span>
            </div>
            <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label={S.axisSelectorLabel}>
              {data.axes.map((a) => (
                <button key={a.key} type="button" onClick={() => setHistoryAxis(a.key)}
                  aria-pressed={historyAxis === a.key} className={chip(historyAxis === a.key)}>
                  {a.label}
                </button>
              ))}
            </div>
            <div className="h-64 sm:h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={historyData} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <XAxis dataKey="year" {...chartAxis(ct)} />
                  <YAxis domain={[-2.5, 2.5]} ticks={[-2, -1, 0, 1, 2]} {...chartAxis(ct)} />
                  <ReferenceLine y={0} stroke={ct.faint} strokeDasharray="4 4" />
                  {/* 教練換帥年：僅時間標記（虛線；姓名列在圖下清單，不進圖面文案） */}
                  {markers.map((m) => (
                    <ReferenceLine key={m.year} x={m.year} stroke={ct.lineStrong} strokeDasharray="3 3" />
                  ))}
                  <Tooltip
                    contentStyle={chartTooltip(ct)}
                    formatter={(val) => [formatZ(Number(val)), historyMeta?.label ?? ""]}
                    labelFormatter={(label) => {
                      const s = historyData.find((d) => d.year === label);
                      return `${label}${s?.in_progress ? `（${S.inProgressBadge}）` : ""}`;
                    }}
                  />
                  <Line dataKey="z" stroke={color} strokeWidth={2} isAnimationActive={false}
                    dot={(props) => {
                      const { key, cx, cy, payload } = props as {
                        key?: string; cx?: number; cy?: number;
                        payload?: { in_progress?: boolean };
                      };
                      return (
                        <circle key={key} cx={cx} cy={cy} r={4} stroke={color} strokeWidth={2}
                          fill={payload?.in_progress ? ct.surface : color} />
                      );
                    }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-faint">
              {markers.length > 0 && (
                <span className="flex flex-wrap items-center gap-1.5">
                  {markers.map((m) => (
                    <span key={m.year} className="rounded bg-surface-2 px-1.5 py-0.5 tabular-nums text-muted">
                      {S.managerMarkerLabel(m.name, m.year)}
                    </span>
                  ))}
                </span>
              )}
              <span>{S.managerFootnote}</span>
              {inProgressYears.length > 0 && <span>{S.inProgressNote(inProgressYears)}</span>}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
