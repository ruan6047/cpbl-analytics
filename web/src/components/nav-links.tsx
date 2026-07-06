"use client";

// 頂欄導覽：以 usePathname 高亮當前頁（aria-current 供輔助技術）。
import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavLinks({ items }: { items: { href: string; label: string; group?: string }[] }) {
  const pathname = usePathname();
  return (
    <nav aria-label="主導覽" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
      {items.map((n, i) => {
        const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
        const newGroup = i > 0 && n.group !== items[i - 1].group;
        return (
          <span key={n.href} className="flex items-center gap-x-4">
            {newGroup && <span aria-hidden className="hidden h-4 w-px bg-line sm:inline-block" />}
            <Link href={n.href} aria-current={active ? "page" : undefined}
              className={active
                ? "border-b-2 border-accent pb-0.5 font-semibold text-ink"
                : "border-b-2 border-transparent pb-0.5 hover:text-ink"}>
              {n.label}
            </Link>
          </span>
        );
      })}
    </nav>
  );
}
