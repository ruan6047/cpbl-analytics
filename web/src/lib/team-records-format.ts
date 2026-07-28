// 「即將挑戰的紀錄」隊史卡（refreshed）的呈現決策（UX-TEAM-HOTZONE1 追加）。
//
// 需求方裁定：`refreshed` 卡明細行原本恆帶「原紀錄 N（保持人）」，但六隊實測
// 21 筆 refreshed 中 19 筆是「自己刷新自己」——`prior_record` 只是他自己上季
// 結束時的舊基準，不是他超越了某個對象，「原紀錄」措辭在自己刷新自己時是
// 誤導。處置：
//   - 原紀錄保持人＝本人 → 明細只留「目前 N」，不顯示原紀錄段落。
//   - 原紀錄保持人是別人 → 原紀錄段落移進點擊/hover 的 Tooltip 氣泡，不佔常駐
//     明細行版位。
//
// 判斷「是否本人」**一律比對 player_id**，不比 name 字串——同名不同人、改名
// （`players.name` 會過期）等情境比名字會出錯，這是專案既有紅線（跨表一律
// player_id join）。抽成純函式便於不依賴 DOM 的單元測試直接釘住這條規則。

export type FranchiseRefreshedHolderFields = {
  player_id: string;
  name: string;
  prior_holder_id: string | null;
  prior_holder: string;
};

/** 原紀錄保持人是否為本人。**只比對 `player_id`／`prior_holder_id`，刻意不看
 * `name`／`prior_holder` 這兩個字串欄位**——即使型別上收了它們（貼近真實
 * payload 形狀，讓測試能真的建構「同人不同姓名字串」情境），比對邏輯也不得
 * 碰它們。`prior_holder_id` 為 null（並列多人，無法唯一判定）時保守回傳
 * false——寧可多顯示一個氣泡，不要在並列情境下誤判成本人而漏資訊。 */
export function isSelfRefresh(row: FranchiseRefreshedHolderFields): boolean {
  return row.prior_holder_id !== null && row.prior_holder_id === row.player_id;
}
