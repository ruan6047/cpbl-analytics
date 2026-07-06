"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { NameTag, prColor } from "@/components/ui";
import { fmtIP } from "@/lib/format";

export type Fmt = "i" | "f1" | "f2" | "f3" | "ip";
export type Tone = "accent" | "dim" | "warn";

export type Col = {
  key: string;
  label: string;
  fmt?: Fmt; // 預設 i（整數/字串原樣）
  tone?: Tone;
  sortable?: boolean; // 預設 true
  tip?: string; // 滑鼠滑過欄位標題顯示的中文說明
  // 若提供，該儲存格渲染成連結 href = base + row[idKey]（如球員名→個人頁）。
  // 用可序列化物件而非函式，server component 才能把 Col 傳給此 client 元件。
  link?: { base: string; idKey: string };
  team?: boolean; // 該欄值為隊名時，渲染隊徽 + 名稱
  bar?: boolean; // Savant 式 inline bar：依當前檢視 min-max 畫底色條 + 藍↔紅發散上色
  lowerBetter?: boolean; // 低為佳（ERA/WHIP…）：bar 長度與顏色反向
};

export type Filter = { key: string; label: string };

type Row = Record<string, number | string | null>;

const fmtVal = (v: number | string | null, fmt?: Fmt): string => {
  if (v === null || v === undefined || v === "") return "—";
  if (fmt === "f1") return Number(v).toFixed(1);
  if (fmt === "f2") return Number(v).toFixed(2);
  if (fmt === "f3") return Number(v).toFixed(3).replace(/^0\./, ".");
  if (fmt === "ip") return fmtIP(v);
  return String(v);
};

const toneCls = (tone?: Tone): string =>
  tone === "accent" ? "text-accent" : tone === "warn" ? "text-accent" : tone === "dim" ? "text-muted" : "";

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
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);

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

  // inline bar 的 per-欄值域（隨篩選後檢視變動；min=max 時退化為中性半長）
  const barRange = useMemo(() => {
    const m: Record<string, { min: number; max: number }> = {};
    for (const c of cols) {
      if (!c.bar) continue;
      const vals = view
        .map((r) => r[c.key])
        .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
      if (vals.length) m[c.key] = { min: Math.min(...vals), max: Math.max(...vals) };
    }
    return m;
  }, [view, cols]);

  const barCell = (c: Col, v: number | string | null) => {
    const rng = barRange[c.key];
    const num = typeof v === "number" && Number.isFinite(v) ? v : null;
    if (!rng || num === null) return fmtVal(v, c.fmt);
    const p = rng.max > rng.min ? (num - rng.min) / (rng.max - rng.min) : 0.5;
    const g = c.lowerBetter ? 1 - p : p; // goodness：條長與顏色一律「越好越長越紅」
    return (
      <span className="relative inline-block min-w-[3.5rem] text-right align-middle">
        <span
          className="absolute inset-y-0.5 left-0 rounded-sm opacity-30"
          style={{ width: `${Math.max(g * 100, 4)}%`, background: prColor(g * 100) }}
        />
        <span className="relative">{fmtVal(v, c.fmt)}</span>
      </span>
    );
  };

  return (
    <div>
      {filters.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-3">
          {filters.map((f) => (
            <label key={f.key} className="flex items-center gap-2 text-sm">
              <span className="text-muted">{f.label}</span>
              <select
                value={sel[f.key] ?? ""}
                onChange={(e) => setSel((s) => ({ ...s, [f.key]: e.target.value }))}
                className="rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 outline-none focus:border-ink"
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
          <span className="self-center text-xs text-faint">{view.length} 筆</span>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-muted">
            <tr>
              <th scope="col" className="px-2.5 py-3 font-medium">#</th>
              {cols.map((c) => {
                const active = c.key === sortKey;
                const sortable = c.sortable !== false;
                // 表頭 tooltip：滑鼠(hover)與鍵盤(focus)皆可觸發；focus 用元素矩形定位
                const showTip = c.tip
                  ? (x: number, y: number) => setTip({ text: c.tip!, x, y })
                  : undefined;
                const tipClass = c.tip
                  ? "underline decoration-line decoration-dotted underline-offset-4"
                  : "";
                const arrow = active ? (dir === -1 ? " ↓" : " ↑") : sortable ? <span className="text-faint"> ↕</span> : "";
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={active ? (dir === -1 ? "descending" : "ascending") : sortable ? "none" : undefined}
                    className={`whitespace-nowrap px-2.5 py-3 font-medium ${active ? "text-accent" : ""}`}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={() => onSort(c.key)}
                        onMouseEnter={showTip ? (e) => showTip(e.clientX, e.clientY) : undefined}
                        onMouseMove={showTip ? (e) => showTip(e.clientX, e.clientY) : undefined}
                        onMouseLeave={() => setTip(null)}
                        onFocus={showTip ? (e) => { const r = e.currentTarget.getBoundingClientRect(); showTip(r.left, r.bottom); } : undefined}
                        onBlur={() => setTip(null)}
                        className={`inline-flex items-center font-medium hover:text-ink ${tipClass}`}
                      >
                        {c.label}
                        {arrow}
                      </button>
                    ) : c.tip ? (
                      <span
                        tabIndex={0}
                        onMouseEnter={showTip ? (e) => showTip(e.clientX, e.clientY) : undefined}
                        onMouseMove={showTip ? (e) => showTip(e.clientX, e.clientY) : undefined}
                        onMouseLeave={() => setTip(null)}
                        onFocus={showTip ? (e) => { const r = e.currentTarget.getBoundingClientRect(); showTip(r.left, r.bottom); } : undefined}
                        onBlur={() => setTip(null)}
                        className={tipClass}
                      >
                        {c.label}
                      </span>
                    ) : (
                      c.label
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {view.map((r, i) => (
              <tr key={i} className="border-t border-line hover:bg-surface-2">
                <td className="px-2.5 py-2.5 text-faint">{i + 1}</td>
                {cols.map((c) => (
                  <td
                    key={c.key}
                    className={`whitespace-nowrap px-2.5 py-2.5 ${c.fmt ? "" : "font-sans"} ${
                      c.key === sortKey ? "font-medium text-ink" : toneCls(c.tone)
                    }`}
                  >
                    {c.team ? (
                      <NameTag name={String(r[c.key] ?? "")} />
                    ) : c.link ? (
                      <Link
                        href={`${c.link.base}${r[c.link.idKey]}`}
                        className="text-accent hover:underline"
                      >
                        {fmtVal(r[c.key], c.fmt)}
                      </Link>
                    ) : c.bar ? (
                      barCell(c, r[c.key])
                    ) : (
                      fmtVal(r[c.key], c.fmt)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {tip && (
        <div
          className="pointer-events-none fixed z-50 max-w-xs rounded-md border border-line bg-zinc-800 px-2.5 py-1.5 text-xs leading-relaxed text-white shadow-xl"
          style={{ left: tip.x + 14, top: tip.y + 16 }}
        >
          {tip.text}
        </div>
      )}
    </div>
  );
}
