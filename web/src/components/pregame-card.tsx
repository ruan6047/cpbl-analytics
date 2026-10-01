import Link from "next/link";
import { PREGAME_COPY, type PregameCardModel } from "@/lib/pregame-card";

// 可嵌入賽前勝率模組（UX-OUTCOME-HOME）。純展示、server-safe：
// 資料抓取與解析走 resolvePregameCard()（消費端負責），本元件只渲染 view model。
// 契約：不抓首頁聚合資料、不決定區塊排序、不修改首頁文案；外層（UX-GAME-HOME1
// 的賽程卡）決定放哪、怎麼排。不可用四態渲染成單行附註，不阻塞外層卡片。

export function PregameCard({ model, homeName, variant = "card" }: {
  model: PregameCardModel; homeName?: string;
  /** aside＝首頁票券右格（#218：直接寫球隊勝率大數字，訊號與方法連結收在下方一行）。 */
  variant?: "card" | "aside";
}) {
  if (variant === "aside") return <PregameAside model={model} homeName={homeName} />;
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
      className="rounded-md bg-surface-2 px-3 py-2.5"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-bold text-ink">
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
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-band" aria-hidden>
        <div className="h-full rounded-full bg-ink" style={{ width: `${pct}%` }} />
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

      {/* 降級揭露（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）：這個機率不是最新回測那一版模型算的。
          用 text-muted 而非 faint——它是必須被讀到的限制，不是次要註腳；但仍不放大成
          警示框，避免搶走賽況頁焦點。文字由 resolvePregameCard 從同一份 response 推導。 */}
      {model.servingNotice && (
        <p
          data-testid="pregame-serving-notice"
          role="note"
          className="mt-1.5 border-t border-line pt-1.5 text-[11px] leading-relaxed text-muted"
        >
          {model.servingNotice}
        </p>
      )}
    </div>
  );
}

/** 票券右格版：缺模型／不支援等四態照樣只寫一句附註（不造 50%）；可用時寫「主隊勝率 NN%」，
 *  主訊號與訓練截止年收成一行小字，方法連結保留（點機率必須能追到方法）。 */
function PregameAside({ model, homeName }: { model: PregameCardModel; homeName?: string }) {
  if (model.status !== "available") {
    return <p className="text-right text-xs leading-snug text-muted" role="note">{model.message}</p>;
  }
  const label = `${homeName ? `${homeName}` : "主隊"}${PREGAME_COPY.probabilityLabel.replace(/^主隊/, "")}`;
  return (
    <div role="group" aria-label={`${PREGAME_COPY.eyebrow}：${label} ${model.probabilityText}`}
      className="grid justify-items-end gap-0.5 text-right">
      <span className="text-xs text-muted">{label}</span>
      <span className="pm-big !text-[34px] text-ink">{model.probabilityText}</span>
      {model.primarySignal && (
        <span className="max-w-full truncate text-[11px] text-muted">
          {model.primarySignal.label} <span className="font-mono tabular-nums">{model.primarySignal.valueText}</span>{" "}
          {model.primarySignal.favorsText}
        </span>
      )}
      <Link href={model.methodologyHref} className="text-[11px] text-accent underline decoration-accent/40 underline-offset-2">
        {PREGAME_COPY.methodologyLabel}
      </Link>
      {model.trainedThroughText && <span className="text-[11px] text-muted">{model.trainedThroughText}</span>}
    </div>
  );
}
