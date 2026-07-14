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
      label: "整體攻擊指數 (OPS)",
      key: "ops",
      format: (v) => v.toFixed(3),
      items: batting.ops || [],
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
      label: "每局被上壘率 (WHIP)",
      key: "whip",
      format: (v) => v.toFixed(2),
      items: pitching.whip || [],
    },
    {
      label: "奪三振 (SO)",
      key: "so",
      format: (v) => Math.round(v).toString(),
      items: pitching.so || [],
    },
    {
      label: "救援成功 (SV)",
      key: "sv",
      format: (v) => Math.round(v).toString(),
      items: pitching.sv || [],
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {categories.map((cat) => {
          const top1 = cat.items[0];
          const runnerUps = cat.items.slice(1, 5);

          return (
            <Card key={cat.key} className="flex flex-col justify-between">
              <div>
                <Eyebrow className="mb-3">{cat.label}</Eyebrow>
                
                {top1 ? (
                  <div className="mb-4 flex items-center justify-between border-b border-line pb-3">
                    <Link
                      href={`/players/${top1.player_id}`}
                      className="group flex items-center gap-3"
                    >
                      <TeamLogo code={null} name={top1.team} size={36} decorative />
                      <div>
                        <div className="font-bold text-ink group-hover:text-accent transition">
                          {top1.name}
                        </div>
                        <div className="text-xs text-muted">{top1.team || "—"}</div>
                      </div>
                    </Link>
                    <div className="text-right">
                      <div className="font-mono text-2xl font-black text-ink">
                        {cat.format(top1.val)}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="py-4 text-center text-xs text-faint">暫無數據</p>
                )}
              </div>

              {runnerUps.length > 0 && (
                <ul className="space-y-1.5 text-xs">
                  {runnerUps.map((item, idx) => (
                    <li
                      key={item.player_id}
                      className="flex items-center justify-between py-1 border-t border-line/40 first:border-0"
                    >
                      <span className="flex items-center gap-2">
                        <span className="w-4 font-mono font-bold text-faint text-right">
                          {idx + 2}
                        </span>
                        <Link
                          href={`/players/${item.player_id}`}
                          className="font-medium text-ink hover:text-accent transition"
                        >
                          {item.name}
                        </Link>
                        <span className="text-[10px] text-muted">({item.team})</span>
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
