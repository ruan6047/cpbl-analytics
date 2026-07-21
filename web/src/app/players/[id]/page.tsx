"use client";

// 球員旗艦頁：IA2 修訂版——Hero 與總覽常駐；role 不再是切換鈕，而是攤成標籤頁
// （雙棲球員同時有「打擊」與「投球」兩個內容頁）。守備自生涯層移出成獨立層。
// 總覽／分項與對戰／生涯在雙棲時把兩種身分上下堆疊，全頁不存在隱性 role 狀態。
// state 與資料抓取集中於此；層與資料需求的判斷集中在 layers.ts。
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { type PlayerProfile, type StatRow, detail } from "@/lib/client";
import { EmptyState } from "@/components/ui";
import { codeFromName, teamColor } from "@/lib/teams";
import { type Ability, type CareerStats, type Disc, type Role } from "./lib";
import {
  type SubLayer, createLoadTracker, layerRole, layersFor, loadGroup, needsData, needsRoleHeading,
  primaryRole, roleLabel, stackedRoles, subLayerFromParams, subLayerLabel,
} from "./layers";
import { CareerYearlySection, SplitsSection } from "./detail";
import { type FieldLeague, FieldingSection } from "./fielding";
import { PlayerMatchupsSection } from "./matchups-section";
import { PlayerHero } from "./hero";
import { SabrSection } from "./sabr";
import { CareerSummary, SeasonSection, TraitsChips } from "./season";
import { BattedMixSection, MovementSection, type Movement, QualitySection, TrackingSection } from "./tracking";
import { CareerTrendCard, SeasonTrendCard, VsTeamCard } from "./trend";

/** 堆疊層的 per-role 狀態：雙棲時兩種身分同時呈現，故不能只存一份。 */
type ByRole<T> = Partial<Record<Role, T | null>>;

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
  // 以下四項在堆疊層需要同時持有兩種身分
  const [vsTeam, setVsTeam] = useState<ByRole<StatRow[]>>({});
  const [career, setCareer] = useState<ByRole<StatRow[]>>({});
  const [careerMonthly, setCareerMonthly] = useState<ByRole<StatRow[]>>({});
  const [trend, setTrend] = useState<ByRole<StatRow[]>>({});
  const [careerStats, setCareerStats] = useState<CareerStats | null>(null);
  const [ability, setAbility] = useState<Ability | null>(null);
  // 本季成績層級：二軍選手預設採計二軍(D)、可切換看一軍(A)。
  const [seasonKind, setSeasonKind] = useState<"A" | "D">("A");
  // 能力值卡尺度（本季/生涯）；只影響 Hero 的能力卡。
  const [dataTab, setDataTab] = useState<"season" | "career">("season");

  useEffect(() => {
    detail.profile(id).then((d) => {
      if (!d.player) return setNotFound(true);
      setProfile(d.player);
      const p = d.player;
      if (!p.roster_level) setDataTab("career");
      if (p.roster_level === "二軍") setSeasonKind("D");
    }).catch(() => setNotFound(true));
    detail.careerStats(id).then(setCareerStats).catch(() => setCareerStats(null));
    detail.abilityCard(id).then(setAbility).catch(() => setAbility(null));
  }, [id]);

  // ---- 導覽狀態（URL 為單一事實來源，無隱性 role state）----
  // 身分判定：含本季一軍(is_*)、生涯曾任(was_*)、本季二軍(farm_*) 任一即列。
  const roles: Role[] = [];
  if (profile?.is_batter || profile?.was_batter || profile?.farm_batter) roles.push("batting");
  if (profile?.is_pitcher || profile?.was_pitcher || profile?.farm_pitcher) roles.push("pitching");
  // 退役/教練：本季完全無登錄層級 → 本季模組必空，預設層落生涯。
  const isRetired = !!profile && !profile.roster_level;
  const sec = subLayerFromParams(params.get("sec"), params.get("role"), roles, isRetired);
  const layers = layersFor(roles);
  const stacked = stackedRoles(roles);
  const showRoleHeading = needsRoleHeading(roles);
  // 身分內容頁用該頁的 role；其餘層（Hero 能力卡）用主身分。
  const heroRole = layerRole(sec) ?? primaryRole(roles);

  const setSec = (value: SubLayer) => {
    const next = new URLSearchParams(params.toString());
    next.set("sec", value);
    // 舊 ?role= 已由 sec 取代其導覽職責，切層時清掉以免兩者不一致。
    next.delete("role");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  // ---- 依層載入：常駐群組恆抓，層專屬群組只在進入該層時抓一次（key 變才重抓）----
  const tracker = useRef(createLoadTracker());
  const once = (group: string, key: string, run: () => void) => {
    if (tracker.current(group, key)) run();
  };
  // 四個堆疊層狀態都是 StatRow[]，特化掉泛型以免傳 null 時 T 被推成 never。
  const setByRole = (
    set: React.Dispatch<React.SetStateAction<ByRole<StatRow[]>>>, r: Role, v: StatRow[] | null,
  ) => set((prev) => ({ ...prev, [r]: v }));

  const stackedKey = stacked.join(",");

  // 常駐（Hero＋總覽）：本季成績、官方進階、賽季走勢。走勢在雙棲時兩身分都要。
  useEffect(() => {
    once(loadGroup("season"), `${id}-${seasonKind}`, () => {
      setSeason(null);
      detail.season(id, seasonKind).then(setSeason).catch(() => setSeason(null));
    });
    once(loadGroup("advanced"), `${id}-${seasonKind}`, () => {
      setAdvanced(null);
      detail.advanced(id, seasonKind).then(setAdvanced).catch(() => setAdvanced(null));
    });
    // profile 未載入時 roles 為空，stacked 會誤判為主身分預設值 → 等 profile 就緒再抓
    if (!profile) return;
    for (const r of stacked) {
      once(loadGroup("trend", r), `${id}-${r}`, () => {
        setByRole(setTrend, r, null);
        detail.trend(id, r).then((d) => setByRole(setTrend, r, d.items))
          .catch(() => setByRole(setTrend, r, []));
      });
    }
  }, [id, seasonKind, stackedKey, profile]);

  // 身分內容頁（打擊／投球）：逐球追蹤、配球傾向、球種卡、球種位移（僅投球頁）
  useEffect(() => {
    if (!profile) return;
    const pageRole = layerRole(sec);
    if (!pageRole || !needsData("tracking", sec)) return;
    once(loadGroup("tracking", pageRole), `${id}-${pageRole}-${seasonKind}`, () => {
      setDisc(null);
      setPitchMix(null);
      setArsenal(null);
      detail.discipline(id, pageRole, seasonKind).then((d) => setDisc(d as Disc)).catch(() => setDisc(null));
      detail.pitchMix(id, pageRole, seasonKind).then((d) => setPitchMix(d.items)).catch(() => setPitchMix([]));
      // 球種卡（arsenal 端點僅一軍樣本）
      if (seasonKind === "A") detail.arsenal(id, pageRole).then((d) => setArsenal(d.items)).catch(() => setArsenal([]));
      else setArsenal([]);
    });
    if (pageRole !== "pitching") return;
    once(loadGroup("movement"), `${id}-${seasonKind}`, () => {
      setMov(null);
      detail.movement(id, seasonKind).then(setMov).catch(() => setMov(null));
    });
  }, [id, seasonKind, sec, profile]);

  // 分項與對戰：對戰各隊、生涯時段分項（分項明細由 SplitsSection 自抓）；雙棲時兩身分都要
  useEffect(() => {
    // profile 未載入時 sec 會因 roles 為空而回退到別層，先抓等於抓錯層的資料
    if (!profile || !needsData("splits", sec)) return;
    for (const r of stacked) {
      once(loadGroup("splits", r), `${id}-${r}`, () => {
        setByRole(setVsTeam, r, null);
        detail.vsTeam(id, r).then((d) => setByRole(setVsTeam, r, d.items))
          .catch(() => setByRole(setVsTeam, r, []));
      });
      once(loadGroup("splits", r) + ":monthly", `${id}-${r}`, () => {
        setByRole(setCareerMonthly, r, null);
        detail.trendCareer(id, r, "week").then((d) => setByRole(setCareerMonthly, r, d.items))
          .catch(() => setByRole(setCareerMonthly, r, []));
      });
    }
  }, [id, sec, stackedKey, profile]);

  // 守備（獨立層）：與 role 無關，只隨一/二軍鏡頭
  useEffect(() => {
    if (!profile || !needsData("fielding", sec)) return;
    once(loadGroup("fielding") + ":career", id, () => {
      detail.fielding(id, "career").then((d) => { setFieldingCareer(d.items); setFieldFromYear(d.from_year ?? null); })
        .catch(() => setFieldingCareer([]));
    });
    once(loadGroup("fielding"), `${id}-${seasonKind}`, () => {
      setFielding(null);
      detail.fielding(id, "season", seasonKind).then((d) => {
        setFielding(d.items);
        setFieldLeague(d.league);
        setQualifyOuts(d.qualify_outs);
      }).catch(() => setFielding([]));
    });
  }, [id, seasonKind, sec, profile]);

  // 生涯：逐年（雙棲時兩身分都要）
  useEffect(() => {
    if (!profile || !needsData("career", sec)) return;
    for (const r of stacked) {
      once(loadGroup("career", r), `${id}-${r}`, () => {
        setByRole(setCareer, r, null);
        detail.career(id, r).then((d) => setByRole(setCareer, r, d.seasons))
          .catch(() => setByRole(setCareer, r, []));
      });
    }
  }, [id, sec, stackedKey, profile]);

  if (notFound) return <p className="text-sm text-muted">查無此球員。</p>;
  if (!profile) return <EmptyState>載入中…</EmptyState>;

  const seasonRow = (r: Role) => (season ? (r === "batting" ? season.batting : season.pitching) : null);
  const hasCareer = !!(careerStats?.batting || careerStats?.pitching);

  // 計算球員隊色作為 hover 光暈顏色
  const ongoingCoach = careerStats?.coach_tenures?.find((t) => t.to == null) ?? null;
  const primaryTeam = (careerStats?.teams ?? []).length
    ? [...(careerStats?.teams ?? [])].sort((a, b) => (b.to - b.from) - (a.to - a.from))[0]
    : null;
  const tc = profile.team ? codeFromName(profile.team)
    : ongoingCoach ? codeFromName(ongoingCoach.team)
    : (primaryTeam?.code ?? null);
  const color = teamColor(tc);

  return (
    <div style={{ "--hover-color": color } as React.CSSProperties}>
      <PlayerHero profile={profile} careerStats={careerStats} ability={ability} role={heroRole}
        s={seasonRow(heroRole)} isRetired={isRetired} hasCareer={hasCareer}
        dataTab={dataTab} setDataTab={setDataTab} />

      {/* ---- 總覽（常駐）：現在如何。雙棲時兩身分上下堆疊 ---- */}
      <section aria-label="總覽" className="mb-6">
        {isRetired ? (
          <div className="mb-5 rounded-xl border border-line bg-surface p-4 text-sm text-muted">
            本季無登錄紀錄（已退役／轉任教練），本季成績與逐球追蹤皆無資料；生涯表現請見「生涯」。
          </div>
        ) : (
          stacked.map((r) => (
            <RoleBlock key={r} role={r} heading={showRoleHeading}>
              <SeasonSection profile={profile} s={seasonRow(r)} role={r}
                seasonKind={seasonKind} setSeasonKind={setSeasonKind} advanced={advanced} />
              <TraitsChips id={id} role={r} />
            </RoleBlock>
          ))
        )}
        {stacked.map((r) => (
          <div key={r} className="mb-2">
            <SeasonTrendCard trend={trend[r] ?? null} role={r} isRetired={isRetired} />
          </div>
        ))}
      </section>

      {/* ---- 分層導覽（?sec=）---- */}
      <SubNav sec={sec} layers={layers} setSec={setSec} />

      <div role="tabpanel" aria-label={subLayerLabel(sec)}>
        {layerRole(sec) && (() => {
          const r = layerRole(sec)!;
          return (
            <>
              {/* key 重掛：id/role/seasonKind 變更時重置球種鏡頭（沿用原重置語義） */}
              <TrackingSection key={`${id}-${r}-${seasonKind}`} disc={disc} role={r} seasonKind={seasonKind} />
              <QualitySection advanced={advanced} role={r} />
              {r === "pitching" && <MovementSection mov={mov} />}
              <BattedMixSection disc={disc} pitchMix={pitchMix} arsenal={arsenal} role={r} />
            </>
          );
        })()}

        {sec === "splits" && stacked.map((r) => (
          <RoleBlock key={r} role={r} heading={showRoleHeading}>
            <section className="mb-6">
              <div className="grid items-stretch gap-6 lg:grid-cols-2">
                <CareerTrendCard careerMonthly={careerMonthly[r] ?? null} role={r} />
                <VsTeamCard vsTeam={vsTeam[r] ?? null} role={r} />
              </div>
            </section>
            <SplitsSection id={id} role={r} seasonKind={seasonKind} isRetired={isRetired} />
            <PlayerMatchupsSection id={id} role={r} name={profile.name} isRetired={isRetired} />
          </RoleBlock>
        ))}

        {sec === "fielding" && (
          <FieldingSection fielding={fielding} fieldingCareer={fieldingCareer} fieldFromYear={fieldFromYear}
            league={fieldLeague} qualifyOuts={qualifyOuts} seasonKind={seasonKind} />
        )}

        {sec === "career" && stacked.map((r) => (
          <RoleBlock key={r} role={r} heading={showRoleHeading}>
            <CareerSummary careerStats={careerStats} role={r} />
            <CareerYearlySection career={career[r] ?? null} role={r} />
            <SabrSection id={id} role={r} />
          </RoleBlock>
        ))}
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
          <p>· <span className="text-muted">守備指標</span>：每 9 局率以守備局數為分母（局數自 2018 年起重建，更早年度僅顯示累計）；聯盟對照僅納入該守位達 100 局者。外野助殺少不等於臂力差——跑者可能因忌憚傳球而不敢進壘。</p>
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

/** 堆疊層的身分區塊：只有雙棲時才加身分小標，單一身分加標題是雜訊。 */
function RoleBlock({ role, heading, children }: {
  role: Role; heading: boolean; children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      {heading && (
        <h3 className="mb-2 border-l-4 border-accent pl-2 text-base font-semibold text-ink">
          {roleLabel(role)}
        </h3>
      )}
      {children}
    </div>
  );
}

/** 分層 sticky 導覽（WAI-ARIA tabs：←/→ 移動並切換）。 */
function SubNav({ sec, layers, setSec }: {
  sec: SubLayer; layers: SubLayer[]; setSec: (l: SubLayer) => void;
}) {
  const idx = Math.max(0, layers.indexOf(sec));
  // 站台 header 也是 sticky top-0 且 z-40，本列若同樣 top-0 會被整個蓋住、捲動後點不到
  // （IA1 prototype 沒有 header，`top-0` 在那裡是對的，搬進正式頁後沒重新檢查）。
  // header 高度隨斷點與內容變動（實測 375px 為 73、1280px 為 63），故執行期量測而非寫死。
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
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  // 只有使用者用鍵盤操作過 tablist 才把焦點跟著移動；deep-link 直開不搶焦點。
  const keyboardMoved = useRef(false);
  const onKey = (e: React.KeyboardEvent) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    keyboardMoved.current = true;
    setSec(layers[(idx + delta + layers.length) % layers.length]);
  };
  useEffect(() => {
    if (!keyboardMoved.current) return;
    refs.current[idx]?.focus({ preventScroll: true });
  }, [idx]);
  return (
    <div role="tablist" aria-label="球員資料分層" onKeyDown={onKey} style={{ top: stickyTop }}
      className="sticky z-20 -mx-1 mb-4 flex gap-1 overflow-x-auto border-b border-line bg-paper px-1 py-2">
      {layers.map((l, i) => (
        <button key={l} role="tab" aria-selected={sec === l} tabIndex={sec === l ? 0 : -1}
          ref={(el) => { refs.current[i] = el; }}
          onClick={() => setSec(l)}
          className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition ${
            sec === l ? "bg-ink font-medium text-paper" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
          {subLayerLabel(l)}
        </button>
      ))}
    </div>
  );
}
