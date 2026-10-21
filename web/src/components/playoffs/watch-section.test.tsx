import assert from "node:assert/strict";
import test from "node:test";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Tooltip } from "@/components/tooltip.tsx";
import { WatchSection } from "./watch-section.tsx";
import { streakOf, streakText } from "./watch-load.ts";
import { PitcherLoadRow } from "./watch-load-strip.tsx";
import type { Load, LoadLevel, PlayoffsWatch, RecentAppearance, WatchPitcher, WatchStarter, WatchTeam } from "@/lib/playoffs-watch.ts";

// #289 S08 WP3：第 4 區各態文字（灰／綠／橘／紅／先發不套燈號）、名單缺。
// #314：4B 占位移除；官方先發投手改為兩隊各一格（已公告／待公告／暫時無法取得）。
// #300 S08c：4A 改懶人包呈現——說明句從常駐改進 `Tooltip`。#289 版的每條斷言都保留，只把「在畫面上」
// 換成「在畫面上」或「在提示裡」其中一層（`visible()`／`tips()`）。需求方逐項裁定移除的項目
// （6191101762，PLAN-r2 §16 的 E14／E16／E19／E20／E22／E24／E25）改為「兩層都不出現」並註明項次。

function text(node: ReactNode): string {
  return renderToStaticMarkup(<>{node}</>).replace(/<[^>]*>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
}

/** 平常畫面：SSR 不渲染 `Tooltip` 內容（掛載後、互動時才 portal 出來），所以這就是「沒互動時看得到的字」。 */
const visible = (data: PlayoffsWatch | null) => text(<WatchSection data={data} />);

/** 展開元件樹（本區元件都無 hook，可直接呼叫），收集每個 `Tooltip` 的觸發元素與提示內容。 */
function collectTips(node: ReactNode, out: { trigger: ReactElement; content: ReactNode }[] = []) {
  if (Array.isArray(node)) { node.forEach((n) => collectTips(n, out)); return out; }
  if (!isValidElement(node)) return out;
  const el = node as ReactElement<{ children?: ReactNode; content?: ReactNode }>;
  if (el.type === Tooltip) {
    out.push({ trigger: el.props.children as ReactElement, content: el.props.content });
    collectTips(el.props.children, out);
  } else if (typeof el.type === "function") {
    collectTips((el.type as (p: unknown) => ReactNode)(el.props), out);
  } else {
    collectTips(el.props.children, out);
  }
  return out;
}

/** 所有提示內容的文字（桌機移入／手機點一下才出現）。 */
const tips = (data: PlayoffsWatch | null) => collectTips(<WatchSection data={data} />).map((t) => text(t.content)).join(" | ");

const days = (p: [number, number, number, number], complete = [true, true, true, true]) =>
  [3, 2, 1, 0].map((k, i) => ({ date: `2026-10-${String(17 - k).padStart(2, "0")}`, offset: k, pitches: p[i],
    appearances: p[i] ? 1 : 0, complete: complete[i], live: false }));

function load(level: LoadLevel, extra: Partial<Load> = {}): Load {
  return {
    policy_version: "playoffs-policy/v2.0-proposed", target_date: "2026-10-17", level, label: "", complete: level !== "unknown",
    metrics: { P0: 0, P1: 0, S2: 0, S3: 0, C: 0, Q: 0 }, c_at_least: false, triggers: [], days: days([0, 0, 0, 0]),
    incomplete: [], unattributed: [], live: false, last_pitch_date: "2026-10-12", full_rest_days: 4,
    rest_unknown_reason: null, ...extra,
  };
}

function pitcher(id: string, role: string | null, l: Load, visible = true): WatchPitcher {
  return { player_id: id, name: `投手${id}`, tactical_role: role, role_source: "本站註記（非官方數據）",
    default_visible: visible, load: l, consecutive_era: null,
    recent: [{ game_key: { year: 2026, kind_code: "E", game_sno: 4 }, date: "2026-10-12", date_trusted: true,
      role_type: "中繼", pitches: 18, outs: 3, ip: "1.0" }],
    registration: { status: "unknown", text: "未知（當場登錄來源尚未接入）" } };
}

test("兼任先發與長中繼只列一位投手，完整兩標籤與原low燈號", () => {
  const p = { ...pitcher("0000000001", null, load("low")), role_format_version: 2 as const,
    tactical_roles: ["先發", "長中繼"] };
  const markup = renderToStaticMarkup(<PitcherLoadRow p={p} scaleMax={1} />);
  assert.equal((markup.match(/data-role=/g) ?? []).length, 2);
  assert.match(text(<PitcherLoadRow p={p} scaleMax={1} />), /#先發.*#長中繼/);
  assert.doesNotMatch(markup, /角色未標記/);
  assert.equal((markup.match(/data-level="low"/g) ?? []).length, 1);
});

// #347 續修：版面契約測試（靜態 markup 的 class 代理指標）。
// 能抓到：版面 class 被改回去（燈號回到 shrink-0、第 1 輪列結構被拆）而測試照樣通過的情境。
// ⛔ 抓不到實際幾何：globals.css／token 改動、新增更長文字、字型改變都要真的排版才看得出來，不能取代正式站截圖。
const classOf = (html: string, attr: string): string[] =>
  [...html.matchAll(new RegExp(`<[^>]*\\b${attr}(?![-\\w])(?:="[^"]*")?[^>]*>`, "g"))].map((m) => / class="([^"]*)"/.exec(m[0])?.[1] ?? "");
const tokens = (cls: string) => cls.split(/\s+/);

test("版面契約（#347）：先發與「未知＋資料不完整」燈號可在左欄內換行，文字原封不動", () => {
  const unknownGap = load("unknown", { incomplete: [{ date: "2026-10-15", offset: 2, reasons: ["box_missing"], text: ["尚未送達"] }] });
  for (const p of [pitcher("1", "先發", load("starter_exempt")), pitcher("2", "中繼", unknownGap)]) {
    const html = renderToStaticMarkup(<PitcherLoadRow p={p} scaleMax={1} />);
    const lamps = classOf(html, "data-lamp");
    assert.equal(lamps.length, 1);
    const lamp = tokens(lamps[0]);
    assert.ok(!lamp.includes("shrink-0"), `燈號不得 shrink-0：${lamps[0]}`);
    for (const c of ["min-w-0", "max-w-full"]) assert.ok(lamp.includes(c), `燈號須含 ${c}：${lamps[0]}`);
    const lampText = classOf(html, "data-lamp-text");
    assert.equal(lampText.length, 1);
    assert.ok(!/whitespace-nowrap|shrink-0/.test(lampText[0]), `燈號文字須可換行：${lampText[0]}`);
    assert.ok(tokens(classOf(html, "data-name")[0]).includes("[overflow-wrap:anywhere]"));
  }
  assert.match(text(<PitcherLoadRow p={pitcher("1", "先發", load("starter_exempt"))} scaleMax={1} />), /先發投手，不套用牛棚負荷燈號/);
  assert.match(text(<PitcherLoadRow p={pitcher("2", "中繼", unknownGap)} scaleMax={1} />), /未知.*資料不完整/);
});

test("版面契約（#347）：第 1 輪列結構不退化（li flex-wrap、左欄 basis-20 min-w-0、日條 w-56 shrink-0、摘要可換行）", () => {
  const html = renderToStaticMarkup(<PitcherLoadRow p={pitcher("1", "中繼", load("low"))} scaleMax={1} />);
  const li = tokens(classOf(html, "data-level")[0]);
  assert.ok(li.includes("flex-wrap"), li.join(" "));
  const left = tokens(/<li[^>]*><div class="([^"]*)"/.exec(html)?.[1] ?? "");
  for (const c of ["basis-20", "min-w-0"]) assert.ok(left.includes(c), `左欄須含 ${c}：${left.join(" ")}`);
  const strip = tokens(classOf(html, "data-strip")[0]);
  for (const c of ["w-56", "shrink-0"]) assert.ok(strip.includes(c), `日條須含 ${c}：${strip.join(" ")}`);
  const summary = classOf(html, "data-streak");
  assert.equal(summary.length, 1);
  assert.ok(!tokens(summary[0]).includes("whitespace-nowrap"), summary[0]);
});

function team(code: string, pitchers: WatchPitcher[], roster = true): WatchTeam {
  return { side: code === "ACN011" ? "away" : "home", team_code: code,
    roster_status: roster ? "submitted" : "missing",
    roster: roster ? { roster_id: "r", published_date: "2026-10-16", source_url: null, annotation_version: 1, note: "" } : null,
    roster_text: roster ? null : "32 人名單尚未提交", days: [], pitchers };
}

function watch(teams: WatchTeam[], extra: Partial<PlayoffsWatch> = {}): PlayoffsWatch {
  return {
    contract: "playoffs-watch/v1", status: "ok", policy_version: "playoffs-policy/v2.0-proposed", year: 2026, series: "C",
    series_id: null, context_version: "c", watch_version: "w", target_game_key: { year: 2026, kind_code: "C", game_sno: 1 },
    requested_game_key: null,
    as_of: { now: "2026-10-17T02:00:00Z", taipei_date: "2026-10-17", last_refresh_at: "2026-10-17T02:24:00Z",
      last_completed_game_date: "2026-10-12" },
    scope: { kinds: ["A", "E", "C", "D"], note: "近三日含一軍例行賽 A、季後 E／C 與二軍 D 已完賽正式場的投手逐場球數" },
    coverage: "complete", missing_reason: [], source_manifest: [],
    registration: { status: "unknown", reason: "registration_source_not_delivered", text: "未知（當場登錄來源尚未接入）" },
    starters: ["ACN011", "AAA011"].map((t) => pending(t)),
    teams, ...extra,
  };
}

function pending(t: string): WatchStarter {
  return { team_code: t, status: "pending", reason: "starter_not_announced", player_id: null, name: null, text: "待公告" };
}

function announced(t: string, id: string, name: string | null): WatchStarter {
  return { team_code: t, status: "announced", reason: name ? null : "starter_name_missing", player_id: id, name,
    text: name ?? "已公告（姓名待更新）" };
}

const re = (s: string) => new RegExp(s.replace(/[()（）+?.]/g, "."));

test("四種燈號與先發不套燈號：顏色旁都有文字", () => {
  const d = watch([team("ACN011", [
    pitcher("1", "終結", load("high", { triggers: [{ metric: "P1", value: 30, threshold: 30 }] })),
    pitcher("2", "勝利組", load("medium", { triggers: [{ metric: "C", value: 2, threshold: 2 }] })),
    pitcher("3", "長中繼", load("low")),
    pitcher("4", "輪值", load("starter_exempt"), false),
  ])]);
  const v = visible(d);
  const t = tips(d);
  // 燈號點＋等級文字常駐（需求方裁定 1：保留燈號）。
  for (const s of ["高負荷", "中負荷", "低負荷", "先發投手，不套用牛棚負荷燈號"]) assert.match(v, re(s));
  // 觸發理由改由點／移入燈號出現。
  for (const s of ["前一日 30 球（≥30）", "連續 2 日登板（≥2）"]) {
    assert.match(t, re(s));
    assert.doesNotMatch(v, re(s));
  }
  // proposed 標記：畫面上常駐短籤，全文在區塊 ⓘ。
  assert.match(v, /建議門檻/);
  assert.match(t, /playoffs-policy\/v2\.0-proposed/);
  assert.match(t, /不是健康判斷、可用性或教練調度/);
  assert.doesNotMatch(v, /不是健康判斷/);
});

test("灰色：列已知球數與理由，不出觸發理由、不寫可用", () => {
  const l = load("unknown", { days: days([0, 0, 20, 0], [true, false, true, true]), triggers: [],
    metrics: { P0: 0, P1: 20, S2: null, S3: null, C: null, Q: 0 },
    incomplete: [{ date: "2026-10-15", offset: 2, reasons: ["box_missing"], text: ["該隊當日正式場已完賽，但投手逐場紀錄尚未送達"] }],
    full_rest_days: null, last_pitch_date: null, rest_unknown_reason: "box_missing" });
  const d = watch([team("AAA011", [pitcher("9", "終結", l)])]);
  const v = visible(d);
  const t = tips(d);
  assert.match(v, /未知/);
  assert.match(v, /資料不完整/); // 可見短標；原因句在燈號提示
  assert.match(t, /資料不完整：10\/15 該隊當日正式場已完賽，但投手逐場紀錄尚未送達/);
  assert.doesNotMatch(v, /該隊當日正式場已完賽/);
  // 已知球數照列、不完整日不寫成 0：#289 版寫在「近期球數」行（E14 移除），現由日條格承擔。
  const cells = [...renderToStaticMarkup(<WatchSection data={d} />).matchAll(/data-day="(\d)" data-complete="(\d)"[^>]*><span[^>]*>([^<]+)</g)]
    .map((m) => `${m[1]}:${m[2]}:${m[3]}`);
  assert.deepEqual(cells, ["3:1:0", "2:0:?", "1:1:20", "0:1:0"]);
  assert.doesNotMatch(t, /近期球數/); // E14
  assert.doesNotMatch(`${v} ${t}`.replace("不是健康判斷、可用性或教練調度", ""), /可用|待命/);
  assert.doesNotMatch(`${v} ${t}`, /連續登板/); // E16；灰的「連投 ?」見下
  assert.match(t, /完整休息 無法判定（近期資料不完整）/);
  // R1：未知 ⛔ 顯示成不累——不出低負荷、不出綠點、摘要不給數字、不完整日格是「?」不是 0。
  const html = renderToStaticMarkup(<WatchSection data={d} />);
  assert.doesNotMatch(v, /低負荷/);
  assert.doesNotMatch(html, /bg-ball/);
  assert.match(html, /data-streak="unknown"[^>]*>連投 \?</);
  assert.match(html, /data-day="2" data-complete="0"[^>]*><span[^>]*>\?</);
});

test("角色未標記的投手不被刪除，收在其他投手", () => {
  const html = renderToStaticMarkup(<WatchSection data={watch([team("ACN011", [
    pitcher("1", "終結", load("low")), pitcher("5", null, load("low"), false), pitcher("6", "unclassified", load("low"), false)])])} />);
  assert.match(html, /<details[^>]*>.*其他投手（.*2.*）/s);
  assert.match(visible(watch([team("ACN011", [pitcher("5", null, load("low"), false)])])), /角色未標記/);
});

test("4B 占位已移除（#314）：不出現兩格、賽前快照或已鎖定樣式", () => {
  const html = renderToStaticMarkup(<WatchSection data={watch([])} />);
  assert.doesNotMatch(html, /賽前快照尚未發布|S09/);
  assert.doesNotMatch(html, /data-slot=/);
  assert.doesNotMatch(html, /推測候選|官方先發與看點/);
  assert.doesNotMatch(html, /已鎖定|locked/);
  assert.doesNotMatch(html, /打序|先發公告/);
});

test("官方先發投手：未公告 ⇒ 兩格各寫「待公告」，標題「官方先發投手」", () => {
  const d = watch([]);
  const html = renderToStaticMarkup(<WatchSection data={d} />);
  assert.equal((html.match(/data-starter-status="pending"/g) ?? []).length, 2);
  assert.match(visible(d), /官方先發投手.*兄弟 待公告.*味全 待公告 牛棚近期使用負荷/);
  assert.equal((visible(d).match(/待公告/g) ?? []).length, 2);
  assert.doesNotMatch(visible(d), /S11|未知|先發對決與看點/);
});

test("官方先發投手：已公告顯示姓名（客、主順序），查無姓名寫「已公告（姓名待更新）」，不顯示 acnt", () => {
  const d = watch([], { starters: [announced("ACN011", "0000005151", "羅戈"), announced("AAA011", "0000007779", null)] });
  const v = visible(d);
  assert.ok(v.indexOf("羅戈") < v.indexOf("已公告（姓名待更新）"));
  assert.doesNotMatch(renderToStaticMarkup(<WatchSection data={d} />), /0000005151|0000007779/);
  assert.equal((renderToStaticMarkup(<WatchSection data={d} />).match(/data-starter-status="announced"/g) ?? []).length, 2);
  // 單邊公告：另一隊仍待公告。
  const one = visible(watch([], { starters: [announced("ACN011", "0000005151", "羅戈"), pending("AAA011")] }));
  assert.match(one, /羅戈/);
  assert.match(one, /待公告/);
});

test("官方先發投手：讀取失敗寫「暫時無法取得」；不顯示公告時間或負荷連結，未更換時不出更換標示", () => {
  const fail = watch([], { starters: ["ACN011", "AAA011"].map((t) => ({ team_code: t, status: "unknown" as const,
    reason: "starter_source_unavailable", player_id: null, name: null, text: "暫時無法取得" })) });
  assert.equal((visible(fail).match(/暫時無法取得/g) ?? []).length, 2);
  const d = watch([], { starters: [announced("ACN011", "0000005151", "羅戈"), announced("AAA011", "0000007779", "蔣銲")] });
  const html = renderToStaticMarkup(<WatchSection data={d} />);
  const starterBlock = html.slice(html.indexOf("官方先發投手"), html.indexOf("牛棚近期使用負荷"));
  assert.doesNotMatch(starterBlock, /公告時間|更新於|\d{1,2}:\d{2}|已更換|更換|<a /);
});

test("官方先發投手（#320 A2）：更換顯示「{姓名}（已更換）」、撤回顯示「待公告（先前公告已撤回）」，不出時間", () => {
  const changed: WatchStarter = { ...announced("ACN011", "0000005151", "羅戈"), classification: "changed", text: "羅戈（已更換）" };
  const retracted: WatchStarter = { ...pending("AAA011"), classification: "retracted", text: "待公告（先前公告已撤回）" };
  const d = watch([], { starters: [changed, retracted], starters_classification: "partial" });
  const html = renderToStaticMarkup(<WatchSection data={d} />);
  const v = visible(d);
  assert.match(v, /官方先發投手.*兄弟 羅戈（已更換）.*味全 待公告（先前公告已撤回） 牛棚近期使用負荷/);
  // status 值域不變：更換仍是 announced、撤回仍是 pending（#314 守門意圖保留）。
  assert.equal((html.match(/data-starter-status="announced"/g) ?? []).length, 1);
  assert.equal((html.match(/data-starter-status="pending"/g) ?? []).length, 1);
  const starterBlock = html.slice(html.indexOf("官方先發投手"), html.indexOf("牛棚近期使用負荷"));
  assert.doesNotMatch(starterBlock, /公告時間|更新於|\d{1,2}:\d{2}|0000005151|<a /);
  // 部分公告逐隊呈現、不另加標籤。
  assert.doesNotMatch(starterBlock, /部分公告|partial/);
});

test("名單未提交：不列投手", () => {
  const d = watch([team("ACN011", [], false)]);
  assert.match(visible(d), /32 人名單尚未提交；不以出賽紀錄代替名單/);
  assert.doesNotMatch(tips(d), /預設列名單中/); // #289 版只在名單已提交時出現這句
  assert.doesNotMatch(`${visible(d)} ${tips(d)}`, /近期球數/);
  assert.doesNotMatch(renderToStaticMarkup(<WatchSection data={d} />), /data-strip/);
});

test("非目前目標與讀取失敗", () => {
  assert.match(visible(watch([], { status: "historical_not_published", text: "本場已完賽，觀戰重點只提供系列下一場" })),
    /本場已完賽，觀戰重點只提供系列下一場/);
  assert.match(visible(null), /第 4 區資料暫時無法讀取/);
});

test("連投 ERA 與逐人當場登錄依裁定不呈現（E19／E20）", () => {
  // #289 版：「3 場 0.0 局 自責 1・ERA 不可定義」＋口徑＋「不代表連投導致此成績」；#300 6191101762 裁定移除。
  const p = pitcher("1", "勝利組", load("medium"));
  p.consecutive_era = { scope: "本季一軍例行賽（A）", appearances: 3, outs: 0, ip: "0.0", er: 1, era: null, complete: true, excluded_untrusted: 0 };
  const d = watch([team("ACN011", [p])]);
  const both = `${visible(d)} ${tips(d)}`;
  assert.doesNotMatch(both, /ERA|自責|不代表連投導致此成績|連投時成績/);
  assert.doesNotMatch(both, /當場登錄/);
});

// —— #300 S08c：可見層 vs 提示層 ——————————————————————————————————————————————

test("平常畫面不出現說明句；裁定保留的都在提示裡、裁定移除的兩層都不出現", () => {
  const p = pitcher("1", "終結", load("medium", { triggers: [{ metric: "S2", value: 26, threshold: 25 }],
    days: days([0, 10, 16, 0]), metrics: { P0: 0, P1: 16, S2: 26, S3: 26, C: 2, Q: 0 },
    unattributed: [{ game_key: { year: 2026, kind_code: "A", game_sno: 9 }, pitches: 12, possible_dates: [] }] }));
  p.consecutive_era = { scope: "本季一軍例行賽（A）", appearances: 2, outs: 6, ip: "2.0", er: 0, era: 0, complete: true, excluded_untrusted: 0 };
  const tm = team("ACN011", [p]);
  tm.days = [{ date: "2026-10-15", offset: 2, complete: false, reasons: ["box_missing"], text: ["投手逐場紀錄尚未送達"], live: false }];
  const d = watch([tm]);
  const v = visible(d);
  const t = tips(d);
  const html = renderToStaticMarkup(<WatchSection data={d} />);
  assert.doesNotMatch(html, /role="tooltip"/);
  // #289 版常駐、#300 改進提示且裁定保留的每一句（逐項對照表的機器版；E 編號＝PLAN-r2 §16）。
  for (const s of [
    "球數與出賽日的描述，不是健康判斷、可用性或教練調度", // E21（ⓘ）
    "門檻為本站建議值（playoffs-policy/v2.0-proposed，尚未經歷史資料校準）", // E23（建議門檻籤提示）
    "預設列名單中 #終結、#勝利組、#長中繼；角色為本站註記，非官方數據", // E26（ⓘ）
    "10/15（前天）：投手逐場紀錄尚未送達", // E3 隊伍缺資料原因（日標籤同 E8 改白話）
    "近 2 日共 26 球（≥25）", // E12
    "完整休息 4 天（最後投球 10/12）", // E15
    "保留賽 另有保留賽 12 球日期未定", // E14 保留部分
    "最近登板 10/12 挑戰賽G4 18 球・1.0 局", // E18
    "連投局數 無法判定：最近登板清單只含 1 筆", // E17
  ]) {
    assert.match(t, re(s), `提示裡找不到：${s}`);
    assert.doesNotMatch(v, re(s), `平常畫面不該出現：${s}`);
  }
  // 需求方裁定移除（6191101762）：兩層都不出現。
  for (const s of [
    d.scope.note, // E22
    "資料最後同步", // E24
    "當場 28 人登錄", // E25
    "近期球數", // E14 逐日部分
    "連續登板", // E16
    "連投時成績", // E19
    "當場登錄", // E20
  ]) {
    assert.doesNotMatch(`${v} | ${t}`, re(s), `已裁定移除卻仍出現：${s}`);
  }
  // 常駐的只有狀態：建議門檻籤、資料更新時間、隊伍缺資料短標、保留賽 +? 記號、連投摘要。
  assert.match(v, /建議門檻/);
  assert.match(v, /資料更新 10\/17 10:24/);
  assert.match(v, /部分日期資料不完整/);
  assert.match(v, /保留賽 \+\?/);
  assert.match(v, /連投 2 天・26 球・\? 局/);
});

test("日條：4 格固定 3 天前→今日、數字常駐、比例尺＝4A 已知單日最大值", () => {
  const a = pitcher("1", "終結", load("low", { days: days([5, 0, 20, 0]) }));
  const b = pitcher("2", "勝利組", load("low", { days: days([0, 40, 0, 0]) }));
  const html = renderToStaticMarkup(<WatchSection data={watch([team("ACN011", [a]), team("AAA011", [b])])} />);
  const row = html.slice(html.indexOf("投手1"), html.indexOf("投手2"));
  assert.deepEqual([...row.matchAll(/data-day="(\d)"/g)].map((m) => m[1]), ["3", "2", "1", "0"]);
  assert.deepEqual([...row.matchAll(/text-\[11px\] text-muted">([^<]+)</g)].map((m) => m[1]), ["3 天前", "前天", "昨天", "今日"]); // E8
  assert.match(row, /height:50%/); // 20 ÷ 40（另一隊的最大值）
  assert.match(row, /height:13%/); // 5 ÷ 40
  assert.match(html.slice(html.indexOf("投手2")), /height:100%/);
});

// —— #300 S08c：連投摘要（天數＋期間球數＋期間局數，fail-closed）——————————————————————

const rp = (date: string, outs: number | null, trusted = true): RecentAppearance => ({
  game_key: { year: 2026, kind_code: "C", game_sno: 1 }, date, date_trusted: trusted, role_type: "中繼",
  pitches: 10, outs, ip: outs == null ? null : `${Math.floor(outs / 3)}.${outs % 3}`,
});

function sp(metrics: Partial<Load["metrics"]>, recent: RecentAppearance[], extra: Partial<Load> = {}) {
  const p = pitcher("1", "終結", load("low", { metrics: { P0: 0, P1: 0, S2: 0, S3: 0, C: 0, Q: 0, ...metrics }, ...extra }));
  p.recent = recent;
  return streakText(streakOf(p));
}

test("連投摘要：C=0 昨日未登板（不寫可用／待命）", () => {
  assert.equal(sp({ C: 0 }, [rp("2026-10-15", 3)], { days: days([0, 12, 0, 0]) }), "昨日未登板");
});

test("連投摘要：C=1／2／3 取 P1／S2／S3，局數由 recent 加總", () => {
  assert.equal(sp({ C: 1, P1: 20 }, [rp("2026-10-16", 4)], { days: days([0, 0, 20, 0]) }), "連投 1 天・20 球・1.1 局");
  assert.equal(sp({ C: 2, P1: 20, S2: 35 }, [rp("2026-10-16", 3), rp("2026-10-15", 2)], { days: days([0, 15, 20, 0]) }),
    "連投 2 天・35 球・1.2 局");
  assert.equal(sp({ C: 3, S3: 50 }, [rp("2026-10-16", 3), rp("2026-10-15", 3), rp("2026-10-14", 3)], { days: days([10, 15, 25, 0]) }),
    "連投 3 天・50 球・3.0 局");
});

test("連投摘要：c_at_least 寫 3+ 天、球數限近 3 日", () => {
  assert.equal(sp({ C: 3, S3: 50 }, [rp("2026-10-16", 3), rp("2026-10-15", 3), rp("2026-10-14", 3)],
    { days: days([10, 15, 25, 0]), c_at_least: true }), "連投 3+ 天・近 3 日 50 球・3.0 局");
});

test("連投摘要：灰色（C=null）不給任何數字", () => {
  const s = sp({ C: null, S2: null, S3: null, P1: 20 }, [rp("2026-10-16", 3)], { days: days([0, 0, 20, 0], [true, false, true, true]) });
  assert.equal(s, "連投 ?");
  assert.doesNotMatch(s, /\d/);
});

test("連投局數 fail-closed：今日登板擠掉 D−3（recent 只有 3 筆）", () => {
  const p = pitcher("1", "終結", load("medium", { metrics: { P0: 8, P1: 10, S2: 20, S3: 30, C: 3, Q: 1 },
    days: days([10, 10, 10, 8]) }));
  p.recent = [rp("2026-10-17", 1), rp("2026-10-16", 3), rp("2026-10-15", 3)];
  const s = streakOf(p);
  assert.equal(streakText(s), "連投 3 天・30 球・? 局");
  assert.ok(s.kind === "streak" && !s.innings.known && /最近登板清單只含 3 筆/.test(s.innings.reason));
  assert.match(tips(watch([team("ACN011", [p])])), /連投局數 無法判定：最近登板清單只含 3 筆/);
});

test("連投局數：雙重賽兩筆都在才加總，缺一筆即未知", () => {
  const two = days([0, 10, 25, 0]);
  two[2].appearances = 2; // D−1 雙重賽
  assert.equal(sp({ C: 2, S2: 35 }, [rp("2026-10-16", 3), rp("2026-10-16", 2), rp("2026-10-15", 3)], { days: two }),
    "連投 2 天・35 球・2.2 局");
  const three = days([10, 10, 25, 0]);
  three[2].appearances = 2;
  assert.equal(sp({ C: 3, S3: 45 }, [rp("2026-10-16", 3), rp("2026-10-16", 2), rp("2026-10-15", 3)], { days: three }),
    "連投 3 天・45 球・? 局");
  // 今日也是雙重賽：recent 3 筆＝今日 2＋D−1 1，D−1 只涵蓋 1／2 筆 ⇒ 未知（⛔ 只加總看得到的那筆）。
  const partial = days([0, 0, 25, 9]);
  partial[2].appearances = 2;
  partial[3].appearances = 2;
  assert.equal(sp({ C: 1, P1: 25, Q: 2 }, [rp("2026-10-17", 1), rp("2026-10-17", 1), rp("2026-10-16", 3)], { days: partial }),
    "連投 1 天・25 球・? 局");
});

test("連投局數：outs=null 不當 0", () => {
  assert.equal(sp({ C: 2, S2: 35 }, [rp("2026-10-16", null), rp("2026-10-15", 3)], { days: days([0, 15, 20, 0]) }),
    "連投 2 天・35 球・? 局");
});

test("連投局數：保留賽（date_trusted=false）不算進該日", () => {
  assert.equal(sp({ C: 1, P1: 20 }, [rp("2026-10-16", 3, false)], { days: days([0, 0, 20, 0]) }), "連投 1 天・20 球・? 局");
});
