"""#350 規劃示意 mockup 產生器（可拋棄；不是產品碼）。

讀正式站 /api/v1/playoffs/roster?season=2026&series=C 的唯讀快照，輸出 A/B 兩個靜態 HTML。
用法：python3 -I gen_mockups.py <snapshot.json> <out_dir>
"""
import html
import json
import sys
from collections import Counter

snap, out = sys.argv[1], sys.argv[2]
d = json.load(open(snap))
teams = d["teams"]

PIT_ORDER = ["先發", "長中繼", "中繼", "勝利組", "拆彈組", "終結"]
BAT_ORDER = ["主力", "指定打擊", "工具人", "守備替補", "代打", "代跑", "替補"]
POS = ["投手", "捕手", "內野手", "外野手"]
POS_SHORT = {"捕手": "捕", "內野手": "內", "外野手": "外", "投手": "投"}


def roles(m):
    if m.get("role_format_version") == 2:
        return m["tactical_roles"]
    r = m.get("tactical_role")
    return [r] if r and r != "unclassified" else []


def g(m):
    return m["background"]["g"]


def line(m):
    l = m["background"]["line"]
    if not l:
        return "—"
    if m["role"] == "pitching":
        return f"ERA {l['era']:.2f} · {l['ip']} IP" if l["era"] is not None else f"ERA — · {l['ip']} IP"
    def r3(v):
        return "—" if v is None else f"{v:.3f}".lstrip("0")
    return f"AVG {r3(l['avg'])} · OPS {r3(l['ops'])}"


def by_g(ms):
    return sorted(ms, key=lambda m: (-(g(m) if g(m) is not None else -1), m["player_id"]))


def role_rows(group_role, order):
    present = []
    for t in teams:
        for m in t["members"]:
            if m["role"] != group_role:
                continue
            for r in roles(m):
                if r not in present:
                    present.append(r)
    known = [r for r in order if r in present]
    return known + [r for r in present if r not in order]


def esc(s):
    return html.escape(str(s))


def logo(code, size=22):
    return (f'<img class="logo" src="../../../../web/public/team-icons/refined-{code}.svg" '
            f'width="{size}" height="{size}" alt="" aria-hidden="true">')


CSS = """
:root{--paper:#ece8e0;--surface:#f7f5f0;--surface-2:#efebe3;--band:#e4dfd5;--line:rgba(30,40,48,.14);
--ink:#1e2830;--muted:#4f5961;--faint:#5d6770;--accent:#1e6c8c;--up:#1d5fb0;--down:#c21f32}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"Noto Sans TC","PingFang TC",system-ui,sans-serif;
font-variant-numeric:tabular-nums;font-size:14px}
.wrap{max-width:1152px;margin:0 auto;padding:16px}
.note{font-size:12px;color:var(--muted);margin:0 0 10px}
.card{background:var(--surface);border-radius:4px}
.panel{background:var(--surface);border-radius:4px;padding:16px}
h2{font-size:14px;font-weight:700;margin:0;display:flex;gap:6px;align-items:center}
.info{display:inline-grid;place-items:center;width:16px;height:16px;border:1px solid var(--line);border-radius:50%;
font-size:10px;color:var(--muted)}
.seg{display:inline-flex;background:var(--band);border-radius:4px;padding:2px;gap:0;height:32px;align-items:center;max-width:100%;overflow-x:auto}
.seg b,.seg span{padding:4px 10px;font-size:12px;border-radius:3px;white-space:nowrap}
.seg b{background:var(--ink);color:var(--paper)}
.seg span{color:var(--muted)}
.mono{font-family:Archivo,ui-monospace,monospace}
.muted{color:var(--muted)}.faint{color:var(--faint)}
.logo{vertical-align:middle}
.mk-AAA011{color:#c8102e}.mk-ACN011{color:#7d5c14}
.tag{display:inline-block;border-radius:3px;font-size:11px;color:var(--muted);background:var(--surface-2);padding:1px 6px;white-space:nowrap}
details>summary{cursor:pointer;font-size:13px;font-weight:700;padding:10px 12px;background:var(--surface-2);border-radius:4px;list-style:none}
details>summary::before{content:"▸ ";color:var(--muted)}
"""

# ───────────────────────── 方案 A：陣容對照表 ─────────────────────────
A_CSS = CSS + """
.vs{display:grid;grid-template-columns:96px 1fr 1fr;gap:0}
.vs>.h{padding:8px 10px;font-weight:700;display:flex;align-items:center;gap:6px;border-bottom:2px solid var(--ink)}
.vs>.rl{padding:8px 10px;font-size:12px;font-weight:700;color:var(--muted);border-top:1px solid var(--line)}
.vs>.c{padding:6px 10px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:4px 6px;align-content:flex-start}
.vs>.c:nth-of-type(odd){}
.vs .sec{grid-column:1/-1;padding:14px 10px 6px;font-size:13px;font-weight:700;display:flex;gap:10px;align-items:baseline}
.cnt{font-family:Archivo,ui-monospace,monospace;font-weight:700;font-size:13px;color:var(--ink);margin-right:2px;min-width:16px}
.chip{display:inline-flex;align-items:baseline;gap:4px;padding:3px 7px;border-radius:3px;background:var(--surface-2);
font-size:13px;line-height:1.35;white-space:nowrap;cursor:pointer}
.chip:hover{background:var(--band)}
.chip .gg{font-size:11px;color:var(--muted);font-family:Archivo,ui-monospace,monospace}
.chip .ps{font-size:11px;color:var(--faint)}
.comp{display:grid;grid-template-columns:96px 1fr 1fr}
.comp>div{padding:6px 10px}
.comp .k{font-size:12px;color:var(--muted);font-weight:700}
.bar{display:flex;height:22px;border-radius:3px;overflow:hidden;font-size:11px;font-weight:700}
.bar>i{font-style:normal;display:flex;align-items:center;justify-content:center;color:var(--paper);white-space:nowrap}
.bar .p{background:#1e2830}.bar .c{background:#4f5961}.bar .i{background:#7c858c}.bar .o{background:#a3aab0;color:var(--ink)}
.legend{font-size:11px;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:3px;vertical-align:-1px}
@media (max-width:639px){
 .vs{grid-template-columns:1fr 1fr}
 .vs>.h:first-child{display:none}
 .vs>.rl{grid-column:1/-1;padding:8px 4px 2px;border-top:1px solid var(--line)}
 .vs>.c{border-top:none;padding:2px 4px 8px}
 .vs .sec{padding:14px 4px 4px}
 .comp{grid-template-columns:1fr 1fr}
 .comp .k{display:none}
 .chip{font-size:12.5px;padding:3px 6px}
 .wrap{padding:16px}
 .panel{padding:12px}
 .bar,.legend{display:none}
 .comp .comptxt{display:block}
}
.comptxt{display:none;font-size:12px;color:var(--muted)}
.comptxt b{color:var(--ink);font-family:Archivo,ui-monospace,monospace}
"""


def team_head(t, extra_cls="h"):
    return f'<div class="{extra_cls}">{logo(t["team_code"])}<span>{esc(t["team_name"])}</span></div>'


def comp_bar(t):
    c = Counter(m["official_position"] for m in t["members"])
    segs = [("p", "投手"), ("c", "捕手"), ("i", "內野手"), ("o", "外野手")]
    total = sum(c.values())
    inner = "".join(
        f'<i class="{k}" style="width:{c[p] / total * 100:.2f}%" title="{p} {c[p]}">{POS_SHORT[p]} {c[p]}</i>'
        for k, p in segs if c[p])
    txt = " · ".join(f"{POS_SHORT[p]} <b>{c[p]}</b>" for _, p in segs)
    return f'<div class="comptxt">{logo(t["team_code"], 16)} {txt}</div><div class="bar" role="img" aria-label="{"、".join(f"{p}{c[p]}人" for _, p in segs)}">{inner}</div>'


def chip(m, show_pos):
    ps = f'<span class="ps">{POS_SHORT.get(m["official_position"], "")}</span>' if show_pos else ""
    gv = g(m)
    return (f'<span class="chip" title="{esc(line(m))}">{esc(m["name"])}{ps}'
            f'<span class="gg">{"—" if gv is None else str(gv) + "G"}</span></span>')


def mock_a():
    t0, t1 = teams
    rows = []
    rows.append('<div class="vs" role="table" aria-label="兩隊陣容對照">')
    rows.append('<div class="h"></div>' + team_head(t0) + team_head(t1))
    # 組成列
    for grp_role, title, order, show_pos in (("pitching", "投手", PIT_ORDER, False), ("batting", "野手", BAT_ORDER, True)):
        n0 = sum(1 for m in t0["members"] if m["role"] == grp_role)
        n1 = sum(1 for m in t1["members"] if m["role"] == grp_role)
        rows.append(f'<div class="sec">{title}<span class="muted mono" style="font-weight:400">'
                    f'{esc(t0["team_name"])} {n0} · {esc(t1["team_name"])} {n1}</span></div>')
        for r in role_rows(grp_role, order):
            cells = []
            for t in (t0, t1):
                ms = by_g([m for m in t["members"] if m["role"] == grp_role and r in roles(m)])
                cells.append(f'<div class="c"><span class="cnt">{len(ms)}</span>'
                             + ("".join(chip(m, show_pos) for m in ms) or '<span class="faint">—</span>') + "</div>")
            rows.append(f'<div class="rl">{esc(r)}</div>' + "".join(cells))
    rows.append("</div>")
    comp = ('<div class="comp" aria-label="名單組成">'
            '<div class="k">組成（32 人）</div>'
            f'<div>{comp_bar(t0)}</div><div>{comp_bar(t1)}</div></div>')
    body = f"""
<div class="panel">
 <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px">
  <h2>系列賽名單 <span class="info">i</span></h2>
  <div class="seg"><b>例行賽背景</b><span>本系列實戰</span></div>
 </div>
 {comp}
 <div class="legend" style="padding:2px 10px 8px"><span><i style="background:#1e2830"></i>投手</span><span><i style="background:#4f5961"></i>捕手</span><span><i style="background:#7c858c"></i>內野手</span><span><i style="background:#a3aab0"></i>外野手</span></div>
 {''.join(rows)}
 <p class="note" style="margin:10px 10px 12px">同一人有多個角色時會出現在每一列；名字旁為出賽數（依目前資料範圍），每列依出賽數多到少。點名字看能力與走勢。</p>
 <details><summary>球員明細（成績・近 15 場・官方 PR）</summary><p class="note" style="padding:10px">（展開後＝現有小卡網格與球隊／守位篩選、排序，內容不變；示意省略）</p></details>
</div>"""
    return page("方案 A：陣容對照表", A_CSS, body)


# ───────────────────────── 方案 B：組成摘要＋並列清單 ─────────────────────────
B_CSS = CSS + """
.sum{width:100%;max-width:760px;border-collapse:collapse;font-size:13px}
.sum th,.sum td{padding:5px 8px;text-align:left}
.sum thead th{background:var(--band);font-size:12px;color:var(--muted)}
.sum td.n{font-family:Archivo,ui-monospace,monospace;font-weight:700;width:36px;text-align:right}
.sum td.b{width:40%}
.sum tr.grp td{font-weight:700;border-top:1px solid var(--line)}
.sum tr.sub td:first-child{padding-left:20px;color:var(--muted)}
.mb{height:8px;background:var(--ink);border-radius:2px}
.mb.r{margin-left:auto}
.lists{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.lt{width:100%;border-collapse:collapse;font-size:13px}
.lt th{background:var(--band);font-size:11px;color:var(--muted);text-align:left;padding:4px 6px;font-weight:600}
.lt td{padding:5px 6px;vertical-align:top}
.lt tbody tr:nth-child(even) td{background:var(--surface-2)}
.lt .nm{font-weight:700;white-space:nowrap}
.lt .g{font-family:Archivo,ui-monospace,monospace;text-align:right;white-space:nowrap}
.lt .ln{font-family:Archivo,ui-monospace,monospace;font-size:12px;color:var(--muted);white-space:nowrap}
.lt .gh td{background:transparent!important;font-size:12px;font-weight:700;color:var(--muted);padding-top:10px}
.mobile-only{display:none}
@media (max-width:639px){
 .lists{grid-template-columns:1fr}
 .lists>section:nth-child(2){display:none}
 .mobile-only{display:inline-flex}
 .lt .ln{display:none}
 .sum td.b{width:28%}
 .wrap{padding:16px}.panel{padding:12px}
}
"""


def mock_b():
    t0, t1 = teams
    mx = max(sum(1 for m in t['members'] if m['role'] == gr) for t in teams for gr in ('pitching', 'batting'))
    def r(label, n0, n1, cls=""):
        def w(n):
            return f"{n / mx * 100:.1f}%"
        return (f'<tr class="{cls}"><td>{esc(label)}</td>'
                f'<td class="b"><div class="mb r" style="width:{w(n0)}"></div></td><td class="n">{n0}</td>'
                f'<td class="n" style="text-align:left">{n1}</td><td class="b"><div class="mb" style="width:{w(n1)}"></div></td></tr>')
    trs = []
    for grp_role, title, order in (("pitching", "投手", PIT_ORDER), ("batting", "野手", BAT_ORDER)):
        c0 = [m for m in t0["members"] if m["role"] == grp_role]
        c1 = [m for m in t1["members"] if m["role"] == grp_role]
        trs.append(r(title, len(c0), len(c1), "grp"))
        if grp_role == "batting":
            for p in POS[1:]:
                trs.append(r(p, sum(m["official_position"] == p for m in c0), sum(m["official_position"] == p for m in c1), "sub"))
        for rr in role_rows(grp_role, order):
            trs.append(r(rr, sum(rr in roles(m) for m in c0), sum(rr in roles(m) for m in c1), "sub"))
    summary = (f'<table class="sum" aria-label="陣容組成對照"><thead><tr><th></th>'
               f'<th colspan="2" style="text-align:right">{logo(t0["team_code"], 18)} {esc(t0["team_name"])}</th>'
               f'<th colspan="2">{esc(t1["team_name"])} {logo(t1["team_code"], 18)}</th></tr></thead>'
               f'<tbody>{"".join(trs)}</tbody></table>')

    def lst(t):
        out = [f'<section><h3 style="font-size:14px;margin:0 0 6px;display:flex;gap:6px;align-items:center">'
               f'{logo(t["team_code"])}{esc(t["team_name"])}</h3><table class="lt"><thead><tr>'
               '<th>球員</th><th>角色</th><th style="text-align:right">出賽</th><th class="ln">成績</th></tr></thead><tbody>']
        for p in POS:
            ms = by_g([m for m in t["members"] if m["official_position"] == p])
            out.append(f'<tr class="gh"><td colspan="4">{p} {len(ms)}</td></tr>')
            for m in ms:
                out.append(f'<tr><td class="nm">{esc(m["name"])}</td>'
                           f'<td>{" ".join(f"<span class=tag>{esc(x)}</span>" for x in roles(m))}</td>'
                           f'<td class="g">{"—" if g(m) is None else str(g(m)) + "G"}</td><td class="ln">{esc(line(m))}</td></tr>')
        out.append("</tbody></table></section>")
        return "".join(out)

    body = f"""
<div class="panel">
 <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px">
  <h2>系列賽名單 <span class="info">i</span></h2>
  <div class="seg"><b>例行賽背景</b><span>本系列實戰</span></div>
 </div>
 <h3 style="font-size:13px;margin:0 0 6px">陣容組成</h3>
 {summary}
 <p class="note" style="margin:6px 0 16px">角色可重複計：一人有兩個角色時兩列都算。</p>
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
  <h3 style="font-size:13px;margin:0">名單</h3>
  <div class="seg mobile-only"><b>{esc(t0["team_name"])}</b><span>{esc(t1["team_name"])}</span></div>
 </div>
 <div class="lists">{lst(t0)}{lst(t1)}</div>
</div>"""
    return page("方案 B：組成摘要＋並列清單", B_CSS, body)


def page(title, css, body):
    asof = d["as_of"]
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css}</style></head>
<body><div class="wrap"><p class="note">#350 規劃示意（靜態 mockup，非產品碼）｜{esc(title)}｜資料：正式站 /api/v1/playoffs/roster?season=2026&amp;series=C 唯讀快照，last_refresh_at {esc(asof["last_refresh_at"])}；例行賽背景範圍</p>
{body}</div></body></html>"""


open(f"{out}/mockup-a.html", "w").write(mock_a())
open(f"{out}/mockup-b.html", "w").write(mock_b())
print("ok")
