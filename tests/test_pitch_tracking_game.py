"""INGEST-GAME-TM-REFACTOR1：單場 API LiveLog 共用 parser 單元測試（DB-free）。

驗證 `parse_pitches` 對單場 API `Data.Game.LiveLog[]` 逐字沿用與 logs API 相同的 `_record`：
- LiveLog 逐球（Trackman 有值、Year 為字串）解析出與 logs 路徑等價的入庫 tuple。
- 非投球事件（牽制／換投／暫停，Trackman=null）自動略過。
- 一場內每筆逐球的 PK (year,kind,game,pitcher,pitch_cnt) 唯一。

fixture 取自 2026-A-99 單場 API 實抽（欄位名與巢狀結構與官方一致；數值為實測樣本）。
"""

from __future__ import annotations

from cpbl.ingest.cpbl_pitch_tracking import _COLS, parse_pitches

_COL_NAMES = [c.strip() for c in _COLS.split(",")]


def _pitch_entry(pitch_cnt: int, pitcher_acnt: str, *, with_hit: bool = True) -> dict:
    """單場 API LiveLog 的一筆「逐球」事件（Trackman 有值）。Year 刻意用字串，比照官方。"""
    tm: dict = {
        "Play": {"PitchTag": {"PitchCall": "InPlay", "AutoPitchType": "breakingball",
                              "TaggedPitchType": "breakingball"}},
        "Pitch": {
            "Release": {"RelSide": 0.399510504, "RelSpeed": 146.74526456832,
                        "SpinRate": 2598.3015, "Extension": 1.51799544, "RelHeight": 1.854826872},
            "Location": {"ZoneTime": 0.425535, "ZoneSpeed": 133.81899746688,
                         "PlateLocSide": -0.046631352, "PlateLocHeight": 0.644475216},
            "Flight": {"PolyFit": {"PitchTrajectory": {
                "X": [16.921417008, -40.62506378400001, 4.418713032],
                "Y": [1.854634848, -1.6213074, -2.872121256],
                "Z": [-0.399050256, 1.298597352, -0.592656168],
            }}},
        },
    }
    if with_hit:
        tm["Hit"] = {
            "Launch": {"Angle": 25.006317, "Direction": 21.831276,
                       "ExitSpeed": 130.47719465088, "HitSpinRate": 4301.546},
            "LandingFlat": {"Bearing": 33.40192, "Distance": 76.647860928,
                            "HangTime": 3.36565, "Confidence": "Medium"},
        }
    return {
        "Year": "2026", "KindCode": "A", "GameSno": 99, "PitchCnt": pitch_cnt,
        "PitcherAcnt": pitcher_acnt, "PitcherName": "獅帝芬",
        "HitterAcnt": "0000006730", "HitterName": "張仁瑋",
        "InningSeq": 1, "BallCnt": 0, "StrikeCnt": 1, "OutCnt": 0, "BattingOrder": 1,
        "Content": "擊出界外球。", "IsBall": "0", "IsStrike": "1", "IsChangePlayer": "0",
        "Trackman": tm,
    }


def _pickoff_entry(pitch_cnt: int) -> dict:
    """牽制事件：Trackman 缺席（單場 API 語意），須被略過。"""
    return {"Year": "2026", "KindCode": "A", "GameSno": 99, "PitchCnt": pitch_cnt,
            "PitcherAcnt": "0000007597", "Content": "投手牽制一壘跑者", "IsChangePlayer": "0"}


def _change_pitcher_entry() -> dict:
    """換投事件：Trackman=null，PitchCnt=0，須被略過（不得與真逐球 PK 相撞）。"""
    return {"Year": "2026", "KindCode": "A", "GameSno": 99, "PitchCnt": 0,
            "PitcherAcnt": "0000007597", "Content": "更換投手：獅帝芬=>高偉強。",
            "IsChangePlayer": "1", "Trackman": None}


def _as_dict(rec: tuple) -> dict:
    assert len(rec) == len(_COL_NAMES)
    return dict(zip(_COL_NAMES, rec, strict=True))


def test_livelog_pitch_parsed_equivalently() -> None:
    """LiveLog 逐球經共用 parser → 與 logs 路徑同欄位、Year 字串正確轉 int。"""
    rows = parse_pitches([_pitch_entry(1, "0000007597")], "A")
    assert len(rows) == 1
    d = _as_dict(rows[0])
    assert d["year"] == 2026 and d["kind_code"] == "A" and d["game_sno"] == 99
    assert d["pitcher_acnt"] == "0000007597" and d["pitch_cnt"] == 1
    # 物理欄位原值保存（_f 不 round）；深層九係數原值
    assert d["rel_speed"] == 146.74526456832
    assert d["traj_x0"] == 16.921417008
    assert d["hit_landing_confidence"] == "Medium"
    assert d["auto_pitch_type"] == "breakingball"


def test_non_pitch_events_skipped() -> None:
    """牽制／換投（Trackman 缺席或 null）不入庫，只留真逐球。"""
    entries = [
        _pitch_entry(1, "0000007597"),
        _pickoff_entry(10),
        _pitch_entry(2, "0000007597", with_hit=False),
        _change_pitcher_entry(),
    ]
    rows = parse_pitches(entries, "A")
    assert len(rows) == 2  # 只有兩筆真逐球
    pitch_cnts = sorted(_as_dict(r)["pitch_cnt"] for r in rows)
    assert pitch_cnts == [1, 2]


def test_livelog_pk_unique_within_game() -> None:
    """一場內各逐球 PK 唯一（換投的 PitchCnt=0 已被略過，不與真球衝突）。"""
    entries = [_pitch_entry(i, "0000007597") for i in range(1, 6)] + [_change_pitcher_entry()]
    rows = parse_pitches(entries, "A")
    pks = [(_as_dict(r)["year"], _as_dict(r)["kind_code"], _as_dict(r)["game_sno"],
            _as_dict(r)["pitcher_acnt"], _as_dict(r)["pitch_cnt"]) for r in rows]
    assert len(pks) == len(set(pks)) == 5


def test_no_hit_pitch_keeps_trajectory() -> None:
    """無擊球（好球/壞球）逐球：Hit 欄為 None，但軌跡九係數仍保存。"""
    rows = parse_pitches([_pitch_entry(3, "0000007597", with_hit=False)], "A")
    d = _as_dict(rows[0])
    assert d["hit_exit_speed"] is None and d["hit_landing_bearing"] is None
    assert d["traj_x0"] == 16.921417008
