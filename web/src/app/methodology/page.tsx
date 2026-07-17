import { Card, Eyebrow, Notice } from "@/components/ui";
import { METHODOLOGY_SECTIONS } from "@/lib/methodology-anchors";

export const metadata = { title: "方法與模型透明度 | CPBL 分析" };

// §5.14 規定每段呈現的欄位；在 UX-MODEL-METHOD1 填入實際內容前，這裡只宣告欄位名稱，
// 不得先放任何回測數字、baseline 或版本——沒有查核過的數字比空白更糟。
const PENDING_FIELDS = ["回答的問題", "資料期間", "validation", "baseline", "限制", "版本"];

/**
 * `/methodology` 骨架（PRODUCT_UX_BLUEPRINT v0.2 §5.14）。
 *
 * 本頁由 UX-NAV-IA1 建立，只負責讓「更多 → 方法」有可用入口，並固定五個模型段落的
 * anchor，使模型旁的說明 badge 能穩定 deep-link。**各段實際內容（回測、baseline、
 * 限制、版本）屬 UX-MODEL-METHOD1 的驗收範圍**，本卡不代填。
 *
 * 段落順序與 id 直接由 METHODOLOGY_SECTIONS 產生，anchor 契約因此不會與 badge 連結漂移。
 */
export default function MethodologyPage() {
  return (
    <div>
      <header className="mb-6">
        <Eyebrow className="mb-2">方法與模型透明度</Eyebrow>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">這個數字怎麼來、可信到哪裡？</h1>
        <p className="mt-1.5 text-sm text-muted">
          本站每個模型結果都應該能回答：它預測什麼、用哪段資料、跟什麼基準比、以及在哪裡會失準。
        </p>
      </header>

      <Notice tone="warn" className="mb-6">
        本頁目前只有骨架。各模型的回測、baseline 與限制尚未填入，請勿將此頁視為模型已通過驗證的依據。
      </Notice>

      <div className="space-y-4">
        {Object.entries(METHODOLOGY_SECTIONS).map(([id, label]) => (
          <Card key={id}>
            {/* scroll-mt 讓 deep-link 錨點不被 sticky header 蓋住 */}
            <h2 id={id} className="scroll-mt-24 text-base font-bold text-ink">
              {label}
            </h2>
            <p className="mt-2 text-sm text-muted">本段將說明：{PENDING_FIELDS.join("、")}。</p>
            <p className="mt-1 text-xs text-faint">內容建置中。</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
