// 上抽前的 BasesOuts，逐字取自 a6331ccff39fe062b2b44e1f6f4542307b8453bd 的
// web/src/components/game-board.tsx。**這是取證基準的凍結副本，勿編輯。**
//
// 為什麼要凍結一份：本 repo 的 merge 會被 `pull --rebase` 線性化而改寫 SHA，
// 分支合併後 `git show a6331cc:...` 對只有 main 的人可能已經取不到。取證腳本仍以
// git 為優先來源，兩者都拿得到時會斷言逐字相同——所以這份副本無法悄悄漂移。
function BasesOuts({ b1, b2, b3, outs, size = 52 }: {
  b1: boolean; b2: boolean; b3: boolean; outs: number; size?: number;
}) {
  // 品字排列：二壘上中、三壘左下、一壘右下，菱形緊靠；下方兩顆出局圓點
  const base = (cx: number, cy: number, on: boolean) => (
    <rect
      x={cx - 15} y={cy - 15} width={30} height={30}
      transform={`rotate(45 ${cx} ${cy})`} rx={4}
      fill={on ? "var(--color-accent)" : "var(--color-line)"}
      stroke="var(--color-surface)" strokeWidth={3}
    />
  );
  const o = Math.min(outs, 2);
  return (
    <svg viewBox="0 0 120 116" width={size} height={size * 116 / 120} aria-label={`壘上${[b1 && "一壘", b2 && "二壘", b3 && "三壘"].filter(Boolean).join("、") || "無人"}，${o} 出局`}>
      {base(60, 26, b2)}
      {base(36, 50, b3)}
      {base(84, 50, b1)}
      <circle cx={48} cy={92} r={9} fill={o >= 1 ? "var(--color-accent)" : "var(--color-line)"} />
      <circle cx={72} cy={92} r={9} fill={o >= 2 ? "var(--color-accent)" : "var(--color-line)"} />
    </svg>
  );
}
