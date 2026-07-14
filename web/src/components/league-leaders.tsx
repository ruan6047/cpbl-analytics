"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, Eyebrow, TeamLogo } from "@/components/ui";

type LeaderItem = {
  player_id: string;
  name: string | null;
  team: string | null;
  val: number;
};

type LeaderCategory = {
  label: string;
  key: string;
  format: (v: number) => string;
  items: LeaderItem[];
};

export default function LeagueLeaders({
  batting,
  pitching,
}: {
  batting: Record<string, LeaderItem[]>;
  pitching: Record<string, LeaderItem[]>;
}) {
  const [activeTab, setActiveTab] = useState<"batting" | "pitching">("batting");

  const battingCategories: LeaderCategory[] = [
    {
      label: "打擊率 (AVG)",
      key: "avg",
      format: (v) => v.toFixed(3).replace(/^0/, ""),
      items: batting.avg || [],
    },
    {
      label: "安打 (H)",
      key: "h",
      format: (v) => Math.round(v).toString(),
      items: batting.h || [],
    },
    {
      label: "全壘打 (HR)",
      key: "hr",
      format: (v) => Math.round(v).toString(),
      items: batting.hr || [],
    },
    {
      label: "打點 (RBI)",
      key: "rbi",
      format: (v) => Math.round(v).toString(),
      items: batting.rbi || [],
    },
    {
      label: "盜壘成功 (SB)",
      key: "sb",
      format: (v) => Math.round(v).toString(),
      items: batting.sb || [],
    },
  ];

  const pitchingCategories: LeaderCategory[] = [
    {
      label: "防禦率 (ERA)",
      key: "era",
      format: (v) => v.toFixed(2),
      items: pitching.era || [],
    },
    {
      label: "勝投 (W)",
      key: "w",
      format: (v) => Math.round(v).toString(),
      items: pitching.w || [],
    },
    {
      label: "中繼成功 (HLD)",
      key: "hld",
      format: (v) => Math.round(v).toString(),
      items: pitching.hld || [],
    },
    {
      label: "救援成功 (SV)",
      key: "sv",
      format: (v) => Math.round(v).toString(),
      items: pitching.sv || [],
    },
    {
      label: "奪三振 (SO)",
      key: "so",
      format: (v) => Math.round(v).toString(),
      items: pitching.so || [],
    },
  ];

  const categories = activeTab === "batting" ? battingCategories : pitchingCategories;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between border-b border-line pb-2">
        <h2 className="text-lg font-bold text-ink">聯盟數據領先</h2>
        <div className="flex rounded-lg bg-surface-2 p-0.5 text-xs">
          <button
            onClick={() => setActiveTab("batting")}
            className={`rounded-md px-3 py-1.5 font-medium transition ${
              activeTab === "batting"
                ? "bg-surface text-ink shadow-sm"
                : "text-muted hover:text-ink"
            }`}
          >
            打擊領先
          </button>
          <button
            onClick={() => setActiveTab("pitching")}
            className={`rounded-md px-3 py-1.5 font-medium transition ${
              activeTab === "pitching"
                ? "bg-surface text-ink shadow-sm"
                : "text-muted hover:text-ink"
            }`}
          >
            投手領先
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
        {categories.map((cat) => {
          const top1 = cat.items[0];
          const runnerUps = cat.items.slice(1, 5);

          return (
            <Card key={cat.key} className="flex flex-col justify-between" padding="p-3">
              <div>
                <Eyebrow className="mb-2">{cat.label}</Eyebrow>
                
                {top1 ? (
                  <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
                    <Link
                      href={`/players/${top1.player_id}`}
                      className="group flex items-center gap-2"
                    >
                      <TeamLogo code={null} name={top1.team} size={28} decorative />
                      <div className="min-w-0">
                        <div className="font-bold text-sm text-ink group-hover:text-accent transition truncate max-w-[80px]">
                          {top1.name}
                        </div>
                        <div className="text-[10px] text-muted truncate max-w-[80px]">{top1.team || "—"}</div>
                      </div>
                    </Link>
                    <div className="text-right">
                      <div className="font-mono text-xl font-black text-ink">
                        {cat.format(top1.val)}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="py-4 text-center text-xs text-faint">暫無數據</p>
                )}
              </div>

              {runnerUps.length > 0 && (
                <ul className="space-y-1 text-[11px]">
                  {runnerUps.map((item, idx) => (
                    <li
                      key={item.player_id}
                      className="flex items-center justify-between py-0.5 border-t border-line/30 first:border-0"
                    >
                      <span className="flex items-center gap-1.5 min-w-0">
                        <span className="w-3.5 font-mono font-bold text-faint text-right">
                          {idx + 2}
                        </span>
                        <Link
                          href={`/players/${item.player_id}`}
                          className="font-medium text-ink hover:text-accent transition truncate max-w-[60px]"
                        >
                          {item.name}
                        </Link>
                        <span className="text-[9px] text-muted truncate max-w-[45px]">({item.team})</span>
                      </span>
                      <span className="font-mono font-semibold text-ink">
                        {cat.format(item.val)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
