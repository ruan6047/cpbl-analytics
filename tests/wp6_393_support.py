"""原WP6專用pytest夾具；無CLI/任意命令/新產品能力，未grant不讀私有輸入。"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path
from unittest import mock

JOBS = ("scrape-daily", "postseason-evening", "weekly-box-revisions",
        "weekly-game-pitches", "schedule-watchdog", "alert-watch")
TABLES = frozenset((
    "games", "game_schedule_status_revisions", "game_source_revisions", "pitching_current",
    "batting_current", "fielding_current", "team_current", "team_standings", "player_transactions",
    "championship_members", "game_scoreboard", "game_livelog", "game_livelog_extra", "batting_gamelog",
    "pitching_gamelog", "box_pitching_revisions", "game_detail", "batter_pitcher_matchups",
    "advanced_stats", "pitch_tracking", "pitching_game_flags", "game_recap_builds",
    "game_recap_source_revisions", "game_plate_appearances", "game_pa_events", "game_pa_pitch_mappings",
    "model_versions", "team_der", "batter_wsb", "fielding_innings", "catcher_runs", "batter_traits",
    "pitcher_traits", "batter_re24", "pitcher_re24", "batting_splits", "pitching_splits",
    "batting_vs_team", "pitching_vs_team", "players", "team_comparison_build", "team_comparison_row",
    "team_comparison_current", "game_features", "refresh_log",
))
ROOT = Path(__file__).resolve().parents[1]


def require(value, tag):
    if not value:
        raise AssertionError(tag)  # 不將真row/token/DSN放入pytest斷言文字。


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), default=str) + "\n").encode()


def job_argv_ok(argv):
    fixed = (["scrape-daily"], ["postseason-evening", "--stage", "all"],
             ["postseason-evening", "--stage", "boxpa"], ["weekly-game-pitches", "--year", "2026"],
             ["schedule-watchdog"], ["alert-watch"])
    return argv in fixed or (len(argv) == 5 and argv[:4] ==
        ["weekly-box-revisions", "--year", "2026", "--days-back"]
        and argv[4].isdigit() and 1 <= int(argv[4]) <= 366)


def claim_case(output):
    (output / "invoked").open("x").close()


def load_plan():
    require(os.environ.get("CPBL_WP6_EXECUTE") == "1", "wp6_not_granted")
    path = Path(os.environ["CPBL_WP6_INPUTS"])
    require(path.is_absolute() and not path.is_symlink(), "wp6_input_path")
    info = path.stat()
    require(info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0 and info.st_size <= 1024**2,
            "wp6_input_privacy")
    raw = path.read_bytes(); plan = json.loads(raw)
    require(plan.get("sealed") is True and plan.get("product_source") ==
            "377f795ce1be2c11cc99f1c684fcb21e0763ffa3", "wp6_unsealed_or_wrong_source")
    require(plan["year"] == 2026 and set(plan["kinds"]) == {"A", "D", "E", "C"}, "wp6_scope")
    require(plan["lease_id"] and plan["creator_receipt_sha256"], "wp6_creator_binding")
    require(not os.path.lexists(Path.cwd() / ".env"), "wp6_no_cwd_dotenv")
    require(set(plan["tables"]) == TABLES, "wp6_original_table_scope")
    for name in ("statement_ms", "lock_ms", "rows_per_table", "private_bytes", "metadata_table_seconds"):
        require(type(plan["limits"][name]) is int and plan["limits"][name] > 0, "wp6_explicit_limits")
    root = Path(plan["private_root"])
    require(root.is_absolute() and root.resolve() == root and root.is_dir(), "wp6_private_root")
    require(root.stat().st_uid == os.geteuid() and root.stat().st_mode & 0o077 == 0, "wp6_root_owner")
    plan["input_sha256"] = digest(raw)
    os.umask(0o077)
    return plan


def asset(plan, item):
    path = Path(item["path"])
    require(path.is_absolute() and not path.is_symlink()
            and path.resolve().is_relative_to(Path(plan["private_root"])), "wp6_asset_scope")
    require(path.is_file() and path.stat().st_size == item["bytes"], "wp6_asset_size")
    require(item["bytes"] <= plan["limits"]["private_bytes"], "wp6_asset_budget")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while part := stream.read(1024**2):
            h.update(part)
    require(h.hexdigest() == item["sha256"], "wp6_asset_hash")
    return path


def checked_dsn(plan, reference=False):
    from psycopg.conninfo import conninfo_to_dict

    name = "CPBL_WP6_REFERENCE_DSN" if reference else "CPBL_ISOLATED_TEST_DSN"
    dsn = os.environ[name]; parsed = conninfo_to_dict(dsn)
    expected = plan["reference_database"] if reference else plan["database"]
    require(plan["database"] != plan["reference_database"], "wp6_reference_must_not_be_target")
    require(parsed.get("dbname") == expected, "wp6_database_binding")
    endpoint = plan["reference_endpoint" if reference else "database_endpoint"]
    require(all(parsed.get(key) == str(endpoint[key]) for key in ("host", "port", "user")),
            "wp6_database_endpoint_binding")
    if not reference:
        require(expected.startswith("cpbl393_wp6_") and parsed.get("port") != "5433", "wp6_isolated_database")
    return dsn


def database(plan, reference=False):
    import psycopg
    return psycopg.connect(checked_dsn(plan, reference), connect_timeout=5)


def transaction_game_fingerprint(connection, key):
    return connection.execute("""SELECT count(*), md5(COALESCE(string_agg(
        md5(to_jsonb(g)::text), '' ORDER BY g.game_season_code), ''))
        FROM cpbl.games g WHERE g.year=%s AND g.kind_code=%s AND g.game_sno=%s""",
        (key["year"], key["kind"], key["sno"])).fetchone()


def records(plan, table, reference=False):
    """真PG伺服器cursor，只輸出key與cell hash；不取出非key原值。"""
    from psycopg import sql

    require(table in TABLES, "wp6_table_whitelist")
    keys = plan["tables"][table]["keys"]
    require(keys and all(isinstance(k, str) and k.isidentifier() for k in keys), "wp6_table_keys")
    key = sql.SQL("jsonb_build_array({})::text").format(
        sql.SQL(",").join(sql.Identifier("t", k) for k in keys))
    query = sql.SQL("""SELECT {key}, md5(to_jsonb(t)::text),
        (SELECT jsonb_object_agg(e.key,md5(e.value::text)) FROM jsonb_each(to_jsonb(t)) e)
        FROM {table} t ORDER BY ({key}) COLLATE "C"
        """).format(
            key=key, table=sql.Identifier("cpbl", table))
    count = 0; started = time.monotonic(); previous_key = None
    with database(plan, reference) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SELECT set_config('statement_timeout',%s,true)", (str(plan["limits"]["statement_ms"]),))
        connection.execute("SELECT set_config('lock_timeout',%s,true)", (str(plan["limits"]["lock_ms"]),))
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        with connection.cursor(name="wp6_metadata") as cur:
            cur.execute(query)
            for key_value, row_hash, cells in cur:
                require(key_value != previous_key, "wp6_metadata_key_must_be_unique")
                previous_key = key_value
                count += 1
                require(count <= plan["limits"]["rows_per_table"]
                        and time.monotonic() - started <= plan["limits"]["metadata_table_seconds"], "wp6_metadata_budget")
                yield {"key": key_value, "row": row_hash, "cells": cells}


def compare_rows(before, after, reasons):
    """同SQL key次序merge；逐列留hash/欄名/明列歸因，永不輸出原值。"""
    a, b = iter(before), iter(after)
    left, right = next(a, None), next(b, None)
    while left is not None or right is not None:
        if right is None or left is not None and left["key"] < right["key"]:
            columns, key_value = ["__removed__"], left["key"]; old, new = left["row"], None
            left = next(a, None)
        elif left is None or right["key"] < left["key"]:
            columns, key_value = ["__added__"], right["key"]; old, new = None, right["row"]
            right = next(b, None)
        else:
            columns = sorted(k for k in left["cells"].keys() | right["cells"].keys()
                             if left["cells"].get(k) != right["cells"].get(k))
            key_value, old, new = left["key"], left["row"], right["row"]
            left, right = next(a, None), next(b, None)
        if columns:
            yield {"key_sha256": digest(key_value.encode()), "before": old, "after": new,
                   "columns": columns, "attribution": {k: reasons.get(k) for k in columns},
                   "attributed": all(bool(reasons.get(k)) for k in columns)}


def comparison(plan, case, output):
    summary = {}; used = 0
    for table in sorted(TABLES):
        for reason in case["reasons"].get(table, {}).values():
            require(isinstance(reason, dict) and reason.get("why")
                    and reason.get("evidence_sha256") in case["attribution_evidence_sha256"],
                    "wp6_difference_needs_real_source_attribution")
        # 兩個reader都保持READ ONLY，差異流式處理；上限屬同grant，不重試超量表。
        first, second = {"count": 0, "hash": hashlib.sha256()}, {"count": 0, "hash": hashlib.sha256()}

        def observed(rows, state):
            for row in rows:
                state["count"] += 1; state["hash"].update(json_bytes(row)); yield row

        path = output / (table + ".diff.jsonl"); differences = unknown = 0
        with path.open("xb") as stream:
            for diff in compare_rows(observed(records(plan, table, True), first),
                                     observed(records(plan, table), second), case["reasons"].get(table, {})):
                data = json_bytes(diff); used += len(data)
                require(used <= plan["limits"]["private_bytes"], "wp6_diff_budget")
                stream.write(data); differences += 1; unknown += int(not diff["attributed"])
        summary[table] = {"reference_count": first["count"], "target_count": second["count"],
                          "reference_sha256": first["hash"].hexdigest(), "target_sha256": second["hash"].hexdigest(),
                          "changed_rows": differences, "unattributed_rows": unknown,
                          "diff_sha256": file_sha256(path)}
    (output / "tables.json").write_bytes(json_bytes(summary))
    require(not any(x["unattributed_rows"] for x in summary.values()), "wp6_attribution_required_no_job_retry")
    return summary


def job_module():
    sys.path.insert(0, str(Path.cwd()))
    try:
        module = importlib.import_module("scripts.jobs")
    except ModuleNotFoundError as exc:
        if exc.name not in ("scripts", "scripts.jobs"):
            raise
        module = importlib.import_module("jobs.jobs")  # 已有runtime映像的固定layout。
    require(digest(Path(module.__file__).read_bytes()) ==
            "ee82a2608bc825b5f5dc7f3027bdf254b9eb5b423febad0a11d6699bcbb05e76", "wp6_product_jobs_source")
    return module


@contextlib.contextmanager
def original_job(plan, case_name, patches):
    """只替真capture的外部取件/httpx/通知邊界；真job/parser/SQL都保留。"""
    checked_dsn(plan)
    import httpx

    from cpbl import db
    from cpbl.config import settings
    from cpbl.ingest import (
        _job_source,
        _replay,
        cpbl_gamelog,
        cpbl_pitch_tracking,
        postseason_evening,
        run_refresh_recent,
    )

    case = plan["cases"][case_name]; output = Path(plan["private_root"]) / "results" / case_name
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not (output / "invoked").exists(), "wp6_case_already_started_no_job_retry")
    require(job_argv_ok(case["argv"]), "wp6_original_argv_only")
    app = output / "app"; app.mkdir(exist_ok=True); state = app / "logs"; state.mkdir(mode=0o700, exist_ok=True)
    # daily原有球種衍生依賴；只供給已封三個CSV，不替換classifier/fit結果。
    for item in case.get("mlb_csv", []):
        require(item["year"] in (2023, 2024, 2025), "wp6_original_mlb_year")
        source = asset(plan, item); target = app / "data/mlb" / f"mv{item['year']}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for item in case.get("state", []):
        source = asset(plan, item); relative = Path(item["destination"])
        require(not relative.is_absolute() and ".." not in relative.parts, "wp6_state_destination")
        target = state / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source.read_bytes())
    module = job_module(); patches.setattr(module, "CODE_ROOT", app)
    patches.setenv("DATABASE_URL", os.environ["CPBL_ISOLATED_TEST_DSN"])
    patches.setattr(settings, "database_url", os.environ["CPBL_ISOLATED_TEST_DSN"])
    patches.setenv("CPBL_JOBS_STATE_DIR", str(state)); patches.setenv("REFRESH_TRIGGER", "manual")
    for key, name in {"POSTSEASON_STATE": "postseason-evening-state.json",
                      "POSTSEASON_STATUS": "last-postseason-evening.json",
                      "POSTSEASON_TODAY_SCHEDULE": "daily-schedule-today.json",
                      "POSTSEASON_STARTER_FLAG": "postseason-starter-checkpoints.enabled",
                      "POSTSEASON_STARTER_WATCH_FLAG": "starter-watch.enabled",
                      "POSTSEASON_STARTER_WATCH_ALERT": "starter-watch-alert.json"}.items():
        patches.setenv(key, str(state / name))
    for key, value in case["environment"].items():
        require(key in {"DAILY_FORCE_FULL", "CPBL_SEASON_CLOSE", "REFRESH_POSTSEASON_KINDS",
                        "POSTSEASON_YEAR", "POSTSEASON_EVENING_KINDS"}, "wp6_env_scope")
        patches.setenv(key, str(value))
    patches.setattr(settings, "refresh_postseason_kinds", case["environment"].get("REFRESH_POSTSEASON_KINDS", ""))
    # 個別消費者時間，非全六job/正式系統凍鐘。
    if case.get("daily_date"):
        class BusinessDate(date):
            @classmethod
            def today(cls):
                return date.fromisoformat(case["daily_date"])
        patches.setattr(run_refresh_recent, "date", BusinessDate)
    if case.get("evening_at"):
        patches.setattr(postseason_evening, "_now", lambda: datetime.fromisoformat(case["evening_at"]))
    if case.get("watchdog_at"):
        evaluate = module.schedule_watch.evaluate_jobs
        patches.setattr(module.schedule_watch, "evaluate_jobs", lambda registry, root, now, url:
                        evaluate(registry, root, datetime.fromisoformat(case["watchdog_at"]), url))
    selected = {(int(x["year"]), x["kind"], int(x["sno"])) for x in case["sample_keys"]}
    require(all(y == 2026 and k in {"A", "D", "E", "C"} and s > 0 for y, k, s in selected), "wp6_true_game_scope")
    def narrowed(function, kind_position):
        def call(*args, **kwargs):
            values = function(*args, **kwargs)
            year = args[0]; kind = kwargs.get("kind_code", args[kind_position] if len(args) > kind_position else "A")
            kept = [s for s in values if (year, kind, s) in selected]
            return set(kept) if isinstance(values, set) else kept
        return call
    for obj, name, position in ((run_refresh_recent, "_completed_snos", 2),
                                (run_refresh_recent, "_missing_gamelog_snos", 1),
                                (run_refresh_recent, "_lagging_pitch_games", 1),
                                (cpbl_gamelog, "completed_snos_within_days", 1),
                                (cpbl_pitch_tracking, "completed_game_snos", 1)):
        patches.setattr(obj, name, narrowed(getattr(obj, name), position))
    verified = []
    trace = {"www": 0, "http": 0, "api": 0, "stats_fault": 0}
    def bump(name, count=1):
        trace[name] += count
        require(trace[name] <= case["maximum_boundary_calls"][name], "wp6_boundary_budget")
    for entry in case["www"]:
        manifest = asset(plan, entry["manifest"]); bundle = Path(entry["bundle"])
        require(bundle.resolve().is_relative_to(Path(plan["private_root"])), "wp6_bundle_scope")
        index = asset(plan, entry["index"])
        require(index == bundle / "index.json", "wp6_index_binding")
        replay = _replay.ReplaySession(manifest, bundle)
        require(replay.index["manifest_sha256"] == entry["manifest"]["sha256"], "wp6_manifest_binding")
        verified.append(replay)
    broken = None
    if case.get("www_fault") in ("corrupt", "oversized"):
        require(verified, "wp6_true_bundle_required")
        original = verified[0]; bad = output / "fault-bundle"; (bad / "responses").mkdir(parents=True)
        used = 0
        for row in original.index["entries"]:
            raw = _replay.www_fetch.read_response(original.bundle, row); used += len(raw)
            require(used <= plan["limits"]["private_bytes"], "wp6_copy_budget")
            (bad / row["body"]).write_bytes(raw)
        shutil.copyfile(original.bundle / "index.json", bad / "index.json")
        body = bad / original.index["entries"][0]["body"]
        with body.open("r+b") as stream:
            if case["www_fault"] == "oversized":
                require(used - body.stat().st_size + _replay.www_fetch.MAX_BODY_BYTES + 1
                        + (bad / "index.json").stat().st_size <= plan["limits"]["private_bytes"], "wp6_size_budget")
                stream.truncate(_replay.www_fetch.MAX_BODY_BYTES + 1)
            else:
                first = stream.read(1); require(first, "wp6_nonempty_body"); stream.seek(0)
                stream.write(bytes([first[0] ^ 1]))
        broken = bad

    def captured_fetch(self, requests):
        bump("www", len(requests))
        if case.get("www_fault") == "unavailable":
            from cpbl.ingest._replay import ReplayError
            raise ReplayError("wp6_injected_source_unavailable")
        if case.get("www_fault") == "expired":
            from datetime import UTC, timedelta
            manifest = json.loads(asset(plan, case["www"][0]["manifest"]).read_bytes())
            end = datetime.now(UTC) - timedelta(minutes=1)
            manifest["window"] = {"start": (end - timedelta(minutes=1)).isoformat(), "end": end.isoformat()}
            expired = output / "expired.json"; expired.write_bytes(json_bytes(manifest))
            with mock.patch("subprocess.Popen", side_effect=AssertionError("wp6_expired_must_not_spawn")):
                rc = _replay.www_fetch.main([str(expired), "--out", str(output / "expired-out")])
            require(rc != 0, "wp6_original_expiry_gate")
            raise _replay.ReplayError("wp6_expired_source")
        if broken is not None:
            return _replay.ReplaySession(asset(plan, case["www"][0]["manifest"]), broken)
        candidates = []
        for replay in verified:
            page = requests[0]["path"]
            if page not in replay._pages:
                continue
            if len(requests) == 1:
                candidates.append(replay); continue
            req = requests[1]
            for stored, response in replay._posts.get((page, req["api"]), []):
                if stored.get("form", {}) == req.get("form", {}) and stored.get("headers", {}) == req.get("headers", {}):
                    candidates.append((replay, response["sha256"]))
        require(candidates, "wp6_unrecorded_www_request")
        if len(requests) == 1:
            return candidates[0]  # 固定輸入次序的真page；post仍按真scope/符號重新驗。
        require(len({x[1] for x in candidates}) == 1, "wp6_ambiguous_true_capture")
        return candidates[0][0]

    patches.setattr(_job_source.SourceSession, "_fetch", captured_fetch)
    def captured_transport_init(self, source):
        # I/O替身不驗publisher/SFTP/FS權限；page/post/符號解析與真capture gate仍原碼。
        self.source, self.pages, self.exported = source, {}, None
    patches.setattr(_job_source.SourceSession, "__init__", captured_transport_init)
    patches.delenv("CPBL_REPLAY_MANIFEST", raising=False); patches.delenv("CPBL_REPLAY_BUNDLE", raising=False)
    real_init = httpx.Client.__init__

    def boundary(request):
        bump("http")
        for item in case["http"]:
            if item["method"] == request.method and item["url"] == str(request.url):
                if case.get("stats_fault_url") == item["url"]:
                    bump("stats_fault")
                    if case["stats_fault"] == "timeout":
                        raise httpx.ReadTimeout("wp6_injected_timeout", request=request)
                    return httpx.Response(403, request=request)
                return httpx.Response(item["status"], content=asset(plan, item).read_bytes(), request=request)
        raise AssertionError("wp6_unrecorded_http_request")

    def client_init(self, *args, **kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(boundary)); kwargs["trust_env"] = False
        return real_init(self, *args, **kwargs)
    patches.setattr(httpx.Client, "__init__", client_init)
    # API觀測用同進程原ASGI app+真PG，不造mock HTTP server；Redis只記外部健康依賴。
    import io
    import urllib.request

    import redis
    from fastapi.testclient import TestClient

    from cpbl.api.main import app as api_app
    patches.setenv("CPBL_JOBS_API_URL", "http://wp6-isolated/api/info")
    patches.setenv("REDIS_URL", "redis://wp6-boundary-only/0")
    class RedisBoundary:
        def ping(self):
            return case.get("redis_up", True)
        def close(self):
            pass
    patches.setattr(redis.Redis, "from_url", lambda *a, **kw: RedisBoundary())
    def api_boundary(request, **kwargs):
        require(request.full_url == "http://wp6-isolated/api/info", "wp6_no_other_urllib")
        bump("api")
        with TestClient(api_app) as client:
            response = client.get("/api/info")
        stream = io.BytesIO(response.content); stream.status = response.status_code
        return stream
    patches.setattr(urllib.request, "urlopen", api_boundary)
    # 此重播只收通知意圖，真正三個SaaS事件有獨立原node，不偷打production check。
    intents = []
    ping = module.alert_ping
    patches.setenv("CPBL_HC_PING_KEY", "fixture-intent-only"); patches.setenv("CPBL_HC_API_KEY", "fixture-intent-only")
    patches.setenv("CPBL_ALERT_SLUG_OVERRIDE", "test")
    patches.setattr(ping, "ping", lambda config, check, signal, **kw:
                    intents.append((check, signal)) or ping.Result("ping", check, True, True))
    patches.setattr(ping, "arm_schedule", lambda config, check, **kw: ping.Result("arm", check, True, True))
    try:
        yield module, case, output, intents, trace
    finally:
        if db._pool is not None:
            db._pool.close(); db._pool = None


def run_job(plan, case_name, patches):
    with original_job(plan, case_name, patches) as (module, case, output, intents, trace):
        argv = case["argv"]
        require(argv[0] in JOBS, "wp6_job_scope")
        with (output / "job.stdout.private").open("w") as stream, contextlib.redirect_stdout(stream):
            claim_case(output)
            rc = module.main(argv)
        result = {"case": case_name, "input_sha256": plan["input_sha256"], "job_exit": rc,
                  "notification_intents": intents, "boundary_calls": trace,
                  "transport": "captured_real_bytes_external_boundary_only"}
        (output / "job-result.json").write_bytes(json_bytes(result))
        require(rc == case["expected_exit"], "wp6_job_exit")
        for boundary_name, minimum in case["minimum_boundary_calls"].items():
            require(trace[boundary_name] >= minimum, "wp6_required_boundary_not_reached")
        comparison(plan, case, output)
        return output, result


def real_prediction(plan, patches, output):
    """只控API此consumer的歷史選列/日期；真PG rows、原ASGI/現役model.predict。"""
    checked_dsn(plan)
    from fastapi.testclient import TestClient

    from cpbl.api import pregame_serving
    from cpbl.api.main import app
    from cpbl.api.routers import outcome

    path = asset(plan, plan["artifact"])
    patches.setattr(pregame_serving, "artifact_path", lambda: path)
    artifact, _ = pregame_serving.serving_state()
    require(artifact is not None, "wp6_real_serving_artifact_required")
    model_type = type(artifact["model"]); predict = model_type.predict; calls = []
    def observed(self, rows):
        calls.append(len(rows)); return predict(self, rows)
    patches.setattr(model_type, "predict", observed)
    real_loader = outcome.load_outcome_rows
    patches.setattr(outcome, "load_outcome_rows", lambda completed_only=False: real_loader(completed_only=True))
    class PredictionDate(date):
        @classmethod
        def today(cls):
            return date.fromisoformat(plan["prediction_date"])
    patches.setattr(outcome, "date", PredictionDate)
    with TestClient(app) as client:
        response = client.get("/api/v1/outcome/pregame?limit=1")
    data = response.json()
    (output / "pregame-response.private.json").write_bytes(response.content)
    require(response.status_code == 200 and data.get("available") is True and data.get("items") and calls,
            "wp6_nonempty_real_prediction_required")
    key = (data["items"][0]["season"], data["items"][0]["game_sno"])
    require(list(key) in plan["prediction_keys"], "wp6_prediction_true_scope")
    require(file_sha256(path) == plan["artifact"]["sha256"], "wp6_artifact_must_not_change")
    return {"api_status": 200, "items": len(data["items"]), "predict_calls": len(calls),
            "response_sha256": digest(response.content), "artifact_sha256": plan["artifact"]["sha256"],
            "test_only_selection": "existing completed_only=True plus API date filter; no row/weight fabrication"}


def test_check_event(plan, event):
    """原三個SaaS事件，用既有helper與HTTP工具；只在單獨核發node執行。"""
    import urllib.parse
    import urllib.request
    sys.path.insert(0, str(Path.cwd()))
    try:
        alert_ping = importlib.import_module("scripts.alert_ping")
    except ModuleNotFoundError as exc:
        if exc.name not in ("scripts", "scripts.alert_ping"):
            raise
        alert_ping = importlib.import_module("jobs.alert_ping")

    require(os.environ.get("CPBL_WP6_HC_EXECUTE") == "1", "wp6_hc_not_granted")
    require(event in ("failed", "interrupted", "silent"), "wp6_original_hc_scope")
    spec = plan["healthchecks"]; config = alert_ping.load_config(use_environment=True)
    require(config.slug_override == "test" and config.api_ready and config.ping_ready, "wp6_test_only_config")
    require(all(urllib.parse.urlsplit(url).hostname in spec["allowed_hosts"]
                for url in (config.api_base, config.ping_base)), "wp6_hc_destination")
    headers = {"X-Api-Key": config.api_key, "User-Agent": alert_ping.USER_AGENT}
    lookup = config.api_base + "/checks/?slug=test"
    def read():
        ok, _, _, body = alert_ping._request(config, urllib.request.Request(lookup, headers=headers),
                                             opener=None, sleep=time.sleep)
        require(ok, "wp6_hc_read_failed")
        checks = [x for x in json.loads(body)["checks"] if x.get("slug") == "test"]
        require(len(checks) == 1, "wp6_unique_test_check")
        require(checks[0].get("uuid") == spec["check_uuid"], "wp6_bound_test_check_uuid")
        return checks[0]
    before = read(); restore = {key: before[key] for key in ("schedule", "tz", "grace", "timeout")}
    require(isinstance(restore["schedule"], str) and isinstance(restore["tz"], str)
            and type(restore["grace"]) is int and type(restore["timeout"]) is int, "wp6_original_hc_format")
    require(type(spec["max_polls"]) is int and spec["max_polls"] > 0
            and spec["poll_seconds"] > 0 and spec["notification_seconds"] > 0, "wp6_hc_explicit_budget")
    require(urllib.parse.urlsplit(before["update_url"]).hostname in spec["allowed_hosts"], "wp6_hc_restore_destination")
    rid = alert_ping.run_id(plan["lease_id"] + ":" + event)
    root = Path(plan["private_root"]) / "results"; root.mkdir(exist_ok=True)
    snapshot = root / ("hc-" + event + "-original.private.json")
    snapshot.write_bytes(json_bytes(restore))
    (root / ("hc-" + event + "-mutation.invoked")).open("x").close()
    down = False; restored = False
    try:
        armed = alert_ping.arm_schedule(config, "test", cron=spec["schedule"], tz=spec["tz"],
                                        grace_seconds=spec["grace"])
        require(armed.ok, "wp6_hc_arm_failed")
        signal = 1 if event == "failed" else "start" if event == "interrupted" else "success"
        require(alert_ping.ping(config, "test", signal, rid=rid).ok, "wp6_test_event_failed")
        for _ in range(spec["max_polls"]):
            if read()["status"] == "down":
                down = True; break
            time.sleep(spec["poll_seconds"])
    finally:
        request = urllib.request.Request(before["update_url"], data=json_bytes(restore), method="POST",
                                         headers={**headers, "Content-Type": "application/json"})
        ok, _, _, _ = alert_ping._request(config, request, opener=None, sleep=time.sleep)
        try:
            after = read() if ok else {}
            restored = ok and all(after.get(key) == value for key, value in restore.items())
        finally:
            reset = alert_ping.ping(config, "test", "success", rid=rid)
            restored = restored and reset.ok
    require(down and restored, "wp6_hc_down_and_restore_required")
    # 通知由原端點owner提供原生證據，不能用API down冒送達；未到就此原項未完成。
    binding_path = Path(spec["notification_bindings"][event])
    require(binding_path.is_absolute() and binding_path.resolve().is_relative_to(Path(plan["private_root"]))
            and not binding_path.is_symlink(), "wp6_notification_scope")
    deadline = time.monotonic() + spec["notification_seconds"]
    while not binding_path.exists() and time.monotonic() < deadline:
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    require(binding_path.exists() and binding_path.stat().st_size <= 4096, "wp6_notification_evidence_missing")
    binding = json.loads(binding_path.read_bytes())
    require(binding["lease_id"] == plan["lease_id"] and binding["event"] == event and binding["rid"] == rid
            and binding["check_uuid"] == spec["check_uuid"] and binding["delivered"] is True,
            "wp6_notification_event_binding")
    notification = asset(plan, binding["artifact"])
    return {"event": event, "down_read_back": down, "restored": restored,
            "notification_evidence_sha256": file_sha256(notification)}
