"use client";

// /matchups 查詢式對戰頁（UX-MATCHUP1；UX-MATCHUP2 抽離共用面板後的 host）。
// 流程：選視角 → 搜尋主角 → 選資料範圍／賽事類型 → 對某隊或對某人。
// 查詢面板（控制列＋基礎實績＋洞察＋單組對決）由共用 MatchupExplorer 負責；
// 本檔只保留跨球員入口的專屬職責：視角切換、主角搜尋，與「URL 即狀態」的
// deep-link adapter（可分享）。
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  matchupApi,
  type Kind,
  type Role,
  type SortKey,
} from "@/components/matchups/api";
import {
  CURRENT_YEAR,
  DEFAULT_CONTROLS,
  type ControlsPatch,
  type MatchupControls,
} from "@/components/matchups/controls";
import MatchupExplorer from "@/components/matchups/explorer";
import SearchCombobox, { type ComboHit } from "@/components/matchups/search-combobox";
import { ContextSwitcher } from "@/components/hierarchical-tabs";
import { NavBarRow, StickyNavBar } from "@/components/sticky-nav-bar";

const SORT_KEYS: SortKey[] = ["plate_appearances", "avg", "ops", "home_runs", "so"];

// 視角標籤（§4.3 Phase 4 對齊：共享 role 軸改用 canonical ContextSwitcher，
// 取代先前手刻 Toggle；explorer 專屬控制不動）。
const ROLE_LABEL: Record<Role, string> = { batting: "打者對投手", pitching: "投手對打者" };

export default function MatchupsClient() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();

  // ---- URL 即狀態（deep-link 唯一事實來源） ----
  const role: Role = sp.get("role") === "pitching" ? "pitching" : "batting";
  const pid = sp.get("pid") ?? "";
  const sortRaw = sp.get("sort") as SortKey | null;
  const controls: MatchupControls = useMemo(() => {
    const scopeRaw = sp.get("scope");
    return {
      kind: sp.get("kind") === "C" ? "C" : sp.get("kind") === "E" ? "E" : "A",
      scope: scopeRaw === "career" || scopeRaw === "range" ? scopeRaw : "season",
      fromYear: Number(sp.get("from")) || CURRENT_YEAR - 1,
      toYear: Number(sp.get("to")) || CURRENT_YEAR,
      team: sp.get("team"),
      opp: sp.get("opp"),
      pick: sp.get("pick") === "1",
      sort: sortRaw && SORT_KEYS.includes(sortRaw) ? sortRaw : "plate_appearances",
      order: sp.get("order") === "asc" ? "asc" : "desc",
    };
  }, [sp, sortRaw]);

  const setParams = useCallback(
    (patch: Record<string, string | null>, mode: "replace" | "push" = "replace") => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null) next.delete(k);
        else next.set(k, v);
      }
      const qs = next.toString();
      router[mode](qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [sp, router, pathname],
  );

  // 共用面板的控制補丁 → URL 參數（預設值不寫進 URL，維持既有網址形狀）
  const onPatch = useCallback(
    (patch: ControlsPatch, mode: "replace" | "push" = "replace") => {
      const out: Record<string, string | null> = {};
      if (patch.kind !== undefined) out.kind = patch.kind === "A" ? null : patch.kind;
      if (patch.scope !== undefined) {
        out.scope = patch.scope === "season" ? null : patch.scope;
        if (patch.scope !== "range") {
          out.from = null;
          out.to = null;
        }
      }
      if (patch.fromYear !== undefined) out.from = String(patch.fromYear);
      if (patch.toYear !== undefined) out.to = String(patch.toYear);
      if (patch.team !== undefined) out.team = patch.team;
      if (patch.opp !== undefined) out.opp = patch.opp;
      if (patch.pick !== undefined) out.pick = patch.pick ? "1" : null;
      if (patch.sort !== undefined)
        out.sort = patch.sort === DEFAULT_CONTROLS.sort ? null : patch.sort;
      if (patch.order !== undefined) out.order = patch.order === "desc" ? null : patch.order;
      setParams(out, mode);
    },
    [setParams],
  );

  // ---- 主角名稱（cold deep-link 時補抓 profile） ----
  const [subjectName, setSubjectName] = useState<string | null>(null);
  useEffect(() => {
    if (!pid) {
      setSubjectName(null);
      return;
    }
    let stale = false;
    matchupApi
      .playerName(pid)
      .then((n) => {
        if (!stale) setSubjectName(n);
      })
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [pid]);

  // ---- 主角搜尋 ----
  const subjectFetcher = useCallback(
    async (q: string): Promise<ComboHit[]> => {
      const d = await matchupApi.searchRoster(role, q);
      return d.items.map((p) => ({ id: p.id, name: p.name ?? p.id, team: p.team, hint: null }));
    },
    [role],
  );

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">投打對決</h1>
        <p className="mt-1.5 text-sm text-muted">
          搜尋一位球員，查他對特定球隊或特定{role === "batting" ? "投手" : "打者"}
          的歷史對戰樣本與基礎實績；通過統計閘門時，另以加值卡標示值得注意的對位。
        </p>
      </header>

      <StickyNavBar label="對決導覽">
        <NavBarRow
          main={
            <ContextSwitcher
              label="視角"
              values={["batting", "pitching"] as const}
              value={role}
              render={(v) => ROLE_LABEL[v]}
              onChange={(v) =>
                // 換視角＝換母體：清空主角與對手
                setParams({
                  role: v === "batting" ? null : v,
                  pid: null,
                  opp: null,
                  team: null,
                  sort: null,
                  order: null,
                })
              }
            />
          }
        />
      </StickyNavBar>

      <MatchupExplorer
        pid={pid}
        role={role}
        subjectName={subjectName}
        controls={controls}
        onPatch={onPatch}
        header={
          <>
            <SearchCombobox
              label={`搜尋${role === "batting" ? "打者" : "投手"}`}
              placeholder={`輸入${role === "batting" ? "打者" : "投手"}姓名或隊伍…`}
              fetcher={subjectFetcher}
              selected={pid ? { id: pid, name: subjectName ?? pid } : null}
              onSelect={(h) => {
                setSubjectName(h.name);
                setParams({ pid: h.id, opp: null }, "push");
              }}
              onClear={() => setParams({ pid: null, opp: null })}
            />
          </>
        }
      />
    </div>
  );
}
