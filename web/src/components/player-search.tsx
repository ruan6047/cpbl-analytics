"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { TeamLogo, Skeleton } from "@/components/ui";
import { detail } from "@/lib/client";

type PlayerItem = {
  id: string;
  name: string;
  team: string;
  type: "batter" | "pitcher";
};

export default function PlayerSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [players, setPlayers] = useState<PlayerItem[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  // 點擊外部關閉下拉選單
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleFocus = async () => {
    setIsOpen(true);
    if (players.length > 0 || loading) return;

    setLoading(true);
    try {
      // 復用 client.ts 的 detail.roster()
      const data = await detail.roster();
      
      const batters: PlayerItem[] = (data.batters || []).map((b) => ({
        id: b.id,
        name: b.name || "",
        team: b.team || "",
        type: "batter" as const,
      }));
      const pitchers: PlayerItem[] = (data.pitchers || []).map((p) => ({
        id: p.id,
        name: p.name || "",
        team: p.team || "",
        type: "pitcher" as const,
      }));
      
      setPlayers([...batters, ...pitchers]);
    } catch (e) {
      console.error("Failed to load player roster for search", e);
    } finally {
      setLoading(false);
    }
  };

  const filteredPlayers = query.trim()
    ? players.filter(
        (p) =>
          p.name.toLowerCase().includes(query.toLowerCase()) ||
          p.team.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 8)
    : players.slice(0, 5); // 預設顯示前五個

  return (
    <div ref={containerRef} className="relative w-full max-w-md mx-auto z-20">
      <div className="relative">
        <input
          type="text"
          placeholder="搜尋球員姓名或球隊 (例如: 林立、兄弟)..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={handleFocus}
          className="w-full rounded-full border border-line bg-surface-2 px-5 py-3 pl-11 text-sm text-ink outline-none transition focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent/15"
        />
        <svg
          className="absolute left-4 top-3.5 h-4.5 w-4.5 text-faint"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        {query && (
          <button
            onClick={() => setQuery("")}
            className="absolute right-4 top-3.5 text-xs text-faint hover:text-ink transition"
          >
            清除
          </button>
        )}
      </div>

      {isOpen && (
        <div className="absolute mt-2 w-full rounded-xl border border-line bg-surface p-1 shadow-lg max-h-72 overflow-y-auto z-30">
          {loading ? (
            <div className="p-3 space-y-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
            </div>
          ) : filteredPlayers.length === 0 ? (
            <div className="p-3 text-center text-xs text-faint">找不到符合的球員</div>
          ) : (
            <ul>
              {filteredPlayers.map((p) => (
                <li key={`${p.type}-${p.id}`}>
                  <button
                    onClick={() => {
                      setIsOpen(false);
                      setQuery("");
                      router.push(`/players/${p.id}`);
                    }}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-surface-2 transition"
                  >
                    <TeamLogo code={null} name={p.team} size={20} decorative />
                    <span className="font-semibold">{p.name}</span>
                    <span className="text-xs text-muted">{p.team}</span>
                    <span className="ml-auto text-[10px] font-semibold text-faint bg-surface-3 px-1.5 py-0.5 rounded">
                      {p.type === "batter" ? "打者" : "投手"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
