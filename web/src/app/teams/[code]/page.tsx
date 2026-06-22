import Link from "next/link";
import { notFound } from "next/navigation";
import { StandingsTrend } from "@/components/standings-trend";
import { Card, StatTile, TeamLogo } from "@/components/ui";
import { api } from "@/lib/api";
import type { SpecialRecord, WL, WTL } from "@/lib/api";
import { contrastText, teamColor } from "@/lib/teams";

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
  const [{ season, items }, derived, special, trend, games, bat, pit] = await Promise.all([
    api.officialStandings(0),
    api.standings(),
    api.specialRecords(),
    api.standingsTrend(),
    api.gamesRecent(200),
    api.battingLeaders("ops", { limit: 500, minPa: 30 }),
    api.pitchingLeaders("era", { limit: 500, minIp: 20 }),
  ]);

  const team = items.find((t) => t.team_code === code);
  if (!team) notFound();

  const adv = derived.standings.find((d) => d.code === code);
  const sp = special.items.find((s) => s.team_code === code);
  const color = teamColor(code);
  const ink = contrastText(color);

  const teamGames = games.items
    .filter((g) => g.home_team_code === code || g.away_team_code === code)
    .sort((a, b) => b.game_date.localeCompare(a.game_date))
    .slice(0, 14);
  const hitters = bat.items.filter((p) => p.team === team.team_name).slice(0, 8);
  const pitchers = pit.items.filter((p) => p.team === team.team_name).slice(0, 8);
  const opponents = items.filter((t) => t.team_code !== code);

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="flex flex-wrap items-center gap-4 rounded-2xl p-6" style={{ background: color, color: ink }}>
        <TeamLogo code={code} size={56} />
        <div>
          <div className="text-2xl font-bold">{team.team_name}</div>
          <div className="text-sm opacity-90">{season} 球季 · 第 {team.rank} 名</div>
        </div>
        <div className="ml-auto text-right">
          <div className="font-mono text-3xl font-bold tabular-nums">{team.w}-{team.t}-{team.l}</div>
          <div className="text-sm opacity-90">
            勝率 {f3(team.win_pct)} · 勝差 {team.gb && team.gb > 0 ? team.gb : "—"} · 近十場 {team.last10 ?? "—"}
          </div>
        </div>
      </div>

      {/* 攻守概覽 */}
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

      {/* 戰績走勢 */}
      {trend.points.length > 0 && (
        <section>
          <h2 className="mb-1 text-lg font-semibold">戰績走勢</h2>
          <p className="mb-3 text-[11px] text-faint">各隊累積勝-敗差；{team.team_name} 為 {team.rank} 名。</p>
          <Card className="p-4"><StandingsTrend teams={trend.teams} points={trend.points} /></Card>
        </section>
      )}

      {/* 對戰各隊 */}
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

      {/* 近期賽事 */}
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

      {/* 主力球員 */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold">主力打者（OPS）</h2>
          <PlayerTable
            rows={hitters.map((p) => ({ id: p.player_id, name: p.name, a: f3(p.ops), b: `${p.hr ?? 0} HR` }))}
            cols={["球員", "OPS", "全壘打"]}
          />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">主力投手（ERA）</h2>
          <PlayerTable
            rows={pitchers.map((p) => ({ id: p.player_id, name: p.name, a: f2(p.era), b: `${p.w ?? 0}勝${p.l ?? 0}敗` }))}
            cols={["球員", "ERA", "勝敗"]}
          />
        </div>
      </section>
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
