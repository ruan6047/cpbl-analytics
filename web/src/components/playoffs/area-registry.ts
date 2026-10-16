import type { AreaRegistration } from "@/lib/playoffs-areas";

// `/playoffs` 第 2／3 區登記（#285 續做 WP2；MOUNT-CONTRACT r3 §4）。
// 各卡在自己的 PR 只加兩行：import 自己的 Section（與 notes 函式）＋這裡一筆登記。
// 沒有登記 ⇒ 該區外框、標題、錨點都不出現（需求方 C1）。陣列順序不影響畫面（依 C2 固定順序排）。
// `any`：各區 payload 型別不同，由各卡登記時自帶（AreaRegistration<各自型別>）。
export const PLAYOFFS_AREAS: AreaRegistration<any>[] = [];
