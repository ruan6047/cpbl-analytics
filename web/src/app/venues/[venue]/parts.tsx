// 球場詳情頁展示元件（Server Component 可用；無 client hooks）。
// 契約義務（VENUE_PARK1_CONTRACT §1.1/1.3）：樣本數與 low_sample 必須可見，
// 文案不得寫成因果斷言 —— 故 pfPhrase() 一律輸出「相對同隊他場基準的偏離幅度＋場數」。
import type { FactorStat, Factors } from "@/lib/api";

export const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));
export const f2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
export const f1 = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`);
export const num = (v: number | null | undefined) => (v == null ? "—" : Number(v).toLocaleString());

export const FACTOR_LABEL: Record<FactorStat, string> = {
  r: "得分",
  hr: "全壘打",
  xbh: "長打",
  h: "安打",
  bb: "保送",
  so: "三振",
};
export const FACTOR_HINT: Record<FactorStat, string> = {
  r: "雙方合計得分",
  hr: "全壘打",
  xbh: "二＋三壘安打（不含全壘打）",
  h: "安打",
  bb: "保送",
  so: "三振",
};

// PF 中性帶：±3% 內視為持平（單球場樣本本就小，不替雜訊命名方向）。
const NEUTRAL = 0.03;

/** 誠實文案：不寫「這球場不容易全壘打」，只描述相對基準的偏離幅度並附場數。
 *  低樣本時把保留直接寫進句子——徽章在旁邊不夠，斷言句本身必須自帶警語。 */
export function pfPhrase(stat: FactorStat, pf: number | null, games: number, lowSample = false): string {
  if (pf == null) return `${FACTOR_LABEL[stat]}無法估計（同隊無其他球場場次可當基準）`;
  const tail = lowSample ? `（${games} 場，樣本少、波動大）` : `（${games} 場）`;
  const d = pf - 1;
  if (Math.abs(d) < NEUTRAL) return `${FACTOR_LABEL[stat]}與同隊他場基準持平${tail}`;
  return `${FACTOR_LABEL[stat]}產出${d > 0 ? "高" : "低"}於同隊他場基準 ${Math.round(Math.abs(d) * 100)}%${tail}`;
}

/** PF 發散長條：中心＝1.00（同隊他場基準），右紅＝放大、左藍＝壓制。 */
export function PfBar({ stat, f, lowSample }: {
  stat: FactorStat;
  f: Factors[FactorStat];
  lowSample: boolean;
}) {
  const pf = f.pf;
  // 視覺尺規固定 0.5–1.5：跨球場可直接比長度；超界夾住（PF 極端值多為小樣本雜訊）。
  const clamped = pf == null ? 1 : Math.min(1.5, Math.max(0.5, pf));
  const half = Math.abs(clamped - 1) * 100; // 0.5 偏離 → 50% 寬（半邊滿格）
  const amplify = clamped > 1;
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="w-16 shrink-0">
        <span className="text-xs font-medium text-ink" title={FACTOR_HINT[stat]}>{FACTOR_LABEL[stat]}</span>
      </div>
      <div className="relative h-4 flex-1 rounded bg-surface-2">
        <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" aria-hidden />
        {pf != null && (
          <div
            className={`absolute inset-y-0.5 rounded-sm ${amplify ? "bg-accent" : "bg-cpbl"} ${lowSample ? "opacity-40" : ""}`}
            style={amplify
              ? { left: "50%", width: `${half}%` }
              : { right: "50%", width: `${half}%` }}
          />
        )}
      </div>
      <div className="w-12 shrink-0 text-right font-mono text-sm tabular-nums font-semibold text-ink">
        {pf == null ? "—" : pf.toFixed(2)}
      </div>
      <div className="hidden w-28 shrink-0 text-right font-mono text-[11px] tabular-nums text-faint sm:block">
        {f.observed} / {f.expected}
      </div>
    </div>
  );
}

/** 低樣本旗標（契約要求可見）。走 amber 警示 token，與延賽/二軍等次級狀態同語彙。 */
export const LowSample = ({ className = "" }: { className?: string }) => (
  <span
    title="樣本不足（單季 <30 場、合併 <60 場的估計基礎），數值波動大"
    className={`rounded bg-amber/15 px-1.5 py-0.5 text-[10px] font-medium text-amber ${className}`}
  >
    樣本少
  </span>
);

/** 數值 + 與聯盟同年基準的差（描述性對照，非因果）。 */
export function VsLeague({ value, league, fmt, invert = false }: {
  value: number | null;
  league: number | null;
  fmt: (v: number | null | undefined) => string;
  invert?: boolean;   // true＝值越低越「投手友善」（SO% 不適用，僅供需要時）
}) {
  if (value == null) return <span className="text-faint">—</span>;
  const d = league == null ? null : value - league;
  const tone = d == null || Math.abs(d) < 1e-9 ? "text-faint"
    : (d > 0) !== invert ? "text-accent" : "text-up";
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="font-mono tabular-nums text-ink">{fmt(value)}</span>
      {d != null && (
        <span className={`font-mono text-[10px] tabular-nums ${tone}`}>
          {d > 0 ? "+" : "−"}{fmt(Math.abs(d)).replace("%", "")}
        </span>
      )}
    </span>
  );
}
