from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pytest

import cpbl.change_signals
import cpbl.db
from cpbl.ingest import evening_receipt
from cpbl.ingest import postseason_evening as pe

DAY = date(2026, 11, 23)
PUBLISHED = datetime(2026, 11, 23, 14, tzinfo=UTC)
RESPONSE = "a" * 64


@pytest.fixture
def batch():
    offer = evening_receipt.make_offer(DAY, [(2026, "E", 4)], ["results"], b"test")
    receipt = {k: v for k, v in offer.items() if k != "snapshot_bytes"}
    at = PUBLISHED.isoformat()
    receipt.update(response_sha256=RESPONSE, published_at=at, rc=0, manifest={
        "at": at, "ok": True, "games": {"2026-E-4": {"results_ok": True}},
        "delivery_mode": "committed", "rows": {"games": 1},
    })
    return offer, receipt


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("games", [["2026", "E", 4]], "evening_game_scope"),
    ("games", [[2026, [], 4]], "evening_game_scope"),
    ("games", [[2026, "E", True]], "evening_game_scope"),
    ("games", [[2026, "E", 4], [2026, "E", 4]], "evening_game_order"),
    ("games", [[2026, "E", 5], [2026, "E", 4]], "evening_game_order"),
    ("parts", ["signals", "results"], "evening_parts"),
    ("as_of", 20261123, "evening_offer_date"),
    ("as_of", "20261123", "evening_offer_date"),
    ("snapshot_sha256", 42, "evening_snapshot_binding"),
    ("snapshot_bytes", True, "evening_snapshot_binding"),
    ("snapshot_bytes", evening_receipt.SNAPSHOT_LIMIT + 1, "evening_snapshot_binding"),
    ("batch_id", None, "evening_batch_identity"),
])
def test_offer_rejects_wrong_types_and_bindings(batch, field, value, reason):
    offer, _ = batch
    with pytest.raises(ValueError, match=reason):
        evening_receipt.validate_offer({**offer, field: value})


@pytest.mark.parametrize(("path", "value", "reason"), [
    (("response_sha256",), "b" * 64, "evening_receipt_binding"),
    (("published_at",), 42, "evening_receipt_time"),
    (("manifest",), [], "evening_receipt_reconcile"),
    (("manifest", "games"), ["2026-E-4"], "evening_receipt_reconcile"),
    (("manifest", "games"), {"2026-E-5": {}}, "evening_receipt_reconcile"),
    (("manifest", "rows"), {"games": True}, "evening_receipt_reconcile"),
    (("manifest", "games", "2026-E-4"), False, "evening_receipt_parts"),
])
def test_receipt_rejects_wrong_types_and_bindings(batch, path, value, reason):
    offer, receipt = batch
    current = receipt
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    with pytest.raises(ValueError, match=reason):
        evening_receipt.validate_receipt(receipt, offer, RESPONSE)


def test_only_fresh_matching_receipt_advances_once(batch):
    offer, receipt = batch
    original = {}
    sent = PUBLISHED - timedelta(minutes=1)
    now = PUBLISHED + timedelta(minutes=1)
    raw = evening_receipt.as_bytes(receipt)
    assert evening_receipt.advance(original, offer, RESPONSE, None, sent, now) == (original, "waiting")
    with pytest.raises(ValueError, match="evening_receipt_time_order"):
        evening_receipt.advance(original, offer, RESPONSE, raw, now, now)
    with pytest.raises(ValueError, match="evening_receipt_time_order"):
        evening_receipt.advance(original, offer, RESPONSE, raw, sent, sent)
    updated, state = evening_receipt.advance(original, offer, RESPONSE, raw, sent, now)
    assert state == "recorded" and original == {} and offer["batch_id"] in updated["boxpa_receipts"]
    assert evening_receipt.advance(updated, offer, RESPONSE, raw, sent, now) == (updated, "already_recorded")
    changed = deepcopy(receipt)
    changed["manifest"]["rows"]["games"] = 2
    with pytest.raises(ValueError, match="evening_receipt_changed"):
        evening_receipt.advance(updated, offer, RESPONSE, evening_receipt.as_bytes(changed), sent, now)


@pytest.mark.parametrize(("jobs", "pi", "action", "writes"), [
    (False, False, "sync", 1),
    (True, False, "idle", 1),
    (True, True, "idle", 0),
])
def test_evening_plan_queues_only_legacy_signal_sync(monkeypatch, tmp_path, capsys, jobs, pi, action, writes):
    path = tmp_path / "state.json"
    monkeypatch.setenv("POSTSEASON_STATE", str(path))
    monkeypatch.setenv("POSTSEASON_STARTER_FLAG", str(tmp_path / "checkpoints"))
    monkeypatch.setenv("POSTSEASON_STARTER_WATCH_FLAG", str(tmp_path / "starter-watch"))
    monkeypatch.setenv("CPBL_JOBS_PI_HANDOFF", "1" if pi else "0")
    monkeypatch.setattr(pe, "_now", lambda: PUBLISHED)
    monkeypatch.setattr(pe, "read_today_schedule", lambda _: (None, None))
    monkeypatch.setattr(pe, "evening_gate", lambda *_, **__: ("run", "fixture", ("E",)))
    monkeypatch.setattr(pe, "farm_final_due", lambda *_, **__: (False, "fixture"))
    monkeypatch.setattr(pe, "plan", lambda *_, **__: ("idle", "fixture"))
    pe.save_json(path, {**pe.empty_state(), "signals_dirty": True})
    calls = []

    from contextlib import nullcontext
    from types import SimpleNamespace

    monkeypatch.setattr(cpbl.db, "conn", lambda: nullcontext(SimpleNamespace(cursor=object)))

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return 1

    monkeypatch.setattr(cpbl.change_signals, "write_signals", record)
    assert pe.main(["plan"], jobs=jobs) == 0
    assert capsys.readouterr().out.strip() == action
    assert len(calls) == writes
    assert pe.load_state(path)["signals_unsynced"] is (not jobs)
