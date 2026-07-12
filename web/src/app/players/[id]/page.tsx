"use client";

// 球員旗艦頁：state 與資料抓取集中於此，區塊 UI 拆在同目錄（hero/season/tracking/trend/fielding/detail）。
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { type PlayerProfile, type StatRow, detail } from "@/lib/client";
import { EmptyState } from "@/components/ui";
import { codeFromName, teamColor } from "@/lib/teams";
import { type Ability, type CareerStats, type Disc, type Role } from "./lib";
import { DetailSection } from "./detail";
import { FieldingSection } from "./fielding";
import { PlayerHero } from "./hero";
import { Tabs } from "./parts";
import { SabrSection } from "./sabr";
import { CareerSummary, SeasonSection, TraitsChips } from "./season";
import { BattedMixSection, MovementSection, type Movement, QualitySection, TrackingSection } from "./tracking";
import { TrendVsSection } from "./trend";

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [role, setRole] = useState<Role>("batting");
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
  const [vsTeam, setVsTeam] = useState<StatRow[] | null>(null);
  const [career, setCareer] = useState<StatRow[] | null>(null);
  const [careerMonthly, setCareerMonthly] = useState<StatRow[] | null>(null);
  const [careerStats, setCareerStats] = useState<CareerStats | null>(null);
  const [ability, setAbility] = useState<Ability | null>(null);
  const [trend, setTrend] = useState<StatRow[] | null>(null);
  // 本季成績層級：二軍選手預設採計二軍(D)、可切換看一軍(A)。
  const [seasonKind, setSeasonKind] = useState<"A" | "D">("A");
  // 版面分頁：數據區（本季/生涯）。
  const [dataTab, setDataTab] = useState<"season" | "career">("season");

  useEffect(() => {
    detail.profile(id).then((d) => {
      if (!d.player) return setNotFound(true);
      setProfile(d.player);
      const p = d.player;
      // role 預設：含本季一軍(is_*)、生涯曾任(was_*)、本季二軍(farm_*) 任一即可。
      const hasBat = p.is_batter || p.was_batter || p.farm_batter;
      const hasPit = p.is_pitcher || p.was_pitcher || p.farm_pitcher;
      setRole(hasBat || !hasPit ? "batting" : "pitching");
      // 退役/教練（本季無登錄層級）數據預設生涯；二軍選手本季成績預設採計二軍。
      if (!p.roster_level) setDataTab("career");
      if (p.roster_level === "二軍") setSeasonKind("D");
    }).catch(() => setNotFound(true));
    detail.fielding(id, "career").then((d) => { setFieldingCareer(d.items); setFieldFromYear(d.from_year ?? null); })
      .catch(() => setFieldingCareer([]));
    detail.careerStats(id).then(setCareerStats).catch(() => setCareerStats(null));
    detail.abilityCard(id).then(setAbility).catch(() => setAbility(null));
  }, [id]);

  useEffect(() => {
    detail.season(id, seasonKind).then(setSeason).catch(() => setSeason(null));
  }, [id, seasonKind]);

  useEffect(() => {
    setTrend(null);
    setVsTeam(null);
    setCareer(null);
    detail.trend(id, role).then((d) => setTrend(d.items)).catch(() => setTrend([]));
    detail.vsTeam(id, role).then((d) => setVsTeam(d.items)).catch(() => setVsTeam([]));
    detail.career(id, role).then((d) => setCareer(d.seasons)).catch(() => setCareer([]));
  }, [id, role]);

  // 生涯時段分項：固定以「週」跨年合併
  useEffect(() => {
    setCareerMonthly(null);
    detail.trendCareer(id, role, "week").then((d) => setCareerMonthly(d.items)).catch(() => setCareerMonthly([]));
  }, [id, role]);

  // 逐球追蹤（好球帶紀律 + 配球傾向）+ 當季守備隨一/二軍鏡頭切換：二軍有獨立樣本
  useEffect(() => {
    setDisc(null);
    setPitchMix(null);
    setArsenal(null);
    detail.discipline(id, role, seasonKind).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
    detail.pitchMix(id, role, seasonKind).then((d) => setPitchMix(d.items)).catch(() => setPitchMix([]));
    // 球種卡（arsenal 端點僅一軍樣本）
    if (seasonKind === "A") detail.arsenal(id, role).then((d) => setArsenal(d.items)).catch(() => setArsenal([]));
    else setArsenal([]);
    // 球種位移（ML-PT2 Phase1；僅投手視角）
    if (role === "pitching") detail.movement(id, seasonKind).then(setMov).catch(() => setMov(null));
    else setMov(null);
    detail.fielding(id, "season", seasonKind).then((d) => setFielding(d.items)).catch(() => setFielding([]));
    detail.advanced(id, seasonKind).then(setAdvanced).catch(() => setAdvanced(null));
  }, [id, role, seasonKind]);

  if (notFound) return <p className="text-sm text-muted">查無此球員。</p>;
  if (!profile) return <EmptyState>載入中…</EmptyState>;

  // 退役/教練：本季完全無登錄層級(roster_level=null) → 本季數值與官方進階必空，整段隱藏。
  // 二軍-only 球員有 roster_level（二軍）故不算退役。
  const isRetired = !profile.roster_level;
  // role tab：含本季一軍(is_*)、生涯曾任(was_*)、本季二軍(farm_*) 任一即列。
  const roles: { v: Role; label: string }[] = [];
  if (profile.is_batter || profile.was_batter || profile.farm_batter) roles.push({ v: "batting", label: "打擊" });
  if (profile.is_pitcher || profile.was_pitcher || profile.farm_pitcher) roles.push({ v: "pitching", label: "投球" });
  const s = season ? (role === "batting" ? season.batting : season.pitching) : null;
  // 生涯資料是否存在（打者或投手任一）→ 控制「生涯」分頁顯示
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

      {roles.length > 1 && <div className="mb-5"><Tabs opts={roles} v={role} set={setRole} /></div>}

      {dataTab === "season" && !isRetired && (
        <>
          <SeasonSection profile={profile} s={s} role={role}
            seasonKind={seasonKind} setSeasonKind={setSeasonKind} advanced={advanced} />
          <TraitsChips id={id} role={role} />
        </>
      )}
      {dataTab === "career" && <CareerSummary careerStats={careerStats} role={role} />}

      {/* key 重掛：id/role/seasonKind 變更時重置球種鏡頭（沿用原重置語義） */}
      <TrackingSection key={`${id}-${role}-${seasonKind}`} disc={disc} role={role} seasonKind={seasonKind} />
      <QualitySection advanced={advanced} role={role} />
      {role === "pitching" && <MovementSection mov={mov} />}
      <BattedMixSection disc={disc} pitchMix={pitchMix} arsenal={arsenal} role={role} />
      <TrendVsSection trend={trend} careerMonthly={careerMonthly} vsTeam={vsTeam} role={role} />
      <SabrSection id={id} role={role} />
      <FieldingSection fielding={fielding} fieldingCareer={fieldingCareer} fieldFromYear={fieldFromYear} />
      <DetailSection id={id} role={role} seasonKind={seasonKind} isRetired={isRetired} career={career} />

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
