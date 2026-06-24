"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { detail, type StatRow } from "@/lib/client";
import GameBoard, { type Live } from "@/components/game-board";

const n = (v: number | string | null) => (v === null || v === undefined ? "" : Number(v));

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

export default function GameLivePage() {
  const { sno } = useParams<{ sno: string }>();
  const sp = useSearchParams();
  const kind = sp.get("kind") || "A";
  const year = sp.get("year") ? Number(sp.get("year")) : undefined;
  const [data, setData] = useState<Live | null>(null);
  const [err, setErr] = useState(false);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    detail.gameLive(Number(sno), kind, year)
      .then((d) => {
        const dd = d as Live;
        setData(dd);
        setIdx(Math.max(0, dd.livelog.length - 1)); // 預設停在終局
      })
      .catch(() => setErr(true));
  }, [sno, kind, year]);

  if (err) return <p className="text-sm text-muted">載入賽況失敗。</p>;
  if (!data) return <p className="text-sm text-faint">載入中…</p>;
  if (!data.game) return <p className="text-sm text-muted">查無此場比賽。</p>;

  const g = data.game;
  return (
    <div>
      <Link href="/games" className="text-xs text-faint hover:text-accent">← 返回賽況列表</Link>

      {data.livelog.length > 0 ? (
        <section className="mb-8 mt-2">
          <GameBoard data={data} idx={idx} setIdx={setIdx} />
        </section>
      ) : (
        <header className="mb-6 mt-2">
          <h1 className="text-2xl font-bold">
            {String(g.away_team_name)} <span className="font-mono">{n(g.away_score)}</span>
            <span className="mx-2 text-faint">@</span>
            {String(g.home_team_name)} <span className="font-mono">{n(g.home_score)}</span>
          </h1>
          <p className="mt-1 text-sm text-muted">{String(g.game_date ?? "")}　{String(g.venue ?? "")}</p>
        </header>
      )}

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
    </div>
  );
}
