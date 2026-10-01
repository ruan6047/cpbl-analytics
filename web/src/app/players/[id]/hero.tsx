"use client";

// Hero 區：身分徽章 + 生涯效力/教練/旅外 + 得獎 + 能力雷達。
import { AbilityCard } from "@/components/ability-card";
import { LetterBadge, TeamLogo } from "@/components/ui";
import { Serial } from "@/components/postmark";
import { type PlayerProfile, type StatRow } from "@/lib/client";
import { fmtIP } from "@/lib/format";
import { codeFromName, eraBadge, markCodeOf } from "@/lib/teams";
import { STATUS_COLORS } from "@/lib/chart-theme";
import { type Ability, type CareerStats, type Role, IMPORT_BADGE, f3, numOf } from "./lib";
import type { PlayerScope } from "./layers";
import { TenureChips } from "./parts";

// 能力值卡跟隨全域 scope；該 scope 缺卡時退回可用尺度，role 缺卡再退回另一 role。
export function selectAbility(ability: Ability | null, role: Role, dataTab: PlayerScope) {
  const sa = (sc: "season" | "career") => !!(ability?.batting?.[sc]?.available || ability?.pitching?.[sc]?.available);
  if (!sa("season") && !sa("career")) return null;
  const eff = sa(dataTab) ? dataTab : sa("season") ? "season" : "career";
  const card = ability?.[role]?.[eff]?.available ? ability[role][eff]
    : ability?.batting?.[eff]?.available ? ability.batting[eff] : ability?.pitching?.[eff];
  if (!card?.available) return null;
  return { eff, card };
}

export function PlayerHero({ profile, careerStats, ability, role, s, scope }: {
  profile: PlayerProfile;
  careerStats: CareerStats | null;
  ability: Ability | null;
  role: Role;
  s: StatRow | null;
  scope: PlayerScope;
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
  const abSel = selectAbility(ability, role, scope);
  const headline = (scope === "season" ? s
    : role === "batting" ? careerStats?.batting : careerStats?.pitching) as StatRow | null | undefined;
  const hasCareer = !!(careerStats?.batting || careerStats?.pitching);

  const hasPlayerRole = hasCareer || !!profile.roster_level;
  const hasCoachRole = (careerStats?.official_coach_tenures && careerStats.official_coach_tenures.length > 0) || (careerStats?.coach_tenures && careerStats.coach_tenures.length > 0);
  const hasManagerRole = (careerStats?.manager_stats && careerStats.manager_stats.length > 0) ||
    careerStats?.official_coach_tenures?.some((t) => t.pos.includes("總教練") || t.pos.includes("監督")) ||
    careerStats?.coach_tenures?.some((t) => t.role?.includes("總教練") || t.role?.includes("監督"));

  return (
      // #218 選手頁首：卡面色塊、不鋪隊色條；身分＝印記＋序號列＋名字＋身分標籤，三圍只在這裡出現一次。
      <div className="card mb-5">
        <div className="px-4 py-4 md:px-5">
        <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          {/* 左欄：身分資訊（置頂）＋得獎（置底） */}
          <div className="flex min-w-0 flex-col">
          <div className="min-w-0">
            <div className="flex items-start gap-3.5">
              <TeamLogo code={tc} name={profile.team ?? undefined} size={52} decorative={!!heroName} />
              <div className="min-w-0 flex-1">
              {/* 名字＋徽章列（左）／本季數值（區塊右上角；窄螢幕掉到名字下方避免擠壓） */}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  {/* 序號列（#218 選手頁）：隊名・主守位・投打——取代原本逐顆徽章的守位／投打 */}
                  <Serial items={[
                    heroName ? { text: heroName } : null,
                    profile.primary_position ? { text: <span title="主守位：本季出賽最多的守位或指定打擊（DH 由打擊出賽扣守備推算；本季無資料則取生涯守備）">{profile.primary_position}</span> } : null,
                    profile.throws ? { text: <span title="投球慣用手">{profile.throws}</span> } : null,
                    profile.bats ? { text: <span title="打擊慣用手">{profile.bats}</span> } : null,
                  ]} />
                  <h1 className="mt-1 text-[26px] font-black leading-tight tracking-[0.04em] text-ink [word-break:keep-all] md:text-[30px]">{profile.name}</h1>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {hasPlayerRole && <span className="pm-tag">球員</span>}
                    {hasCoachRole && <span className="pm-tag">教練</span>}
                    {hasManagerRole && <span className="pm-tag">總教練</span>}
                    {profile.import_status && profile.import_status !== "local" && (
                      <span
                        className="pm-tag font-bold"
                        style={{ color: STATUS_COLORS[profile.import_status] }}
                        title={`${IMPORT_BADGE[profile.import_status].hint}${profile.country ? `（國籍：${profile.country}）` : ""}`}>
                        {profile.import_label}
                      </span>
                    )}
                    {profile.roster_level && (
                      <span
                        className="pm-tag"
                        title={`目前登錄層級（依最後一次升降事件判定）${profile.roster_days
                          ? `：本季累計 一軍 ${profile.roster_days.first} 天 · 二軍 ${profile.roster_days.farm} 天` : ""}`}>
                        {profile.roster_level}選手
                      </span>
                    )}
                    {abSel?.card.signature && (
                      <span className="pm-tag"
                        title={role === "pitching"
                          ? "投球風格：最突出的出局方式（三振／滾地／飛球）"
                          : "打擊特色：進攻工具中最突出者（多項頂尖＝全能）"}>
                        {abSel.card.signature}型
                      </span>
                    )}
                    {profile.pitcher_role && (
                      <span className="pm-tag"
                        title="投手類型：先發＝先發場數佔半數以上；後援＝救援>中繼（終結者傾向）；中繼＝其餘後援投手">
                        {profile.pitcher_role}
                      </span>
                    )}
                  </div>
                  {profile.former_names?.length > 0 && (
                    <p className="mt-1 text-xs text-muted">曾用名：{profile.former_names.join("、")}</p>
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
                      <p className="mt-2 text-[13px] text-muted">{bio.join("・")}</p>
                    ) : null;
                  })()}
                </div>
                {/* headline 與全域 scope 同步 */}
                {/* 三圍（#218）：寬體大數字＋下方標籤；OPS 一行石油藍。投手：ERA／勝敗／局數。 */}
                {headline && role === "batting" && (
                  <div className="shrink-0 rounded-md bg-surface-2 px-3 py-2.5 sm:bg-transparent sm:p-0 sm:text-right"
                    aria-label={`${scope === "season" ? "2026 本季" : "生涯"}打擊率 ${f3(headline.avg)}、上壘率 ${f3(headline.obp)}、長打率 ${f3(headline.slg)}，OPS ${f3(headline.ops)}`}>
                    <div className="mb-1 text-xs text-muted">{scope === "season" ? "2026 本季" : "生涯"}</div>
                    <div className="grid grid-cols-3 gap-x-3.5 sm:justify-end" aria-hidden="true">
                      {([["打擊率", headline.avg], ["上壘率", headline.obp], ["長打率", headline.slg]] as const).map(([k, v]) => (
                        <div key={k}>
                          <div className="font-[family-name:var(--font-wide)] text-[28px] font-black leading-none tabular-nums text-ink [font-stretch:70%] md:text-[30px]">{f3(v)}</div>
                          <div className="mt-1 whitespace-nowrap text-xs text-muted">{k}</div>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 font-[family-name:var(--font-wide)] text-lg font-extrabold tabular-nums text-accent [font-stretch:80%]" aria-hidden="true">OPS {f3(headline.ops)}</div>
                  </div>
                )}
                {headline && role === "pitching" && (
                  <div className="shrink-0 rounded-md bg-surface-2 px-3 py-2.5 sm:bg-transparent sm:p-0 sm:text-right">
                    <div className="mb-1 text-xs text-muted">{scope === "season" ? "2026 本季" : "生涯"}</div>
                    <div className="font-[family-name:var(--font-wide)] text-[30px] font-black leading-none tabular-nums text-ink [font-stretch:70%]">{numOf(headline.era)?.toFixed(2) ?? "—"} <span className="text-base font-bold">ERA</span></div>
                    <div className="mt-1.5 text-sm tabular-nums text-muted">{headline.w ?? 0}-{headline.l ?? 0}・{fmtIP(headline.ip as number | string | null)} 局</div>
                  </div>
                )}
              </div>
              <div className="my-3" />
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
                        className="pm-tag inline-flex items-center gap-1 !text-ink"
                        title={`${t.name}　${t.from === t.to ? t.from : `${t.from}–${t.to}`}`}>
                        {/* 現役 franchise 的當期隊名走核可印記；歷史隊名（兄弟象、Lamigo…）沿用字母章 */}
                        {markCodeOf(null, t.name)
                          ? <TeamLogo name={t.name} size={14} decorative />
                          : <LetterBadge meta={b} size={14} />}
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
                  <span className="text-muted">旅外</span>
                  {careerStats.overseas.map((o) => (
                    <span key={`${o.league}-${o.year}`}
                      className="pm-tag inline-flex items-center gap-1"
                      title={`${o.league}${o.team ? ` · ${o.team}` : ""} · ${o.year} 加盟`}>
                      {o.league}{o.team ? ` · ${o.team}` : ""}
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
            // 榮譽（#218 emoji 處置：🏆🏅 改文字身分標籤「總冠軍 ×2」，獎牌寫「銅牌」）
            <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-3">
              {careerStats?.championships && (
                <span title={`總冠軍年份：${careerStats.championships.years.join("、")}`}
                  className="pm-tag font-bold !text-ink">
                  總冠軍 ×{careerStats.championships.count}
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
                return (
                  <>
                    {groups.map((g) => (
                      <span key={g.label} title={[...new Set(g.years)].sort((a, b) => a - b).map((y) => `'${String(y).slice(2)}`).join(" ")}
                        className="pm-tag !text-ink">
                        {g.label}{g.years.length > 1 && <b className="ml-1 font-bold">×{g.years.length}</b>}
                      </span>
                    ))}
                    {(careerStats?.medals ?? []).map((m, i) => (
                      <span key={`${m.competition}-${m.year}-${i}`} title={m.year ? `'${String(m.year).slice(2)}` : undefined}
                        className="pm-tag !text-ink">
                        {m.competition} {m.color}牌
                      </span>
                    ))}
                    {/* 維基補充：舊聯盟（台灣大聯盟/台灣大賽）與國際/日韓職獎項——官網獎項表沒有 */}
                    {(careerStats?.wiki_awards ?? []).map((w) => (
                      <span key={w.award}
                        title={`${w.years.map((y) => `'${String(y).slice(2)}`).join(" ")}${w.note ? `（${w.note}）` : ""}　資料：維基百科`}
                        className="pm-tag">
                        {w.award}{w.years.length > 1 && <b className="ml-1 font-bold">×{w.years.length}</b>}
                      </span>
                    ))}
                  </>
                );
              })()}
            </div>
          )}
          </div>
          {/* 右欄：能力值雷達，scope 由 Hero 下方的全域控制驅動 */}
          {abSel && (
            <div className="min-w-0 rounded-md bg-surface-2 px-3 py-2.5 lg:bg-transparent lg:p-0">
              <div className="mb-1 text-center text-[13px] font-bold text-ink">
                {abSel.eff === "season" ? "2026 本季能力" : "生涯能力"}
              </div>
              {/* 雷達單色（#218：石油藍線＋淡底），不吃隊色 */}
              <AbilityCard card={abSel.card} chartSize="hero" showChartOverall hideNote />
            </div>
          )}
        </div>
        </div>
      </div>
  );
}
