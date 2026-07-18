"use client";

// UX-PLAYER-IA1 prototype：三種 IA 導覽變體共用視圖。
// A tabs：單層渲染，?layer= deep-link；B anchors：長頁＋scrollspy，#hash deep-link；
// C hybrid：總覽常駐、其餘三層切換，?sec= deep-link。
// role（?role=）與錯誤態模擬（?state=error）跨變體共用。
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  FIXTURES, LAYERS, SCENARIOS, VARIANT_LABELS, VARIANTS,
  type Fixture, type LayerId, type Role, type Variant,
  defaultLayer, defaultRole, isRetired, rolesOf,
} from "./lib";
import { LAYER_RENDERERS } from "./sections";

// ---- Hero（恆在導覽之上，不屬於任一層）----

function HeroLite({ fx, role, setRole }: { fx: Fixture; role: Role; setRole: (r: Role) => void }) {
  const p = fx.profile.player;
  const roles = rolesOf(fx);
  const ability = fx.abilityCard?.[role]?.[isRetired(fx) ? "career" : "season"]
    ?? fx.abilityCard?.[role]?.career;
  return (
    <header className="mb-4 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-xl font-bold text-ink">{p.name}</h1>
        <span className="text-sm text-muted">{p.team ?? "—"}・{p.primary_position ? String(p.primary_position) : "—"}</span>
        {p.roster_level ? (
          <span className="rounded bg-surface-2 px-1.5 py-0.5 text-xs text-muted">{p.roster_level}</span>
        ) : (
          <span className="rounded bg-surface-2 px-1.5 py-0.5 text-xs text-muted">退役／教練</span>
        )}
        <span className="text-xs text-faint">{p.bats ?? "?"}打{p.throws ?? "?"}投</span>
      </div>
      {/* 能力值卡摘要（正式版：雷達圖；退役者尺度退回生涯） */}
      {ability?.available && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(ability.axes ?? []).map((a) => (
            <span key={a.key} className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted">
              {a.label} <span className="font-mono text-ink">{a.pr ?? "—"}</span>
            </span>
          ))}
        </div>
      )}
      {/* role tab：雙棲才出現（打擊/投球），全層共用 */}
      {roles.length > 1 && (
        <div className="mt-3 inline-flex rounded-lg bg-surface-2 p-0.5" role="tablist" aria-label="角色">
          {roles.map((r) => (
            <button key={r.v} role="tab" aria-selected={role === r.v} onClick={() => setRole(r.v)}
              className={`rounded-md px-3 py-1 text-sm transition ${role === r.v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}>
              {r.label}
            </button>
          ))}
        </div>
      )}
    </header>
  );
}

// ---- 鍵盤操作：tablist 左右鍵移動＋選取（WAI-ARIA tabs pattern）----

function useTablistKeys(count: number, active: number, select: (i: number) => void) {
  return (e: React.KeyboardEvent) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = (active + delta + count) % count;
    select(next);
  };
}

// ---- A・Tabs：單層渲染 ----

function TabsNav({ fx, role, layer, setLayer, simError }: {
  fx: Fixture; role: Role; layer: LayerId; setLayer: (l: LayerId) => void; simError: boolean;
}) {
  const idx = LAYERS.findIndex((l) => l.id === layer);
  const onKey = useTablistKeys(LAYERS.length, idx, (i) => setLayer(LAYERS[i].id));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => { refs.current[idx]?.focus({ preventScroll: true }); }, [idx]);
  return (
    <>
      <div role="tablist" aria-label="球員頁分層" onKeyDown={onKey}
        className="sticky top-0 z-20 -mx-1 mb-4 flex gap-1 overflow-x-auto border-b border-line bg-paper px-1 py-2">
        {LAYERS.map((l, i) => (
          <button key={l.id} role="tab" aria-selected={layer === l.id} tabIndex={layer === l.id ? 0 : -1}
            ref={(el) => { refs.current[i] = el; }}
            onClick={() => setLayer(l.id)}
            className={`whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm transition ${
              layer === l.id ? "bg-ink font-medium text-paper" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
            {l.label(role)}
          </button>
        ))}
      </div>
      <div role="tabpanel">{LAYER_RENDERERS[layer]({ fx, role, simError })}</div>
    </>
  );
}

// ---- B・錨點長頁：全層渲染＋scrollspy ----

function AnchorsNav({ fx, role, simError }: { fx: Fixture; role: Role; simError: boolean }) {
  const [active, setActive] = useState<LayerId>(defaultLayer(fx));
  // deep-link 補強：client 渲染完成前瀏覽器已處理過 #hash（找不到節點），mount 後補捲一次。
  // 這是錨點方案的固有成本——hash 目標必須等內容渲染完才存在，決策文件已記錄。
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id && LAYERS.some((l) => l.id === id)) {
      document.getElementById(id)?.scrollIntoView();
      // 同步 active：programmatic scrollIntoView 在部分環境不觸發 scroll listener，
      // 若不補設，deep-link 後 active 停在 overview，會讓下方 role 切換 re-anchor 捲錯層。
      setActive(id as LayerId);
    }
  }, []);
  // scrollspy：取最後一個頂端已越過 sticky nav 下緣的段落（瞬跳與慢捲皆可靠）。
  useEffect(() => {
    const onScroll = () => {
      let cur: LayerId = LAYERS[0].id;
      for (const l of LAYERS) {
        const el = document.getElementById(l.id);
        if (el && el.getBoundingClientRect().top <= 64) cur = l.id;
      }
      setActive(cur);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  // role 切換保留當前層：投打內容高度不同→各層重排，router.replace({scroll:false})
  // 不會因保留 hash 而自動重錨；故 role 變動時明確把當前層（active）捲回定位。
  // 閉包捕捉本次 render 的 active（此刻尚未被重排後的 scroll 事件改寫），rAF 待重排落定再捲。
  const roleRef = useRef(role);
  useEffect(() => {
    if (roleRef.current === role) return;
    roleRef.current = role;
    const target = active;
    requestAnimationFrame(() => document.getElementById(target)?.scrollIntoView());
  }, [role, active]);
  // deep-link：#hash 由瀏覽器原生捲動；scroll-mt 避開 sticky nav
  return (
    <>
      <nav aria-label="頁內導覽"
        className="sticky top-0 z-20 -mx-1 mb-4 flex gap-1 overflow-x-auto border-b border-line bg-paper px-1 py-2">
        {LAYERS.map((l) => (
          <a key={l.id} href={`#${l.id}`} aria-current={active === l.id ? "location" : undefined}
            className={`whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm transition ${
              active === l.id ? "bg-ink font-medium text-paper" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
            {l.label(role)}
          </a>
        ))}
      </nav>
      {LAYERS.map((l) => (
        <section key={l.id} id={l.id} className="mb-8 scroll-mt-14" aria-label={l.label(role)}>
          <h2 className="mb-3 border-l-4 border-accent pl-2 text-base font-semibold text-ink">{l.label(role)}</h2>
          {LAYER_RENDERERS[l.id]({ fx, role, simError })}
        </section>
      ))}
    </>
  );
}

// ---- C・Hybrid：總覽常駐＋其餘三層切換 ----

const HYBRID_LAYERS = LAYERS.filter((l) => l.id !== "overview");

function HybridNav({ fx, role, sec, setSec, simError }: {
  fx: Fixture; role: Role; sec: LayerId; setSec: (l: LayerId) => void; simError: boolean;
}) {
  const idx = Math.max(0, HYBRID_LAYERS.findIndex((l) => l.id === sec));
  const onKey = useTablistKeys(HYBRID_LAYERS.length, idx, (i) => setSec(HYBRID_LAYERS[i].id));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => { refs.current[idx]?.focus({ preventScroll: true }); }, [idx]);
  return (
    <>
      {/* 總覽常駐：退役者總覽為空態時仍顯示（引導往生涯） */}
      <section aria-label="總覽" className="mb-6">
        <h2 className="mb-3 border-l-4 border-accent pl-2 text-base font-semibold text-ink">總覽</h2>
        {LAYER_RENDERERS.overview({ fx, role, simError })}
      </section>
      <div role="tablist" aria-label="進階分層" onKeyDown={onKey}
        className="sticky top-0 z-20 -mx-1 mb-4 flex gap-1 overflow-x-auto border-b border-line bg-paper px-1 py-2">
        {HYBRID_LAYERS.map((l, i) => (
          <button key={l.id} role="tab" aria-selected={sec === l.id} tabIndex={sec === l.id ? 0 : -1}
            ref={(el) => { refs.current[i] = el; }}
            onClick={() => setSec(l.id)}
            className={`whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm transition ${
              sec === l.id ? "bg-ink font-medium text-paper" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
            {l.label(role)}
          </button>
        ))}
      </div>
      <div role="tabpanel">{LAYER_RENDERERS[sec]({ fx, role, simError })}</div>
    </>
  );
}

// ---- 組裝 ----

export function VariantView({ variant, scenario }: { variant: Variant; scenario: string }) {
  const fx = FIXTURES[scenario];
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const simError = params.get("state") === "error";

  const roleParam = params.get("role") as Role | null;
  const role: Role = roleParam && rolesOf(fx).some((r) => r.v === roleParam) ? roleParam : defaultRole(fx);

  // deep-link：tabs/hybrid 用 query（?layer=/?sec=）；anchors 用 #hash（原生）
  const layerParam = params.get(variant === "hybrid" ? "sec" : "layer") as LayerId | null;
  const layer: LayerId = useMemo(() => {
    const valid = (variant === "hybrid" ? HYBRID_LAYERS : LAYERS).some((l) => l.id === layerParam);
    if (valid && layerParam) return layerParam;
    if (variant === "hybrid") return isRetired(fx) ? "career" : "approach";
    return defaultLayer(fx);
  }, [variant, layerParam, fx]);

  const setQuery = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    // anchors 變體的當前層以 #hash 表達（tabs/hybrid 用 query），切 role 時必須保留，
    // 否則 hash 被洗掉→scrollspy 失錨、捲回頁首，違反「切換保留當前層」。
    const hash = typeof window !== "undefined" ? window.location.hash : "";
    router.replace(`${pathname}?${next.toString()}${hash}`, { scroll: false });
  };

  return (
    <main className="mx-auto max-w-3xl px-4 py-4">
      <PrototypeToolbar variant={variant} scenario={scenario} simError={simError} />
      <HeroLite fx={fx} role={role} setRole={(r) => setQuery("role", r)} />
      {variant === "tabs" && (
        <TabsNav fx={fx} role={role} layer={layer} setLayer={(l) => setQuery("layer", l)} simError={simError} />
      )}
      {variant === "anchors" && <AnchorsNav fx={fx} role={role} simError={simError} />}
      {variant === "hybrid" && (
        <HybridNav fx={fx} role={role} sec={layer} setSec={(l) => setQuery("sec", l)} simError={simError} />
      )}
    </main>
  );
}

// ---- 走查工具列：變體/情境/錯誤態 快速切換 ----

function PrototypeToolbar({ variant, scenario, simError }: { variant: Variant; scenario: string; simError: boolean }) {
  return (
    <div className="mb-4 rounded-lg border border-dashed border-line bg-surface-2/60 p-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link href="/dev/player-ia" className="font-semibold text-accent hover:underline">← IA 走查首頁</Link>
        <span className="text-faint">變體：</span>
        {VARIANTS.map((v) => (
          <Link key={v} href={`/dev/player-ia/${v}/${scenario}`}
            className={v === variant ? "font-semibold text-ink" : "text-muted hover:text-ink"}>
            {VARIANT_LABELS[v].slice(0, 1)}
          </Link>
        ))}
        <span className="text-faint">情境：</span>
        {SCENARIOS.map((s) => (
          <Link key={s.key} href={`/dev/player-ia/${variant}/${s.key}`}
            className={s.key === scenario ? "font-semibold text-ink" : "text-muted hover:text-ink"}>
            {s.label.split("（")[0]}
          </Link>
        ))}
        <Link href={`/dev/player-ia/${variant}/${scenario}${simError ? "" : "?state=error"}`}
          className={simError ? "font-semibold text-accent" : "text-muted hover:text-ink"}>
          {simError ? "✓ 錯誤態" : "模擬錯誤態"}
        </Link>
      </div>
      <p className="mt-1 text-faint">{VARIANT_LABELS[variant]}｜{SCENARIOS.find((s) => s.key === scenario)?.note}</p>
    </div>
  );
}
