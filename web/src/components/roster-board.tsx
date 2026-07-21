// 主力選手圖（可重用）：左＝野手守備位置圖（含 DH），右＝以「角色分組」排列的球員格位卡
// （投手先發/中繼/後援、替補…皆為通用 group）。呼叫端只餵已算好的顯示資料，元件不含資料邏輯，
// 故可用於球隊頁、賽前預覽、比較等情境。視覺與互動三者一致：同寬格位、同字級、hover/focus/點擊同邏輯。
import Link from "next/link";
import { FieldDiagram, type FieldCellContent, type FieldCells } from "@/components/field-diagram";

export type RosterCell = { id: string; name: string | null; badge: string; stat?: string | null };
export type RosterGroup = {
  label: string;
  cells: RosterCell[];
  /** 於本組上方畫分隔線，區隔前一段（例：替補野手與投手分工）。 */
  divider?: boolean;
};

// 單一球員格位卡：左角色徽章 + 分隔線 + 主名 + 副數據（OPS+／ERA+）。整卡連向球員頁。
// 互動邏輯與守備圖格位一致：hover 淡 accent 底、focus-visible accent 外框。
export function RoleCell({ id, name, badge, stat }: RosterCell) {
  return (
    <Link href={`/players/${id}`}
      className="flex items-stretch overflow-hidden rounded-md border border-line-strong bg-surface transition hover:bg-accent/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent">
      <span className="flex w-8 shrink-0 items-center justify-center border-r border-line font-mono text-[9px] font-semibold text-muted">{badge}</span>
      <span className="min-w-0 flex-1 px-2 py-1 leading-tight">
        <span className="block truncate text-[11px] font-medium text-ink">{name ?? "—"}</span>
        {stat && <span className="block font-mono text-[9px] text-faint">{stat}</span>}
      </span>
    </Link>
  );
}

export function RosterBoard({ fieldCells, designatedHitter, caption, groups, emptyField = "尚無守備資料。" }: {
  /** 九守位顯示內容（守備位置圖）。 */
  fieldCells: FieldCells;
  /** 指定打擊（守備圖捕手旁另列）。 */
  designatedHitter?: FieldCellContent | null;
  /** 守備圖 aria-label 情境描述。 */
  caption?: string;
  /** 右側角色分組（先發/中繼/後援/替補…），每組一列等寬格位卡。 */
  groups: RosterGroup[];
  /** 無守備資料時的替代文字。 */
  emptyField?: string;
}) {
  const hasField = Object.keys(fieldCells).length > 0;
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="grid gap-x-6 gap-y-5 lg:grid-cols-[360px_1fr]">
        {hasField ? (
          <FieldDiagram cells={fieldCells} designatedHitter={designatedHitter} caption={caption}
            className="mx-auto w-full max-w-[360px] self-start" />
        ) : (
          <p className="self-start px-4 py-6 text-center text-sm text-muted">{emptyField}</p>
        )}
        <div className="space-y-3.5">
          {groups.map((g) => (
            <div key={g.label} className={g.divider ? "border-t border-line pt-3.5" : undefined}>
              <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-muted">{g.label}</h3>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(6.5rem,1fr))] gap-1.5">
                {g.cells.map((c) => <RoleCell key={c.id} {...c} />)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
