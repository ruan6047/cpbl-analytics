import { notFound } from "next/navigation";
import { Suspense } from "react";
import { VariantView } from "../../variant-view";
import { FIXTURES, VARIANTS, type Variant } from "../../lib";

export const metadata = { title: "球員頁 IA prototype（dev only）", robots: { index: false } };

// UX-PLAYER-IA1 prototype：只在開發環境存在（fixture 為截斷的真實資料，不對外）。
export default async function PlayerIaVariantPage({ params }: {
  params: Promise<{ variant: string; scenario: string }>;
}) {
  if (process.env.NODE_ENV === "production") notFound();
  const { variant, scenario } = await params;
  if (!VARIANTS.includes(variant as Variant) || !FIXTURES[scenario]) notFound();
  return (
    <Suspense>
      <VariantView variant={variant as Variant} scenario={scenario} />
    </Suspense>
  );
}
