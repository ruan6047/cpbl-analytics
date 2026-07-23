"""INGEST-DEEP-TRACKMAN1：深層 TrackMan 欄位解析單元測試（DB-free）。

驗證 cpbl_pitch_tracking._record／_COLS 正確搬出落地方位角、落地信心、擊球轉速與官方
九個原始多項式係數，且原值不 round（紅線：不可由衍生 traj_accel_y/z 反推）。
payload 結構取自 2026-A logs API 實例（魔爾曼 0000007790）。
"""

from __future__ import annotations

from cpbl.ingest.cpbl_pitch_tracking import _COLS, _record

# 2026-A logs API 實抽（GameSno 69, PitchCnt 1）——原始高精度值，測 float8 原值保存。
_REAL = {
    "Year": 2026, "KindCode": "A", "GameSno": 69, "PitcherAcnt": "0000007790",
    "PitchCnt": 1, "PitcherName": "魔爾曼", "HitterAcnt": "0000000123", "HitterName": "打者",
    "InningSeq": 1, "BallCnt": 0, "StrikeCnt": 0, "OutCnt": 0, "BattingOrder": 1,
    "Content": "一壘安打",
    "Trackman": {
        "Play": {"PitchTag": {"PitchCall": "InPlay", "AutoPitchType": "Fastball",
                              "TaggedPitchType": None}},
        "Pitch": {
            "Release": {"RelSpeed": 146.3, "SpinRate": 2326.9, "RelSide": -1.2,
                        "RelHeight": 1.8, "Extension": 1.9},
            "Location": {"ZoneSpeed": 140.0, "PlateLocSide": 0.1, "PlateLocHeight": 0.7,
                         "ZoneTime": 0.41},
            "Flight": {"PolyFit": {"PitchTrajectory": {
                "X": [16.698916056, -39.94326276, 4.884487056],
                "Y": [2.134901496, -1.851068688, -2.087227728],
                "Z": [-0.48109632, 1.732123536, -1.504605576],
            }}},
        },
        "Hit": {
            "Launch": {"ExitSpeed": 165.8245526784, "Angle": 17.063635,
                       "Direction": -22.714012, "HitSpinRate": 1204.3561},
            "LandingFlat": {"Bearing": -28.307495, "Distance": 85.23995042400001,
                            "HangTime": 2.753171, "Confidence": "Medium"},
        },
    },
}


def _as_dict(payload: dict) -> dict:
    """把 _record 回傳的 tuple 依 _COLS 對齊成 {col: value}，順帶守欄位對齊不變量。"""
    cols = [c.strip() for c in _COLS.split(",")]
    rec = _record(payload, "A")
    assert rec is not None
    assert len(cols) == len(rec), f"欄位數 {len(cols)} 與 tuple 長度 {len(rec)} 不一致"
    return dict(zip(cols, rec, strict=True))


def test_deep_fields_present_and_raw() -> None:
    d = _as_dict(_REAL)
    # 落地方位角／信心／擊球轉速
    assert d["hit_landing_bearing"] == -28.307495
    assert d["hit_landing_confidence"] == "Medium"
    assert d["hit_spin_rate"] == 1204.3561
    # 官方九係數原值保存（不 round）
    assert d["traj_x0"] == 16.698916056
    assert d["traj_x1"] == -39.94326276
    assert d["traj_x2"] == 4.884487056
    assert d["traj_y0"] == 2.134901496
    assert d["traj_y1"] == -1.851068688
    assert d["traj_y2"] == -2.087227728
    assert d["traj_z0"] == -0.48109632
    assert d["traj_z1"] == 1.732123536
    assert d["traj_z2"] == -1.504605576


def test_raw_coef_not_reconstructable_from_derived() -> None:
    """衍生 traj_accel_y = 2·Y[2] round(4) 有損；原始 traj_y2 必須是未 round 的官方值。"""
    d = _as_dict(_REAL)
    assert d["traj_accel_y"] == round(2.0 * -2.087227728, 4)  # 既有衍生值：-4.1745
    assert d["traj_y2"] == -2.087227728                       # 原值：不等於衍生反推
    assert d["traj_y2"] != d["traj_accel_y"] / 2.0


def test_existing_ivb_hb_unchanged() -> None:
    """非破壞性：既有 ivb_cm/hb_cm 公式維持不變。"""
    d = _as_dict(_REAL)
    t = 0.41
    assert d["ivb_cm"] == round(0.5 * (2.0 * -2.087227728 + 9.81) * t * t * 100.0, 2)
    assert d["hb_cm"] == round(0.5 * (2.0 * -1.504605576) * t * t * 100.0, 2)


def test_no_hit_event_leaves_hit_fields_null() -> None:
    """無擊球（Hit=null）投球：落地/擊球欄為 None，但軌跡九係數仍保存。"""
    payload = {k: v for k, v in _REAL.items() if k != "Trackman"}
    tm = {k: v for k, v in _REAL["Trackman"].items() if k != "Hit"}
    payload["Trackman"] = tm
    d = _as_dict(payload)
    assert d["hit_landing_bearing"] is None
    assert d["hit_landing_confidence"] is None
    assert d["hit_spin_rate"] is None
    assert d["traj_x0"] == 16.698916056  # 投球軌跡與擊球獨立


def test_missing_polyfit_yields_null_coefs() -> None:
    """無 PolyFit（設備缺／晚到）時九係數皆 None，且不影響其他欄位解析。"""
    import copy
    payload = copy.deepcopy(_REAL)
    del payload["Trackman"]["Pitch"]["Flight"]
    d = _as_dict(payload)
    for c in ("traj_x0", "traj_y1", "traj_z2"):
        assert d[c] is None
    assert d["hit_landing_confidence"] == "Medium"  # 擊球欄不受影響


def test_no_trackman_returns_none() -> None:
    """無 TrackMan 設備球場（Trackman=null）→ 不收（同舊版語意）。"""
    payload = {k: v for k, v in _REAL.items() if k != "Trackman"}
    assert _record(payload, "A") is None
