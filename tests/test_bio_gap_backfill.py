"""INGEST-PLAYER-BIO-GAP1 的 fail-closed 寫入閘門守衛。

**為什麼是測試**：canonical `cpbl_player_bio._upsert` 對 height/weight/debut/
education/birthplace/draft 是無條件 `EXCLUDED` 覆蓋（只有 country/birthday/
bats/throws 走 COALESCE）。補值腳本若在「反爬挑戰頁」或「查無此人空頁」上仍呼叫
`_upsert`，`parse_bio` 的全 None 會把該員既有欄位洗成 NULL——補值卡反而弄丟資料。
此守衛把「只有 person_page_parsed 才可寫」釘成可執行契約，而非註解裡的承諾。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill_player_bio_gap1", ROOT / "scripts" / "backfill_player_bio_gap1.py")
assert SPEC and SPEC.loader
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)

from cpbl.ingest.cpbl_player_bio import parse_bio  # noqa: E402

# 反爬挑戰頁：無 CPBL 內容標記
CHALLENGE = "<html><body><script>challenge()</script></body></html>"

# 完整 CPBL 頁但查無此人：有站台標記、無 name 區塊
NO_PERSON = '<html><body><div class="footer">中華職棒全球資訊網</div></body></html>'

# 正常 person 頁：name + 國籍/出生地 + 生日
PERSON = """<html><body><div class="footer">中華職棒全球資訊網</div>
<div class="name">力亞士</div>
<dd class="a"><div class="label">身高/體重</div><div class="desc">190 (CM) / 95 (KG)</div></dd>
<dd class="b"><div class="label">國籍/出生地</div><div class="desc">美國</div></dd>
<dd class="c"><div class="label">生日</div><div class="desc">1995/04/21</div></dd>
</body></html>"""

# person 頁但完全沒有 bio 欄位（官網欄位真的缺）
PERSON_NO_BIO = """<html><body><div class="footer">中華職棒全球資訊網</div>
<div class="name">力亞士</div></body></html>"""


def _symptom(html: str) -> str:
    return backfill.symptom(html, parse_bio(html))


def test_symptom_classifies_each_page_shape():
    assert _symptom(CHALLENGE) == "non_cpbl_page"
    assert _symptom(NO_PERSON) == "cpbl_page_no_person"
    assert _symptom(PERSON) == "person_page_parsed"
    assert _symptom(PERSON_NO_BIO) == "person_page_no_bio_fields"


def test_only_parsed_person_page_is_writable():
    """fail-closed：唯一可寫徵狀是 person_page_parsed。"""
    assert backfill.WRITABLE == "person_page_parsed"
    for html in (CHALLENGE, NO_PERSON, PERSON_NO_BIO):
        assert _symptom(html) != backfill.WRITABLE, (
            "非人員頁／無 bio 頁不得寫入——canonical _upsert 會把既有 "
            "height/weight/debut/birthplace 洗成 NULL")


def test_degraded_pages_parse_to_all_none_which_would_wipe_columns():
    """記錄「為何必須 fail-closed」的事實：退化頁的 parse 結果全是 None。"""
    for html in (CHALLENGE, NO_PERSON):
        bio = parse_bio(html)
        for col in ("height_cm", "weight_kg", "debut", "birthplace", "draft"):
            assert bio[col] is None
