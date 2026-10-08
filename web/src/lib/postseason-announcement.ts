// 季後賽官方公告安排（#237）。這是**公告**，不是資料庫裡的正式場次：
// 頁面上要與已有官方場號的場次分開呈現，也不得由這裡的場序推出單場連結。
//
// 內容原樣轉錄官方公告，不自行補充。公告沒寫、本站也沒取得的欄位寫成 unknown，
// 不寫成「官方未定」——兩者對讀者的意義不同（前者是本站缺資料，後者是官方依條件決定）。
//
// 維護：官方改期時只改本檔，並更新 source 的核對紀錄；經 PR 與部署生效。
// 正式場次出現在資料庫後，日期、球場與比分一律以資料庫為準（見 postseason-journey.ts）。

export type TeamSlot = { code: string } | { placeholder: "E_WINNER" };

/** 球場：固定／依挑戰賽勝隊而定（官方未定，條件明確）／本站未取得。 */
export type VenueSpec = { name: string } | { byWinner: Record<string, string> } | { unknown: true };

export type AnnouncedSlot = {
  /** "E1".."E4"、"C1".."C7"——公告的場序，不是官方場號。 */
  key: string;
  kind: "E" | "C";
  /** 系列內第幾戰。 */
  seq: number;
  /** 台北日期 YYYY-MM-DD。 */
  date: string;
  /** 台北開賽時刻 HH:mm；公告沒有時 null。 */
  start: string | null;
  /** 主客隊；null＝本站未取得。 */
  away: TeamSlot | null;
  home: TeamSlot | null;
  venue: VenueSpec;
  /** 公告標「如有必要」。 */
  conditional: boolean;
  /** 只有 E：官方賽程的 GameSno（2026-E-1…4），**只作歸併候選鍵**，主客隊碼也要一致才算同一場。 */
  officialSno?: number;
};

export type SourceCheck = {
  /** 核對日（台北）。 */
  on: string;
  /** 被核對的範圍。 */
  scope: "E" | "C" | "announcement";
  url: string;
  ok: boolean;
  note: string;
};

export type PostseasonAnnouncement = {
  year: number;
  source: {
    url: string;
    /** 官方發布日（台北）。 */
    publishedOn: string;
    /** 本站取得時刻。 */
    capturedAt: string;
    checks: SourceCheck[];
  };
  series: {
    E: { name: string; bestOf: 5; winsNeeded: 3; handicapTeam: string; teams: [string, string] };
    C: { name: string; bestOf: 7; winsNeeded: 4; seededTeam: string; opponentFrom: "E" };
  };
  slots: AnnouncedSlot[];
  reserveDays: { date: string; series: "C"; note: string }[];
};

const LIONS = "ADD011";
const BROTHERS = "ACN011";
const DRAGONS = "AAA011";
const E_WINNER: TeamSlot = { placeholder: "E_WINNER" };

/** 2026 季後賽：CPBL 官方 10/05 公告，本站 10/06 14:28 取得。 */
export const POSTSEASON_2026: PostseasonAnnouncement = {
  year: 2026,
  source: {
    url: "https://www.cpbl.com.tw/xmdoc/cont?SId=0Q278399722865824041",
    publishedOn: "2026-10-05",
    capturedAt: "2026-10-06T14:28:00+08:00",
    checks: [
      {
        on: "2026-10-08",
        scope: "E",
        url: "https://stats.cpbl.com.tw/api/proxy/v1/games/schedule?kindCode=E&year=2026&month=10",
        ok: true,
        note: "官方進階數據站 E1–E4 的日期、開賽時間、主客與球場與公告一致",
      },
      {
        on: "2026-10-08",
        scope: "C",
        url: "https://stats.cpbl.com.tw/api/proxy/v1/games/schedule?kindCode=C&year=2026&month=10",
        ok: false,
        note: "官方進階數據站尚無台灣大賽賽程，台灣大賽沿用 10/06 取得的公告",
      },
      {
        on: "2026-10-08",
        scope: "announcement",
        url: "https://www.cpbl.com.tw/xmdoc/cont?SId=0Q278399722865824041",
        ok: false,
        note: "官網公告頁讀取失敗（官網反爬挑戰），未重試",
      },
    ],
  },
  series: {
    E: { name: "季後挑戰賽", bestOf: 5, winsNeeded: 3, handicapTeam: BROTHERS, teams: [LIONS, BROTHERS] },
    C: { name: "台灣大賽", bestOf: 7, winsNeeded: 4, seededTeam: DRAGONS, opponentFrom: "E" },
  },
  slots: [
    { key: "E1", kind: "E", seq: 1, date: "2026-10-09", start: "17:05", away: { code: LIONS }, home: { code: BROTHERS }, venue: { name: "洲際" }, conditional: false, officialSno: 1 },
    { key: "E2", kind: "E", seq: 2, date: "2026-10-10", start: "17:05", away: { code: BROTHERS }, home: { code: LIONS }, venue: { name: "亞太主" }, conditional: false, officialSno: 2 },
    { key: "E3", kind: "E", seq: 3, date: "2026-10-11", start: "17:05", away: { code: LIONS }, home: { code: BROTHERS }, venue: { name: "洲際" }, conditional: true, officialSno: 3 },
    { key: "E4", kind: "E", seq: 4, date: "2026-10-12", start: "18:35", away: { code: LIONS }, home: { code: BROTHERS }, venue: { name: "洲際" }, conditional: true, officialSno: 4 },
    { key: "C1", kind: "C", seq: 1, date: "2026-10-17", start: "17:05", away: E_WINNER, home: { code: DRAGONS }, venue: { name: "大巨蛋" }, conditional: false },
    { key: "C2", kind: "C", seq: 2, date: "2026-10-18", start: "17:05", away: E_WINNER, home: { code: DRAGONS }, venue: { name: "大巨蛋" }, conditional: false },
    { key: "C3", kind: "C", seq: 3, date: "2026-10-20", start: "18:35", away: { code: DRAGONS }, home: E_WINNER, venue: { byWinner: { [BROTHERS]: "大巨蛋", [LIONS]: "亞太主" } }, conditional: false },
    { key: "C4", kind: "C", seq: 4, date: "2026-10-21", start: "18:35", away: { code: DRAGONS }, home: E_WINNER, venue: { byWinner: { [BROTHERS]: "大巨蛋", [LIONS]: "亞太主" } }, conditional: false },
    // C5–C7：手上的取證沒有主客與球場 → 未知（本站未取得），不是「官方未定」。
    { key: "C5", kind: "C", seq: 5, date: "2026-10-23", start: "18:35", away: null, home: null, venue: { unknown: true }, conditional: true },
    { key: "C6", kind: "C", seq: 6, date: "2026-10-24", start: "17:05", away: null, home: null, venue: { unknown: true }, conditional: true },
    { key: "C7", kind: "C", seq: 7, date: "2026-10-25", start: "17:05", away: null, home: null, venue: { unknown: true }, conditional: true },
  ],
  reserveDays: [
    { date: "2026-10-19", series: "C", note: "移動補賽日" },
    { date: "2026-10-22", series: "C", note: "移動補賽日" },
  ],
};

const ANNOUNCEMENTS: Record<number, PostseasonAnnouncement> = { 2026: POSTSEASON_2026 };

/** 該年度的季後公告；沒有公告的年份回 null，呼叫端走原路徑。 */
export function announcementFor(year: number): PostseasonAnnouncement | null {
  return ANNOUNCEMENTS[year] ?? null;
}
