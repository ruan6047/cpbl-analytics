import type { ReactNode } from "react";
import { contrastText, markCodeOf, nameMeta, teamColor, teamLetter } from "@/lib/teams";

// #218 郵戳視覺識別的共用元件（#220 套用）。樣式住 globals.css 的 `pm-*` 元件層，
// 這裡只負責 markup 與語意；頁面不得手寫同款（UI_UX_SYSTEM §3）。全部無 hook，
// server／client 皆可用。

/** 隊伍印記：#218 核可的六隊紙面單色印記（`public/team-icons/refined-{隊碼}.svg`）。
 *  只畫現役六隊；歷史／已解散隊沒有核可印記，呼叫端改走字母章（`TeamLogo` 已自動分流）。 */
export function TeamMark({ code, size = 20, label, className = "" }: {
  code: string; size?: number;
  /** 有值＝獨立圖形（role=img）；無值＝旁邊已有隊名，僅裝飾。 */
  label?: string;
  className?: string;
}) {
  return (
    <svg
      className={`pm-ti mk-${code} ${className}`}
      width={size}
      height={size}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <use href={`/team-icons/refined-${code}.svg#mark`} />
    </svg>
  );
}

/** 字母章：歷史／已解散隊（無核可印記）沿用現行字母章，套紙面圓角（3px）。 */
export function LetterMark({ color, letter, size = 16, label }: {
  color: string; letter: string; size?: number; label?: string;
}) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-sm font-extrabold leading-none"
      style={{ width: size, height: size, background: color, color: contrastText(color), fontSize: size * 0.56 }}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {letter}
    </span>
  );
}

/** 隊伍圖示單一入口：現役六隊＝核可印記；其餘＝字母章（隊名優先解析，含歷史隊 iconic 色）。 */
export function TeamIcon({ code, name, size = 20, label }: {
  code?: string | null; name?: string | null; size?: number;
  /** 有值＝獨立圖形；無值＝旁邊已有隊名，僅裝飾。 */
  label?: string;
}) {
  const mc = markCodeOf(code, name);
  if (mc) return <TeamMark code={mc} size={size} label={label} />;
  const m = name ? nameMeta(name) : null;
  const known = m && m.letter !== "?";
  return <LetterMark color={known ? m.color : teamColor(code)} letter={known ? m.letter : teamLetter(code)}
    size={size} label={label} />;
}

/** 郵戳的替代文字：完整日期（「2026年9月28日」）＋球場；`venue` 模式只說球場（日期已由所在區塊標題說過）。 */
export function postmarkSrText(date: string, venue: string | null | undefined, announce: "date-venue" | "venue"): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  const day = m ? `${m[1]}年${Number(m[2])}月${Number(m[3])}日` : date;
  const place = venue ? `球場 ${venue}` : "";
  if (announce === "venue") return place || null;
  return [day, place].filter(Boolean).join("，") || null;
}

/** 郵戳：日期＋球場（缺球場只蓋日期，戳的尺寸不變）。開打時間不進郵戳，放序號列。
 *  只蓋在賽事票根與賽況頁頂；不蓋在比分、勝率、隊名上，選手頁不蓋。
 *  戳面（分行的年／月日／球場）對輔助科技 aria-hidden，改由同一元件輸出的 sr-only 整句承載——
 *  郵戳常是日期／球場在該處的唯一出處，不能只藏不補（#220 F1）。`announce` 決定整句說什麼：
 *  `date-venue`＝日期＋球場（預設，如賽況頁頂）；`venue`＝只說球場（日期已在區塊標題，如首頁今日票券）。 */
export function Postmark({ date, venue, size = "md", placed = "static", reveal = false, bg, announce = "date-venue" }: {
  /** `YYYY-MM-DD`（API 的 game_date）。 */
  date: string;
  venue?: string | null;
  size?: "lg" | "md" | "sm";
  /** absolute＝蓋在票根右側（父層需 relative）；static＝行內。 */
  placed?: "absolute" | "static";
  /** 轉為終場時落章一次（減少動態偏好時關閉）。 */
  reveal?: boolean;
  /** 雙圈之間的底色＝所在底版（卡面／滑過色／頁底）。 */
  bg?: "surface" | "surface-2" | "paper";
  announce?: "date-venue" | "venue";
}) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  const cls = [
    "pm-post",
    size === "lg" ? "pm-post--lg" : size === "sm" ? "pm-post--sm" : "",
    placed === "static" ? "pm-post--static" : "",
    reveal ? "pm-reveal" : "",
  ].filter(Boolean).join(" ");
  const style = bg ? ({ "--pb": `var(--color-${bg})` } as React.CSSProperties) : undefined;
  const sr = postmarkSrText(date, venue, announce);
  return (
    <>
      <span className={cls} style={style} aria-hidden="true">
        {m && <span className="pm-y">{m[1]}</span>}
        <b>{m ? `${m[2]}.${m[3]}` : date}</b>
        {venue && <span>{venue}</span>}
      </span>
      {sr && <span className="sr-only">{sr}</span>}
    </>
  );
}

/** 序號列：場次・開打時間・補賽等；`null`／空字串的項目直接不出現（不補「--:--」）。 */
export function Serial({ items, className = "" }: {
  items: ({ text: ReactNode; kind?: "lead" | "time" } | null | false | undefined)[];
  className?: string;
}) {
  const shown = items.filter((it): it is { text: ReactNode; kind?: "lead" | "time" } =>
    !!it && it.text !== null && it.text !== undefined && it.text !== "");
  if (shown.length === 0) return null;
  return (
    <div className={`pm-serial ${className}`}>
      {shown.map((it, i) => it.kind === "lead"
        ? <b key={i}>{it.text}</b>
        : <span key={i} className={it.kind === "time" ? "pm-t" : undefined}>{it.text}</span>)}
    </div>
  );
}

/** 區塊標題（全站唯一一套）：字＋可選日期＋右側一條註記或資料時間；不加眉標、不加編號。 */
export function SectionTitle({ children, as = "h2", size = "md", date, cue, meta, id, className = "" }: {
  children: ReactNode;
  as?: "h1" | "h2" | "h3" | "div";
  /** md＝頁內第一層 20px；sm＝次標 16px。h1 一律 26px。 */
  size?: "md" | "sm";
  /** 標題後的日期（寬體數字）。 */
  date?: ReactNode;
  /** 緊跟標題的一條短註記（如「終場・左客右主」）。 */
  cue?: ReactNode;
  /** 靠右的資料時間／連結。 */
  meta?: ReactNode;
  id?: string;
  className?: string;
}) {
  const Tag = as;
  return (
    <div className={`pm-sh ${size === "sm" ? "pm-sh--s" : ""} ${className}`}>
      <Tag id={id} className={as === "div" ? "pm-sh-t" : undefined}>
        {children}
        {date != null && <span className="pm-d">{date}</span>}
      </Tag>
      {cue != null && <span className="pm-cue">{cue}</span>}
      {meta != null && <span className="pm-meta">{meta}</span>}
    </div>
  );
}

export type ScoreSide = { code?: string | null; name: string; score: number | null };

/** 比分（全站一個元件）：印記 分數 : 分數 印記，左客右主。勝方只加粗（字重 900、墨色），
 *  敗方細、淡；兩側同字級、同基線。「終場／左客右主」由所在區塊標題說一次，完整句子由
 *  呼叫端寫在外層 aria-label（本元件 aria-hidden）。和局兩側同重。
 *  `stack`＝窄欄兩層式：每隊印記＋隊名收成一組置中於自己那半邊，比分夾在中軸。 */
export function Scoreline({ away, home, stack = false, showNames = true, final = true }: {
  away: ScoreSide; home: ScoreSide;
  stack?: boolean;
  showNames?: boolean;
  /** false＝比分仍會變（賽中／保留）：不判勝方、兩側同重。 */
  final?: boolean;
}) {
  const known = away.score != null && home.score != null;
  const tie = final && known && away.score === home.score;
  const awayWin = final && known && (away.score as number) > (home.score as number);
  const homeWin = final && known && (home.score as number) > (away.score as number);
  const icon = (s: ScoreSide, side: "pm-a" | "pm-h") => (
    <span className={`pm-ti ${side} inline-flex`}><TeamIcon code={s.code} name={s.name} size={stack ? 26 : 30} /></span>
  );
  const n = (v: number | null) => (v == null ? "—" : String(v));
  return (
    <span className={`pm-score ${stack ? "pm-score--stack" : ""} ${tie || (!final && known) ? "pm-score--tie" : ""}`} aria-hidden="true">
      {icon(away, "pm-a")}
      {showNames && <span className={`pm-nm pm-a ${awayWin ? "pm-w" : ""}`}>{away.name}</span>}
      <span className={`pm-n pm-a ${awayWin ? "pm-w" : ""}`}>{n(away.score)}</span>
      <span className="pm-colon">:</span>
      <span className={`pm-n pm-h ${homeWin ? "pm-w" : ""}`}>{n(home.score)}</span>
      {showNames && <span className={`pm-nm pm-h ${homeWin ? "pm-w" : ""}`}>{home.name}</span>}
      {icon(home, "pm-h")}
    </span>
  );
}

/** 局況（壘包＋球數燈）：賽況頁狀態板與首頁賽中格共用同一組 markup。
 *  B／S／O 固定 3／2／2 燈，亮燈實心、未亮空心；列標字母＋整組 aria-label 說出數字，不只靠顏色。
 *  `balls`／`strikes` 為 null＝這個來源沒有球數（首頁），B／S 兩列不畫——不得造值。
 *  `outs` 為 null＝出局數未知：O 列不畫，替代文字說「出局數未知」，不把未知講成 0。 */
export function GameSituation({ bases, outs, balls = null, strikes = null, small = false }: {
  bases: { first: boolean; second: boolean; third: boolean };
  outs: number | null;
  balls?: number | null;
  strikes?: number | null;
  small?: boolean;
}) {
  const occupied = [bases.first && "一壘", bases.second && "二壘", bases.third && "三壘"].filter(Boolean);
  const baseLabel = occupied.length === 3 ? "滿壘" : occupied.length ? `${occupied.join("、")}有人` : "壘上無人";
  const clamp = (v: number, max: number) => Math.max(0, Math.min(v, max));
  const lights = (on: number, total: number, cls: string) =>
    Array.from({ length: total }, (_, i) => <i key={i} data-l={cls.slice(3)} className={i < on ? cls : undefined} />);
  const parts = [
    balls != null ? `${clamp(balls, 3)} 壞球` : null,
    strikes != null ? `${clamp(strikes, 2)} 好球` : null,
    outs != null ? `${clamp(outs, 2)} 出局` : "出局數未知",
  ].filter(Boolean).join("、");
  const w = small ? 38 : 44;
  const h = small ? 28 : 32;
  return (
    <span className={`pm-gamesit ${small ? "pm-gamesit--sm" : ""}`}>
      <svg className="pm-bases" viewBox="0 0 44 32" width={w} height={h} role="img" aria-label={baseLabel}>
        <rect x="17" y="2" width="10" height="10" transform="rotate(45 22 7)" className={bases.second ? "pm-on" : undefined} />
        <rect x="30" y="15" width="10" height="10" transform="rotate(45 35 20)" className={bases.first ? "pm-on" : undefined} />
        <rect x="4" y="15" width="10" height="10" transform="rotate(45 9 20)" className={bases.third ? "pm-on" : undefined} />
      </svg>
      <span className="pm-count" role="img" aria-label={parts}>
        {balls != null && <><span aria-hidden="true">B</span><span aria-hidden="true">{lights(clamp(balls, 3), 3, "pm-b")}</span></>}
        {strikes != null && <><span aria-hidden="true">S</span><span aria-hidden="true">{lights(clamp(strikes, 2), 2, "pm-s")}</span></>}
        {outs != null && <><span aria-hidden="true">O</span><span aria-hidden="true">{lights(clamp(outs, 2), 2, "pm-o")}</span></>}
      </span>
    </span>
  );
}

/** 依賴標記（虛線小方塊）：這個呈現需要後續資料支援。 */
export function DependencyMark({ children }: { children: ReactNode }) {
  return <span className="pm-dep">{children}</span>;
}

/** 身分標籤（選手身分與分類）：細字淡底，不與狀態章混用。 */
export function Tag({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`pm-tag ${className}`}>{children}</span>;
}
