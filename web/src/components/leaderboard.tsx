"use client";

import { useMemo, useState } from "react";

export type Fmt = "i" | "f1" | "f2" | "f3";
export type Tone = "accent" | "dim" | "warn";

export type Col = {
  key: string;
  label: string;
  fmt?: Fmt; // 預設 i（整數/字串原樣）
  tone?: Tone;
  sortable?: boolean; // 預設 true
};

export type Filter = { key: string; label: string };

type Row = Record<string, number | string | null>;

const fmtVal = (v: number | string | null, fmt?: Fmt): string => {
  if (v === null || v === undefined || v === "") return "—";
  if (fmt === "f1") return Number(v).toFixed(1);
  if (fmt === "f2") return Number(v).toFixed(2);
  if (fmt === "f3") return Number(v).toFixed(3).replace(/^0\./, ".");
  return String(v);
};

const toneCls = (tone?: Tone): string =>
  tone === "accent" ? "text-emerald-400" : tone === "warn" ? "text-rose-400/80" : tone === "dim" ? "text-white/50" : "";

function cmp(a: number | string | null, b: number | string | null, dir: 1 | -1): number {
  const an = a === null || a === undefined || a === "";
  const bn = b === null || b === undefined || b === "";
  if (an && bn) return 0;
  if (an) return 1; // null 永遠墊底
  if (bn) return -1;
  if (typeof a === "number" && typeof b === "number") return (a - b) * dir;
  return String(a).localeCompare(String(b), "zh-Hant") * dir;
}

export default function Leaderboard({
  rows,
  cols,
  defaultSort,
  defaultDir = -1,
  filters = [],
}: {
  rows: Row[];
  cols: Col[];
  defaultSort: string;
  defaultDir?: 1 | -1;
  filters?: Filter[];
}) {
  const [sortKey, setSortKey] = useState(defaultSort);
  const [dir, setDir] = useState<1 | -1>(defaultDir);
  const [sel, setSel] = useState<Record<string, string>>({});

  const options = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const f of filters) {
      m[f.key] = Array.from(
        new Set(rows.map((r) => r[f.key]).filter((v): v is string => !!v)),
      ).sort((a, b) => a.localeCompare(b, "zh-Hant"));
    }
    return m;
  }, [rows, filters]);

  const view = useMemo(() => {
    let r = rows;
    for (const f of filters) {
      if (sel[f.key]) r = r.filter((x) => x[f.key] === sel[f.key]);
    }
    return [...r].sort((x, y) => cmp(x[sortKey], y[sortKey], dir));
  }, [rows, filters, sel, sortKey, dir]);

  const onSort = (key: string) => {
    if (key === sortKey) setDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setDir(-1);
    }
  };

  return (
    <div>
      {filters.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-3">
          {filters.map((f) => (
            <label key={f.key} className="flex items-center gap-2 text-sm">
              <span className="text-white/50">{f.label}</span>
              <select
                value={sel[f.key] ?? ""}
                onChange={(e) => setSel((s) => ({ ...s, [f.key]: e.target.value }))}
                className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 outline-none focus:border-emerald-400"
              >
                <option value="">全部</option>
                {options[f.key]?.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <span className="self-center text-xs text-white/30">{view.length} 筆</span>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-left text-white/50">
            <tr>
              <th className="px-2.5 py-3 font-medium">#</th>
              {cols.map((c) => {
                const active = c.key === sortKey;
                const sortable = c.sortable !== false;
                return (
                  <th
                    key={c.key}
                    onClick={sortable ? () => onSort(c.key) : undefined}
                    className={`whitespace-nowrap px-2.5 py-3 font-medium ${
                      sortable ? "cursor-pointer select-none hover:text-white" : ""
                    } ${active ? "text-emerald-400" : ""}`}
                  >
                    {c.label}
                    {active ? (dir === -1 ? " ↓" : " ↑") : sortable ? <span className="text-white/15"> ↕</span> : ""}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {view.map((r, i) => (
              <tr key={i} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-2.5 py-2.5 text-white/40">{i + 1}</td>
                {cols.map((c) => (
                  <td
                    key={c.key}
                    className={`whitespace-nowrap px-2.5 py-2.5 ${c.fmt ? "" : "font-sans"} ${
                      c.key === sortKey ? "text-white" : toneCls(c.tone)
                    }`}
                  >
                    {fmtVal(r[c.key], c.fmt)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
