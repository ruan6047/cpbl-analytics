"""PRD「名單解析與不可變提交 → 輸入格式」的純函式解析器（無 DB、無 I/O）。

格式（範例見 docs/design/PLAYOFFS_PRD_V2.md）::

    @year 2026
    @series C            # 只收 E／C
    @team ACN011         # team_dim 代碼
    @source https://…    # 官方公告網址
    @published 2026-10-16

    [投手]
    球員甲 #輪值、球員乙
    同名球員 @id=0000000001 #終結

規則（PRD 原文）：同組可換行、頓號、逗號分隔，容首尾空白與空行；以實際分隔符切名字，
⛔ 不依字數拆姓名。`@id=` 與 `#角色` 屬於緊鄰的單一姓名；黏連到多人而無法確定歸屬、
一人多個 `#`、未知命令／角色／守位一律回行號與原文片段，⛔ 不猜。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from cpbl.rosters.canonical import POSITIONS, ROLES, UNCLASSIFIED, norm, role_compatible

HEADERS = ("year", "series", "team", "source", "published")
SERIES = ("E", "C")
# 同組分隔符：頓號、半形／全形逗號（換行另行處理）。
_SEPARATORS = re.compile(r"[、,，]")
_MARKER = re.compile(r"@id=[^\s#@]*|#[^\s#@]*")
_PID = re.compile(r"^[0-9]{10}$")
_GROUP = re.compile(r"^\[(.*)\]$")
_HEADER = re.compile(r"^@([A-Za-z_]+)(?:\s+(.*))?$")


@dataclass(frozen=True)
class Issue:
    line: int
    snippet: str
    message: str

    def __str__(self) -> str:
        return f"第 {self.line} 行「{self.snippet}」：{self.message}"


class ParseError(ValueError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))


@dataclass(frozen=True)
class Entry:
    line: int
    position: str
    name: str
    explicit_id: str | None
    role: str | None  # None＝未標（unclassified）


@dataclass(frozen=True)
class ParsedRoster:
    year: int
    kind_code: str
    team_code: str
    source_url: str
    published_date: date
    entries: tuple[Entry, ...]
    raw_text: str = field(repr=False)


def _parse_entry(token: str, line: int, position: str, issues: list[Issue]) -> Entry | None:
    markers = list(_MARKER.finditer(token))
    # 名字片段＝去掉標記後依空白切開；標記若夾在兩段名字之間＝黏連到多人。
    pieces = _MARKER.split(token)
    words = [w for piece in pieces for w in piece.split()]
    if not words:
        issues.append(Issue(line, token, "標記沒有緊鄰的姓名"))
        return None
    if len(words) > 1:
        issues.append(Issue(line, token, "多個姓名黏連在同一段（缺分隔符）；標記無法確定歸屬"))
        return None
    ids = [m.group(0)[4:] for m in markers if m.group(0).startswith("@id=")]
    roles = [m.group(0)[1:] for m in markers if m.group(0).startswith("#")]
    ok = True
    if len(ids) > 1:
        issues.append(Issue(line, token, "同一姓名有多個 @id"))
        ok = False
    if len(roles) > 1:
        issues.append(Issue(line, token, "同一姓名有多個 #角色（每人最多一個戰術角色）"))
        ok = False
    explicit_id = ids[0] if ids else None
    if explicit_id is not None and not _PID.match(explicit_id):
        issues.append(Issue(line, token, f"@id 必須是 10 碼數字：{explicit_id!r}"))
        ok = False
    role = roles[0] if roles else None
    if role is not None:
        if role == UNCLASSIFIED or role not in ROLES:
            issues.append(Issue(line, token, f"未知角色 #{role}"))
            ok = False
        elif not role_compatible(position, role):
            issues.append(Issue(line, token, f"角色 #{role} 與官方守位 {position} 不相容"))
            ok = False
    if not ok:
        return None
    return Entry(line=line, position=position, name=norm(words[0]),
                 explicit_id=explicit_id, role=role)


def parse(text: str) -> ParsedRoster:
    """解析整份文字快照；任何問題一律收齊後丟 ParseError（不寫 DB、不猜）。"""
    issues: list[Issue] = []
    headers: dict[str, str] = {}
    header_line: dict[str, int] = {}
    entries: list[Entry] = []
    position: str | None = None
    normalized = unicodedata.normalize("NFC", text)
    for lineno, raw in enumerate(normalized.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        group = _GROUP.match(line)
        if group:
            name = group.group(1).strip()
            if name not in POSITIONS:
                issues.append(Issue(lineno, line, f"未知守位分組 [{name}]（只收 {'／'.join(POSITIONS)}）"))
                position = None
                continue
            position = name
            continue
        header = _HEADER.match(line)
        if header and not line.startswith("@id="):
            key, value = header.group(1), (header.group(2) or "").strip()
            if key not in HEADERS:
                issues.append(Issue(lineno, line, f"未知命令 @{key}"))
            elif entries or position is not None:
                issues.append(Issue(lineno, line, f"@{key} 必須寫在任何守位分組之前"))
            elif key in headers:
                issues.append(Issue(lineno, line, f"@{key} 重複"))
            elif not value:
                issues.append(Issue(lineno, line, f"@{key} 缺值"))
            else:
                headers[key] = value
                header_line[key] = lineno
            continue
        if position is None:
            issues.append(Issue(lineno, line, "姓名必須寫在 [投手]／[捕手]／[內野手]／[外野手] 分組之下"))
            continue
        for token in _SEPARATORS.split(line):
            token = token.strip()
            if not token:
                issues.append(Issue(lineno, line, "分隔符之間沒有姓名"))
                continue
            entry = _parse_entry(token, lineno, position, issues)
            if entry is not None:
                entries.append(entry)

    for key in HEADERS:
        if key not in headers:
            issues.append(Issue(0, "（整份）", f"缺必填標頭 @{key}"))
    year = kind = team = source = None
    published: date | None = None

    def bad(key: str, message: str) -> None:
        issues.append(Issue(header_line.get(key, 0), f"@{key} {headers[key]}", message))

    if "year" in headers:
        if re.fullmatch(r"[0-9]{4}", headers["year"]):
            year = int(headers["year"])
        else:
            bad("year", "@year 必須是 4 位數年份")
    if "series" in headers:
        kind = headers["series"].upper()
        if kind not in SERIES:
            bad("series", f"@series 只收 {'／'.join(SERIES)}")
    if "team" in headers:
        team = headers["team"]
        if not re.fullmatch(r"[A-Z0-9]+", team):
            bad("team", "@team 必須是隊伍代碼（如 ACN011）")
    if "source" in headers:
        source = headers["source"]
        if not re.match(r"^https?://\S+$", source):
            bad("source", "@source 必須是單一 http(s) 官方公告網址")
    if "published" in headers:
        try:
            published = date.fromisoformat(headers["published"])
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", headers["published"]):
                raise ValueError
        except ValueError:
            bad("published", "@published 必須是 YYYY-MM-DD")
    if issues:
        raise ParseError(issues)
    return ParsedRoster(year=year, kind_code=kind, team_code=team, source_url=source,
                        published_date=published, entries=tuple(entries), raw_text=text)


def render(year: int, kind_code: str, team_code: str, source_url: str, published_date: str,
           members: list[tuple[str, str, str]], roles: dict[str, str] | None = None) -> str:
    """把已核記錄渲染成 PRD 輸入格式；members＝(official_position, 公告姓名, player_id)。

    每人一律帶 `@id=`（已核身份，不靠姓名解析）；用於 official_population 遷入。
    """
    roles = roles or {}
    lines = [f"@year {year}", f"@series {kind_code}", f"@team {team_code}",
             f"@source {source_url}", f"@published {published_date}"]
    for pos in POSITIONS:
        group = [m for m in members if m[0] == pos]
        if not group:
            continue
        lines.append("")
        lines.append(f"[{pos}]")
        for _, name, pid in group:
            role = roles.get(pid)
            lines.append(f"{name} @id={pid}" + (f" #{role}" if role and role != UNCLASSIFIED else ""))
    return "\n".join(lines) + "\n"
