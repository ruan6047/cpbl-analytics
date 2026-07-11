import Link from "next/link";
import { notFound } from "next/navigation";
import { StandingsTrend } from "@/components/standings-trend";
import { ActivePill, Card, EraBadge, StatTile, TeamLogo } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { api } from "@/lib/api";
import { contrastText, fanNick, nameMeta, teamColor } from "@/lib/teams";
import { CoachGrid, GROUPS, ManagersTable, PlayerTable, RetiredNumbers, RosterChips, RosterTable, f2, f3 } from "./parts";

export const dynamic = "force-dynamic";

export default async function TeamPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const [{ season, items }, derived, special, trend, games, bat, pit, eras, roster, der] = await Promise.all([
    api.officialStandings(0),
    api.standings(),
    api.specialRecords(),
    api.standingsTrend(),
    api.gamesRecent(200),
    api.battingLeaders("ops", { limit: 500, minPa: 30 }),
    api.pitchingLeaders("era", { limit: 500, minIp: 20 }),
    api.teamEras(code),
    api.teamPlayers(code),
    api.teamDer(code).catch(() => ({ team: code, franchise: code, items: [] })),
  ]);

  const team = items.find((t) => t.team_code === code);
  // 已解散球隊不在現役 standings，但仍有 franchise 隊史；無隊史才真正 404。
  if (!team && eras.eras.length === 0) notFound();

  const coaches = roster.coaches ?? [];
  const managers = roster.managers ?? [];
  const rst = roster.roster ?? { first_batters: [], first_pitchers: [], farm: [] };
  const retired = roster.retired ?? [];
  const lastEra = eras.eras[eras.eras.length - 1];
  const displayName = team?.team_name ?? lastEra?.name ?? code;
  const adv = team ? derived.standings.find((d) => d.code === code) : undefined;
  const sp = team ? special.items.find((s) => s.team_code === code) : undefined;
  // 歷史/已解散隊：以隊名取 era-correct 隊色(如 三商虎 水藍)；現役 fallback 到 franchise 色。
  const _bd = nameMeta(displayName);
  const color = _bd.letter !== "?" ? _bd.color : teamColor(code);
  const ink = contrastText(color);

  // 本季 DER（守備效率；官方投球總計算術）：值 + 年度名次 + 聯盟均值
  const derNow = team ? der.items.find((d) => d.year === season) : undefined;
  const teamGames = team ? games.items
    .filter((g) => g.home_team_code === code || g.away_team_code === code)
    .sort((a, b) => b.game_date.localeCompare(a.game_date))
    .slice(0, 14) : [];
  const hitters = team ? bat.items.filter((p) => p.team === team.team_name).slice(0, 8) : [];
  const pitchers = team ? pit.items.filter((p) => p.team === team.team_name).slice(0, 8) : [];
  const opponents = items.filter((t) => t.team_code !== code);

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="flex flex-wrap items-center gap-4 rounded-2xl p-6" style={{ background: color, color: ink }}>
        <TeamLogo code={code} name={displayName} size={56} />
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
            {displayName}
            {!team && <span className="rounded bg-black/20 px-2 py-0.5 text-xs font-medium">已解散</span>}
          </h1>
          <div className="text-sm opacity-90">
            {team ? `${season} 球季 · 第 ${team.rank} 名` : `${eras.eras[0]?.from}–${lastEra?.to} · 已退出一軍`}
            {fanNick(code) && (
              <span className="ml-2 opacity-75" title="球迷暱稱（非官方，源自網路社群，部分含自嘲意味）">
                「{fanNick(code)!.nick}」
              </span>
            )}
          </div>
        </div>
        <div className="ml-auto text-right">
          {team ? (
            <>
              <div className="font-mono text-3xl font-bold tabular-nums">{team.w}-{team.t}-{team.l}</div>
              <div className="text-sm opacity-90">
                勝率 {f3(team.win_pct)} · 勝差 {team.gb && team.gb > 0 ? team.gb : "—"} · 近十場 {team.last10 ?? "—"}
              </div>
            </>
          ) : (
            <>
              <div className="font-mono text-3xl font-bold tabular-nums">{eras.total.w}-{eras.total.t}-{eras.total.l}</div>
              <div className="text-sm opacity-90">隊史勝率 {f3(eras.total.win_pct)}</div>
            </>
          )}
        </div>
      </div>

      {/* 攻守概覽（僅現役）*/}
      {team && (
      <section>
        <h2 className="mb-3 text-lg font-semibold">攻守概覽</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatTile label="團隊 OPS" value={f3(adv?.ops)} accent />
          <StatTile label="團隊 ERA" value={f2(adv?.era)} />
          <StatTile label="WHIP" value={f2(adv?.whip)} />
          <StatTile label="得分/場" value={f2(adv?.rs_pg)} />
          <StatTile label="失分/場" value={f2(adv?.ra_pg)} />
          <StatTile label="得失分差" value={adv ? (adv.run_diff > 0 ? `+${adv.run_diff}` : `${adv.run_diff}`) : "—"} accent />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <StatTile label="主場" value={team.home_record ?? "—"} />
          <StatTile label="客場" value={team.away_record ?? "—"} />
          <StatTile label="連勝/敗" value={team.streak ?? "—"} />
          <StatTile label="淘汰指數" value={team.elim && team.elim !== "" ? team.elim : "—"} />
          <StatTile label={`守備效率 DER${derNow ? `（第 ${derNow.rnk} 名）` : ""}`}
            value={derNow ? Number(derNow.der).toFixed(3) : "—"} />
        </div>
      </section>
      )}

      {/* 隊史紀錄（franchise 全史）*/}
      {eras.eras.length >= 1 && (
        <section>
          <h2 className="mb-1 text-lg font-semibold">隊史紀錄</h2>
          <p className="mb-3 text-[11px] text-faint">含改名/轉賣前身的 franchise 全史（一軍例行賽）。</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile label="隊史總戰績" value={`${eras.total.w}-${eras.total.t}-${eras.total.l}`} accent />
            <StatTile label="隊史勝率" value={f3(eras.total.win_pct)} />
            <StatTile label="最長連勝" value={`${eras.longest_win_streak} 場`} />
            <StatTile label="最長連敗" value={`${eras.longest_lose_streak} 場`} />
            <StatTile label="最佳單季"
              value={eras.best_season ? `${eras.best_season.year}・${f3(eras.best_season.win_pct)}` : "—"} />
          </div>
          {eras.worst_season && (
            <p className="mt-2 text-[11px] text-faint">
              最差單季：{eras.worst_season.year}（{eras.worst_season.name}）勝率 {f3(eras.worst_season.win_pct)}
            </p>
          )}
        </section>
      )}

      {/* 球隊沿革（改名/轉賣視為同隊，分時期列出）*/}
      {eras.eras.length > 1 && (
        <section>
          <h2 className="mb-1 text-lg font-semibold">球隊沿革</h2>
          <p className="mb-3 text-[11px] text-faint">改名/轉賣視為同一支球隊，依隊名/年代分時期（一軍例行賽）。</p>
          <DataTable
            columns={[
              { header: "時期", cell: (e, i) => <span className="inline-flex items-center gap-1.5 font-medium"><EraBadge name={e.name} code={e.code} size={18} />{e.name}{team && i === eras.eras.length - 1 && <ActivePill className="ml-0.5 font-normal" />}</span>, nowrap: true, className: "font-sans" },
              { header: "年代", cell: (e) => (e.from === e.to ? e.from : `${e.from}–${e.to}`), className: "text-muted" },
              { header: "勝-和-敗", cell: (e) => `${e.w}-${e.t}-${e.l}` },
              { header: "勝率", cell: (e) => (e.win_pct == null ? "—" : f3(e.win_pct)), className: "text-accent" },
            ] satisfies Column<(typeof eras.eras)[number]>[]}
            rows={eras.eras}
            rowKey={(e) => `${e.code}-${e.from}`}
            dense
          />
        </section>
      )}

      <CoachGrid coaches={coaches} color={color} />
      <ManagersTable managers={managers} />
      <RetiredNumbers retired={retired} color={color} />

      {/* 現役球員（一軍 current + 二軍 D；僅現役球團）*/}
      {(rst.first_batters.length > 0 || rst.farm.length > 0) && (
        <section>
          <h2 className="mb-1 text-lg font-semibold">現役球員</h2>
          <p className="mb-3 text-[11px] text-faint">本季登錄名單；一軍取自當季成績、二軍取自二軍逐場。點擊看個人頁。</p>
          <div className="space-y-3">
            <RosterChips label={`一軍打者 (${rst.first_batters.length})`} players={rst.first_batters} color={color} />
            <RosterChips label={`一軍投手 (${rst.first_pitchers.length})`} players={rst.first_pitchers} color={color} />
            <RosterChips label={`二軍 (${rst.farm.length})`} players={rst.farm} color={color} dim />
          </div>
        </section>
      )}

      {/* 歷代球員（含 OB；曾效力 franchise，依生涯出賽排序，標注現役）*/}
      {(roster.batters.length > 0 || roster.pitchers.length > 0) && (
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <h2 className="mb-1 text-lg font-semibold">歷代打者</h2>
            <p className="mb-3 text-[11px] text-faint">曾效力此球團（含前身）之打者，依生涯出賽數排序。</p>
            <RosterTable rows={roster.batters.map((p) => ({
              id: p.player_id, name: p.name, active: p.active, span: `${p.from}–${p.to}`,
              a: `${p.g} 場`, b: `${p.h} 安 ${p.hr} 轟` }))} cols={["球員", "年代", "出賽", "打擊"]} />
          </div>
          <div>
            <h2 className="mb-1 text-lg font-semibold">歷代投手</h2>
            <p className="mb-3 text-[11px] text-faint">曾效力此球團（含前身）之投手，依生涯出賽數排序。</p>
            <RosterTable rows={roster.pitchers.map((p) => ({
              id: p.player_id, name: p.name, active: p.active, span: `${p.from}–${p.to}`,
              a: `${p.g} 場`, b: `${p.w}勝 ${p.sv}救` }))} cols={["球員", "年代", "出賽", "投球"]} />
          </div>
        </section>
      )}

      {/* 戰績走勢（僅現役）*/}
      {team && trend.points.length > 0 && (
        <section>
          <h2 className="mb-1 text-lg font-semibold">戰績走勢</h2>
          <p className="mb-3 text-[11px] text-faint">各隊累積勝-敗差；{team.team_name} 為 {team.rank} 名。</p>
          <Card teamColor={color} className="p-4"><StandingsTrend teams={trend.teams} points={trend.points} /></Card>
        </section>
      )}

      {/* 對戰各隊（僅現役）*/}
      {team && (
      <section>
        <h2 className="mb-3 text-lg font-semibold">對戰各隊</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {opponents.map((o) => (
            <Card key={o.team_code} teamColor={teamColor(o.team_code)} className="flex items-center gap-2 p-3">
              <TeamLogo code={o.team_code} size={22} />
              <span className="text-sm text-muted">{o.team_name}</span>
              <span className="ml-auto font-mono text-sm">{team.h2h?.[o.team_code] ?? "—"}</span>
            </Card>
          ))}
        </div>
      </section>
      )}

      {/* 近期賽事（僅現役）*/}
      {team && (
      <section>
        <h2 className="mb-3 text-lg font-semibold">近期賽事</h2>
        <DataTable
          hideHeader
          columns={[
            { header: "", cell: (g) => g.game_date.slice(5), className: "text-faint" },
            { header: "", cell: (g) => (g.home_team_code === code ? "主" : "客"), className: "text-muted" },
            { header: "", cell: (g) => {
              const home = g.home_team_code === code;
              const oppCode = home ? g.away_team_code : g.home_team_code;
              const oppName = home ? g.away_team_name : g.home_team_name;
              return <Link href={`/teams/${oppCode}`} className="inline-flex items-center gap-1.5 hover:underline"><TeamLogo code={oppCode} name={oppName} size={18} />{oppName}</Link>;
            }, className: "font-sans" },
            { header: "", cell: (g) => {
              const home = g.home_team_code === code;
              const us = home ? g.home_score : g.away_score;
              const them = home ? g.away_score : g.home_score;
              return <span className={`font-semibold ${us > them ? "text-up" : us === them ? "text-muted" : "text-down"}`}>{us > them ? "勝" : us === them ? "和" : "敗"}</span>;
            } },
            { header: "", cell: (g) => {
              const home = g.home_team_code === code;
              return `${home ? g.home_score : g.away_score}-${home ? g.away_score : g.home_score}`;
            } },
          ] satisfies Column<(typeof teamGames)[number]>[]}
          rows={teamGames}
          rowKey={(g) => g.game_sno}
          dense
        />
      </section>
      )}

      {/* 特殊戰績 */}
      {sp && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">特殊戰績</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {GROUPS.map((grp) => (
              <Card key={grp.title} teamColor={color} className="p-4">
                <div className="mb-2 text-sm font-semibold text-ink">{grp.title}</div>
                <dl className="space-y-1.5">
                  {grp.rows.map((r) => (
                    <div key={r.label} className="flex items-center justify-between text-sm">
                      <dt className="text-muted">{r.label}</dt>
                      <dd className="font-mono tabular-nums">{r.render(sp)}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* 本季主力球員（僅現役）*/}
      {team && (
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold">本季主力打者（OPS）</h2>
          <PlayerTable
            rows={hitters.map((p) => ({ id: p.player_id, name: p.name, a: f3(p.ops), b: `${p.hr ?? 0} HR` }))}
            cols={["球員", "OPS", "全壘打"]}
          />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">本季主力投手（ERA）</h2>
          <PlayerTable
            rows={pitchers.map((p) => ({ id: p.player_id, name: p.name, a: f2(p.era), b: `${p.w ?? 0}勝${p.l ?? 0}敗` }))}
            cols={["球員", "ERA", "勝敗"]}
          />
        </div>
      </section>
      )}
    </div>
  );
}
