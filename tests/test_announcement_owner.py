"""常設owner純fixture，不啟Docker/Redis/SSH/DB或HTTP。"""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from cpbl.ingest import announcement_owner as module


def raw(status="SCHEDULED", name="甲"):
    return {"GameId":"2026-C-1","KindCode":"C","GameSno":1,"PreExeDate":"2026-10-17T17:05:00",
            "GameStatus":status,"Visiting":{"Team":{"Code":"ACN011"},"Hitters":[{"Lineup":1,"HitterAcnt":"0000000001","HitterName":name,"DefendStation":"C","DOB":"private","Hits":99}]},
            "Home":{"Team":{"Code":"AAA011"},"Hitters":[]}}


def owner(tmp_path, monkeypatch, actions):
    now=[100000.0]; calls=[]
    def store(game_id,payload,received):
        assert "DOB" not in str(payload) and "Hits" not in str(payload)
        actions.append((payload["GameStatus"], received))
        return {"action":"inserted" if len(actions)==1 or payload["GameStatus"]=="START" else "seen"}
    monkeypatch.setattr(module,"observe_projected",store)
    def run(*args,**kwargs):
        calls.append((args,kwargs));return SimpleNamespace(returncode=0)
    actor=module.AnnouncementOwner(tmp_path,lock=tmp_path/"refresh.lock",clock=lambda:now[0],runner=run)
    return actor,now,calls


def test_true_timestamps_survive_busy_refresh_and_restart_without_raw_extra_fields(tmp_path,monkeypatch):
    events=[]; actor,now,calls=owner(tmp_path,monkeypatch,events)
    actor.lock.mkdir()
    timestamp=datetime(2026,10,13,tzinfo=UTC)
    actor.observe("2026-C-1",raw(),timestamp)
    assert actor.after_cycle()["state"]=="deferred" and not events and not calls
    actor.lock.rmdir()
    restarted=module.AnnouncementOwner(tmp_path,lock=actor.lock,clock=lambda:now[0],runner=actor.runner)
    assert restarted.after_cycle()["state"]=="synced"
    assert events==[("SCHEDULED",timestamp)]
    assert calls[0][1]["env"]["LINEUP_ONLY"]=="1"
    assert not actor.lock.exists()


def test_last_seen_does_not_backup_each_poll_new_versions_coalesce_and_failed_sync_backs_off(tmp_path,monkeypatch):
    events=[]; actor,now,calls=owner(tmp_path,monkeypatch,events)
    actor.observe("2026-C-1",raw(),datetime(2026,10,13,tzinfo=UTC));actor.after_cycle()
    for sec in [60,120,180]:
        now[0]=100000+sec
        actor.observe("2026-C-1",raw(),datetime(2026,10,13,0,sec//60,tzinfo=UTC));actor.after_cycle()
    assert len(calls)==1
    actor.observe("2026-C-1",raw("START"),datetime(2026,10,17,tzinfo=UTC));actor.after_cycle()
    assert len(calls)==1
    now[0]=100300;actor.after_cycle();assert len(calls)==2
    now[0]+=21600; actor.state["last_seen"]=True
    actor.runner=lambda *a,**k:SimpleNamespace(returncode=69)
    assert actor.after_cycle()["state"]=="sync_failed"
    next_attempt=actor.state["next_attempt"]
    assert next_attempt>now[0] and actor.state["last_seen"]
    assert actor.after_cycle()["state"]=="idle"


def test_timeout_retains_uncertain_writer_lock_and_requires_handoff(tmp_path,monkeypatch):
    import subprocess
    events=[]; actor,now,calls=owner(tmp_path,monkeypatch,events)
    actor.observe("2026-C-1",raw(),datetime(2026,10,13,tzinfo=UTC))
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired("fixture",1200)
    actor.runner=timeout
    with pytest.raises(RuntimeError,match="remote stop"):
        actor.after_cycle()
    assert actor.lock.exists() and actor.state["paused"]
    with pytest.raises(RuntimeError,match="handoff"):
        module.AnnouncementOwner(tmp_path,lock=actor.lock)


def test_transient_persistence_error_keeps_original_observation_and_backs_off(tmp_path,monkeypatch):
    events=[];actor,now,_=owner(tmp_path,monkeypatch,events)
    timestamp=datetime(2026,10,13,tzinfo=UTC)
    actor.observe("2026-C-1",raw(),timestamp)
    def unavailable(*args):raise ConnectionError("synthetic")
    monkeypatch.setattr(module,"observe_projected",unavailable)
    assert actor.after_cycle()["state"]=="persistence_failed"
    assert actor.state["pending"][0]["fetched_at"]==timestamp.isoformat()
    assert actor.after_cycle()["reason"]=="persistence_backoff"
    assert not actor.lock.exists()


def test_maximum_cycle_observations_drain_without_losing_original_timestamps(tmp_path,monkeypatch):
    events=[]; actor,now,calls=owner(tmp_path,monkeypatch,events)
    for minute in range(8):
        actor.observe("2026-C-1",raw(),datetime(2026,10,13,0,minute,tzinfo=UTC))
    assert actor.after_cycle()["state"]=="synced"
    assert len(events)==8 and not actor.state["pending"] and len(calls)==1
    assert [time.minute for _,time in events]==list(range(8))


def test_replayed_commit_before_checkpoint_still_requires_protected_sync(tmp_path,monkeypatch):
    events=[]; actor,now,calls=owner(tmp_path,monkeypatch,events)
    actor.observe("2026-C-1",raw(),datetime(2026,10,13,tzinfo=UTC))
    monkeypatch.setattr(module,"observe_projected",lambda *args:{"action":"replayed"})
    assert actor.after_cycle()["state"]=="synced"
    assert len(calls)==1 and not actor.state["pending"]
