import Link from "next/link";
import { PREGAME_COPY, type PregameCardModel } from "@/lib/pregame-card";

// 可嵌入賽前勝率模組（UX-OUTCOME-HOME）。純展示、server-safe：
// 資料抓取與解析走 resolvePregameCard()（消費端負責），本元件只渲染 view model。
// 契約：不抓首頁聚合資料、不決定區塊排序、不修改首頁文案；外層（UX-GAME-HOME1
// 的賽程卡）決定放哪、怎麼排。不可用四態渲染成單行附註，不阻塞外層卡片。

export function PregameCard({ model, homeName }: { model: PregameCardModel; homeName?: string }) {
  if (model.status !== "available") {
    // 缺模型／不支援／未就緒／錯誤：單行淡色附註即可，勿放大成警示框搶走賽程卡焦點。
    return (
      <p className="text-xs text-faint" role="note">
        {model.message}
      </p>
    );
  }

  const pct = Math.min(99, Math.max(1, Math.round(model.homeWinProbability * 100)));
  const probLabel = `${PREGAME_COPY.probabilityLabel}${homeName ? `（${homeName}）` : ""}`;

  return (
    <div
      role="group"
      aria-label={`${PREGAME_COPY.eyebrow}：${probLabel} ${model.probabilityText}`}
      className="rounded-lg bg-surface-2 px-3 py-2.5"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
          {PREGAME_COPY.eyebrow}
        </span>
        <Link
          href={model.methodologyHref}
          className="text-[11px] text-muted underline decoration-line underline-offset-2 hover:text-accent"
        >
          {PREGAME_COPY.methodologyLabel}
        </Link>
      </div>

      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="text-sm text-muted">{probLabel}</span>
        <span className="font-mono text-xl font-bold tabular-nums text-ink">
          {model.probabilityText}
        </span>
      </div>

      {/* 點機率的視覺化：單一填充條，無區間、無誤差帶。 */}
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-line" aria-hidden>
        <div className="h-full rounded-full bg-cpbl" style={{ width: `${pct}%` }} />
      </div>

      <p className="mt-1.5 truncate text-xs text-muted">
        {model.primarySignal ? (
          <>
            {model.primarySignal.label}{" "}
            <span className="font-mono tabular-nums">{model.primarySignal.valueText}</span>
            <span
              className={
                model.primarySignal.favors === "home"
                  ? "ml-1 text-up"
                  : model.primarySignal.favors === "away"
                    ? "ml-1 text-down"
                    : "ml-1 text-faint"
              }
            >
              {model.primarySignal.favorsText}
            </span>
          </>
        ) : (
          PREGAME_COPY.signalUnavailable
        )}
      </p>

      {model.trainedThroughText && (
        <p className="mt-1 text-[10px] text-faint">{model.trainedThroughText}</p>
      )}
    </div>
  );
}
