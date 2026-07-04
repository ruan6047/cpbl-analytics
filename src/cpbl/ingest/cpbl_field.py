"""官網 /field 球場介紹爬蟲：規格（座位/外野距離/草皮/大螢幕）enrich venue_dim。

結構：/field 索引頁列出各球場連結 /field/cont?SId=…；內頁 stadium_spec 區為
`<div class="label">欄名</div><div class="desc">值</div>` 對（電話/地址同型態）。
距離數字為官方頁原始值（大巨蛋 335/335/400 實測為呎）。

只更新能對到 venue_dim 的球場（NAME_MAP 顯式對照；對不到者 log 略過——多為
歷史/業餘球場，venue PK 須與 games.venue 官網簡稱一致，不宜猜測新增）。

一次性爬 + 手動刷新（不掛 cron）：uv run cpbl-scrape-field
"""

from __future__ import annotations

import logging
import re
import time

from cpbl.db import conn

log = logging.getLogger("cpbl.field")

INDEX_PATH = "/field"

# /field 內頁標題 → venue（PK＝games.venue 官網簡稱；以 games 實資料 28 種值域人工核定）。
# 不在 venue_dim 的列會新增（歷史/二軍場地）；games 另有 台中/桃園(舊名)/亞太副場(變體)/
# 場地未定 等值不在 /field 索引，維持無規格。
NAME_MAP = {
    "台北大巨蛋": "大巨蛋",
    "台北市天母棒球場": "天母",
    "台北市立棒球場": "台北市",
    "新北市立新莊棒球場": "新莊",
    "樂天桃園棒球場": "樂天桃園",
    "桃園龍潭棒球場": "龍潭",
    "青埔運動公園棒球場": "青埔",
    "新竹市中正棒球場": "新竹",
    "台中市洲際棒球場": "洲際",
    "台灣國立體育棒球場": "國體",
    "雲林縣棒球場": "斗六",
    "嘉義市立體育棒球場": "嘉義市",
    "嘉義縣棒球場": "嘉義縣",
    "台南市立體育棒球場": "台南",
    "台南亞太成棒主球場": "亞太主",
    "台南亞太成棒副球場": "亞太副",
    "高雄市澄清湖棒球場": "澄清湖",
    "高雄市立德棒球場": "立德",
    "屏東縣立體育棒球場": "屏東",
    "中國信託公益園區棒球場": "園區",
    "宜蘭縣羅東運動公園棒球場": "羅東",
    "花蓮縣棒球場": "花蓮",
    "台東縣棒球場": "台東",
    "皇鷹學院": "皇鷹學院",
}

_LINK_RE = re.compile(r'href="/field/cont\?[Ss][Ii]d=([0-9A-Za-z]+)"[^>]*>([^<]+)<')
_PAIR_RE = re.compile(r'<div class="label">([^<]+)</div>\s*<div class="desc">(.*?)</div>', re.S)


def _i(v: str) -> int | None:
    m = re.search(r"\d[\d,]*", v or "")
    return int(m.group(0).replace(",", "")) if m else None


def parse_index(html: str) -> dict[str, str]:
    """索引頁 → {球場名: SId}（同名 SId/sid 重複連結去重）。"""
    out: dict[str, str] = {}
    for sid, name in _LINK_RE.findall(html):
        name = name.strip()
        if name and name != "球場介紹":
            out.setdefault(name, sid)
    return out


def _fix_cf(lf: int | None, cf: int | None, rf: int | None) -> tuple:
    """官網偶有左中右填反（實例：亞太主 325/325/400）。中外野必為最深，
    三值齊全且 cf 非最大時，把最大值挪給 cf、其餘依序左右。"""
    if None in (lf, cf, rf) or cf == max(lf, cf, rf):
        return lf, cf, rf
    vals = sorted([lf, cf, rf])
    log.warning("外野距離疑填反（L/C/R=%s/%s/%s）→ 修正為 %s/%s/%s",
                lf, cf, rf, vals[0], vals[2], vals[1])
    return vals[0], vals[2], vals[1]


def parse_specs(html: str) -> dict:
    """內頁 label/desc 對 → 正規化欄位 dict。"""
    raw = {label.strip(): re.sub(r"<[^>]+>", "", val).strip()
           for label, val in _PAIR_RE.findall(html)}
    lf, cf, rf = _fix_cf(_i(raw.get("左外野", "")), _i(raw.get("中外野", "")),
                         _i(raw.get("右外野", "")))
    return {
        "phone": raw.get("電話") or None,
        "address": raw.get("地址") or None,
        "capacity": _i(raw.get("觀眾數", "")),
        "infield_seats": _i(raw.get("內野數", "")),
        "outfield_seats": _i(raw.get("外野數", "")),
        "lf_dist": lf,
        "rf_dist": rf,
        "cf_dist": cf,
        "big_screen": {"有": True, "無": False}.get(raw.get("大螢幕")),
        # 內野草皮（人工草皮/天然草皮）與 venue_dim.turf 語意重疊，僅用於覆核不覆寫
        "_turf_raw": raw.get("內野"),
    }


def upsert_venue_specs(venue: str, sid: str, name: str, specs: dict) -> None:
    """有列則補規格（既有 seed 欄位如 turf/city 不動），無列則新增（歷史/二軍場地）。"""
    with conn() as c:
        c.execute(
            """
            INSERT INTO cpbl.venue_dim (venue, full_name, phone, address, capacity,
                infield_seats, outfield_seats, lf_dist, rf_dist, cf_dist, big_screen, field_sid)
            VALUES (%(venue)s, %(name)s, %(phone)s, %(address)s, %(capacity)s,
                %(infield_seats)s, %(outfield_seats)s, %(lf_dist)s, %(rf_dist)s, %(cf_dist)s,
                %(big_screen)s, %(sid)s)
            ON CONFLICT (venue) DO UPDATE SET
                phone = COALESCE(EXCLUDED.phone, venue_dim.phone),
                address = COALESCE(EXCLUDED.address, venue_dim.address),
                capacity = COALESCE(EXCLUDED.capacity, venue_dim.capacity),
                infield_seats = COALESCE(EXCLUDED.infield_seats, venue_dim.infield_seats),
                outfield_seats = COALESCE(EXCLUDED.outfield_seats, venue_dim.outfield_seats),
                lf_dist = COALESCE(EXCLUDED.lf_dist, venue_dim.lf_dist),
                rf_dist = COALESCE(EXCLUDED.rf_dist, venue_dim.rf_dist),
                cf_dist = COALESCE(EXCLUDED.cf_dist, venue_dim.cf_dist),
                big_screen = COALESCE(EXCLUDED.big_screen, venue_dim.big_screen),
                field_sid = EXCLUDED.field_sid
            """,
            {**{k: v for k, v in specs.items() if not k.startswith("_")},
             "sid": sid, "venue": venue, "name": name},
        )


def scrape(delay: float = 1.0, only: list[str] | None = None) -> dict:
    """爬索引 + 各球場內頁。only=球場名清單（小量驗證用）；None=全部可對照者。"""
    from cpbl.ingest._browser import session
    s = session()
    index = parse_index(s.page_html(INDEX_PATH, require="/field/cont"))
    log.info("索引頁球場 %d 座；可對照 venue_dim %d 座", len(index),
             sum(1 for n in index if n in NAME_MAP))
    done, skipped = 0, []
    for name, sid in index.items():
        venue = NAME_MAP.get(name)
        if venue is None:
            skipped.append(name)
            continue
        if only is not None and name not in only and venue not in only:
            continue
        time.sleep(delay)
        specs = parse_specs(s.page_html(f"/field/cont?SId={sid}", require="stadium_spec"))
        upsert_venue_specs(venue, sid, name, specs)
        log.info("%s → %s：容量=%s 內/外野席=%s/%s 距離 L/C/R=%s/%s/%s 草皮=%s",
                 name, venue, specs["capacity"], specs["infield_seats"], specs["outfield_seats"],
                 specs["lf_dist"], specs["cf_dist"], specs["rf_dist"], specs["_turf_raw"])
        done += 1
    if skipped:
        log.info("無對照略過 %d 座：%s", len(skipped), "、".join(skipped))
    return {"updated": done, "skipped": len(skipped)}
