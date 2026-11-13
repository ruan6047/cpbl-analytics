import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PitchMindDemo } from "./view";

// PitchMind 概念展演頁（#452）：隱藏路由、noindex、不進導覽、完全靜態。
// 全頁為匿名示意資料。比照 /dev/* 走查頁「假資料不得公開」：正式 build 預設 404，
// 只有建置時明設 PITCHMIND_DEMO=1 才產出（例如本機 build:check 後 next start 展演）。
export const metadata: Metadata = {
  title: "PitchMind 情蒐展演（示意）",
  robots: { index: false, follow: false },
};

export default function PitchMindDemoPage() {
  if (process.env.NODE_ENV === "production" && process.env.PITCHMIND_DEMO !== "1") notFound();
  return <PitchMindDemo />;
}
