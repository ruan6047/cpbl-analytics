import { notFound } from "next/navigation";
import { FieldDiagram, type FieldCells } from "@/components/field-diagram";

export const metadata = { title: "FieldDiagram 走查（dev only）", robots: { index: false } };

// UI-FIELD-DIAGRAM1 走查頁：只在開發環境存在。
// 驗收方式（非目視）：開 /dev/field-diagram 後於 console 對每個 svg 跑 getBBox 相交檢測，
// 375px 與桌機各一次；任兩個 text 的 bbox 不得相交。滿守位與超長副標是最壞情境。
const SCENARIOS: Record<string, FieldCells> = {
  "多守位・3 守位（余德龍型：局數）": {
    SS: { sub: "640 局" }, "3B": { sub: "45 局" }, P: { sub: "2 局" },
  },
  "多守位・5 守位（高捷型：場數，2018 前無局數）": {
    "1B": { sub: "12 場" }, "2B": { sub: "30 場" }, "3B": { sub: "8 場" },
    LF: { sub: "51 場" }, RF: { sub: "22 場" },
  },
  "滿守位・9 守位（最壞情境）": {
    LF: { sub: "1234 局" }, CF: { sub: "1234 局" }, RF: { sub: "1234 局" },
    "3B": { sub: "1234 局" }, SS: { sub: "1234 局" }, "2B": { sub: "1234 局" }, "1B": { sub: "1234 局" },
    P: { sub: "1234 局" }, C: { sub: "1234 局" },
  },
  "超長副標（截斷驗證：未來賽況頁球員名用途）": {
    SS: { sub: "王柏融、林立、陳子豪" }, C: { main: "捕手", sub: "戴培峰（第 7 局換上）" },
    "1B": { sub: "1088 局" },
  },
  "副標缺值（只有主標）": { CF: {}, LF: { sub: null } },
  "無任何資料（全部未使用格位）": {},
};

export default function FieldDiagramDevPage() {
  if (process.env.NODE_ENV === "production") notFound();

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-lg font-bold text-ink">FieldDiagram 走查</h1>
      <p className="text-xs text-muted">
        制式格位、非真實球場座標。驗收以 getBBox 相交檢測為準，不以目視。
      </p>
      {Object.entries(SCENARIOS).map(([name, cells]) => (
        <section key={name} className="card space-y-2 p-4" data-scenario={name}>
          <h2 className="font-mono text-xs text-faint">{name}</h2>
          <div className="flex justify-center">
            <FieldDiagram cells={cells} caption="守位分布" />
          </div>
        </section>
      ))}
    </main>
  );
}
