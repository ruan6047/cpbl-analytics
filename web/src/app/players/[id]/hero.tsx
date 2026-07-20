"use client";

// Hero 區：身分徽章 + 生涯效力/教練/旅外 + 得獎 + 能力雷達側欄（本季/生涯切換）。
import { AbilityCard, GradeChip } from "@/components/ability-card";
import { LetterBadge, TeamLogo } from "@/components/ui";
import { type PlayerProfile, type StatRow } from "@/lib/client";
import { fmtIP } from "@/lib/format";
import { codeFromName, contrastText, eraBadge, teamColor } from "@/lib/teams";
import { MEDAL_COLORS, STATUS_COLORS } from "@/lib/chart-theme";
import { type Ability, type CareerStats, type Role, IMPORT_BADGE, f3, numOf } from "./lib";
import { Tabs, TenureChips } from "./parts";

// 能力值卡選取：尺度由能力卡自己的 dataTab（本季/生涯）決定——IA 分層後它只作用於能力卡，
// 不再連動下方區塊顯隱；role 卡缺則退回另一 role
export function selectAbility(ability: Ability | null, role: Role, dataTab: "season" | "career") {
  const sa = (sc: "season" | "career") => !!(ability?.batting?.[sc]?.available || ability?.pitching?.[sc]?.available);
  if (!sa("season") && !sa("career")) return null;
  const eff = sa(dataTab) ? dataTab : sa("season") ? "season" : "career";
  const card = ability?.[role]?.[eff]?.available ? ability[role][eff]
    : ability?.batting?.[eff]?.available ? ability.batting[eff] : ability?.pitching?.[eff];
  if (!card?.available) return null;
  return { eff, card };
}

export function PlayerHero({ profile, careerStats, ability, role, s, isRetired, hasCareer, dataTab, setDataTab }: {
  profile: PlayerProfile;
  careerStats: CareerStats | null;
  ability: Ability | null;
  role: Role;
  s: StatRow | null;
  isRetired: boolean;
  hasCareer: boolean;
  dataTab: "season" | "career";
  setDataTab: (v: "season" | "career") => void;
}) {
  // hero 隊伍：本季球員登錄隊 > 進行中執教隊（教練 tenure 未結束）> 生涯主隊（年資最長）
  const ongoingCoach = careerStats?.coach_tenures?.find((t) => t.to == null) ?? null;
  const primaryTeam = (careerStats?.teams ?? []).length
    ? [...(careerStats?.teams ?? [])].sort((a, b) => (b.to - b.from) - (a.to - a.from))[0]
    : null;
  const heroName = profile.team ?? ongoingCoach?.team ?? primaryTeam?.name ?? null;
  const tc = profile.team ? codeFromName(profile.team)
    : ongoingCoach ? codeFromName(ongoingCoach.team)
    : (primaryTeam?.code ?? null);
  const abSel = selectAbility(ability, role, dataTab);

  const hasPlayerRole = hasCareer || !!profile.roster_level;
  const hasCoachRole = (careerStats?.official_coach_tenures && careerStats.official_coach_tenures.length > 0) || (careerStats?.coach_tenures && careerStats.coach_tenures.length > 0);
  const hasManagerRole = (careerStats?.manager_stats && careerStats.manager_stats.length > 0) ||
    careerStats?.official_coach_tenures?.some((t) => t.pos.includes("總教練") || t.pos.includes("監督")) ||
    careerStats?.coach_tenures?.some((t) => t.role?.includes("總教練") || t.role?.includes("監督"));

  return (
      <div className="card mb-6 overflow-hidden">
        <div className="h-1.5" style={{ background: teamColor(tc) }} />
        <div className="p-5">
        <div className="grid items-stretch gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          {/* 左欄：身分資訊（置頂）＋得獎（置底） */}
          <div className="flex min-w-0 flex-col">
          <div className="min-w-0">
            <div className="flex items-start gap-3.5">
              <TeamLogo code={tc} size={48} />
              <div className="min-w-0 flex-1">
              {/* 名字＋徽章列（左）／本季數值（區塊右上角；窄螢幕掉到名字下方避免擠壓） */}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-2xl font-extrabold tracking-tight text-ink">{profile.name}</h1>
                    {hasPlayerRole && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink">球員</span>
                    )}
                    {hasCoachRole && (
                      <span className="rounded-md bg-muted/15 px-2 py-0.5 text-[11px] font-semibold leading-none text-muted">教練</span>
                    )}
                    {hasManagerRole && (
                      <span className="rounded-md bg-accent/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-accent">總教練</span>
                    )}
                    {profile.import_status && profile.import_status !== "local" && (
                      <span
                        className="rounded-md px-2 py-0.5 text-[11px] font-semibold leading-none"
                        style={{
                          background: `${STATUS_COLORS[profile.import_status]}1a`,
                          color: STATUS_COLORS[profile.import_status],
                        }}
                        title={`${IMPORT_BADGE[profile.import_status].hint}${profile.country ? `（國籍：${profile.country}）` : ""}`}>
                        {profile.import_label}
                      </span>
                    )}
                    {profile.roster_level && (
                      <span
                        className="rounded-md px-2 py-0.5 text-[11px] font-semibold leading-none"
                        style={profile.roster_level === "一軍"
                          ? { background: "color-mix(in srgb, var(--color-cpbl) 12%, transparent)", color: "var(--color-cpbl)" }
                          : { background: "color-mix(in srgb, var(--color-amber) 15%, transparent)", color: "var(--color-amber)" }}
                        title={`目前登錄層級（依最後一次升降事件判定）${profile.roster_days
                          ? `：本季累計 一軍 ${profile.roster_days.first} 天 · 二軍 ${profile.roster_days.farm} 天` : ""}`}>
                        {profile.roster_level}選手
                      </span>
                    )}
                    {abSel?.card.signature && (
                      <span className="rounded-md bg-accent/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-accent"
                        title={role === "pitching"
                          ? "投球風格：最突出的出局方式（三振／滾地／飛球）"
                          : "打擊特色：進攻工具中最突出者（多項頂尖＝全能）"}>
                        {abSel.card.signature}型
                      </span>
                    )}
                    {profile.pitcher_role && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink"
                        title="投手類型：先發＝先發場數佔半數以上；後援＝救援>中繼（終結者傾向）；中繼＝其餘後援投手">
                        {profile.pitcher_role}
                      </span>
                    )}
                    {profile.primary_position && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink"
                        title="主守位：本季出賽最多的守位或指定打擊（DH 由打擊出賽扣守備推算；本季無資料則取生涯守備）">
                        {profile.primary_position}
                      </span>
                    )}
                    {profile.bats && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink" title="打擊慣用手">
                        {profile.bats}
                      </span>
                    )}
                    {profile.throws && (
                      <span className="rounded-md bg-ink/10 px-2 py-0.5 text-[11px] font-semibold leading-none text-ink" title="投球慣用手">
                        {profile.throws}
                      </span>
                    )}
                  </div>
                  {profile.former_names?.length > 0 && (
                    <p className="mt-0.5 text-[11px] text-faint">曾用名：{profile.former_names.join("、")}</p>
                  )}
                  {(() => {
                    const bio: string[] = [];
                    if (profile.height_cm && profile.weight_kg)
                      bio.push(`${profile.height_cm} cm / ${profile.weight_kg} kg`);
                    if (profile.birthday) {
                      const b = new Date(profile.birthday);
                      const age = Math.floor((Date.now() - b.getTime()) / 31557600000);
                      bio.push(`${profile.birthday}（${age} 歲）`);
                    }
                    if (profile.debut) bio.push(`初登場 ${profile.debut}`);
                    if (profile.birthplace && profile.birthplace !== "中華民國")
                      bio.push(`國籍 ${profile.birthplace}`);
                    if (profile.education) bio.push(profile.education);
                    if (profile.draft) bio.push(profile.draft);
                    return bio.length > 0 ? (
                      <p className="mt-1 text-xs text-muted">{bio.join(" · ")}</p>
                    ) : null;
                  })()}
                </div>
                {/* 本季數值：區塊右上角 */}
                {s && role === "batting" && (
                  <div className="shrink-0 font-mono leading-tight text-ink sm:text-right">
                    <div className="text-2xl font-semibold tabular-nums">{f3(s.avg)}/{f3(s.obp)}/{f3(s.slg)}</div>
                    <div className="text-base font-semibold tabular-nums text-accent">OPS {f3(s.ops)}</div>
                  </div>
                )}
                {s && role === "pitching" && (
                  <div className="shrink-0 font-mono leading-tight text-ink sm:text-right">
                    <div className="text-2xl font-semibold tabular-nums">{numOf(s.era)?.toFixed(2) ?? "—"} ERA</div>
                    <div className="text-base tabular-nums text-muted">{s.w ?? 0}-{s.l ?? 0} · {fmtIP(s.ip as number | string | null)} 局</div>
                  </div>
                )}
              </div>
              <div className="my-3 border-t border-line" />
              {(!careerStats?.teams || careerStats.teams.length === 0) && heroName && (
                <p className="text-sm text-muted">
                  {heroName}{!profile.team && ongoingCoach && <span className="ml-1 text-faint">（教練）</span>}
                </p>
              )}
              {careerStats?.teams && careerStats.teams.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {careerStats.teams.map((t) => {
                    const b = eraBadge(t.name, t.code);
                    return (
                      <span key={`${t.code}-${t.from}`}
                        className="inline-flex items-center gap-1 rounded-full py-0.5 pl-0.5 pr-2 text-[11px] font-medium"
                        style={{ background: `${b.color}1a`, color: b.color }}
                        title={`${t.name}　${t.from === t.to ? t.from : `${t.from}–${t.to}`}`}>
                        <LetterBadge meta={b} round />
                        {t.name}
                        <span className="font-mono tabular-nums opacity-70">
                          {t.from === t.to ? `'${String(t.from).slice(2)}` : `'${String(t.from).slice(2)}–'${String(t.to).slice(2)}`}
                        </span>
                      </span>
                    );
                  })}
                </div>
              )}
              {careerStats?.coach_tenures && careerStats.coach_tenures.length > 0 && (
                <TenureChips label="教練" tenures={careerStats.coach_tenures} />
              )}
              {careerStats?.exec_tenures && careerStats.exec_tenures.length > 0 && (
                <TenureChips label="行政" tenures={careerStats.exec_tenures} />
              )}
              {careerStats?.overseas && careerStats.overseas.length > 0 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="text-faint">旅外</span>
                  {careerStats.overseas.map((o) => (
                    <span key={`${o.league}-${o.year}`}
                      className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-muted"
                      title={`${o.league}${o.team ? ` · ${o.team}` : ""} · ${o.year} 加盟`}>
                      ✈ {o.league}{o.team ? ` · ${o.team}` : ""}
                      <span className="font-mono opacity-70">'{String(o.year).slice(2)}</span>
                    </span>
                  ))}
                </div>
              )}
              </div>
            </div>
          </div>
          {/* 得獎/國際賽：置於左欄底部（mt-auto 推到最下） */}
          {((careerStats?.awards?.length ?? 0) > 0 || (careerStats?.medals?.length ?? 0) > 0 || (careerStats?.wiki_awards?.length ?? 0) > 0 || !!careerStats?.championships) && (
            <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
              {careerStats?.championships && (
                <span title={`總冠軍年份：${careerStats.championships.years.join("、")}`}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold"
                  style={{ background: `color-mix(in srgb, ${MEDAL_COLORS.金} 14%, transparent)`, color: "var(--color-amber)", border: `1px solid color-mix(in srgb, ${MEDAL_COLORS.金} 34%, transparent)` }}>
                  <span>🏆 總冠軍</span>
                  <span className="rounded px-1 text-[10px] font-bold" style={{ background: MEDAL_COLORS.金, color: contrastText(MEDAL_COLORS.金) }}>×{careerStats.championships.count}</span>
                </span>
              )}
              {(() => {
                const grp = new Map<string, { label: string; years: number[] }>();
                for (const a of careerStats?.awards ?? []) {
                  const posCat = a.category === "金手套" || a.category === "最佳十人";
                  const label = posCat ? `${a.category}(${a.award})` : a.award;
                  const g = grp.get(label) ?? { label, years: [] };
                  g.years.push(a.year);
                  grp.set(label, g);
                }
                const groups = [...grp.values()].sort((x, y) => y.years.length - x.years.length || y.years[0] - x.years[0]);
                const MC = MEDAL_COLORS;
                return (
                  <>
                    {groups.map((g) => (
                      <span key={g.label} title={[...new Set(g.years)].sort((a, b) => a - b).map((y) => `'${String(y).slice(2)}`).join(" ")}
                        className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-xs">
                        <span className="font-medium text-ink">🏆 {g.label}</span>
                        {g.years.length > 1 && <span className="rounded bg-accent/10 px-1 text-[10px] font-bold text-accent">×{g.years.length}</span>}
                      </span>
                    ))}
                    {(careerStats?.medals ?? []).map((m, i) => (
                      <span key={`${m.competition}-${m.year}-${i}`} title={m.year ? `'${String(m.year).slice(2)}` : undefined}
                        className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-xs">
                        <span className="grid h-4 w-4 place-items-center rounded-full text-[10px] font-bold text-white" style={{ background: MC[m.color] ?? "var(--color-faint)" }}>{m.color}</span>
                        <span className="font-medium text-ink">{m.competition}</span>
                      </span>
                    ))}
                    {/* 維基補充：舊聯盟（台灣大聯盟/台灣大賽）與國際/日韓職獎項——官網獎項表沒有 */}
                    {(careerStats?.wiki_awards ?? []).map((w) => (
                      <span key={w.award}
                        title={`${w.years.map((y) => `'${String(y).slice(2)}`).join(" ")}${w.note ? `（${w.note}）` : ""}　資料：維基百科`}
                        className="inline-flex items-center gap-1 rounded-md border border-dashed border-line bg-surface px-2 py-1 text-xs">
                        <span className="font-medium text-muted">🏅 {w.award}</span>
                        {w.years.length > 1 && <span className="rounded bg-line/60 px-1 text-[10px] font-bold text-muted">×{w.years.length}</span>}
                      </span>
                    ))}
                  </>
                );
              })()}
            </div>
          )}
          </div>
          {/* 右欄：能力值雷達 ＋ 本季/生涯（雷達正下方右側、往上收） */}
          {abSel && (
            <div className="flex items-center gap-2 lg:border-l lg:border-line lg:pl-5">
              <div className="min-w-0 flex-1">
                <AbilityCard card={abSel.card} color={teamColor(tc)} hideNote />
              </div>
              {/* 雷達右側：總評＋本季/生涯（直排），用側欄消化雷達下方空白 */}
              <div className="flex w-16 shrink-0 flex-col items-center justify-center gap-3">
                {abSel.card.overall && (
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-[10px] text-muted">總評</span>
                    <GradeChip grade={abSel.card.overall.grade} size="lg" />
                  </div>
                )}
                {(!isRetired || hasCareer) && (
                  <Tabs vertical opts={[
                    ...(!isRetired ? [{ v: "season" as const, label: "本季" }] : []),
                    ...(hasCareer ? [{ v: "career" as const, label: "生涯" }] : []),
                  ]} v={dataTab} set={setDataTab} />
                )}
              </div>
            </div>
          )}
        </div>
        </div>
      </div>
  );
}
