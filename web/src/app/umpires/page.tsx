"use client";

import Link from "next/link";

// 裁判索引（中性）：本季主審執法場次與逐球追蹤覆蓋，進入個人紀錄。
// ⚠️ NO-GO 邊界（PRODUCT_UX_BLUEPRINT §5.12；ML-UMP1／2 研究）：方向性裁判產品不成立
// （代理帶邊界稍動即全面翻轉）。本頁刻意**無排行、無準確率、無偏隊/送分/勝負影響**；
// 依執法場次排序＝工作量索引（非優劣）。單場好球帶判決分布為描述性視覺化，改置於賽事
// 詳情頁（主審判決 tab），本頁不重複。改名為「代理帶一致率」等仍屬 NO-GO，不採用。
import { useEffect, useState } from "react";
import { clientGet } from "@/lib/client";
import { DataTable, type Column } from "@/components/table";
import { ENTITY_LINK, Skeleton, EmptyState } from "@/components/ui";

type Index = {
  season: number;
  kind_code: string;
  items: { umpire: string; games: number; tracked_games: number }[];
};

export default function UmpiresPage() {
  const [data, setData] = useState<Index | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    clientGet<Index>("/api/v1/umpires")
      .then((d) => setData(d))
      .catch(() => setError(true));
  }, []);

  const cols: Column<Index["items"][number]>[] = [
    {
      header: "主審", nowrap: true, className: "font-sans",
      cell: (u) => (
        <Link href={`/people/umpire/${encodeURIComponent(u.umpire)}`} className={ENTITY_LINK}>
          {u.umpire}
        </Link>
      ),
    },
    { header: "執法場次", cell: (u) => u.games, align: "right" },
    {
      header: "逐球追蹤", align: "right",
      cell: (u) => (
        u.tracked_games > 0
          ? <span className="tabular-nums">{u.tracked_games} 場</span>
          : <span className="text-faint">無</span>
      ),
    },
  ];

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">裁判索引</h1>
        <p className="mt-1.5 text-sm text-muted">
          本季主審執法場次與逐球追蹤覆蓋，可進入個人執法紀錄。這是中性索引，
          <b className="font-semibold text-ink">非優劣排行</b>：依執法場次排序，不評判好壞球判決準確度。
        </p>
      </header>

      {error ? (
        <EmptyState>裁判索引載入失敗，請稍後再試。</EmptyState>
      ) : data === null ? (
        <Skeleton className="h-64 rounded-xl" />
      ) : (
        <>
          <DataTable
            columns={cols}
            rows={data.items}
            rowKey={(u) => u.umpire}
            dense
            emptyText="本季尚無主審執法紀錄。"
          />
          <p className="mt-3 text-[11px] leading-normal text-faint">
            「逐球追蹤」＝該主審有 TrackMan 逐球資料的場次數（設備為球場端、覆蓋不全，2026 起才有）。
            單場好壞球判決分布為描述性視覺化，置於各場賽事詳情頁的「主審判決」；
            固定規則好球帶僅作空間參考、未依打者身高調整，非官方評判。
          </p>
        </>
      )}
    </div>
  );
}
