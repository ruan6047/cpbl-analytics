// #287 S06 第 2 區（#teams）的 registry 登記內容（#285 掛點契約 r3 §4、§8 M1 甲／M4）。
// `area-registry.ts` 只 import 這一筆；端點、元件、更新方式與頁尾說明都在本卡自己的檔。

import { ComparisonSection } from "@/components/playoffs/comparison-section";
import type { AreaRegistration } from "@/lib/playoffs-areas";
import {
  COMPARISON_REFRESH,
  comparisonNotes,
  comparisonPath,
  type ComparisonPayload,
} from "@/lib/playoffs-comparison";

export const COMPARISON_AREA: AreaRegistration<ComparisonPayload> = {
  id: "teams",
  path: comparisonPath,
  Section: ComparisonSection,
  // M4：本系列 box 晚於 final 送達時 context_version 可能不變 ⇒ 每輪重取（E8：每次 GET 約 10–30 ms）。
  refresh: COMPARISON_REFRESH,
  notes: comparisonNotes,
};
