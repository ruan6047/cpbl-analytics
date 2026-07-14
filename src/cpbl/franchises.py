"""CPBL 歷史營運隊碼到 canonical franchise 的唯一後端映射。"""

from __future__ import annotations

FRANCHISE_MAP = {
    "ACC011": "ACN011",  # 兄弟象 → 中信兄弟
    "AEE011": "AEO011",  # 俊國熊 → 興農牛 → 義大犀牛 → 富邦悍將
    "AEG011": "AEO011",
    "AEM011": "AEO011",
    "AJJ011": "AJL011",  # 第一金剛 → La New／Lamigo → 樂天桃猿
    "AJK011": "AJL011",
    "AIL011": "AII011",  # 誠泰 Cobras → 米迪亞暴龍（2008 解散）
}


def franchise_of(team_code: str) -> str:
    return FRANCHISE_MAP.get(team_code, team_code)


def franchise_prefixes(team_code: str) -> set[str]:
    """回傳同一 franchise 的所有三碼歷史隊碼，供跨年度資料篩選。"""
    prefix = team_code[:3]
    canonical = franchise_of(team_code)[:3]
    if canonical == prefix:
        canonical = franchise_of(f"{prefix}011")[:3]
    known_codes = set(FRANCHISE_MAP) | set(FRANCHISE_MAP.values()) | {team_code}
    return {
        code[:3]
        for code in known_codes
        if franchise_of(code)[:3] == canonical
    }
