// 伺服器端 API 成功資料的跨請求快取（#441 規劃 v2 §4.1）。只給 Server Component／server 模組用。
//
// 原則：成功共享、失敗不共享、live 語意保留。
//   - 只有「成功取得且成功解析」的 JSON 會寫入快取，依原端點 TTL 跨請求共用（保留 7e9c55c1 的請求量）。
//   - HTTP 非 2xx、斷線、逾時、壞 JSON 一律在被快取函式內拋 ApiError → 不寫入快取；轉成區塊降級
//     （settle／SourceUnavailable／metadata 中性標題）全部在快取外處理。⛔ 不可在被快取函式內 catch 後回傳
//     null／空陣列／錯誤值，否則降級結果會被保存，API 恢復後下一次請求仍顯示錯誤（違反驗收 3）。
//   - 內層 fetch 是 no-store（fetchApiJson）：防止 Next 另存一份原始 HTTP 回應（例如 HTTP 200 的壞 JSON），
//     那份會繞過上述「只存成功解析」的規則。
//   - 即時端點不走這裡（api.ts 的 getLive／live journey）。
import { unstable_cache } from "next/cache";
import { fetchApiJson } from "./fetch-result.ts";

/** 快取格式版本：改變快取內容形狀或鍵的組成時要遞增，避免讀到舊格式。 */
export const API_CACHE_FORMAT = "cpbl-441-v2-json-1";

export type SharedCache = <T>(load: () => Promise<T>, key: string[], ttlSeconds: number) => Promise<T>;

const nextDataCache: SharedCache = (load, key, ttlSeconds) =>
  unstable_cache(load, key, { revalidate: ttlSeconds })();

let sharedCache: SharedCache = nextDataCache;

/** 測試替身：node:test 沒有 Next 的 incrementalCache，以記憶體實作取代（null 還原為 Next 資料快取）。
 *  產品程式不得呼叫。 */
export function setSharedCacheForTest(impl: SharedCache | null): void {
  sharedCache = impl ?? nextDataCache;
}

/** 快取鍵：格式版本＋API 基底＋完整路徑與 query＋TTL。不含任何每次請求不同的值、headers 或 cookies。 */
export const apiCacheKey = (base: string, path: string, ttlSeconds: number) =>
  [API_CACHE_FORMAT, base, path, `ttl=${ttlSeconds}`];

/** 取 API JSON，成功結果依 TTL 跨請求共用；失敗拋 ApiError、不進快取。 */
export function cachedApiJson<T>(base: string, path: string, ttlSeconds: number): Promise<T> {
  return sharedCache(() => fetchApiJson<T>(base, path), apiCacheKey(base, path, ttlSeconds), ttlSeconds);
}
