"use client";

import { useEffect, useState } from "react";
import {
  detail,
  KIND_LABEL,
  type Roster,
  type RosterPlayer,
  type StatRow,
  type VsTeamData,
} from "@/lib/client";

const f3 = (v: number | string | null) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(3).replace(/^0/, "");
const n = (v: number | string | null) => (v === null || v === undefined ? "—" : String(v));

function Picker({
  label,
  players,
  value,
  onChange,
}: {
  label: string;
  players: RosterPlayer[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-1 flex-col gap-1.5">
      <span className="text-xs text-white/50">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-emerald-400"
      >
        <option value="">— 請選擇 —</option>
        {players.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}（{p.team ?? "?"}）
          </option>
        ))}
      </select>
    </label>
  );
}

// 投打對決：一個賽別一張卡
function MatchupCard({ row }: { row: StatRow }) {
  const cells: [string, string][] = [
    ["打席", n(row.plate_appearances)],
    ["打數", n(row.at_bats)],
    ["安打", n(row.hits)],
    ["全壘打", n(row.home_runs)],
    ["四壞", n(row.bb)],
    ["三振", n(row.so)],
    ["打擊率", f3(row.avg)],
    ["上壘率", f3(row.obp)],
    ["長打率", f3(row.slg)],
    ["OPS", f3(row.ops)],
  ];
  const adv: [string, string][] = [
    ["揮空%", row.whiff_pct === null ? "—" : `${Number(row.whiff_pct).toFixed(1)}%`],
    ["揮棒%", row.swing_pct === null ? "—" : `${Number(row.swing_pct).toFixed(1)}%`],
    ["滾飛比 GB%", row.gb_pct === null ? "—" : `${Number(row.gb_pct).toFixed(1)}%`],
  ];
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 text-sm font-medium text-emerald-400">
        {KIND_LABEL[String(row.kind_code)] ?? row.kind_code} · 生涯累計
      </div>
      <div className="grid grid-cols-5 gap-y-3 font-mono tabular-nums sm:grid-cols-10">
        {cells.map(([k, v]) => (
          <div key={k}>
            <div className="text-[11px] font-sans text-white/40">{k}</div>
            <div className="text-base">{v}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-6 border-t border-white/5 pt-3 font-mono tabular-nums">
        {adv.map(([k, v]) => (
          <div key={k}>
            <div className="text-[11px] font-sans text-white/40">{k}</div>
            <div className="text-sm text-white/70">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function VsTeamTable({ data, role }: { data: VsTeamData | null; role: "batting" | "pitching" }) {
  if (!data) return null;
  if (data.items.length === 0)
    return <p className="text-sm text-white/40">尚無對戰各隊資料（投手資料爬取中…）。</p>;

  const head =
    role === "batting"
      ? ["對手", "G", "PA", "AB", "H", "HR", "RBI", "BB", "SO", "AVG", "OBP", "SLG", "OPS"]
      : ["對手", "G", "先發", "W", "L", "SV", "IP", "ERA", "WHIP", "H", "HR", "BB", "SO"];

  return (
    <div className="overflow-x-auto rounded-xl border border-white/10">
      <table className="w-full text-sm">
        <thead className="bg-white/5 text-left text-white/50">
          <tr>
            {head.map((h) => (
              <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {data.items.map((r, i) => (
            <tr key={i} className="border-t border-white/5 hover:bg-white/5">
              <td className="whitespace-nowrap px-2 py-2 font-sans">{n(r.fight_team_name)}</td>
              {role === "batting" ? (
                <>
                  <td className="px-2 py-2 text-white/50">{n(r.total_games)}</td>
                  <td className="px-2 py-2">{n(r.plate_appearances)}</td>
                  <td className="px-2 py-2 text-white/50">{n(r.at_bats)}</td>
                  <td className="px-2 py-2">{n(r.hits)}</td>
                  <td className="px-2 py-2">{n(r.home_runs)}</td>
                  <td className="px-2 py-2">{n(r.rbi)}</td>
                  <td className="px-2 py-2 text-white/50">{n(r.bb)}</td>
                  <td className="px-2 py-2 text-white/50">{n(r.so)}</td>
                  <td className="px-2 py-2">{f3(r.avg)}</td>
                  <td className="px-2 py-2">{f3(r.obp)}</td>
                  <td className="px-2 py-2">{f3(r.slg)}</td>
                  <td className="px-2 py-2 text-emerald-400">{f3(r.ops)}</td>
                </>
              ) : (
                <>
                  <td className="px-2 py-2 text-white/50">{n(r.total_games)}</td>
                  <td className="px-2 py-2 text-white/50">{n(r.starts)}</td>
                  <td className="px-2 py-2">{n(r.wins)}</td>
                  <td className="px-2 py-2">{n(r.loses)}</td>
                  <td className="px-2 py-2">{n(r.save_ok)}</td>
                  <td className="px-2 py-2">{n(r.inning_pitched_cnt)}</td>
                  <td className="px-2 py-2 text-emerald-400">{f3(r.era)}</td>
                  <td className="px-2 py-2">{f3(r.whip)}</td>
                  <td className="px-2 py-2 text-white/50">{n(r.hits)}</td>
                  <td className="px-2 py-2 text-white/50">{n(r.home_runs)}</td>
                  <td className="px-2 py-2 text-white/50">{n(r.bb)}</td>
                  <td className="px-2 py-2">{n(r.so)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MatchupsPage() {
  const [roster, setRoster] = useState<Roster | null>(null);
  const [hitter, setHitter] = useState("");
  const [pitcher, setPitcher] = useState("");
  const [items, setItems] = useState<StatRow[] | null>(null);
  const [bTeam, setBTeam] = useState<VsTeamData | null>(null);
  const [pTeam, setPTeam] = useState<VsTeamData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    detail.roster().then(setRoster).catch(() => setRoster(null));
  }, []);

  useEffect(() => {
    if (!hitter || !pitcher) {
      setItems(null);
      return;
    }
    setLoading(true);
    Promise.all([
      detail.matchups(hitter, pitcher),
      detail.vsTeam(hitter, "batting"),
      detail.vsTeam(pitcher, "pitching"),
    ])
      .then(([m, bt, pt]) => {
        setItems(m.items);
        setBTeam(bt);
        setPTeam(pt);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [hitter, pitcher]);

  const hName = roster?.batters.find((b) => b.id === hitter)?.name;
  const pName = roster?.pitchers.find((p) => p.id === pitcher)?.name;

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">投打對決</h1>
        <p className="mt-2 text-sm text-white/50">
          打者 vs 投手生涯對戰（含進階球種比例），以及雙方對戰各隊成績。資料來源 cpbl.com.tw。
        </p>
      </header>

      {!roster ? (
        <p className="text-sm text-white/40">載入名單中…</p>
      ) : (
        <div className="mb-6 flex flex-col gap-3 sm:flex-row">
          <Picker label="打者" players={roster.batters} value={hitter} onChange={setHitter} />
          <Picker label="投手" players={roster.pitchers} value={pitcher} onChange={setPitcher} />
        </div>
      )}

      {loading && <p className="text-sm text-white/40">查詢中…</p>}

      {items && !loading && (
        <section className="space-y-4">
          {items.length === 0 ? (
            <p className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-white/50">
              {hName ?? "該打者"} 與 {pName ?? "該投手"} 生涯無對戰紀錄（或投手非本季登錄）。
            </p>
          ) : (
            <>
              <h2 className="text-lg font-semibold">
                {hName} <span className="text-white/30">vs</span> {pName}
              </h2>
              {items.map((r, i) => (
                <MatchupCard key={i} row={r} />
              ))}
            </>
          )}
        </section>
      )}

      {hitter && pitcher && !loading && (
        <section className="mt-8 grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-medium text-white/70">{hName}：對戰各隊（本季打擊）</h3>
            <VsTeamTable data={bTeam} role="batting" />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium text-white/70">{pName}：對戰各隊（本季投球）</h3>
            <VsTeamTable data={pTeam} role="pitching" />
          </div>
        </section>
      )}
    </div>
  );
}
