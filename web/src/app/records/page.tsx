import Link from "next/link";
import { api } from "@/lib/api";
import { contrastText, eraBadge, nameMeta } from "@/lib/teams";

function PlayerLink({ pid, name }: { pid?: string; name: string }) {
  return pid ? <Link href={`/players/${pid}`} className="text-accent hover:underline">{name}</Link> : <>{name}</>;
}

export const dynamic = "force-dynamic";

const f3 = (v: number | string | null) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));

function TeamTag({ name }: { name: string }) {
  const m = nameMeta(name);
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-flex h-4 w-4 items-center justify-center rounded text-[9px] font-extrabold"
        style={{ background: m.color, color: contrastText(m.color) }}>{m.letter}</span>
      {name}
    </span>
  );
}

type GameRec = { year: number; date: string; home: string; away: string; hs: number; as: number } | null;

function GameCard({ label, rec, hint }: { label: string; rec: GameRec; hint: string }) {
  if (!rec) return null;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-[11px] font-medium text-muted">{label}</div>
      <div className="mt-2 flex items-center justify-between text-sm">
        <TeamTag name={rec.away} /><span className="font-mono text-lg font-bold tabular-nums">{rec.as}</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-sm">
        <TeamTag name={rec.home} /><span className="font-mono text-lg font-bold tabular-nums">{rec.hs}</span>
      </div>
      <div className="mt-2 text-[11px] text-faint">{rec.date}　{hint}</div>
    </div>
  );
}

function SeasonTile({ label, rec, fmt }: { label: string; rec?: { name: string; pid: string; year: number; val: number | string }[]; fmt?: (v: number | string) => string }) {
  const r = rec?.[0];
  if (!r) return null;
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="text-[11px] text-muted">{label}</div>
      <div className="mt-0.5 font-mono text-xl font-bold tabular-nums text-accent">{fmt ? fmt(r.val) : r.val}</div>
      <div className="mt-0.5 text-xs text-ink"><PlayerLink pid={r.pid} name={r.name} /><span className="ml-1 text-faint">{r.year}</span></div>
    </div>
  );
}

function LeaderList({ title, rows, fmt }: { title: string; rows?: { name: string; pid: string; val: number }[]; fmt?: (v: number) => string }) {
  if (!rows?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-2 text-sm font-semibold text-ink">{title}</div>
      <ol className="space-y-1.5 text-sm">
        {rows.map((r, i) => (
          <li key={r.name} className="flex items-center justify-between">
            <span><span className="mr-2 inline-block w-4 text-right font-mono text-faint">{i + 1}</span><PlayerLink pid={r.pid} name={r.name} /></span>
            <span className="font-mono font-semibold tabular-nums">{fmt ? fmt(r.val) : r.val}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function FranchiseCard({ fr }: { fr: Awaited<ReturnType<typeof api.franchises>>["items"][number] }) {
  const head = eraBadge(fr.name, fr.code);
  return (
    <Link href={`/teams/${fr.code}`}
      className="block rounded-xl border border-line bg-surface p-3.5 transition hover:border-accent hover:shadow-sm">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-extrabold"
          style={{ background: head.color, color: contrastText(head.color) }}>{head.letter}</span>
        <span className="font-semibold text-ink">{fr.name}</span>
        {!fr.active && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">已解散</span>}
      </div>
      <div className="mt-1.5 font-mono text-[11px] tabular-nums text-muted">
        {fr.from}–{fr.to}　{fr.w}-{fr.t}-{fr.l}　勝率 {f3(fr.win_pct)}
      </div>
      {fr.eras.length > 1 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {fr.eras.map((e) => {
            const b = eraBadge(e.name, e.code);
            return (
              <span key={`${e.code}-${e.from}`}
                className="inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px]"
                style={{ background: `${b.color}1a`, color: b.color }}>
                {e.name}
              </span>
            );
          })}
        </div>
      )}
    </Link>
  );
}

export default async function RecordsPage() {
  const [d, fr] = await Promise.all([api.records(), api.franchises()]);
  const activeFr = fr.items.filter((f) => f.active);
  const goneFr = fr.items.filter((f) => !f.active);
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">歷史紀錄室</h1>
        <p className="mt-2 text-sm text-muted">
          中華職棒一軍歷史之最。比賽紀錄含全史（1990 起）；單季/生涯以官方歷年彙總（1990–2024，近兩季另計）。
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-lg font-semibold">比賽紀錄</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <GameCard label="單場最大分差" rec={d.games.max_margin} hint={`分差 ${Math.abs((d.games.max_margin?.hs ?? 0) - (d.games.max_margin?.as ?? 0))}`} />
          <GameCard label="單隊單場最多得分" rec={d.games.max_team_runs} hint={`最多 ${Math.max(d.games.max_team_runs?.hs ?? 0, d.games.max_team_runs?.as ?? 0)} 分`} />
          <GameCard label="單場雙方最多得分" rec={d.games.max_combined} hint={`合計 ${(d.games.max_combined?.hs ?? 0) + (d.games.max_combined?.as ?? 0)} 分`} />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">單季之最</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <SeasonTile label="最多全壘打" rec={d.season_batting.hr} />
          <SeasonTile label="最高打擊率" rec={d.season_batting.avg} fmt={(v) => f3(v)} />
          <SeasonTile label="最多打點" rec={d.season_batting.rbi} />
          <SeasonTile label="最多盜壘" rec={d.season_batting.sb} />
          <SeasonTile label="最多勝投" rec={d.season_pitching.w} />
          <SeasonTile label="最多救援" rec={d.season_pitching.sv} />
          <SeasonTile label="最多三振" rec={d.season_pitching.so} />
        </div>
      </section>

      <section>
        <h2 className="mb-1 text-lg font-semibold">歷代球隊</h2>
        <p className="mb-3 text-[11px] text-faint">現役球團（含改名/轉賣沿革）與已解散球隊；點入看隊史沿革、各時期戰績與歷代球員。</p>
        <div className="mb-2 text-xs font-medium text-muted">現役</div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {activeFr.map((f) => <FranchiseCard key={f.code} fr={f} />)}
        </div>
        <div className="mb-2 mt-4 text-xs font-medium text-muted">已解散</div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {goneFr.map((f) => <FranchiseCard key={f.code} fr={f} />)}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">生涯排行</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <LeaderList title="生涯全壘打" rows={d.career_batting.hr} />
          <LeaderList title="生涯安打" rows={d.career_batting.h} />
          <LeaderList title="生涯打點" rows={d.career_batting.rbi} />
          <LeaderList title="生涯盜壘" rows={d.career_batting.sb} />
          <LeaderList title="生涯勝投" rows={d.career_pitching.w} />
          <LeaderList title="生涯救援" rows={d.career_pitching.sv} />
          <LeaderList title="生涯三振" rows={d.career_pitching.so} />
        </div>
      </section>
    </div>
  );
}
