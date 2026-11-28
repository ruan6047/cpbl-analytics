"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Skeleton } from "@/components/ui";
import { CLIENT_API } from "@/lib/client";
import {
  DRAWER_COPY,
  drawerState,
  drawerStatLine,
  drawerSubtitle,
  playerHref,
  rosterPlayerPath,
  type RosterMember,
  type RosterPlayerDetail,
  type RosterScope,
} from "@/lib/playoffs-roster";
import { teamColor } from "@/lib/teams";

// #286 S05 WP4：第 3 區能力／走勢抽屜（按需詳情；需求方 Q3、#285 掛點契約 §2.2、§2.3）。
//
// - #467：原生 `<dialog>`＋`showModal()`（top layer，不再 portal）：375／390 全高度底部抽屜、右上角關閉；md 以上同元件改右側面板。
//   Escape（原生 cancel）與焦點限制（dialog 外 inert）交給瀏覽器；點背景（target＝dialog 本身）關閉；
//   關閉後焦點回原小卡按鈕（由呼叫端 `onClose` 歸還）。背景捲動鎖見下方 useBodyScrollLock（iOS 實測理由）。
// - 詳情以 `CLIENT_API`＋`no-store` 按需取，不隨 30 秒輪詢重取；區資料更新時抽屜不關、不搶焦點。
//   詳情 `context_version` ≠ 目前區資料 ⇒「資料已更新，請重開」，⛔ 拼接不同版本。
// - #350：主視圖只列人名，個人數值（本範圍 G、ERA·局數或 AVG·OPS、主守位出賽、DH 先發）放標頭第二行，取自摘要 member。
// - #415：雷達／走勢（recharts）收進 `roster-charts.tsx`，以 `next/dynamic(ssr:false)` 按需載入——`/playoffs` 首載
//   不再帶 recharts；抽屜掛載時即預載該 chunk，與詳情 API 平行。chunk 未到時以等高 `Skeleton` 佔位。

// 同一個 loader 給 dynamic 與預載用：webpack 對同一 import() 只產生一個 chunk，預載與渲染共用。
// ⛔ 本檔不得靜態 import `./roster-charts`、`ability-card`、`trend`（會把 recharts 拉回 `/playoffs` 首載；見 roster-drawer.test.ts）。
const loadRosterCharts = () => import("./roster-charts");
const RosterCharts = dynamic(loadRosterCharts, { ssr: false, loading: () => <RosterChartsSkeleton /> });

/**
 * 圖表 chunk 尚未到達時的等高佔位（UI_UX_SYSTEM §1 原則 8、§10.4：只用 `Skeleton`，不塌陷）。
 * 高度對齊 ready 態：能力區標題（h-5）＋ compact 雷達容器 `h-36`；走勢卡 `card p-4`＋卡頭列（h-7 ≈ 指標下拉）＋ `mb-3`
 * ＋ 圖表 `CHART_H`（220px）。
 */
function RosterChartsSkeleton() {
  return (
    <div className="space-y-4" aria-hidden data-testid="roster-charts-skeleton">
      <div className="space-y-2">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-36 w-full" />
      </div>
      <div className="card p-4">
        <Skeleton className="mb-3 h-7 w-44" />
        <Skeleton className="h-[220px] w-full" />
      </div>
    </div>
  );
}

/**
 * 背景捲動鎖（#467 WP5 採 L3：保留改前的 JS 鎖）。
 *
 * ⛔ 刻意保留、不是遺漏：showModal() 本身不擋背景捲動，純 CSS 的兩級在 iOS 模擬器實測都擋不住名單抽屜——
 * L1（dialog／::backdrop 的 overscroll-behavior: contain）在 iOS 27.2 擋不住；L2（再加 html:has(dialog:modal)
 * { overflow: hidden }）在 27.2 擋得住、在 26.5 擋不住。iOS 26.5 與 27.2 實測只有 body position:fixed 擋得住
 * （證據：~/.wf-evidence/cpbl-analytics/467/evidence/ 的 WP5 紀錄）。需求方裁定「背景不可捲動」優先於「移除捲動鎖」，
 * 驗收 3 放寬條款允許保留最小形式的鎖並註明理由。關閉時還原捲動位置。
 */
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

export function RosterDrawer({ member, scope = "background", year, series, sectionVersion, sectionRosterVersion, onClose }: {
  member: RosterMember;
  /** 目前名單區的資料範圍（標頭個人數值跟著它）。 */
  scope?: RosterScope;
  year: number;
  series: "E" | "C";
  /** 目前區資料的 `context_version`（輪詢更新時會變；抽屜不關，只比對版本）。 */
  sectionVersion: string | null;
  sectionRosterVersion: string;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  // close 事件是非同步派送的：卸載時我們自己 close() 的那次，以及 StrictMode 開發模式「掛載→清理→再掛載」
  // 清理時 close()、再掛載又 showModal() 之後才到的那次，都不得回呼 onClose（否則抽屜一開就關）。
  // 只有 dialog 真的被瀏覽器關掉（仍掛載且已非 open）才回呼。
  const unmounting = useRef(false);
  const [detail, setDetail] = useState<RosterPlayerDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useBodyScrollLock();

  // layout effect：在首次繪製前進 top layer（未 open 的 dialog 為 display:none，不會閃一格）。
  // `!open` 防 StrictMode 重跑 effect 時重複 showModal（已 open 再呼叫會丟 InvalidStateError）。
  useLayoutEffect(() => {
    const dialog = dialogRef.current!;
    unmounting.current = false;
    if (!dialog.open) dialog.showModal();
    // showModal() 已把焦點給第一個可聚焦元素（＝關閉鈕），但 iOS Safari 會因此畫出 :focus-visible 環（改前點擊開啟時沒有）。
    // 先 blur 再以 focusVisible:false 聚焦同一顆，照改前視覺不畫；鍵盤操作 Tab 移動後仍照常顯示。
    // TS 的 lib.dom 尚未收這個 FocusOptions 欄位，故轉型。
    const close = closeRef.current;
    close?.blur();
    close?.focus({ focusVisible: false } as FocusOptions);
    return () => {
      unmounting.current = true;
      if (dialog.open) dialog.close();
    };
  }, []);

  // #415：抽屜一開就預載圖表 chunk，與下方詳情 fetch 平行（不等 ready 態才開始下載）。
  useEffect(() => { void loadRosterCharts(); }, []);

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

  const state = drawerState(detail, failed, sectionVersion, sectionRosterVersion);
  const headingId = `roster-drawer-${member.player_id}`;
  // dialog 鋪滿視窗、本身透明不留 padding：點到 dialog 本身（面板以外）＝點背景；遮罩色由 ::backdrop 提供。
  // UA 預設的 margin／max-*／border／padding／底色全歸零，視覺與改前相同。`open:flex`：未 open 時維持 UA 的 display:none。
  return (
    <dialog ref={dialogRef} data-roster-drawer={member.player_id} aria-labelledby={headingId}
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClose={() => { if (!unmounting.current && !dialogRef.current?.open) onClose(); }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="fixed inset-0 m-0 h-full max-h-none w-full max-w-none items-end overflow-hidden border-0 bg-transparent p-0 text-ink backdrop:bg-ink/40 open:flex md:items-stretch md:justify-end">
      <div className="relative flex h-full w-full flex-col overflow-hidden bg-paper shadow-xl md:w-[min(640px,100vw)]">
        <div className="flex items-start gap-3 border-b border-line px-4 py-3">
          <span aria-hidden className="mt-1 inline-block h-6 w-1 shrink-0 rounded-sm" style={{ background: teamColor(detail?.team_code) }} />
          <div className="min-w-0 flex-1">
            <h2 id={headingId} className="truncate text-lg font-bold text-ink">{member.name}</h2>
            <p className="text-xs text-muted">
              {drawerSubtitle(member)}
            </p>
            <p className="font-mono text-xs tabular-nums text-ink" data-drawer-stats>
              {drawerStatLine(member, scope)}
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
    </dialog>
  );
}

function DrawerBody({ state, member }: { state: ReturnType<typeof drawerState>; member: RosterMember }) {
  if (state.kind === "loading") return <p role="status" className="text-sm text-muted">{DRAWER_COPY.loading}</p>;
  if (state.kind === "error") return <p role="status" className="text-sm text-muted">{DRAWER_COPY.failed}</p>;
  if (state.kind === "stale") return <p role="status" className="text-sm text-ink">{DRAWER_COPY.stale}</p>;
  return (
    <>
      <RosterCharts detail={state.detail} />
      <Link href={playerHref(member)} className="inline-flex min-h-11 items-center font-semibold text-accent underline underline-offset-4">
        {DRAWER_COPY.deepLink}
      </Link>
    </>
  );
}

export default RosterDrawer;
