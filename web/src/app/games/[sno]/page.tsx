"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { detail, type StatRow } from "@/lib/client";
import { fmtIPParts } from "@/lib/format";
import GameBoard, { type Live } from "@/components/game-board";

const n = (v: number | string | null) => (v === null || v === undefined ? "" : Number(v));

const i0 = (v: number | string | null | undefined) => (v === null || v === undefined ? "—" : String(v));
const ipTxt = (r: StatRow) => fmtIPParts(r.inning_pitched_cnt as number | null, r.inning_pitched_div3 as number | null);

// 打者亮點標記：滿貫/猛打賞(3安+)/致勝打點/MVP
function batterMark(r: StatRow): string {
  const t: string[] = [];
  if (n(r.grand_slam) as number) t.push("滿貫");
  if ((n(r.hits) as number) >= 3) t.push("猛打賞");
  if (n(r.gw_rbi) as number) t.push("致勝打點");
  if (r.is_mvp) t.push("MVP");
  return t.join("·");
}

function BoxBatting({ rows, team }: { rows: StatRow[]; team: string }) {
  const cols: [string, (r: StatRow) => string][] = [
    ["AB", (r) => i0(r.at_bats)], ["R", (r) => i0(r.runs)], ["H", (r) => i0(r.hits)],
    ["2B", (r) => i0(r.doubles)], ["3B", (r) => i0(r.triples)], ["HR", (r) => i0(r.home_runs)],
    ["打點", (r) => i0(r.rbi)], ["BB", (r) => i0(r.bb)], ["SO", (r) => i0(r.so)], ["SB", (r) => i0(r.sb)],
  ];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr><th className="px-3 py-2 font-medium">{team}　打者</th>
            {cols.map(([h]) => <th key={h} className="px-2 py-2 text-right font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r, i) => {
            const mark = batterMark(r);
            return (
              <tr key={i} className="border-t border-line">
                <td className="whitespace-nowrap px-3 py-1.5 font-sans text-ink">{String(r.hitter_name ?? "")}
                  <span className="ml-1 text-[10px] text-faint">{String(r.role_type ?? "")}</span>
                  {mark && <span className="ml-1 text-[10px] font-semibold text-cpbl">{mark}</span>}</td>
                {cols.map(([h, f]) => <td key={h} className="px-2 py-1.5 text-right">{f(r)}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// 投手結果標記：勝/敗 + S(救援) + 完投/完封
function pitcherMark(r: StatRow, closerId: string): string {
  const t: string[] = [];
  const gr = String(r.game_result ?? "");
  if (gr === "勝" || gr === "敗") t.push(gr);
  if (closerId && String(r.pitcher_acnt) === closerId) t.push("S");
  if (r.is_complete_game) t.push(r.is_shutout ? "完封" : "完投");
  return t.join("·");
}

function BoxPitching({ rows, team, closerId }: { rows: StatRow[]; team: string; closerId: string }) {
  const cols: [string, (r: StatRow) => string][] = [
    ["IP", ipTxt], ["H", (r) => i0(r.hits)], ["R", (r) => i0(r.runs)], ["ER", (r) => i0(r.earned_runs)],
    ["BB", (r) => i0(r.bb)], ["SO", (r) => i0(r.so)], ["被HR", (r) => i0(r.home_runs)],
    ["球數", (r) => i0(r.pitch_cnt)], ["最快", (r) => (r.max_speed ? `${r.max_speed}` : "—")],
  ];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr><th className="px-3 py-2 font-medium">{team}　投手</th>
            {cols.map(([h]) => <th key={h} className="px-2 py-2 text-right font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r, i) => {
            const mark = pitcherMark(r, closerId);
            return (
              <tr key={i} className="border-t border-line">
                <td className="whitespace-nowrap px-3 py-1.5 font-sans text-ink">{String(r.pitcher_name ?? "")}
                  {mark && <span className="ml-1 text-[10px] font-semibold text-accent">{mark}</span>}</td>
                {cols.map(([h, f]) => <td key={h} className="px-2 py-1.5 text-right">{f(r)}</td>)}
              </tr>
            );
          })}
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

      {g.delay_kind && (() => {
        const md = (s: unknown) => {
          const p = String(s ?? "").slice(5).split("-");
          return p.length === 2 ? `${+p[0]}/${+p[1]}` : "";
        };
        const orig = md(g.orig_date);
        const played = md(g.game_date);
        const done = n(g.present_status) === 1 && ((n(g.home_score) as number) + (n(g.away_score) as number)) > 0;
        const note = g.delay_kind === "保留"
          ? `因雨保留比賽　原 ${orig} 開賽${done ? `，${played} 續賽完成` : "，擇期續賽"}`
          : `因雨延賽　原定 ${orig}${done && played !== orig ? `，${played} 補賽` : "，擇期補賽"}`;
        return (
          <div className="mb-6 flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-900">
            <span>☔</span><span className="font-medium">{note}</span>
          </div>
        );
      })()}

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

      {(() => {
        // 本場焦點：滿貫/多響砲/猛打賞/完投完封/最速球
        const hi: string[] = [];
        for (const r of data.batting) {
          const nm = String(r.hitter_name ?? "");
          const hr = n(r.home_runs) as number;
          if (n(r.grand_slam) as number) hi.push(`${nm} 滿貫砲`);
          else if (hr >= 2) hi.push(`${nm} ${hr} 響砲`);
          if ((n(r.hits) as number) >= 4) hi.push(`${nm} ${r.hits} 安猛打賞`);
        }
        for (const r of data.pitching) {
          const nm = String(r.pitcher_name ?? "");
          if (r.is_shutout) hi.push(`${nm} 完封`);
          else if (r.is_complete_game) hi.push(`${nm} 完投`);
        }
        const maxSp = Math.max(0, ...data.pitching.map((r) => (n(r.max_speed) as number) || 0));
        if (maxSp) hi.push(`最速球 ${maxSp} km/h`);
        return hi.length ? (
          <section className="mb-6">
            <h2 className="mb-2 text-lg font-semibold">本場焦點</h2>
            <div className="flex flex-wrap gap-2">
              {hi.map((t, i) => (
                <span key={i} className="rounded-full bg-cpbl/10 px-3 py-1 text-sm font-medium text-cpbl">{t}</span>
              ))}
            </div>
          </section>
        ) : null;
      })()}

      {data.detail && (() => {
        const d = data.detail;
        const umps = [["主審", d.head_umpire], ["一壘", d.first_umpire], ["二壘", d.second_umpire],
          ["三壘", d.third_umpire], ["左審", d.left_umpire], ["右審", d.right_umpire]]
          .filter(([, v]) => v).map(([l, v]) => `${l} ${v}`).join("、");
        const info: string[] = [];
        if (d.attendance) info.push(`觀眾 ${Number(d.attendance).toLocaleString()} 人`);
        if (d.game_time) info.push(`時長 ${String(d.game_time)}`);
        return (info.length || umps) ? (
          <div className="mb-6 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-muted">
            {info.length > 0 && <span className="mr-4">{info.join("　·　")}</span>}
            {umps && <span>裁判：{umps}</span>}
          </div>
        ) : null;
      })()}

      {data.batting.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold">Box Score</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            <BoxBatting rows={data.batting.filter((r) => String(r.visiting_home_type) === "1")} team={String(g.away_team_name)} />
            <BoxBatting rows={data.batting.filter((r) => String(r.visiting_home_type) === "2")} team={String(g.home_team_name)} />
            <BoxPitching rows={data.pitching.filter((r) => String(r.visiting_home_type) === "1")} team={String(g.away_team_name)} closerId={String(g.closer_id ?? "")} />
            <BoxPitching rows={data.pitching.filter((r) => String(r.visiting_home_type) === "2")} team={String(g.home_team_name)} closerId={String(g.closer_id ?? "")} />
          </div>
        </section>
      )}
    </div>
  );
}
