"""#350 修訂方案 C 示意 mockup 產生器（可拋棄；不是產品碼）。

輸入全是正式站唯讀快照：
- roster-2026-C-snapshot.json   ← GET /api/v1/playoffs/roster?season=2026&series=C
- fielding-2026-A-snapshot.json ← GET /api/v1/season/fielding?season=2026&limit=1000&kind_code=A
- series-dh-starts-2026-C.json  ← derive_series_dh.py 由 GET /api/v1/games/{1,2,3}/live?season=2026&kind_code=C 算出
用法：python3 -I gen_mockup_c.py <assets_dir>
"""
import html
import json
import sys
from collections import Counter, defaultdict

D = sys.argv[1]
roster = json.load(open(f"{D}/roster-2026-C-snapshot.json"))
fld = json.load(open(f"{D}/fielding-2026-A-snapshot.json"))["items"]
sdh = json.load(open(f"{D}/series-dh-starts-2026-C.json"))["dh_starts"]
teams = roster["teams"]

FIELD_POS = ["捕手", "一壘手", "二壘手", "三壘手", "游擊手", "左外野手", "中外野手", "右外野手"]
PIT_ORDER = ["先發", "長中繼", "中繼", "勝利組", "拆彈組", "終結"]
POS_G = defaultdict(dict)
for it in fld:
    if it["pos"] in FIELD_POS:
        POS_G[it["player_id"]][it["pos"]] = POS_G[it["player_id"]].get(it["pos"], 0) + (it["g"] or 0)

def esc(s):
    return html.escape(str(s))
def r3(v):
    return "—" if v is None else f"{v:.3f}".lstrip("0") if v < 1 else f"{v:.3f}"


def roles(m):
    return m["tactical_roles"] if m.get("role_format_version") == 2 else ([m["tactical_role"]] if m.get("tactical_role") else [])


def logo(code, size=20):
    return (f'<img src="../../../../web/public/team-icons/refined-{code}.svg" width="{size}" height="{size}" '
            f'alt="" aria-hidden="true" style="vertical-align:middle">')


def prow(m):
    l = m["background"]["line"] or {}
    era = "—" if l.get("era") is None else f'{l["era"]:.2f}'
    return (f'<div class="r"><span class="n">{esc(m["name"])}</span><span class="v">{m["background"]["g"] or 0}G</span>'
            f'<span class="v">{era}</span><span class="v x">{esc(l.get("ip", "—"))}</span></div>')


def frow(m, num, numlabel):
    l = m["background"]["line"] or {}
    return (f'<div class="r"><span class="n">{esc(m["name"])}</span><span class="v">{num}{numlabel}</span>'
            f'<span class="v">{r3(l.get("ops"))}</span><span class="v x">{r3(l.get("avg"))}</span></div>')


def block(title, cols, hdr, cells, note=""):
    counts = " · ".join(f"{len(c)}" for c in cells)
    out = [f'<div class="blk"><div class="bh"><b>{esc(title)}</b><span class="cnt">{counts}</span>'
           f'{f"<span class=bn>{esc(note)}</span>" if note else ""}</div><div class="two">']
    for t, c in zip(teams, cells, strict=False):
        out.append(f'<div class="col"><div class="r hd"><span class="n tn">{logo(t["team_code"], 14)} {esc(t["team_name"])}</span>{hdr}</div>'
                   + ("".join(c) or '<div class="r"><span class="n faint">—</span></div>') + "</div>")
    out.append("</div></div>")
    return "".join(out)


def build():
    parts = []
    # 組成
    comp = []
    for t in teams:
        c = Counter(m["official_position"] for m in t["members"])
        comp.append(f'<div class="comp">{logo(t["team_code"], 18)} <b>{esc(t["team_name"])}</b> '
                    f'<span>投手 <b>{c["投手"]}</b> · 捕手 <b>{c["捕手"]}</b> · 內野 <b>{c["內野手"]}</b> · 外野 <b>{c["外野手"]}</b></span></div>')
    parts.append(f'<div class="two comps">{"".join(comp)}</div>')
    # 投手：角色區塊，人名＋G／ERA／IP
    parts.append('<h3>投手</h3><div class="blocks">')
    phdr = '<span class="v">出賽</span><span class="v">ERA</span><span class="v x">局數</span>'
    for r in PIT_ORDER:
        cells = []
        for t in teams:
            ms = sorted([m for m in t["members"] if m["role"] == "pitching" and r in roles(m)],
                        key=lambda m: -(m["background"]["g"] or 0))
            cells.append([prow(m) for m in ms])
        if any(cells):
            parts.append(block(r, 3, phdr, cells))
    # 野手：守位區塊（例行賽該守位出賽），人名＋該守位 G／OPS／AVG
    parts.append('</div><h3>野手（依守位；數字＝例行賽該守位出賽）</h3><div class="blocks">')
    fhdr = '<span class="v">出賽</span><span class="v">OPS</span><span class="v x">AVG</span>'
    for p in FIELD_POS:
        cells = []
        for t in teams:
            ms = [(m, POS_G[m["player_id"]].get(p, 0)) for m in t["members"] if m["role"] == "batting"]
            ms = sorted([x for x in ms if x[1] > 0], key=lambda x: -x[1])
            cells.append([frow(m, g, "G") for m, g in ms])
        parts.append(block(p, 3, fhdr, cells))
    # DH：本系列 DH 先發次數（門檻待定，示意列出 ≥1）
    cells = []
    for t in teams:
        ms = sorted([(m, sdh.get(m["player_id"], 0)) for m in t["members"] if m["role"] == "batting"
                     and sdh.get(m["player_id"], 0) > 0], key=lambda x: -x[1])
        cells.append([frow(m, n, "場") for m, n in ms])
    parts.append(block("指定打擊（DH）", 3,
                       '<span class="v">DH先發</span><span class="v">OPS</span><span class="v x">AVG</span>', cells,
                       "示意：本系列 DH 先發 ≥1 場；門檻與範圍待確認"))
    parts.append('</div>')
    return "".join(parts)


CSS = """
:root{--paper:#ece8e0;--surface:#f7f5f0;--surface-2:#efebe3;--band:#e4dfd5;--line:rgba(30,40,48,.14);
--ink:#1e2830;--muted:#4f5961;--faint:#5d6770}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:"Noto Sans TC","PingFang TC",system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:14px}
.wrap{max-width:1152px;margin:0 auto;padding:16px}.panel{background:var(--surface);border-radius:4px;padding:16px}
.note{font-size:12px;color:var(--muted);margin:0 0 10px}.faint{color:var(--faint)}
h2{font-size:14px;margin:0;display:flex;gap:6px;align-items:center}
h3{font-size:13px;margin:18px 0 6px;padding-bottom:4px;border-bottom:2px solid var(--ink)}
.seg{display:inline-flex;background:var(--band);border-radius:4px;padding:2px;height:32px;align-items:center}
.seg b,.seg span{padding:4px 10px;font-size:12px;border-radius:3px;white-space:nowrap}.seg b{background:var(--ink);color:var(--paper)}
.seg span{color:var(--muted)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:0 20px}
.comps{margin:4px 0 4px}.comp{font-size:13px;color:var(--muted);padding:6px 0}.comp b{color:var(--ink)}.comp>b:first-of-type{font-size:15px;margin-right:6px}
.comps{border-bottom:1px solid var(--line)}
.blk{border-top:1px solid var(--line);padding:6px 0 8px}
.bh{display:flex;gap:10px;align-items:baseline;font-size:12px;margin-bottom:2px}.bh b{font-size:13px}
.cnt{font-family:Archivo,ui-monospace,monospace;color:var(--muted)}.bn{color:var(--faint);font-size:11px}
.r{display:grid;grid-template-columns:minmax(0,1fr) 44px 46px 46px;gap:4px;padding:2px 6px;font-size:13px;line-height:1.5}
.col .r:nth-child(odd):not(.hd){background:var(--surface-2)}
.r.hd{font-size:11px;color:var(--muted);background:transparent}
.r .n{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.r .v{text-align:right;font-family:Archivo,ui-monospace,monospace}
.r.hd .v{font-family:inherit}.r.hd .tn{font-weight:600;color:var(--muted)}
@media (min-width:1024px){.blocks{display:grid;grid-template-columns:1fr 1fr;gap:0 32px;align-items:start}}
@media (max-width:639px){.wrap{padding:16px}.panel{padding:12px}.two{gap:0 10px}
 .r{grid-template-columns:minmax(0,1fr) 36px 38px;font-size:12.5px;padding:2px 3px}.r .x{display:none}
 .r.hd .v{font-size:10px}.comp span{display:block}}
"""

page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>方案 C：兩隊並列守位表</title><style>{CSS}</style></head>
<body><div class="wrap"><p class="note">#350 修訂示意（靜態 mockup，非產品碼）｜方案 C｜資料：正式站唯讀快照——名單 API（last_refresh_at {esc(roster["as_of"]["last_refresh_at"])}）、/api/v1/season/fielding（2026 一軍例行賽各守位出賽）、本系列 G1–G3 /games/live（DH 先發）；例行賽背景範圍</p>
<div class="panel">
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
<h2>系列賽名單 <span style="font-size:10px;color:var(--muted)">ⓘ</span></h2><div class="seg"><b>例行賽背景</b><span>本系列實戰</span></div></div>
{build()}
<p class="note" style="margin-top:12px">區塊標題旁數字＝兩隊各幾人。同一人守過多個位置會在各守位出現，數字是他在該守位的例行賽出賽數。</p>
</div></div></body></html>"""
open(f"{D}/mockup-c.html", "w").write(page)
print("ok")
