"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { AbilityCard } from "@/components/ability-card";
import { SeasonTrendCard } from "@/app/players/[id]/trend";
import { CLIENT_API } from "@/lib/client";
import {
  DRAWER_COPY,
  drawerState,
  drawerSubtitle,
  pickAbility,
  playerHref,
  rosterPlayerPath,
  trapFocus,
  type RosterMember,
  type RosterPlayerDetail,
} from "@/lib/playoffs-roster";
import { teamColor } from "@/lib/teams";

// #286 S05 WP4：第 3 區能力／走勢抽屜（按需詳情；需求方 Q3、#285 掛點契約 §2.2、§2.3）。
//
// - `createPortal(document.body)`、`fixed inset-0 z-50`：375／390 全高度底部抽屜、右上角關閉；md 以上同元件改右側面板。
// - `role="dialog"`、`aria-modal`、焦點陷阱、Escape／點背景關閉、關閉後焦點回原小卡按鈕（由呼叫端 `onClose` 歸還）、
//   背景捲動鎖（iOS Safari 用 position:fixed 鎖，關閉時還原捲動位置）。
// - 詳情以 `CLIENT_API`＋`no-store` 按需取，不隨 30 秒輪詢重取；區資料更新時抽屜不關、不搶焦點。
//   詳情 `context_version` ≠ 目前區資料 ⇒「資料已更新，請重開」，⛔ 拼接不同版本。

const FOCUSABLE = 'a[href], button:not([disabled]), select, input, textarea, [tabindex]:not([tabindex="-1"])';

function useBodyScrollLock() {
  useLayoutEffect(() => {
    const { body } = document;
    const y = window.scrollY;
    const prev = { position: body.style.position, top: body.style.top, width: body.style.width, overflow: body.style.overflow };
    body.style.position = "fixed";
    body.style.top = `-${y}px`;
    body.style.width = "100%";
    body.style.overflow = "hidden";
    return () => {
      body.style.position = prev.position;
      body.style.top = prev.top;
      body.style.width = prev.width;
      body.style.overflow = prev.overflow;
      window.scrollTo(0, y);
    };
  }, []);
}

export function RosterDrawer({ member, year, series, sectionVersion, onClose }: {
  member: RosterMember;
  year: number;
  series: "E" | "C";
  /** 目前區資料的 `context_version`（輪詢更新時會變；抽屜不關，只比對版本）。 */
  sectionVersion: string | null;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [detail, setDetail] = useState<RosterPlayerDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useBodyScrollLock();

  // 只在開啟（或換人）時取一次；⛔ 依 sectionVersion 重取（版本不同就顯示請重開）。
  useEffect(() => {
    const ctrl = new AbortController();
    setDetail(null);
    setFailed(false);
    fetch(`${CLIENT_API}${rosterPlayerPath(year, series, member.player_id)}`, { cache: "no-store", signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: RosterPlayerDetail) => setDetail(d))
      .catch(() => { if (!ctrl.signal.aborted) setFailed(true); });
    return () => ctrl.abort();
  }, [year, series, member.player_id]);

  useEffect(() => { closeRef.current?.focus(); }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (e.key !== "Tab" || !panelRef.current) return;
      const els = [...panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
      const next = trapFocus(els.indexOf(document.activeElement as HTMLElement), els.length, e.shiftKey);
      if (next !== null) { e.preventDefault(); els[next]?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const state = drawerState(detail, failed, sectionVersion);
  const headingId = `roster-drawer-${member.player_id}`;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end md:items-stretch md:justify-end" data-roster-drawer={member.player_id}>
      <div aria-hidden className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={headingId}
        className="relative flex h-full w-full flex-col overflow-hidden bg-paper shadow-xl md:w-[min(640px,100vw)]">
        <div className="flex items-start gap-3 border-b border-line px-4 py-3">
          <span aria-hidden className="mt-1 inline-block h-6 w-1 shrink-0 rounded-sm" style={{ background: teamColor(detail?.team_code) }} />
          <div className="min-w-0 flex-1">
            <h2 id={headingId} className="truncate text-lg font-bold text-ink">{member.name}</h2>
            <p className="text-xs text-muted">
              {drawerSubtitle(member)}
            </p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label={DRAWER_COPY.close}
            className="-mr-2 -mt-1 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent">
            <svg aria-hidden viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4">
          <DrawerBody state={state} member={member} />
        </div>
      </div>
    </div>,
    document.body,
  );
}

function DrawerBody({ state, member }: { state: ReturnType<typeof drawerState>; member: RosterMember }) {
  if (state.kind === "loading") return <p role="status" className="text-sm text-muted">{DRAWER_COPY.loading}</p>;
  if (state.kind === "error") return <p role="status" className="text-sm text-muted">{DRAWER_COPY.failed}</p>;
  if (state.kind === "stale") return <p role="status" className="text-sm text-ink">{DRAWER_COPY.stale}</p>;
  const d = state.detail;
  const ab = pickAbility(d);
  return (
    <>
      <section aria-label={ab?.label ?? DRAWER_COPY.abilitySeason} className="space-y-2">
        <h3 className="text-sm font-bold text-muted">{ab?.label ?? DRAWER_COPY.abilitySeason}</h3>
        {ab ? <AbilityCard card={ab.card} color={teamColor(d.team_code)} compact />
          : <p className="text-sm text-muted">{DRAWER_COPY.abilityNone}</p>}
      </section>
      {d.trend ? (
        // 包一層：SeasonTrendCard 的 Card 是 h-full，直接放在捲動區會被撐成整個抽屜高。
        <div><SeasonTrendCard trend={d.trend.items} role={d.player.role} isRetired={false} /></div>
      ) : null}
      <Link href={playerHref(member)} className="inline-flex min-h-11 items-center font-semibold text-accent underline underline-offset-4">
        {DRAWER_COPY.deepLink}
      </Link>
    </>
  );
}

export default RosterDrawer;
