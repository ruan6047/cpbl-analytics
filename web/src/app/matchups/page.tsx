"use client";

import { useEffect, useMemo, useState } from "react";
import Leaderboard from "@/components/leaderboard";
import { Card } from "@/components/ui";
import { matchupCols } from "@/lib/cols";
import { detail, KIND_LABEL, type Roster, type RosterPlayer, type StatRow } from "@/lib/client";

type Role = "batting" | "pitching";

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
            value === o.v ? "bg-ink text-paper" : "text-muted hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function MatchupsPage() {
  const [roster, setRoster] = useState<Roster | null>(null);
  const [role, setRole] = useState<Role>("batting");
  const [pid, setPid] = useState("");
  const [kind, setKind] = useState<"A" | "C" | "E">("A");
  const [rows, setRows] = useState<StatRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    detail.roster().then(setRoster).catch(() => setRoster(null));
  }, []);

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
    setLoading(true);
    detail
      .playerMatchups(pid, role, kind)
      .then((d) => setRows(d.items))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [pid, role, kind]);

  const pName = players.find((p) => p.id === pid)?.name;
  const oppLabel = role === "batting" ? "投手" : "打者";

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">投打對決</h1>
        <p className="mt-2 text-sm text-muted">
          選一位球員，列出他生涯對戰過的所有{oppLabel}（同隊不對戰，已自然排除）。
          點欄位排序、依對手球隊篩選、點對手名字看個人頁。
        </p>
      </header>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Toggle<Role>
          options={[
            { v: "batting", label: "以打者查" },
            { v: "pitching", label: "以投手查" },
          ]}
          value={role}
          onChange={setRole}
        />
        {roster && (
          <select
            value={pid}
            aria-label="選擇球員"
            onChange={(e) => setPid(e.target.value)}
            className="min-w-52 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-ink"
          >
            <option value="">選擇{role === "batting" ? "打者" : "投手"}…</option>
            {players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}（{p.team ?? "?"}）
              </option>
            ))}
          </select>
        )}
        <Toggle
          options={[
            { v: "A", label: "例行賽" },
            { v: "C", label: "總冠軍" },
            { v: "E", label: "季後賽" },
          ]}
          value={kind}
          onChange={setKind}
        />
      </div>

      {!pid && <p className="text-sm text-faint">請先選擇一位{role === "batting" ? "打者" : "投手"}。</p>}
      {loading && <p className="text-sm text-faint">查詢中…</p>}

      {rows && !loading && (
        rows.length === 0 ? (
          <Card className="text-sm text-muted">
            {pName ?? "該球員"} 在「{KIND_LABEL[kind]}」生涯無對戰{oppLabel}紀錄。
          </Card>
        ) : (
          <>
            <h2 className="mb-3 text-lg font-semibold">
              {pName}：生涯對戰{oppLabel}（{KIND_LABEL[kind]}，共 {rows.length} 位）
            </h2>
            <Leaderboard
              rows={rows}
              cols={matchupCols(role)}
              defaultSort="plate_appearances"
              filters={[{ key: "opp_team", label: "對手球隊" }]}
            />
          </>
        )
      )}
    </div>
  );
}
