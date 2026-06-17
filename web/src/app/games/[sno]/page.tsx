"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { detail, type StatRow } from "@/lib/client";

const n = (v: number | string | null) => (v === null || v === undefined ? "" : Number(v));

type Live = { game: StatRow | null; scoreboard: StatRow[]; livelog: StatRow[] };

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

function PlayByPlay({ log }: { log: StatRow[] }) {
  // 依「局 × 上下半」分組
  const groups: { inning: number; half: string; events: StatRow[] }[] = [];
  for (const e of log) {
    const last = groups[groups.length - 1];
    if (!last || last.inning !== Number(e.inning_seq) || last.half !== String(e.visiting_home_type)) {
      groups.push({ inning: Number(e.inning_seq), half: String(e.visiting_home_type), events: [e] });
    } else {
      last.events.push(e);
    }
  }

  return (
    <div className="space-y-5">
      {groups.map((g, gi) => (
        <div key={gi} className="rounded-xl border border-line bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold text-accent">
            {g.inning} 局{g.half === "1" ? "上" : "下"}
          </h3>
          <div className="space-y-0.5">
            {g.events.map((e, i) => {
              const prev = g.events[i - 1];
              const newBatter = !prev || prev.hitter_acnt !== e.hitter_acnt;
              const isScore = Boolean(e.is_score);
              const content = String(e.content ?? "");
              const isPitch = content.length <= 8; // 粗略：短句多為單球描述
              return (
                <div key={i}>
                  {newBatter && e.hitter_name && (
                    <div className="mt-2.5 text-sm font-medium text-ink">
                      🏏 {String(e.hitter_name)}
                      <span className="ml-2 text-xs text-faint">投：{String(e.pitcher_name ?? "")}</span>
                    </div>
                  )}
                  <div
                    className={`pl-5 ${
                      isScore ? "text-accent" : isPitch ? "text-xs text-faint" : "text-sm text-ink"
                    }`}
                  >
                    {content}
                    {isScore && (
                      <span className="ml-2 font-mono text-xs">
                        ({n(e.visiting_score)}-{n(e.home_score)})
                      </span>
                    )}
                  </div>
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

  useEffect(() => {
    detail.gameLive(Number(sno), kind).then((d) => setData(d as Live)).catch(() => setErr(true));
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

      <section className="mb-8">
        <h2 className="mb-2 text-lg font-semibold">逐局比分</h2>
        <Scoreboard sb={data.scoreboard} game={g} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">逐打席賽況</h2>
        {data.livelog.length === 0 ? (
          <p className="text-sm text-faint">無逐打席資料。</p>
        ) : (
          <PlayByPlay log={data.livelog} />
        )}
      </section>
    </div>
  );
}
