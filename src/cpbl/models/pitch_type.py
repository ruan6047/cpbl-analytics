"""球種細分（離線推算）：逐投手 GMM 分群 + 規則命名 → pitch_tracking.pitch_type_pred。

背景：源頭 `auto_pitch_type` 98.5% 全標 breakingball（壞資料）；`tagged_pitch_type` 只有
二元 fastball/breakingball。本模組改用 logs API 軌跡導出的 4 維特徵
`(rel_speed, ivb_cm, hb_cm, spin_rate)`，逐投手標準化後 GMM（BIC 選 k）分群，再以
教科書規則命名叢集。完整背景/座標軸/公式/驗收見 docs/PITCH_TYPE_PLAN.md。

紅線：
- **誠實標註**：所有顯示處標「推算」（前端負責）。
- **不硬命名**：對不上規則的叢集歸「變化球」，寧粗勿錯。
- **不做 PA 眾數平滑**：一個打席內投手本就會投多種球路，強制同打席同球種是統計錯誤，
  會抹平真實配球（故意不做，與規劃初稿保留意見不同）。
- 左右手依 avg(rel_side) 符號（正=右投，已用已知左投陳冠宇/右投李振昌實證）。
"""

from __future__ import annotations

import logging

import numpy as np
from sklearn.cluster import KMeans

from cpbl.db import conn

log = logging.getLogger("cpbl.pitch_type")

MIN_N = 150   # 少於此樣本不分群，退回 tagged 二元
_K = 4        # 固定 4 群（見 _cluster）

# 整場完整才分類：一場的逐球覆蓋率(tracked/pitches) 未達門檻，該場全部球不分（pred 留 NULL）。
# 避免對「發布延遲/部分缺漏」的半套資料硬分（同投手抽樣被截斷、前端顯示到一半推算球種）。
# 2026A 實測覆蓋率呈雙峰：有設備且發布齊 ≥95%、無設備場 0%、中間僅零星部分場——0.90 乾淨切開。
_COVER_OK = 0.90    # 場級覆蓋率門檻（tracked/pitches）
_MIN_PITCHES = 50   # 太少球的場不判（避免雜訊；比照 cpbl-check-coverage）

# tagged_pitch_type 弱標籤 → 中文（fallback 用）
_TAGGED_ZH = {"fastball": "速球", "breakingball": "變化球", "offspeed": "變速"}

_FEATURES = ("rel_speed", "ivb_cm", "hb_cm", "spin_rate")


def _cluster(x: np.ndarray) -> np.ndarray:
    """逐投手標準化特徵 → KMeans 固定 4 群的叢集標籤。

    為何固定 k=4 而非自動選 k（皆經全季實測校正，見 docs/PITCH_TYPE_PLAN.md）：
    - silhouette 的全域峰常落在 k=3，把四縫線與卡特/硬滑併成一群、稀釋速球中心
      （羅戈 IVB 53→35），全季 速球↔tagged fastball 精確率僅 ~89%。
    - BIC 對 GMM 反向：大樣本單調偏好更多成分（k→6），把速球拆碎。
    - k=4 精確重現研究基準（速球 149.3/IVB53/41%），全季精確率 93.5%。多出的群會由命名
      規則映回同名（寧多分再合併，也不欠分而糊成一團）。
    KMeans n_init=10 + 固定資料排序（_load 有 ORDER BY）→ 結果可重現，無 GMM 的 init 抖動。
    """
    k = min(_K, len(x))
    if k < 2:
        return np.zeros(len(x), dtype=int)
    mu, sd = x.mean(axis=0), x.std(axis=0)
    sd[sd == 0] = 1.0
    z = (x - mu) / sd
    return KMeans(n_clusters=k, random_state=0, n_init=10).fit_predict(z)


def _name_cluster(speed: float, ivb: float, hb_norm: float, spin: float,
                  top_speed: float, is_fastest: bool, is_slowest: bool) -> str:
    """依叢集中心命名。hb_norm 已翻左右手：>0=手套側、<0=臂側。

    命名精準度優先於規劃初稿的列舉順序，修正兩處重疊（規劃 §3 未處理）：
    1. 低轉(<1600)是指叉/變速鐵證 → 提前判，免被「卡特」的 |HB| 條件攔截。
    2. 手套側橫掃(hb_norm>0 且 IVB 低)是滑球 → 必須早於「曲球(IVB<-10 且最慢)」判，
       否則 §3 羅戈 31% 群(132.3/IVB-22/HB+17)會被誤標曲球（實為滑球）。
    """
    speed_drop = top_speed - speed
    if spin < 1600:
        return "指叉/變速"                                    # 低轉招牌
    if (is_fastest or speed_drop < 5) and ivb > 25:
        return "速球"                                          # 最快群或近同速、正上飄（含硬式伸卡）
    if hb_norm > 12 and ivb < 20:
        return "滑球/橫掃"                                      # 手套側橫移為主、低上飄
    if ivb < -10 and is_slowest:
        return "曲球"                                          # 大幅下墜且最慢群（縱向為主）
    if abs(hb_norm) < 12 and 10 <= ivb <= 35:
        return "卡特/滑球"                                      # 近中性橫移、中上飄
    if speed_drop > 8 and hb_norm < 0 and ivb > 0:
        return "指叉/變速"                                      # 臂側位移的減速球
    return "變化球"                                            # 對不上→不硬命名


def _classify_pitcher(rows: list[dict]) -> dict[tuple[int, int], str]:
    """回傳 {(game_sno, pitch_cnt): pitch_type_pred}。rows 為單一投手該 year/kind 全球。"""
    # 特徵齊全者才進 GMM；其餘退回 tagged 弱標籤
    feat_rows = [r for r in rows if all(r[c] is not None for c in _FEATURES)]
    out: dict[tuple[int, int], str] = {}
    for r in rows:
        tz = _TAGGED_ZH.get(r["tagged_pitch_type"])
        if tz:
            out[(r["game_sno"], r["pitch_cnt"])] = tz  # 先鋪 fallback，下方 GMM 覆蓋

    if len(feat_rows) < MIN_N:
        return out  # 樣本不足：只用 tagged fallback

    right_handed = np.nanmean([r["rel_side"] for r in feat_rows
                               if r["rel_side"] is not None]) >= 0
    x = np.array([[r[c] for c in _FEATURES] for r in feat_rows], dtype=float)
    labels = _cluster(x)

    # 叢集中心 → 命名。hb_norm 翻左右手使 >0 恆為手套側。
    speeds = {c: float(x[labels == c, 0].mean()) for c in set(labels)}
    top_speed = max(speeds.values())
    fastest = max(speeds, key=speeds.get)
    slowest = min(speeds, key=speeds.get)
    cluster_name: dict[int, str] = {}
    for c in set(labels):
        m = x[labels == c].mean(axis=0)
        hb_norm = m[2] * (1.0 if right_handed else -1.0)
        cluster_name[c] = _name_cluster(m[0], m[1], hb_norm, m[3], top_speed,
                                        is_fastest=(c == fastest), is_slowest=(c == slowest))

    for r, lab in zip(feat_rows, labels, strict=True):
        out[(r["game_sno"], r["pitch_cnt"])] = cluster_name[lab]
    return out


def _complete_games(year: int, kind_code: str) -> set[int]:
    """TrackMan「整場完整」的 game_sno 集合＝逐球覆蓋率(tracked/pitches) ≥ _COVER_OK 的完成場。

    pitches＝該場 livelog 的好壞球數（實投球數）；tracked＝pitch_tracking 筆數。無設備場
    (tracked≈0)、發布延遲/部分缺漏場(覆蓋率不足)皆不列入 → 其球不分類、等發布齊下輪再補。
    """
    with conn() as c:
        rows = c.execute(
            """
            SELECT g.game_sno,
              (SELECT count(*) FROM cpbl.game_livelog ll
                 WHERE ll.year=g.year AND ll.kind_code=g.kind_code AND ll.game_sno=g.game_sno
                   AND (ll.is_ball OR ll.is_strike)) AS pitches,
              (SELECT count(*) FROM cpbl.pitch_tracking pt
                 WHERE pt.year=g.year AND pt.kind_code=g.kind_code AND pt.game_sno=g.game_sno) AS tracked
            FROM cpbl.games g
            WHERE g.year=%s AND g.kind_code=%s AND g.home_score + g.away_score > 0
            """,
            (year, kind_code),
        ).fetchall()
    return {sno for sno, pitches, tracked in rows
            if pitches >= _MIN_PITCHES and tracked / pitches >= _COVER_OK}


def _load(year: int, kind_code: str) -> dict[str, list[dict]]:
    cols = "game_sno,pitch_cnt,pitcher_acnt,rel_speed,ivb_cm,hb_cm,spin_rate,rel_side,tagged_pitch_type"
    by_pitcher: dict[str, list[dict]] = {}
    with conn() as c:
        for row in c.execute(
            f"SELECT {cols} FROM cpbl.pitch_tracking WHERE year=%s AND kind_code=%s "
            "ORDER BY game_sno, pitcher_acnt, pitch_cnt",  # 固定順序 → 分類可重現
            (year, kind_code),
        ).fetchall():
            d = dict(zip(cols.split(","), row, strict=True))
            for k in ("rel_speed", "ivb_cm", "hb_cm", "spin_rate", "rel_side"):
                d[k] = float(d[k]) if d[k] is not None else None
            by_pitcher.setdefault(d["pitcher_acnt"], []).append(d)
    return by_pitcher


def _write(year: int, kind_code: str, preds: list[tuple[int, str, int, str]]) -> int:
    """preds: [(game_sno, pitcher_acnt, pitch_cnt, pred)]。temp table + UPDATE FROM 一次寫回。

    join 必須含 pitcher_acnt：pitch_cnt 是逐投手每場的累計，同場兩位投手 pitch_cnt 會重疊，
    少了 pitcher_acnt 會把 A 投手的預測蓋到 B 投手（PK = year,kind,game,pitcher,pitch_cnt）。
    """
    if not preds:
        return 0
    with conn() as c:
        cur = c.cursor()
        # 先清空該 year/kind 舊值：本次未涵蓋的球不得殘留上輪標籤
        cur.execute("UPDATE cpbl.pitch_tracking SET pitch_type_pred=NULL "
                    "WHERE year=%s AND kind_code=%s AND pitch_type_pred IS NOT NULL",
                    (year, kind_code))
        cur.execute("CREATE TEMP TABLE _pp (game_sno int, pitcher_acnt text, pitch_cnt int, "
                    "pred text) ON COMMIT DROP")
        with cur.copy("COPY _pp (game_sno, pitcher_acnt, pitch_cnt, pred) FROM STDIN") as cp:
            for g, pa, pc, p in preds:
                cp.write_row((g, pa, pc, p))
        cur.execute(
            "UPDATE cpbl.pitch_tracking t SET pitch_type_pred = _pp.pred "
            "FROM _pp WHERE t.year=%s AND t.kind_code=%s AND t.game_sno=_pp.game_sno "
            "AND t.pitcher_acnt=_pp.pitcher_acnt AND t.pitch_cnt=_pp.pitch_cnt",
            (year, kind_code),
        )
        return cur.rowcount


def classify(year: int, kind_code: str = "A") -> dict:
    """逐投手分類該 year/kind 逐球，寫回 pitch_type_pred。回傳統計摘要。

    只分「整場 TrackMan 完整」的場（見 _complete_games）：覆蓋不足場的球一律不分、pred 留
    NULL，等官方發布齊下輪 classify 再補。分群/命名皆逐投手跨整季，但樣本僅取完整場。
    """
    complete = _complete_games(year, kind_code)
    by_pitcher = _load(year, kind_code)
    preds: list[tuple[int, str, int, str]] = []
    n_gmm = n_fallback = skipped = 0
    for acnt, rows in by_pitcher.items():
        crows = [r for r in rows if r["game_sno"] in complete]  # 只留完整場的球
        skipped += len(rows) - len(crows)
        if not crows:
            continue
        feat_n = sum(1 for r in crows if all(r[c] is not None for c in _FEATURES))
        result = _classify_pitcher(crows)
        if feat_n >= MIN_N:
            n_gmm += 1
        else:
            n_fallback += 1
        for (g, pc), pred in result.items():
            preds.append((g, acnt, pc, pred))
    written = _write(year, kind_code, preds)
    summary = {"pitchers": len(by_pitcher), "complete_games": len(complete),
               "gmm": n_gmm, "fallback": n_fallback, "labeled": len(preds),
               "skipped_incomplete": skipped, "written": written}
    log.info("classify %d/%s → %s", year, kind_code, summary)
    return summary
