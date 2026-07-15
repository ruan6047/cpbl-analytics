"use client";

// 生涯排行：頁籤切換打者／投手，各項獨立排行卡。
import { useState } from "react";
import { PlayerLink } from "@/components/ui";

type CareerRec = { name: string; pid: string; val: number | string; active: boolean };
export type CareerGroup = { title: string; rows?: CareerRec[] };

function LeaderCard({ title, rows }: CareerGroup) {
  const items = rows ?? [];
  return (
    <div className="card p-4">
      <h4 className="mb-2.5 text-sm font-semibold text-ink">{title}</h4>
      <ol className="space-y-1.5">
        {items.map((r, i) => (
          <li key={`${r.pid}-${i}`} className="flex items-center gap-2 text-sm">
            <span className="w-4 shrink-0 text-right font-mono text-xs tabular-nums text-faint">{i + 1}</span>
            <span className="min-w-0 flex-1 truncate font-sans">
              <PlayerLink pid={r.pid} name={r.name} />
              {r.active && <span className="ml-1.5 text-[10px] font-medium text-up">現役</span>}
            </span>
            <span className="shrink-0 font-mono font-semibold tabular-nums text-accent">{r.val}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function CareerLeaders({ batting, pitching }: { batting: CareerGroup[]; pitching: CareerGroup[] }) {
  const [tab, setTab] = useState<"bat" | "pit">("bat");
  const groups = tab === "bat" ? batting : pitching;
  const tabBtn = (v: "bat" | "pit", label: string) => (
    <button
      key={v}
      onClick={() => setTab(v)}
      aria-pressed={tab === v}
      className={`rounded-md px-4 py-1 text-sm font-medium transition ${tab === v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
    >
      {label}
    </button>
  );
  return (
    <div>
      <div className="mb-3 inline-flex gap-1 rounded-lg bg-surface-2 p-1">
        {tabBtn("bat", "打者")}
        {tabBtn("pit", "投手")}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {groups.map((g) => <LeaderCard key={g.title} title={g.title} rows={g.rows} />)}
      </div>
    </div>
  );
}
