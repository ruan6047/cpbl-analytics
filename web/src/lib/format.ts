// 投球局數 [IP] 統一顯示為分數。
// CPBL 資料以 .1/.2 棒球記法儲存（.1=⅓局、.2=⅔局），顯示時轉成分數避免誤解為十進位。
export function fmtIP(ip: number | string | null | undefined): string {
  if (ip == null || ip === "") return "—";
  const v = typeof ip === "string" ? Number(ip) : ip;
  if (Number.isNaN(v)) return "—";
  const whole = Math.floor(v + 1e-9);
  const outs = Math.round((v - whole) * 10); // 0 / 1 / 2
  return outs === 0 ? `${whole}` : `${whole}${outs === 1 ? "⅓" : "⅔"}`;
}

// 逐場 box score 用兩欄（整數局 + 出局數 0/1/2）→ 分數顯示。
export function fmtIPParts(cnt: number | null | undefined, div3: number | null | undefined): string {
  if (cnt == null) return "—";
  const o = div3 ?? 0;
  return o === 0 ? `${cnt}` : `${cnt}${o === 1 ? "⅓" : "⅔"}`;
}
