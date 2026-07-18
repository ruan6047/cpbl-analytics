import { Suspense } from "react";
import { TableSkeleton } from "@/components/ui";
import MatchupsClient from "./matchups-client";

export const metadata = { title: "投打對決" };

// 查詢狀態全在 URL（deep-link）；useSearchParams 需 Suspense 邊界供預渲染。
export default function MatchupsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={5} />}>
      <MatchupsClient />
    </Suspense>
  );
}
