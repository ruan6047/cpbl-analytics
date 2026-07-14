"""官方球隊登錄名單解析（`/team/index` 的 TeamPlayersList）。"""

from __future__ import annotations

from cpbl.ingest.cpbl_roster import parse_roster

# 官網實測結構（2026-07）：教練列**沒有** Acnt 連結，球員列才有。
_HTML = """
<div class="cat_title"><a name="coach"></a>教練</div>
<div class="TeamPlayersList">
  <div class="item"><div><div class="img"><span></span></div>
    <div class="cont">
      <div class="pos">一軍總教練</div>
      <div class="name">曾豪駒</div>
      <div class="number">99</div>
    </div></div></div>
</div>
<div class="cat_title"><a name="pitcher"></a>投手</div>
<div class="TeamPlayersList">
  <div class="item"><div><div class="img"><a href="/team/person?Acnt=0000005558"><span>蘇俊璋</span></a></div>
    <div class="cont">
      <div class="pos">投手</div>
      <div class="name"><a href="/team/person?Acnt=0000005558">蘇俊璋</a></div>
      <div class="number">00</div>
    </div></div></div>
</div>
"""


def test_parses_players_with_position_and_number():
    rows = parse_roster(_HTML)

    assert rows == [{"pos": "投手", "player_id": "0000005558",
                     "name": "蘇俊璋", "uniform_no": "00"}]


def test_coaches_are_excluded_by_absence_of_acnt_link():
    """教練與球員同頁；教練列無 Acnt 連結，故不會被誤收進登錄名單。"""
    assert all(r["name"] != "曾豪駒" for r in parse_roster(_HTML))


def test_empty_html_yields_nothing():
    assert parse_roster("<div></div>") == []
