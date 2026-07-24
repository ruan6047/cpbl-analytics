"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { DataTable, type Column } from "@/components/table";
import { Tooltip } from "@/components/tooltip";
import { ENTITY_LINK, NameTag, Pill, TeamLogo, prColor } from "@/components/ui";
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
  chip?: boolean; // 類別值（守位/角色）渲染成標籤 pill（獨立欄；併入名字欄改用 subChipKey）
  teamKey?: string; // 提供時，link 名稱欄前加該欄（隊名）的隊徽 icon（隊欄併入名字）
  subChipKey?: string; // link 名稱欄下方疊一枚該欄（守位/角色）標籤 pill（守位/角色併入名字欄）
  rate?: boolean; // 率值欄（AVG/OPS/ERA…）：以此欄排序時套規定打席/局數門檻，未達者置底不計名次
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
  qualKey,
  qualMin,
}: {
  rows: Row[];
  cols: Col[];
  defaultSort: string;
  defaultDir?: 1 | -1;
  filters?: Filter[];
  qualKey?: string; // 規定門檻的計量欄（打者 pa／投手 ip）
  qualMin?: number; // 規定打席/局數；以率值欄排序時，未達者置底不計名次
}) {
  const [sortKey, setSortKey] = useState(defaultSort);
  const [dir, setDir] = useState<1 | -1>(defaultDir);
  const [sel, setSel] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState(false);
  // 窄螢幕真正把 mobileHide 欄「移出 DOM」（非 CSS display:none）：table 佈局下 display:none
  // 欄會殘留幽靈寬度造成假性水平捲動，故於 client 依 matchMedia 過濾欄位。SSR/首次 render
  // 皆為桌機欄（isNarrow=false），與伺服器一致無 hydration 落差，掛載後再依實際寬度調整。
  const [isNarrow, setIsNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const sync = () => setIsNarrow(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  // §5.6 減法：有標 primary 的欄集才啟用「精簡/完整」切換；否則顯示全部（向後相容）。
  const hasPrimary = cols.some((c) => c.primary);
  const visibleCols = (hasPrimary && !expanded ? cols.filter((c) => c.primary) : cols)
    .filter((c) => !(isNarrow && c.mobileHide));

  const options = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const f of filters) {
      m[f.key] = Array.from(
        new Set(rows.map((r) => r[f.key]).filter((v): v is string => !!v)),
      ).sort((a, b) => a.localeCompare(b, "zh-Hant"));
    }
    return m;
  }, [rows, filters]);

  // 以率值欄（rate）排序時套規定門檻：達標者依指標排序在前並計名次，未達者（小樣本）
  // 置底、灰階、不佔名次——避免 1 打席 OPS 2.000 灌爆榜首；計數型欄（HR/勝…）不套門檻。
  const qualifying = !!(cols.find((c) => c.key === sortKey)?.rate && qualKey && qualMin);
  const { view, qualCount } = useMemo(() => {
    let r = rows;
    for (const f of filters) {
      if (sel[f.key]) r = r.filter((x) => x[f.key] === sel[f.key]);
    }
    const byKey = (a: Row, b: Row) => cmp(a[sortKey], b[sortKey], dir);
    if (qualifying) {
      const ok = (x: Row) => (Number(x[qualKey!]) || 0) >= qualMin!;
      const q = r.filter(ok).sort(byKey);
      const nq = r.filter((x) => !ok(x)).sort(byKey);
      return { view: [...q, ...nq], qualCount: q.length };
    }
    return { view: [...r].sort(byKey), qualCount: -1 }; // -1＝全員計名次
  }, [rows, filters, sel, sortKey, dir, qualifying, qualKey, qualMin]);

  const onSort = (key: string) => {
    if (key === sortKey) setDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setDir(-1);
    }
  };

  // inline bar 的 per-欄值域（隨篩選後檢視變動；min=max 時退化為中性半長）
  const barRange = useMemo(() => {
    // 套門檻時，bar 值域取「達標者」，免小樣本極端值（OPS 2.000）壓縮眾人條長。
    const barRows = qualifying && qualCount > 0 ? view.slice(0, qualCount) : view;
    const m: Record<string, { min: number; max: number }> = {};
    for (const c of cols) {
      if (!c.bar) continue;
      const vals = barRows
        .map((r) => r[c.key])
        .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
      if (vals.length) m[c.key] = { min: Math.min(...vals), max: Math.max(...vals) };
    }
    return m;
  }, [view, qualCount, qualifying, cols]);

  const barCell = (c: Col, v: number | string | null) => {
    const rng = barRange[c.key];
    const num = typeof v === "number" && Number.isFinite(v) ? v : null;
    if (!rng || num === null) return fmtVal(v, c.fmt);
    const p = rng.max > rng.min ? (num - rng.min) / (rng.max - rng.min) : 0.5;
    const gRaw = c.lowerBetter ? 1 - p : p; // goodness：條長與顏色一律「越好越長越紅」
    // clamp 至 [0,1]：值域取達標者後，置底小樣本（如 OPS 2.000 超出達標最高值）會使
    // g>1、bar 寬 >100% 而水平溢出撐爆 table scrollWidth（造成捲到空白的假性捲動）。
    const g = Math.min(Math.max(gRaw, 0), 1);
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
      cell: (_row, i) => (qualCount >= 0 && i >= qualCount ? "–" : i + 1),
      align: "right",
      nowrap: true,
      className: "text-faint",
      width: "3rem",
    },
    ...visibleCols.map((c): Column<Row> => {
      const active = c.key === sortKey;
      return {
        header: header(c),
        ariaSort: active ? (dir === -1 ? "descending" : "ascending") : c.sortable === false ? undefined : "none",
        align: c.fmt ? "right" : "left",
        nowrap: true,
        sticky: c === visibleCols[0],
        headClassName: active ? "text-accent" : "",
        className: `${c.fmt ? "" : "font-sans"} ${active ? "font-medium text-ink" : toneCls(c.tone)}`,
        cell: (r) => c.team ? (
          <NameTag name={String(r[c.key] ?? "")} link />
        ) : c.link ? (
          <span className="inline-flex items-center gap-1.5">
            {c.teamKey && <TeamLogo name={String(r[c.teamKey] ?? "")} size={16} decorative />}
            <span className="inline-flex flex-col items-start leading-tight">
              <Link href={`${c.link.base}${r[c.link.idKey]}`} className={ENTITY_LINK}>
                {fmtVal(r[c.key], c.fmt)}
              </Link>
              {c.subChipKey && r[c.subChipKey] && <Pill className="mt-0.5">{String(r[c.subChipKey])}</Pill>}
            </span>
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

      {qualifying && qualCount >= 0 && (
        <p className="mb-2 text-[11px] text-faint">
          依{cols.find((c) => c.key === sortKey)?.label} 排序：灰階 {view.length - qualCount} 人未達
          {qualMin ? `規定門檻（${qualKey === "ip" ? "投球局數" : "打席"} ≥ ${qualMin}）` : "規定門檻"}，
          置底且不列入名次，避免小樣本失真。
        </p>
      )}
      <DataTable
        columns={columns}
        rows={view}
        rowKey={(r, i) => String(r.player_id ?? r.opp_id ?? `${r.name ?? r.opp_name ?? "row"}-${r.team ?? r.opp_team ?? ""}-${i}`)}
        rowClassName={(_r, i) => (qualCount >= 0 && i >= qualCount ? "opacity-55" : "")}
        dense
      />
    </div>
  );
}
