// 方案 B 導覽模型（PRODUCT_UX_BLUEPRINT v0.2 §4.1、§5.5）。
// 純資料 + 純函式，供 layout/nav-links 與元件測試共用。

export type NavItem = {
  href: string;
  label: string;
  /** 除 href 外也視為同一導覽項的路徑前綴（如「球員」涵蓋投手排行與個人頁）。 */
  match?: string[];
  /** 行動端面板分組眉標。 */
  group?: string;
};

/** 頂層導覽：今日／賽程／戰績／球員／對戰，另加「更多」展開選單。 */
export const PRIMARY_NAV: NavItem[] = [
  { href: "/", label: "今日", group: "主要" },
  { href: "/games", label: "賽程", group: "主要" },
  { href: "/standings", label: "戰績", group: "主要" },
  // 需求方 2026-07-17 決策（§12-3）：固定進打者排行，角色切換在排行介面內。
  { href: "/batters", label: "球員", match: ["/pitchers", "/players"], group: "主要" },
  { href: "/matchups", label: "對戰", group: "主要" },
];

// 需求方 2026-07-17 決策（§12-2）：紀錄室桌機維持在「更多」，與球場同層。
// 「賽事預測」暫收於此：§4.1 要求 /predict 不競爭主要導覽位置，§7.1 要求
// 首頁替代品（UX-GAME-HOME1）上線後才由 DEP-PREDICT-LEGACY1 移除入口。
// 「方法」待 UX-MODEL-METHOD1 建立 /methodology 後才加入，避免導覽指向 404。
export const MORE_NAV: NavItem[] = [
  { href: "/records", label: "紀錄室", group: "更多" },
  { href: "/venues", label: "球場", group: "更多" },
  { href: "/predict", label: "賽事預測", group: "更多" },
];

/**
 * 目前路徑是否落在該導覽項下。
 * 「今日」只在首頁精確命中；其餘比對路徑邊界，避免 /venues 被 /venues-x 之類誤判。
 */
export function isNavActive(item: NavItem, pathname: string): boolean {
  if (item.href === "/") return pathname === "/";
  return [item.href, ...(item.match ?? [])].some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

/** 「更多」按鈕是否需顯示為作用中（收納項之一命中）。 */
export function isMoreActive(pathname: string): boolean {
  return MORE_NAV.some((item) => isNavActive(item, pathname));
}
