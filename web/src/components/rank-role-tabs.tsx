import Link from "next/link";

// 排行頁打者/投手切換（§5.5：角色切換在排行介面內清楚可達）。
// 保留 kind（一/二軍）與 year，讓 /batters ↔ /pitchers 互跳時脈絡不失。
const ROLES = [
  { v: "batting", label: "打者", base: "/batters" },
  { v: "pitching", label: "投手", base: "/pitchers" },
] as const;

export function RankRoleTabs({ role, kind, year }: { role: "batting" | "pitching"; kind: string; year: number }) {
  const qs = new URLSearchParams();
  if (kind === "D") qs.set("kind", kind);
  if (year) qs.set("year", String(year));
  const suffix = qs.toString() ? `?${qs}` : "";
  return (
    <nav className="mb-3 inline-flex items-center rounded-full border border-line bg-surface p-1" aria-label="打者／投手排行切換">
      {ROLES.map((r) => (
        <Link
          key={r.v}
          href={`${r.base}${suffix}`}
          aria-current={r.v === role ? "page" : undefined}
          className={`rounded-full px-4 py-1 text-sm font-medium transition ${
            r.v === role ? "bg-ink text-paper" : "text-muted hover:bg-surface-2"
          }`}
        >
          {r.label}
        </Link>
      ))}
    </nav>
  );
}
