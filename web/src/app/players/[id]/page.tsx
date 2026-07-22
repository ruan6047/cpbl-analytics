"use client";

// 球員旗艦頁：scope、role、view、level 四軸分離，URL 為單一事實來源。
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { type PlayerProfile, type StatRow, detail } from "@/lib/client";
import { EmptyState } from "@/components/ui";
import { ContextSwitcher, HierarchicalTabs, type HierarchicalTabGroup } from "@/components/hierarchical-tabs";
import { codeFromName, teamColor } from "@/lib/teams";
import { type Ability, type CareerStats, type Disc, type Role } from "./lib";
import {
  type PlayerLevel, type PlayerScope, type PlayerView, createLoadTracker, loadGroup,
  playerNavFromParams, roleLabel, viewsFor,
} from "./layers";
import { CareerYearlySection, SplitsSection } from "./detail";
import { type FieldLeague, FieldingSection } from "./fielding";
import { PlayerMatchupsSection } from "./matchups-section";
import { PlayerHero } from "./hero";
import { SabrSection } from "./sabr";
import { CareerSummary, SeasonSection, TraitsChips } from "./season";
import { BattedMixSection, MovementSection, type Movement, QualitySection, TrackingSection } from "./tracking";
import { CareerTrendCard, SeasonTrendCard, VsTeamCard } from "./trend";

const VIEW_LABEL: Record<PlayerView, string> = {
  overview: "總覽",
  tracking: "逐球追蹤",
  yearly: "逐年成績",
  splits: "分項對戰",
  fielding: "守備",
  value: "進階價值",
};

const PLAYER_TAB_GROUPS: readonly HierarchicalTabGroup<PlayerScope, PlayerView>[] = (["season", "career"] as const)
  .map((scope) => ({
    value: scope,
    label: scope === "season" ? "本季" : "生涯",
    items: viewsFor(scope).map((view) => ({ value: view, label: VIEW_LABEL[view] })),
  }));

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
  const [trend, setTrend] = useState<StatRow[] | null>(null);
  const [careerStats, setCareerStats] = useState<CareerStats | null>(null);
  const [ability, setAbility] = useState<Ability | null>(null);

  useEffect(() => {
    setNotFound(false);
    setProfile(null);
    detail.profile(id).then((d) => d.player ? setProfile(d.player) : setNotFound(true))
      .catch(() => setNotFound(true));
    detail.careerStats(id).then(setCareerStats).catch(() => setCareerStats(null));
    detail.abilityCard(id).then(setAbility).catch(() => setAbility(null));
  }, [id]);

  const roles: Role[] = [];
  if (profile?.is_batter || profile?.was_batter || profile?.farm_batter) roles.push("batting");
  if (profile?.is_pitcher || profile?.was_pitcher || profile?.farm_pitcher) roles.push("pitching");
  const isRetired = !!profile && !profile.roster_level;
  const nav = playerNavFromParams({
    scope: params.get("scope"),
    view: params.get("view"),
    role: params.get("role"),
    level: params.get("level"),
    sec: params.get("sec"),
  }, roles, isRetired, profile?.roster_level);

  const replaceNav = (patch: Partial<{ scope: PlayerScope; view: PlayerView; role: Role; level: PlayerLevel }>) => {
    const next = new URLSearchParams(params.toString());
    const scope = patch.scope ?? nav.scope;
    const requestedView = patch.view ?? nav.view;
    const view = viewsFor(scope).includes(requestedView) ? requestedView : "overview";
    next.set("scope", scope);
    next.set("view", view);
    next.set("role", patch.role ?? nav.role);
    if (scope === "season") next.set("level", patch.level ?? nav.level);
    else next.delete("level");
    next.delete("sec");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  const tracker = useRef(createLoadTracker());
  const once = (group: string, key: string, run: () => void) => {
    if (tracker.current(group, key)) run();
  };

  // 本季資料只在本季 scope 載入；生涯畫面不再背景載入或渲染本季總覽。
  useEffect(() => {
    if (!profile || nav.scope !== "season") return;
    once(loadGroup("season"), `${id}-${nav.level}`, () => {
      setSeason(null);
      detail.season(id, nav.level).then(setSeason).catch(() => setSeason(null));
    });
    if (nav.view === "overview" || nav.view === "tracking") {
      once(loadGroup("advanced"), `${id}-${nav.level}`, () => {
        setAdvanced(null);
        detail.advanced(id, nav.level).then(setAdvanced).catch(() => setAdvanced(null));
      });
    }
  }, [id, nav.scope, nav.view, nav.level, profile]);

  useEffect(() => {
    if (!profile || nav.scope !== "season" || nav.view !== "overview") return;
    once(loadGroup("trend", nav.role), `${id}-${nav.role}`, () => {
      setTrend(null);
      detail.trend(id, nav.role).then((d) => setTrend(d.items)).catch(() => setTrend([]));
    });
  }, [id, nav.scope, nav.view, nav.role, profile]);

  useEffect(() => {
    if (!profile || nav.scope !== "season" || nav.view !== "tracking") return;
    once(loadGroup("tracking", nav.role), `${id}-${nav.role}-${nav.level}`, () => {
      setDisc(null);
      setPitchMix(null);
      setArsenal(null);
      detail.discipline(id, nav.role, nav.level).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
      detail.pitchMix(id, nav.role, nav.level).then((d) => setPitchMix(d.items)).catch(() => setPitchMix([]));
      if (nav.level === "A") detail.arsenal(id, nav.role).then((d) => setArsenal(d.items)).catch(() => setArsenal([]));
      else setArsenal([]);
    });
    if (nav.role === "pitching") {
      once(loadGroup("movement"), `${id}-${nav.level}`, () => {
        setMov(null);
        detail.movement(id, nav.level).then(setMov).catch(() => setMov(null));
      });
    }
  }, [id, nav.scope, nav.view, nav.role, nav.level, profile]);

  useEffect(() => {
    if (!profile || nav.view !== "splits") return;
    if (nav.scope === "season") {
      once(loadGroup("splits", nav.role), `${id}-${nav.role}`, () => {
        setVsTeam(null);
        detail.vsTeam(id, nav.role).then((d) => setVsTeam(d.items)).catch(() => setVsTeam([]));
      });
    }
  }, [id, nav.scope, nav.view, nav.role, profile]);

  useEffect(() => {
    if (!profile || nav.scope !== "career" || nav.view !== "overview") return;
    once(loadGroup("trend", nav.role) + ":career", `${id}-${nav.role}`, () => {
      setCareerMonthly(null);
      detail.trendCareer(id, nav.role, "week").then((d) => setCareerMonthly(d.items))
        .catch(() => setCareerMonthly([]));
    });
  }, [id, nav.scope, nav.view, nav.role, profile]);

  useEffect(() => {
    if (!profile || nav.view !== "fielding") return;
    if (nav.scope === "career") {
      once(loadGroup("fielding") + ":career", id, () => {
        setFieldingCareer(null);
        detail.fielding(id, "career").then((d) => {
          setFieldingCareer(d.items);
          setFieldFromYear(d.from_year ?? null);
        }).catch(() => setFieldingCareer([]));
      });
      return;
    }
    once(loadGroup("fielding"), `${id}-${nav.level}`, () => {
      setFielding(null);
      detail.fielding(id, "season", nav.level).then((d) => {
        setFielding(d.items);
        setFieldLeague(d.league);
        setQualifyOuts(d.qualify_outs);
      }).catch(() => setFielding([]));
    });
    if (nav.level === "D") {
      once(loadGroup("fielding") + ":career", id, () => {
        setFieldingCareer(null);
        detail.fielding(id, "career").then((d) => {
          setFieldingCareer(d.items);
          setFieldFromYear(d.from_year ?? null);
        }).catch(() => setFieldingCareer([]));
      });
    }
  }, [id, nav.scope, nav.view, nav.level, profile]);

  useEffect(() => {
    if (!profile || nav.scope !== "career" || nav.view !== "yearly") return;
    once(loadGroup("career", nav.role), `${id}-${nav.role}`, () => {
      setCareer(null);
      detail.career(id, nav.role).then((d) => setCareer(d.seasons)).catch(() => setCareer([]));
    });
  }, [id, nav.scope, nav.view, nav.role, profile]);

  if (notFound) return <p className="text-sm text-muted">查無此球員。</p>;
  if (!profile) return <EmptyState>載入中…</EmptyState>;

  const seasonRow = nav.role === "batting" ? season?.batting ?? null : season?.pitching ?? null;
  const ongoingCoach = careerStats?.coach_tenures?.find((t) => t.to == null) ?? null;
  const primaryTeam = (careerStats?.teams ?? []).length
    ? [...(careerStats?.teams ?? [])].sort((a, b) => (b.to - b.from) - (a.to - a.from))[0]
    : null;
  const tc = profile.team ? codeFromName(profile.team)
    : ongoingCoach ? codeFromName(ongoingCoach.team)
    : (primaryTeam?.code ?? null);
  const color = teamColor(tc);
  const hasLevelChoice = !!(profile.farm_batter || profile.farm_pitcher || profile.roster_level === "二軍" || profile.roster_days?.farm);

  return (
    <div style={{ "--hover-color": color } as React.CSSProperties}>
      <PlayerHero profile={profile} careerStats={careerStats} ability={ability} role={nav.role}
        s={seasonRow} scope={nav.scope} />

      <PlayerNavigation nav={nav} roles={roles} hasLevelChoice={hasLevelChoice}
        onScope={(scope) => replaceNav({ scope, view: "overview" })}
        onRole={(role) => replaceNav({ role })}
        onLevel={(level) => replaceNav({ level })}
        onView={(view) => replaceNav({ view })} />

      <div role="tabpanel" aria-label={`${nav.scope === "season" ? "本季" : "生涯"}・${VIEW_LABEL[nav.view]}`}>
        {nav.scope === "season" && nav.view === "overview" && (
          isRetired ? (
            <EmptyState>本季無登錄紀錄（已退役／轉任教練）；可切換「生涯」查看完整表現。</EmptyState>
          ) : (
            <section aria-label="本季總覽" className="mb-6">
              <SeasonSection profile={profile} s={seasonRow} role={nav.role}
                seasonKind={nav.level} advanced={advanced} />
              <TraitsChips id={id} role={nav.role} />
              <div className="mt-5">
                <SeasonTrendCard trend={trend} role={nav.role} isRetired={isRetired} />
              </div>
            </section>
          )
        )}

        {nav.scope === "season" && nav.view === "tracking" && (
          isRetired ? <EmptyState>本季無逐球追蹤資料（未登錄球員名單）。</EmptyState> : (
            <>
              <TrackingSection key={`${id}-${nav.role}-${nav.level}`} disc={disc} role={nav.role} seasonKind={nav.level} />
              <QualitySection advanced={advanced} role={nav.role} />
              {nav.role === "pitching" && <MovementSection mov={mov} />}
              <BattedMixSection pitchMix={pitchMix} arsenal={arsenal} role={nav.role} />
            </>
          )
        )}

        {nav.view === "splits" && (
          <>
            {nav.scope === "season" && (
              <section className="mb-6"><VsTeamCard vsTeam={vsTeam} role={nav.role} /></section>
            )}
            <SplitsSection key={`splits-${id}-${nav.scope}-${nav.role}`} id={id} role={nav.role}
              seasonKind={nav.level} scope={nav.scope} />
            <PlayerMatchupsSection key={`matchups-${id}-${nav.scope}-${nav.role}`} id={id}
              role={nav.role} name={profile.name} scope={nav.scope} />
          </>
        )}

        {nav.view === "fielding" && (
          <FieldingSection fielding={fielding} fieldingCareer={fieldingCareer} fieldFromYear={fieldFromYear}
            league={fieldLeague} qualifyOuts={qualifyOuts} seasonKind={nav.level} scope={nav.scope} />
        )}

        {nav.scope === "career" && nav.view === "overview" && (
          <>
            <CareerSummary careerStats={careerStats} role={nav.role} />
            <section className="mb-6"><CareerTrendCard careerMonthly={careerMonthly} role={nav.role} /></section>
          </>
        )}
        {nav.scope === "career" && nav.view === "yearly" && (
          <CareerYearlySection career={career} role={nav.role} />
        )}
        {nav.scope === "career" && nav.view === "value" && <SabrSection id={id} role={nav.role} />}
      </div>

      <details className="mb-6 rounded-xl border border-line bg-surface">
        <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium text-muted hover:text-ink">
          資料說明與名詞解釋
        </summary>
        <div className="space-y-1.5 border-t border-line px-4 py-3 text-[11px] leading-relaxed text-faint">
          <p>· <span className="text-muted">能力值卡</span>：各軸為多項指標綜合的全聯盟百分位 [PR]（本季 打 AB≥50／投 IP≥20；生涯 AB≥300／IP≥100）。本季納官方進階（初速／強擊球%／Barrel%／揮空率／wOBA，覆蓋稀疏，無則退回傳統指標）；等級 S–G 由 PR 換算，皆客觀自算。滑鼠移到軸名看組成與權重。</p>
          <p>· <span className="text-muted">官方進階 · PR</span>：stats.cpbl 官方 TrackMan 全季值；色條＝PR（藍低→紅高）。打者為進攻、投手為被打數值。</p>
          <p>· <span className="text-muted">生涯／史上排名</span>：一軍例行賽各季合計（近兩季由逐場補）；史上排名以官方歷年累計、近兩季另計。生涯逐年源 cpbl-opendata（不含當季）。</p>
          <p>· <span className="text-muted">逐球追蹤</span>：部分球場未配置設備、涵蓋場次少於全季，與官方進階全季值會有差異。</p>
          <p>· <span className="text-muted">一／二軍</span>：本季主要登錄層級由官網升降事件重建登錄天數判定。主守位＝本季出賽最多的守位或指定打擊（DH 由打擊出賽扣守備推算）。</p>
          <p>· <span className="text-muted">守備指標</span>：每 9 局率以守備局數為分母（局數自 2018 年起重建，更早年度僅顯示累計）；聯盟對照僅納入該守位達 100 局者。外野助殺少不等於臂力差——跑者可能因忌憚傳球而不敢進壘。</p>
          <p>· <span className="text-muted">進階指標（推算）</span>：RE24／wSB／捕手 RA9 以自建 CPBL 得分期望矩陣（逐打席 2018–25，經外部資料交叉驗證）與官方計數推算，非官方數據。RE24 名次為該年 PA≥200／BF≥200 合格者；捕手 RA/9 含非自責分（非 cERA）；跨年代比較受得分環境影響。</p>
        </div>
      </details>
    </div>
  );
}

function PlayerNavigation({ nav, roles, hasLevelChoice, onScope, onRole, onLevel, onView }: {
  nav: { scope: PlayerScope; view: PlayerView; role: Role; level: PlayerLevel };
  roles: Role[];
  hasLevelChoice: boolean;
  onScope: (scope: PlayerScope) => void;
  onRole: (role: Role) => void;
  onLevel: (level: PlayerLevel) => void;
  onView: (view: PlayerView) => void;
}) {
  const [stickyTop, setStickyTop] = useState(0);
  useEffect(() => {
    const header = document.querySelector("header");
    if (!header) return;
    const update = () => setStickyTop(header.getBoundingClientRect().height);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(header);
    return () => ro.disconnect();
  }, []);

  return (
    <nav aria-label="球員資料導覽" style={{ top: stickyTop }}
      className="sticky z-20 -mx-1 mb-6 border-b border-line bg-paper/95 px-1 py-1.5 backdrop-blur">
      <HierarchicalTabs label="資料範圍" groups={PLAYER_TAB_GROUPS}
        activeGroup={nav.scope} activeItem={nav.view} onGroupChange={onScope} onItemChange={onView}
        controls={(roles.length > 1 || (nav.scope === "season" && hasLevelChoice)) ? <>
          {roles.length > 1 && (
            <ContextSwitcher label="身分" values={roles} value={nav.role}
              render={roleLabel} onChange={onRole} />
          )}
          {nav.scope === "season" && hasLevelChoice && (
            <ContextSwitcher label="層級" values={["A", "D"] as const} value={nav.level}
              render={(v) => v === "A" ? "一軍" : "二軍"} onChange={onLevel} />
          )}
        </> : undefined} />
    </nav>
  );
}
