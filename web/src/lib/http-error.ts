/** API 來源失敗的分類（#441）。`not_found` 只來自 HTTP 404；其餘一律是「暫時無法取得」，
 *  ⛔ 不得被呼叫端解讀成資源不存在或「沒有資料」。 */
export type SourceFailure = "not_found" | "http" | "network" | "timeout" | "parse";

export class ApiError extends Error {
  readonly path: string;
  /** HTTP status；非 HTTP 失敗（斷線、逾時、壞 JSON）為 0。 */
  readonly status: number;
  readonly failure: SourceFailure;

  constructor(path: string, status: number, failure?: SourceFailure) {
    super(`API ${path} → ${status || failure}`);
    this.name = "ApiError";
    this.path = path;
    this.status = status;
    this.failure = failure ?? (status === 404 ? "not_found" : "http");
  }
}

export async function optionalNotFound<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
