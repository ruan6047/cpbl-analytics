"use client";

// 球員旗艦頁：C・Hybrid IA（UX-PLAYER-IA1 決策）——Hero 與總覽常駐，
// 打法/球路、分項與對戰、生涯三層以 ?sec= 切換，role 以 ?role= 表達（切 role 保留當前層）。
// state 與資料抓取集中於此；區塊 UI 拆在同目錄，層與資料需求的判斷集中在 layers.ts。
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { type PlayerProfile, type StatRow, detail } from "@/lib/client";
import { EmptyState } from "@/components/ui";
import { codeFromName, teamColor } from "@/lib/teams";
import { type Ability, type CareerStats, type Disc, type Role } from "./lib";
import { SUB_LAYERS, type SubLayer, needsData, roleFromParam, subLayerFromParam, subLayerLabel } from "./layers";
import { CareerYearlySection, SplitsSection } from "./detail";
import { type FieldLeague, FieldingSection } from "./fielding";
import { PlayerHero } from "./hero";
import { Tabs } from "./parts";
import { SabrSection } from "./sabr";
import { CareerSummary, SeasonSection, TraitsChips } from "./season";
import { BattedMixSection, MovementSection, type Movement, QualitySection, TrackingSection } from "./tracking";
import { CareerTrendCard, SeasonTrendCard, VsTeamCard } from "./trend";

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [season, setSeason] = useState<{ batting: StatRow | null; pitching: StatRow | null } | null>(null);
  const [advanced, setAdvanced] = useState<{ batting: StatRow | null; pitching: StatRow | null } | null>(null);
  const [disc, setDisc] = useState<Disc | null>(null);
  const [pitchMix, setPitchMix] = useState<{ bucket: string; n: number; mix: { pitch_type: string; pct: number }[] }[] | null>(null);
  const [arsenal, setArsenal] = useState<{ pitch_type: string; n: number; usage: number;
    avg_speed: number | null; avg_spin: number | null; whiff_pct: number | null; avg_ev: number | null }[] | null>(null);
  const [mov, setMov] = useState<Movement | null>(null);
  const [fielding, setFielding] = useState<StatRow[] | null>(null);
  const [fieldingCareer, setFieldingCareer] = useState<StatRow[] | null>(null);
  const [fieldFromYear, setFieldFromYear] = useState<number | null>(null);
  const [fieldLeague, setFieldLeague] = useState<FieldLeague | undefined>();
  const [qualifyOuts, setQualifyOuts] = useState<number | undefined>();
  const [vsTeam, setVsTeam] = useState<StatRow[] | null>(null);
  const [career, setCareer] = useState<StatRow[] | null>(null);
  const [careerMonthly, setCareerMonthly] = useState<StatRow[] | null>(null);
  const [careerStats, setCareerStats] = useState<CareerStats | null>(null);
  const [ability, setAbility] = useState<Ability | null>(null);
  const [trend, setTrend] = useState<StatRow[] | null>(null);
  // 本季成績層級：二軍選手預設採計二軍(D)、可切換看一軍(A)。
  const [seasonKind, setSeasonKind] = useState<"A" | "D">("A");
  // 能力值卡尺度（本季/生涯）；IA 分層後只影響 Hero 的能力卡，不再控制區塊顯隱。
  const [dataTab, setDataTab] = useState<"season" | "career">("season");

  useEffect(() => {
    detail.profile(id).then((d) => {
      if (!d.player) return setNotFound(true);
      setProfile(d.player);
      const p = d.player;
      // 退役/教練（本季無登錄層級）能力卡預設生涯；二軍選手本季成績預設採計二軍。
      if (!p.roster_level) setDataTab("career");
      if (p.roster_level === "二軍") setSeasonKind("D");
    }).catch(() => setNotFound(true));
    detail.careerStats(id).then(setCareerStats).catch(() => setCareerStats(null));
    detail.abilityCard(id).then(setAbility).catch(() => setAbility(null));
  }, [id]);

  // ---- 導覽狀態（URL 為單一事實來源；role 與層彼此獨立，故切 role 天然保留當前層）----
  // role tab：含本季一軍(is_*)、生涯曾任(was_*)、本季二軍(farm_*) 任一即列。
  const roles: { v: Role; label: string }[] = [];
  if (profile?.is_batter || profile?.was_batter || profile?.farm_batter) roles.push({ v: "batting", label: "打擊" });
  if (profile?.is_pitcher || profile?.was_pitcher || profile?.farm_pitcher) roles.push({ v: "pitching", label: "投球" });
  // role 預設：有打擊 role 先打擊，否則投球（沿用原邏輯）
  const fallbackRole: Role = roles.some((r) => r.v === "batting") || roles.length === 0 ? "batting" : "pitching";
  const role = roleFromParam(params.get("role"), roles.map((r) => r.v), fallbackRole);
  // 退役/教練：本季完全無登錄層級(roster_level=null) → 本季模組必空，預設層落生涯。
  // 二軍-only 球員有 roster_level（二軍）故不算退役。
  const isRetired = !!profile && !profile.roster_level;
  const sec = subLayerFromParam(params.get("sec"), isRetired);

  const setQuery = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    // scroll:false —— 切 role 或切層都不該把使用者彈回頁首。
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  // ---- 依層載入：常駐群組恆抓，層專屬群組只在進入該層時抓一次（key 變才重抓）----
  const loaded = useRef<Record<string, string>>({});
  const once = (group: string, key: string, run: () => void) => {
    if (loaded.current[group] === key) return;
    loaded.current[group] = key;
    run();
  };

  useEffect(() => {
    once("season", `${id}-${seasonKind}`, () => {
      setSeason(null);
      detail.season(id, seasonKind).then(setSeason).catch(() => setSeason(null));
    });
    once("advanced", `${id}-${seasonKind}`, () => {
      setAdvanced(null);
      detail.advanced(id, seasonKind).then(setAdvanced).catch(() => setAdvanced(null));
    });
    once("trend", `${id}-${role}`, () => {
      setTrend(null);
      detail.trend(id, role).then((d) => setTrend(d.items)).catch(() => setTrend([]));
    });
  }, [id, role, seasonKind]);

  // L2 打法／球路：逐球追蹤、配球傾向、球種卡、球種位移（僅投手）
  useEffect(() => {
    if (!needsData("tracking", sec)) return;
    once("tracking", `${id}-${role}-${seasonKind}`, () => {
      setDisc(null);
      setPitchMix(null);
      setArsenal(null);
      detail.discipline(id, role, seasonKind).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
      detail.pitchMix(id, role, seasonKind).then((d) => setPitchMix(d.items)).catch(() => setPitchMix([]));
      // 球種卡（arsenal 端點僅一軍樣本）
      if (seasonKind === "A") detail.arsenal(id, role).then((d) => setArsenal(d.items)).catch(() => setArsenal([]));
      else setArsenal([]);
    });
    if (role !== "pitching") return setMov(null);
    once("movement", `${id}-${seasonKind}`, () => {
      setMov(null);
      // 球種位移（ML-PT2 Phase1；僅投手視角）
      detail.movement(id, seasonKind).then(setMov).catch(() => setMov(null));
    });
  }, [id, role, seasonKind, sec]);

  // L3 分項與對戰：對戰各隊、生涯時段分項（分項明細由 SplitsSection 自抓）
  useEffect(() => {
    if (!needsData("splits", sec)) return;
    once("vsTeam", `${id}-${role}`, () => {
      setVsTeam(null);
      detail.vsTeam(id, role).then((d) => setVsTeam(d.items)).catch(() => setVsTeam([]));
    });
    // 生涯時段分項：固定以「週」跨年合併
    once("careerMonthly", `${id}-${role}`, () => {
      setCareerMonthly(null);
      detail.trendCareer(id, role, "week").then((d) => setCareerMonthly(d.items)).catch(() => setCareerMonthly([]));
    });
  }, [id, role, sec]);

  // L4 生涯：逐年、守備（守備與 role 無關，只隨一/二軍鏡頭）
  useEffect(() => {
    if (!needsData("career", sec)) return;
    once("career", `${id}-${role}`, () => {
      setCareer(null);
      detail.career(id, role).then((d) => setCareer(d.seasons)).catch(() => setCareer([]));
    });
    once("fieldingCareer", id, () => {
      detail.fielding(id, "career").then((d) => { setFieldingCareer(d.items); setFieldFromYear(d.from_year ?? null); })
        .catch(() => setFieldingCareer([]));
    });
    once("fielding", `${id}-${seasonKind}`, () => {
      setFielding(null);
      detail.fielding(id, "season", seasonKind).then((d) => {
        setFielding(d.items);
        setFieldLeague(d.league);
        setQualifyOuts(d.qualify_outs);
      }).catch(() => setFielding([]));
    });
  }, [id, role, seasonKind, sec]);

  if (notFound) return <p className="text-sm text-muted">查無此球員。</p>;
  if (!profile) return <EmptyState>載入中…</EmptyState>;

  const s = season ? (role === "batting" ? season.batting : season.pitching) : null;
  // 生涯資料是否存在（打者或投手任一）→ 控制能力卡「生涯」尺度顯示
  const hasCareer = !!(careerStats?.batting || careerStats?.pitching);

  // 計算球員隊色作為 hover 光暈顏色
  const ongoingCoach = careerStats?.coach_tenures?.find((t) => t.to == null) ?? null;
  const primaryTeam = (careerStats?.teams ?? []).length
    ? [...(careerStats?.teams ?? [])].sort((a, b) => (b.to - b.from) - (a.to - a.from))[0]
    : null;
  const tc = profile.team ? codeFromName(profile.team)
    : ongoingCoach ? codeFromName(ongoingCoach.team)
    : (primaryTeam?.code ?? null);
  const color = teamColor(tc); // teamColor 已含 fallback（未知隊→faint 灰）

  return (
    <div style={{ "--hover-color": color } as React.CSSProperties}>
      <PlayerHero profile={profile} careerStats={careerStats} ability={ability} role={role} s={s}
        isRetired={isRetired} hasCareer={hasCareer} dataTab={dataTab} setDataTab={setDataTab} />

      {roles.length > 1 && (
        <div className="mb-5"><Tabs opts={roles} v={role} set={(r) => setQuery("role", r)} /></div>
      )}

      {/* ---- L1 總覽（常駐）：現在如何 ---- */}
      <section aria-label="總覽" className="mb-6">
        {isRetired ? (
          <div className="mb-5 rounded-xl border border-line bg-surface p-4 text-sm text-muted">
            本季無登錄紀錄（已退役／轉任教練），本季成績與逐球追蹤皆無資料；生涯表現請見下方「生涯」。
          </div>
        ) : (
          <>
            <SeasonSection profile={profile} s={s} role={role}
              seasonKind={seasonKind} setSeasonKind={setSeasonKind} advanced={advanced} />
            <TraitsChips id={id} role={role} />
          </>
        )}
        <div className="mb-2">
          <SeasonTrendCard trend={trend} role={role} isRetired={isRetired} />
        </div>
      </section>

      {/* ---- 進階三層：sticky 子導覽（?sec=）---- */}
      <SubNav sec={sec} role={role} setSec={(l) => setQuery("sec", l)} />

      <div role="tabpanel" aria-label={subLayerLabel(sec, role)}>
        {sec === "approach" && (
          <>
            {/* key 重掛：id/role/seasonKind 變更時重置球種鏡頭（沿用原重置語義） */}
            <TrackingSection key={`${id}-${role}-${seasonKind}`} disc={disc} role={role} seasonKind={seasonKind} />
            <QualitySection advanced={advanced} role={role} />
            {role === "pitching" && <MovementSection mov={mov} />}
            <BattedMixSection disc={disc} pitchMix={pitchMix} arsenal={arsenal} role={role} />
          </>
        )}

        {sec === "splits" && (
          <>
            <section className="mb-6">
              <div className="grid items-stretch gap-6 lg:grid-cols-2">
                <CareerTrendCard careerMonthly={careerMonthly} role={role} />
                <VsTeamCard vsTeam={vsTeam} role={role} />
              </div>
            </section>
            <SplitsSection id={id} role={role} seasonKind={seasonKind} isRetired={isRetired} />
          </>
        )}

        {sec === "career" && (
          <>
            <CareerSummary careerStats={careerStats} role={role} />
            <CareerYearlySection career={career} role={role} />
            <SabrSection id={id} role={role} />
            <FieldingSection fielding={fielding} fieldingCareer={fieldingCareer} fieldFromYear={fieldFromYear}
              league={fieldLeague} qualifyOuts={qualifyOuts} seasonKind={seasonKind} />
          </>
        )}
      </div>

      {/* 資料說明（統一彙整於頁尾，各區不再重複） */}
      <details className="mb-6 rounded-xl border border-line bg-surface">
        <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium text-muted hover:text-ink">
          資料說明與名詞解釋
        </summary>
        <div className="space-y-1.5 border-t border-line px-4 py-3 text-[11px] leading-relaxed text-faint">
          <p>· <span className="text-muted">能力值卡</span>：各軸為多項指標綜合的全聯盟百分位 [PR]（本季 打 AB≥50／投 IP≥20；生涯 AB≥300／IP≥100）。本季納官方進階（初速／強擊球%／Barrel%／揮空率／wOBA，覆蓋稀疏，無則退回傳統指標）；等級 S–G 由 PR 換算，皆客觀自算。滑鼠移到軸名看組成與權重。</p>
          <p>· <span className="text-muted">官方進階 · PR</span>：stats.cpbl 官方 TrackMan 全季值；色條＝PR（藍低→紅高）。打者為進攻、投手為被打數值。</p>
          <p>· <span className="text-muted">生涯／史上排名</span>：一軍例行賽各季合計（近兩季由逐場補）；史上排名以官方歷年累計、近兩季另計。生涯逐年源 cpbl-opendata（不含當季）。</p>
          <p>· <span className="text-muted">逐球追蹤</span>：部分球場未配置設備、涵蓋場次少於全季，與官方進階全季值會有差異；擊球品質分布紅框＝強勁擊球理想仰角帶（近似 barrel 甜蜜區）。</p>
          <p>· <span className="text-muted">一／二軍</span>：本季主要登錄層級由官網升降事件重建登錄天數判定。主守位＝本季出賽最多的守位或指定打擊（DH 由打擊出賽扣守備推算）。</p>
          <p>· <span className="text-muted">進階指標（推算）</span>：RE24／wSB／捕手 RA9 以自建 CPBL 得分期望矩陣（逐打席 2018–25，經外部資料交叉驗證）與官方計數推算，非官方數據。RE24 名次為該年 PA≥200／BF≥200 合格者；捕手 RA/9 含非自責分（非 cERA）；跨年代比較受得分環境影響。</p>
        </div>
      </details>

      <div className="flex gap-4 text-sm">
        <Link href="/matchups" className="text-accent hover:underline">投打對決 →</Link>
        <Link href="/batters" className="text-muted hover:text-ink">← 返回排行</Link>
      </div>
    </div>
  );
}

/** 進階三層 sticky 子導覽（WAI-ARIA tabs：←/→ 移動並切換）。 */
function SubNav({ sec, role, setSec }: { sec: SubLayer; role: Role; setSec: (l: SubLayer) => void }) {
  const idx = Math.max(0, SUB_LAYERS.indexOf(sec));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  // 只有使用者用鍵盤操作過 tablist 才把焦點跟著移動；deep-link 直開不搶焦點。
  const keyboardMoved = useRef(false);
  const onKey = (e: React.KeyboardEvent) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    keyboardMoved.current = true;
    setSec(SUB_LAYERS[(idx + delta + SUB_LAYERS.length) % SUB_LAYERS.length]);
  };
  useEffect(() => {
    if (!keyboardMoved.current) return;
    refs.current[idx]?.focus({ preventScroll: true });
  }, [idx]);
  return (
    <div role="tablist" aria-label="球員資料分層" onKeyDown={onKey}
      className="sticky top-0 z-20 -mx-1 mb-4 flex gap-1 overflow-x-auto border-b border-line bg-paper px-1 py-2">
      {SUB_LAYERS.map((l, i) => (
        <button key={l} role="tab" aria-selected={sec === l} tabIndex={sec === l ? 0 : -1}
          ref={(el) => { refs.current[i] = el; }}
          onClick={() => setSec(l)}
          className={`whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm transition ${
            sec === l ? "bg-ink font-medium text-paper" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
          {subLayerLabel(l, role)}
        </button>
      ))}
    </div>
  );
}
