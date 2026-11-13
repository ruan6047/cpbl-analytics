import type { Metadata } from "next";
import { PitchMindDemo } from "./view";

// PitchMind 概念展演頁（#452）：隱藏路由、noindex、不進導覽、完全靜態。
// 全頁為匿名示意資料，頁面本身標「示意資料」。正式 build 公開產出（需求方裁定
// issuecomment-6845545073「改成公開 noindex」）；本站目前沒有 sitemap，若日後新增須排除本路由。
export const metadata: Metadata = {
  title: "PitchMind 情蒐展演（示意）",
  robots: { index: false, follow: false },
};

export default function PitchMindDemoPage() {
  return <PitchMindDemo />;
}
