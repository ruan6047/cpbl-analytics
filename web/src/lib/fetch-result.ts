// SSR 取數結果（#441）：把「API 失敗」保留成可辨識的值，讓頁面按區塊降級，而不是整頁錯誤。
//
// 三種結果刻意分開，⛔ 不可互相冒充：
//   - 成功：帶原 payload；payload 內的空陣列／available=false 才是「確實沒有資料」，由各區塊既有判斷處理。
//   - not_found：HTTP 404。只有呼叫端另有足夠證據時才能據此判資源不存在（D2 裁定）。
//   - 其他失敗（HTTP 非 2xx、斷線、逾時、壞 JSON）：一律是「暫時無法取得」，⛔ 不轉 404、⛔ 不轉空資料。
//
// `settle` 只吸收 ApiError；頁面衍生運算或 render 拋的其他錯誤照常往上，交給既有錯誤邊界。
import { ApiError, type SourceFailure } from "./http-error.ts";

export type Fetched<T> =
  | { ok: true; data: T }
  | { ok: false; failure: SourceFailure; status: number };

/** 一般 SSR 取數的逾時上限。這是 #441 規劃的建議參數，不是量測出的正式 API 延遲保證；
 *  可用 `API_FETCH_TIMEOUT_MS` 覆寫（驗證與排查用）。 */
export const SSR_FETCH_TIMEOUT_MS = Number(process.env.API_FETCH_TIMEOUT_MS) > 0
  ? Number(process.env.API_FETCH_TIMEOUT_MS) : 5000;

function isTimeout(error: unknown): boolean {
  return error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
}

/** 取 JSON；任何失敗都轉成帶分類的 ApiError。這一層的 fetch 一律 no-store：不讓 Next 另存原始 HTTP 回應
 *  （包括 HTTP 200 的壞 JSON）。跨請求共用只發生在外層 api-cache.ts，且只存成功解析的資料（#441 規劃 v2）。 */
export async function fetchApiJson<T>(base: string, path: string, timeoutMs = SSR_FETCH_TIMEOUT_MS): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
  } catch (error) {
    throw new ApiError(path, 0, isTimeout(error) ? "timeout" : "network");
  }
  if (!res.ok) throw new ApiError(path, res.status);
  try {
    return (await res.json()) as T;
  } catch (error) {
    // 讀 body 途中逾時也算逾時；其餘是回應格式壞掉。
    throw new ApiError(path, 0, isTimeout(error) ? "timeout" : "parse");
  }
}

/** 把一個 API promise 轉成結果值。只吸收 ApiError，其他例外照常拋出。 */
export async function settle<T>(promise: Promise<T>): Promise<Fetched<T>> {
  try {
    return { ok: true, data: await promise };
  } catch (error) {
    if (error instanceof ApiError) return { ok: false, failure: error.failure, status: error.status };
    throw error;
  }
}

/** 已解決的成功值；失敗回 null。⚠️ 只在呼叫端另外用 `failed()` 標示錯誤時使用，
 *  ⛔ 不可把這個 null 當成「沒有資料」。 */
export const dataOf = <T>(r: Fetched<T> | Fetched<null>): T | null => (r.ok ? r.data : null);

/** 來源暫時無法取得（不含 404）。 */
export const failed = (r: Fetched<unknown>): boolean => !r.ok && r.failure !== "not_found";

/** HTTP 404：只代表「該端點說找不到」，是否等於資源不存在由呼叫端依其他證據判斷。 */
export const notFoundResult = (r: Fetched<unknown>): boolean => !r.ok && r.failure === "not_found";

/** 已完成但未請求的區塊：條件不適用時放這個，讓型別一致而不發請求。 */
export const SKIPPED = { ok: true, data: null } as const satisfies Fetched<null>;

/** 區塊降級的統一文案（規劃 §3.1）。不輸出內部 URL、status 或例外細節給訪客。 */
export const unavailableCopy = (label: string) => `${label}資料暫時無法取得，請稍後重新整理。`;
