"""DEV-SITEMAP-RECONCILE1：`docs/CPBL_SITE_MAP.md` §4b 的「已爬 ✅／未爬 ⬜」標記機械對帳。

## 為什麼存在

§4b 自稱是爬蟲的事實單一來源（CLAUDE.md 明載），但它的標記一直是**人工維護、從無機械驗證**。
2026-08-20 一小時內連續三次照它行事而報錯，且偏差方向相反——方向相反代表這不是「文件落後」
這種可用時間解釋的漂移，而是根本沒有東西在驗。

## 判準（需求方 2026-08-20 四輪研究後裁定，不得自行改設計）

**掃 module docstring 宣告的端點，不是掃程式碼字串。**
掃字面行不通且會重現本卡要修的錯：`cpbl_advanced.py` 的 URL 是
``f"{BASE}/api/proxy/v1/leaderboards/{lb}"``，端點由變數組成，掃字面找不到
``leaderboards/summary``——而「以為 summary 未爬」正是當天犯的錯之一。
docstring 則是字面、且是人寫給人看的宣告。``{a,b,c}`` 展開語法是既有慣例
（`cpbl_advanced`／`cpbl_home_runs` 皆如此），故解析器必須支援。

## ⚠️ 射程界線（讀報告的人請先看這裡）

本對帳只比對「文件標記 vs docstring 宣告」，**完全不驗證端點是否仍正常運作**。
`/standings/seasonaction` 那種「有爬、docstring 也宣告了、但它忽略 `Year` 參數回錯資料」
（見 issue #154）——**本檔看不出來，也不宣稱看得出來**。那是當天被同一份文件騙的第三次，
而它不在本卡射程。

## 直接執行可產生 artifact

    python tests/test_sitemap_reconcile.py     # 印出完整對帳表，不一致則 exit 1
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_MAP_PATH = REPO_ROOT / "docs" / "CPBL_SITE_MAP.md"
INGEST_DIR = REPO_ROOT / "src" / "cpbl" / "ingest"

# ---------------------------------------------------------------------------
# 封閉集合：官網路由的第一段
# ---------------------------------------------------------------------------
# 刻意是**封閉集合**而非「任何看起來像路徑的字串」。開放式 regex 掃中文 docstring 會撈到
# `/H/RBI/SB`、`/upsert/atomic`、`docs/reference/...` 這類非端點雜訊，讓對帳訊號被洗掉。
# 值域來自 §4b 主站導覽盤點（2026-07-04 實抽 nav）＋ stats 站的 `/api/proxy` 前綴。
OFFICIAL_ROOTS = (
    "api",  # stats.cpbl.com.tw 的 /api/proxy/v1/...
    "about",
    "box",
    "contactus",
    "field",
    "news",
    "player",
    "schedule",
    "sitenav",
    "standings",
    "stats",
    "team",
    "teamhistory",
    "xmdoc",
)

# 前導 `/` 可省略：`cpbl_gamelog` 寫 "box/getlive"、`cpbl_standings` 寫 "standings/seasonaction"。
# 但省略前導 `/` 時必須至少有一層 `/`，否則 "stats.cpbl.com.tw"、"players"、"team_dim"
# 這類散文會被誤判成端點。尾端 negative lookahead 擋 "player" 匹配到 "players" 的前綴。
_ENDPOINT_RE = re.compile(
    r"(?<![0-9A-Za-z_./-])"
    r"(?P<lead>/?)"
    r"(?:" + "|".join(OFFICIAL_ROOTS) + r")"
    r"(?P<rest>(?:/[0-9A-Za-z_{},.*=?&<>-]+)*)"
    r"(?![0-9A-Za-z_-])"
)

_PLACEHOLDER = "\x00"  # 展開期間的佔位符哨兵，避免 `{}` 被無限重複匹配

# ---------------------------------------------------------------------------
# 排除清單：不歸本對帳管的 ingest 模組
# ---------------------------------------------------------------------------
# ⚠️ 語意是「斷言為空」不是「跳過」：見 test_excluded_modules_declare_no_official_endpoint。
# 這幾支若哪天開始宣告官網端點，對帳會轉紅並要求重新評估，不會靜默放行。
EXCLUDED_MODULES: dict[str, str] = {
    "cpbl_coaches_history.py": "打 twbsball（台灣棒球維基館）個人經歷節，非官網；§4c 另有「外部資料源」專節",
    "cpbl_managers.py": "打 zh.wikipedia API（球隊條目歷屆總教練表），非官網；§4c 外部資料源",
    "cpbl_overseas.py": "打 twbsball api.php 取 wikitext（繞 Anubis），非官網；§4c 外部資料源",
    "cpbl_retired.py": "解析 zh.wikipedia 退休背號段，docstring 無 URL、不打官網",
    "cpbl_season_backfill.py": "以 teamscore 回填季彙總，docstring 無 URL；且 §4 註記此模組已壞（遺留）",
    "cpbl_team_history.py": "⚠️ 檔名易誤導：抓的是 twbsball「分類:職棒球隊年表」，不是官網 /teamhistory",
}

# ---------------------------------------------------------------------------
# 文件側的兩種逃生口，一律釘成封閉清單
# ---------------------------------------------------------------------------
# 若不釘死，任何人都能把 ✅ 改成 △ 或加一句「非 ingest」來讓守衛閉嘴。釘成字面清單後，
# 新增逃生口必須改這個檔案，會出現在 code review 的 diff 裡。
# 見 test_ambiguous_rows_are_pinned / test_exempt_rows_are_pinned。

# △＝「部分／間接」，對「是否有 ingest 模組在爬」不構成單一答案，故不做斷言。
AMBIGUOUS_ROWS: dict[str, str] = {
    "/api/proxy/v1/leaderboards/pitch-tracking": "已抓但資料契約待修（一人多列 PitchType）",
    "/player": "名單改由 teamscore 取得，此頁本身未爬；分隊瀏覽視角未用",
}

# ✅ 但不是任何 ingest 模組在爬——結構上不同類，不是「掩蓋不一致」。
EXEMPT_ROWS: dict[str, str] = {
    "/sitenav": "官方規則 PDF 於 2026-07-04 一次性人工下載建檔到 docs/reference/，"
    "無 ingest 模組、無排程；此列的 ✅ 指「已建檔」不是「已爬」",
}

VALID_MARKERS = ("✅", "⬜", "△")


# ---------------------------------------------------------------------------
# 純函式：端點正規化
# ---------------------------------------------------------------------------


def expand_braces(path: str) -> list[str]:
    """展開 ``{a,b,c}``（既有慣例）；無逗號的 ``{year}`` 視為佔位符正規化成 ``{}``。

    佔位符**不做萬用字元比對**：`/api/proxy/v1/players/{acnt}` 正規化後是
    `/api/proxy/v1/players/{}`，不會匹配到 `/api/proxy/v1/players/logs`。若做成萬用字元，
    §4b 標 ⬜ 的 `players/{acnt}` 會被 logs 的宣告誤判成已爬。
    """
    match = re.search(r"\{([^{}]*)\}", path)
    if match is None:
        return [path.replace(_PLACEHOLDER, "{}")]
    inner = match.group(1)
    options = [o.strip() for o in inner.split(",")] if "," in inner else [_PLACEHOLDER]
    out: list[str] = []
    for opt in options:
        out.extend(expand_braces(path[: match.start()] + opt + path[match.end() :]))
    return out


def normalize_endpoint(raw: str) -> str:
    """統一成小寫、有前導 `/`、去 query string 的形式。

    去 query 是刻意的：文件寫 `/team/person?acnt=`、docstring 寫 `/team/person?Acnt=<id>`
    （官網 A 大小寫不一致），保留 query 只會製造假不一致。代價是本對帳**不比對參數**——
    `/standings/seasonaction` 忽略 `Year` 這種缺陷因此看不出來（見模組 docstring 的射程界線）。
    """
    path = raw.split("?", 1)[0].rstrip("/.,;:，。）)")
    return ("/" + path.lstrip("/")).lower()


def extract_declared_endpoints(docstring: str) -> set[str]:
    """從一段 module docstring 抽出它宣告的官網端點。"""
    found: set[str] = set()
    for match in _ENDPOINT_RE.finditer(docstring):
        # 沒有前導 `/`、也沒有下一層路徑 → 是散文裡的普通詞（stats.cpbl / team_dim / players）
        if not match.group("lead") and not match.group("rest"):
            continue
        for expanded in expand_braces(match.group(0)):
            endpoint = normalize_endpoint(expanded)
            if len(endpoint) > 3:
                found.add(endpoint)
    return found


def _module_docstring_of(name: str, ingest_dir: Path = INGEST_DIR) -> str:
    source = (ingest_dir / name).read_text(encoding="utf-8")
    return ast.get_docstring(ast.parse(source)) or ""


def collect_declarations(ingest_dir: Path = INGEST_DIR) -> dict[str, set[str]]:
    """掃 `src/cpbl/ingest/*.py` 全部模組 → {端點: {宣告它的模組檔名}}。

    ⚠️ **預設納入、明列排除**，不是白名單。新增一支爬蟲不需要註冊到任何清單就會被掃到；
    要脫離對帳必須主動寫進 EXCLUDED_MODULES 並附理由（且那也只是斷言為空）。
    """
    declared: dict[str, set[str]] = {}
    for path in sorted(ingest_dir.glob("*.py")):
        if path.name == "__init__.py" or path.name in EXCLUDED_MODULES:
            continue
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        for endpoint in extract_declared_endpoints(docstring):
            declared.setdefault(endpoint, set()).add(path.name)
    return declared


# ---------------------------------------------------------------------------
# 文件側：解析 §4b 的表格列
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocRow:
    endpoint: str
    marker: str  # "✅" / "⬜" / "△" / ""（未標記）
    raw_status: str
    line_no: int
    status_index: int
    siblings: int  # 同一行列出的端點數（`/schedule`、`/box` 這類合併列）


def _split_cells(line: str, n_cols: int) -> list[str]:
    cells = line.strip().strip("|").split("|")
    # 內容欄可能自帶 `|`（例：`PitchType=fastball|breakingball`）→ 溢出的併回最後一欄
    if len(cells) > n_cols:
        cells = cells[: n_cols - 1] + ["|".join(cells[n_cols - 1 :])]
    return cells


def parse_site_map_rows(text: str) -> list[DocRow]:
    """抽 §4b（未爬資源盤點）兩張表的所有列。"""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## 4b."))
    end = next(
        i for i, ln in enumerate(lines) if i > start and ln.startswith("## ") and "4b." not in ln
    )

    rows: list[DocRow] = []
    header: list[str] | None = None
    for idx in range(start, end):
        line = lines[idx]
        if not line.startswith("|"):
            header = None  # 表格結束
            continue
        raw_cells = line.strip().strip("|").split("|")
        if set("".join(raw_cells)) <= set("-: "):
            continue  # 分隔列
        if header is None:
            header = [c.strip() for c in raw_cells]
            continue
        cells = [c.strip() for c in _split_cells(line, len(header))]
        ep_i = next(i for i, h in enumerate(header) if "端點" in h or "路由" in h)
        st_i = next(i for i, h in enumerate(header) if "狀態" in h)
        status = cells[st_i]
        marker = status[:1] if status[:1] in VALID_MARKERS else ""
        tokens = re.findall(r"`([^`]+)`", cells[ep_i])
        for token in tokens:
            rows.append(
                DocRow(
                    endpoint=normalize_endpoint(expand_braces(token)[0]),
                    marker=marker,
                    raw_status=status,
                    line_no=idx,
                    status_index=st_i,
                    siblings=len(tokens),
                )
            )
    return rows


def set_marker(text: str, endpoint: str, marker: str) -> str:
    """把某一列的狀態欄改成指定標記（變異檢驗用）。"""
    rows = [r for r in parse_site_map_rows(text) if r.endpoint == endpoint]
    if len(rows) != 1:
        raise ValueError(f"變異目標必須唯一對到一列：{endpoint} 命中 {len(rows)} 列")
    row = rows[0]
    if row.siblings != 1:
        raise ValueError(f"{endpoint} 與其他端點共用同一列，改標記會波及鄰居")
    lines = text.splitlines()
    cells = _split_cells(lines[row.line_no], row.status_index + 2)
    cells[row.status_index] = f" {marker} "
    lines[row.line_no] = "|" + "|".join(cells) + "|"
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# 對帳
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    kind: str  # under_claim / over_claim / excluded_module_regressed
    endpoint: str
    marker: str
    modules: tuple[str, ...] = field(default=())

    def __str__(self) -> str:
        mods = "、".join(self.modules) if self.modules else "（無）"
        if self.kind == "under_claim":
            return f"[under_claim] {self.endpoint} 文件標「{self.marker or '未標記'}」但 {mods} 的 docstring 宣告在爬"
        if self.kind == "over_claim":
            return f"[over_claim] {self.endpoint} 文件標「✅」但沒有任何 ingest 模組的 docstring 宣告它"
        return f"[{self.kind}] {self.endpoint} {mods}"


def declaring_modules(endpoint: str, declared: dict[str, set[str]]) -> tuple[str, ...]:
    """哪些模組宣告了這個文件列所代表的端點。

    比對規則是**單向前綴**：宣告端點 E 命中文件列 R ⟺ ``E.startswith(R)``。
    §4b 主站表列的是**頁面路由**，docstring 宣告的常是該頁底下的 AJAX 端點，故需要前綴：
    `/box` ← `/box/getlive`、`/standings/season` ← `/standings/seasonaction`、
    `/stats/recordall` ← `/stats/recordallaction`、`/team/*` ← `/team/index`。
    反向（R.startswith(E)）**刻意不做**：`cpbl_stats` 宣告了家族層級的 `/stats`，反向比對
    會讓 `/stats/toplist`、`/stats/mvp` 這些真的沒爬的列全部誤報成已爬。
    """
    prefix = endpoint.rstrip("*")
    hit: set[str] = set()
    for declared_ep, modules in declared.items():
        if declared_ep == endpoint or declared_ep.startswith(prefix):
            hit |= modules
    return tuple(sorted(hit))


def reconcile(rows: list[DocRow], declared: dict[str, set[str]]) -> list[Finding]:
    """雙向對帳。回傳空 list ＝ 文件與 docstring 一致。"""
    findings: list[Finding] = []
    for row in rows:
        if row.endpoint in AMBIGUOUS_ROWS or row.endpoint in EXEMPT_ROWS:
            continue
        modules = declaring_modules(row.endpoint, declared)
        if row.marker == "✅" and not modules:
            findings.append(Finding("over_claim", row.endpoint, row.marker))
        # 未標記（例：「非數據，不爬」）採 fail-closed，與 ⬜ 同待遇：沒說在爬就不該有人在爬
        elif row.marker in ("⬜", "") and modules:
            findings.append(Finding("under_claim", row.endpoint, row.marker, modules))
    return findings


def check_excluded_modules(ingest_dir: Path = INGEST_DIR) -> list[Finding]:
    """排除清單是「斷言為空」不是「跳過」：這幾支開始宣告官網端點就轉紅。"""
    findings: list[Finding] = []
    for name in sorted(EXCLUDED_MODULES):
        path = ingest_dir / name
        if not path.exists():
            continue
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        endpoints = extract_declared_endpoints(docstring)
        if endpoints:
            findings.append(
                Finding("excluded_module_regressed", name, "", tuple(sorted(endpoints)))
            )
    return findings


def uncovered_declarations(rows: list[DocRow], declared: dict[str, set[str]]) -> dict[str, tuple]:
    """宣告了官網端點、但 §4b 完全沒有對應列的情形（新增爬蟲忘了更新文件）。

    這裡用**雙向**家族比對（E 在 R 底下，或 R 在 E 底下），因為問的是「文件有沒有涵蓋到
    這個端點所屬的頁面」，跟 ``declaring_modules`` 問的「這一列有沒有人在爬」不是同一個問題。
    """
    route_prefixes = [r.endpoint.rstrip("*") for r in rows]
    out: dict[str, tuple] = {}
    for endpoint, modules in sorted(declared.items()):
        covered = any(
            endpoint.startswith(prefix) or prefix.startswith(endpoint)
            for prefix in route_prefixes
        )
        if not covered:
            out[endpoint] = tuple(sorted(modules))
    return out


# ---------------------------------------------------------------------------
# 測試
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def site_map_text() -> str:
    return SITE_MAP_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def declared() -> dict[str, set[str]]:
    return collect_declarations()


def test_parser_finds_both_tables(site_map_text: str):
    """先證明解析器沒有靜默空轉——後面每一條斷言都建立在這上面。"""
    rows = parse_site_map_rows(site_map_text)
    assert len(rows) >= 25, f"§4b 只解析到 {len(rows)} 列，表格格式可能變了"
    endpoints = {r.endpoint for r in rows}
    assert "/api/proxy/v1/leaderboards/summary" in endpoints  # stats 站表
    assert "/stats/hr" in endpoints  # 主站表
    assert all(r.marker in (*VALID_MARKERS, "") for r in rows)


def test_literal_grep_would_miss_endpoints_that_docstring_declares(declared: dict[str, set[str]]):
    """本卡的判準之所以是 docstring：URL 由 f-string 組成，掃字面會漏。

    ⚠️ 卡面舉的例子（`leaderboards/summary` 掃字面找不到）**不精確**：URL 確實是
    `f"{BASE}/api/proxy/v1/leaderboards/{lb}"` 組出來的，但 `cpbl_advanced.py:348` 另有一個
    run-manifest 標籤字串 `"leaderboards/summary"`，naive grep 反而會歪打正著命中。
    真正掃字面必漏的是 `exit-velocity` 與 `batted-ball`——它們只在 `:332` 以
    `"leaderboards/pr-table+exit-velocity+batted-ball"` 這種 `+` 串接標籤出現，
    子字串比對不會命中。結論（用 docstring 不用字面）不變，例子換成會真的失敗的那兩個。
    """
    src = (INGEST_DIR / "cpbl_advanced.py").read_text(encoding="utf-8")
    assert 'f"{BASE}/api/proxy/v1/leaderboards/{lb}"' in src, "URL 組法變了，請重讀本卡判準理由"

    for slug in ("exit-velocity", "batted-ball"):
        endpoint = f"/api/proxy/v1/leaderboards/{slug}"
        assert endpoint.removeprefix("/api/proxy/v1/") not in src.replace(
            _module_docstring_of("cpbl_advanced.py"), ""
        ), f"{slug} 現在有字面出現了，掃字面失效的前提要重驗"
        assert declared[endpoint] == {"cpbl_advanced.py"}, "docstring 判準必須抓得到"

    assert declared["/api/proxy/v1/leaderboards/summary"] == {"cpbl_advanced.py"}


def test_brace_list_expands_and_placeholder_does_not():
    """``{a,b,c}`` 展開是既有慣例；``{year}`` 是佔位符，兩者不可混為一談。"""
    assert set(expand_braces("/x/{a,b,c}")) == {"/x/a", "/x/b", "/x/c"}
    assert expand_braces("/api/proxy/v1/games/{year}-{kind}-{sno}") == [
        "/api/proxy/v1/games/{}-{}-{}"
    ]
    # 佔位符不是萬用字元：players/{acnt} 不得吃掉 players/logs
    assert not declaring_modules(
        "/api/proxy/v1/players/{}", {"/api/proxy/v1/players/logs": {"x.py"}}
    )


def test_site_map_markers_reconcile_with_docstrings(site_map_text, declared):
    """核心守衛：§4b 的 ✅／⬜ 必須與 ingest docstring 的宣告一致。"""
    rows = parse_site_map_rows(site_map_text)
    findings = reconcile(rows, declared)
    assert not findings, "\n".join(["§4b 標記與 docstring 宣告不一致：", *map(str, findings)])


def test_excluded_modules_declare_no_official_endpoint():
    """排除＝斷言為空。這幾支哪天開始打官網，這條會紅並要求重新評估排除理由。"""
    findings = check_excluded_modules()
    assert not findings, "\n".join(
        [
            "排除清單中的模組現在宣告了官網端點，排除理由已失效，須重新評估：",
            *map(str, findings),
        ]
    )
    # 非空轉證明：這 6 支確實都存在且確實被掃過
    present = [n for n in EXCLUDED_MODULES if (INGEST_DIR / n).exists()]
    assert len(present) == 6, f"排除清單與現實不符，只找到 {present}"


def test_every_declared_endpoint_is_covered_by_site_map(site_map_text, declared):
    """反向：有人在爬、但 §4b 連一列都沒有 → 文件漏列。"""
    rows = parse_site_map_rows(site_map_text)
    uncovered = uncovered_declarations(rows, declared)
    assert not uncovered, f"下列端點有 docstring 宣告但 §4b 無對應列：{uncovered}"


def test_ambiguous_rows_are_pinned(site_map_text):
    """△ 是唯一「不做斷言」的標記，故它的成員必須釘死，否則會變成閉嘴用的逃生口。"""
    rows = parse_site_map_rows(site_map_text)
    actual = {r.endpoint for r in rows if r.marker == "△"}
    assert actual == set(AMBIGUOUS_ROWS), (
        f"§4b 的 △ 列變了（實際 {sorted(actual)}）。新增 △ 等於讓該列脫離對帳，"
        "必須在 AMBIGUOUS_ROWS 補上理由。"
    )


def test_exempt_rows_are_pinned(site_map_text):
    """✅ 但非 ingest 模組所為的例外，同樣釘死成封閉清單。"""
    rows = {r.endpoint for r in parse_site_map_rows(site_map_text)}
    assert set(EXEMPT_ROWS) <= rows, "EXEMPT_ROWS 有列已從 §4b 消失，請一併清掉"
    assert set(EXEMPT_ROWS) == {"/sitenav"}, "新增豁免必須是有意識的 diff，不可默默長出來"


# ---- 2026-08-20 三次真實錯誤的回歸樣本（判準的驗收樣本，不是舉例） ----


def test_regression_samples_2026_08_20(site_map_text, declared):
    """(a)(b) 必須抓到、(c) 不得誤報——三者在同一次對帳裡一起斷言。

    合成一份「當天的文件狀態」：把 summary 與 stats/hr 改回 ⬜（當天的錯誤標記），
    其餘不動。正確的判準必須恰好報出這兩筆，且不碰 (c) 的三個真未爬端點。
    """
    mutated = site_map_text
    for endpoint in ("/api/proxy/v1/leaderboards/summary", "/stats/hr"):
        mutated = set_marker(mutated, endpoint, "⬜")

    findings = reconcile(parse_site_map_rows(mutated), declared)
    caught = {f.endpoint for f in findings if f.kind == "under_claim"}

    # (a) 文件標 ⬜、cpbl_advanced.py docstring 有宣告 → 必須抓到
    assert "/api/proxy/v1/leaderboards/summary" in caught
    assert "cpbl_advanced.py" in dict(
        (f.endpoint, f.modules) for f in findings
    )["/api/proxy/v1/leaderboards/summary"]

    # (b) 文件標 ⬜、cpbl_home_runs.py docstring 有宣告 → 必須抓到
    assert "/stats/hr" in caught
    assert "cpbl_home_runs.py" in dict((f.endpoint, f.modules) for f in findings)["/stats/hr"]

    # (c) 文件標 ⬜ 且 docstring 也無 → 不得誤報
    for endpoint in ("/standings/special", "/stats/toplist", "/standings/history"):
        assert endpoint not in {f.endpoint for f in findings}

    # 恰好兩筆：多報就是誤報，少報就是漏抓
    assert caught == {"/api/proxy/v1/leaderboards/summary", "/stats/hr"}
    assert not [f for f in findings if f.kind == "over_claim"]


def test_regression_samples_are_not_vacuous(site_map_text):
    """證明上一條不是空轉：拿掉判準（宣告集合清空）→ (a)(b) 就抓不到了。

    這對應「移除判準時三組樣本測試要紅」。(c) 的不誤報單獨看是可以靠「什麼都不報」
    作弊通過的，所以 (a)(b)(c) 綁在同一條斷言、再用本條證明 (a)(b) 依賴真實抽取。
    """
    mutated = site_map_text
    for endpoint in ("/api/proxy/v1/leaderboards/summary", "/stats/hr"):
        mutated = set_marker(mutated, endpoint, "⬜")
    rows = parse_site_map_rows(mutated)

    gutted = [f for f in reconcile(rows, {}) if f.kind == "under_claim"]
    assert not gutted, "判準被抽掉後仍有 under_claim，代表發現來源不是 docstring"

    real = [f for f in reconcile(rows, collect_declarations()) if f.kind == "under_claim"]
    assert {f.endpoint for f in real} == {"/api/proxy/v1/leaderboards/summary", "/stats/hr"}

    # 判準被抽掉後，over_claim 反而會全面誤報 → 說明「宣告集合為空」不是安全的退化態，
    # 沒有人能靠讓抽取器回空集合來讓整套對帳閉嘴。
    assert len([f for f in reconcile(rows, {}) if f.kind == "over_claim"]) > 10


# ---- 可證偽的變異檢驗（雙向）：查核者會親手改，這裡先程式化證明一次 ----


def test_mutation_crawled_endpoint_marked_not_crawled_turns_red(site_map_text, declared):
    """方向一：把實際有在爬的 `/api/proxy/v1/players/logs` 改標 ⬜ → 必須轉紅；還原 → 轉綠。"""
    target = "/api/proxy/v1/players/logs"
    assert not reconcile(parse_site_map_rows(site_map_text), declared)  # 還原態＝綠

    mutated = set_marker(site_map_text, target, "⬜")
    findings = reconcile(parse_site_map_rows(mutated), declared)
    assert [f.endpoint for f in findings] == [target]
    assert findings[0].kind == "under_claim"
    assert "cpbl_pitch_tracking.py" in findings[0].modules

    restored = set_marker(mutated, target, "✅")
    assert not reconcile(parse_site_map_rows(restored), declared)


def test_mutation_uncrawled_endpoint_marked_crawled_turns_red(site_map_text, declared):
    """方向二：把真的沒爬的 `/stats/toplist` 改標 ✅ → 必須轉紅；還原 → 轉綠。"""
    target = "/stats/toplist"
    mutated = set_marker(site_map_text, target, "✅")
    findings = reconcile(parse_site_map_rows(mutated), declared)
    assert [f.endpoint for f in findings] == [target]
    assert findings[0].kind == "over_claim"

    restored = set_marker(mutated, target, "⬜")
    assert not reconcile(parse_site_map_rows(restored), declared)


# ---------------------------------------------------------------------------
# artifact：直接執行印出完整對帳表
# ---------------------------------------------------------------------------


def main() -> int:
    text = SITE_MAP_PATH.read_text(encoding="utf-8")
    rows = parse_site_map_rows(text)
    decl = collect_declarations()

    print(f"# CPBL_SITE_MAP §4b 對帳（{SITE_MAP_PATH.relative_to(REPO_ROOT)}）")
    print(f"# 文件列 {len(rows)}／docstring 宣告端點 {len(decl)}"
          f"／掃描模組目錄 {INGEST_DIR.relative_to(REPO_ROOT)}")
    print(f"# 排除模組 {len(EXCLUDED_MODULES)} 支（斷言為空）")
    print("#" + "-" * 100)
    print(f"{'標記':<4} {'端點':<46} {'判定':<12} 宣告模組")
    for row in rows:
        modules = declaring_modules(row.endpoint, decl)
        if row.endpoint in AMBIGUOUS_ROWS:
            verdict = "△ 不斷言"
        elif row.endpoint in EXEMPT_ROWS:
            verdict = "豁免"
        elif row.marker == "✅" and not modules:
            verdict = "OVER-CLAIM"
        elif row.marker in ("⬜", "") and modules:
            verdict = "UNDER-CLAIM"
        else:
            verdict = "ok"
        print(f"{row.marker or '—':<4} {row.endpoint:<46} {verdict:<12} {'、'.join(modules)}")

    findings = reconcile(rows, decl) + check_excluded_modules()
    uncovered = uncovered_declarations(rows, decl)
    print("#" + "-" * 100)
    for finding in findings:
        print(finding)
    for endpoint, modules in uncovered.items():
        print(f"[uncovered] {endpoint} 有宣告但 §4b 無對應列（{'、'.join(modules)}）")
    total = len(findings) + len(uncovered)
    print(f"# 結果：{'PASS（0 不一致）' if total == 0 else f'FAIL（{total} 筆不一致）'}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
