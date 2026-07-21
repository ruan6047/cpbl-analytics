import Link from "next/link";
import { notFound } from "next/navigation";
import { ActivePill, Card, EraBadge, StatTile, TeamLogo } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { Tabs } from "@/components/tabs";
import { type FieldCells, type FieldPosition } from "@/components/field-diagram";
import { RosterBoard, type RosterGroup } from "@/components/roster-board";
import { api } from "@/lib/api";
import { contrastText, nameMeta, teamColor } from "@/lib/teams";
import { CoachGrid, GROUPS, ManagersTable, RetiredNumbers, RosterChips, RosterTable, f2, f3 } from "./parts";

export const dynamic = "force-dynamic";

export default async function TeamPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const [{ season, items }, derived, special, games, cal, bat, pit, field, eras, roster, der] = await Promise.all([
    api.officialStandings(0),
    api.standings(),
    api.specialRecords(),
    api.gamesRecent(200),
    api.gamesCalendar(),
    api.battingLeaders("ops", { limit: 500, minPa: 0 }),
    api.pitchingLeaders("ip", { limit: 500, minIp: 0 }),
    api.fielding("g", { limit: 1000 }),
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
  // 攻守概覽各項聯盟名次（六隊 adv 資料已載入，client 端排序，零額外請求）
  const teamN = derived.standings.length;
  const rankOf = (key: "ops" | "era" | "whip" | "rs_pg" | "ra_pg" | "run_diff", lowerBetter: boolean): number | null => {
    if (!adv) return null;
    const mine = adv[key];
    if (mine == null) return null;
    const vals = derived.standings.map((d) => d[key]).filter((v): v is number => v != null);
    const sorted = [...vals].sort((a, b) => (lowerBetter ? a - b : b - a));
    const r = sorted.indexOf(mine);
    return r >= 0 ? r + 1 : null;
  };
  const sp = team ? special.items.find((s) => s.team_code === code) : undefined;
  // 歷史/已解散隊：以隊名取 era-correct 隊色(如 三商虎 水藍)；現役 fallback 到 franchise 色。
  const _bd = nameMeta(displayName);
  const color = _bd.letter !== "?" ? _bd.color : teamColor(code);
  const ink = contrastText(color);

  // 本季 DER（守備效率；官方投球總計算術）：值 + 年度名次 + 聯盟均值
  const derNow = team ? der.items.find((d) => d.year === season) : undefined;
  // 近期賽事：下一場未開打（若有）+ 最近完賽，湊滿一排 6 張賽況卡
  const pad2 = (n: number) => String(n).padStart(2, "0");
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
  const isTeamGame = (g: { home_team_code: string; away_team_code: string }) => g.home_team_code === code || g.away_team_code === code;
  const upcoming = team ? cal.items
    .filter((g) => isTeamGame(g) && g.home_score + g.away_score === 0 && g.game_date >= todayStr)
    .sort((a, b) => a.game_date.localeCompare(b.game_date))[0] : undefined;
  const teamCompleted = team ? games.items
    .filter(isTeamGame)
    .sort((a, b) => b.game_date.localeCompare(a.game_date)) : [];
  const recentCompleted = teamCompleted.slice(0, upcoming ? 5 : 6);
  const teamGames = [
    ...(upcoming ? [{ ...upcoming, done: false }] : []),
    ...recentCompleted.map((g) => ({ ...g, done: true })),
  ];
  // Hero 近況：近 8 場勝負（舊→新，最新在右）
  const form = teamCompleted.slice(0, 8).map((g) => {
    const home = g.home_team_code === code;
    const us = home ? g.home_score : g.away_score;
    const them = home ? g.away_score : g.home_score;
    const opp = home ? g.away_team_name : g.home_team_name;
    return { r: us > them ? "W" : us === them ? "T" : "L", title: `${g.game_date.slice(5)} ${home ? "主" : "客"} vs ${opp} ${us}-${them}` };
  }).reverse();
  // 連勝敗：官方 streak 為「勝2／敗3」→ 口語「二連勝／三連敗」；單場不用「連」（避免「一連敗」）
  const streakZh = (s?: string | null): string => {
    if (!s) return "—";
    const m = s.match(/^(勝|敗|負|和)\s*(\d+)$/);
    if (!m) return s;
    const n = parseInt(m[2], 10);
    if (!n) return s;
    const res = m[1] === "負" ? "敗" : m[1];
    if (n === 1) return `1${res}`;
    const cjk = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
    const numZh = (x: number): string =>
      x <= 10 ? cjk[x] : x < 20 ? `十${cjk[x - 10]}` : `${cjk[Math.floor(x / 10)]}十${x % 10 ? cjk[x % 10] : ""}`;
    return `${numZh(n)}連${res}`;
  };
  const opponents = items.filter((t) => t.team_code !== code);

  // ── 本季陣容：守備位置圖（含 DH）+ 主要替補 + 投手分工（先發/中繼/後援）──
  // 目的是「快速認人」，非成績排行；每人可點入看細節，卡面至多帶 OPS+／ERA+。
  const POS_ZH_TO_FIELD: Record<string, FieldPosition> = {
    "左外野手": "LF", "中外野手": "CF", "右外野手": "RF",
    "三壘手": "3B", "游擊手": "SS", "二壘手": "2B", "一壘手": "1B", "捕手": "C",
  };
  const teamBat = team ? bat.items.filter((b) => b.team === team.team_name) : [];
  const teamPit = team ? pit.items.filter((p) => p.team === team.team_name) : [];
  const teamField = team ? field.items.filter((f) => f.team === team.team_name) : [];
  const opsPlusById = new Map(teamBat.map((b) => [b.player_id, b.ops_plus]));
  const opsSub = (id: string, fallback: string) => {
    const op = opsPlusById.get(id);
    return op != null ? `OPS+ ${op}` : fallback;
  };

  // 每人守備總出賽（判 DH 用）+ 各守位主力（守備出賽最多者）
  const fieldTotG = new Map<string, number>();
  for (const f of teamField) fieldTotG.set(f.player_id, (fieldTotG.get(f.player_id) ?? 0) + (f.g ?? 0));
  const byPos = new Map<FieldPosition, { id: string; name: string; g: number }>();
  for (const f of teamField) {
    const fp = POS_ZH_TO_FIELD[f.pos];
    if (!fp) continue;
    const g = f.g ?? 0;
    const cur = byPos.get(fp);
    if (!cur || g > cur.g) byPos.set(fp, { id: f.player_id, name: f.name ?? "—", g });
  }
  const lineupCells: FieldCells = {};
  for (const [fp, v] of byPos) lineupCells[fp] = { main: v.name, sub: opsSub(v.id, `${v.g} 場`), href: `/players/${v.id}` };
  const starterIds = new Set([...byPos.values()].map((v) => v.id));
  // 每人主守位（守備出賽最多的守位）→ 替補卡徽章；無守備者標「DH」
  const primaryPosById = new Map<string, string>();
  {
    const bestByPlayer = new Map<string, { pos: string; g: number }>();
    for (const f of teamField) {
      const fp = POS_ZH_TO_FIELD[f.pos];
      if (!fp) continue;
      const g = f.g ?? 0;
      const cur = bestByPlayer.get(f.player_id);
      if (!cur || g > cur.g) bestByPlayer.set(f.player_id, { pos: fp, g });
    }
    for (const [id, v] of bestByPlayer) primaryPosById.set(id, v.pos);
  }

  // 指定打擊：守備出賽≤打擊出賽半數（主要 DH）、打席最多者
  const dh = teamBat
    .filter((b) => (b.pa ?? 0) >= 80 && (fieldTotG.get(b.player_id) ?? 0) * 2 <= (b.g ?? 0))
    .sort((a, b) => (b.pa ?? 0) - (a.pa ?? 0))[0];
  const dhCell = dh ? { main: dh.name ?? "—", sub: dh.ops_plus != null ? `OPS+ ${dh.ops_plus}` : `${dh.pa} 打席`, href: `/players/${dh.player_id}` } : null;

  // 主要替補：非各守位主力、非 DH，達 30 打席者，依打席取前 6
  const bench = teamBat
    .filter((b) => !starterIds.has(b.player_id) && b.player_id !== dh?.player_id && (b.pa ?? 0) >= 30)
    .sort((a, b) => (b.pa ?? 0) - (a.pa ?? 0))
    .slice(0, 6);

  // 投手分工：先發（先發過半）／後援（救援>中繼）／中繼（其餘後援投手，依中繼場次）
  const isStarter = (p: typeof teamPit[number]) => (p.gs ?? 0) * 2 >= (p.g ?? 0) && (p.gs ?? 0) >= 1;
  const startersP = teamPit.filter(isStarter).sort((a, b) => (b.ip ?? 0) - (a.ip ?? 0)).slice(0, 5);
  const relievers = teamPit.filter((p) => !isStarter(p));
  const closers = relievers.filter((p) => (p.sv ?? 0) > (p.hld ?? 0)).sort((a, b) => (b.sv ?? 0) - (a.sv ?? 0)).slice(0, 3);
  const closerIds = new Set(closers.map((p) => p.player_id));
  const setup = relievers.filter((p) => !closerIds.has(p.player_id))
    .sort((a, b) => (b.hld ?? 0) - (a.hld ?? 0) || (b.g ?? 0) - (a.g ?? 0)).slice(0, 5);
  const eraPlusSub = (p: typeof teamPit[number]) => (p.era_plus != null ? `ERA+ ${p.era_plus}` : f2(p.era) ?? "—");
  const pitcherGroups = [
    { label: "先發投手", code: "SP", players: startersP },
    { label: "中繼投手", code: "RP", players: setup },
    { label: "後援投手", code: "CL", players: closers },
  ].filter((g) => g.players.length > 0);
  // 主力選手圖右側分組：投手（先發/中繼/後援）+ 替補野手（上方分隔線區隔）
  const rosterGroups: RosterGroup[] = [
    ...pitcherGroups.map((g) => ({
      label: g.label,
      cells: g.players.map((p) => ({ id: p.player_id, name: p.name, badge: g.code, stat: eraPlusSub(p) })),
    })),
    ...(bench.length > 0 ? [{
      label: "替補野手",
      divider: true,
      cells: bench.map((b) => ({
        id: b.player_id, name: b.name,
        badge: primaryPosById.get(b.player_id) ?? "DH",
        stat: b.ops_plus != null ? `OPS+ ${b.ops_plus}` : `${b.pa} 打席`,
      })),
    }] : []),
  ];

  return (
    <div className="space-y-8">
      {/* Hero：快速掌握球隊戰績與近況 */}
      <div className="rounded-2xl p-6" style={{ background: color, color: ink }}>
        <div className="flex flex-wrap items-center gap-4">
          <TeamLogo code={code} name={displayName} size={56} />
          <div className="min-w-0">
            <h1 className="flex flex-wrap items-center gap-x-2 gap-y-1 text-2xl font-extrabold tracking-tight">
              {displayName}
              {!team && <span className="rounded bg-black/20 px-2 py-0.5 text-xs font-medium">已解散</span>}
              {/* 球迷暱稱（fanNick）保留供未來搜尋/別名比對用，不於頁面直接顯示 */}
            </h1>
            <div className="text-sm opacity-90">
              {team ? `${season} 球季 · 第 ${team.rank} 名` : `${eras.eras[0]?.from}–${lastEra?.to} · 已退出一軍`}
            </div>
          </div>
          <div className="ml-auto text-right">
            {team ? (
              <>
                <div className="font-mono text-3xl font-bold tabular-nums">{team.w}-{team.t}-{team.l}</div>
                <div className="text-sm opacity-90">勝率 {f3(team.win_pct)}</div>
              </>
            ) : (
              <>
                <div className="font-mono text-3xl font-bold tabular-nums">{eras.total.w}-{eras.total.t}-{eras.total.l}</div>
                <div className="text-sm opacity-90">隊史勝率 {f3(eras.total.win_pct)}</div>
              </>
            )}
          </div>
        </div>

        {team && (
          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 border-t pt-3.5" style={{ borderColor: `${ink}2b` }}>
            {[
              { label: "勝差", value: team.gb && team.gb > 0 ? String(team.gb) : "—" },
              { label: "", value: streakZh(team.streak) },
              { label: "淘汰指數", value: team.elim && team.elim !== "" ? team.elim : "—" },
            ].map((s, i) => (
              <div key={s.label || i} className="flex items-baseline gap-1.5">
                {s.label && <span className="text-xs opacity-70">{s.label}</span>}
                <span className="font-mono text-base font-semibold tabular-nums">{s.value}</span>
              </div>
            ))}
            {form.length > 0 && (
              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs opacity-70">近況</span>
                <div className="flex items-center gap-1">
                  {form.map((f, i) => (
                    <span key={i} title={f.title}
                      className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-bold"
                      style={f.r === "W" ? { background: ink, color }
                        : f.r === "T" ? { background: `${ink}44`, color: ink }
                        : { boxShadow: `inset 0 0 0 1.5px ${ink}66`, color: ink, opacity: 0.75 }}>
                      {f.r === "W" ? "勝" : f.r === "T" ? "和" : "敗"}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {(() => {
        const pageTabs = [] as { label: string; content: React.ReactNode }[];

        // ── 本季戰況（僅現役）──
        if (team) pageTabs.push({ label: "本季", content: (
          <div className="space-y-5">
            {/* 攻守概覽：進攻 / 守備投球 兩組並排（桌機）＋橫向格位，最省縱向空間；進攻/守備 子標即分組，省區塊標題 */}
            <section>
              <div className="grid gap-x-6 gap-y-3 lg:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted">進攻</h3>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <StatTile label="OPS" value={f3(adv?.ops)} accent rank={rankOf("ops", false)} rankTotal={teamN} />
                    <StatTile label="得分/場" value={f2(adv?.rs_pg)} rank={rankOf("rs_pg", false)} rankTotal={teamN} />
                    <StatTile label="得失分差" value={adv ? (adv.run_diff > 0 ? `+${adv.run_diff}` : `${adv.run_diff}`) : "—"} accent rank={rankOf("run_diff", false)} rankTotal={teamN} />
                  </div>
                </div>
                <div>
                  <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted">守備投球</h3>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <StatTile label="ERA" value={f2(adv?.era)} rank={rankOf("era", true)} rankTotal={teamN} />
                    <StatTile label="WHIP" value={f2(adv?.whip)} rank={rankOf("whip", true)} rankTotal={teamN} />
                    <StatTile label="失分/場" value={f2(adv?.ra_pg)} rank={rankOf("ra_pg", true)} rankTotal={teamN} />
                    <StatTile label="DER" value={derNow ? Number(derNow.der).toFixed(3) : "—"} rank={derNow?.rnk ?? null} rankTotal={teamN} />
                  </div>
                </div>
              </div>
            </section>

            {/* 本季主力選手圖：野手守備圖（含 DH）+ 投手（先發/中繼/後援）+ 替補野手，統一為一張格位語言的圖。
                置於攻守概覽之後、近期賽事之前，讓主力選手圖能在電腦畫面內完整顯示。 */}
            <section>
              <h2 className="mb-3 text-lg font-semibold">本季主力選手</h2>
              <RosterBoard fieldCells={lineupCells} designatedHitter={dhCell} groups={rosterGroups}
                caption={`${displayName}本季各守位主力`} emptyField="尚無本季守備資料。" />
            </section>

            {/* 近期賽事（賽況頁記分條式：客隊徽左／主隊徽右、日期居中、比分夾中、勝方粗體；含下一場未開打）*/}
            <section>
              <h2 className="mb-3 text-lg font-semibold">近期賽事</h2>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
                {teamGames.map((g) => {
                  const [gy, gm, gd] = g.game_date.split("-").map(Number);
                  const wd = "日一二三四五六"[new Date(gy, gm - 1, gd).getDay()];
                  const winner = g.done && g.home_score !== g.away_score ? (g.home_score > g.away_score ? "home" : "away") : null;
                  const scoreCls = (side: "away" | "home") =>
                    `w-6 shrink-0 text-center font-mono text-lg tabular-nums ${winner === side ? "font-bold text-ink" : "text-muted"}`;
                  return (
                    <Link key={`${g.kind_code}-${g.game_sno}`} href={`/games/${g.game_sno}?kind=${g.kind_code}&year=${g.year}`}
                      className={`flex items-center gap-1.5 rounded-lg border bg-surface px-2 py-2 transition hover:bg-surface-2 ${g.done ? "border-line" : "border-dashed border-line"}`}>
                      <TeamLogo code={g.away_team_code} name={g.away_team_name} size={26} />
                      <span className={scoreCls("away")}>{g.done ? g.away_score : ""}</span>
                      <div className="flex-1 text-center leading-tight">
                        <div className="whitespace-nowrap font-mono text-xs text-faint tabular-nums">{g.game_date.slice(5)}</div>
                        <div className="text-[10px] text-faint">{g.done ? `（${wd}）` : "未開打"}</div>
                      </div>
                      <span className={scoreCls("home")}>{g.done ? g.home_score : ""}</span>
                      <TeamLogo code={g.home_team_code} name={g.home_team_name} size={26} />
                    </Link>
                  );
                })}
              </div>
            </section>

            {/* 對戰各隊 */}
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

            {/* 戰績分項：主客場與特殊情境戰績同一組卡片格 */}
            <section>
              <h2 className="mb-3 text-lg font-semibold">戰績分項</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Card teamColor={color} className="p-4">
                  <div className="mb-2 text-sm font-semibold text-ink">主客場</div>
                  <dl className="space-y-1.5">
                    <div className="flex items-center justify-between text-sm">
                      <dt className="text-muted">主場</dt>
                      <dd className="font-mono tabular-nums">{team.home_record ?? "—"}</dd>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <dt className="text-muted">客場</dt>
                      <dd className="font-mono tabular-nums">{team.away_record ?? "—"}</dd>
                    </div>
                  </dl>
                </Card>
                {sp && GROUPS.map((grp) => (
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
          </div>
        )});

        // ── 現役陣容（僅現役；球員 + 教練）──
        if (team && (rst.first_batters.length > 0 || rst.first_pitchers.length > 0 || rst.farm.length > 0 || coaches.length > 0)) {
          pageTabs.push({ label: "現役陣容", content: (
            <div className="space-y-8">
              {(rst.first_batters.length > 0 || rst.first_pitchers.length > 0 || rst.farm.length > 0) && (
                <section>
                  <h2 className="mb-1 text-lg font-semibold">現役球員</h2>
                  <p className="mb-3 text-[11px] text-faint">本季登錄名單；一軍取自當季成績、二軍取自二軍逐場。點擊看個人頁。</p>
                  <div className="space-y-4">
                    <RosterChips label="一軍打者" players={rst.first_batters} color={color} />
                    <RosterChips label="一軍投手" players={rst.first_pitchers} color={color} />
                    <RosterChips label="二軍" players={rst.farm} color={color} dim />
                  </div>
                </section>
              )}
              <CoachGrid coaches={coaches} color={color} />
            </div>
          )});
        }

        // ── 歷屆人物（歷代球員 + 退休背號 + 歷任總教練）──
        if (roster.batters.length > 0 || roster.pitchers.length > 0 || managers.length > 0) {
          pageTabs.push({ label: "歷屆成員", content: (
            <div className="space-y-8">
              {/* 歷代成員（打者/投手/教練收內層頁籤）*/}
              {(roster.batters.length > 0 || roster.pitchers.length > 0 || managers.length > 0) && (
                <section>
                  <h2 className="mb-1 text-lg font-semibold">歷代成員</h2>
                  <p className="mb-3 text-[11px] text-faint">曾效力此球團（含前身）之球員與教練，依生涯出賽數／任期排序。</p>
                  {(() => {
                    const tabs = [] as { label: string; content: React.ReactNode }[];
                    if (roster.batters.length) tabs.push({ label: `打者 (${roster.batters.length})`, content: (
                      <RosterTable rows={roster.batters.map((p) => ({
                        id: p.player_id, name: p.name, active: p.active, span: `${p.from}–${p.to}`,
                        a: `${p.g} 場`, b: `${p.h} 安 ${p.hr} 轟` }))} cols={["球員", "年代", "出賽", "打擊"]} />
                    ) });
                    if (roster.pitchers.length) tabs.push({ label: `投手 (${roster.pitchers.length})`, content: (
                      <RosterTable rows={roster.pitchers.map((p) => ({
                        id: p.player_id, name: p.name, active: p.active, span: `${p.from}–${p.to}`,
                        a: `${p.g} 場`, b: `${p.w}勝 ${p.sv}救` }))} cols={["球員", "年代", "出賽", "投球"]} />
                    ) });
                    if (managers.length) tabs.push({ label: `教練 (${managers.length})`, content: (
                      <ManagersTable managers={managers} />
                    ) });
                    return <Tabs items={tabs} />;
                  })()}
                </section>
              )}
            </div>
          )});
        }

        // ── 隊史（franchise 全史 + 沿革）──
        if (eras.eras.length >= 1) {
          pageTabs.push({ label: "隊史", content: (
            <div className="space-y-8">
              <section>
                <h2 className="mb-1 text-lg font-semibold">隊史紀錄</h2>
                <p className="mb-3 text-[11px] text-faint">含改名/轉賣前身的 franchise 全史（一軍例行賽）。</p>
                {eras.championship_count > 0 && (
                  <div className="mb-3 rounded-lg border border-line bg-surface p-3">
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-sm font-semibold text-ink">🏆 隊史總冠軍</span>
                      <span className="font-mono text-xl font-bold tabular-nums text-accent">{eras.championship_count}</span>
                      <span className="text-xs text-muted">座</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {eras.championships.map((y) => (
                        <span key={y} className="rounded bg-accent/10 px-2 py-0.5 font-mono text-xs tabular-nums text-accent">{y}</span>
                      ))}
                    </div>
                  </div>
                )}
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

              <RetiredNumbers retired={retired} color={color} />

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
            </div>
          )});
        }

        return <Tabs items={pageTabs} />;
      })()}

    </div>
  );
}
