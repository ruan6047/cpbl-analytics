import Link from "next/link";
import { notFound } from "next/navigation";
import { StandingsTrend } from "@/components/standings-trend";
import { Card, StatTile, TeamLogo } from "@/components/ui";
import { api } from "@/lib/api";
import type { SpecialRecord, WL, WTL } from "@/lib/api";
import { contrastText, eraBadge, teamColor } from "@/lib/teams";

export const dynamic = "force-dynamic";

const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));
const f2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));

// W-L 上色字串
function wl(p?: WL) {
  if (!p) return <span className="text-faint">—</span>;
  const [w, l] = p;
  if (w + l === 0) return <span className="text-faint">0-0</span>;
  const c = w / (w + l);
  return <span className={c > 0.5 ? "text-up" : c < 0.5 ? "text-down" : "text-muted"}>{w}-{l}</span>;
}
function wtl(p?: WTL) {
  if (!p) return <span className="text-faint">—</span>;
  const [w, t, l] = p;
  if (w + t + l === 0) return <span className="text-faint">—</span>;
  return <span className={w > l ? "text-up" : l > w ? "text-down" : "text-muted"}>{w}-{t}-{l}</span>;
}

// 特殊戰績分組（單隊縱向呈現）
const GROUPS: { title: string; rows: { label: string; render: (s: SpecialRecord) => React.ReactNode }[] }[] = [
  {
    title: "場地",
    rows: [
      { label: "天然草皮", render: (s) => wl(s.natural) },
      { label: "人工草皮", render: (s) => wl(s.artificial) },
      { label: "室內（大巨蛋）", render: (s) => wl(s.indoor) },
    ],
  },
  {
    title: "比分型",
    rows: [
      { label: "一分差", render: (s) => wl(s.one_run) },
      { label: "大勝大敗（≥5）", render: (s) => wl(s.blowout) },
      { label: "完封 勝-被", render: (s) => wl(s.shutout) },
      { label: "逆轉 勝-被", render: (s) => wl(s.comeback) },
    ],
  },
  {
    title: "賽況軌跡",
    rows: [
      { label: "得分先馳", render: (s) => wl(s.scored_first) },
      { label: "先失分", render: (s) => wl(s.scored_first_against) },
      { label: "戰況激烈", render: (s) => wl(s.intense) },
      { label: "順風（曾領先≥3）", render: (s) => wl(s.tailwind) },
      { label: "逆風（曾落後≥3）", render: (s) => wl(s.headwind) },
      { label: "大局（單局≥4）", render: (s) => wl(s.big_inning) },
    ],
  },
  {
    title: "終局與守備",
    rows: [
      { label: "延長賽", render: (s) => wl(s.extra) },
      { label: "救援守成 成-敗", render: (s) => wl(s.save) },
      { label: "失誤場", render: (s) => wl(s.errorful) },
    ],
  },
  {
    title: "賽程 / 對手",
    rows: [
      { label: "平日", render: (s) => wl(s.weekday) },
      { label: "假日", render: (s) => wl(s.weekend) },
      { label: "vs 左投", render: (s) => wl(s.vs_lhp) },
      { label: "vs 右投", render: (s) => wl(s.vs_rhp) },
    ],
  },
  {
    title: "系列賽",
    rows: [
      { label: "三連戰 勝-平-負", render: (s) => wtl(s.series3) },
      { label: "三連戰橫掃", render: (s) => <span className="text-muted">{s.sweeps || "—"}</span> },
      { label: "被三連戰橫掃", render: (s) => <span className="text-muted">{s.swept || "—"}</span> },
      { label: "雙連賽 勝-平-負", render: (s) => wtl(s.series2) },
    ],
  },
  {
    title: "再見 / 連勝",
    rows: [
      { label: "再見勝", render: (s) => <span className="text-up">{s.walkoff || "—"}</span> },
      { label: "被再見", render: (s) => <span className="text-down">{s.walked_off || "—"}</span> },
      { label: "最大連勝", render: (s) => <span className="text-up">{s.max_win_streak || "—"}</span> },
      { label: "最大連敗", render: (s) => <span className="text-down">{s.max_lose_streak || "—"}</span> },
    ],
  },
];

export default async function TeamPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const [{ season, items }, derived, special, trend, games, bat, pit, eras, roster] = await Promise.all([
    api.officialStandings(0),
    api.standings(),
    api.specialRecords(),
    api.standingsTrend(),
    api.gamesRecent(200),
    api.battingLeaders("ops", { limit: 500, minPa: 30 }),
    api.pitchingLeaders("era", { limit: 500, minIp: 20 }),
    api.teamEras(code),
    api.teamPlayers(code),
  ]);

  const team = items.find((t) => t.team_code === code);
  // 已解散球隊不在現役 standings，但仍有 franchise 隊史；無隊史才真正 404。
  if (!team && eras.eras.length === 0) notFound();

  const coaches = roster.coaches ?? [];
  const rst = roster.roster ?? { first_batters: [], first_pitchers: [], farm: [] };
  const lastEra = eras.eras[eras.eras.length - 1];
  const displayName = team?.team_name ?? lastEra?.name ?? code;
  const adv = team ? derived.standings.find((d) => d.code === code) : undefined;
  const sp = team ? special.items.find((s) => s.team_code === code) : undefined;
  const color = teamColor(code);
  const ink = contrastText(color);

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
        <TeamLogo code={code} size={56} />
        <div>
          <div className="flex items-center gap-2 text-2xl font-bold">
            {displayName}
            {!team && <span className="rounded bg-black/20 px-2 py-0.5 text-xs font-medium">已解散</span>}
          </div>
          <div className="text-sm opacity-90">
            {team ? `${season} 球季 · 第 ${team.rank} 名` : `${eras.eras[0]?.from}–${lastEra?.to} · 已退出一軍`}
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
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="主場" value={team.home_record ?? "—"} />
          <StatTile label="客場" value={team.away_record ?? "—"} />
          <StatTile label="連勝/敗" value={team.streak ?? "—"} />
          <StatTile label="淘汰指數" value={team.elim && team.elim !== "" ? team.elim : "—"} />
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
          <div className="overflow-hidden rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-muted">
                <tr>{["時期", "年代", "勝-和-敗", "勝率"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {eras.eras.map((e, i) => {
                  const bg = eraBadge(e.name, e.code);
                  return (
                  <tr key={`${e.code}-${e.from}`} className="border-t border-line hover:bg-surface-2">
                    <td className="whitespace-nowrap px-3 py-2 font-sans font-medium">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="inline-flex h-[18px] w-[18px] items-center justify-center rounded-md text-[10px] font-extrabold"
                          style={{ background: bg.color, color: contrastText(bg.color) }}>{bg.letter}</span>
                        {e.name}
                        {team && i === eras.eras.length - 1 && <span className="ml-0.5 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-normal text-muted">現役</span>}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-muted">{e.from === e.to ? e.from : `${e.from}–${e.to}`}</td>
                    <td className="px-3 py-2">{e.w}-{e.t}-{e.l}</td>
                    <td className="px-3 py-2 text-accent">{e.win_pct == null ? "—" : f3(e.win_pct)}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 現役教練團（僅現役球團；官網現役名單，無歷史勝率）*/}
      {coaches.length > 0 && (
        <section>
          <h2 className="mb-1 text-lg font-semibold">現役教練團</h2>
          <p className="mb-3 text-[11px] text-faint">官方現役教練名單（一軍）；總教練居首。</p>
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
            {coaches.map((co) => (
              <Card key={`${co.pos}-${co.name}`} className="flex items-center gap-2.5 p-3">
                <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md font-mono text-xs font-bold tabular-nums"
                  style={{ background: `${color}1a`, color }}>{co.uniform_no ?? "—"}</span>
                <div className="min-w-0">
                  <div className="truncate text-[11px] text-muted">{co.pos.replace(/^一軍/, "")}</div>
                  <div className="truncate font-medium text-ink">{co.name}</div>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

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
          <Card className="p-4"><StandingsTrend teams={trend.teams} points={trend.points} /></Card>
        </section>
      )}

      {/* 對戰各隊（僅現役）*/}
      {team && (
      <section>
        <h2 className="mb-3 text-lg font-semibold">對戰各隊</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {opponents.map((o) => (
            <Card key={o.team_code} className="flex items-center gap-2 p-3">
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
        <div className="overflow-hidden rounded-xl border border-line">
          <table className="w-full text-sm">
            <tbody className="font-mono tabular-nums">
              {teamGames.map((g) => {
                const home = g.home_team_code === code;
                const us = home ? g.home_score : g.away_score;
                const them = home ? g.away_score : g.home_score;
                const oppCode = home ? g.away_team_code : g.home_team_code;
                const oppName = home ? g.away_team_name : g.home_team_name;
                const win = us > them;
                return (
                  <tr key={g.game_sno} className="border-t border-line first:border-0 hover:bg-surface-2">
                    <td className="px-3 py-2 text-faint">{g.game_date.slice(5)}</td>
                    <td className="px-3 py-2 text-muted">{home ? "主" : "客"}</td>
                    <td className="px-3 py-2 font-sans">
                      <Link href={`/teams/${oppCode}`} className="inline-flex items-center gap-1.5 hover:underline">
                        <TeamLogo code={oppCode} size={18} />{oppName}
                      </Link>
                    </td>
                    <td className={`px-3 py-2 font-semibold ${win ? "text-up" : us === them ? "text-muted" : "text-down"}`}>
                      {win ? "勝" : us === them ? "和" : "敗"}
                    </td>
                    <td className="px-3 py-2">{us}-{them}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      )}

      {/* 特殊戰績 */}
      {sp && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">特殊戰績</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {GROUPS.map((grp) => (
              <Card key={grp.title} className="p-4">
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

function RosterChips({ label, players, color, dim }: {
  label: string; players: { player_id: string; name: string }[]; color: string; dim?: boolean;
}) {
  if (players.length === 0) return null;
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium text-muted">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {players.map((p) => (
          <Link key={p.player_id} href={`/players/${p.player_id}`}
            className={`rounded-full border border-line px-2.5 py-1 text-sm transition hover:border-current ${dim ? "text-muted" : ""}`}
            style={dim ? undefined : { color }}>
            {p.name}
          </Link>
        ))}
      </div>
    </div>
  );
}

function RosterTable({ rows, cols }: {
  rows: { id: string; name: string; active: boolean; span: string; a: string; b: string }[];
  cols: string[];
}) {
  if (rows.length === 0) return <p className="text-sm text-faint">尚無資料。</p>;
  return (
    <div className="overflow-hidden rounded-xl border border-line">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr>{cols.map((c) => <th key={c} className="px-3 py-2 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-line hover:bg-surface-2">
              <td className="px-3 py-2">
                <Link href={`/players/${r.id}`} className="inline-flex items-center gap-1.5 hover:underline">
                  {r.name}
                  {r.active && <span className="rounded bg-up/15 px-1 py-0.5 text-[9px] font-medium text-up">現役</span>}
                </Link>
              </td>
              <td className="px-3 py-2 font-mono text-[11px] text-muted">{r.span}</td>
              <td className="px-3 py-2 font-mono">{r.a}</td>
              <td className="px-3 py-2 font-mono text-muted">{r.b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlayerTable({ rows, cols }: { rows: { id: string; name: string | null; a: string; b: string }[]; cols: [string, string, string] | string[] }) {
  if (rows.length === 0) return <p className="text-sm text-faint">尚無資料。</p>;
  return (
    <div className="overflow-hidden rounded-xl border border-line">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr>{cols.map((c) => <th key={c} className="px-3 py-2 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-line hover:bg-surface-2">
              <td className="px-3 py-2"><Link href={`/players/${r.id}`} className="hover:underline">{r.name ?? "—"}</Link></td>
              <td className="px-3 py-2 font-mono">{r.a}</td>
              <td className="px-3 py-2 font-mono text-muted">{r.b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
