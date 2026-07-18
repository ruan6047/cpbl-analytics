"""API 共用工具：預設球季、層級 kind 群組、cursor→dict、四捨五入、特徵字串解析、局數記法換算。"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

DEFAULT_SEASON = _date.today().year

# 層級 → 該層級包含的所有 kind_code（含季後賽）：
# 一軍 A ＋ 季後挑戰賽 E ＋ 台灣大賽 C；二軍 D ＋ 二軍季後 F。季後賽併入同層顯示。
KIND_GROUPS = {"A": ("A", "E", "C"), "D": ("D", "F")}


def kinds_of(kind_code: str) -> list[str]:
    """層級代碼 → 要查的 kind_code 清單；未知代碼原樣查（不猜測）。"""
    return list(KIND_GROUPS.get(kind_code, (kind_code,)))


def _batted_result(content: str | None) -> str:
    """從逐球 content 文字判斷擊球結果：hr/3b/2b/1b/out。
    content 在 DB 為雙重編碼（UTF-8 bytes 被當 latin-1 存），讀取時先還原。
    （tracking 與 games 兩 router 共用；勿在前端重寫分類，保持單一事實來源。）"""
    try:
        c = (content or "").encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        c = content or ""
    if "全壘打" in c:
        return "hr"
    if "三壘安打" in c:
        return "3b"
    if "二壘安打" in c:
        return "2b"
    if "一壘安打" in c or "內野安打" in c:
        return "1b"
    return "out"


def _ip_real(ip: float | None) -> float | None:
    """.1/.2 局數記法 → 真實局數（如 180.2 → 180⅔）。"""
    if ip is None:
        return None
    ip = float(ip)
    whole = int(ip)
    return whole + round((ip - whole) * 10) / 3.0


def _real_ip(ip: Any) -> float:
    """同 _ip_real，但 None → 0.0（加總用）。"""
    return _ip_real(ip) or 0.0


def _parse_features(features: str) -> list[str]:
    return [f.strip() for f in features.split(",") if f.strip()]
def _ip_disp(real: float | None) -> float | None:
    """真實局數 → .1/.2 棒球記法顯示（如 180⅔ → 180.2）。"""
    if real is None:
        return None
    real = float(real)
    whole = int(real + 1e-9)
    outs = round((real - whole) * 3)
    if outs >= 3:
        whole, outs = whole + 1, 0
    return round(whole + outs / 10, 1)
def _dicts(cur) -> list[dict]:
    """cursor → list[dict]，欄名取自 cursor.description；real 已是 float。"""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
def _round(x: float | None, n: int) -> float | None:
    return round(x, n) if x is not None else None
