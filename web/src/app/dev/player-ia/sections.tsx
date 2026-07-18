"use client";

// UX-PLAYER-IA1 prototype：四層內容渲染器。以真實 fixture 摘要各現有模組（非完整圖表——
// 本卡只驗證 IA 導覽，模組完整遷移屬 UX-PLAYER-SECTIONS1）。每模組支援 正常/空/錯誤 三態。
import { Card, EmptyState } from "@/components/ui";
import { type Fixture, type LayerId, type Role, type RoleData, f3, isRetired, num } from "./lib";

// ---- 三態外框：錯誤態模擬（?state=error 時全模組套用，驗證錯誤處理一致性）----

function ModuleCard({ title, badge, state, emptyHint, children }: {
  title: string;
  badge?: string;
  state: "normal" | "empty" | "error";
  emptyHint?: string;
  children?: React.ReactNode;
}) {
  return (
    <Card className="mb-4">
      <h3 className="mb-2 text-sm font-semibold text-ink">
        {title}
        {badge && <span className="ml-2 rounded bg-accent/10 px-1.5 py-0.5 text-xs font-semibold text-accent">{badge}</span>}
      </h3>
      {state === "error" ? (
        <div className="rounded-lg border border-dashed border-line bg-surface-2 px-4 py-6 text-center text-sm text-muted">
          載入失敗——此區獨立重試，不阻塞其他區塊。
          <button className="ml-2 text-accent hover:underline">重試</button>
        </div>
      ) : state === "empty" ? (
        <EmptyState className="py-6">{emptyHint ?? "無資料"}</EmptyState>
      ) : children}
    </Card>
  );
}

type SectionProps = { fx: Fixture; role: Role; simError: boolean };

function roleData(fx: Fixture, role: Role): RoleData | undefined {
  return fx[role];
}

// ---- L1 總覽：本季核心數據＋相對聯盟位置＋特質＋近期趨勢 ----

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const min = Math.min(...values); const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / span) * 24}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" className="h-8 w-full" preserveAspectRatio="none" aria-hidden>
      <polyline points={pts} fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
    </svg>
  );
}

export function OverviewLayer({ fx, role, simError }: SectionProps) {
  const rd = roleData(fx, role);
  const s = role === "batting" ? fx.season.batting : fx.season.pitching;
  const adv = role === "batting" ? fx.advanced.batting : fx.advanced.pitching;
  const kindBadge = fx._meta.kind === "D" ? "二軍" : undefined;
  const retired = isRetired(fx);
  const st = (has: boolean): "normal" | "empty" | "error" => (simError ? "error" : has ? "normal" : "empty");

  const tiles: [string, string][] = role === "batting"
    ? [["AVG", f3(s?.avg)], ["OBP", f3(s?.obp)], ["SLG", f3(s?.slg)], ["OPS+", s?.ops_plus == null ? "—" : String(s.ops_plus)],
       ["PA", s?.pa == null ? "—" : String(s.pa)], ["HR", s?.hr == null ? "—" : String(s.hr)]]
    : [["ERA", s?.era == null ? "—" : String(s.era)], ["WHIP", s?.whip == null ? "—" : String(s.whip)],
       ["IP", s?.ip == null ? "—" : String(s.ip)], ["SO", s?.so == null ? "—" : String(s.so)],
       ["W-L", s ? `${s.w ?? 0}-${s.l ?? 0}` : "—"], ["ERA+", s?.era_plus == null ? "—" : String(s.era_plus)]];

  const prKeys = role === "batting"
    ? [["wOBA", "woba_pr"], ["SLG", "slg_pr"], ["打擊率", "ba_pr"]]
    : [["被wOBA", "woba_pr"], ["被打擊率", "ba_pr"], ["被長打率", "slg_pr"]];

  const trendVals = (rd?.trend.items ?? [])
    .map((r) => num(role === "batting" ? r.ops : r.era))
    .filter((v): v is number => v != null)
    .slice(-30);

  return (
    <>
      <ModuleCard title="本季成績" badge={kindBadge} state={st(!!s)}
        emptyHint={retired ? "已退役——本季無出賽，成績請見「生涯」層。" : "本季尚無成績。"}>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {tiles.map(([label, value]) => (
            <div key={label} className="rounded-lg bg-surface-2 px-2 py-2.5 text-center">
              <div className="text-[11px] text-muted">{label}</div>
              <div className="mt-0.5 font-mono text-lg leading-none tabular-nums text-ink">{value}</div>
            </div>
          ))}
        </div>
      </ModuleCard>

      <ModuleCard title="相對聯盟位置（官方 PR）" state={st(!!adv)}
        emptyHint="無官方進階資料（二軍／退役無官方 PR）。">
        <div className="space-y-1.5">
          {prKeys.map(([label, key]) => {
            const pr = num(adv?.[key]);
            return (
              <div key={key} className="flex items-center gap-2 text-xs">
                <span className="w-16 text-muted">{label}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line/60">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${pr ?? 0}%` }} />
                </div>
                <span className="w-8 text-right font-mono tabular-nums text-faint">{pr ?? "—"}</span>
              </div>
            );
          })}
        </div>
      </ModuleCard>

      <ModuleCard title="近期趨勢" state={st(trendVals.length >= 2)}
        emptyHint={retired ? "已退役——無本季走勢。" : "樣本不足，無法繪製走勢。"}>
        <Sparkline values={trendVals} />
        <p className="mt-1 text-[11px] text-faint">
          {role === "batting" ? "OPS" : "ERA"} 逐場累積（{trendVals.length} 場）
        </p>
      </ModuleCard>
    </>
  );
}

// ---- L2 打法／球路：逐球追蹤＋擊球品質＋位移＋配球 ----

export function ApproachLayer({ fx, role, simError }: SectionProps) {
  const rd = roleData(fx, role);
  const disc = rd?.discipline;
  const pitches = num(disc?.summary?.pitches) ?? 0;
  const kindBadge = fx._meta.kind === "D" ? "二軍" : undefined;
  const st = (has: boolean): "normal" | "empty" | "error" => (simError ? "error" : has ? "normal" : "empty");
  const trackHint = isRetired(fx)
    ? "已退役——逐球追蹤 2026 年起才有資料。"
    : "無逐球追蹤資料（部分球場未配置 TrackMan，樣本可能缺漏）。";
  const sparse = pitches > 0 && pitches < 50;

  const sum = disc?.summary ?? {};
  const discRows: [string, unknown][] = role === "batting"
    ? [["揮棒率", sum.swing_pct], ["揮空率", sum.whiff_pct], ["出棒追擊率", sum.chase_pct], ["好球帶率", sum.zone_pct]]
    : [["誘使揮棒率", sum.swing_pct], ["揮空率", sum.whiff_pct], ["CSW%", sum.csw_pct], ["好球帶率", sum.zone_pct]];

  return (
    <>
      <ModuleCard title={`逐球追蹤（${pitches} 球）`} badge={kindBadge} state={st(pitches > 0)} emptyHint={trackHint}>
        {sparse && (
          <p className="mb-2 rounded bg-surface-2 px-2 py-1 text-[11px] text-muted">
            ⚠ 樣本僅 {pitches} 球（場地覆蓋不足），數字僅供參考。
          </p>
        )}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {discRows.map(([label, v]) => (
            <div key={String(label)} className="rounded-lg bg-surface-2 px-2 py-2 text-center">
              <div className="text-[11px] text-muted">{String(label)}</div>
              <div className="mt-0.5 font-mono tabular-nums text-ink">{v == null ? "—" : `${v}%`}</div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-faint">
          正式版：進壘點散圖／擊球落點／熱區／揮棒紀律長條（遷移自 TrackingSection）。
        </p>
      </ModuleCard>

      <ModuleCard title="擊球品質" state={st(!!disc && Object.values(disc.quality ?? {}).some((v) => v != null))}
        emptyHint={trackHint}>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          {Object.entries(disc?.quality ?? {}).slice(0, 6).map(([k, v]) => (
            <span key={k}>{k}: <span className="font-mono text-ink">{v ?? "—"}</span></span>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-faint">正式版：彈道散點＋官方進階細項（QualitySection＋BattedMix）。</p>
      </ModuleCard>

      {role === "pitching" && (
        <ModuleCard title="球路位移與放球點" state={st(!!rd?.movement && rd.movement.summary.length > 0)}
          emptyHint={trackHint}>
          <table className="w-full text-xs">
            <thead><tr className="text-left text-muted">
              <th className="py-1">球種</th><th className="text-right">佔比</th><th className="text-right">均速</th>
              <th className="text-right">IVB</th><th className="text-right">HB</th>
            </tr></thead>
            <tbody>
              {(rd?.movement?.summary ?? []).map((m) => (
                <tr key={m.pt} className="border-t border-line">
                  <td className="py-1 text-ink">{m.pt}</td>
                  <td className="text-right font-mono tabular-nums">{m.usage}%</td>
                  <td className="text-right font-mono tabular-nums">{m.speed ?? "—"}</td>
                  <td className="text-right font-mono tabular-nums">{m.ivb ?? "—"}</td>
                  <td className="text-right font-mono tabular-nums">{m.hb ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-faint">
            放球點一致性：{rd?.movement?.release.consistency_cm ?? "—"} cm（正式版：MovementSection 完整散圖；標「推定球種」）
          </p>
        </ModuleCard>
      )}

      <ModuleCard title={role === "pitching" ? "球種配置" : "面對配球傾向"}
        state={st(!!rd && (rd.arsenal.items.length > 0 || rd.pitchMix.items.length > 0))} emptyHint={trackHint}>
        <div className="flex flex-wrap gap-2 text-xs">
          {(rd?.arsenal.items.length ? rd.arsenal.items.map((a) => `${a.pitch_type} ${a.usage}%`)
            : (rd?.pitchMix.items[0]?.mix ?? []).map((m) => `${m.pitch_type} ${m.pct}%`))
            .map((txt) => <span key={txt} className="rounded-full bg-surface-2 px-2.5 py-1 text-muted">{txt}</span>)}
        </div>
      </ModuleCard>
    </>
  );
}

// ---- L3 分項與對戰：vs team＋splits＋時段分項＋（未來）對戰洞察 ----

export function SplitsLayer({ fx, role, simError }: SectionProps) {
  const rd = roleData(fx, role);
  const st = (has: boolean): "normal" | "empty" | "error" => (simError ? "error" : has ? "normal" : "empty");
  const vs = rd?.vsTeam.items ?? [];
  const splits = (rd?.splitsSeason.items.length ? rd.splitsSeason.items : rd?.splitsCareer.items) ?? [];
  const splitsScope = rd?.splitsSeason.items.length ? "本季" : "生涯";

  return (
    <>
      <ModuleCard title="對戰各隊" state={st(vs.length > 0)}
        emptyHint={isRetired(fx) ? "已退役——本季無對戰資料；生涯對戰請切「生涯」範圍（正式版提供）。" : "本季尚無對戰資料。"}>
        <table className="w-full text-xs">
          <thead><tr className="text-left text-muted">
            <th className="py-1">對手</th><th className="text-right">{role === "batting" ? "PA" : "BF"}</th>
            <th className="text-right">{role === "batting" ? "AVG" : "被AVG"}</th>
          </tr></thead>
          <tbody>
            {vs.slice(0, 6).map((r) => (
              <tr key={String(r.fight_team_code)} className="border-t border-line">
                <td className="py-1 text-ink">{String(r.fight_team_name ?? r.fight_team_code)}</td>
                <td className="text-right font-mono tabular-nums">{String(r.plate_appearances ?? r.batters_faced ?? "—")}</td>
                <td className="text-right font-mono tabular-nums">{f3(r.avg ?? r.batting_average)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ModuleCard>

      <ModuleCard title={`分項明細（${splitsScope}）`} state={st(splits.length > 0)}
        emptyHint="此範圍無分項資料。">
        <div className="flex flex-wrap gap-2 text-xs">
          {splits.slice(0, 10).map((r, i) => (
            <span key={i} className="rounded-full bg-surface-2 px-2.5 py-1 text-muted">
              {String(r.item_name)}：{f3(r.avg ?? r.batting_average)}
            </span>
          ))}
          {splits.length > 10 && <span className="px-1 py-1 text-faint">…共 {splits.length} 項</span>}
        </div>
        <p className="mt-2 text-[11px] text-faint">正式版：分類手風琴＋本季/生涯＋例行/總冠軍/季後切換（DetailSection 分項）。</p>
      </ModuleCard>

      <ModuleCard title="生涯時段分項" state={st((rd?.trendCareer.items.length ?? 0) > 0)}
        emptyHint="無跨季時段資料。">
        <p className="text-xs text-muted">跨年同週合併 {rd?.trendCareer.items.length ?? 0} 個時段（正式版：月／週切換圖表）。</p>
      </ModuleCard>

      <ModuleCard title="對戰洞察（ML-MATCHUP1）" state={simError ? "error" : "empty"}
        emptyHint="尚未上線——依藍圖 §5.7 將顯示候選、PA、baseline、credibility 與 coverage（描述性、非預測）。" />
    </>
  );
}

// ---- L4 生涯：彙總＋逐年＋SABR 推算＋守備＋獎項 ----

export function CareerLayer({ fx, role, simError }: SectionProps) {
  const rd = roleData(fx, role);
  const cs = fx.careerStats;
  const agg = role === "batting" ? cs.batting : cs.pitching;
  const seasons = rd?.career.seasons ?? [];
  const sabrYears = (rd?.sabr.years ?? []).filter((y) => y.re24 != null || y.wsb != null);
  const fielding = fx.fieldingCareer.items.length ? fx.fieldingCareer.items : fx.fieldingSeason.items;
  const st = (has: boolean): "normal" | "empty" | "error" => (simError ? "error" : has ? "normal" : "empty");

  return (
    <>
      <ModuleCard title="生涯彙總" state={st(!!agg)} emptyHint="無生涯資料。">
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          <span>年資 <span className="font-mono text-ink">{agg?.seasons ?? "—"}</span> 季</span>
          {role === "batting" ? (
            <>
              <span>安打 <span className="font-mono text-ink">{cs.batting?.h ?? "—"}</span></span>
              <span>全壘打 <span className="font-mono text-ink">{cs.batting?.hr ?? "—"}</span></span>
              <span>打擊率 <span className="font-mono text-ink">{f3(cs.batting?.avg)}</span></span>
            </>
          ) : (
            <>
              <span>局數 <span className="font-mono text-ink">{cs.pitching?.ip ?? "—"}</span></span>
              <span>勝場 <span className="font-mono text-ink">{cs.pitching?.w ?? "—"}</span></span>
              <span>三振 <span className="font-mono text-ink">{cs.pitching?.so ?? "—"}</span></span>
            </>
          )}
        </div>
        <p className="mt-2 text-[11px] text-faint">正式版：最佳單季＋里程碑＋史上排名（CareerSummary）。</p>
      </ModuleCard>

      <ModuleCard title="生涯逐年" state={st(seasons.length > 0)} emptyHint="無逐年資料。">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-muted">
            <th className="py-1">年度</th><th>球隊</th>
            {role === "batting"
              ? <><th className="text-right">AVG</th><th className="text-right">HR</th><th className="text-right">OPS</th></>
              : <><th className="text-right">ERA</th><th className="text-right">W</th><th className="text-right">SO</th></>}
          </tr></thead>
          <tbody>
            {seasons.slice(-8).map((r) => (
              <tr key={String(r.year)} className="border-t border-line">
                <td className="py-1 text-ink">{String(r.year)}</td>
                <td className="text-muted">{String(r.teams ?? "—")}</td>
                {role === "batting"
                  ? <><td className="text-right font-mono tabular-nums">{f3(r.avg)}</td>
                      <td className="text-right font-mono tabular-nums">{String(r.hr ?? "—")}</td>
                      <td className="text-right font-mono tabular-nums">{f3(r.ops)}</td></>
                  : <><td className="text-right font-mono tabular-nums">{String(r.era ?? "—")}</td>
                      <td className="text-right font-mono tabular-nums">{String(r.w ?? "—")}</td>
                      <td className="text-right font-mono tabular-nums">{String(r.so ?? "—")}</td></>}
              </tr>
            ))}
          </tbody>
        </table>
      </ModuleCard>

      <ModuleCard title="進階指標（RE24／wSB 推算）" state={st(sabrYears.length > 0)}
        emptyHint="無推算樣本（逐打席 2018 年起）。">
        <div className="flex flex-wrap gap-2 text-xs">
          {sabrYears.slice(0, 6).map((y) => (
            <span key={y.year} className="rounded-full bg-surface-2 px-2.5 py-1 text-muted">
              {y.year}：RE24 <span className="font-mono text-ink">{y.re24 ?? "—"}</span>{y.rnk ? `（${y.rnk}/${y.n}）` : ""}
            </span>
          ))}
        </div>
      </ModuleCard>

      <ModuleCard title="守備" state={st(fielding.length > 0)} emptyHint="無守備資料（純 DH／投手打者）。">
        <div className="flex flex-wrap gap-2 text-xs">
          {fielding.slice(0, 5).map((r, i) => (
            <span key={i} className="rounded-full bg-surface-2 px-2.5 py-1 text-muted">
              {String(r.pos)}：{String(r.g)} 場・守備率 {f3(r.fpct)}
            </span>
          ))}
        </div>
      </ModuleCard>

      <ModuleCard title="獎項與經歷" state={st((cs.awards?.length ?? 0) > 0)} emptyHint="無獎項紀錄。">
        <div className="flex flex-wrap gap-2 text-xs">
          {(cs.awards ?? []).slice(0, 6).map((a, i) => (
            <span key={i} className="rounded-full bg-surface-2 px-2.5 py-1 text-muted">{a.year} {a.award}</span>
          ))}
          {(cs.awards?.length ?? 0) > 6 && <span className="px-1 py-1 text-faint">…共 {cs.awards!.length} 項</span>}
        </div>
      </ModuleCard>
    </>
  );
}

export const LAYER_RENDERERS: Record<LayerId, (p: SectionProps) => React.ReactNode> = {
  overview: (p) => <OverviewLayer {...p} />,
  approach: (p) => <ApproachLayer {...p} />,
  splits: (p) => <SplitsLayer {...p} />,
  career: (p) => <CareerLayer {...p} />,
};
