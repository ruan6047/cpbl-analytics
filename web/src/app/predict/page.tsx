import { redirect } from "next/navigation";
import { methodologyHref } from "@/lib/methodology-anchors";

/** 舊自由特徵預測頁退場後，保留既有 deep link 的單一教育入口。 */
export default function LegacyPredictPage() {
  redirect(methodologyHref("pregame"));
}
