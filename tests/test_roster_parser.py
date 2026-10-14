"""#284 名單解析與雜湊（純函式；E01、E03、E14）。樣本＝official_population 2026 E 真實 64 人。"""

from __future__ import annotations

import pytest

from cpbl.ingest.run_roster import _official_text
from cpbl.rosters.canonical import membership_hash, revision_hash, source_hash
from cpbl.rosters.parser import ParseError, parse, render


def real_text(team: str) -> str:
    return _official_text(2026, "E", team)[0]


def members_of(text: str):
    p = parse(text)
    return p, [(e.position, e.explicit_id) for e in p.entries]


@pytest.mark.parametrize("team", ["ACN011", "ADD011"])
def test_e01_real_rendered_text_parses_to_32(team):
    p, members = members_of(real_text(team))
    assert (p.year, p.kind_code, p.team_code) == (2026, "E", team)
    assert p.source_url.startswith("https://www.cpbl.com.tw/")
    assert p.published_date.isoformat() == "2026-10-08"
    assert len(p.entries) == 32 and all(e.explicit_id for e in p.entries)
    assert all(e.role is None for e in p.entries)


def _variant_separators(text: str) -> str:
    """同組改用頓號／逗號／全形逗號串成一行，加空行與首尾空白。"""
    out, group = [], []
    for line in text.splitlines():
        if line.startswith("[") or line.startswith("@") or not line.strip():
            if group:
                seps = ["、", ",", "，"]
                out.append("  " + "".join(g + seps[i % 3] for i, g in enumerate(group[:-1])) + group[-1] + "  ")
                group = []
            out.append(line)
            out.append("")
        else:
            group.append(line)
    if group:
        out.append("、".join(group))
    return "\n".join(out)


@pytest.mark.parametrize("team", ["ACN011", "ADD011"])
def test_e01_separator_whitespace_variants_same_entries_and_hash(team):
    base = parse(real_text(team))
    var = parse(_variant_separators(real_text(team)))
    key = lambda p: sorted((e.position, e.name, e.explicit_id) for e in p.entries)  # noqa: E731
    assert key(base) == key(var)
    h = lambda p: membership_hash(p.year, p.kind_code, p.team_code,  # noqa: E731
                                  [(e.position, e.explicit_id) for e in p.entries])
    assert h(base) == h(var)


HEAD = "@year 2026\n@series C\n@team ACN011\n@source https://example.invalid/a\n@published 2026-10-16\n"


@pytest.mark.parametrize(("body", "line", "message"), [
    ("[投手]\n甲 #先發\n", 7, "未知角色"),
    ("[教練]\n甲\n", 6, "未知守位分組"),
    ("@coach 甲\n[投手]\n甲\n", 6, "未知命令"),
    ("[投手]\n甲 乙 #輪值\n", 7, "黏連"),
    ("[投手]\n甲 #輪值 #終結\n", 7, "多個 #角色"),
    ("[投手]\n甲 #主力\n", 7, "不相容"),
    ("[外野手]\n甲 #輪值\n", 7, "不相容"),
    ("[投手]\n#輪值\n", 7, "沒有緊鄰的姓名"),
    ("[投手]\n甲 @id=12345\n", 7, "10 碼"),
    ("[投手]\n甲、、乙\n", 7, "沒有姓名"),
    ("甲\n", 6, "分組之下"),
])
def test_e03_syntax_errors_carry_line_and_snippet(body, line, message):
    with pytest.raises(ParseError) as exc:
        parse(HEAD + body)
    issue = next(i for i in exc.value.issues if message in i.message)
    assert issue.line == line
    assert issue.snippet and issue.snippet in (HEAD + body).splitlines()[line - 1]


@pytest.mark.parametrize(("head", "message"), [
    (HEAD.replace("@series C", "@series A"), "@series"),
    (HEAD.replace("@published 2026-10-16", "@published 2026/10/16"), "@published"),
    (HEAD.replace("@source https://example.invalid/a\n", ""), "缺必填標頭 @source"),
    (HEAD.replace("@source https://example.invalid/a", "@source 官網"), "@source"),
    (HEAD + "@team ADD011\n", "重複"),
])
def test_e03_header_errors(head, message):
    with pytest.raises(ParseError) as exc:
        parse(head + "[投手]\n甲\n")
    hit = [i for i in exc.value.issues if message in str(i)]
    assert hit
    if "缺必填" not in message:  # 格式錯的標頭回報它自己的行號
        assert hit[0].line >= 1


def test_e14_membership_hash_invariants():
    p = parse(real_text("ACN011"))
    m = [(e.position, e.explicit_id) for e in p.entries]
    h = membership_hash(2026, "E", "ACN011", m)
    assert h == membership_hash(2026, "E", "ACN011", list(reversed(m)))          # 列序
    assert h == membership_hash(2026, "E", "ACN011", [(f" {a} ", f"{b}　") for a, b in m])  # 空白
    swapped = list(m)
    swapped[0] = ("捕手", swapped[0][1])
    assert h != membership_hash(2026, "E", "ACN011", swapped)                     # 守位
    assert h != membership_hash(2026, "E", "ACN011", m[:-1] + [(m[-1][0], "0000000001")])  # ID
    assert h != membership_hash(2026, "C", "ACN011", m)                           # 系列


def test_e14_source_and_revision_hash_invariants():
    p = parse(real_text("ADD011"))
    ann = [(e.explicit_id, e.name) for e in p.entries]
    s = source_hash(p.source_url, "2026-10-08", "date", ann)
    assert s == source_hash(p.source_url + " ", "2026-10-08", "date", list(reversed(ann)))
    assert s != source_hash(p.source_url + "x", "2026-10-08", "date", ann)
    assert s != source_hash(p.source_url, "2026-10-09", "date", ann)
    assert s != source_hash(p.source_url, "2026-10-08", "date", [(ann[0][0], "另名")] + ann[1:])
    roles = [(pid, "unclassified") for pid, _ in ann]
    r = revision_hash(roles)
    assert r == revision_hash(list(reversed(roles)))
    assert r != revision_hash([(roles[0][0], "輪值")] + roles[1:])


def test_render_roundtrip_keeps_roles():
    p = parse(real_text("ACN011"))
    members = [(e.position, e.name, e.explicit_id) for e in p.entries]
    text = render(2026, "E", "ACN011", p.source_url, "2026-10-08", members,
                  {members[0][2]: "輪值", members[-1][2]: "主力"})
    q = parse(text)
    assert q.entries[0].role == "輪值" and q.entries[-1].role == "主力"
