// 測試用的記憶體共享快取（#441 規劃 v2）。語意比照 Next 資料快取被 unstable_cache 使用時的行為：
// load 成功才寫入、TTL 內同鍵直接回存值、load 拋錯不寫入並照常拋出。只供 *.test.ts 使用。
// 真正的 Next 跨請求快取行為由 standalone 矩陣驗證（node:test 沒有 incrementalCache）。
import type { SharedCache } from "./api-cache.ts";

export function memorySharedCache(now: () => number = Date.now) {
  const store = new Map<string, { value: unknown; expires: number }>();
  const keys: string[][] = [];
  const impl: SharedCache = async <T>(load: () => Promise<T>, key: string[], ttlSeconds: number) => {
    keys.push(key);
    const k = JSON.stringify(key);
    const hit = store.get(k);
    if (hit && hit.expires > now()) return hit.value as T;
    const value = await load();               // 拋錯 → 不寫入
    store.set(k, { value, expires: now() + ttlSeconds * 1000 });
    return value;
  };
  return { impl, store, keys };
}
