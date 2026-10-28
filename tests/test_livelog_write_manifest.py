"""#383 段 1 WP1-b：livelog 寫入端在同一交易讀回主表，把 manifest 記進 livelog revision 的 detail。"""

from __future__ import annotations

import json

from cpbl.ingest import cpbl_gamelog
from cpbl.ingest import pa_build as pb

KEY = (2026, "A", 1)


def new_events() -> list[dict]:
    base = {"year": 2026, "kind_code": "A", "game_sno": 1, "inning_seq": 1, "visiting_home_type": "1",
            "pitcher_acnt": "P1", "is_strike": True, "is_ball": False, "is_score": False,
            "is_change_player": False, "is_special_event": False, "content": "x"}
    return [{**base, "main_event_no": f"{i:010d}", "hitter_acnt": f"H{i}", "pitch_cnt": i}
            for i in range(1, 6)]


# ============================================================ 寫入端 manifest（WP1-b）
class _ReadbackCursor:
    def __init__(self, events):
        self.events = events

    def execute(self, sql, params=None):
        assert "FROM cpbl.game_livelog" in sql and params == KEY

    def fetchall(self):
        return [dict(e) for e in self.events]


def test_written_manifest_matches_builder_manifest_and_counts_residual() -> None:
    events = new_events()
    out = cpbl_gamelog._written_manifest(_ReadbackCursor(events), *KEY,
                                         {e["main_event_no"] for e in events})
    assert out == {"livelog_manifest_sha256": pb._livelog_manifest(events)[0],
                   "livelog_manifest_rows": 5, "livelog_residual_rows": 0,
                   "livelog_writer": pb.LIVELOG_WRITER_VERSION}
    residual = cpbl_gamelog._written_manifest(_ReadbackCursor(events), *KEY,
                                              {e["main_event_no"] for e in events[:4]})
    assert residual["livelog_residual_rows"] == 1


def _scrape_with(monkeypatch, *, manifest: dict | None) -> dict:
    payload = {"ScoreboardJson": "[]", "BattingJson": "[]", "PitchingJson": "[]",
               "LiveLogJson": json.dumps([{"MainEventNo": "0000000001", "Content": "x"}])}

    class _Session:
        def page_html(self, *_a, **_k):
            return '<input name="__RequestVerificationToken" value="tok" />'

        def post(self, *_a, **_k):
            return 200, json.dumps(payload)

    seen: list[dict] = []

    def fake_write(y, k, s, data, *, replace_extra):
        if manifest is not None:
            cpbl_gamelog.LIVELOG_WRITE_MANIFESTS[(y, k, s)] = manifest
        return 1, 0

    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: _Session())
    monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _d: None)
    monkeypatch.setattr(cpbl_gamelog, "_upsert", lambda _t, _c, _pk, rows: len(rows))
    monkeypatch.setattr(cpbl_gamelog, "record_box_pitching_revisions", lambda *_a: None)
    monkeypatch.setattr(cpbl_gamelog, "record_source_revision", lambda **k: seen.append(k))
    monkeypatch.setattr(cpbl_gamelog, "_write_livelog", fake_write)
    cpbl_gamelog.scrape_gamelogs(2026, [9], "A", delay=0)
    return next(k["detail"] for k in seen if k["source"] == "livelog")


def test_scrape_records_written_manifest_in_livelog_revision_detail(monkeypatch) -> None:
    m = {"livelog_manifest_sha256": "a" * 64, "livelog_manifest_rows": 1,
         "livelog_residual_rows": 0, "livelog_writer": pb.LIVELOG_WRITER_VERSION}
    detail = _scrape_with(monkeypatch, manifest=m)
    assert {k: detail[k] for k in m} == m and detail["event_rows"] == 1
    assert (2026, "A", 9) not in cpbl_gamelog.LIVELOG_WRITE_MANIFESTS


def test_scrape_without_written_manifest_leaves_detail_unbound(monkeypatch) -> None:
    detail = _scrape_with(monkeypatch, manifest=None)
    assert "livelog_manifest_sha256" not in detail
