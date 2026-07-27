"use client";

import { useEffect, useState } from "react";
import {
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceArea,
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
  buildHistoryVM,
  clampZ,
  formatZ,
  managerRuns,
  tenurePaletteFrom,
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
  // 預設第一軸（速度戰）：raw＋聯盟平均模式；discipline 選中時才退回 z 呈現。
  const [historyAxis, setHistoryAxis] = useState<TeamStyleAxisKey>("speed");

  const season = data.seasons.find((s) => s.year === year);
  const color = ct.series[0];

  const radarData = season
    ? data.axes.map((a) => ({ axis: a.label, z: clampZ(season.axes[a.key].z) }))
    : [];

  const runs = managerRuns(data.seasons);
  const inProgressYears = data.seasons.filter((s) => s.in_progress).map((s) => s.year);

  // 任期標色（需求方第三批＋補充裁定）：--chart-2 起輪替，**跳過 chart-1（資料
  // 折線專用）與 chart-6（中性灰＝參考元素保留：聯盟均線）**；顏色僅作**身分
  // 區辨**（非 up/down、非好壞）；圖內背景帶低 alpha 不壓折線。
  // 同一教練的顏色在圖內標注／chips／tooltip 三處一致（keyed by 任期段 index）。
  const tenurePalette = tenurePaletteFrom(ct.series);
  const runColor = (i: number) => tenurePalette[i % tenurePalette.length];
  // 年 → 任期（有標記的季才有歸屬；未標年（如統一 2019）無色，維持不標語意）
  const tenureOfYear = new Map<number, { name: string; color: string }>();
  data.seasons.forEach((s) => {
    if (s.manager == null) return;
    const i = runs.findIndex((r) => r.name === s.manager && r.from <= s.year && s.year <= r.to);
    if (i >= 0) tenureOfYear.set(s.year, { name: runs[i].name, color: runColor(i) });
  });

  // 圖內教練姓名：375px 下 5+ 任期標籤會疊，窄螢幕（<640px，沿 mobileHide 界線）
  // 只留換帥虛線＋圖下 chips；寬螢幕才在圖內標姓名（僅時間標記，無任何風格文案）。
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  // 歷史逐季（需求方 2026-07-27 續審裁定）：畫「原始值」＋同圖疊當季聯盟平均參考線
  // （讓聯盟環境逐年變化看得見，避免把年代效應誤讀成球隊變化）；z 與排名退 tooltip。
  // discipline 複合軸無單一 raw（凍結 spec），該軸退回 z 呈現並以 caption 說明。
  // 聯盟基準的呈現契約（raw＝均線序列／z＝標示 y=0）由 buildHistoryVM 給定並經
  // 測試釘住——元件只認 vm，不得自行決定畫不畫（第四批回歸的防再犯）。
  const historyCopy = TEAM_STYLE_COPY[historyAxis];
  const vm = buildHistoryVM(historyAxis, data.seasons);
  const rawMode = vm.mode === "raw";
  const historyData = vm.points;
  // 數值 x 軸（year ± 0.5 半格）：任期背景帶才能完整覆蓋起迄年（含單季任期與
  // 位於時間軸尾端的當季任期——類別軸上零寬畫不出來）；刻度仍逐年。
  const xMin = Math.min(...years) - 0.5;
  const xMax = Math.max(...years) + 0.5;

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

          {/* 歷史逐季：單軸原始值折線＋聯盟平均參考線＋教練時間標記（約束 2：分段維持逐季） */}
          <div className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <h3 className="text-sm font-semibold text-ink">{S.historyHeading}</h3>
              <span className="text-[10px] text-faint">{rawMode ? S.historyCaption : S.historyCaptionZ}</span>
            </div>
            <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label={S.axisSelectorLabel}>
              {data.axes.map((a) => (
                <button key={a.key} type="button" onClick={() => setHistoryAxis(a.key)}
                  aria-pressed={historyAxis === a.key} className={chip(historyAxis === a.key)}>
                  {a.label}
                </button>
              ))}
            </div>
            {/* 兩系列必有 legend（設計系統 §6.3）；z 退回模式的基準線在圖內直接標示 */}
            {rawMode && (
              <div className="mb-1 flex items-center gap-3 text-[10px] text-muted">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-0.5 w-4 rounded" style={{ background: color }} />
                  {S.legendTeam}
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-4 border-t-2 border-dotted" style={{ borderColor: ct.muted }} />
                  {S.legendLeague}
                </span>
              </div>
            )}
            <div className="h-64 sm:h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={historyData} margin={{ top: 8, right: 12, bottom: 0, left: rawMode ? -6 : -18 }}>
                  {/* 數值軸＋半格 domain：任期帶覆蓋 from−0.5～to+0.5（單季／尾端當季皆有寬度） */}
                  <XAxis dataKey="year" type="number" domain={[xMin, xMax]} ticks={years} {...chartAxis(ct)} />
                  {rawMode ? (
                    <YAxis domain={["auto", "auto"]} tickFormatter={historyCopy.formatRaw} {...chartAxis(ct)} />
                  ) : (
                    <YAxis domain={[-2.5, 2.5]} ticks={[-2, -1, 0, 1, 2]} {...chartAxis(ct)} />
                  )}
                  {/* z 退回模式的聯盟基準：z=0 即聯盟平均，標示同一文案（vm 契約，測試釘住）。
                      樣式與換帥垂直線區辨：基準/均線＝點虛線＋muted；換帥＝短劃線＋lineStrong */}
                  {vm.zeroBaseline && (
                    <ReferenceLine y={0} stroke={ct.muted} strokeDasharray="2 4"
                      label={{ value: vm.baselineLabel, position: "insideTopRight", fill: ct.muted, fontSize: 10 }} />
                  )}
                  {/* 教練任期：低 alpha 同色背景帶（未標年不上色）＋換帥短劃線＋
                      （寬螢幕）圖內同色姓名——僅時間標記，無風格文案 */}
                  {runs.map((m, i) => (
                    <ReferenceArea key={`band-${m.from}`} x1={m.from - 0.5} x2={m.to + 0.5}
                      fill={runColor(i)} fillOpacity={0.08} stroke="none"
                      label={narrow ? undefined : (props) => {
                        const vb = (props as { viewBox?: { x?: number; y?: number } }).viewBox;
                        return (
                          <text x={(vb?.x ?? 0) + 4} y={(vb?.y ?? 0) + 12}
                            fill={runColor(i)} fontSize={10}>
                            {m.name}
                          </text>
                        );
                      }} />
                  ))}
                  {runs.map((m) => (
                    m.from - 0.5 > xMin && (
                      <ReferenceLine key={`chg-${m.from}`} x={m.from - 0.5}
                        stroke={ct.lineStrong} strokeDasharray="3 3" />
                    )
                  ))}
                  <Tooltip
                    content={({ active, payload }) => {
                      const p = payload?.[0]?.payload as (typeof historyData)[number] | undefined;
                      if (!active || !p) return null;
                      const tenure = tenureOfYear.get(p.year);
                      return (
                        <div style={chartTooltip(ct)} className="px-2.5 py-1.5">
                          <div className="font-medium">
                            {p.year}
                            {p.in_progress ? `（${S.inProgressBadge}）` : ""}
                            {/* 教練名＝時間標記；同任期同色（未判定年無歸屬不顯示） */}
                            {tenure && (
                              <span className="ml-1.5" style={{ color: tenure.color }}>{tenure.name}</span>
                            )}
                          </div>
                          <div>{historyCopy.detail(p.v)}</div>
                          {rawMode && p.v.league_raw_mean != null && (
                            <div>{S.tooltipLeagueLabel} {historyCopy.formatRaw?.(p.v.league_raw_mean)}</div>
                          )}
                          <div>{S.rankLabel(p.v.rank, p.n_teams)}・z {formatZ(p.v.z)}</div>
                        </div>
                      );
                    }}
                  />
                  {/* 聯盟平均：降飽和**點虛線**參考系列（vm 契約，測試釘住；與換帥
                      短劃線樣式區辨——跨年可比的誠實性；年代效應可視） */}
                  {vm.leagueSeries && (
                    <Line dataKey="league" stroke={ct.muted} strokeWidth={1.5} strokeDasharray="2 4"
                      strokeLinecap="round" dot={false} isAnimationActive={false} />
                  )}
                  <Line dataKey="value" stroke={color} strokeWidth={2} isAnimationActive={false}
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
              {runs.length > 0 && (
                <span className="flex flex-wrap items-center gap-1.5">
                  {runs.map((m, i) => (
                    <span key={m.from} className="rounded px-1.5 py-0.5 tabular-nums"
                      style={{ color: runColor(i), background: `${runColor(i)}1f` }}>
                      {/* 任期止於進行中賽季＝現任 → 開區間「名 起–」（其餘閉區間） */}
                      {inProgressYears.includes(m.to)
                        ? S.managerMarkerLabelOpen(m.name, m.from)
                        : S.managerMarkerLabel(m.name, m.from, m.to)}
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
