"use client";

// 進階指標（sabr 推算）：打者 RE24/wSB、投手 RE24、捕手 RA9+阻殺。
// 全部自算（livelog + RE 矩陣 + 官方計數），非官方數據 → 區塊標「推算」。
import { useEffect, useState } from "react";
import { detail } from "@/lib/client";
import type { Role } from "./lib";

type SabrYear = {
  year: number; pa?: number | null; bf?: number | null; re24: string | null;
  rnk: number | null; n: number | null; sb?: number | null; cs?: number | null; wsb?: string | null;
};
type CatcherYear = {
  year: number; runs: number; games: number; outs: number; ra9: string | null;
  cs: number | null; sba: number | null; cs_pct: number | null;
};

const num = (v: string | number | null | undefined) => (v == null ? null : Number(v));
const signed = (v: number) => (v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1));
// 出局數 → 棒球記法局數（.1=⅓）
const ipTxt = (outs: number) => `${Math.floor(outs / 3)}${outs % 3 ? `.${outs % 3}` : ""}`;

export function SabrSection({ id, role }: { id: string; role: Role }) {
  const [d, setD] = useState<{ years: SabrYear[]; catcher?: CatcherYear[] } | null>(null);
  useEffect(() => {
    setD(null);
    detail.sabr(id, role).then(setD).catch(() => setD(null));
  }, [id, role]);

  const years = (d?.years ?? []).filter((y) => y.re24 != null || num(y.wsb));
  const catcher = d?.catcher ?? [];
  if (!years.length && !catcher.length) return null;

  // RE24 正=創造得分價值：打者越高越好、投手越低（壓制）越好
  const good = (v: number) => (role === "batting" ? v > 0 : v < 0);
  const reCell = (v: number | null) => v == null ? <span className="text-faint">—</span> : (
    <span className={good(v) ? "font-semibold text-accent" : ""}>{signed(v)}</span>
  );

  return (
    <section className="mb-8">
      <h2 className="mb-1 text-lg font-semibold">
        進階指標 <span className="text-xs font-normal text-faint">（RE24／wSB 推算・一軍例行）</span>
      </h2>
      <p className="mb-3 text-xs text-faint">
        RE24＝打席前後得分期望變化的累計（跑者盜壘等異動不計入打者）；wSB＝盜壘淨得分價值。
        皆以自建 CPBL 得分期望矩陣（2018–25）推算，{role === "batting" ? "正值" : "負值"}越大越好。
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">年度</th>
                <th className="px-2 py-2 text-right font-medium">{role === "batting" ? "PA" : "BF"}</th>
                <th className="px-2 py-2 text-right font-medium">RE24</th>
                <th className="px-2 py-2 text-right font-medium">年度名次</th>
                {role === "batting" && <th className="px-2 py-2 text-right font-medium">wSB</th>}
                {role === "batting" && <th className="px-3 py-2 text-right font-medium">盜壘 SB-CS</th>}
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {years.slice(0, 9).map((y) => (
                <tr key={y.year} className="border-t border-line">
                  <td className="px-3 py-1.5">{y.year}</td>
                  <td className="px-2 py-1.5 text-right">{y.pa ?? y.bf ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right">{reCell(num(y.re24))}</td>
                  <td className="px-2 py-1.5 text-right text-muted">
                    {y.rnk ? `${y.rnk}/${y.n}` : "—"}
                  </td>
                  {role === "batting" && (
                    <td className="px-2 py-1.5 text-right">{num(y.wsb) != null ? signed(num(y.wsb)!) : "—"}</td>
                  )}
                  {role === "batting" && (
                    <td className="px-3 py-1.5 text-right text-muted">
                      {y.sb != null ? `${y.sb}-${y.cs ?? 0}` : "—"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {role === "batting" && catcher.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">捕手守備</th>
                  <th className="px-2 py-2 text-right font-medium">接捕局數</th>
                  <th className="px-2 py-2 text-right font-medium" title="接捕時每 9 局失分（含非自責）">RA/9</th>
                  <th className="px-2 py-2 text-right font-medium" title="阻殺 / (阻殺+被盜)">阻殺率</th>
                  <th className="px-3 py-2 text-right font-medium">CS-被盜</th>
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {catcher.slice(0, 9).map((y) => (
                  <tr key={y.year} className="border-t border-line">
                    <td className="px-3 py-1.5">{y.year}</td>
                    <td className="px-2 py-1.5 text-right">{ipTxt(y.outs)}</td>
                    <td className="px-2 py-1.5 text-right">{y.ra9 ?? "—"}</td>
                    <td className="px-2 py-1.5 text-right">{y.cs_pct != null ? `${y.cs_pct}%` : "—"}</td>
                    <td className="px-3 py-1.5 text-right text-muted">
                      {y.cs != null ? `${y.cs}-${y.sba ?? 0}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
