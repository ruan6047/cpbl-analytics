"""#350 方案 D 示意 mockup 產生器（可拋棄；不是產品碼）。輸出 mockup-d-background.html／mockup-d-series.html。

輸入全是正式站唯讀快照（mockup 用；產品實作一律由名單 API 擴充欄位提供，⛔ 前端不另抓這些端點）：
- roster-2026-C-snapshot.json            ← GET /api/v1/playoffs/roster?season=2026&series=C
- fielding-2026-A-snapshot.json          ← GET /api/v1/season/fielding?season=2026&limit=1000&kind_code=A（主守位）
- batting-leaders-2026-A-snapshot.json   ← GET /api/v1/season/batting-leaders?season=2026&limit=500&min_pa=0&kind_code=A（例行賽打擊原始計數）
- series-2026-C.json                     ← derive_series_batting.py 由 GET /api/v1/games/{1,2,3}/live 彙總（本系列打擊計數＋DH 先發）
例行賽 DH 先發數沒有任何公開端點，mockup 的例行賽 DH 區只放佔位，須待 API 擴充。
用法：python3 -I gen_mockup_d.py <assets_dir>
"""
import html
import json
import sys
from collections import Counter, defaultdict

D = sys.argv[1]
roster = json.load(open(f"{D}/roster-2026-C-snapshot.json"))
fld = json.load(open(f"{D}/fielding-2026-A-snapshot.json"))["items"]
bl = {r["player_id"]: r for r in json.load(open(f"{D}/batting-leaders-2026-A-snapshot.json"))["items"]}
ser = json.load(open(f"{D}/series-2026-C.json"))
teams = roster["teams"]

FIELD_POS = ["捕手", "一壘手", "二壘手", "三壘手", "游擊手", "左外野手", "中外野手", "右外野手"]
PIT_ORDER = ["先發", "長中繼", "中繼", "勝利組", "拆彈組", "終結"]
POS_G = defaultdict(dict)
for it in fld:
    if it["pos"] in FIELD_POS:
        POS_G[it["player_id"]][it["pos"]] = POS_G[it["player_id"]].get(it["pos"], 0) + (it["g"] or 0)


def primary(pid):
    d = POS_G.get(pid)
    if not d:
        return None
    return max(FIELD_POS, key=lambda p: (d.get(p, 0), -FIELD_POS.index(p))) if any(d.values()) else None


esc = lambda s: html.escape(str(s))


def r3(v):
    return "—" if v is None else (f"{v:.3f}"[1:] if v < 1 else f"{v:.3f}")


def roles(m):
    return m["tactical_roles"] if m.get("role_format_version") == 2 else ([m["tactical_role"]] if m.get("tactical_role") else [])


def logo(code, size=18):
    return (f'<img src="../../../../web/public/team-icons/refined-{code}.svg" width="{size}" height="{size}" '
            f'alt="" aria-hidden="true" style="vertical-align:middle">')


def bat_counts(pid, scope):
    if scope == "series":
        return ser["batting"].get(pid)
    r = bl.get(pid)
    return None if r is None else {k: r.get(k) or 0 for k in ("pa", "ab", "h", "bb", "hbp", "sf", "tb")} | {"g": r.get("g") or 0}


def bat_comp(ms, scope):
    if not ms:
        return "—"
    t = Counter()
    for m in ms:
        c = bat_counts(m["player_id"], scope)
        if c:
            t.update({k: c.get(k, 0) for k in ("ab", "h", "bb", "hbp", "sf", "tb")})
    if not t["ab"]:
        return "AVG — · OPS —"
    avg = t["h"] / t["ab"]
    den = t["ab"] + t["bb"] + t["hbp"] + t["sf"]
    obp = (t["h"] + t["bb"] + t["hbp"]) / den if den else None
    slg = t["tb"] / t["ab"]
    return f"AVG <b>{r3(avg)}</b> · OPS <b>{r3((obp or 0) + slg)}</b>"


def pit_line(m, scope):
    if scope == "series":
        s = m.get("series") or {}
        return s.get("line")
    return m["background"]["line"]


def pit_comp(ms, scope):
    outs = er = 0
    for m in ms:
        l = pit_line(m, scope)
        if l:
            outs += l.get("outs") or 0
            er += l.get("er") or 0
    if not ms:
        return "—"
    if not outs:
        return "ERA — · 0 局"
    return f"ERA <b>{er * 27 / outs:.2f}</b> · <b>{outs // 3}.{outs % 3}</b> 局"


def g_of(m, scope, pos=None):
    if scope == "series":
        s = m.get("series") or {}
        return s.get("g") or 0
    return POS_G.get(m["player_id"], {}).get(pos, 0) if pos else (m["background"]["g"] or 0)


def names(ms):
    if not ms:
        return '<span class="faint">—</span>'
    return "".join(f'<button class="nm" type="button">{esc(m["name"])}</button>' for m in ms)


def block(title, per_team, note=""):
    cols = "".join(f'<div class="col"><div class="comp">{logo(t["team_code"], 14)} {comp}</div>'
                   f'<div class="names">{nm}</div></div>' for t, (comp, nm) in zip(teams, per_team))
    return (f'<section class="blk"><h4>{esc(title)}'
            f'{f"<span class=bn>{esc(note)}</span>" if note else ""}</h4><div class="two">{cols}</div></section>')


def build(scope):
    out = []
    comp = []
    for t in teams:
        c = Counter(m["official_position"] for m in t["members"])
        comp.append(f'<div class="tc">{logo(t["team_code"], 20)} <b>{esc(t["team_name"])}</b>'
                    f'<span>投手 <b>{c["投手"]}</b> · 捕手 <b>{c["捕手"]}</b> · 內野 <b>{c["內野手"]}</b> · 外野 <b>{c["外野手"]}</b></span></div>')
    out.append(f'<div class="two tcs">{"".join(comp)}</div>')
    out.append('<h3>投手</h3><div class="blocks">')
    for r in PIT_ORDER:
        per = []
        for t in teams:
            ms = sorted([m for m in t["members"] if m["role"] == "pitching" and r in roles(m)],
                        key=lambda m: (-g_of(m, scope), m["player_id"]))
            per.append((pit_comp(ms, scope), names(ms)))
        out.append(block(r, per))
    out.append('</div><h3>野手（依主守位）</h3><div class="blocks">')
    for p in FIELD_POS:
        per = []
        for t in teams:
            ms = [m for m in t["members"] if m["role"] == "batting" and primary(m["player_id"]) == p]
            ms.sort(key=lambda m: (-g_of(m, scope, p if scope == "background" else None), m["player_id"]))
            per.append((bat_comp(ms, scope), names(ms)))
        out.append(block(p, per))
    per = []
    if scope == "series":
        for t in teams:
            ms = [m for m in t["members"] if m["role"] == "batting" and ser["dh_starts"].get(m["player_id"], 0) >= 1]
            ms.sort(key=lambda m: (-ser["dh_starts"].get(m["player_id"], 0), m["player_id"]))
            per.append((bat_comp(ms, scope), names(ms)))
        out.append(block("指定打擊（DH）", per, "本系列 DH 先發 ≥1 場"))
    else:
        ph = '<span class="dep">例行賽 DH 先發數待名單 API 擴充，示意無資料</span>'
        out.append(block("指定打擊（DH）", [("AVG — · OPS —", ph)] * 2, "例行賽 DH 先發 ≥4 場"))
    nofield = [m for t in teams for m in t["members"] if m["role"] == "batting" and primary(m["player_id"]) is None]
    out.append("</div>")
    if nofield:
        out.append(f'<p class="note">無例行賽守備紀錄：{"、".join(esc(m["name"]) for m in nofield)}</p>')
    return "".join(out)


CSS = """
:root{--paper:#ece8e0;--surface:#f7f5f0;--surface-2:#efebe3;--band:#e4dfd5;--line:rgba(30,40,48,.14);
--ink:#1e2830;--muted:#4f5961;--faint:#5d6770;--accent:#1e6c8c}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:"Noto Sans TC","PingFang TC",system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:14px}
.wrap{max-width:1152px;margin:0 auto;padding:16px}.panel{background:var(--surface);border-radius:4px;padding:16px}
.note{font-size:12px;color:var(--muted);margin:0 0 10px}.faint{color:var(--faint)}
h2{font-size:14px;margin:0}
h3{font-size:13px;margin:18px 0 4px;padding-bottom:4px;border-bottom:2px solid var(--ink)}
h4{font-size:13px;margin:0 0 4px;display:flex;gap:8px;align-items:baseline}.bn{font-size:11px;font-weight:400;color:var(--faint)}
.seg{display:inline-flex;background:var(--band);border-radius:4px;padding:2px;height:32px;align-items:center}
.seg b,.seg span{padding:4px 10px;font-size:12px;border-radius:3px;white-space:nowrap}.seg b{background:var(--ink);color:var(--paper)}
.seg span{color:var(--muted)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}
.tcs{padding:4px 0 8px;border-bottom:1px solid var(--line)}.tc{font-size:13px;color:var(--muted)}.tc b{color:var(--ink)}
.tc>b:first-of-type{font-size:15px;margin-right:8px}
.blk{border-top:1px solid var(--line);padding:8px 0 10px}
.comp{font-size:12px;color:var(--muted);background:var(--surface-2);border-radius:3px;padding:4px 8px;margin-bottom:6px;
font-family:Archivo,ui-monospace,monospace}
.comp b{color:var(--ink);font-size:13px}
.names{display:flex;flex-wrap:wrap;gap:4px 12px;padding:0 8px}
.nm{all:unset;cursor:pointer;font-size:13.5px;line-height:1.7;border-bottom:1px solid var(--line)}
.nm:hover{color:var(--accent);border-color:var(--accent)}
.dep{font-size:11px;color:var(--muted);border:1.5px dashed var(--muted);padding:2px 6px;border-radius:3px}
@media (min-width:1024px){.blocks{display:grid;grid-template-columns:1fr 1fr;gap:0 32px;align-items:start}}
@media (max-width:639px){.wrap{padding:16px}.panel{padding:12px}.two{gap:0 10px}.tc span{display:block}
 .comp{padding:4px 6px;font-size:11px}.comp b{font-size:12px}.names{padding:0 4px;gap:2px 10px}}
"""


def page(scope):
    label = "例行賽背景" if scope == "background" else "本系列實戰"
    seg = ('<div class="seg"><b>例行賽背景</b><span>本系列實戰</span></div>' if scope == "background"
           else '<div class="seg"><span>例行賽背景</span><b>本系列實戰</b></div>')
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>方案 D：{label}</title><style>{CSS}</style></head>
<body><div class="wrap"><p class="note">#350 方案 D 示意（靜態 mockup，非產品碼）｜{label}｜資料：正式站唯讀快照（名單 API last_refresh_at {esc(roster["as_of"]["last_refresh_at"])}、/season/fielding、/season/batting-leaders、本系列 G1–G3 /games/live）；產品版改由名單 API 擴充欄位提供</p>
<div class="panel"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
<h2>系列賽名單 <span style="font-size:10px;color:var(--muted)">ⓘ</span></h2>{seg}</div>
{build(scope)}
<p class="note" style="margin-top:12px">灰底是該位置的綜合成績（{"例行賽" if scope == "background" else "本系列"}成員合計）；點名字看個人成績與能力。</p>
</div></div></body></html>"""


for sc in ("background", "series"):
    open(f"{D}/mockup-d-{sc}.html", "w").write(page(sc))
print("ok")
