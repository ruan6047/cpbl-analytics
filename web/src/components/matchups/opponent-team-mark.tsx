// 對手交手隊別標示（#201）：清單、洞察候選與單組對決卡共用，同一對手在同畫面
// 不得出現互相矛盾的隊別。四態見 team-affiliation.ts。
import { TeamLogo } from "@/components/ui";
import { teamShort } from "@/lib/teams";
import type { TeamStatus } from "./api";
import { teamAffiliation } from "./team-affiliation";

export default function OpponentTeamMark({
  status,
  franchises,
  fallbackCode,
  size = 18,
}: {
  status?: TeamStatus | null;
  franchises?: readonly string[] | null;
  fallbackCode?: string | null;
  size?: number;
}) {
  const { codes, note } = teamAffiliation(status, franchises, fallbackCode);
  if (!status) return <TeamLogo code={fallbackCode} size={size} decorative />;
  const names = codes.map((c) => teamShort(c) || c).join("、");
  const label = note ? (names ? `${names}（${note}）` : note) : names;
  return (
    <span className="inline-flex shrink-0 items-center gap-0.5" title={label}>
      {names && <span className="sr-only">{names}</span>}
      {codes.map((c) => (
        <TeamLogo key={c} code={c} size={size} decorative />
      ))}
      {note && (
        <span className="ml-0.5 whitespace-nowrap rounded bg-surface-2 px-1 py-0.5 text-[10px] font-normal leading-none text-muted">
          {note}
        </span>
      )}
    </span>
  );
}
