from __future__ import annotations

from fastapi.testclient import TestClient

from cpbl.api.main import app
from cpbl.config import settings


def test_plate_appearance_fails_closed_for_corrupt_artifact(tmp_path, monkeypatch):
    (tmp_path / "pa_sim.joblib").write_bytes(b"not-a-joblib-artifact")
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)

    response = TestClient(app).get(
        "/api/v1/outcome/plate-appearance",
        params={
            "hitter": "h", "pitcher": "p", "inning": 1, "half": "1",
            "away_score": 0, "home_score": 0, "bases": "___", "outs": 0,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"available": False, "reason": "pa_sim artifact 無法載入"}
