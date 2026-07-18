"use client";

// /matchups 查詢式對戰頁（UX-MATCHUP1）。
// 流程：選視角 → 搜尋主角 → 選資料範圍／賽事類型 → 對某隊或對某人。
// 基礎實績（樣本與逐對手成績）是常態 hero；ML-MATCHUP1 洞察只是加值層，
// fail-closed 四狀態是常態版面。查詢狀態全放 URL（deep-link 可分享）。
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui";
import { KIND_LABEL } from "@/lib/client";
import {
  matchupApi,
  type FranchiseInfo,
  type InsightsResponse,
  type Kind,
  type MatchupList,
  type MatchupQuery,
  type MatchupRow,
  type PairDetail,
  type Role,
  type SortKey,
} from "./api";
import InsightSection from "./insight-section";
import OpponentsTable from "./opponents-table";
import PairCard from "./pair-card";
import SearchCombobox, { type ComboHit } from "./search-combobox";

const CURRENT_YEAR = new Date().getFullYear();
const MIN_YEAR = 1990; // 對戰資料源下限（cpbl-opendata／官網彙總最早年）
const YEARS = Array.from({ length: CURRENT_YEAR - MIN_YEAR + 1 }, (_, i) => CURRENT_YEAR - i);
const SORT_KEYS: SortKey[] = ["plate_appearances", "avg", "ops", "home_runs", "so"];
const PREVIEW_ROWS = 30;

function Toggle<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { v: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="inline-flex gap-1 rounded-lg bg-surface-2 p-1" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          aria-pressed={value === o.v}
          className={`rounded-md px-3 py-1 text-sm transition ${
            value === o.v ? "bg-ink font-medium text-paper" : "text-muted hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      {label}
      {children}
    </label>
  );
}

const selectCls =
  "rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-ink";

export default function MatchupsClient() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();

  // ---- URL 即狀態（deep-link 唯一事實來源） ----
  const role: Role = sp.get("role") === "pitching" ? "pitching" : "batting";
  const kind: Kind = sp.get("kind") === "C" ? "C" : sp.get("kind") === "E" ? "E" : "A";
  const scopeRaw = sp.get("scope");
  const scope = scopeRaw === "career" || scopeRaw === "range" ? scopeRaw : "season";
  const fromYear = Number(sp.get("from")) || CURRENT_YEAR - 1;
  const toYear = Number(sp.get("to")) || CURRENT_YEAR;
  const pid = sp.get("pid") ?? "";
  const team = sp.get("team");
  const opp = sp.get("opp");
  const sortRaw = sp.get("sort") as SortKey | null;
  const sort: SortKey = sortRaw && SORT_KEYS.includes(sortRaw) ? sortRaw : "plate_appearances";
  const order: "asc" | "desc" = sp.get("order") === "asc" ? "asc" : "desc";

  const query: MatchupQuery = useMemo(
    () => ({ role, kind, scope, fromYear: scope === "range" ? fromYear : null, toYear: scope === "range" ? toYear : null }),
    [role, kind, scope, fromYear, toYear],
  );

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

  // ---- 名稱（cold deep-link 時補抓 profile） ----
  const [names, setNames] = useState<Record<string, string>>({});
  const rememberName = useCallback((id: string, name: string | null) => {
    if (name) setNames((m) => (m[id] === name ? m : { ...m, [id]: name }));
  }, []);
  useEffect(() => {
    for (const id of [pid, opp]) {
      if (id && !names[id]) {
        matchupApi.playerName(id).then((n) => rememberName(id, n)).catch(() => {});
      }
    }
  }, [pid, opp, names, rememberName]);

  // ---- 資料抓取 ----
  const [franchises, setFranchises] = useState<FranchiseInfo[]>([]);
  useEffect(() => {
    matchupApi.franchises().then((d) => setFranchises(d.items)).catch(() => setFranchises([]));
  }, []);

  const [list, setList] = useState<MatchupList | null>(null);
  const [listErr, setListErr] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  useEffect(() => {
    if (!pid) {
      setList(null);
      return;
    }
    let stale = false;
    setListLoading(true);
    setListErr(false);
    matchupApi
      .list(pid, query, { team, sort, order })
      .then((d) => {
        if (!stale) setList(d);
      })
      .catch(() => {
        if (!stale) {
          setList(null);
          setListErr(true);
        }
      })
      .finally(() => {
        if (!stale) setListLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [pid, query, team, sort, order]);

  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [insightsErr, setInsightsErr] = useState(false);
  useEffect(() => {
    if (!pid || opp) {
      setInsights(null);
      return;
    }
    let stale = false;
    setInsights(null);
    setInsightsErr(false);
    matchupApi
      .insights(pid, query, team)
      .then((d) => {
        if (!stale) setInsights(d);
      })
      .catch(() => {
        if (!stale) setInsightsErr(true);
      });
    return () => {
      stale = true;
    };
  }, [pid, opp, query, team]);

  const [pair, setPair] = useState<PairDetail | null>(null);
  const [pairErr, setPairErr] = useState(false);
  useEffect(() => {
    if (!pid || !opp) {
      setPair(null);
      return;
    }
    let stale = false;
    setPair(null);
    setPairErr(false);
    const hitter = role === "batting" ? pid : opp;
    const pitcher = role === "batting" ? opp : pid;
    matchupApi
      .pair(hitter, pitcher, query)
      .then((d) => {
        if (!stale) {
          setPair(d);
          rememberName(opp, role === "batting" ? d.items[0]?.pitcher_name ?? null : d.items[0]?.hitter_name ?? null);
        }
      })
      .catch(() => {
        if (!stale) setPairErr(true);
      });
    return () => {
      stale = true;
    };
  }, [pid, opp, role, query, rememberName]);

  // ---- 搜尋 fetchers ----
  const subjectFetcher = useCallback(
    async (q: string): Promise<ComboHit[]> => {
      const d = await matchupApi.searchRoster(role, q);
      return d.items.map((p) => ({ id: p.id, name: p.name ?? p.id, team: p.team, hint: null }));
    },
    [role],
  );

  // 對某人：優先列「已交手對手」（含退役者），再補當季名單搜尋
  const oppRole: Role = role === "batting" ? "pitching" : "batting";
  const oppLabel = role === "batting" ? "投手" : "打者";
  const listItems = list?.items;
  const opponentFetcher = useCallback(
    async (q: string): Promise<ComboHit[]> => {
      const local: ComboHit[] = (listItems ?? [])
        .filter((r) => (r.opp_name ?? "").includes(q))
        .slice(0, 8)
        .map((r) => ({
          id: r.opp_id,
          name: r.opp_name ?? r.opp_id,
          team: r.opp_team,
          hint: `已交手 ${r.plate_appearances} 打席`,
        }));
      let remote: ComboHit[] = [];
      try {
        const d = await matchupApi.searchRoster(oppRole, q, 8);
        remote = d.items.map((p) => ({ id: p.id, name: p.name ?? p.id, team: p.team, hint: null }));
      } catch {
        // 當季名單搜尋失敗時仍回傳已交手清單
      }
      const seen = new Set(local.map((h) => h.id));
      return [...local, ...remote.filter((h) => !seen.has(h.id))];
    },
    [listItems, oppRole],
  );

  // ---- 顯示輔助 ----
  const scopeLabel =
    scope === "season" ? "本季" : scope === "career" ? "生涯" : `${fromYear}–${toYear} 年`;
  const contextLabel = `${scopeLabel}・${KIND_LABEL[kind]}`;
  const subjectName = pid ? names[pid] ?? pid : null;
  const teamName = team ? franchises.find((f) => f.code === team)?.name ?? team : null;
  const [showAll, setShowAll] = useState(false);
  useEffect(() => setShowAll(false), [pid, role, kind, scope, team]);

  // 對手模式：選定 opp 或 pick=1（搜尋中）＝對某人；team＝對某隊；否則全部
  const pick = sp.get("pick") === "1";
  const oppMode: "all" | "team" | "person" = opp || pick ? "person" : team ? "team" : "all";

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">投打對決</h1>
        <p className="mt-1.5 text-sm text-muted">
          搜尋一位球員，查他對特定球隊或特定{oppLabel}的歷史對戰樣本與基礎實績；
          通過統計閘門時，另以加值卡標示值得注意的對位。
        </p>
      </header>

      {/* 查詢列 */}
      <div className="card mb-6 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <Toggle<Role>
            label="視角"
            options={[
              { v: "batting", label: "打者對投手" },
              { v: "pitching", label: "投手對打者" },
            ]}
            value={role}
            onChange={(v) =>
              // 換視角＝換母體：清空主角與對手
              setParams({ role: v === "batting" ? null : v, pid: null, opp: null, team: null, sort: null, order: null })
            }
          />
          <SearchCombobox
            label={`搜尋${role === "batting" ? "打者" : "投手"}`}
            placeholder={`輸入${role === "batting" ? "打者" : "投手"}姓名或隊伍…`}
            fetcher={subjectFetcher}
            selected={pid ? { id: pid, name: subjectName ?? pid } : null}
            onSelect={(h) => {
              rememberName(h.id, h.name);
              setParams({ pid: h.id, opp: null }, "push");
            }}
            onClear={() => setParams({ pid: null, opp: null })}
          />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-3">
          <Field label="資料範圍">
            <select
              className={selectCls}
              value={scope}
              onChange={(e) => {
                const v = e.target.value;
                setParams({
                  scope: v === "season" ? null : v,
                  from: v === "range" ? String(fromYear) : null,
                  to: v === "range" ? String(toYear) : null,
                });
              }}
            >
              <option value="season">本季</option>
              <option value="career">生涯</option>
              <option value="range">指定年度範圍</option>
            </select>
          </Field>
          {scope === "range" && (
            <div className="flex items-center gap-1.5">
              <Field label="從">
                <select
                  className={selectCls}
                  value={fromYear}
                  onChange={(e) =>
                    setParams({
                      from: e.target.value,
                      to: String(Math.max(Number(e.target.value), toYear)),
                    })
                  }
                >
                  {YEARS.map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </Field>
              <Field label="到">
                <select
                  className={selectCls}
                  value={toYear}
                  onChange={(e) =>
                    setParams({
                      to: e.target.value,
                      from: String(Math.min(Number(e.target.value), fromYear)),
                    })
                  }
                >
                  {YEARS.map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </Field>
            </div>
          )}
          <Field label="賽事類型">
            <select
              className={selectCls}
              value={kind}
              onChange={(e) => setParams({ kind: e.target.value === "A" ? null : e.target.value })}
            >
              {(["A", "E", "C"] as Kind[]).map((k) => (
                <option key={k} value={k}>{KIND_LABEL[k]}</option>
              ))}
            </select>
          </Field>
          <Field label="對手">
            <select
              className={selectCls}
              value={oppMode === "person" ? "person" : team ?? "all"}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "all") setParams({ team: null, opp: null, pick: null });
                else if (v === "person") setParams({ team: null, pick: "1" });
                else setParams({ team: v, opp: null, pick: null });
              }}
            >
              <option value="all">全部球隊</option>
              {franchises.map((f) => (
                <option key={f.code} value={f.code}>
                  {f.name}
                  {f.active ? "" : `（${f.from}–${f.to}）`}
                </option>
              ))}
              <option value="person">找特定{oppLabel}…</option>
            </select>
          </Field>
        </div>

        {/* 對某人：搜尋框（未選定對手時） */}
        {pid && !opp && pick && (
          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3">
            <span className="text-xs text-muted">指定對手：</span>
            <SearchCombobox
              label={`搜尋對手${oppLabel}`}
              placeholder={`輸入${oppLabel}姓名（已交手者優先）…`}
              fetcher={opponentFetcher}
              selected={null}
              onSelect={(h) => {
                rememberName(h.id, h.name);
                setParams({ opp: h.id }, "push");
              }}
              onClear={() => {}}
              autoFocus
            />
          </div>
        )}
      </div>

      {/* 結果區 */}
      {!pid && (
        <EmptyState>
          先搜尋並選定一位{role === "batting" ? "打者" : "投手"}，即可查詢對戰樣本與基礎實績。
        </EmptyState>
      )}

      {pid && opp && (
        <div>
          <button
            type="button"
            onClick={() => setParams({ opp: null })}
            className="mb-3 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-muted transition hover:text-ink"
          >
            ← 返回對手清單
          </button>
          {pairErr && <ErrorState>對決資料載入失敗，請重試。</ErrorState>}
          {!pair && !pairErr && <TableSkeleton rows={4} cols={4} />}
          {/* 對決卡自身分 A/C/E 段呈現，範圍標籤只帶資料範圍不帶賽事類型 */}
          {pair && <PairCard data={pair} role={role} scopeLabel={scopeLabel} />}
        </div>
      )}

      {pid && !opp && (
        <>
          <section aria-labelledby="record-heading">
            <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 id="record-heading" className="text-lg font-bold text-ink">
                {subjectName ?? "…"}：對戰{oppLabel}基礎實績
              </h2>
              <span className="text-sm text-muted">
                {contextLabel}
                {teamName ? `・限 ${teamName}` : ""}
              </span>
              {list && (
                <span className="text-xs text-faint">
                  共 {list.available_count} 位對手・此球員對戰資料涵蓋：
                  {list.coverage.career ? "生涯彙總" : ""}
                  {list.coverage.career && list.coverage.annual_years.length ? "＋" : ""}
                  {list.coverage.annual_years.length ? `年度 ${list.coverage.annual_years.join("、")}` : ""}
                  {!list.coverage.career && list.coverage.annual_years.length === 0 ? "無" : ""}
                </span>
              )}
            </div>

            {listErr && <ErrorState>對戰資料載入失敗，請重試。</ErrorState>}
            {listLoading && <TableSkeleton rows={8} cols={7} />}

            {list && !listLoading && list.items.length === 0 && (
              <EmptyState>
                {subjectName ?? "該球員"}在「{contextLabel}
                {teamName ? `・${teamName}` : ""}」查無對戰紀錄。
                {scope === "range" && (
                  <span className="mt-1 block text-xs">
                    官網對戰資料僅提供本季年度列與生涯彙總
                    {list.coverage.annual_years.length
                      ? `（此球員年度資料涵蓋：${list.coverage.annual_years.join("、")}）`
                      : ""}
                    ，歷史年度區間多半無資料；可改查「生涯」或「本季」。
                  </span>
                )}
              </EmptyState>
            )}

            {list && !listLoading && list.items.length > 0 && (
              <>
                <OpponentsTable
                  rows={showAll ? list.items : list.items.slice(0, PREVIEW_ROWS)}
                  role={role}
                  sort={sort}
                  order={order}
                  onSort={(key) =>
                    setParams(
                      key === sort
                        ? { order: order === "desc" ? "asc" : null }
                        : { sort: key === "plate_appearances" ? null : key, order: null },
                    )
                  }
                  onPick={(r) => {
                    rememberName(r.opp_id, r.opp_name);
                    setParams({ opp: r.opp_id }, "push");
                  }}
                />
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted">
                  {list.items.length > PREVIEW_ROWS && (
                    <button
                      type="button"
                      onClick={() => setShowAll((v) => !v)}
                      className="rounded-lg border border-line bg-surface px-2.5 py-1 transition hover:text-ink"
                    >
                      {showAll ? "收合清單" : `顯示全部 ${list.items.length} 位`}
                    </button>
                  )}
                  {list.available_count > list.items.length && (
                    <span>
                      另有 {list.available_count - list.items.length} 位樣本較小的對手未列出
                      （單次查詢上限 200 位）；可用「找特定{oppLabel}」直接指定。
                    </span>
                  )}
                </div>
              </>
            )}
          </section>

          {insightsErr && (
            <p className="mt-8 text-sm text-faint">洞察服務暫時無法載入；基礎實績不受影響。</p>
          )}
          {insights && (
            <InsightSection
              data={insights}
              role={role}
              teamFilterName={teamName}
              onPickOpponent={(id, name) => {
                rememberName(id, name);
                setParams({ opp: id }, "push");
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
