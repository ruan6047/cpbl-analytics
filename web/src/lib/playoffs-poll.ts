// `/playoffs` 共用輪詢控制器（#285 S04）：純邏輯、可注入時鐘／可見性／取數，node test 直接驗。
//
// 規則（需求方 Q9「一律 30 秒」；PLAN r4 §2）：
// 1. 頁面可見時每 30 秒一輪；每輪先 overview、再（有掛第 4 區時）watch。
// 2. 頁面隱藏即停（中止進行中請求、不排程）；回到前景立即一輪再照常排程。
// 3. 失敗退避：30→60→120→240 秒封頂；任一輪成功歸零。被下一輪計時器取代的慢請求也算失敗。
// 4. 新一輪開始就中止上一輪（AbortController），並以 request token 丟棄晚到回應——
//    晚到的舊回應永遠不會上畫面。`?game` 變更同樣開新一輪。
// 5. 版本：watch 的 `context_version` ≠ 本輪 overview，或（目標場來自 overview 時）watch 回 `not_target`
//    ⇒ 先重取 overview、再重取 watch 一次；仍不一致 ⇒ 第 4 區保留上一份畫面並標「資料更新中」，
//    ⛔ 拼接不同版本。（PRD「重取 overview 後只重取受影響區」：watch 較新時只重取 watch 永遠追不上舊 overview。）
// 6. 更新只換資料，⛔ 捲動、⛔ 移焦點——那是呈現層的事，本檔只交出資料。
// 7. 第 2／3 區（registry 登記的區，#285 續做 PLAN r6 §3、MOUNT-CONTRACT r3 §3）：
//    - 第一次接近 viewport 才 `activate(id)`；未啟用的區請求數 0。啟用時立即一輪。
//    - 每輪 overview → 第 4 區 → 已啟用的區（並行）。`every_round` 每輪重取；`on_context_change` 只在
//      overview `context_version` 與該區上次接受的版本不同時重取。
//    - 版本：區回應 `context_version` ≠ 當下 overview ⇒ 本輪最多重取 overview 一次，再重取受影響區一次；
//      仍不一致 ⇒ 該區 `stale`（保留上一份）。區不吃 `?game`、不解讀區層級 `status`。
//    - 區讀取失敗只改該區狀態；⛔ 計入退避（沿用第 4 區時的失敗定義：overview 或 watch 失敗才算），
//      ⛔ 影響第 1 區「暫時無法更新」提示。新一輪開始時與 overview／watch 一起中止。
//    - 各區獨立結算（審核 F1，review-8）：一區一回來就上畫面，⛔ 等其他區；本輪的 overview／watch 結束即算
//      本輪結束（onRound、退避判斷），區請求在背景繼續，⛔ 讓慢區把整輪拖成「被下一輪取代＝失敗」。
//      跨輪未回的區請求在下一輪開始時中止（不計失敗），版本錯配共用同一次 overview 重取。

export const POLL_INTERVAL_MS = 30_000;
export const BACKOFF_MS = [30_000, 60_000, 120_000, 240_000] as const;

/** 連續失敗 n 次後的下一次間隔。 */
export function nextDelay(failures: number): number {
  return BACKOFF_MS[Math.min(Math.max(failures, 0), BACKOFF_MS.length - 1)];
}

export type VersionedOverview = {
  context_version: string;
  /** 第 2／3 區的 series 參數（MOUNT-CONTRACT §4）；缺時退回 `sections.watch.series`（同一個 S02 預設系列）。 */
  default_series?: string;
  sections: { watch: { status: string; series: string; game: number | null } };
};
/** `context_version` 為 null（不應發生）時與任何 overview 都不一致，照版本落差處理。 */
export type VersionedWatch = { context_version: string | null; status: string };

export type WatchDecision = "accept" | "refetch_overview" | "keep_previous";

/**
 * watch 回應要不要接受。`requested`＝目標場來自 `?game`（使用者指定）：此時 `not_target` 是正當結果
 * （指定了未來非目標場），照接受、讓元件顯示其文字；只有目標場取自 overview 時 `not_target` 才代表版本落差。
 */
export function watchDecision(overviewVersion: string, watch: VersionedWatch, opts: { requested: boolean; retried: boolean }): WatchDecision {
  const sameVersion = watch.context_version === overviewVersion;
  const targetDrift = !opts.requested && watch.status === "not_target";
  if (sameVersion && !targetDrift) return "accept";
  return opts.retried ? "keep_previous" : "refetch_overview";
}

/** 第 2／3 區回應的最小形狀：版本處置只看 `context_version`。 */
export type VersionedArea = { context_version: string | null };

/** 區回應要不要接受：同 `watchDecision`，但沒有 `?game`（D2）也不解讀區層級 `status`。 */
export function areaDecision(overviewVersion: string, area: VersionedArea, opts: { retried: boolean }): WatchDecision {
  if (area.context_version === overviewVersion) return "accept";
  return opts.retried ? "keep_previous" : "refetch_overview";
}

export type AreaRefresh = "every_round" | "on_context_change";

export type PollArea<A extends VersionedArea = VersionedArea> = {
  id: string;
  refresh: AreaRefresh;
  fetch: (series: string, signal: AbortSignal) => Promise<A>;
};

export type WatchState<W> =
  | { kind: "idle" }                       // 尚未取得（首屏占位）
  | { kind: "data"; data: W }
  | { kind: "error"; previous: W | null }  // 本輪 watch 讀取失敗
  | { kind: "stale"; previous: W | null }; // 重取後版本仍不一致：保留上一份＋「資料更新中」

export type PollDeps<O extends VersionedOverview, W extends VersionedWatch> = {
  fetchOverview: (signal: AbortSignal) => Promise<O>;
  /** 未掛第 4 區（只上第 1 區）時不給：每輪只取 overview，watch 請求數為 0。 */
  fetchWatch?: (target: { series: string; game: number }, signal: AbortSignal) => Promise<W>;
  isVisible: () => boolean;
  setTimer: (fn: () => void, ms: number) => unknown;
  clearTimer: (handle: unknown) => void;
  onOverview: (o: O) => void;
  onWatch?: (s: WatchState<W>) => void;
  /** 第 2／3 區（registry 登記）；不給＝沒有區，行為與只有第 1／4 區時相同。 */
  areas?: PollArea[];
  /** 區狀態與第 4 區同形（`AreaState` ＝ `WatchState`）。 */
  onArea?: (id: string, s: WatchState<VersionedArea>) => void;
  /** 每輪結束回報（測試與除錯用）。 */
  /** `overviewOk`＝本輪 overview 已取得並上畫面（watch 失敗不影響第 1 區的「暫時無法更新」提示）。 */
  onRound?: (r: { ok: boolean; overviewOk: boolean; failures: number; nextDelayMs: number | null }) => void;
};

export type Trigger = "start" | "timer" | "visible" | "game" | "activate";

export type AreaState<A> = WatchState<A>;

export class PlayoffsPoller<O extends VersionedOverview, W extends VersionedWatch> {
  private seq = 0;
  private timer: unknown = null;
  private inflight: AbortController | null = null;
  private failures = 0;
  private lastWatch: W | null = null;
  private stopped = false;
  private overviewOk = false;
  private deps: PollDeps<O, W>;
  private requestedGame: number | null;
  private active = new Set<string>();
  private areaLast = new Map<string, VersionedArea>();
  private activatePending = false;
  /** 本輪區請求的中止器（本輪 overview／watch 結束後區請求仍在背景跑，下一輪開始時中止、不計失敗）。 */
  private areaAc: AbortController | null = null;

  constructor(deps: PollDeps<O, W>, requestedGame: number | null = null) {
    this.deps = deps;
    this.requestedGame = requestedGame;
  }

  /** `immediate`＝立即跑第一輪（首屏需要 client 取 watch 時）；否則 30 秒後才第一輪（SSR 已給 overview）。 */
  start(immediate: boolean): void {
    this.stopped = false;
    if (immediate) void this.tick("start");
    else this.schedule(nextDelay(this.failures));
  }

  stop(): void {
    this.stopped = true;
    this.abort();
    this.clear();
  }

  /** 可見性變化：隱藏即停；回前景立即一輪。 */
  visibilityChanged(): void {
    if (this.stopped) return;
    if (this.deps.isVisible()) void this.tick("visible");
    else {
      this.abort();
      this.clear();
    }
  }

  /** `?game` 變更：舊 game 的進行中回應作廢，立即以新 game 取一輪。 */
  setGame(game: number | null): void {
    if (game === this.requestedGame) return;
    this.requestedGame = game;
    this.lastWatch = null;
    if (!this.stopped) void this.tick("game");
  }

  /** 區第一次接近 viewport：啟用並立即一輪（同一個 microtask 內多區啟用只跑一輪）。 */
  activate(id: string): void {
    if (this.active.has(id)) return;
    this.active.add(id);
    if (this.stopped || this.activatePending) return;
    this.activatePending = true;
    void Promise.resolve().then(() => {
      this.activatePending = false;
      if (!this.stopped) void this.tick("activate");
    });
  }

  /** 標記為已啟用但不立即跑一輪（控制器建立前就接近 viewport 的區；隨 `start` 的第一輪一起取）。 */
  preactivate(ids: Iterable<string>): void {
    for (const id of ids) this.active.add(id);
  }

  isActive(id: string): boolean {
    return this.active.has(id);
  }

  get failureCount(): number {
    return this.failures;
  }

  private clear(): void {
    if (this.timer !== null) this.deps.clearTimer(this.timer);
    this.timer = null;
  }

  private abort(): void {
    this.inflight?.abort();
    this.inflight = null;
    this.areaAc?.abort();
    this.areaAc = null;
  }

  private schedule(ms: number): void {
    this.clear();
    this.timer = this.deps.setTimer(() => {
      this.timer = null;
      void this.tick("timer");
    }, ms);
  }

  async tick(trigger: Trigger): Promise<void> {
    if (this.inflight) {
      this.inflight.abort();
      if (trigger === "timer") this.failures += 1;   // 一整個間隔都沒回來＝慢，退避
    }
    this.areaAc?.abort();                           // 上一輪仍在背景的區請求：中止、不計失敗
    this.areaAc = null;
    this.clear();
    this.inflight = null;
    if (this.stopped || !this.deps.isVisible()) return;
    this.schedule(nextDelay(this.failures));
    const token = ++this.seq;
    const ac = new AbortController();
    this.inflight = ac;
    this.areaAc = ac;
    const live = () => token === this.seq && !ac.signal.aborted;
    this.overviewOk = false;
    try {
      const ok = await this.round(ac.signal, live);
      if (!live()) return;
      if (ok) this.failures = 0;
      else {
        this.failures += 1;
        this.schedule(nextDelay(this.failures));
      }
      this.deps.onRound?.({ ok, overviewOk: this.overviewOk, failures: this.failures, nextDelayMs: nextDelay(this.failures) });
    } finally {
      if (token === this.seq && this.inflight === ac) this.inflight = null;
    }
  }

  /** 回傳本輪是否成功；任何一步失敗或被取代都不會呼叫 onOverview／onWatch。 */
  private async round(signal: AbortSignal, live: () => boolean): Promise<boolean> {
    let overview: O;
    try {
      overview = await this.deps.fetchOverview(signal);
    } catch {
      return false;
    }
    if (!live()) return false;
    this.deps.onOverview(overview);
    this.overviewOk = true;
    let current = overview;
    const watchOk = await this.roundWatch(overview, signal, live, (o) => { current = o; });
    if (!live()) return false;
    this.roundAreas(current, signal, live);         // ⛔ await：區獨立結算，不拖住本輪（審核 F1）
    return watchOk;
  }

  /** 第 4 區（行為與 SHA-F3 相同）。`onFresh` 回報本輪重取後的 overview，供第 2／3 區比版本。 */
  private async roundWatch(overview: O, signal: AbortSignal, live: () => boolean, onFresh: (o: O) => void): Promise<boolean> {
    const fetchWatch = this.deps.fetchWatch;
    if (!fetchWatch) return true;

    const requested = this.requestedGame !== null;
    const attempt = async (o: O, retried: boolean): Promise<boolean> => {
      const target = o.sections.watch;
      const game = this.requestedGame ?? target.game;
      if (target.status !== "ok" && !requested) {
        this.lastWatch = null;
        this.deps.onWatch?.({ kind: "idle" });
        return true;
      }
      if (game === null) return true;
      let watch: W;
      try {
        watch = await fetchWatch({ series: target.series, game }, signal);
      } catch {
        if (!live()) return false;
        this.deps.onWatch?.({ kind: "error", previous: this.lastWatch });
        return false;
      }
      if (!live()) return false;
      const decision = watchDecision(o.context_version, watch, { requested, retried });
      if (decision === "accept") {
        this.lastWatch = watch;
        this.deps.onWatch?.({ kind: "data", data: watch });
        return true;
      }
      if (decision === "keep_previous") {
        this.deps.onWatch?.({ kind: "stale", previous: this.lastWatch });
        return true;
      }
      let fresh: O;
      try {
        fresh = await this.deps.fetchOverview(signal);
      } catch {
        if (!live()) return false;
        this.deps.onWatch?.({ kind: "stale", previous: this.lastWatch });
        return false;
      }
      if (!live()) return false;
      this.deps.onOverview(fresh);
      onFresh(fresh);
      return attempt(fresh, true);
    };
    return attempt(overview, false);
  }

  /** 第 2／3 區：已啟用者並行取、各自結算；版本不一致者共用同一次 overview 重取，再各重取一次。 */
  private roundAreas(overview: O, signal: AbortSignal, live: () => boolean): void {
    const areas = (this.deps.areas ?? []).filter((a) => this.active.has(a.id));
    const due = areas.filter((a) => a.refresh === "every_round"
      || this.areaLast.get(a.id)?.context_version !== overview.context_version);
    if (!due.length) return;
    let fresh: Promise<O | null> | null = null;
    const freshOverview = () => (fresh ??= this.deps.fetchOverview(signal).then(
      (o) => { if (live()) this.deps.onOverview(o); return o; },
      () => null,
    ));
    for (const a of due) void this.runArea(a, overview, signal, live, freshOverview);
  }

  private async runArea(a: PollArea, overview: O, signal: AbortSignal, live: () => boolean,
    freshOverview: () => Promise<O | null>): Promise<void> {
    const series = (o: O) => o.default_series ?? o.sections.watch.series;
    const fetchOne = async (o: O): Promise<VersionedArea | null> => {
      try {
        return await a.fetch(series(o), signal);
      } catch {
        return null;
      }
    };
    const settle = (data: VersionedArea | null, o: O, retried: boolean): boolean => {
      const previous = this.areaLast.get(a.id) ?? null;
      if (data === null) {
        this.deps.onArea?.(a.id, { kind: "error", previous });
        return true;
      }
      const decision = areaDecision(o.context_version, data, { retried });
      if (decision === "accept") {
        this.areaLast.set(a.id, data);
        this.deps.onArea?.(a.id, { kind: "data", data });
        return true;
      }
      if (decision === "keep_previous") {
        this.deps.onArea?.(a.id, { kind: "stale", previous });
        return true;
      }
      return false;   // 需要重取 overview
    };
    const first = await fetchOne(overview);
    if (!live()) return;
    if (settle(first, overview, false)) return;
    const o2 = await freshOverview();
    if (!live()) return;
    if (!o2) {
      this.deps.onArea?.(a.id, { kind: "stale", previous: this.areaLast.get(a.id) ?? null });
      return;
    }
    const second = await fetchOne(o2);
    if (!live()) return;
    settle(second, o2, true);
  }
}

/** client 端取 JSON：非 2xx 視為失敗（丟出），交給控制器退避。 */
export async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const res = await fetch(url, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return (await res.json()) as T;
}
