"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { DataTable, type Column } from "@/components/table";
import { Tooltip } from "@/components/tooltip";
import { NameTag, Pill, TeamLogo, prColor } from "@/components/ui";
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
  // 排行減法（§5.6）：primary=預設精簡檢視顯示的欄（未標 primary 者收進「完整欄位」）。
  // 任一欄標 primary 才啟用精簡/完整切換；全無 primary 時維持顯示全部（向後相容）。
  primary?: boolean;
  mobileHide?: boolean; // 窄螢幕（<sm）隱藏：手機只留排名/球員/主指標+1~2 支持
  chip?: boolean; // 類別值（守位/角色）渲染成標籤 pill
  teamKey?: string; // 提供時，link 名稱欄前加該欄（隊名）的隊徽 icon（隊欄併入名字）
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
  const [expanded, setExpanded] = useState(false);

  // §5.6 減法：有標 primary 的欄集才啟用「精簡/完整」切換；否則顯示全部（向後相容）。
  const hasPrimary = cols.some((c) => c.primary);
  const visibleCols = hasPrimary && !expanded ? cols.filter((c) => c.primary) : cols;

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
      <span className="relative inline-block min-w-[2.75rem] text-right align-middle">
        <span
          className="absolute inset-y-0.5 left-0 rounded-sm opacity-30"
          style={{ width: `${Math.max(g * 100, 4)}%`, background: prColor(g * 100) }}
        />
        <span className="relative">{fmtVal(v, c.fmt)}</span>
      </span>
    );
  };

  const header = (c: Col) => {
    const active = c.key === sortKey;
    const sortable = c.sortable !== false;
    const label = c.tip ? (
      <Tooltip content={c.tip}>
        <span className="underline decoration-line decoration-dotted underline-offset-4">{c.label}</span>
      </Tooltip>
    ) : c.label;
    if (!sortable) return label;
    return (
      <button
        type="button"
        onClick={() => onSort(c.key)}
        className={`inline-flex w-full items-center gap-1 font-medium hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${c.fmt ? "justify-end" : "justify-start"}`}
      >
        {label}
        <span aria-hidden className={active ? "text-accent" : "text-faint"}>
          {active ? (dir === -1 ? "↓" : "↑") : "↕"}
        </span>
      </button>
    );
  };

  const columns: Column<Row>[] = [
    {
      header: "#",
      cell: (_row, i) => i + 1,
      align: "right",
      nowrap: true,
      className: "text-faint",
      width: "3rem",
    },
    ...visibleCols.map((c): Column<Row> => {
      const active = c.key === sortKey;
      const hideCls = c.mobileHide ? "hidden sm:table-cell" : "";
      return {
        header: header(c),
        ariaSort: active ? (dir === -1 ? "descending" : "ascending") : c.sortable === false ? undefined : "none",
        align: c.fmt ? "right" : "left",
        nowrap: true,
        sticky: c === visibleCols[0],
        headClassName: `${active ? "text-accent" : ""} ${hideCls}`,
        className: `${c.fmt ? "" : "font-sans"} ${active ? "font-medium text-ink" : toneCls(c.tone)} ${hideCls}`,
        cell: (r) => c.team ? (
          <NameTag name={String(r[c.key] ?? "")} />
        ) : c.link ? (
          <span className="inline-flex items-center gap-1.5">
            {c.teamKey && <TeamLogo name={String(r[c.teamKey] ?? "")} size={16} decorative />}
            <Link href={`${c.link.base}${r[c.link.idKey]}`} className="text-accent hover:underline">
              {fmtVal(r[c.key], c.fmt)}
            </Link>
          </span>
        ) : c.chip ? (
          r[c.key] ? <Pill>{String(r[c.key])}</Pill> : <span className="text-faint">—</span>
        ) : c.bar ? (
          barCell(c, r[c.key])
        ) : (
          fmtVal(r[c.key], c.fmt)
        ),
      };
    }),
  ];

  return (
    <div>
      {(filters.length > 0 || hasPrimary) && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
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
          {filters.length > 0 && <span className="self-center text-xs text-faint">{view.length} 筆</span>}
          {hasPrimary && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              aria-pressed={expanded}
              className="ml-auto rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-sm text-muted transition hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {expanded ? "精簡欄位" : "完整欄位"}
            </button>
          )}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={view}
        rowKey={(r, i) => String(r.player_id ?? r.opp_id ?? `${r.name ?? r.opp_name ?? "row"}-${r.team ?? r.opp_team ?? ""}-${i}`)}
        dense
      />
    </div>
  );
}
