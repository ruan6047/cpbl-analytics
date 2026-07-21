"use client";

// 對戰查詢面板（UX-MATCHUP2 自 /matchups 抽離的共用元件）。
// 給定主角（pid＋role）後，負責：範圍／賽事／對手控制列、對手清單（基礎實績
// hero）、ML-MATCHUP1 洞察（fail-closed 常態版面）、單組對決卡與全部空／錯誤
// 狀態。/matchups 與球員頁共用此面板，統計判定與空狀態只存在這一份（T4 紅線：
// 前端不得重做 EB 判斷，也不得在整合端另造空狀態）。
// 狀態由 host 持有（URL 或 local state），透過 controls／onPatch 受控。
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui";
import { KIND_LABEL } from "@/lib/client";
import {
  matchupApi,
  type FranchiseInfo,
  type InsightsResponse,
  type Kind,
  type MatchupList,
  type MatchupQuery,
  type PairDetail,
  type Role,
  type SortKey,
} from "./api";
import { CURRENT_YEAR, MIN_YEAR, type ControlsPatch, type MatchupControls } from "./controls";
import InsightSection from "./insight-section";
import OpponentsTable from "./opponents-table";
import PairCard from "./pair-card";
import SearchCombobox, { type ComboHit } from "./search-combobox";

const YEARS = Array.from({ length: CURRENT_YEAR - MIN_YEAR + 1 }, (_, i) => CURRENT_YEAR - i);
const PREVIEW_ROWS = 30;

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

export default function MatchupExplorer({
  pid,
  role,
  subjectName,
  controls,
  onPatch,
  header,
  compactInsight = false,
}: {
  /** 主角球員；空字串＝尚未選定（/matchups 首開），只顯示控制列與提示。 */
  pid: string;
  role: Role;
  subjectName: string | null;
  controls: MatchupControls;
  /** host 更新控制狀態；mode="push" 表示值得進瀏覽器歷史（選定對手）。 */
  onPatch: (patch: ControlsPatch, mode?: "replace" | "push") => void;
  /** 查詢卡頂部的 host 專屬列（/matchups 的視角切換＋主角搜尋）。 */
  header?: React.ReactNode;
  /** 球員頁用：洞察非 ok 態收合（fail-closed 在球員頁是次要加值層）。 */
  compactInsight?: boolean;
}) {
  const { kind, scope, fromYear, toYear, team, opp, pick, sort, order } = controls;
  const headingId = useId();

  const query: MatchupQuery = useMemo(
    () => ({ role, kind, scope, fromYear: scope === "range" ? fromYear : null, toYear: scope === "range" ? toYear : null }),
    [role, kind, scope, fromYear, toYear],
  );

  // ---- 對手名稱（cold deep-link 時補抓 profile；pair 回應也會回填） ----
  const [names, setNames] = useState<Record<string, string>>({});
  const rememberName = useCallback((id: string, name: string | null) => {
    if (name) setNames((m) => (m[id] === name ? m : { ...m, [id]: name }));
  }, []);
  useEffect(() => {
    if (opp && !names[opp]) {
      matchupApi.playerName(opp).then((n) => rememberName(opp, n)).catch(() => {});
    }
  }, [opp, names, rememberName]);

  // ---- 資料抓取 ----
  const [franchises, setFranchises] = useState<FranchiseInfo[]>([]);
  useEffect(() => {
    matchupApi.franchises().then((d) => setFranchises(d.items)).catch(() => setFranchises([]));
  }, []);

  const [list, setList] = useState<MatchupList | null>(null);
  const [listErr, setListErr] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  // 該主角在目前 role／範圍下實際交手過的球隊（franchise code）。
  // 只在「全部球隊」（未篩隊）時由完整對手清單推導，因為篩隊後只剩單一隊。
  // 用來把對手下拉收斂成「有對戰過的隊」，濾掉從未交手的解散隊與自家隊。
  const scopeKey = `${pid}|${role}|${kind}|${scope}|${query.fromYear}|${query.toYear}`;
  const [faced, setFaced] = useState<{ key: string; codes: string[] } | null>(null);
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
        if (stale) return;
        setList(d);
        if (!team) {
          const codes = new Set<string>();
          for (const r of d.items) if (r.opp_franchise) codes.add(r.opp_franchise);
          setFaced({ key: scopeKey, codes: [...codes] });
        }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scopeKey 由 query 諸欄位決定，query 已在依賴內
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

  // ---- 對某人：優先列「已交手對手」（含退役者），再補當季名單搜尋 ----
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
  const teamName = team ? franchises.find((f) => f.code === team)?.name ?? team : null;
  const [showAll, setShowAll] = useState(false);
  useEffect(() => setShowAll(false), [pid, role, kind, scope, team]);

  // 對手模式：選定 opp 或 pick（搜尋中）＝對某人；team＝對某隊；否則全部
  const oppMode: "all" | "team" | "person" = opp || pick ? "person" : team ? "team" : "all";

  // 對手隊下拉：已知交手隊時只列有對戰過的（含目前選定隊，避免 deep-link 選中卻被隱藏）；
  // 尚未載入完整清單時退回全部，避免空白。faced 需與目前範圍相符才採用。
  const facedCodes = faced && faced.key === scopeKey ? new Set(faced.codes) : null;
  const visibleFranchises = facedCodes
    ? franchises.filter((f) => facedCodes.has(f.code) || f.code === team)
    : franchises;

  return (
    <div>
      {/* 查詢列 */}
      <div className="card mb-6 p-4">
        {header && <div className="flex flex-wrap items-center gap-3">{header}</div>}

        <div
          className={`flex flex-wrap items-center gap-x-4 gap-y-2 ${
            header ? "mt-3 border-t border-line pt-3" : ""
          }`}
        >
          <Field label="資料範圍">
            <select
              className={selectCls}
              value={scope}
              onChange={(e) => {
                const v = e.target.value as MatchupControls["scope"];
                onPatch(v === "range" ? { scope: v, fromYear, toYear } : { scope: v });
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
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    onPatch({ fromYear: v, toYear: Math.max(v, toYear) });
                  }}
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
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    onPatch({ toYear: v, fromYear: Math.min(v, fromYear) });
                  }}
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
              onChange={(e) => onPatch({ kind: e.target.value as Kind })}
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
                if (v === "all") onPatch({ team: null, opp: null, pick: false });
                else if (v === "person") onPatch({ team: null, pick: true });
                else onPatch({ team: v, opp: null, pick: false });
              }}
            >
              <option value="all">全部球隊</option>
              {visibleFranchises.map((f) => (
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
                onPatch({ opp: h.id }, "push");
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
            onClick={() => onPatch({ opp: null })}
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
          <section aria-labelledby={headingId}>
            <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 id={headingId} className="text-lg font-bold text-ink">
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
                  onSort={(key: SortKey) =>
                    onPatch(
                      key === sort
                        ? { order: order === "desc" ? "asc" : "desc" }
                        : { sort: key, order: "desc" },
                    )
                  }
                  onPick={(r) => {
                    rememberName(r.opp_id, r.opp_name);
                    onPatch({ opp: r.opp_id }, "push");
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
              compact={compactInsight}
              onPickOpponent={(id, name) => {
                rememberName(id, name);
                onPatch({ opp: id }, "push");
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
