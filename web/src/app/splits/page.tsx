"use client";

import { useEffect, useMemo, useState } from "react";
import { detail, type Roster, type RosterPlayer, type StatRow } from "@/lib/client";

type Role = "batting" | "pitching";

const n = (v: number | string | null) => (v === null || v === undefined ? "—" : String(v));
const f3 = (v: number | string | null) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(3).replace(/^0\./, ".");
const ip = (r: StatRow) =>
  r.inning_pitched_cnt === null ? "—" : `${r.inning_pitched_cnt}.${r.inning_pitched_div3 ?? 0}`;

// [欄名, 中文說明(hover), 取值]
const BAT_COLS: [string, string, (r: StatRow) => string][] = [
  ["PA", "打席", (r) => n(r.plate_appearances)],
  ["AB", "打數", (r) => n(r.at_bats)],
  ["H", "安打", (r) => n(r.hits)],
  ["HR", "全壘打", (r) => n(r.home_runs)],
  ["RBI", "打點", (r) => n(r.rbi)],
  ["BB", "四壞球（保送）", (r) => n(r.bb)],
  ["SO", "被三振", (r) => n(r.so)],
  ["AVG", "打擊率 = 安打 ÷ 打數", (r) => f3(r.avg)],
  ["OBP", "上壘率", (r) => f3(r.obp)],
  ["SLG", "長打率 = 壘打數 ÷ 打數", (r) => f3(r.slg)],
  ["OPS", "整體攻擊指數 = 上壘率＋長打率", (r) => f3(r.ops)],
];

const PIT_COLS: [string, string, (r: StatRow) => string][] = [
  ["先發", "先發場數", (r) => n(r.starts)],
  ["W", "勝場", (r) => n(r.wins)],
  ["L", "敗場", (r) => n(r.loses)],
  ["IP", "投球局數（.1=⅓局、.2=⅔局）", ip],
  ["PA", "面對打席", (r) => n(r.plate_appearances)],
  ["球數", "投球數", (r) => n(r.pitch_cnt)],
  ["H", "被安打", (r) => n(r.hits)],
  ["HR", "被全壘打", (r) => n(r.home_runs)],
  ["BB", "投出四壞球", (r) => n(r.bb)],
  ["SO", "奪三振", (r) => n(r.so)],
  ["失分", "失分（含非自責）", (r) => n(r.runs)],
  ["自責", "自責分：計入防禦率的失分", (r) => n(r.earned_runs)],
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
    <div className="inline-flex gap-1 rounded-lg bg-surface-2 p-1">
      {options.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className={`rounded-md px-3 py-1 text-sm transition ${
            value === o.v ? "bg-ink text-white" : "text-muted hover:text-white"
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
    // 從個人頁帶入 ?id=&role= 預選
    const q = new URLSearchParams(window.location.search);
    const qrole = q.get("role");
    const qid = q.get("id");
    if (qrole === "batting" || qrole === "pitching") setRole(qrole);
    if (qid) setPid(qid);
  }, []);

  // 使用者切換 role 時清空已選球員（程式從 URL 設定的不受影響）
  const switchRole = (r: Role) => {
    setRole(r);
    setPid("");
    setRows(null);
  };

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
        <p className="mt-2 text-sm text-muted">
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
          onChange={switchRole}
        />
        {roster && (
          <select
            value={pid}
            onChange={(e) => setPid(e.target.value)}
            className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-ink"
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

      {loading && <p className="text-sm text-faint">查詢中…</p>}

      {rows && !loading && (
        rows.length === 0 ? (
          <p className="rounded-xl border border-line bg-surface p-4 text-sm text-muted">
            {pName ?? "該選手"} 在此範圍無分項資料。
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-muted">
                <tr>
                  <th className="whitespace-nowrap px-2.5 py-3 font-medium">分項</th>
                  {cols.map(([h, tip]) => (
                    <th
                      key={h}
                      title={tip}
                      className="cursor-help whitespace-nowrap px-2.5 py-3 font-medium underline decoration-line decoration-dotted underline-offset-4"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {rows.map((r, i) => (
                  <tr key={i} className="border-t border-line hover:bg-surface-2">
                    <td className="whitespace-nowrap px-2.5 py-2.5 font-sans text-ink">
                      {n(r.item_name)}
                    </td>
                    {cols.map(([h, , get]) => (
                      <td key={h} className="px-2.5 py-2.5">
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
