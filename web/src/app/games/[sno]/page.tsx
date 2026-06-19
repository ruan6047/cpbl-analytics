"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { detail, type StatRow } from "@/lib/client";
import GameReplay from "@/components/game-replay";

const n = (v: number | string | null) => (v === null || v === undefined ? "" : Number(v));

type Live = {
  game: StatRow | null; scoreboard: StatRow[]; livelog: StatRow[];
  batting: StatRow[]; pitching: StatRow[]; people: Record<string, string>;
};

function Scoreboard({ sb, game }: { sb: StatRow[]; game: StatRow }) {
  const away = sb.filter((r) => String(r.visiting_home_type) === "1");
  const home = sb.filter((r) => String(r.visiting_home_type) === "2");
  const innings = [...new Set(sb.map((r) => Number(r.inning_seq)))].sort((a, b) => a - b);
  const cell = (rows: StatRow[], inn: number) =>
    rows.find((r) => Number(r.inning_seq) === inn)?.score_cnt ?? "";
  const tot = (rows: StatRow[], key: string) =>
    rows.reduce((s, r) => s + (Number(r[key]) || 0), 0);

  const row = (label: string, rows: StatRow[], score: number) => (
    <tr className="border-t border-line">
      <td className="whitespace-nowrap px-3 py-2 font-sans font-medium">{label}</td>
      {innings.map((inn) => (
        <td key={inn} className="px-2.5 py-2 text-center text-muted">{String(cell(rows, inn))}</td>
      ))}
      <td className="px-2.5 py-2 text-center font-semibold text-accent">{score}</td>
      <td className="px-2.5 py-2 text-center text-muted">{tot(rows, "hitting_cnt")}</td>
      <td className="px-2.5 py-2 text-center text-muted">{tot(rows, "error_cnt")}</td>
    </tr>
  );

  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full text-sm font-mono tabular-nums">
        <thead className="bg-surface-2 text-muted">
          <tr>
            <th className="px-3 py-2 text-left font-medium">隊伍</th>
            {innings.map((inn) => <th key={inn} className="px-2.5 py-2 font-medium">{inn}</th>)}
            <th className="px-2.5 py-2 font-medium">R</th>
            <th className="px-2.5 py-2 font-medium">H</th>
            <th className="px-2.5 py-2 font-medium">E</th>
          </tr>
        </thead>
        <tbody>
          {row(String(game.away_team_name), away, Number(game.away_score))}
          {row(String(game.home_team_name), home, Number(game.home_score))}
        </tbody>
      </table>
    </div>
  );
}

const i0 = (v: number | string | null | undefined) => (v === null || v === undefined ? "—" : String(v));
const ipTxt = (r: StatRow) => `${r.inning_pitched_cnt ?? 0}.${r.inning_pitched_div3 ?? 0}`;

function BoxBatting({ rows, team }: { rows: StatRow[]; team: string }) {
  const cols: [string, (r: StatRow) => string][] = [
    ["AB", (r) => i0(r.at_bats)], ["R", (r) => i0(r.runs)], ["H", (r) => i0(r.hits)],
    ["HR", (r) => i0(r.home_runs)], ["打點", (r) => i0(r.rbi)], ["BB", (r) => i0(r.bb)], ["SO", (r) => i0(r.so)],
  ];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr><th className="px-3 py-2 font-medium">{team}　打者</th>
            {cols.map(([h]) => <th key={h} className="px-2 py-2 text-right font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              <td className="whitespace-nowrap px-3 py-1.5 font-sans text-ink">{String(r.hitter_name ?? "")}
                <span className="ml-1 text-[10px] text-faint">{String(r.role_type ?? "")}</span></td>
              {cols.map(([h, f]) => <td key={h} className="px-2 py-1.5 text-right">{f(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BoxPitching({ rows, team }: { rows: StatRow[]; team: string }) {
  const cols: [string, (r: StatRow) => string][] = [
    ["IP", ipTxt], ["H", (r) => i0(r.hits)], ["R", (r) => i0(r.runs)], ["ER", (r) => i0(r.earned_runs)],
    ["BB", (r) => i0(r.bb)], ["SO", (r) => i0(r.so)], ["球數", (r) => i0(r.pitch_cnt)],
  ];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr><th className="px-3 py-2 font-medium">{team}　投手</th>
            {cols.map(([h]) => <th key={h} className="px-2 py-2 text-right font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              <td className="whitespace-nowrap px-3 py-1.5 font-sans text-ink">{String(r.pitcher_name ?? "")}
                {r.game_result && <span className="ml-1 text-[10px] text-accent">{String(r.game_result)}</span>}</td>
              {cols.map(([h, f]) => <td key={h} className="px-2 py-1.5 text-right">{f(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlayByPlay({ log, idx, setIdx }: { log: StatRow[]; idx: number; setIdx: (i: number) => void }) {
  // 依「局 × 上下半」分組，並保留每筆事件在 log 的全域索引
  const groups: { inning: number; half: string; events: { e: StatRow; gi: number }[] }[] = [];
  log.forEach((e, gi) => {
    const last = groups[groups.length - 1];
    if (!last || last.inning !== Number(e.inning_seq) || last.half !== String(e.visiting_home_type)) {
      groups.push({ inning: Number(e.inning_seq), half: String(e.visiting_home_type), events: [{ e, gi }] });
    } else {
      last.events.push({ e, gi });
    }
  });

  const activeRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [idx]);

  return (
    <div className="space-y-5">
      {groups.map((g, gIdx) => (
        <div key={gIdx} className="rounded-xl border border-line bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold text-accent">
            {g.inning} 局{g.half === "1" ? "上" : "下"}
          </h3>
          <div className="space-y-0.5">
            {g.events.map(({ e, gi }, i) => {
              const prev = g.events[i - 1]?.e;
              const newBatter = !prev || prev.hitter_acnt !== e.hitter_acnt;
              const isScore = Boolean(e.is_score);
              const content = String(e.content ?? "");
              const isPitch = content.length <= 8; // 粗略：短句多為單球描述
              const active = gi === idx;
              return (
                <div key={i}>
                  {newBatter && e.hitter_name && (
                    <div className="mt-2.5 text-sm font-medium text-ink">
                      🏏 {String(e.hitter_name)}
                      <span className="ml-2 text-xs text-faint">投：{String(e.pitcher_name ?? "")}</span>
                    </div>
                  )}
                  <button
                    ref={active ? activeRef : undefined}
                    onClick={() => setIdx(gi)}
                    className={`block w-full rounded pl-5 pr-2 py-0.5 text-left transition-colors hover:bg-surface-2 ${
                      active ? "bg-accent/10 ring-1 ring-accent/30" : ""
                    } ${isScore ? "text-accent" : isPitch ? "text-xs text-faint" : "text-sm text-ink"}`}
                  >
                    {content}
                    {isScore && (
                      <span className="ml-2 font-mono text-xs">
                        ({n(e.visiting_score)}-{n(e.home_score)})
                      </span>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function GameLivePage() {
  const { sno } = useParams<{ sno: string }>();
  const sp = useSearchParams();
  const kind = sp.get("kind") || "A";
  const [data, setData] = useState<Live | null>(null);
  const [err, setErr] = useState(false);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    detail.gameLive(Number(sno), kind)
      .then((d) => {
        const dd = d as Live;
        setData(dd);
        setIdx(Math.max(0, dd.livelog.length - 1)); // 預設停在終局，按播放從頭重播
      })
      .catch(() => setErr(true));
  }, [sno, kind]);

  if (err) return <p className="text-sm text-muted">載入賽況失敗。</p>;
  if (!data) return <p className="text-sm text-faint">載入中…</p>;
  if (!data.game) return <p className="text-sm text-muted">查無此場比賽。</p>;

  const g = data.game;
  return (
    <div>
      <Link href="/games" className="text-xs text-faint hover:text-accent">← 返回賽況列表</Link>
      <header className="mb-5 mt-2">
        <h1 className="text-2xl font-bold">
          {String(g.away_team_name)} <span className="font-mono">{n(g.away_score)}</span>
          <span className="mx-2 text-faint">@</span>
          {String(g.home_team_name)} <span className="font-mono">{n(g.home_score)}</span>
        </h1>
        <p className="mt-1 text-sm text-muted">
          {String(g.game_date ?? "")}　{String(g.venue ?? "")}
        </p>
      </header>

      {(() => {
        const ppl = data.people;
        const items: [string, string | undefined][] = [
          ["先發(客)", ppl[String(g.away_starter_id)]],
          ["先發(主)", ppl[String(g.home_starter_id)]],
          ["勝投", ppl[String(g.winning_pitcher_id)]],
          ["敗投", ppl[String(g.losing_pitcher_id)]],
          ["救援", ppl[String(g.closer_id)]],
          ["MVP", ppl[String(g.mvp_id)]],
        ].filter(([, v]) => v) as [string, string][];
        return items.length ? (
          <div className="mb-6 flex flex-wrap gap-x-5 gap-y-1.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
            {items.map(([l, v]) => (
              <span key={l}><span className="text-muted">{l}</span> <span className="font-medium text-ink">{v}</span></span>
            ))}
          </div>
        ) : null;
      })()}

      {data.livelog.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-2 text-lg font-semibold">賽況重播</h2>
          <GameReplay
            log={data.livelog} game={g}
            idx={idx} setIdx={setIdx}
            playing={playing} setPlaying={setPlaying}
            speed={speed} setSpeed={setSpeed}
          />
        </section>
      )}

      <section className="mb-8">
        <h2 className="mb-2 text-lg font-semibold">逐局比分</h2>
        <Scoreboard sb={data.scoreboard} game={g} />
      </section>

      {data.batting.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold">Box Score</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            <BoxBatting rows={data.batting.filter((r) => String(r.visiting_home_type) === "1")} team={String(g.away_team_name)} />
            <BoxBatting rows={data.batting.filter((r) => String(r.visiting_home_type) === "2")} team={String(g.home_team_name)} />
            <BoxPitching rows={data.pitching.filter((r) => String(r.visiting_home_type) === "1")} team={String(g.away_team_name)} />
            <BoxPitching rows={data.pitching.filter((r) => String(r.visiting_home_type) === "2")} team={String(g.home_team_name)} />
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold">逐打席賽況</h2>
        {data.livelog.length === 0 ? (
          <p className="text-sm text-faint">無逐打席資料。</p>
        ) : (
          <PlayByPlay log={data.livelog} idx={idx} setIdx={setIdx} />
        )}
      </section>
    </div>
  );
}
