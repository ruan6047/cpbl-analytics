"use client";

import { useEffect, useMemo, useState } from "react";
import { detail, type Roster, type RosterPlayer, type StatRow } from "@/lib/client";

type Role = "batting" | "pitching";

const n = (v: number | string | null) => (v === null || v === undefined ? "—" : String(v));
const f3 = (v: number | string | null) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(3).replace(/^0\./, ".");
const ip = (r: StatRow) =>
  r.inning_pitched_cnt === null ? "—" : `${r.inning_pitched_cnt}.${r.inning_pitched_div3 ?? 0}`;

const BAT_COLS: [string, (r: StatRow) => string][] = [
  ["PA", (r) => n(r.plate_appearances)],
  ["AB", (r) => n(r.at_bats)],
  ["H", (r) => n(r.hits)],
  ["HR", (r) => n(r.home_runs)],
  ["RBI", (r) => n(r.rbi)],
  ["BB", (r) => n(r.bb)],
  ["SO", (r) => n(r.so)],
  ["AVG", (r) => f3(r.avg)],
  ["OBP", (r) => f3(r.obp)],
  ["SLG", (r) => f3(r.slg)],
  ["OPS", (r) => f3(r.ops)],
];

const PIT_COLS: [string, (r: StatRow) => string][] = [
  ["先發", (r) => n(r.starts)],
  ["W", (r) => n(r.wins)],
  ["L", (r) => n(r.loses)],
  ["IP", ip],
  ["PA", (r) => n(r.plate_appearances)],
  ["球數", (r) => n(r.pitch_cnt)],
  ["H", (r) => n(r.hits)],
  ["HR", (r) => n(r.home_runs)],
  ["BB", (r) => n(r.bb)],
  ["SO", (r) => n(r.so)],
  ["失分", (r) => n(r.runs)],
  ["自責", (r) => n(r.earned_runs)],
];

function Toggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { v: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex gap-1 rounded-lg bg-white/5 p-1">
      {options.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className={`rounded-md px-3 py-1 text-sm transition ${
            value === o.v ? "bg-emerald-500 text-black" : "text-white/60 hover:text-white"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function SplitsPage() {
  const [roster, setRoster] = useState<Roster | null>(null);
  const [role, setRole] = useState<Role>("batting");
  const [pid, setPid] = useState("");
  const [scope, setScope] = useState<"season" | "career">("season");
  const [kind, setKind] = useState<"A" | "C" | "E">("A");
  const [rows, setRows] = useState<StatRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    detail.roster().then(setRoster).catch(() => setRoster(null));
  }, []);

  // 切換 role 時清空選擇
  useEffect(() => {
    setPid("");
    setRows(null);
  }, [role]);

  const players: RosterPlayer[] = useMemo(
    () => (roster ? (role === "batting" ? roster.batters : roster.pitchers) : []),
    [roster, role],
  );

  useEffect(() => {
    if (!pid) {
      setRows(null);
      return;
    }
    const year = scope === "season" ? 2026 : 9999;
    const k = scope === "season" ? "A" : kind;
    setLoading(true);
    detail
      .splits(pid, role, year, k)
      .then((d) => setRows(d.items))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [pid, role, scope, kind]);

  const cols = role === "batting" ? BAT_COLS : PIT_COLS;
  const pName = players.find((p) => p.id === pid)?.name;

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">分項成績</h1>
        <p className="mt-2 text-sm text-white/50">
          主客場 / 左右投打 / 本土外籍 / 壘上跑者 / 出局數 / 局數 / 比分 / 月份 / 球場 / 棒次。
          本季僅一軍例行賽；生涯累計含季後賽。資料來源 cpbl.com.tw。
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Toggle<Role>
          options={[
            { v: "batting", label: "打者" },
            { v: "pitching", label: "投手" },
          ]}
          value={role}
          onChange={setRole}
        />
        {roster && (
          <select
            value={pid}
            onChange={(e) => setPid(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-emerald-400"
          >
            <option value="">— 選擇{role === "batting" ? "打者" : "投手"} —</option>
            {players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}（{p.team ?? "?"}）
              </option>
            ))}
          </select>
        )}
        <Toggle
          options={[
            { v: "season", label: "本季" },
            { v: "career", label: "生涯" },
          ]}
          value={scope}
          onChange={setScope}
        />
        {scope === "career" && (
          <Toggle
            options={[
              { v: "A", label: "例行賽" },
              { v: "C", label: "總冠軍" },
              { v: "E", label: "季後賽" },
            ]}
            value={kind}
            onChange={setKind}
          />
        )}
      </div>

      {loading && <p className="text-sm text-white/40">查詢中…</p>}

      {rows && !loading && (
        rows.length === 0 ? (
          <p className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-white/50">
            {pName ?? "該選手"} 在此範圍無分項資料。
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-left text-white/50">
                <tr>
                  <th className="whitespace-nowrap px-2.5 py-3 font-medium">分項</th>
                  {cols.map(([h]) => (
                    <th key={h} className="whitespace-nowrap px-2.5 py-3 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {rows.map((r, i) => (
                  <tr key={i} className="border-t border-white/5 hover:bg-white/5">
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-sans text-white/80">
                      {n(r.item_name)}
                    </td>
                    {cols.map(([h, get], j) => (
                      <td
                        key={h}
                        className={`px-2.5 py-2.5 ${j >= cols.length - 4 && role === "batting" ? "" : ""}`}
                      >
                        {get(r)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
